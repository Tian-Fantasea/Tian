#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
import os
import sys
from datetime import datetime


def run_kubectl(args, kubeconfig=None):
    cmd = ["kubectl"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result


def measure_api_call_latency(kubeconfig, resource, verb, namespace="default", iterations=20):
    latencies = []
    successful = 0

    for i in range(iterations):
        start = time.time()
        if verb == "create":
            name = f"perf-test-{resource}-{i}"
            if resource == "configmap":
                result = run_kubectl(
                    ["create", "configmap", name, "-n", namespace,
                     "--from-literal=key=value"],
                    kubeconfig
                )
            elif resource == "secret":
                result = run_kubectl(
                    ["create", "secret", "generic", name, "-n", namespace,
                     "--from-literal=key=value"],
                    kubeconfig
                )
            else:
                result = run_kubectl(
                    ["create", resource, name, "-n", namespace],
                    kubeconfig
                )
        elif verb == "get":
            result = run_kubectl(
                ["get", resource, "-n", namespace, "--no-headers"],
                kubeconfig
            )
        elif verb == "list":
            result = run_kubectl(
                ["get", resource, "-n", namespace],
                kubeconfig
            )
        elif verb == "delete":
            name = f"perf-test-{resource}-{i}"
            result = run_kubectl(
                ["delete", resource, name, "-n", namespace,
                 "--force", "--grace-period=0", "--ignore-not-found"],
                kubeconfig
            )
        else:
            result = run_kubectl(
                [verb, resource, "-n", namespace],
                kubeconfig
            )

        elapsed_ms = (time.time() - start) * 1000
        if result.returncode == 0:
            latencies.append(elapsed_ms)
            successful += 1

        if verb == "create" and result.returncode == 0:
            cleanup_name = f"perf-test-{resource}-{i}"
            run_kubectl(
                ["delete", resource, cleanup_name, "-n", namespace,
                 "--force", "--grace-period=0", "--ignore-not-found"],
                kubeconfig
            )
            time.sleep(0.1)

    return latencies, successful


def calculate_percentiles(latencies):
    if not latencies:
        return {"p50": 0, "p90": 0, "p95": 0, "p99": 0, "avg": 0, "min": 0, "max": 0}

    sorted_lat = sorted(latencies)
    n = len(sorted_lat)
    avg = sum(sorted_lat) / n

    def percentile(p):
        idx = int(n * p / 100)
        if idx >= n:
            idx = n - 1
        return sorted_lat[idx]

    return {
        "p50": percentile(50),
        "p90": percentile(90),
        "p95": percentile(95),
        "p99": percentile(99),
        "avg": avg,
        "min": sorted_lat[0],
        "max": sorted_lat[-1]
    }


def main():
    parser = argparse.ArgumentParser(description="API server responsiveness benchmark for Kubernetes on ARM64")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--kubeconfig", required=True)
    args = parser.parse_args()

    results_dir = args.results_dir
    kubeconfig = args.kubeconfig

    test_operations = [
        ("mutating", "configmap", "create"),
        ("read-only-resource", "pod", "get"),
        ("read-only-namespace", "pod", "list"),
        ("mutating-delete", "configmap", "delete"),
    ]

    all_results = []

    for category, resource, verb in test_operations:
        print(f"[API-LATENCY] Testing {category}: {verb} {resource}...")
        all_latencies = []

        for iter_num in range(1, args.iterations + 1):
            latencies, successful = measure_api_call_latency(
                kubeconfig, resource, verb, iterations=20
            )
            percentiles = calculate_percentiles(latencies)
            all_latencies.extend(latencies)

            iter_result = {
                "iteration": iter_num,
                "category": category,
                "resource": resource,
                "verb": verb,
                "calls_successful": successful,
                "calls_total": 20,
                "p50_latency_ms": round(percentiles["p50"], 2),
                "p90_latency_ms": round(percentiles["p90"], 2),
                "p95_latency_ms": round(percentiles["p95"], 2),
                "p99_latency_ms": round(percentiles["p99"], 2),
                "avg_latency_ms": round(percentiles["avg"], 2),
                "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            all_results.append(iter_result)
            print(f"[API-LATENCY] iter={iter_num} p50={percentiles['p50']:.0f}ms p99={percentiles['p99']:.0f}ms")

        overall_percentiles = calculate_percentiles(all_latencies)
        all_results.append({
            "iteration": f"overall-{category}",
            "category": category,
            "resource": resource,
            "verb": verb,
            "calls_total": len(all_latencies),
            "p50_latency_ms": round(overall_percentiles["p50"], 2),
            "p90_latency_ms": round(overall_percentiles["p90"], 2),
            "p95_latency_ms": round(overall_percentiles["p95"], 2),
            "p99_latency_ms": round(overall_percentiles["p99"], 2),
            "avg_latency_ms": round(overall_percentiles["avg"], 2),
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        })

    benchmark_data = {
        "benchmark": "api_latency",
        "description": "Kubernetes API server responsiveness on ARM64 - measures latency of mutating and read-only API calls (official SLO: mutating p99 <= 1s, read-only resource p99 <= 1s, read-only namespace p99 <= 30s)",
        "reference": "https://github.com/kubernetes/community/blob/master/sig-scalability/slos/slos.md",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "p99_latency_ms": {
                "unit": "ms",
                "description": "99th percentile API call latency"
            },
            "p50_latency_ms": {
                "unit": "ms",
                "description": "50th percentile API call latency"
            },
            "category": {
                "unit": "string",
                "description": "Type of API call: mutating, read-only-resource, read-only-namespace"
            }
        },
        "dataset_info": {
            "name": "API call test",
            "size": "20 calls per operation per iteration",
            "source": "Synthetic kubectl commands"
        },
        "results": all_results
    }

    output_file = os.path.join(results_dir, "benchmark_api_latency.json")
    with open(output_file, 'w') as f:
        json.dump(benchmark_data, f, indent=2)

    print(f"[API-LATENCY] Results saved to {output_file}")


if __name__ == "__main__":
    main()