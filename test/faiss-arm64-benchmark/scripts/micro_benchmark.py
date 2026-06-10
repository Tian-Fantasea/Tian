#!/usr/bin/env python3
import json
import time
import argparse
import datetime
import os
import numpy as np
import faiss

SCALE_MAP = {
    "1M": 1000000,
    "10M": 10000000,
    "100M": 100000000,
}

OPS = {
    "kmeans_clustering": {
        "description": "K-means clustering on random vectors (Faiss native)",
        "reference": "Faiss built-in K-means implementation",
    },
    "add_vectors_flat": {
        "description": "Add vectors to IndexFlatL2 (bulk insertion throughput)",
        "reference": "Faiss IndexFlatL2.add()",
    },
    "search_single_flat": {
        "description": "Single query search on IndexFlatL2 (per-query latency)",
        "reference": "Faiss IndexFlatL2.search()",
    },
    "search_batch_flat": {
        "description": "Batch query search on IndexFlatL2 (batch throughput)",
        "reference": "Faiss IndexFlatL2.search()",
    },
    "range_search_flat": {
        "description": "Range search on IndexFlatL2 (radius-based search)",
        "reference": "Faiss IndexFlatL2.range_search()",
    },
    "pq_encoding": {
        "description": "Product Quantization encoding throughput",
        "reference": "Faiss IndexPQ encoding",
    },
}

def bench_kmeans(xb, d, k_centroids=100, iterations=3):
    results = []
    for i in range(iterations):
        start = time.time()
        kmeans = faiss.Kmeans(d, k_centroids, niter=20, verbose=False)
        kmeans.train(xb)
        elapsed = time.time() - start
        results.append(elapsed)
    return round(sum(results) / len(results), 4), results

def bench_add_vectors(xb, d, iterations=3):
    results = []
    n = xb.shape[0]
    for i in range(iterations):
        index = faiss.IndexFlatL2(d)
        start = time.time()
        index.add(xb)
        elapsed = time.time() - start
        add_rate = n / elapsed if elapsed > 0 else 0
        results.append({"time_s": elapsed, "add_rate": round(add_rate, 2)})
    avg_time = round(sum(r["time_s"] for r in results) / len(results), 4)
    avg_rate = round(sum(r["add_rate"] for r in results) / len(results), 2)
    return avg_time, avg_rate, results

def bench_search_single(xb, d, iterations=3):
    results = []
    index = faiss.IndexFlatL2(d)
    index.add(xb)
    xq_single = xb[:1]
    for i in range(iterations):
        start = time.time()
        for _ in range(1000):
            D, I = index.search(xq_single, 10)
        elapsed = time.time() - start
        latency_us = (elapsed / 1000) * 1e6
        results.append({"total_time_s": elapsed, "latency_us": round(latency_us, 2)})
    avg_latency = round(sum(r["latency_us"] for r in results) / len(results), 2)
    return avg_latency, results

def bench_search_batch(xb, d, nq=10000, k=10, iterations=3):
    results = []
    index = faiss.IndexFlatL2(d)
    index.add(xb)
    xq = np.random.random((nq, d)).astype('float32')
    for i in range(iterations):
        start = time.time()
        D, I = index.search(xq, k)
        elapsed = time.time() - start
        qps = nq / elapsed if elapsed > 0 else 0
        results.append({"time_s": elapsed, "qps": round(qps, 2)})
    avg_time = round(sum(r["time_s"] for r in results) / len(results), 4)
    avg_qps = round(sum(r["qps"] for r in results) / len(results), 2)
    return avg_time, avg_qps, results

def bench_range_search(xb, d, iterations=3):
    results = []
    index = faiss.IndexFlatL2(d)
    index.add(xb)
    xq = xb[:100]
    radius = 5.0
    for i in range(iterations):
        start = time.time()
        lims, D, I = index.range_search(xq, radius)
        elapsed = time.time() - start
        nq = xq.shape[0]
        qps = nq / elapsed if elapsed > 0 else 0
        avg_results = (lims[-1] - lims[0]) / nq if nq > 0 else 0
        results.append({"time_s": elapsed, "qps": round(qps, 2), "avg_results_per_query": round(avg_results, 2)})
    avg_time = round(sum(r["time_s"] for r in results) / len(results), 4)
    avg_qps = round(sum(r["qps"] for r in results) / len(results), 2)
    return avg_time, avg_qps, results

