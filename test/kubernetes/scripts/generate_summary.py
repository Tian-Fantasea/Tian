#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description="Generate text summary of benchmark results")
    parser.add_argument("--input", required=True, help="Input results.json file")
    parser.add_argument("--output", required=True, help="Output results.txt file")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("[SUMMARY] results.json not found")
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    summary = data.get("summary", {})
    env = data.get("environment", {})
    benchmarks = data.get("benchmarks", {})

    lines = []
    lines.append("=" * 70)
    lines.append("Kubernetes ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
    lines.append("")

    if env:
        lines.append("--- Environment ---")
        lines.append(f"Architecture:          {env.get('architecture', 'N/A')}")
        lines.append(f"OS:                    {env.get('os', 'N/A')}")
        lines.append(f"Kernel:                {env.get('kernel', 'N/A')}")
        lines.append(f"CPU:                   {env.get('cpu_model', 'N/A')} ({env.get('cores', 'N/A')} cores)")
        lines.append(f"Memory:                {env.get('memory_mb', 'N/A')} MB")
        lines.append(f"Kubernetes Version:    {env.get('software_version', 'N/A')}")
        lines.append(f"Server Version:        {env.get('server_version', 'N/A')}")
        lines.append(f"kubectl Version:       {env.get('kubectl_version', 'N/A')}")
        lines.append(f"Cluster:               {env.get('cluster_name', 'N/A')} ({env.get('nodes_ready', 'N/A')} nodes)")
        lines.append(f"Install Method:        {env.get('install_method', 'N/A')}")
        lines.append("")

    pod_startup = benchmarks.get("pod_startup", {})
    if pod_startup:
        lines.append("--- Pod Startup Latency (Phase 3a) ---")
        lines.append(f"Reference: {pod_startup.get('reference', 'N/A')}")
        lines.append(f"Description: {pod_startup.get('description', 'N/A')}")
        lines.append("")
        results = pod_startup.get("results", [])
        for r in results:
            if r.get("iteration") == "overall":
                p99 = r.get("p99_latency_ms", 0)
                slo_met = p99 <= 5000
                status = "PASS" if slo_met else "FAIL"
                lines.append(f"  Overall p99: {p99:.0f} ms  [SLO: <= 5000ms]  [{status}]")
                lines.append(f"  Overall p50: {r.get('p50_latency_ms', 0):.0f} ms")
                lines.append("")
        if "pod_startup_p99_ms" in summary:
            lines.append(f"  Summary p99: {summary['pod_startup_p99_ms']:.0f} ms")
            lines.append(f"  SLO met: {summary.get('pod_startup_slo_met', False)}")
            lines.append("")

    api_latency = benchmarks.get("api_latency", {})
    if api_latency:
        lines.append("--- API Responsiveness (Phase 3b) ---")
        lines.append(f"Reference: {api_latency.get('reference', 'N/A')}")
        lines.append("")
        if "api_mutating_p99_ms" in summary:
            slo_met = summary.get("api_mutating_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Mutating p99: {summary['api_mutating_p99_ms']:.0f} ms  [SLO: <= 1000ms]  [{status}]")
        if "api_read_resource_p99_ms" in summary:
            slo_met = summary.get("api_read_resource_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Read-only (resource) p99: {summary['api_read_resource_p99_ms']:.0f} ms  [SLO: <= 1000ms]  [{status}]")
        if "api_read_namespace_p99_ms" in summary:
            lines.append(f"  Read-only (namespace) p99: {summary['api_read_namespace_p99_ms']:.0f} ms  [SLO: <= 30000ms]")
        lines.append("")

    micro = benchmarks.get("micro", {})
    if micro:
        lines.append("--- Micro Benchmarks (Phase 3c) ---")
        lines.append(f"Reference: {micro.get('reference', 'N/A')}")
        lines.append("")
        if "scheduler_throughput_pods_per_sec" in summary:
            slo_met = summary.get("scheduler_throughput_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Scheduler throughput: {summary['scheduler_throughput_pods_per_sec']:.1f} pods/sec  [Threshold: >= 100]  [{status}]")
        if "kubelet_avg_create_ms" in summary:
            lines.append(f"  Kubelet avg create: {summary['kubelet_avg_create_ms']:.0f} ms")
            lines.append(f"  Kubelet avg delete: {summary['kubelet_avg_delete_ms']:.0f} ms")
        lines.append("")

    if summary:
        lines.append("--- Overall Summary ---")
        if "max_throughput" in summary:
            mt = summary["max_throughput"]
            lines.append(f"  Max throughput: {mt['value']} {mt['unit']} ({mt['name']})")
        if "avg_throughput" in summary:
            lines.append(f"  Avg throughput: {summary['avg_throughput']} ops/sec")
        if "max_latency" in summary:
            ml = summary["max_latency"]
            lines.append(f"  Max latency: {ml['value']} {ml['unit']} ({ml['name']})")
        if "avg_latency" in summary:
            lines.append(f"  Avg latency: {summary['avg_latency']} ms")

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
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_text = "\n".join(lines)
    with open(args.output, 'w') as f:
        f.write(summary_text)
    print(f"[SUMMARY] Saved to {args.output}")


if __name__ == "__main__":
    main()