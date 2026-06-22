#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import re


def parse_redis_benchmark_output(output):
    results = {}
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
        match = re.match(r'^(\S+):\s*(\d+\.?\d*)\s*$', line)
        if match:
            key = match.group(1).strip()
            val = match.group(2)
            try:
                results[key] = float(val)
            except ValueError:
                results[key] = val
    return results


def run_benchmark_test(redis_benchmark, port, test_name, num_requests=1000000, num_clients=50, keyspace=1000000, data_size=100):
    cmd = [
        redis_benchmark,
        '-p', str(port),
        '-t', test_name,
        '-n', str(num_requests),
        '-c', str(num_clients),
        '-d', str(data_size),
        '-q',
    ]
    start_time = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - start_time
    output = proc.stdout.strip()
    parsed = parse_redis_benchmark_output(output)
    if 'throughput' not in parsed:
        if elapsed > 0 and num_requests > 0:
            parsed['throughput'] = num_requests / elapsed
        else:
            parsed['throughput'] = 0
    parsed['elapsed_sec'] = round(elapsed, 3)
    parsed['test_name'] = test_name
    parsed['num_clients'] = num_clients
    parsed['num_requests'] = num_requests
    parsed['data_size'] = data_size
    return parsed


def run_latency_test(redis_benchmark, port, test_name, num_requests=100000, num_clients=1, data_size=100):
    cmd = [
        redis_benchmark,
        '-p', str(port),
        '-t', test_name,
        '-n', str(num_requests),
        '-c', str(num_clients),
        '-d', str(data_size),
        '--latency-dist',
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    output = proc.stdout.strip()
    latency_data = {}
    percentile_matches = re.findall(r'(\d+\.\d+)%<=([\d+\.\d]+)\s*(ms|usec)', output)
    for match in percentile_matches:
        percentile = float(match[0])
        value = float(match[1])
        unit = match[2]
        if unit == 'usec':
            value = value / 1000.0
        latency_data[f'p{int(percentile)}_latency_ms'] = value
    latency_data['test_name'] = test_name
    latency_data['num_clients'] = num_clients
    latency_data['raw_output'] = output.split('\n')[-20:]
    return latency_data


def main():
    parser = argparse.ArgumentParser(description='Throughput benchmark for Redis on ARM64')
    parser.add_argument('--redis-home', required=True, help='Redis installation directory')
    parser.add_argument('--port', type=int, default=6380, help='Redis port')
    parser.add_argument('--results-dir', required=True, help='Results output directory')
    parser.add_argument('--iterations', type=int, default=3, help='Number of iterations')
    args = parser.parse_args()

    redis_benchmark = os.path.join(args.redis_home, 'src', 'redis-benchmark')
    redis_cli = os.path.join(args.redis_home, 'src', 'redis-cli')

    print("[THROUGHPUT] Starting throughput benchmark for Redis on ARM64")

    tests = [
        {'name': 'GET', 'test': 'get', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'SET', 'test': 'set', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'MGET_10', 'test': 'mget', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'HSET', 'test': 'hset', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'HGETALL', 'test': 'hgetall', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'LPUSH', 'test': 'lpush', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'LRANGE_100', 'test': 'lrange', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'SADD', 'test': 'sadd', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'ZADD', 'test': 'zadd', 'keyspace': 1000000, 'data_size': 100},
        {'name': 'PING', 'test': 'ping', 'keyspace': 1, 'data_size': 0},
    ]

    client_levels = [1, 10, 50, 100]

    all_results = []
    for test_info in tests:
        for clients in client_levels:
            for iteration in range(args.iterations):
                print(f"[THROUGHPUT] Running {test_info['name']} with {clients} clients (iteration {iteration+1})...")
                result = run_benchmark_test(
                    redis_benchmark, args.port,
                    test_info['test'],
                    num_requests=1000000,
                    num_clients=clients,
                    data_size=test_info['data_size']
                )
                result['iteration'] = iteration + 1
                result['operation'] = test_info['name']
                all_results.append(result)

    throughput_by_op = {}
    for r in all_results:
        op = r.get('operation', r.get('test_name', 'unknown'))
        tp = r.get('throughput', 0)
        if op not in throughput_by_op:
            throughput_by_op[op] = []
        throughput_by_op[op].append(tp)

    summary = {}
    for op, values in throughput_by_op.items():
        avg = sum(values) / len(values) if values else 0
        max_val = max(values) if values else 0
        min_val = min(values) if values else 0
        summary[op] = {
            'avg_throughput': round(avg, 1),
            'max_throughput': round(max_val, 1),
            'min_throughput': round(min_val, 1),
            'iterations': len(values),
        }

    get_throughput = summary.get('GET', {}).get('avg_throughput', 0)
    set_throughput = summary.get('SET', {}).get('avg_throughput', 0)

    result_json = {
        'benchmark': 'throughput',
        'description': 'Redis throughput at various client concurrency levels, measuring ops/sec for common operations',
        'reference': 'redis-benchmark (built-in)',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'performance_metrics': {
            'throughput_get': {
                'unit': 'ops_per_sec',
                'description': 'Average GET throughput across all client levels'
            },
            'throughput_set': {
                'unit': 'ops_per_sec',
                'description': 'Average SET throughput across all client levels'
            },
            'avg_latency_ms': {
                'unit': 'ms',
                'description': 'Average request latency'
            },
        },
        'dataset_info': {
            'name': 'redis_benchmark_synthetic',
            'size': '1M keys, 100 bytes per value',
            'source': 'Generated by redis-benchmark tool'
        },
        'results': all_results,
        'summary': summary,
        'throughput_get': get_throughput,
        'throughput_set': set_throughput,
    }

    output_file = os.path.join(args.results_dir, 'benchmark_throughput.json')
    with open(output_file, 'w') as f:
        json.dump(result_json, f, indent=2)
    print(f"[THROUGHPUT] Results written to {output_file}")
    print(f"[THROUGHPUT] GET avg throughput: {get_throughput:.1f} ops/sec")
    print(f"[THROUGHPUT] SET avg throughput: {set_throughput:.1f} ops/sec")

    subprocess.run([redis_cli, '-p', str(args.port), 'FLUSHDB'], capture_output=True, timeout=30)
    print("[THROUGHPUT] Throughput benchmark complete.")


if __name__ == '__main__':
    main()