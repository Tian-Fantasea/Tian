#!/usr/bin/env python3
"""Run glibc benchtests and parse JSON output.

glibc's `make bench` runs benchtests via the loader trick:
  /path/to/elf/ld-linux-aarch64.so.1 --library-path /path/to/build bench-binary

Each benchtest writes JSON to benchtests/bench-<name>.out with format:
  {"timing_type": "...", "functions": {"memcpy": {"...": {"timings": [...], "mean": ...}}}}

This script:
1. Runs `make bench BENCHSET=<name>` for each benchset
2. Collects and parses the bench-*.out JSON files
3. Aggregates into a single results_summary
"""
import subprocess
import sys
import os
import json
import glob
import shutil
from datetime import datetime, timezone

BENCHSETS = ["bench-math", "bench-string", "bench-pthread", "bench-malloc"]


def run_benchset(build_dir, benchset, timeout=600):
    """Run a single benchset via `make bench BENCHSET=...` in the build dir."""
    print(f"[BENCHMARK_GLIBC] Running {benchset}...")
    result = subprocess.run(
        ["make", f"BENCHSET={benchset}", "bench"],
        cwd=build_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        print(f"[BENCHMARK_GLIBC] {benchset} had issues: {result.stderr[:300]}")
    return result.returncode == 0


def parse_bench_json(json_path):
    """Parse a single bench-*.out JSON file and extract function timings."""
    try:
        with open(json_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[BENCHMARK_GLIBC] Failed to parse {json_path}: {e}")
        return {}

    results = {}
    timing_type = data.get("timing_type", "unknown")
    functions = data.get("functions", {})

    for func_name, func_data in functions.items():
        if not isinstance(func_data, dict):
            continue
        for variant, variant_data in func_data.items():
            if not isinstance(variant_data, dict):
                continue
            timings = variant_data.get("timings", [])
            if not timings:
                continue
            mean = variant_data.get("mean", 0)
            if mean == 0 and timings:
                mean = sum(timings) / len(timings)
            key = f"{func_name}.{variant}" if variant != "" else func_name
            results[key] = {
                "function": func_name,
                "variant": variant,
                "mean_ns": round(mean, 2),
                "timings_count": len(timings),
                "min_ns": round(min(timings), 2),
                "max_ns": round(max(timings), 2),
            }
    return {"timing_type": timing_type, "functions": results}


def collect_bench_results(build_dir):
    """Collect all bench-*.out JSON files from benchtests/ directory."""
    bench_dir = os.path.join(build_dir, "benchtests")
    if not os.path.isdir(bench_dir):
        print(f"[BENCHMARK_GLIBC] benchtests dir not found: {bench_dir}")
        return {}

    all_results = {}
    for json_path in sorted(glob.glob(os.path.join(bench_dir, "bench-*.out"))):
        name = os.path.basename(json_path).replace("bench-", "").replace(".out", "")
        parsed = parse_bench_json(json_path)
        if parsed:
            all_results[name] = parsed
            func_count = len(parsed.get("functions", {}))
            print(f"[BENCHMARK_GLIBC] Parsed {name}: {func_count} functions")

    return all_results


def main():
    if len(sys.argv) < 3:
        print("Usage: benchmark_glibc.py <build_dir> <output_file>")
        sys.exit(1)
    build_dir = sys.argv[1]
    output_file = sys.argv[2]

    if not os.path.isdir(build_dir):
        print(f"[BENCHMARK_GLIBC] Build dir not found: {build_dir}")
        sys.exit(1)

    version_str = os.environ.get("SOFTWARE_VERSION", "2.44")

    # Check if bench results already exist (from `make bench` in test.sh)
    bench_dir = os.path.join(build_dir, "benchtests")
    existing_files = glob.glob(os.path.join(bench_dir, "bench-*.out")) if os.path.isdir(bench_dir) else []

    if not existing_files:
        # Run benchtests ourselves
        for benchset in BENCHSETS:
            run_benchset(build_dir, benchset)

    # Collect and parse results
    results_summary = collect_bench_results(build_dir)

    if not results_summary:
        print("[BENCHMARK_GLIBC] No bench results found. Creating stub output.")
        results_summary = {"error": "no bench results generated"}

    out = {
        "benchmark": "glibc_benchtests",
        "description": f"glibc benchtests ({', '.join(BENCHSETS)}) on ARM64, run via loader trick",
        "reference": "https://sourceware.org/glibc/wiki/",
        "software": "glibc",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "mean_ns": {"unit": "ns", "description": "Mean timing per function call (nanoseconds)"},
            "min_ns": {"unit": "ns", "description": "Minimum timing"},
            "max_ns": {"unit": "ns", "description": "Maximum timing"},
        },
        "parameters": {
            "benchsets": BENCHSETS,
            "timing_method": "glibc hp-timing (architecture-specific high-precision counter)",
        },
        "results_summary": results_summary,
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    total_funcs = sum(len(r.get("functions", {})) for r in results_summary.values() if isinstance(r, dict))
    print(f"[BENCHMARK_GLIBC] Output written to {output_file} ({len(results_summary)} benchsets, {total_funcs} functions)")


if __name__ == "__main__":
    main()
