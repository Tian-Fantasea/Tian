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
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result


def measure_scheduler_throughput(kubeconfig, num_pods, batch_size=10):
    namespace = "perf-scheduler"
    run_kubectl(["create", "namespace", namespace], kubeconfig)
    time.sleep(1)

    pods_spec = []
    for i in range(num_pods):
        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": f"sched-pod-{i}", "namespace": namespace},
            "spec": {
                "containers": [{
                    "name": "test",
                    "image": "busybox:1.36",
                    "command": ["sh", "-c", "echo ready && sleep 3600"]
                }],
                "terminationGracePeriodSeconds": 1
            }
        }
        pods_spec.append(pod)

    start_time = time.time()

    for batch_start in range(0, num_pods, batch_size):
        batch_end = min(batch_start + batch_size, num_pods)
        batch = pods_spec[batch_start:batch_end]

        manifest = ""
        for pod in batch:
            manifest += json.dumps(pod) + "\n---\n"

        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"],
            input=manifest, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"[SCHEDULER] Batch {batch_start}-{batch_end} apply failed: {result.stderr}")

    all_ready = False
    wait_start = time.time()
    while time.time() - wait_start < 300:
        result = run_kubectl(
            ["get", "pods", "-n", namespace, "--no-headers"],
            kubeconfig
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines and lines[0]:
                ready_count = sum(1 for l in lines if "Running" in l)
                total_count = len([l for l in lines if l.strip()])
                if ready_count >= total_count * 0.9:
                    all_ready = True
                    break
        time.sleep(2)

    total_time = time.time() - start_time
    throughput = num_pods / total_time if total_time > 0 else 0

    cleanup_start = time.time()
    run_kubectl(
        ["delete", "namespace", namespace, "--force", "--grace-period=0"],
        kubeconfig
    )
    time.sleep(5)
    cleanup_time = time.time() - cleanup_start

    run_kubectl(
        ["delete", "namespace", namespace, "--force", "--grace-period=0", "--ignore-not-found"],
        kubeconfig
    )

    return {
        "pods_scheduled": num_pods,
        "time_seconds": round(total_time, 2),
        "throughput_pods_per_sec": round(throughput, 2),
        "all_ready": all_ready,
        "cleanup_time_seconds": round(cleanup_time, 2),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }


def measure_kubelet_operations(kubeconfig):
    operations = {}

    pod_lifecycle_latencies = []
    for i in range(10):
        namespace = "perf-kubelet"
        pod_name = f"kubelet-pod-{i}"

        run_kubectl(["create", "namespace", namespace, "--ignore-not-found"], kubeconfig)

        start = time.time()
        pod_spec = json.dumps({
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": pod_name, "namespace": namespace},
            "spec": {
                "containers": [{
                    "name": "test",
                    "image": "busybox:1.36",
                    "command": ["sh", "-c", "echo ready && sleep 60"]
                }],
                "terminationGracePeriodSeconds": 1
            }
        })
        subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"],
            input=pod_spec, capture_output=True, text=True, timeout=30
        )

        while True:
            result = run_kubectl(
                ["get", "pod", pod_name, "-n", namespace,
                 "-o", "jsonpath={.status.phase}"],
                kubeconfig
            )
            if result.returncode == 0 and result.stdout.strip() == "Running":
                break
            time.sleep(0.5)
            if time.time() - start > 60:
                break

        create_latency = (time.time() - start) * 1000
        pod_lifecycle_latencies.append(create_latency)

        start = time.time()
        run_kubectl(
            ["delete", "pod", pod_name, "-n", namespace,
             "--force", "--grace-period=0"],
            kubeconfig
        )
        time.sleep(2)
        delete_latency = (time.time() - start) * 1000

        operations[f"pod_create_{i}"] = round(create_latency, 2)
        operations[f"pod_delete_{i}"] = round(delete_latency, 2)

    run_kubectl(
        ["delete", "namespace", namespace, "--force", "--grace-period=0", "--ignore-not-found"],
        kubeconfig
    )

    avg_create = sum(v for k, v in operations.items() if k.startswith("pod_create")) / 10
    avg_delete = sum(v for k, v in operations.items() if k.startswith("pod_delete")) / 10

    return {
        "avg_pod_create_ms": round(avg_create, 2),
        "avg_pod_delete_ms": round(avg_delete, 2),
        "pod_lifecycle_samples": 10,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }


