#!/usr/bin/env python3

import argparse
import json
import os
import sys


def generate_summary(results_dir):
    all_path = os.path.join(results_dir, "all_results.json")
    if not os.path.exists(all_path):
        print("[SUMMARY] No aggregated results found", file=sys.stderr)
        return

    with open(all_path, "r") as f:
        all_data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("bbolt ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)

    vi = all_data.get("version_info", {})
    sw = vi.get("software", {})
    lines.append(f"Software:   bbolt v{sw.get('version', 'N/A')}")
    lines.append(f"Runtime:    {sw.get('runtime_language', 'N/A')} {sw.get('runtime_version', 'N/A')}")
    lines.append(f"Architecture: {vi.get('architecture', 'N/A')}")
    lines.append(f"CPU:        {vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)")
    lines.append(f"Memory:     {vi.get('memory_mb', 'N/A')} MB")
    lines.append(f"Kernel:     {vi.get('kernel', 'N/A')}")
    lines.append(f"OS:         {vi.get('os', 'N/A')}")
    lines.append(f"Timestamp:  {vi.get('timestamp', 'N/A')}")
    lines.append("")
    lines.append("-" * 70)

    for bench in all_data.get("benchmarks", []):
        name = bench.get("benchmark", "unknown")
        lines.append(f"Benchmark: {name}")
        lines.append(f"  Description: {bench.get('description', 'N/A')}")
        results = bench.get("results", [])
        if results:
            ops_vals = [r.get("ops_per_sec", r.get("OpsPerSec", 0)) for r in results if isinstance(r, dict)]
            lat_vals = [r.get("avg_latency_ms", r.get("AvgLatencyMs", 0)) for r in results if isinstance(r, dict)]
            if ops_vals:
                avg_ops = sum(ops_vals) / len(ops_vals)
                lines.append(f"  Avg ops/sec: {avg_ops:.1f}")
            if lat_vals:
                avg_lat = sum(lat_vals) / len(lat_vals)
                lines.append(f"  Avg latency: {avg_lat:.2f} ms")
            lines.append(f"  Total results: {len(results)}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    out_path = os.path.join(results_dir, "benchmark_summary.txt")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"[SUMMARY] Saved to {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()
    generate_summary(args.results_dir)


if __name__ == "__main__":
    main()