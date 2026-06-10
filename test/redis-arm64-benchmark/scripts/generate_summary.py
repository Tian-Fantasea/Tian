#!/usr/bin/env python3
import argparse
import json
import os
import time


def format_throughput(value, unit='ops/sec'):
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M {unit}"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K {unit}"
    else:
        return f"{value:.1f} {unit}"


def main():
    parser = argparse.ArgumentParser(description='Generate text summary from benchmark results')
    parser.add_argument('--results-dir', required=True, help='Results directory')
    args = parser.parse_args()

    results_dir = args.results_dir
    all_results_file = os.path.join(results_dir, 'all_results.json')

    if not os.path.exists(all_results_file):
        print("[SUMMARY] No aggregated results found. Run aggregate_results.py first.")
        return

    with open(all_results_file, 'r') as f:
        all_data = json.load(f)

    env = all_data.get('environment', {})
    benchmarks = all_data.get('benchmarks', {})
    summary = all_data.get('summary', {})

    lines = []
    lines.append("=" * 80)
    lines.append("Redis ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append("")
    lines.append("Environment Information:")
    lines.append(f"  Architecture:    {env.get('architecture', 'N/A')}")
    lines.append(f"  CPU:             {env.get('cpu_model', 'N/A')}")
    lines.append(f"  CPU Cores:       {env.get('cpu_cores', 'N/A')}")
    lines.append(f"  Memory:          {env.get('memory_mb', 'N/A')} MB")
    lines.append(f"  OS:              {env.get('os', 'N/A')}")
    lines.append(f"  Kernel:          {env.get('kernel', 'N/A')}")
    lines.append(f"  Redis Version:   {env.get('software_version', 'N/A')}")
    lines.append(f"  Compiler:        {env.get('compiler_version', 'N/A')}")
    lines.append(f"  Benchmark Date:  {env.get('timestamp', 'N/A')}")
    lines.append("")

    for bench_name, bench_data in benchmarks.items():
        if 'error' in bench_data:
            lines.append(f"[ERROR] {bench_name}: {bench_data['error']}")
            continue
        lines.append("-" * 60)
        lines.append(f"Benchmark: {bench_name.upper()}")
        lines.append(f"Description: {bench_data.get('description', 'N/A')}")
        lines.append(f"Reference: {bench_data.get('reference', 'N/A')}")
        lines.append("")

        bench_summary = bench_data.get('summary', bench_data.get('summary_by_concurrency', {}))
        if isinstance(bench_summary, dict):
            for key, val in bench_summary.items():
                if isinstance(val, dict):
                    avg_tp = val.get('avg_throughput', val.get('avg_throughput_ops_per_sec', 0))
                    if isinstance(avg_tp, (int, float)):
                        lines.append(f"  {key}: throughput={format_throughput(avg_tp)}")
                    avg_lat = val.get('avg_latency_ms', 0)
                    if isinstance(avg_lat, (int, float)) and avg_lat > 0:
                        lines.append(f"  {key}: avg latency={avg_lat:.3f} ms")
                elif isinstance(val, (int, float)):
                    lines.append(f"  {key}: {val}")

        bench_results = bench_data.get('results', [])
        if isinstance(bench_results, list) and len(bench_results) > 0:
            lines.append(f"  Total iterations: {len(bench_results)}")
            throughputs = []
            for r in bench_results:
                tp = r.get('throughput', r.get('overall_throughput', r.get('avg_throughput', 0)))
                if isinstance(tp, (int, float)):
                    throughputs.append(tp)
            if throughputs:
                avg = sum(throughputs) / len(throughputs)
                lines.append(f"  Average throughput: {format_throughput(avg)}")
                lines.append(f"  Max throughput: {format_throughput(max(throughputs))}")
                lines.append(f"  Min throughput: {format_throughput(min(throughputs))}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("Overall Summary:")
    if 'max_throughput' in summary:
        mt = summary['max_throughput']
        lines.append(f"  Max throughput: {format_throughput(mt['value'])} ({mt['name']})")
    if 'min_throughput' in summary:
        mt = summary['min_throughput']
        lines.append(f"  Min throughput: {format_throughput(mt['value'])} ({mt['name']})")
    if 'avg_throughput' in summary:
        lines.append(f"  Avg throughput: {format_throughput(summary['avg_throughput'])}")
    if 'max_latency' in summary:
        ml = summary['max_latency']
        lines.append(f"  Max latency: {ml['value']:.3f} ms ({ml['name']})")
    if 'min_latency' in summary:
        ml = summary['min_latency']
        lines.append(f"  Min latency: {ml['value']:.3f} ms ({ml['name']})")
    if 'avg_latency' in summary:
        lines.append(f"  Avg latency: {summary['avg_latency']:.3f} ms")
    lines.append("")
    lines.append("=" * 80)
    lines.append(f"Report generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    lines.append("=" * 80)

    output_file = os.path.join(results_dir, 'benchmark_summary.txt')
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))
    print(f"[SUMMARY] Summary written to {output_file}")


if __name__ == '__main__':
    main()