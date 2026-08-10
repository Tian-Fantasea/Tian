#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def compute_summary(primary, micro):
    summary = {}
    rs = primary.get("results_summary", {})

    # Library info
    lib = rs.get("library", {})
    if isinstance(lib, dict) and lib.get("size_bytes"):
        summary["lib_size_bytes"] = lib["size_bytes"]
        summary["lib_size_mb"] = lib.get("size_mb", round(lib["size_bytes"] / (1024 * 1024), 2))

    # Link test
    link = rs.get("link_test", {})
    if isinstance(link, dict):
        if link.get("compile_ok"):
            summary["link_test_passed"] = True
            if link.get("link_test_ops_per_sec"):
                summary["link_test_ops_per_sec"] = link["link_test_ops_per_sec"]
        elif "error" in link:
            summary["link_test_passed"] = False

    # Any benchmark binaries found
    bench_count = sum(1 for k, v in rs.items()
                     if isinstance(v, dict) and v.get("passed") is not None and k != "link_test")
    summary["benchmark_binaries_found"] = bench_count

    # Micro results
    mresults = micro.get("results", {})
    if isinstance(mresults, dict):
        lib_analysis = mresults.get("library_analysis", {})
        if isinstance(lib_analysis, dict):
            if lib_analysis.get("symbol_count"):
                summary["symbol_count"] = lib_analysis["symbol_count"]
            if lib_analysis.get("defined_symbols"):
                summary["defined_symbols"] = lib_analysis["defined_symbols"]
        bin_scan = mresults.get("binary_scan", {})
        if isinstance(bin_scan, dict):
            if bin_scan.get("total_binaries") is not None:
                summary["total_binaries"] = bin_scan["total_binaries"]
            if bin_scan.get("binaries_passed") is not None:
                summary["binaries_passed"] = bin_scan["binaries_passed"]

    return summary


def aggregate_results(results_dir, output_file):
    primary = {}
    micro = {}
    version_info = {}
    for fname, key in [("benchmark_bolt.json", "primary"), ("micro_benchmark.json", "micro")]:
        path = os.path.join(results_dir, fname)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            if key == "primary":
                primary = data
            else:
                micro = data
            print(f"[AGGREGATE] Loaded {key} from {path}")
    env_path = os.path.join(results_dir, "version_info.json")
    if os.path.exists(env_path):
        with open(env_path) as f:
            version_info = json.load(f)
    summary = compute_summary(primary, micro)
    result = {
        "test_time": version_info.get("test_time", version_info.get("timestamp",
                       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))),
        "environment": version_info,
        "benchmarks": {"primary": primary, "micro": micro},
        "summary": summary,
        "software": "bolt",
        "version": version_info.get("software_version", "main"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_file)) or ".", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[AGGREGATE] Aggregated results saved to {output_file}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: aggregate_results.py <results_dir> <output_file>")
        sys.exit(1)
    aggregate_results(sys.argv[1], sys.argv[2])
