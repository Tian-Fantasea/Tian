#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description="Aggregate all benchmark JSON results")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    all_data = {}
    json_files = [
        "version_info.json",
        "benchmark_ycsb.json",
        "benchmark_dbbench.json",
        "micro_benchmark.json",
    ]

    for filename in json_files:
        filepath = os.path.join(args.results_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                data = json.load(f)
            all_data[filename] = data
            print(f"[AGGREGATE] Loaded {filename}")
        else:
            print(f"[AGGREGATE] WARNING: {filename} not found, skipping")

    all_data["aggregation_timestamp"] = datetime.datetime.now().isoformat()
    all_data["aggregation_files"] = json_files

    output_path = os.path.join(args.results_dir, "all_results.json")
    with open(output_path, "w") as f:
        json.dump(all_data, f, indent=2)

    print(f"[AGGREGATE] All results aggregated at: {output_path}")


if __name__ == "__main__":
    main()