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


def collect_ops_from_results(results):
    if isinstance(results, list):
        ops_vals = []
        for r in results:
            if isinstance(r, dict):
                ops = r.get("ops_per_sec", r.get("OpsPerSec", r.get("write_ops_per_sec", 0)))
                if ops > 0:
                    ops_vals.append(safe_float(ops))
        return ops_vals
    return []


def collect_latency_from_results(results):
    if isinstance(results, list):
        lat_vals = []
        for r in results:
            if isinstance(r, dict):
                lat = r.get("avg_latency_ms", r.get("AvgLatencyMs", 0))
                if lat > 0:
                    lat_vals.append(safe_float(lat))
        return lat_vals
    return []


def main():
    parser = argparse.ArgumentParser(description='Aggregate bbolt benchmark results')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--output', required=True, help='Output results.json file path')
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = {}
    vi_path = os.path.join(results_dir, 'version_info.json')
    if os.path.exists(vi_path):
        with open(vi_path, 'r') as f:
            version_info = json.load(f)

    ycsb_data = {}
    ycsb_path = os.path.join(results_dir, 'benchmark_ycsb.json')
    if os.path.exists(ycsb_path):
        with open(ycsb_path, 'r') as f:
            ycsb_data = json.load(f)

    throughput_data = {}
    throughput_path = os.path.join(results_dir, 'benchmark_throughput.json')
    if os.path.exists(throughput_path):
        with open(throughput_path, 'r') as f:
            throughput_data = json.load(f)

    micro_data = {}
    micro_path = os.path.join(results_dir, 'micro_benchmark.json')
    if os.path.exists(micro_path):
        with open(micro_path, 'r') as f:
            micro_data = json.load(f)

    concurrency_data = {}
    concurrency_path = os.path.join(results_dir, 'benchmark_concurrency.json')
    if os.path.exists(concurrency_path):
        with open(concurrency_path, 'r') as f:
            concurrency_data = json.load(f)

    summary = {}

    ycsb_results = ycsb_data.get('results', [])
    ycsb_ops = collect_ops_from_results(ycsb_results)
    ycsb_lat = collect_latency_from_results(ycsb_results)
    if ycsb_ops:
        summary["avg_ycsb_ops_per_sec"] = round(sum(ycsb_ops) / len(ycsb_ops), 1)
    if ycsb_lat:
        summary["avg_ycsb_latency_ms"] = round(sum(ycsb_lat) / len(ycsb_lat), 2)

    throughput_results = throughput_data.get('results', [])
    tp_ops = collect_ops_from_results(throughput_results)
    if tp_ops:
        summary["avg_throughput_write_ops"] = round(sum(tp_ops) / len(tp_ops), 1)

    micro_results = micro_data.get('results', [])
    micro_ops = collect_ops_from_results(micro_results)
    micro_lat = collect_latency_from_results(micro_results)
    if micro_ops:
        summary["avg_micro_ops_per_sec"] = round(sum(micro_ops) / len(micro_ops), 1)
    if micro_lat:
        summary["avg_micro_latency_ms"] = round(sum(micro_lat) / len(micro_lat), 2)

    concurrency_results = concurrency_data.get('results', [])
    conc_ops = collect_ops_from_results(concurrency_results)
    if conc_ops:
        summary["avg_concurrency_ops_per_sec"] = round(sum(conc_ops) / len(conc_ops), 1)

    result = {
        "environment": version_info,
        "benchmarks": {
            "ycsb": ycsb_data,
            "throughput": throughput_data,
            "micro": micro_data,
            "concurrency": concurrency_data,
        },
        "summary": summary,
        "timestamp": datetime.datetime.now().isoformat(),
        "software": "bbolt",
        "version": version_info.get("software_version", "1.4.3"),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"[AGGREGATE] Results saved to {args.output}")


if __name__ == '__main__':
    main()
