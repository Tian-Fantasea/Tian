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


def create_test_pod(name, namespace, kubeconfig, image="busybox:1.36"):
    pod_spec = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "containers": [{
                "name": "test",
                "image": image,
                "command": ["sh", "-c", "echo ready && sleep 3600"]
            }],
            "terminationGracePeriodSeconds": 1
        }
    }
    spec_json = json.dumps(pod_spec)
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"],
        input=spec_json, capture_output=True, text=True, timeout=30
    )
    return result


def wait_for_pod_ready(name, namespace, kubeconfig, timeout=120):
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = run_kubectl(
            ["get", "pod", name, "-n", namespace,
             "-o", "jsonpath={.status.containerStatuses[0].ready}"],
            kubeconfig
        )
        if result.returncode == 0 and result.stdout.strip() == "true":
            return time.time() - start_time
        time.sleep(0.5)
    return None


def get_pod_creation_timestamp(name, namespace, kubeconfig):
    result = run_kubectl(
        ["get", "pod", name, "-n", namespace,
         "-o", "jsonpath={.metadata.creationTimestamp}"],
        kubeconfig
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def delete_pod(name, namespace, kubeconfig):
    run_kubectl(
        ["delete", "pod", name, "-n", namespace,
         "--force", "--grace-period=0"],
        kubeconfig
    )
    time.sleep(1)


def measure_pod_startup_latency(namespace, kubeconfig, num_pods, iteration):
    latencies = []
    successful = 0
    failed = 0

    for i in range(num_pods):
        pod_name = f"perf-pod-{iteration}-{i}"
        create_start = time.time()
        create_result = create_test_pod(pod_name, namespace, kubeconfig)
        if create_result.returncode != 0:
            failed += 1
            continue

        startup_time = wait_for_pod_ready(pod_name, namespace, kubeconfig, timeout=120)
        if startup_time is not None:
            latency_ms = startup_time * 1000
            latencies.append(latency_ms)
            successful += 1
        else:
            failed += 1

        delete_pod(pod_name, namespace, kubeconfig)

    return latencies, successful, failed


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
    parser = argparse.ArgumentParser(description="Pod startup latency benchmark for Kubernetes on ARM64")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--data-size", type=int, default=20)
    parser.add_argument("--kubeconfig", required=True)
    args = parser.parse_args()

    results_dir = args.results_dir
    iterations = args.iterations
    num_pods = min(args.data_size, 50)
    kubeconfig = args.kubeconfig

    namespace = "perf-test-startup"

    run_kubectl(["create", "namespace", namespace], kubeconfig)
    time.sleep(2)

    all_iteration_results = []
    all_latencies = []

    for iter_num in range(1, iterations + 1):
        print(f"[POD-STARTUP] Iteration {iter_num}/{iterations}: Creating {num_pods} pods...")
        latencies, successful, failed = measure_pod_startup_latency(
            namespace, kubeconfig, num_pods, iter_num
        )
        percentiles = calculate_percentiles(latencies)
        all_latencies.extend(latencies)

        iter_result = {
            "iteration": iter_num,
            "pods_requested": num_pods,
            "pods_successful": successful,
            "pods_failed": failed,
            "success_rate": round(successful / num_pods * 100, 2) if num_pods > 0 else 0,
            "p50_latency_ms": round(percentiles["p50"], 2),
            "p90_latency_ms": round(percentiles["p90"], 2),
            "p95_latency_ms": round(percentiles["p95"], 2),
            "p99_latency_ms": round(percentiles["p99"], 2),
            "avg_latency_ms": round(percentiles["avg"], 2),
            "min_latency_ms": round(percentiles["min"], 2),
            "max_latency_ms": round(percentiles["max"], 2),
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        all_iteration_results.append(iter_result)
        print(f"[POD-STARTUP] p50={percentiles['p50']:.0f}ms p99={percentiles['p99']:.0f}ms success={successful}/{num_pods}")

    overall_percentiles = calculate_percentiles(all_latencies)

    benchmark_data = {
        "benchmark": "pod_startup",
        "description": "Kubernetes pod startup latency on ARM64 - measures time from pod creation to containers ready (official Kubernetes SLO: p99 <= 5s)",
        "reference": "https://github.com/kubernetes/community/blob/master/sig-scalability/slos/slos.md",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "p99_latency_ms": {
                "unit": "ms",
                "description": "99th percentile pod startup latency (Kubernetes SLO: <= 5000ms)"
            },
            "p50_latency_ms": {
                "unit": "ms",
                "description": "50th percentile pod startup latency"
            },
            "success_rate": {
                "unit": "%",
                "description": "Percentage of pods that started successfully"
            }
        },
        "dataset_info": {
            "name": "busybox pods",
            "size": f"{num_pods} pods per iteration",
            "source": "Synthetic test pods using busybox:1.36"
        },
        "results": all_iteration_results + [{
            "iteration": "overall",
            "pods_total": len(all_latencies),
            "p50_latency_ms": round(overall_percentiles["p50"], 2),
            "p90_latency_ms": round(overall_percentiles["p90"], 2),
            "p95_latency_ms": round(overall_percentiles["p95"], 2),
            "p99_latency_ms": round(overall_percentiles["p99"], 2),
            "avg_latency_ms": round(overall_percentiles["avg"], 2),
            "min_latency_ms": round(overall_percentiles["min"], 2),
            "max_latency_ms": round(overall_percentiles["max"], 2),
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }]
    }

    output_file = os.path.join(results_dir, "benchmark_pod_startup.json")
    with open(output_file, 'w') as f:
        json.dump(benchmark_data, f, indent=2)

    run_kubectl(["delete", "namespace", namespace, "--force", "--grace-period=0"], kubeconfig)

    print(f"[POD-STARTUP] Overall: p99={overall_percentiles['p99']:.0f}ms (SLO: 5000ms)")
    print(f"[POD-STARTUP] Results saved to {output_file}")


if __name__ == "__main__":
    main()