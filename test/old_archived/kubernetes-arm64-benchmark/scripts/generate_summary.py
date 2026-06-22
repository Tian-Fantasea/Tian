#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Generate text summary of benchmark results")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    results_dir = args.results_dir
    agg_file = os.path.join(results_dir, "all_results.json")

    try:
        with open(agg_file, 'r') as f:
            data = json.load(f)
    except Exception:
        print("[SUMMARY] No aggregated results found")
        return

    summary = data.get("summary", {})
    version_info = data.get("version_info", {})

    lines = []
    lines.append("=" * 70)
    lines.append("Kubernetes ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Timestamp: {data.get('timestamp', 'unknown')}")
    lines.append(f"Architecture: {version_info.get('architecture', 'unknown')}")
    lines.append(f"CPU: {version_info.get('cpu_model', 'unknown')}")
    lines.append(f"Cores: {version_info.get('cores', 'unknown')}")
    lines.append(f"Memory: {version_info.get('memory_mb', 'unknown')} MB")
    lines.append(f"OS: {version_info.get('os', 'unknown')}")
    lines.append(f"Kubernetes Version: {version_info.get('software_version', 'unknown')}")
    lines.append(f"Server Version: {version_info.get('server_version', 'unknown')}")
    lines.append(f"Cluster: {version_info.get('cluster_name', 'unknown')} ({version_info.get('nodes_ready', 0)} nodes)")
    lines.append("")
    lines.append("-" * 70)
    lines.append("Benchmark Results")
    lines.append("-" * 70)
    lines.append("")

    if "pod_startup_p99_ms" in summary:
        slo_met = summary.get("pod_startup_slo_met", False)
        status = "PASS" if slo_met else "FAIL"
        lines.append(f"Pod Startup Latency (Primary Benchmark)")
        lines.append(f"  p99: {summary['pod_startup_p99_ms']:.0f} ms  [SLO: <= 5000ms]  [{status}]")
        lines.append(f"  p50: {summary.get('pod_startup_p50_ms', 0):.0f} ms")
        lines.append("")

    if "api_mutating_p99_ms" in summary:
        slo_met = summary.get("api_mutating_slo_met", False)
        status = "PASS" if slo_met else "FAIL"
        lines.append(f"API Responsiveness (Secondary Benchmark)")
        lines.append(f"  Mutating calls p99: {summary['api_mutating_p99_ms']:.0f} ms  [SLO: <= 1000ms]  [{status}]")
        if "api_read_resource_p99_ms" in summary:
            slo_met = summary.get("api_read_resource_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Read-only (resource) p99: {summary['api_read_resource_p99_ms']:.0f} ms  [SLO: <= 1000ms]  [{status}]")
        if "api_read_namespace_p99_ms" in summary:
            lines.append(f"  Read-only (namespace) p99: {summary['api_read_namespace_p99_ms']:.0f} ms  [SLO: <= 30000ms]")
        lines.append("")

    if "scheduler_throughput_pods_per_sec" in summary:
        slo_met = summary.get("scheduler_throughput_slo_met", False)
        status = "PASS" if slo_met else "FAIL"
        lines.append(f"Scheduler Throughput (Micro Benchmark)")
        lines.append(f"  Throughput: {summary['scheduler_throughput_pods_per_sec']:.1f} pods/sec  [Threshold: >= 100]  [{status}]")
        lines.append("")

    if "kubelet_avg_create_ms" in summary:
        lines.append(f"Kubelet Pod Lifecycle (Micro Benchmark)")
        lines.append(f"  Avg create: {summary['kubelet_avg_create_ms']:.0f} ms")
        lines.append(f"  Avg delete: {summary['kubelet_avg_delete_ms']:.0f} ms")
        lines.append("")

    if "stress_max_concurrency" in summary:
        stable = summary.get("stress_cluster_stable", False)
        status = "PASS" if stable else "FAIL"
        lines.append(f"Stress Test")
        lines.append(f"  Max concurrency: {summary['stress_max_concurrency']} pods")
        lines.append(f"  Max throughput: {summary['stress_max_throughput_pods_per_sec']:.1f} pods/sec")
        lines.append(f"  Cluster stable: {stable}  [{status}]")
        lines.append("")

    lines.append("-" * 70)
    lines.append("Kubernetes Official SLOs (Reference)")
    lines.append("-" * 70)
    lines.append("  Pod startup p99 latency: <= 5s")
    lines.append("  Mutating API call p99 latency: <= 1s")
    lines.append("  Read-only API call (resource) p99: <= 1s")
    lines.append("  Read-only API call (namespace) p99: <= 30s")
    lines.append("")
    lines.append("=" * 70)

    output_file = os.path.join(results_dir, "benchmark_summary.txt")
    with open(output_file, 'w') as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Summary saved to {output_file}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()