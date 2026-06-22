#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description="Generate text summary of benchmark results")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    all_results_path = os.path.join(args.results_dir, "all_results.json")
    if not os.path.exists(all_results_path):
        print("[SUMMARY] all_results.json not found")
        return

    with open(all_results_path, "r") as f:
        all_data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("RocksDB ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
    lines.append("")

    vi = all_data.get("version_info.json", {})
    if vi:
        lines.append("--- Environment ---")
        lines.append(f"Architecture:          {vi.get('architecture', 'N/A')}")
        lines.append(f"OS:                    {vi.get('os', 'N/A')}")
        lines.append(f"Kernel:                {vi.get('kernel', 'N/A')}")
        lines.append(f"CPU:                   {vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)")
        lines.append(f"Memory:                {vi.get('total_memory_mb', 'N/A')} MB")
        lines.append(f"RocksDB Version:       {vi.get('rocksdb_version', 'N/A')}")
        lines.append(f"ARM64 CRC32C:          {vi.get('arm64_crc32c_source_exists', vi.get('arm64_crc_detected', 'N/A'))}")
        lines.append(f"db_bench:              {vi.get('db_bench_installed', 'N/A')}")
        lines.append(f"Static Lib:            {vi.get('static_lib_exists', 'N/A')}")
        lines.append("")

    ycsb = all_data.get("benchmark_ycsb.json", {})
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

    dbbench = all_data.get("benchmark_dbbench.json", {})
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

    micro = all_data.get("micro_benchmark.json", {})
    if micro:
        lines.append("--- Micro Benchmarks (Phase 3c) ---")
        lines.append(f"Reference: {micro.get('reference', 'N/A')}")
        results = micro.get("results", {})
        for op_category, op_data in results.items():
            lines.append(f"  {op_category}:")
            for op_name, op_info in op_data.items():
                lines.append(f"    {op_name}: {op_info.get('avg_ops_sec', 'N/A')} ops/s, Lat={op_info.get('avg_latency_ms', 'N/A')} ms")
            lines.append("")

    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_text = "\n".join(lines)
    output_path = os.path.join(args.results_dir, "benchmark_summary.txt")
    with open(output_path, "w") as f:
        f.write(summary_text)

    print(summary_text)
    print(f"[SUMMARY] Saved to {output_path}")


if __name__ == "__main__":
    main()