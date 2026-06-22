#!/usr/bin/env python3
import argparse
import json
import os


def main():
    parser = argparse.ArgumentParser(description='Aggregate all benchmark JSON results')
    parser.add_argument('--results-dir', required=True, help='Results directory')
    parser.add_argument('--output', required=True, help='Output file path')
    args = parser.parse_args()

    results_dir = args.results_dir
    benchmark_files = {
        'ycsb': os.path.join(results_dir, 'benchmark_ycsb.json'),
        'throughput': os.path.join(results_dir, 'benchmark_throughput.json'),
        'micro': os.path.join(results_dir, 'micro_benchmark.json'),
        'stress': os.path.join(results_dir, 'benchmark_stress.json'),
    }

    version_file = os.path.join(results_dir, 'version_info.json')

    aggregated = {
        'benchmark_suite': 'redis_arm64_performance',
        'timestamp': None,
        'environment': None,
        'benchmarks': {},
        'summary': {},
    }

    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            aggregated['environment'] = json.load(f)
        aggregated['timestamp'] = aggregated['environment'].get('timestamp', '')

    all_throughputs = []
    all_latencies = []

    for bench_name, bench_file in benchmark_files.items():
        if os.path.exists(bench_file):
            try:
                with open(bench_file, 'r') as f:
                    data = json.load(f)
                aggregated['benchmarks'][bench_name] = data

                results = data.get('results', [])
                if isinstance(results, list):
                    for r in results:
                        tp = r.get('throughput', r.get('overall_throughput', r.get('avg_throughput', 0)))
                        if isinstance(tp, (int, float)) and tp > 0:
                            all_throughputs.append((bench_name, tp))
                        lat = r.get('avg_latency_ms', r.get('p99_latency_ms', r.get('p99_read_latency_ms', 0)))
                        if isinstance(lat, (int, float)) and lat > 0:
                            all_latencies.append((bench_name, lat))

                summary = data.get('summary', data.get('summary_by_concurrency', {}))
                if isinstance(summary, dict):
                    for key, val in summary.items():
                        if isinstance(val, dict):
                            avg_tp = val.get('avg_throughput', val.get('avg_throughput_ops_per_sec', 0))
                            if isinstance(avg_tp, (int, float)):
                                all_throughputs.append((f'{bench_name}.{key}', avg_tp))
            except (json.JSONDecodeError, Exception) as e:
                aggregated['benchmarks'][bench_name] = {'error': str(e)}

    if all_throughputs:
        max_tp = max(all_throughputs, key=lambda x: x[1])
        min_tp = min(all_throughputs, key=lambda x: x[1])
        avg_tp = sum(x[1] for x in all_throughputs) / len(all_throughputs)
        aggregated['summary']['max_throughput'] = {'name': max_tp[0], 'value': round(max_tp[1], 1), 'unit': 'ops/sec'}
        aggregated['summary']['min_throughput'] = {'name': min_tp[0], 'value': round(min_tp[1], 1), 'unit': 'ops/sec'}
        aggregated['summary']['avg_throughput'] = round(avg_tp, 1)

    if all_latencies:
        max_lat = max(all_latencies, key=lambda x: x[1])
        min_lat = min(all_latencies, key=lambda x: x[1])
        avg_lat = sum(x[1] for x in all_latencies) / len(all_latencies)
        aggregated['summary']['max_latency'] = {'name': max_lat[0], 'value': round(max_lat[1], 4), 'unit': 'ms'}
        aggregated['summary']['min_latency'] = {'name': min_lat[0], 'value': round(min_lat[1], 4), 'unit': 'ms'}
        aggregated['summary']['avg_latency'] = round(avg_lat, 4)

    with open(args.output, 'w') as f:
        json.dump(aggregated, f, indent=2)
    print(f"[AGGREGATE] Results aggregated to {args.output}")
    print(f"[AGGREGATE] Benchmarks included: {list(aggregated['benchmarks'].keys())}")


if __name__ == '__main__':
    main()
