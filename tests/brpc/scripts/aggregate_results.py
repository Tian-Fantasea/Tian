#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def compute_summary(primary, micro):
    summary = {}
    rs = primary.get("results_summary", {})
    all_qps = []
    all_p99 = []
    for label, res in rs.items():
        if not isinstance(res, dict):
            continue
        if res.get("qps"):
            all_qps.append(safe_float(res["qps"]))
        if res.get("p99_us"):
            all_p99.append(safe_float(res["p99_us"]))
    if all_qps:
        summary["avg_qps"] = round(sum(all_qps) / len(all_qps), 2)
        summary["max_qps"] = round(max(all_qps), 2)
    if all_p99:
        summary["avg_p99_us"] = round(sum(all_p99) / len(all_p99), 2)
        summary["min_p99_us"] = round(min(all_p99), 2)
    t16 = rs.get("threads_16", {})
    if isinstance(t16, dict) and t16.get("qps"):
        summary["qps_t16"] = safe_float(t16["qps"])
        summary["p99_t16"] = safe_float(t16.get("p99_us", 0))
    t64 = rs.get("threads_64", {})
    t1 = rs.get("threads_1", {})
    if isinstance(t64, dict) and isinstance(t1, dict) and t64.get("qps") and t1.get("qps"):
        summary["thread_scaling_ratio"] = round(safe_float(t64["qps"]) / safe_float(t1["qps"]), 2)
    mresults = micro.get("results", {})
    if isinstance(mresults, dict):
        ps = mresults.get("payload_sweep", {})
        if isinstance(ps, dict) and ps:
            ps_qps = [safe_float(v.get("qps", 0)) for v in ps.values() if isinstance(v, dict) and v.get("qps")]
            if ps_qps:
                summary["payload_avg_qps"] = round(sum(ps_qps) / len(ps_qps), 2)
    return summary


def aggregate_results(results_dir, output_file):
    primary = {}
    micro = {}
    version_info = {}
    for fname, key in [("benchmark_rpc.json", "primary"), ("micro_benchmark.json", "micro")]:
        path = os.path.join(results_dir, fname)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            if key == "primary":
                primary = data
            else:
                micro = data
            print(f"[AGGREGATE] Loaded {key} from {path}")
    env_path = os.path.join(results_dir, "version_info.json")
    if os.path.exists(env_path):
        with open(env_path) as f:
            version_info = json.load(f)
    summary = compute_summary(primary, micro)
    result = {
        "test_time": version_info.get("test_time", version_info.get("timestamp",
                       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))),
        "environment": version_info,
        "benchmarks": {"primary": primary, "micro": micro},
        "summary": summary,
        "software": "brpc",
        "version": version_info.get("software_version", "1.17.0"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_file)) or ".", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[AGGREGATE] Aggregated results saved to {output_file}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: aggregate_results.py <results_dir> <output_file>")
        sys.exit(1)
    aggregate_results(sys.argv[1], sys.argv[2])
