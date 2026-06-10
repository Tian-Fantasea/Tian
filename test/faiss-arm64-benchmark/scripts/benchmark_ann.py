#!/usr/bin/env python3
import json
import time
import argparse
import datetime
import os
import numpy as np
import faiss

INDEX_CONFIGS = {
    "FlatL2": {
        "constructor": lambda d: faiss.IndexFlatL2(d),
        "description": "Exact brute-force L2 search",
        "needs_training": False,
    },
    "IVFFlat": {
        "constructor": lambda d: faiss.IndexIVFFlat(faiss.IndexFlatL2(d), d, 100),
        "description": "Inverted file with flat L2 quantizer, 100 lists",
        "needs_training": True,
        "nlist": 100,
    },
    "IVFPQ": {
        "constructor": lambda d: faiss.IndexIVFPQ(faiss.IndexFlatL2(d), d, 100, 8, 8),
        "description": "Inverted file with Product Quantization, 100 lists, 8 sub-quantizers, 8 bits",
        "needs_training": True,
        "nlist": 100,
    },
    "HNSWFlat": {
        "constructor": lambda d: faiss.IndexHNSWFlat(d, 32),
        "description": "HNSW graph-based index, M=32",
        "needs_training": False,
    },
    "PQ": {
        "constructor": lambda d: faiss.IndexPQ(d, 8, 8),
        "description": "Product Quantization standalone, 8 sub-quantizers, 8 bits",
        "needs_training": True,
    },
}

SCALE_MAP = {
    "1M": 1000000,
    "10M": 10000000,
    "100M": 100000000,
}

def generate_data(n, d, seed=42):
    np.random.seed(seed)
    xb = np.random.random((n, d)).astype('float32')
    nq = min(10000, n // 10)
    xq = np.random.random((nq, d)).astype('float32')
    return xb, xq

def compute_recall(I_approx, gt_I, k):
    nq = I_approx.shape[0]
    recall = 0.0
    for i in range(nq):
        recall += len(set(I_approx[i].tolist()) & set(gt_I[i].tolist())) / k
    return recall / nq

def benchmark_index(index_name, config, xb, xq, d, k, iterations, gt_D, gt_I):
    results = []
    n = xb.shape[0]
    nq = xq.shape[0]

    for iteration in range(iterations):
        print(f'[ANN] {index_name} iteration {iteration+1}/{iterations}')

        index = config["constructor"](d)

        build_start = time.time()
        if config["needs_training"]:
            nlist = config.get("nlist", 100)
            training_size = min(n, max(nlist * 256, 50000))
            train_data = xb[:training_size]
            index.train(train_data)
        train_time = time.time() - build_start

        add_start = time.time()
        index.add(xb)
        add_time = time.time() - add_start
        build_time = time.time() - build_start

        search_start = time.time()
        D, I = index.search(xq, k)
        search_time = time.time() - search_start

        qps = nq / search_time if search_time > 0 else 0
        latency_per_query_us = (search_time / nq) * 1e6 if nq > 0 else 0

        recall = compute_recall(I, gt_I, k)

        mem_bytes = 0
        if hasattr(index, 'ntotal'):
            try:
                import faiss
                serialized = faiss.serialize_index(index)
                mem_bytes = len(serialized)
            except Exception:
                mem_bytes = 0

        result = {
            "iteration": iteration + 1,
            "build_time_s": round(build_time, 4),
            "train_time_s": round(train_time, 4),
            "add_time_s": round(add_time, 4),
            "search_time_s": round(search_time, 6),
            "qps": round(qps, 2),
            "latency_per_query_us": round(latency_per_query_us, 2),
            f"recall_at_{k}": round(recall, 4),
            "index_size_bytes": mem_bytes,
            "num_vectors": n,
            "num_queries": nq,
        }
        results.append(result)

    avg_results = {}
    keys = [k for k in results[0].keys() if k != "iteration"]
    for key in keys:
        vals = [r[key] for r in results]
        avg_results[key] = round(sum(vals) / len(vals), 4)

    return avg_results, results

def main():
    parser = argparse.ArgumentParser(description='Faiss ANN Benchmark (ann-benchmarks methodology)')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--data-scale', default='1M', choices=list(SCALE_MAP.keys()))
    parser.add_argument('--data-dim', type=int, default=128)
    parser.add_argument('--iterations', type=int, default=3)
    parser.add_argument('--k', type=int, default=10)
    args = parser.parse_args()

    n = SCALE_MAP[args.data_scale]
    d = args.data_dim
    k = args.k

    print(f'[ANN] Generating {n} vectors of dimension {d}...')
    xb, xq = generate_data(n, d)
    nq = xq.shape[0]

    print(f'[ANN] Computing ground truth with IndexFlatL2...')
    gt_index = faiss.IndexFlatL2(d)
    gt_index.add(xb)
    gt_D, gt_I = gt_index.search(xq, k)

    all_results = {}
    detailed_results = {}

    for index_name, config in INDEX_CONFIGS.items():
        print(f'[ANN] Benchmarking {index_name}: {config["description"]}')
        try:
            avg, detailed = benchmark_index(
                index_name, config, xb, xq, d, k, args.iterations, gt_D, gt_I
            )
            all_results[index_name] = avg
            detailed_results[index_name] = detailed
        except Exception as e:
            print(f'[ANN] ERROR benchmarking {index_name}: {e}')
            all_results[index_name] = {"error": str(e)}

    output = {
        "benchmark": "ann_search",
        "description": "Approximate Nearest Neighbor search benchmark following ann-benchmarks methodology",
        "reference": "https://github.com/erikbern/ann-benchmarks",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "qps": {
                "unit": "queries/sec",
                "description": "Queries per second throughput"
            },
            "recall_at_k": {
                "unit": "ratio (0-1)",
                "description": f"Recall@{k} - fraction of true nearest neighbors found"
            },
            "build_time": {
                "unit": "seconds",
                "description": "Total time to train and add vectors to index"
            },
            "latency_per_query": {
                "unit": "microseconds",
                "description": "Average latency per single query"
            },
            "index_size": {
                "unit": "bytes",
                "description": "Serialized index size in memory"
            }
        },
        "dataset_info": {
            "name": "synthetic_random_float32",
            "size": f"{args.data_scale} vectors x {d} dimensions",
            "source": "numpy random uniform distribution"
        },
        "parameters": {
            "num_vectors": n,
            "dimension": d,
            "num_queries": nq,
            "k": k,
            "iterations": args.iterations
        },
        "results_summary": all_results,
        "results_detailed": detailed_results
    }

    output_path = os.path.join(args.results_dir, 'benchmark_ann.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'[ANN] Results saved to: {output_path}')
    for name, res in all_results.items():
        if "error" not in res:
            print(f'[ANN] {name}: QPS={res["qps"]}, Recall@{k}={res[f"recall_at_{k}"]}, Build={res["build_time_s"]}s')
    print('[ANN] Benchmark complete')

if __name__ == '__main__':
    main()