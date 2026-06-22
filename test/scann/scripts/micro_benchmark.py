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


def bench_build_times(data, k, n, iterations):
    results = {}
    configs = {
        "brute_force": lambda: scann.scann_ops_pybind.builder(data, k, "squared_l2").score_brute_force().build(),
        "brute_force_quantized": lambda: scann.scann_ops_pybind.builder(data, k, "squared_l2").score_brute_force(quantize=True).build(),
        "ah_only": lambda: scann.scann_ops_pybind.builder(data, k, "squared_l2").score_ah(
            dimensions_per_block=2, anisotropic_quantization_threshold=0.2).build(),
        "tree_ah_rescore": lambda: scann.scann_ops_pybind.builder(data, k, "squared_l2").tree(
            num_leaves=int(np.sqrt(n)), num_leaves_to_search=1, training_sample_size=min(n, 50000)).score_ah(
            dimensions_per_block=2, anisotropic_quantization_threshold=0.2).reorder(
            reordering_num_neighbors=100).build(),
    }

    for name, builder_fn in configs.items():
        print(f'[MICRO] Build time: {name}')
        run_times = []
        for i in range(iterations):
            start = time.time()
            searcher = builder_fn()
            elapsed = time.time() - start
            run_times.append(elapsed)
            del searcher
        avg_time = round(sum(run_times) / len(run_times), 4)
        results[name] = {"avg_build_time_s": avg_time, "iterations": iterations}
    return results


