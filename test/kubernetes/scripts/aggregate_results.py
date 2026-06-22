#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Aggregate all benchmark JSON results")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True, help="Output results.json file")
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = load_json(os.path.join(results_dir, "version_info.json"))
    pod_startup = load_json(os.path.join(results_dir, "benchmark_pod_startup.json"))
    api_latency = load_json(os.path.join(results_dir, "benchmark_api_latency.json"))
    micro = load_json(os.path.join(results_dir, "micro_benchmark.json"))

    aggregated = {
        "benchmark_suite": "kubernetes_arm64_performance",
        "timestamp": datetime.datetime.now().isoformat(),
        "environment": version_info or {},
        "benchmarks": {
            "pod_startup": pod_startup or {},
            "api_latency": api_latency or {},
            "micro": micro or {}
        },
        "summary": {}
    }

    all_throughputs = []
    all_latencies = []

    if pod_startup and pod_startup.get("results"):
        overall = [r for r in pod_startup["results"] if r.get("iteration") == "overall"]
        if overall:
            p99 = overall[0].get("p99_latency_ms", 0)
            p50 = overall[0].get("p50_latency_ms", 0)
            aggregated["summary"]["pod_startup_p99_ms"] = p99
            aggregated["summary"]["pod_startup_p50_ms"] = p50
            aggregated["summary"]["pod_startup_slo_met"] = p99 <= 5000
            all_latencies.append(("pod_startup_p99", p99))

        iter_results = [r for r in pod_startup["results"] if isinstance(r.get("iteration"), int)]
        for r in iter_results:
            tp = r.get("success_rate", 0)
            if isinstance(tp, (int, float)) and tp > 0:
                all_throughputs.append(("pod_startup_success", tp))

    if api_latency and api_latency.get("results"):
        mutating = [r for r in api_latency["results"]
                    if r.get("iteration", "").startswith("overall-mutating")]
        read_resource = [r for r in api_latency["results"]
                         if r.get("iteration", "").startswith("overall-read-only-resource")]
        read_namespace = [r for r in api_latency["results"]
                          if r.get("iteration", "").startswith("overall-read-only-namespace")]
        if mutating:
            p99 = mutating[0].get("p99_latency_ms", 0)
            aggregated["summary"]["api_mutating_p99_ms"] = p99
            aggregated["summary"]["api_mutating_slo_met"] = p99 <= 1000
            all_latencies.append(("api_mutating_p99", p99))
        if read_resource:
            p99 = read_resource[0].get("p99_latency_ms", 0)
            aggregated["summary"]["api_read_resource_p99_ms"] = p99
            aggregated["summary"]["api_read_resource_slo_met"] = p99 <= 1000
            all_latencies.append(("api_read_p99", p99))
        if read_namespace:
            aggregated["summary"]["api_read_namespace_p99_ms"] = read_namespace[0].get("p99_latency_ms", 0)

    if micro and micro.get("results"):
        sched = [r for r in micro["results"]
                 if r.get("operation") == "scheduler_throughput"]
        if sched:
            avg_throughput = sum(r.get("throughput_pods_per_sec", 0) for r in sched) / len(sched)
            aggregated["summary"]["scheduler_throughput_pods_per_sec"] = round(avg_throughput, 2)
            aggregated["summary"]["scheduler_throughput_slo_met"] = avg_throughput >= 100
            all_throughputs.append(("scheduler", avg_throughput))

        kubelet = [r for r in micro["results"]
                   if r.get("operation") == "kubelet_lifecycle"]
        if kubelet:
            aggregated["summary"]["kubelet_avg_create_ms"] = kubelet[0].get("avg_pod_create_ms", 0)
            aggregated["summary"]["kubelet_avg_delete_ms"] = kubelet[0].get("avg_pod_delete_ms", 0)

    if all_throughputs:
        max_tp = max(all_throughputs, key=lambda x: x[1])
        avg_tp = sum(x[1] for x in all_throughputs) / len(all_throughputs)
        aggregated["summary"]["max_throughput"] = {"name": max_tp[0], "value": round(max_tp[1], 1), "unit": "ops/sec"}
        aggregated["summary"]["avg_throughput"] = round(avg_tp, 1)

    if all_latencies:
        max_lat = max(all_latencies, key=lambda x: x[1])
        avg_lat = sum(x[1] for x in all_latencies) / len(all_latencies)
        aggregated["summary"]["max_latency"] = {"name": max_lat[0], "value": round(max_lat[1], 2), "unit": "ms"}
        aggregated["summary"]["avg_latency"] = round(avg_lat, 2)

    with open(args.output, 'w') as f:
        json.dump(aggregated, f, indent=2)

    print(f"[AGGREGATE] Results aggregated to {args.output}")
    print(f"[AGGREGATE] Summary: {json.dumps(aggregated['summary'], indent=2)}")


if __name__ == "__main__":
    main()