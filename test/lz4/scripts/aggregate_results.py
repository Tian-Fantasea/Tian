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
    parser = argparse.ArgumentParser(description='Aggregate lz4 benchmark results')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--output', required=True, help='Output results.json file path')
    args = parser.parse_args()

    results_dir = args.results_dir

    version_info = {}
    compression_data = {}
    decompression_data = {}
    micro_data = {}
    concurrency_data = {}

    vi_path = os.path.join(results_dir, 'version_info.json')
    if os.path.exists(vi_path):
        with open(vi_path, 'r') as f:
            version_info = json.load(f)

    comp_path = os.path.join(results_dir, 'benchmark_compression.json')
    if os.path.exists(comp_path):
        with open(comp_path, 'r') as f:
            compression_data = json.load(f)

    decomp_path = os.path.join(results_dir, 'benchmark_decompression.json')
    if os.path.exists(decomp_path):
        with open(decomp_path, 'r') as f:
            decompression_data = json.load(f)

    micro_path = os.path.join(results_dir, 'micro_benchmark.json')
    if os.path.exists(micro_path):
        with open(micro_path, 'r') as f:
            micro_data = json.load(f)

    conc_path = os.path.join(results_dir, 'benchmark_concurrency.json')
    if os.path.exists(conc_path):
        with open(conc_path, 'r') as f:
            concurrency_data = json.load(f)

    summary = {}

    if compression_data.get("results"):
        level1_text = [r for r in compression_data["results"]
                       if r.get("compression_level") == 1 and r.get("data_type") == "text"]
        if level1_text:
            throughput_vals = [safe_float(r.get("compression_throughput_mb_per_sec", 0)) for r in level1_text]
            summary["avg_compression_throughput_mb"] = round(sum(throughput_vals) / len(throughput_vals), 2)

        ratio_vals = [safe_float(r.get("compression_ratio", 0)) for r in compression_data["results"]
                      if r.get("data_type") == "text" and r.get("compression_level") == 1]
        if ratio_vals:
            summary["avg_compression_ratio"] = round(sum(ratio_vals) / len(ratio_vals), 4)

        hc9_text = [r for r in compression_data["results"]
                    if r.get("compression_level") == 9 and r.get("data_type") == "text"]
        if hc9_text and level1_text:
            hc_throughput = [safe_float(r.get("compression_throughput_mb_per_sec", 0)) for r in hc9_text]
            fast_throughput = [safe_float(r.get("compression_throughput_mb_per_sec", 0)) for r in level1_text]
            if fast_throughput and hc_throughput:
                avg_fast = sum(fast_throughput) / len(fast_throughput)
                avg_hc = sum(hc_throughput) / len(hc_throughput)
                if avg_fast > 0:
                    summary["hc_vs_fast_ratio"] = round(avg_hc / avg_fast, 4)

    if decompression_data.get("results"):
        text_1mb = [r for r in decompression_data["results"]
                    if "1MB" in r.get("data_name", "") and r.get("data_type") == "text"]
        if text_1mb:
            decomp_throughput = [safe_float(r.get("decompression_throughput_mb_per_sec", 0)) for r in text_1mb]
            summary["avg_decompression_throughput_mb"] = round(sum(decomp_throughput) / len(decomp_throughput), 2)

        avg_lats = [safe_float(r.get("avg_latency_ms", 0)) for r in decompression_data["results"]]
        p99_lats = [safe_float(r.get("p99_latency_ms", 0)) for r in decompression_data["results"]]
        if avg_lats:
            summary["max_avg_decompression_latency_ms"] = round(max(avg_lats), 4)
        if p99_lats:
            summary["max_p99_decompression_latency_ms"] = round(max(p99_lats), 4)

        if "avg_compression_throughput_mb" in summary and "avg_decompression_throughput_mb" in summary:
            comp = summary["avg_compression_throughput_mb"]
            decomp = summary["avg_decompression_throughput_mb"]
            if comp > 0:
                summary["decompress_vs_compress_ratio"] = round(decomp / comp, 2)

    if micro_data.get("results"):
        compress_ops = [safe_float(r.get("ops_per_sec", 0)) for r in micro_data["results"]
                       if "compress_default" in r.get("operation", "")]
        decompress_ops = [safe_float(r.get("ops_per_sec", 0)) for r in micro_data["results"]
                         if "decompress_default" in r.get("operation", "")]

        if compress_ops:
            summary["avg_compress_ops_per_sec"] = round(sum(compress_ops) / len(compress_ops), 2)
        if decompress_ops:
            summary["avg_decompress_ops_per_sec"] = round(sum(decompress_ops) / len(decompress_ops), 2)

        fast_ops = [safe_float(r.get("ops_per_sec", 0)) for r in micro_data["results"]
                    if "compress_fast" in r.get("operation", "") and r.get("acceleration") == 1]
        if fast_ops and compress_ops:
            summary["fast_vs_default_ratio"] = round(
                sum(fast_ops) / len(fast_ops) / (sum(compress_ops) / len(compress_ops)), 2)

    if concurrency_data.get("results"):
        compress_1t = [r for r in concurrency_data["results"]
                      if r.get("mode") == "compress" and r.get("thread_count") == 1]
        compress_8t = [r for r in concurrency_data["results"]
                      if r.get("mode") == "compress" and r.get("thread_count") == 8]

        if compress_1t and compress_8t:
            s1 = safe_float(compress_1t[0].get("total_throughput_mb_per_sec", 0))
            s8 = safe_float(compress_8t[0].get("total_throughput_mb_per_sec", 0))
            if s1 > 0:
                summary["concurrency_scaling_ratio"] = round(s8 / s1, 2)

    result = {
        "environment": version_info,
        "benchmarks": {
            "compression": compression_data,
            "decompression": decompression_data,
            "micro": micro_data,
            "concurrency": concurrency_data,
        },
        "summary": summary,
        "timestamp": datetime.datetime.now().isoformat(),
        "software": "lz4",
        "version": version_info.get("software_version", "1.10.0"),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"[AGGREGATE] Results saved to {args.output}")


if __name__ == '__main__':
    main()
