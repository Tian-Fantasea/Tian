#!/usr/bin/env python3

import argparse
import json
import os
import sys


def aggregate_results(results_dir):
    benchmark_files = {
        "tpcds": "benchmark_tpcds.json",
        "streaming": "benchmark_streaming.json",
        "micro": "micro_benchmark.json",
        "state": "benchmark_state.json",
    }

    version_file = os.path.join(results_dir, "version_info.json")
    all_data = {}

    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            all_data["version_info"] = json.load(f)

    benchmarks = {}
    for name, filename in benchmark_files.items():
        filepath = os.path.join(results_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                benchmarks[name] = json.load(f)
        else:
            benchmarks[name] = {"benchmark": name, "results": [], "raw_results": [], "note": "file not found"}

    all_data["benchmarks"] = benchmarks

    out_file = os.path.join(results_dir, "all_results.json")
    with open(out_file, "w") as f:
        json.dump(all_data, f, indent=2)
    print(f"[AGGREGATE] Combined results saved to {out_file}")
    return all_data


def main():
    parser = argparse.ArgumentParser(description="Aggregate all benchmark results")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    aggregate_results(args.results_dir)


if __name__ == "__main__":
    main()