def bench_search_latency_by_batch(data, k, n, iterations):
    searcher = scann.scann_ops_pybind.builder(data, k, "squared_l2").tree(
        num_leaves=int(np.sqrt(n)), num_leaves_to_search=3, training_sample_size=min(n, 50000)
    ).score_ah(
        dimensions_per_block=2, anisotropic_quantization_threshold=0.2
    ).reorder(
        reordering_num_neighbors=100
    ).build()

    batch_sizes = [1, 10, 100, 1000]
    results = {}

    for bs in batch_sizes:
        print(f'[MICRO] Search latency by batch size: {bs}')
        nq = min(bs, data.shape[0] // 10)
        queries = data[:nq]
        run_results = []
        for i in range(iterations):
            start = time.time()
            indices, distances = searcher.search_batched(queries, final_num_neighbors=k)
            elapsed = time.time() - start
            qps = nq / elapsed if elapsed > 0 else 0
            latency_us = (elapsed / nq) * 1e6 if nq > 0 else 0
            run_results.append({"time_s": elapsed, "qps": round(qps, 2), "latency_per_query_us": round(latency_us, 2)})
        avg_time = round(sum(r["time_s"] for r in run_results) / len(run_results), 6)
        avg_qps = round(sum(r["qps"] for r in run_results) / len(run_results), 2)
        avg_latency = round(sum(r["latency_per_query_us"] for r in run_results) / len(run_results), 2)
        results[f"batch_{bs}"] = {"avg_time_s": avg_time, "avg_qps": avg_qps, "avg_latency_per_query_us": avg_latency}
    return results


def bench_reorder_sweep(data, k, n, iterations):
    reorder_values = [50, 100, 200]
    results = {}
    nq = min(10000, n // 10)
    queries = data[:nq]

    gt_I = np.zeros((nq, k), dtype=np.int64)
    chunk = min(500, nq)
    for i in range(0, nq, chunk):
        end = min(i + chunk, nq)
        dists = np.sum((queries[i:end].reshape(end - i, 1, -1) - data.reshape(1, n, -1)) ** 2, axis=2)
        gt_I[i:end] = np.argsort(dists, axis=1)[:, :k]

    num_leaves = int(np.sqrt(n))
    for reorder_k in reorder_values:
        label = f"reorder_{reorder_k}"
        print(f'[MICRO] Reorder sweep: {label}')
        run_results = []
        for i in range(iterations):
            searcher = scann.scann_ops_pybind.builder(data, k, "squared_l2").tree(
                num_leaves=num_leaves, num_leaves_to_search=3, training_sample_size=min(n, 50000)
            ).score_ah(
                dimensions_per_block=2, anisotropic_quantization_threshold=0.2
            ).reorder(
                reordering_num_neighbors=reorder_k
            ).build()

            start = time.time()
            indices, distances = searcher.search_batched(queries, final_num_neighbors=k)
            elapsed = time.time() - start

            qps = nq / elapsed if elapsed > 0 else 0
            recall = 0.0
            for j in range(nq):
                recall += len(set(indices[j].tolist()) & set(gt_I[j].tolist())) / k
            recall /= nq

            run_results.append({"qps": round(qps, 2), f"recall_at_{k}": round(recall, 4), "time_s": elapsed})
            del searcher

        avg_qps = round(sum(r["qps"] for r in run_results) / len(run_results), 2)
        avg_recall = round(sum(r[f"recall_at_{k}"] for r in run_results) / len(run_results), 4)
        results[label] = {"avg_qps": avg_qps, f"avg_recall_at_{k}": avg_recall, "reordering_num_neighbors": reorder_k}
    return results


def bench_dims_per_block(data, k, n, iterations):
    dims_values = [1, 2]
    results = {}
    nq = min(10000, n // 10)
    queries = data[:nq]

    for dpb in dims_values:
        label = f"dims_per_block_{dpb}"
        print(f'[MICRO] dims_per_block sweep: {label}')
        run_results = []
        for i in range(iterations):
            searcher = scann.scann_ops_pybind.builder(data, k, "squared_l2").score_ah(
                dimensions_per_block=dpb, anisotropic_quantization_threshold=0.2
            ).build()
            start = time.time()
            indices, distances = searcher.search_batched(queries, final_num_neighbors=k)
            elapsed = time.time() - start
            qps = nq / elapsed if elapsed > 0 else 0
            run_results.append({"qps": round(qps, 2), "time_s": elapsed})
            del searcher

        avg_qps = round(sum(r["qps"] for r in run_results) / len(run_results), 2)
        results[label] = {"avg_qps": avg_qps, "dimensions_per_block": dpb}
    return results


def main():
    results_dir = os.environ.get("RESULTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
    data_scale = os.environ.get("DATA_SCALE", "100K")
    data_dim = int(os.environ.get("DATA_DIM", "128"))
    iterations = int(os.environ.get("ITERATIONS", "1"))
    k = 10

    n = SCALE_MAP.get(data_scale, 100000)
    d = data_dim

    print(f'[MICRO] Generating {n} vectors of dimension {d}...')
    np.random.seed(42)
    data = np.random.random((n, d)).astype('float32')

    all_results = {}

    print('[MICRO] Running build_times...')
    all_results["build_times"] = bench_build_times(data, k, n, iterations)

    print('[MICRO] Running search_latency_by_batch...')
    all_results["search_latency_by_batch"] = bench_search_latency_by_batch(data, k, n, iterations)

    print('[MICRO] Running reorder_sweep...')
    all_results["reorder_sweep"] = bench_reorder_sweep(data, k, n, iterations)

    print('[MICRO] Running dims_per_block sweep...')
    all_results["dims_per_block_sweep"] = bench_dims_per_block(data, k, n, iterations)

    scann_ver = getattr(scann, '__version__', 'unknown')
    output = {
        "benchmark": "micro_operations",
        "description": "Micro-level benchmarks for core ScaNN operations on ARM64",
        "reference": "https://github.com/google-research/google-research/tree/master/scann",
        "software": "scann",
        "version": scann_ver,
        "architecture": "arm64",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "performance_metrics": {
            "build_time": {
                "unit": "seconds",
                "description": "Time to build different ScaNN index configurations"
            },
            "search_qps": {
                "unit": "queries/sec",
                "description": "Search throughput at different batch sizes"
            },
            "recall": {
                "unit": "ratio (0-1)",
                "description": "Recall at different reorder parameter values"
            }
        },
        "dataset_info": {
            "name": "synthetic_random_float32",
            "size": f"{data_scale} vectors x {d} dimensions",
            "source": "numpy random uniform distribution"
        },
        "results": all_results
    }

    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, 'micro_benchmark.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'[MICRO] Results saved to: {output_path}')
    for name, res in all_results.items():
        print(f'[MICRO] {name}: {res}')
    print('[MICRO] Benchmark complete')


if __name__ == '__main__':
    main()
