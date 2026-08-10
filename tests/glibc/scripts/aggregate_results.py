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

    all_means = []
    all_mins = []
    benchset_count = 0
    func_count = 0

    for benchset_name, benchset_data in rs.items():
        if not isinstance(benchset_data, dict):
            continue
        if "error" in benchset_data:
            continue
        benchset_count += 1
        functions = benchset_data.get("functions", {})
        for func_name, func_data in functions.items():
            if not isinstance(func_data, dict):
                continue
            func_count += 1
            mean = func_data.get("mean_ns")
            if mean:
                all_means.append(safe_float(mean))
            min_val = func_data.get("min_ns")
            if min_val:
                all_mins.append(safe_float(min_val))

    summary["benchset_count"] = benchset_count
    summary["function_count"] = func_count
    if all_means:
        summary["avg_mean_ns"] = round(sum(all_means) / len(all_means), 2)
        summary["max_mean_ns"] = round(max(all_means), 2)
    if all_mins:
        summary["min_timing_ns"] = round(min(all_mins), 2)

    mresults = micro.get("results", {})
    if isinstance(mresults, dict):
        pthread = mresults.get("pthread_scaling", {})
        if isinstance(pthread, dict) and pthread:
            pthread_means = [safe_float(v.get("mean_ns", 0)) for v in pthread.values()
                            if isinstance(v, dict) and v.get("mean_ns")]
            if pthread_means:
                summary["pthread_avg_mean_ns"] = round(sum(pthread_means) / len(pthread_means), 2)
                summary["pthread_count"] = len(pthread_means)
        malloc = mresults.get("malloc_scaling", {})
        if isinstance(malloc, dict) and malloc:
            malloc_means = [safe_float(v.get("mean_ns", 0)) for v in malloc.values()
                           if isinstance(v, dict) and v.get("mean_ns")]
            if malloc_means:
                summary["malloc_avg_mean_ns"] = round(sum(malloc_means) / len(malloc_means), 2)
                summary["malloc_count"] = len(malloc_means)

    return summary


def aggregate_results(results_dir, output_file):
    primary = {}
    micro = {}
    version_info = {}

    for fname, key in [("benchmark_glibc.json", "primary"), ("micro_benchmark.json", "micro")]:
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
        print(f"[AGGREGATE] Loaded environment from {env_path}")

    summary = compute_summary(primary, micro)

    result = {
        "test_time": version_info.get("test_time", version_info.get("timestamp",
                       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))),
        "environment": version_info,
        "benchmarks": {"primary": primary, "micro": micro},
        "summary": summary,
        "software": "glibc",
        "version": version_info.get("software_version", "2.44"),
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
