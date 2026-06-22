#!/usr/bin/env python3
import json
import os
import sys


def main():
    results_dir = sys.argv[1]

    agg_path = os.path.join(results_dir, "all_results.json")
    if not os.path.exists(agg_path):
        print("[SUMMARY] No aggregated results found")
        return

    with open(agg_path) as f:
        data = json.load(f)

    lines = []
    lines.append("=" * 60)
    lines.append("OpenViking ARM64 Performance Benchmark Summary")
    lines.append("=" * 60)
    lines.append("")

    env = data.get("environment", {})
    sw = data.get("software", {})
    lines.append("Environment:")
    lines.append(f"  Architecture: {env.get('architecture', 'N/A')}")
    lines.append(f"  OS:           {env.get('os', 'N/A')}")
    lines.append(f"  Kernel:       {env.get('kernel', 'N/A')}")
    lines.append(f"  CPU:          {env.get('cpu_model', 'N/A')}")
    lines.append(f"  Cores:        {env.get('cores', 'N/A')}")
    lines.append(f"  Memory:       {env.get('memory_mb', 'N/A')} MB")
    lines.append("")
    lines.append("Software:")
    lines.append(f"  Name:         {sw.get('name', 'N/A')}")
    lines.append(f"  Version:      {sw.get('version', 'N/A')}")
    lines.append("")

    benchmarks = data.get("benchmarks", {})

    for bench_name in ["locomo", "hotpotqa", "micro", "stress"]:
        bench = benchmarks.get(bench_name)
        if not bench:
            continue
        lines.append("-" * 40)
        lines.append(f"Benchmark: {bench.get('benchmark', bench_name)}")
        lines.append(f"Description: {bench.get('description', 'N/A')}")
        lines.append("")
        summary = bench.get("summary", {})
        results = bench.get("results", [])
        if summary:
            for key, val in summary.items():
                lines.append(f"  {key}: {val}")
        elif results:
            if isinstance(results, list) and len(results) > 0:
                for r in results[:3]:
                    op = r.get("operation", "unknown")
                    lines.append(f"  [{op}] iteration={r.get('iteration', 'N/A')}")
                    for k, v in r.items():
                        if k not in ("operation", "iteration", "error"):
                            lines.append(f"    {k}: {v}")
                    if "error" in r:
                        lines.append(f"    error: {r['error']}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("End of Summary")
    lines.append("=" * 60)

    output_path = os.path.join(results_dir, "benchmark_summary.txt")
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"[SUMMARY] Summary written to {output_path}")


if __name__ == "__main__":
    main()