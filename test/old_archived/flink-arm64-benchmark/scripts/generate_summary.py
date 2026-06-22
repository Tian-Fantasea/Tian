#!/usr/bin/env python3

import argparse
import json
import os
import sys


def generate_summary(results_dir):
    agg_file = os.path.join(results_dir, "all_results.json")
    if not os.path.exists(agg_file):
        print("[SUMMARY] No aggregated results found")
        return

    with open(agg_file, "r") as f:
        data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("Apache Flink ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)

    vi = data.get("version_info", {})
    sw = vi.get("software", {})
    lines.append(f"\nSoftware:    Apache Flink {sw.get('version', 'N/A')}")
    lines.append(f"Scala:       {sw.get('scala_version', 'N/A')}")
    lines.append(f"Java:        {sw.get('java_version', 'N/A')}")
    lines.append(f"Architecture: {vi.get('architecture', 'N/A')}")
    lines.append(f"CPU:         {vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)")
    lines.append(f"Memory:      {vi.get('memory_mb', 'N/A')} MB")
    lines.append(f"OS:          {vi.get('os', 'N/A')}")
    lines.append(f"Kernel:      {vi.get('kernel', 'N/A')}")
    lines.append(f"Timestamp:   {vi.get('timestamp', 'N/A')}")

    benchmarks = data.get("benchmarks", {})

    lines.append(f"\n{'-' * 70}")
    lines.append("TPC-DS SQL Benchmark")
    lines.append(f"{'-' * 70}")
    tpcds = benchmarks.get("tpcds", {})
    for r in tpcds.get("results", []):
        lines.append(f"  Query {r.get('query', 'N/A')}: avg {r.get('avg_elapsed_sec', 'N/A')}s, {r.get('avg_records_per_sec', 'N/A')} records/s ({r.get('iterations', 'N/A')} iterations)")

    lines.append(f"\n{'-' * 70}")
    lines.append("Streaming Throughput Benchmark")
    lines.append(f"{'-' * 70}")
    streaming = benchmarks.get("streaming", {})
    for r in streaming.get("results", []):
        lines.append(f"  {r.get('config', 'N/A')} (p={r.get('parallelism', 'N/A')}): avg {r.get('avg_elapsed_sec', 'N/A')}s, {r.get('avg_records_per_sec', 'N/A')} records/s, latency {r.get('avg_latency_ms', 'N/A')}ms")

    lines.append(f"\n{'-' * 70}")
    lines.append("Micro Benchmark")
    lines.append(f"{'-' * 70}")
    micro = benchmarks.get("micro", {})
    for r in micro.get("results", []):
        lines.append(f"  {r.get('name', 'N/A')}: avg {r.get('avg_elapsed_sec', 'N/A')}s, {r.get('avg_rows_per_sec', 'N/A')} rows/s")

    lines.append(f"\n{'-' * 70}")
    lines.append("State Backend Benchmark")
    lines.append(f"{'-' * 70}")
    state = benchmarks.get("state", {})
    for r in state.get("results", []):
        ckpt_mb = round(r.get("avg_checkpoint_size_bytes", 0) / 1024 / 1024, 2)
        lines.append(f"  {r.get('name', 'N/A')}: avg {r.get('avg_elapsed_sec', 'N/A')}s, checkpoint {ckpt_mb} MB, interval {r.get('checkpoint_interval_ms', 'N/A')}ms")

    lines.append(f"\n{'=' * 70}")
    lines.append("End of Summary")
    lines.append(f"{'=' * 70}")

    summary = "\n".join(lines)
    out_file = os.path.join(results_dir, "benchmark_summary.txt")
    with open(out_file, "w") as f:
        f.write(summary)
    print(summary)
    print(f"[SUMMARY] Saved to {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark summary")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    generate_summary(args.results_dir)


if __name__ == "__main__":
    main()