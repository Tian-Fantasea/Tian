#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description='Generate text summary of folly benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.txt file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print('[SUMMARY] results.json not found')
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get('environment', {})
    cont = data.get('benchmarks', {}).get('containers', {})
    conc = data.get('benchmarks', {}).get('concurrency', {})
    codec = data.get('benchmarks', {}).get('codec', {})
    scaling = data.get('benchmarks', {}).get('scaling', {})
    summary = data.get('summary', {})

    lines = []
    lines.append('=' * 70)
    lines.append('folly ARM64 Performance Benchmark Summary')
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
        lines.append(f'folly Version:         {env.get("folly_version", env.get("software_version", "N/A"))}')
        lines.append(f'Compiler:              {env.get("compiler_version", "N/A")}')
        lines.append(f'CMake:                 {env.get("cmake_version", "N/A")}')
        lines.append(f'Install Method:        {env.get("install_method", "N/A")}')
        lines.append(f'Category:              {env.get("category", "N/A")}')
        lines.append(f'Language:              {env.get("language", "N/A")}')
        lines.append('')

    if cont:
        lines.append('--- Container Throughput (Phase 3a) ---')
        lines.append(f'Reference: {cont.get("reference", "N/A")}')
        lines.append('')
        for r in cont.get("results", []):
            lines.append(f'  {r.get("operation", "N/A")} ({r.get("container_type", "N/A")}):')
            lines.append(f'    ops/sec:     {r.get("ops_per_sec", "N/A")}')
            lines.append(f'    avg latency: {r.get("avg_latency_ms", "N/A")} ms')
        lines.append('')

    if conc:
        lines.append('--- Concurrency Latency (Phase 3b) ---')
        lines.append(f'Reference: {conc.get("reference", "N/A")}')
        lines.append('')
        for r in conc.get("results", []):
            lines.append(f'  {r.get("operation", "N/A")}:')
            lines.append(f'    Avg:  {r.get("avg_latency_ms", "N/A")} ms')
            lines.append(f'    P50:  {r.get("p50_latency_ms", "N/A")} ms')
            lines.append(f'    P90:  {r.get("p90_latency_ms", "N/A")} ms')
            lines.append(f'    P99:  {r.get("p99_latency_ms", "N/A")} ms')
            lines.append(f'    Min:  {r.get("min_latency_ms", "N/A")} ms')
            lines.append(f'    Max:  {r.get("max_latency_ms", "N/A")} ms')
        lines.append('')

    if codec:
        lines.append('--- Codec Micro Benchmarks (Phase 3c) ---')
        lines.append(f'Reference: {codec.get("reference", "N/A")}')
        lines.append('')
        for r in codec.get("results", []):
            lines.append(f'  {r.get("operation", "N/A")} ({r.get("category", "N/A")}):')
            lines.append(f'    ops/sec:     {r.get("ops_per_sec", "N/A")}')
            lines.append(f'    avg latency: {r.get("avg_latency_ms", "N/A")} ms')
        lines.append('')

    if scaling:
        lines.append('--- Concurrency Scaling (Phase 3d) ---')
        lines.append(f'Reference: {scaling.get("reference", "N/A")}')
        lines.append('')
        for r in scaling.get("results", []):
            lines.append(f'  {r.get("mode", "N/A")} threads={r.get("thread_count", "N/A")}:')
            lines.append(f'    Total ops/sec: {r.get("total_ops_per_sec", "N/A")}')
            lines.append(f'    Avg latency:   {r.get("avg_latency_ms", "N/A")} ms')
        lines.append('')

    if summary:
        lines.append('--- Overall Summary ---')
        if 'avg_f14_ops_per_sec' in summary:
            lines.append(f'  Avg F14FastMap ops: {summary["avg_f14_ops_per_sec"]} ops/sec')
        if 'avg_fbstring_ops_per_sec' in summary:
            lines.append(f'  Avg fbstring ops:   {summary["avg_fbstring_ops_per_sec"]} ops/sec')
        if 'fbstring_vs_std_ratio' in summary:
            lines.append(f'  fbstring vs std::string: {summary["fbstring_vs_std_ratio"]}x')
        if 'max_avg_concurrency_latency_ms' in summary:
            lines.append(f'  Max avg concurrency latency: {summary["max_avg_concurrency_latency_ms"]} ms')
        if 'max_p99_concurrency_latency_ms' in summary:
            lines.append(f'  Max P99 concurrency latency: {summary["max_p99_concurrency_latency_ms"]} ms')
        if 'avg_json_parse_ops' in summary:
            lines.append(f'  Avg JSON parse ops: {summary["avg_json_parse_ops"]} ops/sec')
        if 'avg_iobuf_ops' in summary:
            lines.append(f'  Avg IOBuf ops:      {summary["avg_iobuf_ops"]} ops/sec')
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