def measure_etcd_performance(kubeconfig):
    result = run_kubectl(
        ["get", "--raw", "/healthz", "--kubeconfig", kubeconfig],
        kubeconfig
    )
    api_health = result.returncode == 0 and "ok" in result.stdout.lower()

    result = run_kubectl(
        ["get", "--raw", "/livez", "--kubeconfig", kubeconfig],
        kubeconfig
    )
    api_live = result.returncode == 0 and "ok" in result.stdout.lower()

    result = run_kubectl(
        ["get", "--raw", "/readyz", "--kubeconfig", kubeconfig],
        kubeconfig
    )
    api_ready = result.returncode == 0 and "ok" in result.stdout.lower()

    start = time.time()
    result = run_kubectl(
        ["get", "namespaces", "--no-headers", "--kubeconfig", kubeconfig],
        kubeconfig
    )
    list_latency = (time.time() - start) * 1000

    start = time.time()
    result = run_kubectl(
        ["get", "nodes", "-o", "json", "--kubeconfig", kubeconfig],
        kubeconfig
    )
    node_watch_latency = (time.time() - start) * 1000

    return {
        "api_healthz_ok": api_health,
        "api_livez_ok": api_live,
        "api_readyz_ok": api_ready,
        "namespace_list_latency_ms": round(list_latency, 2),
        "node_info_latency_ms": round(node_watch_latency, 2),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }


