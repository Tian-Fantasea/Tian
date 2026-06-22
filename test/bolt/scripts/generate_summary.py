#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description='Generate text summary of bbolt benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.txt file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print('[SUMMARY] results.json not found')
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get('environment', {})
    ycsb = data.get('benchmarks', {}).get('ycsb', {})
    throughput = data.get('benchmarks', {}).get('throughput', {})
    micro = data.get('benchmarks', {}).get('micro', {})
    concurrency = data.get('benchmarks', {}).get('concurrency', {})
    summary = data.get('summary', {})

    lines = []
    lines.append('=' * 70)
    lines.append('bbolt ARM64 Performance Benchmark Summary')
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
        lines.append(f'bbolt Version:         {env.get("bbolt_version", env.get("software_version", "N/A"))}')
        lines.append(f'Go Version:            {env.get("go_version", env.get("runtime_version", "N/A"))}')
        lines.append(f'Install Method:        {env.get("install_method", "N/A")}')
        lines.append('')

    if ycsb:
        lines.append('--- YCSB Benchmark (Phase 3a) ---')
        lines.append(f'Reference: {ycsb.get("reference", "N/A")}')
        results = ycsb.get('results', [])
        for r in results:
            if isinstance(r, dict):
                wl = r.get('workload', 'N/A')
                ops = r.get('ops_per_sec', r.get('OpsPerSec', 0))
                lat = r.get('avg_latency_ms', r.get('AvgLatencyMs', 0))
                lines.append(f'  {wl}: ops/sec={ops:.1f}, avg_latency={lat:.2f}ms')
        lines.append('')

    if throughput:
        lines.append('--- Throughput Scaling (Phase 3b) ---')
        lines.append(f'Reference: {throughput.get("reference", "N/A")}')
        results = throughput.get('results', [])
        for r in results:
            if isinstance(r, dict):
                kc = r.get('key_count', 'N/A')
                w_ops = r.get('write_ops_per_sec', r.get('WriteOpsSec', 0))
                lines.append(f'  keys={kc}: write_ops={w_ops:.1f} ops/sec')
        lines.append('')

    if micro:
        lines.append('--- Micro Benchmarks (Phase 3c) ---')
        lines.append(f'Reference: {micro.get("reference", "N/A")}')
        results = micro.get('results', [])
        for r in results:
            if isinstance(r, dict):
                op = r.get('operation', 'N/A')
                ops = r.get('ops_per_sec', r.get('OpsPerSec', 0))
                lat = r.get('avg_latency_ms', r.get('AvgLatencyMs', 0))
                lines.append(f'  {op}: ops/sec={ops:.1f}, avg_latency={lat:.2f}ms')
        lines.append('')

    if concurrency:
        lines.append('--- Concurrency Scaling (Phase 3d) ---')
        lines.append(f'Reference: {concurrency.get("reference", "N/A")}')
        results = concurrency.get('results', [])
        for r in results:
            if isinstance(r, dict):
                gr = r.get('goroutines', 'N/A')
                mode = r.get('mode', 'N/A')
                ops = r.get('ops_per_sec', r.get('OpsPerSec', 0))
                lat = r.get('avg_latency_ms', r.get('AvgLatencyMs', 0))
                lines.append(f'  {mode} goroutines={gr}: ops/sec={ops:.1f}, avg_latency={lat:.2f}ms')
        lines.append('')

    if summary:
        lines.append('--- Overall Summary ---')
        for key, val in summary.items():
            lines.append(f'  {key}: {val}')

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
