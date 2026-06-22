#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description="Aggregate all benchmark JSON results")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True, help="Output results.json file")
    args = parser.parse_args()

    all_data = {
        "benchmark_suite": "rocksdb_arm64_performance",
        "timestamp": None,
        "environment": None,
        "benchmarks": {},
        "summary": {},
    }

    json_files = {
        "ycsb": os.path.join(args.results_dir, "benchmark_ycsb.json"),
        "dbbench": os.path.join(args.results_dir, "benchmark_dbbench.json"),
        "micro": os.path.join(args.results_dir, "micro_benchmark.json"),
    }

    version_file = os.path.join(args.results_dir, "version_info.json")

    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            all_data["environment"] = json.load(f)
        all_data["timestamp"] = all_data["environment"].get("timestamp", "")

    all_throughputs = []
    all_latencies = []

    for bench_name, bench_file in json_files.items():
        if os.path.exists(bench_file):
            try:
                with open(bench_file, "r") as f:
                    data = json.load(f)
                all_data["benchmarks"][bench_name] = data

                results = data.get("results", {})
                if isinstance(results, dict):
                    for wl_name, wl_data in results.items():
                        if isinstance(wl_data, dict):
                            run_ops = wl_data.get("run_throughput_ops_sec", wl_data.get("avg_ops_sec", 0))
                            if isinstance(run_ops, (int, float)) and run_ops > 0:
                                all_throughputs.append((f"{bench_name}.{wl_name}", run_ops))
                            run_lat = wl_data.get("run_latency_avg_ms", wl_data.get("avg_latency_ms", 0))
                            if isinstance(run_lat, (int, float)) and run_lat > 0:
                                all_latencies.append((f"{bench_name}.{wl_name}", run_lat))
                elif isinstance(results, list):
                    for r in results:
                        tp = r.get("ops_per_sec", r.get("avg_ops_sec", 0))
                        if isinstance(tp, (int, float)) and tp > 0:
                            all_throughputs.append((bench_name, tp))
            except (json.JSONDecodeError, Exception) as e:
                all_data["benchmarks"][bench_name] = {"error": str(e)}

    if all_throughputs:
        max_tp = max(all_throughputs, key=lambda x: x[1])
        min_tp = min(all_throughputs, key=lambda x: x[1])
        avg_tp = sum(x[1] for x in all_throughputs) / len(all_throughputs)
        all_data["summary"]["max_throughput"] = {"name": max_tp[0], "value": round(max_tp[1], 1), "unit": "ops/sec"}
        all_data["summary"]["min_throughput"] = {"name": min_tp[0], "value": round(min_tp[1], 1), "unit": "ops/sec"}
        all_data["summary"]["avg_throughput"] = round(avg_tp, 1)

    if all_latencies:
        max_lat = max(all_latencies, key=lambda x: x[1])
        min_lat = min(all_latencies, key=lambda x: x[1])
        avg_lat = sum(x[1] for x in all_latencies) / len(all_latencies)
        all_data["summary"]["max_latency"] = {"name": max_lat[0], "value": round(max_lat[1], 4), "unit": "ms"}
        all_data["summary"]["min_latency"] = {"name": min_lat[0], "value": round(min_lat[1], 4), "unit": "ms"}
        all_data["summary"]["avg_latency"] = round(avg_lat, 4)

    with open(args.output, "w") as f:
        json.dump(all_data, f, indent=2)
    print(f"[AGGREGATE] Results aggregated to {args.output}")


if __name__ == "__main__":
    main()
