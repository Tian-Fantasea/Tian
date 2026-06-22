#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import random
import string
import re


def parse_benchmark_output(output):
    results = {}
    latency_percentiles = {}
    lines = output.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'(\d+)\s+requests/sec.*?(\d+\.\d+)\s*ms\s*avg', line)
        if match:
            results['throughput'] = int(match.group(1))
            results['avg_latency_ms'] = float(match.group(2))
            continue
        match = re.match(r'(\d+\.\d+)%\s*<=\s*([\d.]+)\s*(ms|usec)', line)
        if match:
            pct = float(match.group(1))
            val = float(match.group(2))
            unit = match.group(3)
            if unit == 'usec':
                val = val / 1000.0
            latency_percentiles[f'p{int(pct)}_latency_ms'] = val
        match = re.match(r'^(\S+):\s*(\d+\.?\d*)\s*$', line)
        if match:
            key = match.group(1).strip()
            val = match.group(2)
            try:
                results[key] = float(val)
            except ValueError:
                results[key] = val
    results['latency_percentiles'] = latency_percentiles
    return results


def run_micro_operation(redis_benchmark, port, op_name, test_cmd, num_requests=100000, num_clients=1, data_size=100, iterations=3):
    all_iters = []
    for iteration in range(iterations):
        cmd = [
            redis_benchmark,
            '-p', str(port),
            '-t', test_cmd,
            '-n', str(num_requests),
            '-c', str(num_clients),
            '-d', str(data_size),
            '--latency-dist',
        ]
        start_time = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        elapsed = time.time() - start_time
        output = proc.stdout.strip()
        parsed = parse_benchmark_output(output)
        parsed['iteration'] = iteration + 1
        parsed['operation'] = op_name
        parsed['elapsed_sec'] = round(elapsed, 3)
        parsed['num_clients'] = num_clients
        parsed['num_requests'] = num_requests
        parsed['data_size'] = data_size
        all_iters.append(parsed)
    avg_throughput = sum(r.get('throughput', 0) for r in all_iters) / len(all_iters)
    avg_latency = sum(r.get('avg_latency_ms', 0) for r in all_iters) / len(all_iters)
    p50_values = [r.get('latency_percentiles', {}).get('p50_latency_ms', 0) for r in all_iters]
    p99_values = [r.get('latency_percentiles', {}).get('p99_latency_ms', 0) for r in all_iters]
    avg_p50 = sum(p50_values) / len(p50_values) if p50_values else 0
    avg_p99 = sum(p99_values) / len(p99_values) if p99_values else 0
    return {
        'operation': op_name,
        'avg_throughput': round(avg_throughput, 1),
        'avg_latency_ms': round(avg_latency, 4),
        'p50_latency_ms': round(avg_p50, 4),
        'p99_latency_ms': round(avg_p99, 4),
        'iterations': all_iters,
    }


