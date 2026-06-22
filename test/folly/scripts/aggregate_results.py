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
    parser = argparse.ArgumentParser(description='Aggregate folly benchmark results')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--output', required=True, help='Output results.json file path')
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = {}
    containers_data = {}
    concurrency_data = {}
    codec_data = {}
    scaling_data = {}

    vi_path = os.path.join(results_dir, 'version_info.json')
    if os.path.exists(vi_path):
        with open(vi_path, 'r') as f:
            version_info = json.load(f)

    cont_path = os.path.join(results_dir, 'benchmark_containers.json')
    if os.path.exists(cont_path):
        with open(cont_path, 'r') as f:
            containers_data = json.load(f)

    conc_path = os.path.join(results_dir, 'benchmark_concurrency.json')
    if os.path.exists(conc_path):
        with open(conc_path, 'r') as f:
            concurrency_data = json.load(f)

    codec_path = os.path.join(results_dir, 'benchmark_codec.json')
    if os.path.exists(codec_path):
        with open(codec_path, 'r') as f:
            codec_data = json.load(f)

    scale_path = os.path.join(results_dir, 'benchmark_scaling.json')
    if os.path.exists(scale_path):
        with open(scale_path, 'r') as f:
            scaling_data = json.load(f)

    summary = {}

    if containers_data.get("results"):
        f14_results = [r for r in containers_data["results"] if "f14_ops_per_sec" in r]
        if f14_results:
            f14_ops = [safe_float(r.get("f14_ops_per_sec", 0)) for r in f14_results]
            summary["avg_f14_ops_per_sec"] = round(sum(f14_ops) / len(f14_ops), 2)

        fbstring_results = [r for r in containers_data["results"] if r.get("container_type") == "fbstring"]
        if fbstring_results:
            fb_ops = [safe_float(r.get("ops_per_sec", 0)) for r in fbstring_results]
            summary["avg_fbstring_ops_per_sec"] = round(sum(fb_ops) / len(fb_ops), 2)

        std_results = [r for r in containers_data["results"] if r.get("container_type") == "std::string"]
        fb_append = [r for r in containers_data["results"] if r.get("operation") == "fbstring_append"]
        std_append = [r for r in containers_data["results"] if r.get("operation") == "std_string_append"]
        if fb_append and std_append:
            fb_val = safe_float(fb_append[0].get("ops_per_sec", 0))
            std_val = safe_float(std_append[0].get("ops_per_sec", 0))
            if std_val > 0:
                summary["fbstring_vs_std_ratio"] = round(fb_val / std_val, 2)

    if concurrency_data.get("results"):
        avg_lats = [safe_float(r.get("avg_latency_ms", 0)) for r in concurrency_data["results"]]
        p99_lats = [safe_float(r.get("p99_latency_ms", 0)) for r in concurrency_data["results"]]
        if avg_lats:
            summary["max_avg_concurrency_latency_ms"] = round(max(avg_lats), 4)
        if p99_lats:
            summary["max_p99_concurrency_latency_ms"] = round(max(p99_lats), 4)

    if codec_data.get("results"):
        json_parse = [r for r in codec_data["results"] if r.get("operation") == "json_parse"]
        if json_parse:
            summary["avg_json_parse_ops"] = round(safe_float(json_parse[0].get("ops_per_sec", 0)), 2)

        iobuf_results = [r for r in codec_data["results"] if r.get("category") == "buffer"]
        if iobuf_results:
            iobuf_ops = [safe_float(r.get("ops_per_sec", 0)) for r in iobuf_results]
            summary["avg_iobuf_ops"] = round(sum(iobuf_ops) / len(iobuf_ops), 2)

    if scaling_data.get("results"):
        insert_1t = [r for r in scaling_data["results"] if r.get("thread_count") == 1 and r.get("mode") == "insert"]
        insert_8t = [r for r in scaling_data["results"] if r.get("thread_count") == 8 and r.get("mode") == "insert"]
        if insert_1t and insert_8t:
            s1 = safe_float(insert_1t[0].get("total_ops_per_sec", 0))
            s8 = safe_float(insert_8t[0].get("total_ops_per_sec", 0))
            if s1 > 0:
                summary["concurrency_scaling_ratio"] = round(s8 / s1, 2)

    result = {
        "environment": version_info,
        "benchmarks": {
            "containers": containers_data,
            "concurrency": concurrency_data,
            "codec": codec_data,
            "scaling": scaling_data,
        },
        "summary": summary,
        "timestamp": datetime.datetime.now().isoformat(),
        "software": "folly",
        "version": version_info.get("software_version", "2024.10.14.00"),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"[AGGREGATE] Results saved to {args.output}")


if __name__ == '__main__':
    main()
