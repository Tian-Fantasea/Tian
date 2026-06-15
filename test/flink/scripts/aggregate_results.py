#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Aggregate benchmark results")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = {}
    vi_path = os.path.join(results_dir, "version_info.json")
    if os.path.exists(vi_path):
        with open(vi_path) as f:
            version_info = json.load(f)

    primary_benchmark = {}
    pb_path = os.path.join(results_dir, "benchmark_primary.json")
    if os.path.exists(pb_path):
        with open(pb_path) as f:
            primary_benchmark = json.load(f)

    secondary_benchmark = {}
    sb_path = os.path.join(results_dir, "benchmark_secondary.json")
    if os.path.exists(sb_path):
        with open(sb_path) as f:
            secondary_benchmark = json.load(f)

    micro_benchmark = {}
    mb_path = os.path.join(results_dir, "micro_benchmark.json")
    if os.path.exists(mb_path):
        with open(mb_path) as f:
            micro_benchmark = json.load(f)

    primary_avg = primary_benchmark.get("average_throughput_ops_per_sec", 0)
    secondary_avg_throughput = secondary_benchmark.get("average_throughput_events_per_sec", 0)
    secondary_avg_latency = secondary_benchmark.get("average_latency_ms", 0)

    micro_ops = {}
    if micro_benchmark.get("results"):
        for op in micro_benchmark["results"]:
            micro_ops[op.get("operation_id", "unknown")] = {
                "name": op.get("name", "unknown"),
                "throughput": op.get("average_throughput_ops_per_sec", 0),
                "latency": op.get("average_latency_ms", 0),
                "category": op.get("category", "unknown")
            }

    tpcds_pass = primary_avg >= 500
    streaming_pass = secondary_avg_throughput >= 10000 and secondary_avg_latency <= 500

    overall_pass = tpcds_pass and streaming_pass

    output = {
        "software": "flink",
        "version": version_info.get("version", "unknown"),
        "architecture": version_info.get("architecture", "arm64"),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": version_info,
        "primary_benchmark": primary_benchmark,
        "secondary_benchmark": secondary_benchmark,
        "micro_benchmark": micro_benchmark,
        "summary": {
            "tpcds_avg_throughput_ops_per_sec": primary_avg,
            "streaming_avg_throughput_events_per_sec": secondary_avg_throughput,
            "streaming_avg_latency_ms": secondary_avg_latency,
            "micro_operations": micro_ops,
            "tpcds_pass": tpcds_pass,
            "streaming_pass": streaming_pass,
            "overall_pass": overall_pass
        },
        "thresholds": {
            "tpcds_min_throughput_ops_per_sec": 500,
            "streaming_min_throughput_events_per_sec": 10000,
            "streaming_max_latency_ms": 500
        }
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print("[AGGREGATE] Results aggregated to {}".format(args.output))

if __name__ == "__main__":
    main()