def bench_pq_encoding(xb, d, iterations=3):
    results = []
    n = xb.shape[0]
    pq = faiss.IndexPQ(d, 8, 8)
    train_data = xb[:min(n, 50000)]
    pq.train(train_data)
    for i in range(iterations):
        start = time.time()
        pq.add(xb)
        elapsed = time.time() - start
        encode_rate = n / elapsed if elapsed > 0 else 0
        results.append({"time_s": elapsed, "encode_rate": round(encode_rate, 2)})
    avg_time = round(sum(r["time_s"] for r in results) / len(results), 4)
    avg_rate = round(sum(r["encode_rate"] for r in results) / len(results), 2)
    return avg_time, avg_rate, results

def main():
    parser = argparse.ArgumentParser(description='Faiss Micro Benchmarks')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--data-scale', default='1M', choices=list(SCALE_MAP.keys()))
    parser.add_argument('--data-dim', type=int, default=128)
    parser.add_argument('--iterations', type=int, default=3)
    args = parser.parse_args()

    n = SCALE_MAP[args.data_scale]
    d = args.data_dim
    iterations = args.iterations

    print(f'[MICRO] Generating {n} vectors of dimension {d}...')
    np.random.seed(42)
    xb = np.random.random((n, d)).astype('float32')

    all_results = {}

    print('[MICRO] Running kmeans_clustering...')
    avg_time, detailed = bench_kmeans(xb, d, iterations=iterations)
    all_results["kmeans_clustering"] = {"avg_time_s": avg_time}

    print('[MICRO] Running add_vectors_flat...')
    avg_time, avg_rate, detailed = bench_add_vectors(xb, d, iterations=iterations)
    all_results["add_vectors_flat"] = {"avg_time_s": avg_time, "add_rate_per_sec": avg_rate}

    print('[MICRO] Running search_single_flat...')
    avg_latency, detailed = bench_search_single(xb, d, iterations=iterations)
    all_results["search_single_flat"] = {"avg_latency_us": avg_latency}

    print('[MICRO] Running search_batch_flat...')
    avg_time, avg_qps, detailed = bench_search_batch(xb, d, iterations=iterations)
    all_results["search_batch_flat"] = {"avg_time_s": avg_time, "avg_qps": avg_qps}

    print('[MICRO] Running range_search_flat...')
    avg_time, avg_qps, detailed = bench_range_search(xb, d, iterations=iterations)
    all_results["range_search_flat"] = {"avg_time_s": avg_time, "avg_qps": avg_qps}

    print('[MICRO] Running pq_encoding...')
    avg_time, avg_rate, detailed = bench_pq_encoding(xb, d, iterations=iterations)
    all_results["pq_encoding"] = {"avg_time_s": avg_time, "encode_rate_per_sec": avg_rate}

    output = {
        "benchmark": "micro_operations",
        "description": "Micro-level benchmarks for core Faiss operations on ARM64",
        "reference": "Faiss library built-in operations (https://github.com/facebookresearch/faiss)",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "kmeans_time": {
                "unit": "seconds",
                "description": "Time for K-means clustering (100 centroids, 20 iterations)"
            },
            "add_rate": {
                "unit": "vectors/sec",
                "description": "Vector addition rate to IndexFlatL2"
            },
            "search_latency": {
                "unit": "microseconds",
                "description": "Per-query latency for single vector search"
            },
            "search_qps": {
                "unit": "queries/sec",
                "description": "Batch search throughput"
            },
            "encode_rate": {
                "unit": "vectors/sec",
                "description": "PQ encoding throughput"
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
            "iterations": iterations
        },
        "results": all_results
    }

    output_path = os.path.join(args.results_dir, 'benchmark_micro.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'[MICRO] Results saved to: {output_path}')
    for name, res in all_results.items():
        print(f'[MICRO] {name}: {res}')
    print('[MICRO] Benchmark complete')

if __name__ == '__main__':
    main()