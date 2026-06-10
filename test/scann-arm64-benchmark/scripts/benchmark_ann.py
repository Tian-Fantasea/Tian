#!/usr/bin/env python3
import json
import time
import argparse
import datetime
import os
import numpy as np
import scann

SCALE_MAP = {
    "1M": 1000000,
    "10M": 10000000,
}

INDEX_CONFIGS = {
    "BruteForce_L2": {
        "builder_fn": lambda data, k: scann.scann_ops_pybind.builder(data, k, "squared_l2").score_brute_force().build(),
        "description": "Brute-force exact search with squared L2 distance",
        "needs_partitioning": False,
    },
    "AH_NoPartition_L2": {
        "builder_fn": lambda data, k: scann.scann_ops_pybind.builder(data, k, "squared_l2").score_ah(
            dimensions_per_block=2, anisotropic_quantization_threshold=0.2).build(),
        "description": "Asymmetric Hashing scoring only (no partitioning), dims_per_block=2",
        "needs_partitioning": False,
    },
    "TreeAH_Rescore_L2": {
        "builder_fn": lambda data, k, n: scann.scann_ops_pybind.builder(data, k, "squared_l2").tree(
            num_leaves=int(np.sqrt(n)), num_leaves_to_search=1, training_sample_size=min(n, 50000)).score_ah(
            dimensions_per_block=2, anisotropic_quantization_threshold=0.2).reorder(
            reordering_num_neighbors=100).build(),
        "description": "Full 3-phase: Partitioning (sqrt(n) leaves) + AH scoring + Rescoring (100 neighbors)",
        "needs_partitioning": True,
    },
    "TreeAH_Rescore_IP": {
        "builder_fn": lambda data, k, n: scann.scann_ops_pybind.builder(data, k, "dot_product").tree(
            num_leaves=int(np.sqrt(n)), num_leaves_to_search=1, training_sample_size=min(n, 50000)).score_ah(
            dimensions_per_block=2, anisotropic_quantization_threshold=0.2).reorder(
            reordering_num_neighbors=100).build(),
        "description": "Full 3-phase with dot product distance",
        "needs_partitioning": True,
    },
    "BruteForce_Qnt_L2": {
        "builder_fn": lambda data, k: scann.scann_ops_pybind.builder(data, k, "squared_l2").score_brute_force(
            quantize=True).build(),
        "description": "Quantized brute-force (8-bit quantization for memory bandwidth optimization)",
        "needs_partitioning": False,
    },
}

LEAVES_TO_SEARCH_VALUES = [1, 2, 3, 5, 10, 20]

def compute_ground_truth_l2(data, queries, k):
    nq = queries.shape[0]
    gt_I = np.zeros((nq, k), dtype=np.int64)
    chunk = 500
    for i in range(0, nq, chunk):
        end = min(i + chunk, nq)
        dists = np.sum((queries[i:end].reshape(end - i, 1, -1) - data.reshape(1, data.shape[0], -1)) ** 2, axis=2)
        gt_I[i:end] = np.argsort(dists, axis=1)[:, :k]
    return gt_I

def compute_ground_truth_ip(data, queries, k):
    nq = queries.shape[0]
    gt_I = np.zeros((nq, k), dtype=np.int64)
    chunk = 500
    for i in range(0, nq, chunk):
        end = min(i + chunk, nq)
        sims = np.dot(queries[i:end], data.T)
        gt_I[i:end] = np.argsort(-sims, axis=1)[:, :k]
    return gt_I

def compute_recall(indices, gt_I, k):
    nq = indices.shape[0]
    recall = 0.0
    for i in range(nq):
        recall += len(set(indices[i].tolist()) & set(gt_I[i].tolist())) / k
    return recall / nq

def benchmark_config(config_name, config, data, queries, d, k, n, iterations, gt_I):
    results = []
    nq = queries.shape[0]

    for iteration in range(iterations):
        print(f'[ANN] {config_name} iteration {iteration+1}/{iterations}')

        build_start = time.time()
        if config["needs_partitioning"]:
            searcher = config["builder_fn"](data, k, n)
        else:
            searcher = config["builder_fn"](data, k)
        build_time = time.time() - build_start

        search_start = time.time()
        indices, distances = searcher.search_batched(queries, final_num_neighbors=k)
        search_time = time.time() - search_start

        qps = nq / search_time if search_time > 0 else 0
        latency_per_query_us = (search_time / nq) * 1e6 if nq > 0 else 0
        recall = compute_recall(indices, gt_I, k)

        result = {
            "iteration": iteration + 1,
            "build_time_s": round(build_time, 4),
            "search_time_s": round(search_time, 6),
            "qps": round(qps, 2),
            "latency_per_query_us": round(latency_per_query_us, 2),
            f"recall_at_{k}": round(recall, 4),
            "num_vectors": n,
            "num_queries": nq,
        }
        results.append(result)

    avg_results = {}
    keys = [key for key in results[0].keys() if key != "iteration"]
    for key in keys:
        vals = [r[key] for r in results]
        avg_results[key] = round(sum(vals) / len(vals), 4) if isinstance(vals[0], float) else vals[0]

    return avg_results, results