def run_latency_distribution(redis_benchmark, port, test_cmd, num_requests=100000, data_size=100):
    cmd = [
        redis_benchmark,
        '-p', str(port),
        '-t', test_cmd,
        '-n', str(num_requests),
        '-c', '1',
        '-d', str(data_size),
        '--latency-dist',
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    output = proc.stdout.strip()
    percentiles = {}
    percentile_matches = re.findall(r'(\d+\.\d+)%\s*<=\s*([\d.]+)\s*(ms|usec)', output)
    for match in percentile_matches:
        pct = float(match[0])
        val = float(match[1])
        unit = match[2]
        if unit == 'usec':
            val = val / 1000.0
        percentiles[f'p{int(pct)}'] = round(val, 4)
    throughput_match = re.search(r'(\d+)\s+requests/sec', output)
    throughput = int(throughput_match.group(1)) if throughput_match else 0
    avg_match = re.search(r'(\d+\.\d+)\s*ms\s*avg', output)
    avg_latency = float(avg_match.group(1)) if avg_match else 0
    return {
        'test': test_cmd,
        'throughput': throughput,
        'avg_latency_ms': avg_latency,
        'percentile_distribution': percentiles,
    }


def run_concurrency_stress(redis_benchmark, port, num_requests=100000, data_size=100, iterations=3):
    concurrency_levels = [1, 5, 10, 20, 50, 100, 200]
    stress_results = []
    for clients in concurrency_levels:
        for iteration in range(iterations):
            cmd = [
                redis_benchmark,
                '-p', str(port),
                '-t', 'set,get',
                '-n', str(num_requests),
                '-c', str(clients),
                '-d', str(data_size),
                '-q',
            ]
            start_time = time.time()
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            elapsed = time.time() - start_time
            output = proc.stdout.strip()
            parsed = parse_benchmark_output(output)
            parsed['concurrency'] = clients
            parsed['iteration'] = iteration + 1
            parsed['elapsed_sec'] = round(elapsed, 3)
            if 'throughput' not in parsed:
                parsed['throughput'] = num_requests / elapsed if elapsed > 0 else 0
            parsed['avg_latency_ms'] = parsed.get('avg_latency_ms', elapsed * 1000 / num_requests if num_requests > 0 else 0)
            stress_results.append(parsed)
    return stress_results


def main():
    parser = argparse.ArgumentParser(description='Micro benchmark + stress test for Redis on ARM64')
    parser.add_argument('--redis-home', required=True, help='Redis installation directory')
    parser.add_argument('--port', type=int, default=6380, help='Redis port')
    parser.add_argument('--results-dir', required=True, help='Results output directory')
    parser.add_argument('--iterations', type=int, default=3, help='Number of iterations')
    parser.add_argument('--data-size', type=int, default=1000000, help='Number of data records')
    parser.add_argument('--stress-only', action='store_true', help='Run only stress test (Phase 3d)')
    args = parser.parse_args()

    redis_benchmark = os.path.join(args.redis_home, 'src', 'redis-benchmark')
    redis_cli = os.path.join(args.redis_home, 'src', 'redis-cli')

    if args.stress_only:
        print("[STRESS] Starting concurrency scaling stress test...")
        stress_results = run_concurrency_stress(
            redis_benchmark, args.port,
            num_requests=1000000,
            data_size=100,
            iterations=args.iterations
        )

        stress_summary = {}
        for r in stress_results:
            c = r.get('concurrency', 0)
            tp = r.get('throughput', 0)
            if c not in stress_summary:
                stress_summary[c] = {'throughputs': [], 'latencies': []}
            stress_summary[c]['throughputs'].append(tp)
            stress_summary[c]['latencies'].append(r.get('avg_latency_ms', 0))

        avg_by_concurrency = {}
        for c, data in stress_summary.items():
            avg_by_concurrency[c] = {
                'avg_throughput': round(sum(data['throughputs']) / len(data['throughputs']), 1),
                'avg_latency_ms': round(sum(data['latencies']) / len(data['latencies']), 4),
            }

        result_json = {
            'benchmark': 'stress',
            'description': 'Concurrency scaling stress test: measuring throughput and latency as client count increases from 1 to 200',
            'reference': 'redis-benchmark with varying client counts',
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'performance_metrics': {
                'throughput_scaling': {
                    'unit': 'ops_per_sec',
                    'description': 'Throughput at each concurrency level'
                },
                'latency_at_concurrency': {
                    'unit': 'ms',
                    'description': 'Average latency at each concurrency level'
                },
            },
            'dataset_info': {
                'name': 'stress_test',
                'size': '1M operations per test',
                'source': 'redis-benchmark synthetic'
            },
            'results': stress_results,
            'summary_by_concurrency': avg_by_concurrency,
        }

        output_file = os.path.join(args.results_dir, 'benchmark_stress.json')
        with open(output_file, 'w') as f:
            json.dump(result_json, f, indent=2)
        print(f"[STRESS] Results written to {output_file}")
        print("[STRESS] Stress test complete.")
        return

    print("[MICRO] Starting micro benchmarks for Redis on ARM64")

    micro_operations = [
        ('GET', 'get', 100),
        ('SET', 'set', 100),
        ('PING', 'ping', 0),
        ('MSET_10', 'mset', 100),
        ('MGET_10', 'mget', 100),
        ('HSET', 'hset', 100),
        ('HGET', 'hget', 100),
        ('HGETALL', 'hgetall', 100),
        ('LPUSH', 'lpush', 100),
        ('LRANGE_100', 'lrange', 100),
        ('SADD', 'sadd', 100),
        ('SPOP', 'spop', 100),
        ('ZADD', 'zadd', 100),
        ('ZRANGE_100', 'zrange', 100),
        ('INCR', 'incr', 0),
        ('APPEND', 'append', 100),
    ]

    micro_results = []
    for op_name, test_cmd, data_size in micro_operations:
        print(f"[MICRO] Running {op_name} ({args.iterations} iterations)...")
        result = run_micro_operation(
            redis_benchmark, args.port,
            op_name, test_cmd,
            num_requests=100000,
            num_clients=1,
            data_size=data_size,
            iterations=args.iterations
        )
        micro_results.append(result)
        print(f"[MICRO] {op_name}: throughput={result['avg_throughput']} ops/sec, p99={result['p99_latency_ms']} ms")

    latency_dist_results = []
    for op_name, test_cmd, data_size in [('GET', 'get', 100), ('SET', 'set', 100), ('PING', 'ping', 0)]:
        print(f"[MICRO] Running latency distribution for {op_name}...")
        dist = run_latency_distribution(redis_benchmark, args.port, test_cmd, num_requests=100000, data_size=data_size)
        latency_dist_results.append(dist)

    print("[MICRO] Running concurrency stress test...")
    stress_results = run_concurrency_stress(
        redis_benchmark, args.port,
        num_requests=1000000,
        data_size=100,
        iterations=args.iterations
    )

    result_json = {
        'benchmark': 'micro',
        'description': 'Micro benchmarks: individual command latency distributions, per-command throughput, and latency percentile analysis on ARM64',
        'reference': 'redis-benchmark built-in tool + custom latency analysis',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'performance_metrics': {
            'avg_throughput': {
                'unit': 'ops_per_sec',
                'description': 'Average throughput per operation'
            },
            'avg_latency_ms': {
                'unit': 'ms',
                'description': 'Average latency per operation'
            },
            'p50_latency_ms': {
                'unit': 'ms',
                'description': '50th percentile latency'
            },
            'p99_latency_ms': {
                'unit': 'ms',
                'description': '99th percentile latency'
            },
            'GET': {
                'unit': 'ms',
                'description': 'GET operation latency metrics'
            },
        },
        'dataset_info': {
            'name': 'micro_benchmark_synthetic',
            'size': f'{args.data_size} keys',
            'source': 'redis-benchmark with custom analysis'
        },
        'results': micro_results,
        'latency_distribution': latency_dist_results,
        'stress_test': stress_results,
        'GET': micro_results[0] if micro_results else {},
    }

    output_file = os.path.join(args.results_dir, 'micro_benchmark.json')
    with open(output_file, 'w') as f:
        json.dump(result_json, f, indent=2)
    print(f"[MICRO] Results written to {output_file}")

    subprocess.run([redis_cli, '-p', str(args.port), 'FLUSHDB'], capture_output=True, timeout=30)
    print("[MICRO] Micro benchmarks complete.")


if __name__ == '__main__':
    main()