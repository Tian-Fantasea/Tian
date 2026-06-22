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
    parser = argparse.ArgumentParser(description="Generate text summary for brpc benchmarks")
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
    lines.append("  brpc ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append(f"  brpc:           {version}")
    lines.append(f"  Date:            {timestamp}")
    lines.append(f"  Architecture:    {vi.get('architecture', 'unknown')}")
    lines.append(f"  CPU:             {vi.get('cpu_model', 'unknown')} ({vi.get('cores', 'unknown')} cores)")
    lines.append(f"  Memory:          {fmt_val(vi.get('memory_mb', 0), 'MB', 0)}")
    lines.append(f"  OS:              {vi.get('os', 'unknown')}")
    lines.append(f"  Kernel:          {vi.get('kernel', 'unknown')}")
    lines.append(f"  Compiler:        {vi.get('gcc_version', 'unknown')}")
    lines.append(f"  CMake:           {vi.get('cmake_version', 'unknown')}")
    lines.append(f"  Protobuf:        {vi.get('protobuf_version', 'unknown')}")
    lines.append(f"  OpenSSL:         {vi.get('openssl_support', 'unknown')}")
    lines.append("=" * 80)

    rpc = data.get("rpc_benchmark", {})
    if rpc:
        lines.append("")
        lines.append("  RPC BENCHMARK (Primary - baidu_std Protocol)")
        lines.append("-" * 80)
        lines.append(f"  Reference: {rpc.get('reference', 'N/A')}")
        lines.append(f"  Error:     {rpc.get('error', 'None')}")
        conc_levels = rpc.get("parameters", {}).get("concurrency_levels", [])
        lines.append(f"  Concurrency Levels: {conc_levels}")
        for name, res in rpc.get("results", {}).items():
            if isinstance(res, dict):
                qps = res.get("avg_qps", "N/A")
                avg_lat = res.get("avg_avg_latency_ms", "N/A")
                p99_lat = res.get("avg_p99_latency_ms", "N/A")
                errs = res.get("errors", 0)
                status = "OK" if errs == 0 else f"ERRORS({errs})"
                lines.append(f"    {name}: QPS={qps}  avg_lat={avg_lat}ms  p99={p99_lat}ms  [{status}]")

    proto = data.get("protocol_benchmark", {})
    if proto:
        lines.append("")
        lines.append("  PROTOCOL BENCHMARK (Secondary - Multi-Protocol Comparison)")
        lines.append("-" * 80)
        lines.append(f"  Reference: {proto.get('reference', 'N/A')}")
        lines.append(f"  Error:     {proto.get('error', 'None')}")
        protocols = proto.get("parameters", {}).get("protocols", [])
        lines.append(f"  Protocols: {protocols}")
        for pname, res in proto.get("results", {}).items():
            if isinstance(res, dict):
                qps = res.get("avg_qps", "N/A")
                avg_lat = res.get("avg_avg_latency_ms", "N/A")
                p99_lat = res.get("avg_p99_latency_ms", "N/A")
                lines.append(f"    {pname}: QPS={qps}  avg_lat={avg_lat}ms  p99={p99_lat}ms")

    micro = data.get("micro_benchmark", {})
    if micro:
        lines.append("")
        lines.append("  C++ MICRO BENCHMARKS")
        lines.append("-" * 80)
        lines.append(f"  Reference: {micro.get('reference', 'N/A')}")
        lines.append(f"  Compiler:  {micro.get('parameters', {}).get('compiler', 'N/A')}")
        lines.append(f"  Error:     {micro.get('error', 'None')}")
        for mname, res in micro.get("results", {}).items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                avg_ns = res.get("avg_avg_ns", "N/A")
                ops = res.get("avg_ops_per_sec", "N/A")
                lines.append(f"    {mname}: {desc}")
                lines.append(f"      avg_ns={avg_ns}  ops/sec={ops}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  ARM64 Threshold Reference")
    lines.append("=" * 80)
    lines.append("  - brpc baidu_std QPS >= 50,000 at conc=64 on ARM64")
    lines.append("  - brpc baidu_std P99 latency <= 2ms at conc=64 on ARM64")
    lines.append("  - brpc HTTP QPS >= 30,000 at conc=64 on ARM64")
    lines.append("  - mutex lock/unlock avg_ns <= 50 on ARM64")
    lines.append("  - atomic increment avg_ns <= 20 on ARM64")
    lines.append("  - memcpy 64KB avg_ns <= 30,000 on ARM64")
    lines.append("=" * 80)

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Text summary saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