def benchmark_tree_ah_leaves_sweep(data, queries, d, k, n, iterations, gt_I):
    num_leaves = int(np.sqrt(n))
    sweep_results = {}

    for leaves_to_search in LEAVES_TO_SEARCH_VALUES:
        label = f"leaves_to_search_{leaves_to_search}"
        print(f'[ANN] TreeAH leaves sweep: {label}')

        run_results = []
        for iteration in range(iterations):
            searcher = scann.scann_ops_pybind.builder(data, k, "squared_l2").tree(
                num_leaves=num_leaves, num_leaves_to_search=leaves_to_search,
                training_sample_size=min(n, 50000)
            ).score_ah(
                dimensions_per_block=2, anisotropic_quantization_threshold=0.2
            ).reorder(
                reordering_num_neighbors=100
            ).build()

            start = time.time()
            indices, distances = searcher.search_batched(queries, final_num_neighbors=k)
            elapsed = time.time() - start

            nq = queries.shape[0]
            qps = nq / elapsed if elapsed > 0 else 0
            latency_us = (elapsed / nq) * 1e6 if nq > 0 else 0
            recall = compute_recall(indices, gt_I, k)

            run_results.append({
                "time_s": elapsed,
                "qps": round(qps, 2),
                f"recall_at_{k}": round(recall, 4),
                "latency_per_query_us": round(latency_us, 2),
            })

        avg_time = round(sum(r["time_s"] for r in run_results) / len(run_results), 6)
        avg_qps = round(sum(r["qps"] for r in run_results) / len(run_results), 2)
        avg_recall = round(sum(r[f"recall_at_{k}"] for r in run_results) / len(run_results), 4)
        avg_latency = round(sum(r["latency_per_query_us"] for r in run_results) / len(run_results), 2)

        sweep_results[label] = {
            "avg_time_s": avg_time,
            "avg_qps": avg_qps,
            f"avg_recall_at_{k}": avg_recall,
            "avg_latency_per_query_us": avg_latency,
            "leaves_to_search": leaves_to_search,
            "num_leaves": num_leaves,
        }

    return sweep_results

def main():
    parser = argparse.ArgumentParser(description='ScaNN ANN Benchmark (ann-benchmarks methodology)')
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
    np.random.seed(42)
    data = np.random.random((n, d)).astype('float32')
    nq = min(10000, n // 10)
    queries = np.random.random((nq, d)).astype('float32')

    print(f'[ANN] Computing ground truth for L2...')
    gt_I = compute_ground_truth_l2(data, queries, k)

    all_results = {}
    detailed_results = {}

    for config_name, config in INDEX_CONFIGS.items():
        if config_name == "TreeAH_Rescore_IP":
            gt_I_ip = compute_ground_truth_ip(data, queries, k)
            print(f'[ANN] Benchmarking {config_name}: {config["description"]}')
            try:
                avg, detailed = benchmark_config(
                    config_name, config, data, queries, d, k, n, args.iterations, gt_I_ip
                )
                all_results[config_name] = avg
                detailed_results[config_name] = detailed
            except Exception as e:
                print(f'[ANN] ERROR benchmarking {config_name}: {e}')
                all_results[config_name] = {"error": str(e)}
        else:
            print(f'[ANN] Benchmarking {config_name}: {config["description"]}')
            try:
                avg, detailed = benchmark_config(
                    config_name, config, data, queries, d, k, n, args.iterations, gt_I
                )
                all_results[config_name] = avg
                detailed_results[config_name] = detailed
            except Exception as e:
                print(f'[ANN] ERROR benchmarking {config_name}: {e}')
                all_results[config_name] = {"error": str(e)}

    print('[ANN] Running TreeAH leaves_to_search parameter sweep...')
    try:
        sweep = benchmark_tree_ah_leaves_sweep(data, queries, d, k, n, args.iterations, gt_I)
        all_results["TreeAH_leaves_sweep"] = sweep
    except Exception as e:
        print(f'[ANN] ERROR in leaves sweep: {e}')
        all_results["TreeAH_leaves_sweep"] = {"error": str(e)}

    output = {
        "benchmark": "ann_search",
        "description": "Approximate Nearest Neighbor search benchmark for ScaNN following ann-benchmarks methodology",
        "reference": "https://ann-benchmarks.com and https://github.com/google-research/google-research/tree/master/scann",
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
                "description": "Time to build ScaNN searcher"
            },
            "latency_per_query": {
                "unit": "microseconds",
                "description": "Average latency per single query"
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
            "iterations": args.iterations,
            "leaves_to_search_values": LEAVES_TO_SEARCH_VALUES,
        },
        "results_summary": all_results,
        "results_detailed": detailed_results
    }

    output_path = os.path.join(args.results_dir, 'benchmark_ann.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'[ANN] Results saved to: {output_path}')
    for name, res in all_results.items():
        if isinstance(res, dict) and "error" in res:
            print(f'[ANN] {name}: ERROR - {res["error"]}')
        elif isinstance(res, dict) and "qps" in res:
            recall_key = f"recall_at_{k}"
            print(f'[ANN] {name}: QPS={res["qps"]}, Recall@{k}={res.get(recall_key, "N/A")}, Build={res.get("build_time_s", "N/A")}s')
        elif isinstance(res, dict) and "TreeAH_leaves_sweep" not in name:
            for sub_name, sub_res in res.items():
                print(f'[ANN] {name}/{sub_name}: QPS={sub_res.get("avg_qps", "N/A")}, Recall={sub_res.get(f"avg_recall_at_{k}", "N/A")}')
    print('[ANN] Benchmark complete')

if __name__ == '__main__':
    main()