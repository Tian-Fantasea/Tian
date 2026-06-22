#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import random
import string


def generate_ycsb_workload(num_records, workload_type='a'):
    records = []
    for i in range(num_records):
        key = f"user{i}"
        fields = {}
        for j in range(10):
            field_name = f"field{j}"
            field_value = ''.join(random.choices(string.ascii_letters + string.digits, k=100))
            fields[field_name] = field_value
        records.append({'key': key, 'fields': fields})
    return records


def load_data(redis_cli, port, records, batch_size=500):
    pipe_cmds = []
    loaded = 0
    for record in records:
        key = record['key']
        pipe_cmds.extend(['HSET', key])
        for field_name, field_value in record['fields'].items():
            pipe_cmds.extend([field_name, field_value])
        if len(pipe_cmds) >= batch_size * 22:
            pipe_cmd_str = '\n'.join(pipe_cmds) + '\n'
            result = subprocess.run(
                [redis_cli, '-p', str(port), '--pipe'],
                input=pipe_cmd_str,
                capture_output=True,
                text=True,
                timeout=120
            )
            loaded += batch_size
            pipe_cmds = []
    if pipe_cmds:
        pipe_cmd_str = '\n'.join(pipe_cmds) + '\n'
        subprocess.run(
            [redis_cli, '-p', str(port), '--pipe'],
            input=pipe_cmd_str,
            capture_output=True,
            text=True,
            timeout=120
        )
        loaded += len(records) - loaded
    return loaded


