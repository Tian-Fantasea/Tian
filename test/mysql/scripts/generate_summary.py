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
    parser = argparse.ArgumentParser(description="Generate text summary for MySQL benchmarks")
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
    lines.append("  MySQL ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append(f"  MySQL:         {version}")
    lines.append(f"  Date:          {timestamp}")
    lines.append(f"  Architecture:  {vi.get('architecture', 'unknown')}")
    lines.append(f"  CPU:           {vi.get('cpu_model', 'unknown')} ({vi.get('cores', 'unknown')} cores)")
    lines.append(f"  Memory:        {fmt_val(vi.get('memory_mb', 0), 'MB', 0)}")
    lines.append(f"  OS:            {vi.get('os', 'unknown')}")
    lines.append(f"  Kernel:        {vi.get('kernel', 'unknown')}")
    lines.append(f"  Compile Machine: {vi.get('compile_machine', 'unknown')}")
    lines.append(f"  Sysbench:      {vi.get('sysbench_version', 'unknown')}")
    lines.append(f"  InnoDB Buffer: {vi.get('innodb_buffer_pool_size', 'unknown')}")
    lines.append(f"  Max Conn:      {vi.get('max_connections', 'unknown')}")
    lines.append(f"  flush_log:     {vi.get('innodb_flush_log_at_trx_commit', 'unknown')}")
    lines.append(f"  sync_binlog:   {vi.get('sync_binlog', 'unknown')}")
    lines.append("=" * 80)

    oltp = data.get("oltp_benchmark", {})
    if oltp:
        lines.append("")
        lines.append("  OLTP BENCHMARK (sysbench)")
        lines.append("-" * 80)
        lines.append(f"  Reference: {oltp.get('reference', 'N/A')}")
        params = oltp.get("parameters", {})
        lines.append(f"  Table size: {params.get('table_size', 'N/A')} rows, Threads: {params.get('threads', 'N/A')}")
        for test_name, res in oltp.get("results", {}).items():
            if isinstance(res, dict):
                lines.append(f"    {test_name}:")
                lines.append(f"      TPS:    {res.get('avg_tps', 'N/A')}")
                lines.append(f"      QPS:    {res.get('avg_qps', 'N/A')}")
                lines.append(f"      LatAvg: {res.get('avg_latency_avg_ms', 'N/A')} ms")
                lines.append(f"      LatP95: {res.get('avg_latency_p95_ms', 'N/A')} ms")
                lines.append(f"      LatP99: {res.get('avg_latency_p99_ms', 'N/A')} ms")

    olap = data.get("olap_benchmark", {})
    if olap:
        lines.append("")
        lines.append("  CONCURRENCY SCALING & ANALYTICAL QUERIES")
        lines.append("-" * 80)
        lines.append(f"  Reference: {olap.get('reference', 'N/A')}")
        concurrency = olap.get("results", {}).get("concurrency_scaling", {})
        if concurrency:
            lines.append("  Concurrency Scaling (oltp_read_write):")
            for label, res in concurrency.items():
                lines.append(f"    {label}: TPS={res.get('avg_tps', 'N/A')}, QPS={res.get('avg_qps', 'N/A')}, LatP95={res.get('avg_lat_p95_ms', 'N/A')}ms")
        analytics = olap.get("results", {}).get("analytical_queries", {})
        if analytics:
            lines.append("  Analytical Queries:")
            for qname, res in analytics.items():
                lines.append(f"    {qname}: avg={res.get('avg_time_ms', 'N/A')}ms")

    micro = data.get("micro_benchmark", {})
    if micro:
        lines.append("")
        lines.append("  MICRO BENCHMARKS")
        lines.append("-" * 80)
        lines.append(f"  Reference: {micro.get('reference', 'N/A')}")
        for op_name, res in micro.get("results", {}).items():
            lines.append(f"    {op_name}: {json.dumps(res)}")

    lines.append("")
    lines.append("=" * 80)

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Text summary saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
