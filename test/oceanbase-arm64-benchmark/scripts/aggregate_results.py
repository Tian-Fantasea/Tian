#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.environ.get(
    "RESULTS_DIR",
    os.path.join(os.path.dirname(SCRIPT_DIR), "results")
)


def load_json(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)


def aggregate():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    version_info = {}
    primary_bench = {}
    secondary_bench = {}
    micro_bench = {}

    version_file = os.path.join(RESULTS_DIR, "version_info.json")
    primary_file = os.path.join(RESULTS_DIR, "benchmark_primary.json")
    secondary_file = os.path.join(RESULTS_DIR, "benchmark_secondary.json")
    micro_file = os.path.join(RESULTS_DIR, "micro_benchmark.json")

    if os.path.exists(version_file):
        version_info = load_json(version_file)
    if os.path.exists(primary_file):
        primary_bench = load_json(primary_file)
    if os.path.exists(secondary_file):
        secondary_bench = load_json(secondary_file)
    if os.path.exists(micro_file):
        micro_bench = load_json(micro_file)

    avg_tpmc = 0
    if primary_bench and "results" in primary_bench:
        tpmc_values = [r.get("tpmC", 0) for r in primary_bench["results"] if r.get("tpmC", 0) > 0]
        if tpmc_values:
            avg_tpmc = round(sum(tpmc_values) / len(tpmc_values), 2)

    max_throughput = 0
    avg_latency = 0
    p99_latency = 0
    if secondary_bench and "results" in secondary_bench:
        throughputs = [r.get("throughput_ops_per_sec", 0) for r in secondary_bench["results"]]
        latencies = [r.get("avg_latency_ms", 0) for r in secondary_bench["results"]]
        p99s = [r.get("p99_latency_ms", 0) for r in secondary_bench["results"]]
        if throughputs:
            max_throughput = round(max(throughputs), 2)
        if latencies:
            avg_latency = round(sum(latencies) / len(latencies), 2)
        if p99s:
            p99_latency = round(max(p99s), 2)

    micro_summary = []
    if micro_bench and "results" in micro_bench:
        for r in micro_bench["results"]:
            micro_summary.append({
                "operation": r.get("operation", "unknown"),
                "avg_latency_ms": r.get("avg_latency_ms", 0),
                "p99_latency_ms": r.get("p99_latency_ms", 0),
            })

    aggregated = {
        "software_name": "oceanbase",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": version_info,
        "primary_benchmark": {
            "name": "tpcc",
            "average_tpmC": avg_tpmc,
            "iterations": len(primary_bench.get("results", [])),
            "results": primary_bench.get("results", []),
        },
        "secondary_benchmark": {
            "name": "ycsb",
            "max_throughput_ops_per_sec": max_throughput,
            "avg_latency_ms": avg_latency,
            "p99_latency_ms": p99_latency,
            "results": secondary_bench.get("results", []),
        },
        "micro_benchmark": {
            "name": "micro",
            "operations": micro_summary,
            "results": micro_bench.get("results", []),
        },
    }

    output_path = os.path.join(RESULTS_DIR, "all_results.json")
    save_json(output_path, aggregated)
    print(f"[AGGREGATE] Aggregated results saved to {output_path}")
    print(f"[AGGREGATE] Average tpmC: {avg_tpmc}")
    print(f"[AGGREGATE] Max YCSB throughput: {max_throughput} ops/sec")
    print(f"[AGGREGATE] Average YCSB latency: {avg_latency} ms")


if __name__ == "__main__":
    aggregate()