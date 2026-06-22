#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Aggregate all benchmark JSON results")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True, help="Output results.json file")
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = load_json(os.path.join(results_dir, "version_info.json"))
    locomo = load_json(os.path.join(results_dir, "benchmark_locomo.json"))
    hotpotqa = load_json(os.path.join(results_dir, "benchmark_hotpotqa.json"))
    micro = load_json(os.path.join(results_dir, "micro_benchmark.json"))

    aggregated = {
        "benchmark_suite": "openviking_arm64_performance",
        "timestamp": datetime.datetime.now().isoformat(),
        "environment": version_info or {},
        "benchmarks": {
            "locomo": locomo or {},
            "hotpotqa": hotpotqa or {},
            "micro": micro or {}
        },
        "summary": {}
    }

    all_throughputs = []
    all_latencies = []

    if locomo and locomo.get("results"):
        summary = locomo.get("summary", {})
        if summary:
            avg_acc = summary.get("avg_accuracy_pct", 0)
            avg_lat = summary.get("avg_query_time_ms", 0)
            aggregated["summary"]["locomo_avg_accuracy_pct"] = avg_acc
            aggregated["summary"]["locomo_avg_latency_ms"] = avg_lat
            aggregated["summary"]["locomo_slo_met"] = avg_acc >= 80 and avg_lat <= 500
            if avg_lat > 0:
                all_latencies.append(("locomo_avg", avg_lat))

    if hotpotqa and hotpotqa.get("results"):
        summary = hotpotqa.get("summary", {})
        if summary:
            avg_acc = summary.get("avg_accuracy_pct", 0)
            avg_lat = summary.get("avg_query_time_ms", 0)
            aggregated["summary"]["hotpotqa_avg_accuracy_pct"] = avg_acc
            aggregated["summary"]["hotpotqa_avg_latency_ms"] = avg_lat
            aggregated["summary"]["hotpotqa_slo_met"] = avg_acc >= 72
            if avg_lat > 0:
                all_latencies.append(("hotpotqa_avg", avg_lat))

    if micro and micro.get("results"):
        emb_results = [r for r in micro["results"]
                       if r.get("operation") == "embedding_throughput"]
        if emb_results:
            avg_throughput = sum(r.get("embeddings_per_sec", 0) for r in emb_results) / len(emb_results)
            aggregated["summary"]["embedding_throughput_per_sec"] = round(avg_throughput, 2)
            aggregated["summary"]["embedding_throughput_slo_met"] = avg_throughput >= 50
            all_throughputs.append(("embedding", avg_throughput))

        ret_results = [r for r in micro["results"]
                       if r.get("operation") == "retrieval_latency"]
        if ret_results:
            avg_qps = sum(r.get("queries_per_sec", 0) for r in ret_results) / len(ret_results)
            avg_lat = sum(r.get("avg_latency_ms", 0) for r in ret_results) / len(ret_results)
            aggregated["summary"]["retrieval_qps"] = round(avg_qps, 2)
            aggregated["summary"]["retrieval_avg_latency_ms"] = round(avg_lat, 2)
            aggregated["summary"]["retrieval_qps_slo_met"] = avg_qps >= 10
            all_throughputs.append(("retrieval", avg_qps))
            all_latencies.append(("retrieval_avg", avg_lat))

        ctx_results = [r for r in micro["results"]
                       if r.get("operation") == "context_tier_loading"]
        if ctx_results:
            aggregated["summary"]["context_L0_avg_ms"] = ctx_results[0].get("L0_avg_ms", 0)
            aggregated["summary"]["context_L1_avg_ms"] = ctx_results[0].get("L1_avg_ms", 0)
            aggregated["summary"]["context_L2_avg_ms"] = ctx_results[0].get("L2_avg_ms", 0)

    if all_throughputs:
        max_tp = max(all_throughputs, key=lambda x: x[1])
        avg_tp = sum(x[1] for x in all_throughputs) / len(all_throughputs)
        aggregated["summary"]["max_throughput"] = {"name": max_tp[0], "value": round(max_tp[1], 1), "unit": "ops/sec"}
        aggregated["summary"]["avg_throughput"] = round(avg_tp, 1)

    if all_latencies:
        max_lat = max(all_latencies, key=lambda x: x[1])
        avg_lat_val = sum(x[1] for x in all_latencies) / len(all_latencies)
        aggregated["summary"]["max_latency"] = {"name": max_lat[0], "value": round(max_lat[1], 2), "unit": "ms"}
        aggregated["summary"]["avg_latency"] = round(avg_lat_val, 2)

    with open(args.output, 'w') as f:
        json.dump(aggregated, f, indent=2)

    print(f"[AGGREGATE] Results aggregated to {args.output}")


if __name__ == "__main__":
    main()