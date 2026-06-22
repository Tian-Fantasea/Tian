#!/usr/bin/env python3
import json
import subprocess
import time
import argparse
import datetime
import os
import re
import sys

OLTP_TESTS = {
    "oltp_point_select": {
        "test": "oltp_point_select",
        "description": "Point select queries (SELECT by primary key)",
        "tables": 1,
    },
    "oltp_read_only": {
        "test": "oltp_read_only",
        "description": "Read-only OLTP workload (point selects + range queries + sums)",
        "tables": 1,
    },
    "oltp_write_only": {
        "test": "oltp_write_only",
        "description": "Write-only OLTP workload (INSERT + UPDATE + DELETE)",
        "tables": 1,
    },
    "oltp_read_write": {
        "test": "oltp_read_write",
        "description": "Mixed read-write OLTP workload (full transactional)",
        "tables": 1,
    },
    "oltp_update_index": {
        "test": "oltp_update_index",
        "description": "UPDATE with indexed column",
        "tables": 1,
    },
    "oltp_update_non_index": {
        "test": "oltp_update_non_index",
        "description": "UPDATE with non-indexed column",
        "tables": 1,
    },
}

def run_sysbench(test_name, mysql_args, table_size, threads, time_sec=60):
    cmd = [
        'sysbench',
        test_name,
        '--mysql-host=127.0.0.1',
        f'--mysql-port={mysql_args["port"]}',
        f'--mysql-user={mysql_args["user"]}',
        f'--mysql-password={mysql_args["password"]}',
        '--mysql-db=sbtest',
        f'--tables={OLTP_TESTS[test_name]["tables"]}',
        f'--table-size={table_size}',
        f'--threads={threads}',
        f'--time={time_sec}',
        '--percentile=95',
        '--percentile=99',
        '--report-interval=10',
        'run',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=time_sec + 60)
    output = result.stdout

    metrics = {
        "tps": 0, "qps": 0, "latency_avg_ms": 0,
        "latency_p95_ms": 0, "latency_p99_ms": 0,
        "read_per_sec": 0, "write_per_sec": 0,
        "other_per_sec": 0, "errors": 0, "reconnects": 0,
    }

    for line in output.split('\n'):
        line = line.strip()
        m = re.search(r'transactions:\s+(\d+)\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["total_transactions"] = int(m.group(1))
            metrics["tps"] = float(m.group(2))

        m = re.search(r'queries:\s+(\d+)\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["total_queries"] = int(m.group(1))
            metrics["qps"] = float(m.group(2))

        m = re.search(r'read:\s+(\d+)\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["total_read"] = int(m.group(1))
            metrics["read_per_sec"] = float(m.group(2))

        m = re.search(r'write:\s+(\d+)\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["total_write"] = int(m.group(1))
            metrics["write_per_sec"] = float(m.group(2))

        m = re.search(r'other:\s+(\d+)\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["total_other"] = int(m.group(1))
            metrics["other_per_sec"] = float(m.group(2))

        m = re.search(r'latency\s+\(ms\):\s+min:\s+([\d.]+)\s+avg:\s+([\d.]+)\s+max:\s+([\d.]+)\s+95th\s+percentile:\s+([\d.]+)\s+99th\s+percentile:\s+([\d.]+)', line)
        if m:
            metrics["latency_min_ms"] = float(m.group(1))
            metrics["latency_avg_ms"] = float(m.group(2))
            metrics["latency_max_ms"] = float(m.group(3))
            metrics["latency_p95_ms"] = float(m.group(4))
            metrics["latency_p99_ms"] = float(m.group(5))

        m = re.search(r'errors:\s+(\d+)\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["errors"] = int(m.group(1))

        m = re.search(r'reconnects:\s+(\d+)\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["reconnects"] = int(m.group(1))

    metrics["raw_output"] = output
    return metrics

def sysbench_prepare(mysql_args, table_size, threads):
    cmd = [
        'sysbench', 'oltp_read_write',
        '--mysql-host=127.0.0.1',
        f'--mysql-port={mysql_args["port"]}',
        f'--mysql-user={mysql_args["user"]}',
        f'--mysql-password={mysql_args["password"]}',
        '--mysql-db=sbtest',
        '--tables=1',
        f'--table-size={table_size}',
        f'--threads={threads}',
        'prepare',
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print('[OLTP] sysbench data prepared')

def sysbench_cleanup(mysql_args, threads):
    cmd = [
        'sysbench', 'oltp_read_write',
        '--mysql-host=127.0.0.1',
        f'--mysql-port={mysql_args["port"]}',
        f'--mysql-user={mysql_args["user"]}',
        f'--mysql-password={mysql_args["password"]}',
        '--mysql-db=sbtest',
        '--tables=1',
        f'--threads={threads}',
        'cleanup',
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)

def main():
    parser = argparse.ArgumentParser(description='MySQL OLTP Benchmark using sysbench')
    parser.add_argument('--results-json', required=True)
    parser.add_argument('--section', default='oltp_benchmark')
    parser.add_argument('--table-size', type=int, default=100000)
    parser.add_argument('--threads', type=int, default=16)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--mysql-port', type=int, default=3307)
    parser.add_argument('--mysql-user', default='root')
    parser.add_argument('--mysql-password', default='bench123')
    args = parser.parse_args()

    mysql_args = {
        'user': args.mysql_user,
        'password': args.mysql_password,
        'port': args.mysql_port,
    }

    print(f'[OLTP] Preparing sysbench data (table_size={args.table_size}, threads={args.threads})...')
    sysbench_prepare(mysql_args, args.table_size, args.threads)

    all_results = {}

    for test_name, config in OLTP_TESTS.items():
        print(f'[OLTP] Running {test_name}: {config["description"]}')
        iteration_results = []
        for i in range(args.iterations):
            print(f'[OLTP]   iteration {i+1}/{args.iterations}')
            metrics = run_sysbench(test_name, mysql_args, args.table_size, args.threads, time_sec=60)
            iteration_results.append(metrics)

        avg_metrics = {}
        metric_keys = ["tps", "qps", "latency_avg_ms", "latency_p95_ms", "latency_p99_ms",
                       "read_per_sec", "write_per_sec", "other_per_sec"]
        for key in metric_keys:
            vals = [r.get(key, 0) for r in iteration_results if isinstance(r.get(key, 0), (int, float))]
            avg_metrics[f"avg_{key}"] = round(sum(vals) / len(vals), 2) if vals else 0

        avg_metrics["iterations"] = args.iterations
        avg_metrics["threads"] = args.threads
        avg_metrics["table_size"] = args.table_size
        all_results[test_name] = avg_metrics

        tps = avg_metrics.get("avg_tps", 0)
        qps = avg_metrics.get("avg_qps", 0)
        lat_avg = avg_metrics.get("avg_latency_avg_ms", 0)
        lat_p95 = avg_metrics.get("avg_latency_p95_ms", 0)
        print(f'[OLTP] {test_name}: TPS={tps}, QPS={qps}, LatAvg={lat_avg}ms, P95={lat_p95}ms')

    sysbench_cleanup(mysql_args, args.threads)

    output = {
        "benchmark": "oltp_sysbench",
        "description": "MySQL OLTP benchmark using sysbench (point select, read-only, write-only, read-write, update indexed/non-indexed)",
        "reference": "sysbench (https://github.com/akopytov/sysbench)",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "tps": {"unit": "transactions/sec", "description": "Transactions per second"},
            "qps": {"unit": "queries/sec", "description": "Queries per second"},
            "latency_avg": {"unit": "milliseconds", "description": "Average latency per transaction"},
            "latency_p95": {"unit": "milliseconds", "description": "95th percentile latency"},
            "latency_p99": {"unit": "milliseconds", "description": "99th percentile latency"},
        },
        "dataset_info": {
            "name": "sysbench sbtest",
            "size": f"{args.table_size} rows per table",
            "source": "sysbench oltp_read_write prepare"
        },
        "parameters": {
            "table_size": args.table_size,
            "threads": args.threads,
            "iterations": args.iterations,
            "time_per_test": 60,
        },
        "results": all_results
    }

    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output)
    ], check=True)

    print('[OLTP] Benchmark complete')

if __name__ == '__main__':
    main()
