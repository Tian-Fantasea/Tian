#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.environ.get(
    "RESULTS_DIR",
    os.path.join(os.path.dirname(SCRIPT_DIR), "results")
)


def load_json(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def generate_summary():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    agg = load_json(os.path.join(RESULTS_DIR, "all_results.json"))
    version = load_json(os.path.join(RESULTS_DIR, "version_info.json"))

    if not agg:
        print("[SUMMARY] No aggregated results found")
        return

    lines = []
    lines.append("=" * 70)
    lines.append("OceanBase ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Generated: " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    lines.append("")

    env = agg.get("environment", version)
    if env:
        lines.append("--- Environment ---")
        lines.append(f"  Architecture:     {env.get('architecture', 'unknown')}")
        lines.append(f"  OS:               {env.get('os', 'unknown')}")
        lines.append(f"  Kernel:           {env.get('kernel', 'unknown')}")
        lines.append(f"  CPU Model:        {env.get('cpu_model', 'unknown')}")
        lines.append(f"  CPU Cores:        {env.get('cores', 'unknown')}")
        lines.append(f"  Memory:           {env.get('memory_mb', 0)} MB")
        lines.append(f"  OceanBase Version: {env.get('software_version', 'unknown')}")
        lines.append(f"  OBD Version:       {env.get('obd_version', 'unknown')}")
        lines.append(f"  Java Version:      {env.get('java_version', 'unknown')}")
        lines.append("")

    primary = agg.get("primary_benchmark", {})
    if primary:
        lines.append("--- TPC-C Benchmark (Primary) ---")
        lines.append(f"  Average tpmC:       {primary.get('average_tpmC', 0)}")
        lines.append(f"  Iterations:         {primary.get('iterations', 0)}")
        results = primary.get("results", [])
        if results:
            lines.append(f"  Individual Results:")
            for r in results:
                it = r.get("iteration", "?")
                tpmc = r.get("tpmC", 0)
                elapsed = r.get("elapsed_seconds", 0)
                status = r.get("status", "unknown")
                lines.append(f"    Iteration {it}: tpmC={tpmc}, elapsed={elapsed}s, status={status}")
        lines.append("")

    secondary = agg.get("secondary_benchmark", {})
    if secondary:
        lines.append("--- YCSB Benchmark (Secondary) ---")
        lines.append(f"  Max Throughput:     {secondary.get('max_throughput_ops_per_sec', 0)} ops/sec")
        lines.append(f"  Avg Latency:        {secondary.get('avg_latency_ms', 0)} ms")
        lines.append(f"  P99 Latency:        {secondary.get('p99_latency_ms', 0)} ms")
        lines.append("")

    micro = agg.get("micro_benchmark", {})
    if micro:
        lines.append("--- Micro Benchmark ---")
        ops = micro.get("operations", [])
        if ops:
            lines.append(f"  {'Operation':<25} {'Avg Latency':<15} {'P99 Latency':<15}")
            lines.append(f"  {'-'*25} {'-'*15} {'-'*15}")
            for op in ops:
                name = op.get("operation", "unknown")
                avg = op.get("avg_latency_ms", 0)
                p99 = op.get("p99_latency_ms", 0)
                lines.append(f"  {name:<25} {avg:<15} {p99:<15}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_path = os.path.join(RESULTS_DIR, "benchmark_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines))
    print(f"[SUMMARY] Summary saved to {summary_path}")


if __name__ == "__main__":
    generate_summary()