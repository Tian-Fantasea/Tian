#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time


def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def fmt_val(value, unit="", precision=2):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f} {unit}"
    if isinstance(value, int):
        return f"{value} {unit}"
    return f"{value}"


def main():
    parser = argparse.ArgumentParser(description="Generate text summary for CloudWeGo benchmarks")
    parser.add_argument("--input", required=True, help="Path to results.json")
    parser.add_argument("--output", required=True, help="Path to results.txt")
    args = parser.parse_args()

    data = load_or_create_json(args.input)
    if not data:
        with open(args.output, "w") as f:
            f.write("ERROR: No results.json found\n")
        return 1

    vi = data.get("version_info", {})
    timestamp = data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    version = data.get("version", "unknown")

    lines = []
    lines.append("=" * 80)
    lines.append("  CloudWeGo ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append(f"  CloudWeGo:    {version}")
    lines.append(f"  Date:         {timestamp}")
    lines.append(f"  Architecture: {vi.get('architecture', 'unknown')}")
    lines.append(f"  CPU:          {vi.get('cpu_model', 'unknown')} ({vi.get('cores', 'unknown')} cores)")
    lines.append(f"  Memory:       {fmt_val(vi.get('memory_mb', 0), 'MB', 0)}")
    lines.append(f"  OS:           {vi.get('os', 'unknown')}")
    lines.append(f"  Kernel:       {vi.get('kernel', 'unknown')}")
    lines.append(f"  Go:           {vi.get('go_version', 'unknown')}")
    lines.append(f"  Kitex:        {vi.get('kitex_version', 'unknown')}")
    lines.append(f"  Hertz:        {vi.get('hertz_version', 'unknown')}")
    lines.append(f"  wrk:          {vi.get('wrk_version', 'unknown')}")
    lines.append("=" * 80)

    kitex = data.get("kitex_benchmark", {})
    if kitex:
        lines.append("")
        lines.append("  KITEX RPC BENCHMARK (Primary)")
        lines.append("-" * 80)
        lines.append(f"  Reference: {kitex.get('reference', 'N/A')}")
        for r in kitex.get("results", []):
            if "concurrency" in r:
                lines.append(f"    Conc={r['concurrency']:>5d}  QPS={r.get('qps', 0):>10,.0f}  Avg={r.get('avg_latency_ms', 0):>8.2f}ms  P99={r.get('p99_latency_ms', 0):>8.2f}ms")
            elif "operation" in r:
                lines.append(f"    {r.get('operation', 'N/A'):<40s}  {r.get('ops_per_sec', 0):>10,.0f} ops/s")

    hertz = data.get("hertz_benchmark", {})
    if hertz:
        lines.append("")
        lines.append("  HERTZ HTTP BENCHMARK (Secondary)")
        lines.append("-" * 80)
        lines.append(f"  Reference: {hertz.get('reference', 'N/A')}")
        for r in hertz.get("results", []):
            if "concurrency" in r:
                lines.append(f"    Conc={r['concurrency']:>5d}  QPS={r.get('qps', 0):>10,.0f}  Avg={r.get('avg_latency_ms', 0):>8.2f}ms  P99={r.get('p99_latency_ms', 'N/A'):>8}ms")
            elif "operation" in r:
                lines.append(f"    {r.get('operation', 'N/A'):<40s}  {r.get('ops_per_sec', 0):>10,.0f} ops/s")

    micro = data.get("micro_benchmark", {})
    if micro:
        lines.append("")
        lines.append("  MICRO BENCHMARKS")
        lines.append("-" * 80)
        lines.append(f"  Reference: {micro.get('reference', 'N/A')}")
        for r in micro.get("results", []):
            comp = r.get("component", "")
            op = r.get("operation", "")
            ops = r.get("ops_per_sec", 0)
            ns = r.get("ns_per_op", 0)
            lines.append(f"    [{comp:<20s}] {op:<35s}  {ops:>10,.0f} ops/s  ({ns:>8.1f} ns/op)")

    stress = data.get("stress_benchmark", {})
    if stress:
        lines.append("")
        lines.append("  STRESS BENCHMARK")
        lines.append("-" * 80)
        lines.append(f"  Reference: {stress.get('reference', 'N/A')}")
        for r in stress.get("results", []):
            if "concurrency" in r:
                lines.append(f"    Conc={r['concurrency']:>5d}  QPS={r.get('qps', 0):>10,.0f}  Avg={r.get('avg_latency_ms', 0):>8.2f}ms")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  ARM64 THRESHOLD REFERENCE")
    lines.append("=" * 80)
    lines.append("  Kitex Thrift QPS >= 50,000 at conc=100 on ARM64")
    lines.append("  Hertz HTTP QPS >= 30,000 at conc=100 on ARM64")
    lines.append("  Kitex P99 latency <= 5ms at conc=100 on ARM64")
    lines.append("  Hertz P99 latency <= 3ms at conc=100 on ARM64")
    lines.append("  Sonic JSON >= 50MB/s serialization on ARM64")
    lines.append("  Netpoll >= Kitex with go net throughput on ARM64")
    lines.append("=" * 80)

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Text summary saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
