#!/usr/bin/env python3

import argparse
import glob
import json
import os
import sys


def aggregate_results(results_dir):
    version_file = os.path.join(results_dir, "version_info.json")
    all_data = {"benchmarks": []}

    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            all_data["version_info"] = json.load(f)

    bench_files = sorted(glob.glob(os.path.join(results_dir, "benchmark_*.json")))
    for bf in bench_files:
        try:
            with open(bf, "r") as f:
                data = json.load(f)
            all_data["benchmarks"].append(data)
        except Exception as e:
            print(f"[AGGREGATE] Warning: skipping {bf}: {e}", file=sys.stderr)

    micro_file = os.path.join(results_dir, "micro_benchmark.json")
    if os.path.exists(micro_file):
        try:
            with open(micro_file, "r") as f:
                data = json.load(f)
            all_data["benchmarks"].append(data)
        except Exception as e:
            print(f"[AGGREGATE] Warning: skipping {micro_file}: {e}", file=sys.stderr)

    out_path = os.path.join(results_dir, "all_results.json")
    with open(out_path, "w") as f:
        json.dump(all_data, f, indent=2)
    print(f"[AGGREGATE] Saved aggregated results to {out_path}")
    print(f"[AGGREGATE] Total benchmark files: {len(all_data['benchmarks'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()
    aggregate_results(args.results_dir)


if __name__ == "__main__":
    main()