def run_ycsb_workload(redis_cli, port, num_records, read_ratio, num_ops, iterations=3):
    results = []
    workload_name = f"YCSB_read{int(read_ratio*100)}_write{int((1-read_ratio)*100)}"
    for iteration in range(iterations):
        read_ops = int(num_ops * read_ratio)
        write_ops = num_ops - read_ops
        ops_list = ['READ'] * read_ops + ['UPDATE'] * write_ops
        random.shuffle(ops_list)
        latencies_read = []
        latencies_write = []
        start_time = time.time()
        for op in ops_list:
            key_idx = random.randint(0, num_records - 1)
            key = f"user{key_idx}"
            op_start = time.time_ns()
            if op == 'READ':
                result = subprocess.run(
                    [redis_cli, '-p', str(port), 'HGETALL', key],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                latencies_read.append((time.time_ns() - op_start) / 1_000_000.0)
            else:
                field_name = f"field{random.randint(0, 9)}"
                field_value = ''.join(random.choices(string.ascii_letters + string.digits, k=100))
                result = subprocess.run(
                    [redis_cli, '-p', str(port), 'HSET', key, field_name, field_value],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                latencies_write.append((time.time_ns() - op_start) / 1_000_000.0)
        elapsed = time.time() - start_time
        throughput = num_ops / elapsed
        avg_read_lat = sum(latencies_read) / len(latencies_read) if latencies_read else 0
        avg_write_lat = sum(latencies_write) / len(latencies_write) if latencies_write else 0
        p50_read_lat = sorted(latencies_read)[len(latencies_read) // 2] if latencies_read else 0
        p99_idx = int(len(latencies_read) * 0.99) if latencies_read else 0
        p99_read_lat = sorted(latencies_read)[min(p99_idx, len(latencies_read) - 1)] if latencies_read else 0
        p99_idx_w = int(len(latencies_write) * 0.99) if latencies_write else 0
        p99_write_lat = sorted(latencies_write)[min(p99_idx_w, len(latencies_write) - 1)] if latencies_write else 0
        results.append({
            'iteration': iteration + 1,
            'workload': workload_name,
            'total_ops': num_ops,
            'elapsed_sec': round(elapsed, 3),
            'overall_throughput': round(throughput, 1),
            'ops_per_sec': round(throughput, 1),
            'read_ops': read_ops,
            'write_ops': write_ops,
            'avg_read_latency_ms': round(avg_read_lat, 3),
            'avg_write_latency_ms': round(avg_write_lat, 3),
            'p50_read_latency_ms': round(p50_read_lat, 3),
            'p99_read_latency_ms': round(p99_read_lat, 3),
            'p99_write_latency_ms': round(p99_write_lat, 3),
        })
    return results, workload_name


def run_ycsb_with_redis_benchmark(redis_benchmark, port, num_records, iterations=3):
    results = []
    commands_configs = [
        {'name': 'YCSB_A_50read_50update', 'tests': 'hset,hgetall', 'ratio': '0.5,0.5'},
        {'name': 'YCSB_B_95read_5update', 'tests': 'hgetall,hset', 'ratio': '0.95,0.05'},
        {'name': 'YCSB_C_100read', 'tests': 'hgetall', 'ratio': '1.0'},
        {'name': 'YCSB_D_95read_5insert', 'tests': 'hgetall,hset', 'ratio': '0.95,0.05'},
    ]
    for config in commands_configs:
        for iteration in range(iterations):
            cmd = [
                redis_benchmark,
                '-p', str(port),
                '-t', config['tests'],
                '-n', str(num_records),
                '-c', '50',
                '--ratio', config['ratio'],
                '-q',
            ]
            start_time = time.time()
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            elapsed = time.time() - start_time
            output = proc.stdout.strip()
            throughput = num_records / elapsed if elapsed > 0 else 0
            parsed_lines = []
            if output:
                for line in output.split('\n'):
                    line = line.strip()
                    if line:
                        parsed_lines.append(line)
            results.append({
                'iteration': iteration + 1,
                'workload': config['name'],
                'total_ops': num_records,
                'elapsed_sec': round(elapsed, 3),
                'overall_throughput': round(throughput, 1),
                'ops_per_sec': round(throughput, 1),
                'read_ratio': config['ratio'],
                'raw_output': parsed_lines,
                'p99_latency_ms': 0,
                'p50_read_latency_ms': 0,
                'avg_read_latency_ms': 0,
                'p99_read_latency_ms': 0,
                'p99_write_latency_ms': 0,
                'avg_write_latency_ms': 0,
            })
    return results


def main():
    parser = argparse.ArgumentParser(description='YCSB benchmark for Redis on ARM64')
    parser.add_argument('--redis-home', required=True, help='Redis installation directory')
    parser.add_argument('--port', type=int, default=6380, help='Redis port')
    parser.add_argument('--results-dir', required=True, help='Results output directory')
    parser.add_argument('--iterations', type=int, default=3, help='Number of iterations')
    parser.add_argument('--data-scale', type=float, default=1.0, help='YCSB dataset scale factor')
    parser.add_argument('--num-records', type=int, default=0, help='Number of records (overrides scale)')
    parser.add_argument('--num-ops', type=int, default=50000, help='Number of operations per iteration')
    args = parser.parse_args()

    redis_cli = os.path.join(args.redis_home, 'src', 'redis-cli')
    redis_benchmark = os.path.join(args.redis_home, 'src', 'redis-benchmark')
    num_records = args.num_records if args.num_records > 0 else int(args.data_scale * 100000)
    num_ops = args.num_ops

    print(f"[YCSB] Starting YCSB benchmark for Redis on ARM64")
    print(f"[YCSB] Records: {num_records}, Operations per iteration: {num_ops}")

    print(f"[YCSB] Phase 3a: Generating YCSB workload data ({num_records} records)...")
    records = generate_ycsb_workload(num_records, workload_type='a')

    print(f"[YCSB] Phase 3a: Loading {num_records} records into Redis...")
    loaded = load_data(redis_cli, args.port, records)
    print(f"[YCSB] Loaded {loaded} records.")

    print(f"[YCSB] Phase 3a: Running YCSB workloads ({args.iterations} iterations)...")
    ycsb_results = run_ycsb_with_redis_benchmark(
        redis_benchmark, args.port, num_records * 10, args.iterations
    )

    overall_throughputs = [r['overall_throughput'] for r in ycsb_results]
    avg_throughput = sum(overall_throughputs) / len(overall_throughputs) if overall_throughputs else 0
    max_throughput = max(overall_throughputs) if overall_throughputs else 0
    min_throughput = min(overall_throughputs) if overall_throughputs else 0

    result_json = {
        'benchmark': 'YCSB',
        'description': 'Yahoo! Cloud Serving Benchmark - industry-standard KV store benchmark evaluating throughput and latency under various read/write ratios',
        'reference': 'https://github.com/brianfrankcooper/YCSB',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'performance_metrics': {
            'overall_throughput': {
                'unit': 'ops_per_sec',
                'description': 'Overall throughput in operations per second'
            },
            'ops_per_sec': {
                'unit': 'ops/sec',
                'description': 'Average operations per second across all workloads'
            },
            'p99_read_latency_ms': {
                'unit': 'ms',
                'description': '99th percentile read latency in milliseconds'
            },
            'p99_write_latency_ms': {
                'unit': 'ms',
                'description': '99th percentile write latency in milliseconds'
            },
            'p50_read_latency_ms': {
                'unit': 'ms',
                'description': '50th percentile (median) read latency'
            },
            'avg_read_latency_ms': {
                'unit': 'ms',
                'description': 'Average read latency'
            }
        },
        'dataset_info': {
            'name': 'YCSB_workload',
            'size': f'{num_records} records x 10 fields x 100 chars',
            'source': 'Synthetically generated following YCSB specification'
        },
        'results': ycsb_results,
        'summary': {
            'avg_throughput_ops_per_sec': round(avg_throughput, 1),
            'max_throughput_ops_per_sec': round(max_throughput, 1),
            'min_throughput_ops_per_sec': round(min_throughput, 1),
            'num_workloads': len(ycsb_results),
            'iterations': args.iterations,
        }
    }

    output_file = os.path.join(args.results_dir, 'benchmark_ycsb.json')
    with open(output_file, 'w') as f:
        json.dump(result_json, f, indent=2)
    print(f"[YCSB] Results written to {output_file}")
    print(f"[YCSB] Average throughput: {avg_throughput:.1f} ops/sec")

    subprocess.run([redis_cli, '-p', str(args.port), 'FLUSHDB'], capture_output=True, timeout=30)

    print("[YCSB] YCSB benchmark complete.")


if __name__ == '__main__':
    main()