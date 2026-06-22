#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime


def load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Aggregate all benchmark JSON results")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = load_json(os.path.join(results_dir, "version_info.json"))
    pod_startup = load_json(os.path.join(results_dir, "benchmark_pod_startup.json"))
    api_latency = load_json(os.path.join(results_dir, "benchmark_api_latency.json"))
    micro = load_json(os.path.join(results_dir, "micro_benchmark.json"))
    stress = load_json(os.path.join(results_dir, "benchmark_stress.json"))

    aggregated = {
        "software_name": "kubernetes",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version_info": version_info or {},
        "benchmarks": {
            "pod_startup": pod_startup or {},
            "api_latency": api_latency or {},
            "micro": micro or {},
            "stress": stress or {}
        },
        "summary": {}
    }

    if pod_startup and pod_startup.get("results"):
        overall = [r for r in pod_startup["results"] if r.get("iteration") == "overall"]
        if overall:
            aggregated["summary"]["pod_startup_p99_ms"] = overall[0].get("p99_latency_ms", 0)
            aggregated["summary"]["pod_startup_p50_ms"] = overall[0].get("p50_latency_ms", 0)
            aggregated["summary"]["pod_startup_slo_met"] = overall[0].get("p99_latency_ms", 0) <= 5000

    if api_latency and api_latency.get("results"):
        mutating = [r for r in api_latency["results"]
                    if r.get("iteration", "").startswith("overall-mutating")]
        read_resource = [r for r in api_latency["results"]
                         if r.get("iteration", "").startswith("overall-read-only-resource")]
        read_namespace = [r for r in api_latency["results"]
                          if r.get("iteration", "").startswith("overall-read-only-namespace")]
        if mutating:
            aggregated["summary"]["api_mutating_p99_ms"] = mutating[0].get("p99_latency_ms", 0)
            aggregated["summary"]["api_mutating_slo_met"] = mutating[0].get("p99_latency_ms", 0) <= 1000
        if read_resource:
            aggregated["summary"]["api_read_resource_p99_ms"] = read_resource[0].get("p99_latency_ms", 0)
            aggregated["summary"]["api_read_resource_slo_met"] = read_resource[0].get("p99_latency_ms", 0) <= 1000
        if read_namespace:
            aggregated["summary"]["api_read_namespace_p99_ms"] = read_namespace[0].get("p99_latency_ms", 0)

    if micro and micro.get("results"):
        sched = [r for r in micro["results"]
                 if r.get("operation") == "scheduler_throughput"]
        if sched:
            avg_throughput = sum(r.get("throughput_pods_per_sec", 0) for r in sched) / len(sched)
            aggregated["summary"]["scheduler_throughput_pods_per_sec"] = round(avg_throughput, 2)
            aggregated["summary"]["scheduler_throughput_slo_met"] = avg_throughput >= 100

        kubelet = [r for r in micro["results"]
                   if r.get("operation") == "kubelet_lifecycle"]
        if kubelet:
            aggregated["summary"]["kubelet_avg_create_ms"] = kubelet[0].get("avg_pod_create_ms", 0)
            aggregated["summary"]["kubelet_avg_delete_ms"] = kubelet[0].get("avg_pod_delete_ms", 0)

    if stress and stress.get("results"):
        max_concurrency = max(r.get("concurrency", 0) for r in stress["results"])
        max_throughput = max(r.get("throughput_pods_per_sec", 0) for r in stress["results"])
        all_stable = all(r.get("stable", False) for r in stress["results"])
        aggregated["summary"]["stress_max_concurrency"] = max_concurrency
        aggregated["summary"]["stress_max_throughput_pods_per_sec"] = max_throughput
        aggregated["summary"]["stress_cluster_stable"] = all_stable

    output_file = os.path.join(results_dir, "all_results.json")
    with open(output_file, 'w') as f:
        json.dump(aggregated, f, indent=2)

    print(f"[AGGREGATE] Results aggregated to {output_file}")
    print(f"[AGGREGATE] Summary: {json.dumps(aggregated['summary'], indent=2)}")


if __name__ == "__main__":
    main()