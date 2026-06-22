#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def main():
    parser = argparse.ArgumentParser(description='Aggregate protobuf benchmark results')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--output', required=True, help='Output results.json file path')
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = {}
    serialization_data = {}
    latency_data = {}
    micro_data = {}
    concurrency_data = {}

    vi_path = os.path.join(results_dir, 'version_info.json')
    if os.path.exists(vi_path):
        with open(vi_path, 'r') as f:
            version_info = json.load(f)

    ser_path = os.path.join(results_dir, 'benchmark_serialization.json')
    if os.path.exists(ser_path):
        with open(ser_path, 'r') as f:
            serialization_data = json.load(f)

    lat_path = os.path.join(results_dir, 'benchmark_latency.json')
    if os.path.exists(lat_path):
        with open(lat_path, 'r') as f:
            latency_data = json.load(f)

    micro_path = os.path.join(results_dir, 'micro_benchmark.json')
    if os.path.exists(micro_path):
        with open(micro_path, 'r') as f:
            micro_data = json.load(f)

    conc_path = os.path.join(results_dir, 'benchmark_concurrency.json')
    if os.path.exists(conc_path):
        with open(conc_path, 'r') as f:
            concurrency_data = json.load(f)

    summary = {}

    if serialization_data.get("results"):
        small = [r for r in serialization_data["results"] if r.get("message_type") == "small_struct"]
        if small:
            summary["avg_serialize_ops_small"] = round(safe_float(small[0].get("serialize_ops_per_sec", 0)), 2)
            summary["avg_deserialize_ops_small"] = round(safe_float(small[0].get("deserialize_ops_per_sec", 0)), 2)
            summary["avg_serialize_bytes_small"] = round(safe_float(small[0].get("serialize_bytes_per_sec", 0)), 2)

        medium = [r for r in serialization_data["results"] if r.get("message_type") == "medium_struct"]
        if medium:
            summary["avg_serialize_ops_medium"] = round(safe_float(medium[0].get("serialize_ops_per_sec", 0)), 2)

        large = [r for r in serialization_data["results"] if r.get("message_type") == "large_struct"]
        if large:
            summary["avg_serialize_ops_large"] = round(safe_float(large[0].get("serialize_ops_per_sec", 0)), 2)

    if latency_data.get("results"):
        avg_lats = [safe_float(r.get("avg_latency_ms", 0)) for r in latency_data["results"]]
        p99_lats = [safe_float(r.get("p99_latency_ms", 0)) for r in latency_data["results"]]
        if avg_lats:
            summary["max_avg_latency_ms"] = round(max(avg_lats), 4)
        if p99_lats:
            summary["max_p99_latency_ms"] = round(max(p99_lats), 4)

    if micro_data.get("results"):
        serialize_ops = [safe_float(r.get("serialize_ops_per_sec", 0)) for r in micro_data["results"]]
        deserialize_ops = [safe_float(r.get("deserialize_ops_per_sec", 0)) for r in micro_data["results"]]
        if serialize_ops:
            summary["avg_micro_serialize_ops"] = round(sum(serialize_ops) / len(serialize_ops), 2)
        if deserialize_ops:
            summary["avg_micro_deserialize_ops"] = round(sum(deserialize_ops) / len(deserialize_ops), 2)

    if concurrency_data.get("results"):
        serialize_1t = [r for r in concurrency_data["results"] if r.get("thread_count") == 1 and r.get("mode") == "serialize"]
        serialize_8t = [r for r in concurrency_data["results"] if r.get("thread_count") == 8 and r.get("mode") == "serialize"]
        if serialize_1t and serialize_8t:
            s1 = safe_float(serialize_1t[0].get("total_ops_per_sec", 0))
            s8 = safe_float(serialize_8t[0].get("total_ops_per_sec", 0))
            if s1 > 0:
                summary["concurrency_scaling_ratio"] = round(s8 / s1, 2)

    result = {
        "environment": version_info,
        "benchmarks": {
            "serialization": serialization_data,
            "latency": latency_data,
            "micro": micro_data,
            "concurrency": concurrency_data,
        },
        "summary": summary,
        "timestamp": datetime.datetime.now().isoformat(),
        "software": "protobuf",
        "version": version_info.get("software_version", "29.4"),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"[AGGREGATE] Results saved to {args.output}")


if __name__ == '__main__':
    main()
