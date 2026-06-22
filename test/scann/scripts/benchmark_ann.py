#!/usr/bin/env python3
import json
import time
import os
import sys
import numpy as np
import datetime

try:
    import scann
except ImportError:
    print("[ERROR] scann module not installed")
    sys.exit(1)

SCALE_MAP = {
    "100K": 100000,
    "1M": 1000000,
    "10M": 10000000,
}

INDEX_CONFIGS = {
    "BruteForce_L2": {
        "builder_fn": "score_brute_force",
        "description": "Brute-force exact search with squared L2 distance",
        "needs_partitioning": False,
    },
    "AH_NoPartition_L2": {
        "builder_fn": "score_ah",
        "description": "Asymmetric Hashing scoring only (no partitioning), dims_per_block=2",
        "needs_partitioning": False,
    },
    "TreeAH_Rescore_L2": {
        "builder_fn": "tree_ah_rescore",
        "description": "Full 3-phase: Partitioning + AH scoring + Rescoring (100 neighbors)",
        "needs_partitioning": True,
    },
    "BruteForce_Qnt_L2": {
        "builder_fn": "score_brute_force_quantized",
        "description": "Quantized brute-force (8-bit quantization for memory bandwidth optimization)",
        "needs_partitioning": False,
    },
}

LEAVES_TO_SEARCH_VALUES = [1, 2, 5]


def compute_ground_truth_l2(data, queries, k):
    nq = queries.shape[0]
    gt_I = np.zeros((nq, k), dtype=np.int64)
    chunk = min(500, nq)
    for i in range(0, nq, chunk):
        end = min(i + chunk, nq)
        dists = np.sum((queries[i:end].reshape(end - i, 1, -1) - data.reshape(1, data.shape[0], -1)) ** 2, axis=2)
        gt_I[i:end] = np.argsort(dists, axis=1)[:, :k]
    return gt_I


def compute_recall(indices, gt_I, k):
    nq = indices.shape[0]
    recall = 0.0
    for i in range(nq):
        recall += len(set(indices[i].tolist()) & set(gt_I[i].tolist())) / k
    return recall / nq


def build_searcher(config_name, config, data, k, n):
    builder = scann.scann_ops_pybind.builder(data, k, "squared_l2")
    if config_name == "BruteForce_L2":
        return builder.score_brute_force().build()
    elif config_name == "AH_NoPartition_L2":
        return builder.score_ah(dimensions_per_block=2, anisotropic_quantization_threshold=0.2).build()
    elif config_name == "TreeAH_Rescore_L2":
        return builder.tree(
            num_leaves=int(np.sqrt(n)), num_leaves_to_search=1,
            training_sample_size=min(n, 50000)
        ).score_ah(
            dimensions_per_block=2, anisotropic_quantization_threshold=0.2
        ).reorder(
            reordering_num_neighbors=100
        ).build()
    elif config_name == "BruteForce_Qnt_L2":
        return builder.score_brute_force(quantize=True).build()
    else:
        return builder.score_brute_force().build()


def benchmark_config(config_name, config, data, queries, k, n, iterations, gt_I):
    results = []
    nq = queries.shape[0]

    for iteration in range(iterations):
        print(f'[ANN] {config_name} iteration {iteration+1}/{iterations}')
        build_start = time.time()
        searcher = build_searcher(config_name, config, data, k, n)
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
        del searcher

    avg_results = {}
    keys = [key for key in results[0].keys() if key != "iteration"]
    for key in keys:
        vals = [r[key] for r in results]
        avg_results[key] = round(sum(vals) / len(vals), 4) if isinstance(vals[0], float) else vals[0]

    return avg_results, results


def benchmark_tree_ah_leaves_sweep(data, queries, k, n, iterations, gt_I):
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
            del searcher

        avg_qps = round(sum(r["qps"] for r in run_results) / len(run_results), 2)
        avg_recall = round(sum(r[f"recall_at_{k}"] for r in run_results) / len(run_results), 4)
        avg_latency = round(sum(r["latency_per_query_us"] for r in run_results) / len(run_results), 2)

        sweep_results[label] = {
            "avg_qps": avg_qps,
            f"avg_recall_at_{k}": avg_recall,
            "avg_latency_per_query_us": avg_latency,
            "leaves_to_search": leaves_to_search,
            "num_leaves": num_leaves,
        }

    return sweep_results


def main():
    results_dir = os.environ.get("RESULTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
    data_scale = os.environ.get("DATA_SCALE", "100K")
    data_dim = int(os.environ.get("DATA_DIM", "128"))
    iterations = int(os.environ.get("ITERATIONS", "1"))
    k = int(os.environ.get("K", "10"))

    n = SCALE_MAP.get(data_scale, 100000)
    d = data_dim

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
        print(f'[ANN] Benchmarking {config_name}: {config["description"]}')
        try:
            avg, detailed = benchmark_config(config_name, config, data, queries, k, n, iterations, gt_I)
            all_results[config_name] = avg
            detailed_results[config_name] = detailed
        except Exception as e:
            print(f'[ANN] ERROR benchmarking {config_name}: {e}')
            all_results[config_name] = {"error": str(e)}

    print('[ANN] Running TreeAH leaves_to_search parameter sweep...')
    try:
        sweep = benchmark_tree_ah_leaves_sweep(data, queries, k, n, iterations, gt_I)
        all_results["TreeAH_leaves_sweep"] = sweep
    except Exception as e:
        print(f'[ANN] ERROR in leaves sweep: {e}')
        all_results["TreeAH_leaves_sweep"] = {"error": str(e)}

    scann_ver = getattr(scann, '__version__', 'unknown')
    output = {
        "benchmark": "ann_search",
        "description": "Approximate Nearest Neighbor search benchmark for ScaNN following ann-benchmarks methodology",
        "reference": "https://ann-benchmarks.com and https://github.com/google-research/google-research/tree/master/scann",
        "software": "scann",
        "version": scann_ver,
        "architecture": "arm64",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
            "size": f"{data_scale} vectors x {d} dimensions",
            "source": "numpy random uniform distribution"
        },
        "results_summary": all_results,
        "results_detailed": detailed_results
    }

    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, 'benchmark_primary.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'[ANN] Results saved to: {output_path}')
    for name, res in all_results.items():
        if isinstance(res, dict) and "error" in res:
            print(f'[ANN] {name}: ERROR - {res["error"]}')
        elif isinstance(res, dict) and "qps" in res:
            recall_key = f"recall_at_{k}"
            print(f'[ANN] {name}: QPS={res["qps"]}, Recall@{k}={res.get(recall_key, "N/A")}, Build={res.get("build_time_s", "N/A")}s')
    print('[ANN] Benchmark complete')


if __name__ == '__main__':
    main()
