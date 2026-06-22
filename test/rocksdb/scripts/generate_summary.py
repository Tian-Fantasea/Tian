#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description="Generate text summary of benchmark results")
    parser.add_argument("--input", required=True, help="Input results.json file")
    parser.add_argument("--output", required=True, help="Output results.txt file")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("[SUMMARY] results.json not found")
        return

    with open(args.input, "r") as f:
        all_data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("RocksDB ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
    lines.append("")

    env = all_data.get("environment", {})
    if env:
        lines.append("--- Environment ---")
        lines.append(f"Architecture:          {env.get('architecture', 'N/A')}")
        lines.append(f"OS:                    {env.get('os', 'N/A')}")
        lines.append(f"Kernel:                {env.get('kernel', 'N/A')}")
        lines.append(f"CPU:                   {env.get('cpu_model', 'N/A')} ({env.get('cpu_cores', 'N/A')} cores)")
        lines.append(f"Memory:                {env.get('total_memory_mb', 'N/A')} MB")
        lines.append(f"RocksDB Version:       {env.get('rocksdb_version', 'N/A')}")
        lines.append(f"ARM64 CRC32C:          {env.get('arm64_crc32c_detected', 'N/A')}")
        lines.append(f"db_bench:              {env.get('db_bench_path', 'N/A')}")
        lines.append(f"Static Lib:            {env.get('static_lib_exists', 'N/A')}")
        lines.append("")

    benchmarks = all_data.get("benchmarks", {})

    ycsb = benchmarks.get("ycsb", {})
    if ycsb:
        lines.append("--- YCSB Workloads (Phase 3a) ---")
        lines.append(f"Reference: {ycsb.get('reference', 'N/A')}")
        params = ycsb.get("parameters", {})
        lines.append(f"Keys: {params.get('num_keys', 'N/A')}, Value: {params.get('value_size', 'N/A')}B, Threads: {params.get('threads', 'N/A')}")
        lines.append("")
        results = ycsb.get("results", {})
        for wl_name, wl_data in results.items():
            lines.append(f"  {wl_name}: {wl_data.get('description', '')}")
            lines.append(f"    Load TPS:    {wl_data.get('load_throughput_ops_sec', 'N/A')} ops/sec")
            lines.append(f"    Run TPS:     {wl_data.get('run_throughput_ops_sec', 'N/A')} ops/sec")
            lines.append(f"    Run LatAvg:  {wl_data.get('run_latency_avg_ms', 'N/A')} ms")
            lines.append("")

    dbbench = benchmarks.get("dbbench", {})
    if dbbench:
        lines.append("--- db_bench Advanced Benchmarks (Phase 3b) ---")
        lines.append(f"Reference: {dbbench.get('reference', 'N/A')}")
        results = dbbench.get("results", {})

        comp = results.get("compaction_styles", {})
        if comp:
            lines.append("  Compaction Styles:")
            for style, data in comp.items():
                lines.append(f"    {style}: Fill={data.get('fillrandom_avg_ops_sec', 'N/A')} ops/s, Overwrite={data.get('overwrite_avg_ops_sec', 'N/A')} ops/s")
            lines.append("")

        compress = results.get("compression_algorithms", {})
        if compress:
            lines.append("  Compression Algorithms:")
            for algo, data in compress.items():
                lines.append(f"    {algo}: Fill={data.get('fillseq_avg_ops_sec', 'N/A')} ops/s, Read={data.get('readrandom_avg_ops_sec', 'N/A')} ops/s, DB={data.get('avg_db_size_mb', 'N/A')} MB")
            lines.append("")

        filters = results.get("bloom_ribbon_filters", {})
        if filters:
            lines.append("  Bloom/Ribbon Filters (readrandom):")
            for filt, data in filters.items():
                lines.append(f"    {filt}: {data.get('avg_read_ops_sec', 'N/A')} ops/s, Lat={data.get('avg_read_lat_ms', 'N/A')} ms")
            lines.append("")

        conc = results.get("concurrency_scaling", {})
        if conc:
            lines.append("  Concurrency Scaling (readrandom):")
            for label, data in conc.items():
                lines.append(f"    {data.get('threads', 'N/A')} threads: Read={data.get('readrandom_ops_sec', 'N/A')} ops/s, Lat={data.get('readrandom_lat_ms', 'N/A')} ms")
            lines.append("")

    micro = benchmarks.get("micro", {})
    if micro:
        lines.append("--- Micro Benchmarks (Phase 3c) ---")
        lines.append(f"Reference: {micro.get('reference', 'N/A')}")
        results = micro.get("results", {})
        for op_category, op_data in results.items():
            lines.append(f"  {op_category}:")
            if isinstance(op_data, dict):
                for op_name, op_info in op_data.items():
                    lines.append(f"    {op_name}: {op_info.get('avg_ops_sec', 'N/A')} ops/s, Lat={op_info.get('avg_latency_ms', 'N/A')} ms")
            lines.append("")

    summary = all_data.get("summary", {})
    if summary:
        lines.append("--- Overall Summary ---")
        if "max_throughput" in summary:
            mt = summary["max_throughput"]
            lines.append(f"  Max throughput: {mt['value']} ops/sec ({mt['name']})")
        if "avg_throughput" in summary:
            lines.append(f"  Avg throughput: {summary['avg_throughput']} ops/sec")
        if "max_latency" in summary:
            ml = summary["max_latency"]
            lines.append(f"  Max latency: {ml['value']} ms ({ml['name']})")
        if "avg_latency" in summary:
            lines.append(f"  Avg latency: {summary['avg_latency']} ms")

    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_text = "\n".join(lines)
    with open(args.output, "w") as f:
        f.write(summary_text)
    print(f"[SUMMARY] Saved to {args.output}")


if __name__ == "__main__":
    main()
