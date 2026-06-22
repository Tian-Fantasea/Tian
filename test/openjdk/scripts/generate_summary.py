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
    parser = argparse.ArgumentParser(description="Generate text summary for OpenJDK benchmarks")
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
    lines.append("  OpenJDK ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append(f"  OpenJDK:       {version}")
    lines.append(f"  Date:          {timestamp}")
    lines.append(f"  Architecture:  {vi.get('architecture', 'unknown')}")
    lines.append(f"  CPU:           {vi.get('cpu_model', 'unknown')} ({vi.get('cores', 'unknown')} cores)")
    lines.append(f"  Memory:        {fmt_val(vi.get('memory_mb', 0), 'MB', 0)}")
    lines.append(f"  OS:            {vi.get('os', 'unknown')}")
    lines.append(f"  Kernel:        {vi.get('kernel', 'unknown')}")
    lines.append(f"  JVM Name:      {vi.get('jvm_name', 'unknown')}")
    lines.append(f"  JVM Vendor:    {vi.get('jvm_vendor', 'unknown')}")
    lines.append(f"  Default GC:    {vi.get('gc_default', 'unknown')}")
    lines.append(f"  JIT Compiler:  {vi.get('jit_compiler', 'unknown')}")
    lines.append("=" * 80)

    renaissance = data.get("renaissance_benchmark", {})
    if renaissance:
        lines.append("")
        lines.append("  RENAISSANCE BENCHMARK (Primary - Industry Standard JVM Suite)")
        lines.append("-" * 80)
        lines.append(f"  Reference: {renaissance.get('reference', 'N/A')}")
        lines.append(f"  Version:   {renaissance.get('parameters', {}).get('renaissance_version', 'N/A')}")
        lines.append(f"  Error:     {renaissance.get('error', 'None')}")
        for bench_name, res in renaissance.get("results", {}).items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                elapsed = res.get("avg_total_ms", "N/A")
                errs = res.get("errors", 0)
                status = "OK" if errs == 0 else f"ERRORS({errs})"
                lines.append(f"    {bench_name}: {desc}")
                lines.append(f"      avg_elapsed={elapsed}ms  [{status}]")

    dacapo = data.get("dacapo_benchmark", {})
    if dacapo:
        lines.append("")
        lines.append("  DACAPO BENCHMARK (Secondary - Classic Java Workload Suite)")
        lines.append("-" * 80)
        lines.append(f"  Reference: {dacapo.get('reference', 'N/A')}")
        lines.append(f"  Version:   {dacapo.get('parameters', {}).get('dacapo_version', 'N/A')}")
        lines.append(f"  Error:     {dacapo.get('error', 'None')}")
        for bench_name, res in dacapo.get("results", {}).items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                elapsed = res.get("avg_elapsed_ms", "N/A")
                throughput = res.get("avg_throughput_ops_per_sec", "N/A")
                errs = res.get("errors", 0)
                status = "OK" if errs == 0 else f"ERRORS({errs})"
                lines.append(f"    {bench_name}: {desc}")
                lines.append(f"      avg_elapsed={elapsed}ms  avg_throughput={throughput} ops/sec  [{status}]")

    micro = data.get("micro_benchmark", {})
    if micro:
        lines.append("")
        lines.append("  JVM MICRO BENCHMARKS")
        lines.append("-" * 80)
        lines.append(f"  Reference: {micro.get('reference', 'N/A')}")
        lines.append(f"  Error:     {micro.get('error', 'None')}")
        for bench_name, res in micro.get("results", {}).items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                avg_ns = res.get("avg_avg_ns", "N/A")
                ops = res.get("avg_ops_per_sec", "N/A")
                lines.append(f"    {bench_name}: {desc}")
                lines.append(f"      avg_ns={avg_ns}  ops/sec={ops}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  ARM64 Threshold Reference")
    lines.append("=" * 80)
    lines.append("  - Renaissance akka-uct >= 10,000 ops/sec on ARM64")
    lines.append("  - DaCapo h2 elapsed <= 500ms on ARM64")
    lines.append("  - StringBuilder concat avg_ns <= 100,000 on ARM64")
    lines.append("  - Array sort 100K avg_ns <= 50,000,000 on ARM64")
    lines.append("=" * 80)

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Text summary saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
