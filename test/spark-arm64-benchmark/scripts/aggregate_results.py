#!/usr/bin/env python3
"""
Aggregate all benchmark results into a single JSON file
"""

import sys
import os
import json
import glob
from datetime import datetime


def aggregate_results(result_dir, timestamp, output_file):
    """Find and aggregate all benchmark result JSON files"""
    all_results = {}

    # Find all result JSON files (excluding environment info and this aggregate)
    pattern = os.path.join(result_dir, "*_results_*.json")
    result_files = glob.glob(pattern)

    for rf in result_files:
        try:
            with open(rf) as f:
                data = json.load(f)
            bench_name = data.get("benchmark", "unknown")
            all_results[bench_name] = data
            print(f"[AGGREGATE] Loaded {bench_name} from {rf}")
        except Exception as e:
            print(f"[AGGREGATE] Failed to load {rf}: {e}")

    # Load environment info
    env_pattern = os.path.join(result_dir, "environment_info_*.json")
    env_files = glob.glob(env_pattern)
    if env_files:
        with open(env_files[0]) as f:
            env_info = json.load(f)
        all_results["environment"] = env_info
        print(f"[AGGREGATE] Loaded environment info from {env_files[0]}")

    aggregate = {
        "workflow": "Apache Spark ARM64 Performance Benchmark",
        "timestamp": datetime.now().isoformat(),
        "result_dir": result_dir,
        "benchmarks": all_results
    }

    with open(output_file, "w") as f:
        json.dump(aggregate, f, indent=2)
    print(f"[AGGREGATE] Aggregated results saved to {output_file}")

    return aggregate


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: aggregate_results.py <result_dir> <timestamp> <output_file>")
        sys.exit(1)

    result_dir = sys.argv[1]
    timestamp = sys.argv[2]
    output_file = sys.argv[3]
    aggregate_results(result_dir, timestamp, output_file)