def run_stress_test(kubeconfig, num_pods=100, concurrency_levels=[10, 20, 50, 100]):
    stress_results = []

    for concurrency in concurrency_levels:
        actual_pods = min(concurrency, num_pods)
        namespace = f"perf-stress-{concurrency}"
        print(f"[STRESS] Testing with {actual_pods} pods (concurrency={concurrency})...")

        run_kubectl(["create", "namespace", namespace], kubeconfig)
        time.sleep(1)

        pods_spec = []
        for i in range(actual_pods):
            pods_spec.append(json.dumps({
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": f"stress-pod-{i}", "namespace": namespace},
                "spec": {
                    "containers": [{
                        "name": "test",
                        "image": "busybox:1.36",
                        "command": ["sh", "-c", "echo ready && sleep 3600"]
                    }],
                    "terminationGracePeriodSeconds": 1
                }
            }) + "\n---\n")

        start = time.time()
        manifest = "".join(pods_spec)
        subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"],
            input=manifest, capture_output=True, text=True, timeout=120
        )

        ready_count = 0
        while time.time() - start < 300:
            result = run_kubectl(
                ["get", "pods", "-n", namespace, "--no-headers"],
                kubeconfig
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                running = sum(1 for l in lines if "Running" in l)
                ready_count = running
                if running >= actual_pods * 0.9:
                    break
            time.sleep(3)

        startup_time = time.time() - start
        throughput = actual_pods / startup_time if startup_time > 0 else 0

        node_result = run_kubectl(["get", "nodes", "--no-headers"], kubeconfig)
        node_stable = node_result.returncode == 0 and "Ready" in node_result.stdout

        api_result = run_kubectl(["get", "--raw", "/healthz"], kubeconfig)
        api_stable = api_result.returncode == 0

        stress_results.append({
            "concurrency": concurrency,
            "pods_requested": actual_pods,
            "pods_running": ready_count,
            "startup_time_seconds": round(startup_time, 2),
            "throughput_pods_per_sec": round(throughput, 2),
            "node_stable": node_stable,
            "api_stable": api_stable,
            "stable": node_stable and api_stable,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        })

        run_kubectl(
            ["delete", "namespace", namespace, "--force", "--grace-period=0"],
            kubeconfig
        )
        time.sleep(5)

    return stress_results


def main():
    parser = argparse.ArgumentParser(description="Micro benchmarks and stress test for Kubernetes on ARM64")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--stress-only", action="store_true")
    args = parser.parse_args()

    results_dir = args.results_dir
    kubeconfig = args.kubeconfig

    if args.stress_only:
        stress_results = run_stress_test(kubeconfig, num_pods=100)
        benchmark_data = {
            "benchmark": "stress",
            "description": "Kubernetes stress test on ARM64 - measures cluster stability under increasing pod density",
            "reference": "https://github.com/kubernetes/perf-tests",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "performance_metrics": {
                "throughput_pods_per_sec": {
                    "unit": "pods/sec",
                    "description": "Pod creation throughput at various concurrency levels"
                },
                "stable": {
                    "unit": "boolean",
                    "description": "Whether cluster remained stable (nodes Ready + API healthz ok)"
                }
            },
            "dataset_info": {
                "name": "busybox stress pods",
                "size": "10, 20, 50, 100 pods",
                "source": "Synthetic test pods"
            },
            "results": stress_results
        }
        output_file = os.path.join(results_dir, "benchmark_stress.json")
        with open(output_file, 'w') as f:
            json.dump(benchmark_data, f, indent=2)
        print(f"[STRESS] Results saved to {output_file}")
        return

    micro_results = []

    print("[MICRO] Measuring scheduler throughput...")
    for iter_num in range(1, args.iterations + 1):
        sched_result = measure_scheduler_throughput(kubeconfig, num_pods=30)
        sched_result["iteration"] = iter_num
        sched_result["operation"] = "scheduler_throughput"
        micro_results.append(sched_result)
        print(f"[MICRO] iter={iter_num} throughput={sched_result['throughput_pods_per_sec']} pods/sec")

    print("[MICRO] Measuring kubelet operations...")
    kubelet_result = measure_kubelet_operations(kubeconfig)
    kubelet_result["iteration"] = "overall"
    kubelet_result["operation"] = "kubelet_lifecycle"
    micro_results.append(kubelet_result)
    print(f"[MICRO] avg_create={kubelet_result['avg_pod_create_ms']}ms avg_delete={kubelet_result['avg_pod_delete_ms']}ms")

    print("[MICRO] Measuring etcd/control plane performance...")
    etcd_result = measure_etcd_performance(kubeconfig)
    etcd_result["iteration"] = "overall"
    etcd_result["operation"] = "control_plane_health"
    micro_results.append(etcd_result)
    print(f"[MICRO] healthz={etcd_result['api_healthz_ok']} list_latency={etcd_result['namespace_list_latency_ms']}ms")

    benchmark_data = {
        "benchmark": "micro",
        "description": "Kubernetes micro benchmarks on ARM64 - scheduler throughput, kubelet lifecycle, control plane health",
        "reference": "https://github.com/kubernetes/perf-tests",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "throughput": {
                "unit": "pods/sec",
                "description": "Scheduler throughput (pods scheduled per second)"
            },
            "avg_pod_create_ms": {
                "unit": "ms",
                "description": "Average pod creation latency"
            },
            "namespace_list_latency_ms": {
                "unit": "ms",
                "description": "Control plane namespace list latency"
            }
        },
        "dataset_info": {
            "name": "synthetic pods",
            "size": "30 pods for scheduler, 10 pods for kubelet",
            "source": "Synthetic busybox pods"
        },
        "results": micro_results
    }

    output_file = os.path.join(results_dir, "micro_benchmark.json")
    with open(output_file, 'w') as f:
        json.dump(benchmark_data, f, indent=2)

    print(f"[MICRO] Results saved to {output_file}")


if __name__ == "__main__":
    main()