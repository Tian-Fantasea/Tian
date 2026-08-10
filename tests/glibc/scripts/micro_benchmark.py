#!/usr/bin/env python3
"""Micro benchmark for glibc: per-function latency and multithread scaling.

Uses the same benchtests JSON output but extracts per-function detail
and attempts to measure thread scaling via bench-pthread benchset.
"""
import subprocess
import signal
import sys
import os
import json
import glob
import shutil
from datetime import datetime, timezone

BENCHSETS_MT = ["bench-pthread"]


def run_benchset(build_dir, benchset, timeout=300):
    """Run a benchset with proper process group timeout handling."""
    print(f"[MICRO] Running {benchset}...")
    proc = subprocess.Popen(
        ["make", f"BENCHSET={benchset}", "bench"],
        cwd=build_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()
        print(f"[MICRO] {benchset} timed out after {timeout}s, collecting partial results")

    bench_out = os.path.join(build_dir, "benchtests", "bench.out")
    bench_named = os.path.join(build_dir, "benchtests", f"{benchset}.out")
    if os.path.exists(bench_out):
        shutil.copy2(bench_out, bench_named)
        print(f"[MICRO] Saved {benchset} results to {benchset}.out")
    return os.path.exists(bench_named)


def parse_pthread_results(build_dir):
    """Parse bench-pthread results for thread scaling data."""
    bench_dir = os.path.join(build_dir, "benchtests")
    results = {}
    for json_path in sorted(glob.glob(os.path.join(bench_dir, "bench-pthread*.out"))):
        try:
            with open(json_path) as f:
                data = json.load(f)
        except Exception:
            continue
        functions = data.get("functions", {})
        for func_name, func_data in functions.items():
            if not isinstance(func_data, dict):
                continue
            for variant, vdata in func_data.items():
                if not isinstance(vdata, dict):
                    continue
                timings = vdata.get("timings", [])
                if timings:
                    mean = vdata.get("mean", sum(timings) / len(timings))
                    results[f"{func_name}.{variant}" if variant else func_name] = {
                        "mean_ns": round(mean, 2),
                        "min_ns": round(min(timings), 2),
                        "max_ns": round(max(timings), 2),
                    }
                elif "mean" in vdata:
                    results[f"{func_name}.{variant}" if variant else func_name] = {
                        "mean_ns": round(vdata.get("mean", 0), 2),
                        "min_ns": round(vdata.get("min", 0), 2),
                        "max_ns": round(vdata.get("max", 0), 2),
                    }
    return results


def parse_malloc_results(build_dir):
    """Parse bench-malloc results for thread scaling."""
    bench_dir = os.path.join(build_dir, "benchtests")
    results = {}
    for json_path in sorted(glob.glob(os.path.join(bench_dir, "bench-malloc*.out"))):
        try:
            with open(json_path) as f:
                data = json.load(f)
        except Exception:
            continue
        functions = data.get("functions", {})
        for func_name, func_data in functions.items():
            if not isinstance(func_data, dict):
                continue
            for variant, vdata in func_data.items():
                if not isinstance(vdata, dict):
                    continue
                timings = vdata.get("timings", [])
                if timings:
                    mean = vdata.get("mean", sum(timings) / len(timings))
                elif "mean" in vdata:
                    mean = vdata.get("mean", 0)
                else:
                    continue
                results[f"{func_name}.{variant}" if variant else func_name] = {
                    "mean_ns": round(mean, 2),
                }
    return results


def main():
    if len(sys.argv) < 3:
        print("Usage: micro_benchmark.py <build_dir> <output_file>")
        sys.exit(1)
    build_dir = sys.argv[1]
    output_file = sys.argv[2]
    version_str = os.environ.get("SOFTWARE_VERSION", "2.44")

    if not os.path.isdir(build_dir):
        print(f"[MICRO] Build dir not found: {build_dir}")
        sys.exit(1)

    bench_dir = os.path.join(build_dir, "benchtests")
    existing = glob.glob(os.path.join(bench_dir, "bench-pthread*.out")) + \
               glob.glob(os.path.join(bench_dir, "bench-malloc*.out"))
    bench_timeout = int(os.environ.get("BENCH_TIMEOUT", "300"))
    if not existing:
        for benchset in BENCHSETS_MT:
            run_benchset(build_dir, benchset, timeout=bench_timeout)

    print("[MICRO] Parsing pthread results...")
    pthread_results = parse_pthread_results(build_dir)
    print(f"[MICRO] Found {len(pthread_results)} pthread functions")

    print("[MICRO] Parsing malloc results...")
    malloc_results = parse_malloc_results(build_dir)
    print(f"[MICRO] Found {len(malloc_results)} malloc functions")

    out = {
        "benchmark": "micro_operations",
        "description": "glibc micro: pthread lock scaling + malloc thread scaling on ARM64",
        "reference": "https://sourceware.org/glibc/wiki/",
        "software": "glibc",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "mean_ns": {"unit": "ns", "description": "Mean timing per operation (nanoseconds)"},
        },
        "parameters": {
            "benchsets": BENCHSETS_MT,
        },
        "results": {
            "pthread_scaling": pthread_results,
            "malloc_scaling": malloc_results,
        },
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[MICRO] Output written to {output_file}")


if __name__ == "__main__":
    main()
