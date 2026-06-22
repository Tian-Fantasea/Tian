#!/usr/bin/env python3
import json
import os
import sys


def main():
    results_dir = sys.argv[1]

    bench_files = [
        ("locomo", os.path.join(results_dir, "benchmark_locomo.json")),
        ("hotpotqa", os.path.join(results_dir, "benchmark_hotpotqa.json")),
        ("micro", os.path.join(results_dir, "micro_benchmark.json")),
        ("stress", os.path.join(results_dir, "stress_benchmark.json")),
    ]

    version_file = os.path.join(results_dir, "version_info.json")
    version_info = {}
    if os.path.exists(version_file):
        with open(version_file) as f:
            version_info = json.load(f)

    all_data = {
        "software_name": "openviking",
        "aggregation_timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmttime()),
        "environment": version_info.get("environment", {}),
        "software": version_info.get("software", {}),
        "benchmarks": {}
    }

    for bench_name, bench_path in bench_files:
        if os.path.exists(bench_path):
            with open(bench_path) as f:
                all_data["benchmarks"][bench_name] = json.load(f)

    output_path = os.path.join(results_dir, "all_results.json")
    with open(output_path, "w") as f:
        json.dump(all_data, f, indent=2)
    print(f"[AGGREGATE] Aggregated {len(all_data['benchmarks'])} benchmarks to {output_path}")


if __name__ == "__main__":
    main()