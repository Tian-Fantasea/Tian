#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description='Generate text summary of lz4 benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.txt file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print('[SUMMARY] results.json not found')
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get('environment', {})
    comp = data.get('benchmarks', {}).get('compression', {})
    decomp = data.get('benchmarks', {}).get('decompression', {})
    micro = data.get('benchmarks', {}).get('micro', {})
    conc = data.get('benchmarks', {}).get('concurrency', {})
    summary = data.get('summary', {})

    lines = []
    lines.append('=' * 70)
    lines.append('lz4 ARM64 Performance Benchmark Summary')
    lines.append('=' * 70)
    lines.append(f'Generated: {datetime.datetime.now().isoformat()}')
    lines.append('')

    if env:
        lines.append('--- Environment ---')
        lines.append(f'Architecture:          {env.get("architecture", "N/A")}')
        lines.append(f'OS:                    {env.get("os", "N/A")}')
        lines.append(f'Kernel:                {env.get("kernel", "N/A")}')
        lines.append(f'CPU:                   {env.get("cpu_model", "N/A")} ({env.get("cores", "N/A")} cores)')
        lines.append(f'Memory:                {env.get("memory_mb", "N/A")} MB')
        lines.append(f'lz4 Version:           {env.get("lz4_version", env.get("software_version", "N/A"))}')
        lines.append(f'Python lz4:            {env.get("lz4_py_version", "N/A")}')
        lines.append(f'lz4 CLI:               {env.get("lz4_cli_version", "N/A")}')
        lines.append(f'Install Method:        {env.get("install_method", "N/A")}')
        lines.append(f'Category:              {env.get("category", "N/A")}')
        lines.append(f'Language:              {env.get("language", "N/A")}')
        lines.append('')

    if comp:
        lines.append('--- Compression Throughput (Phase 3a) ---')
        lines.append(f'Reference: {comp.get("reference", "N/A")}')
        lines.append('')
        for r in comp.get("results", []):
            if r.get("data_type") == "text" and r.get("compression_level") in [1, 6, 12]:
                lines.append(f'  {r.get("data_size", "N/A")} level={r.get("compression_level", "N/A")}:')
                lines.append(f'    Throughput:   {r.get("compression_throughput_mb_per_sec", "N/A")} MB/s')
                lines.append(f'    Ratio:        {r.get("compression_ratio", "N/A")}x')
                lines.append(f'    Latency:      {r.get("avg_latency_ms", "N/A")} ms')
        lines.append('')

    if decomp:
        lines.append('--- Decompression Throughput (Phase 3b) ---')
        lines.append(f'Reference: {decomp.get("reference", "N/A")}')
        lines.append('')
        for r in decomp.get("results", []):
            lines.append(f'  {r.get("data_name", "N/A")}:')
            lines.append(f'    Throughput: {r.get("decompression_throughput_mb_per_sec", "N/A")} MB/s')
            lines.append(f'    Avg:  {r.get("avg_latency_ms", "N/A")} ms')
            lines.append(f'    P50:  {r.get("p50_latency_ms", "N/A")} ms')
            lines.append(f'    P99:  {r.get("p99_latency_ms", "N/A")} ms')
        lines.append('')

    if micro:
        lines.append('--- Micro Benchmarks (Phase 3c) ---')
        lines.append(f'Reference: {micro.get("reference", "N/A")}')
        lines.append('')
        for r in micro.get("results", []):
            if r.get("block_size_name") == "64KB":
                lines.append(f'  {r.get("operation", "N/A")} (64KB):')
                lines.append(f'    ops/sec:     {r.get("ops_per_sec", "N/A")}')
                lines.append(f'    latency:     {r.get("avg_latency_ms", "N/A")} ms')
                lines.append(f'    throughput:  {r.get("throughput_mb_per_sec", "N/A")} MB/s')
        lines.append('')

    if conc:
        lines.append('--- Concurrency Scaling (Phase 3d) ---')
        lines.append(f'Reference: {conc.get("reference", "N/A")}')
        lines.append('')
        for r in conc.get("results", []):
            lines.append(f'  {r.get("mode", "N/A")} threads={r.get("thread_count", "N/A")}:')
            lines.append(f'    Total throughput: {r.get("total_throughput_mb_per_sec", "N/A")} MB/s')
            lines.append(f'    Total ops/sec:   {r.get("total_ops_per_sec", "N/A")}')
            lines.append(f'    Avg latency:     {r.get("avg_latency_ms", "N/A")} ms')
        lines.append('')

    if summary:
        lines.append('--- Overall Summary ---')
        if 'avg_compression_throughput_mb' in summary:
            lines.append(f'  Avg compression throughput:  {summary["avg_compression_throughput_mb"]} MB/s')
        if 'avg_compression_ratio' in summary:
            lines.append(f'  Avg compression ratio:       {summary["avg_compression_ratio"]}x')
        if 'avg_decompression_throughput_mb' in summary:
            lines.append(f'  Avg decompression throughput: {summary["avg_decompression_throughput_mb"]} MB/s')
        if 'decompress_vs_compress_ratio' in summary:
            lines.append(f'  Decompress/Compress ratio:    {summary["decompress_vs_compress_ratio"]}x')
        if 'max_avg_decompression_latency_ms' in summary:
            lines.append(f'  Max avg decompression latency: {summary["max_avg_decompression_latency_ms"]} ms')
        if 'max_p99_decompression_latency_ms' in summary:
            lines.append(f'  Max P99 decompression latency: {summary["max_p99_decompression_latency_ms"]} ms')
        if 'avg_compress_ops_per_sec' in summary:
            lines.append(f'  Avg compress ops:             {summary["avg_compress_ops_per_sec"]} ops/sec')
        if 'avg_decompress_ops_per_sec' in summary:
            lines.append(f'  Avg decompress ops:           {summary["avg_decompress_ops_per_sec"]} ops/sec')
        if 'hc_vs_fast_ratio' in summary:
            lines.append(f'  HC vs Fast throughput ratio:  {summary["hc_vs_fast_ratio"]}x')
        if 'concurrency_scaling_ratio' in summary:
            lines.append(f'  Concurrency scaling (8t vs 1t): {summary["concurrency_scaling_ratio"]}x')

    lines.append('')
    lines.append('=' * 70)
    lines.append('End of Summary')
    lines.append('=' * 70)

    summary_text = '\n'.join(lines)
    with open(args.output, 'w') as f:
        f.write(summary_text)
    print(f'[SUMMARY] Saved to {args.output}')


if __name__ == '__main__':
    main()
