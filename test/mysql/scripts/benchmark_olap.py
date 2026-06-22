#!/usr/bin/env python3
import json
import subprocess
import sys
import time
import argparse
import datetime
import os
import re

THREAD_VALUES = [1, 2, 4, 8, 16, 32, 64]

def run_sysbench_concurrency(test_name, mysql_args, table_size, threads, time_sec=30):
    cmd = [
        'sysbench', test_name,
        '--mysql-host=127.0.0.1',
        f'--mysql-port={mysql_args["port"]}',
        f'--mysql-user={mysql_args["user"]}',
        f'--mysql-password={mysql_args["password"]}',
        '--mysql-db=sbtest',
        '--tables=1',
        f'--table-size={table_size}',
        f'--threads={threads}',
        f'--time={time_sec}',
        '--percentile=95',
        '--percentile=99',
        'run',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=time_sec + 60)
    output = result.stdout

    metrics = {}
    for line in output.split('\n'):
        line = line.strip()
        m = re.search(r'transactions:\s+\d+\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["tps"] = float(m.group(1))
        m = re.search(r'queries:\s+\d+\s+\(([\d.]+)\s+per sec\)', line)
        if m:
            metrics["qps"] = float(m.group(1))
        m = re.search(r'latency \(ms\):\s+min:\s+([\d.]+)\s+avg:\s+([\d.]+)\s+max:\s+([\d.]+)\s+95th percentile:\s+([\d.]+)\s+99th percentile:\s+([\d.]+)', line)
        if m:
            metrics["lat_avg_ms"] = float(m.group(2))
            metrics["lat_p95_ms"] = float(m.group(4))
            metrics["lat_p99_ms"] = float(m.group(5))
    metrics["threads"] = threads
    return metrics

def run_analytical_queries(mysql_args, table_size, iterations):
    results = {}

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'CREATE DATABASE IF NOT EXISTS bench_analytics;'], capture_output=True, timeout=10)

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    f'USE bench_analytics; '
                    f'CREATE TABLE IF NOT EXISTS analytics_data ('
                    f'id INT PRIMARY KEY AUTO_INCREMENT, '
                    f'category VARCHAR(50), '
                    f'value DECIMAL(10,2), '
                    f'timestamp DATETIME, '
                    f'status VARCHAR(20), '
                    f'region VARCHAR(30));'], capture_output=True, timeout=10)

    for i in range(table_size):
        if i % 10000 == 0:
            batch_end = min(i + 10000, table_size)
            rows = []
            for j in range(i, batch_end):
                cat = f'cat_{j % 50}'
                val = j * 1.5
                ts = f'2025-01-{j % 30 + 1:02d} {j % 24:02d}:{j % 60:02d}:00'
                status = f'status_{j % 10}'
                region = f'region_{j % 20}'
                rows.append(f"('{cat}',{val:.2f},'{ts}','{status}','{region}')")
            insert_sql = f"INSERT INTO analytics_data (category,value,timestamp,status,region) VALUES {','.join(rows)};"
            subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                            '-P', str(mysql_args['port']), '-e', insert_sql],
                           capture_output=True, timeout=60)

    queries = {
        "simple_filter": "SELECT COUNT(*) FROM analytics_data WHERE category = 'cat_0';",
        "aggregation_avg": "SELECT AVG(value) FROM analytics_data;",
        "group_by_category": "SELECT category, COUNT(*), AVG(value), SUM(value) FROM analytics_data GROUP BY category;",
        "group_by_region_status": "SELECT region, status, COUNT(*), AVG(value) FROM analytics_data GROUP BY region, status;",
        "range_filter": "SELECT COUNT(*) FROM analytics_data WHERE value BETWEEN 100 AND 5000;",
        "order_by_limit": "SELECT * FROM analytics_data ORDER BY value DESC LIMIT 100;",
        "multi_condition": "SELECT COUNT(*) FROM analytics_data WHERE category = 'cat_5' AND region = 'region_10' AND status = 'status_3';",
        "distinct": "SELECT DISTINCT category FROM analytics_data;",
    }

    for qname, query in queries.items():
        print(f'[OLAP] Running analytical query: {qname}')
        run_times = []
        for i in range(iterations):
            start = time.time()
            subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                            '-P', str(mysql_args['port']), '-e',
                            f'USE bench_analytics; {query}'],
                           capture_output=True, timeout=30)
            elapsed = time.time() - start
            run_times.append(elapsed)
        avg_time = round(sum(run_times) / len(run_times) * 1000, 4)
        min_time = round(min(run_times) * 1000, 4)
        max_time = round(max(run_times) * 1000, 4)
        results[qname] = {
            "avg_time_ms": avg_time,
            "min_time_ms": min_time,
            "max_time_ms": max_time,
            "iterations": iterations,
            "query": query,
        }
        print(f'[OLAP]   {qname}: avg={avg_time}ms')

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'DROP DATABASE IF EXISTS bench_analytics;'], capture_output=True, timeout=10)

    return results

def main():
    parser = argparse.ArgumentParser(description='MySQL OLAP & Concurrency Scaling Benchmark')
    parser.add_argument('--results-json', required=True)
    parser.add_argument('--section', default='olap_benchmark')
    parser.add_argument('--table-size', type=int, default=100000)
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

    all_results = {}

    print('[OLAP] Phase 3b-1: Concurrency scaling for oltp_read_write...')
    concurrency_results = {}
    for threads in THREAD_VALUES:
        label = f"threads_{threads}"
        print(f'[OLAP]   threads={threads}')
        iteration_runs = []
        for i in range(args.iterations):
            metrics = run_sysbench_concurrency('oltp_read_write', mysql_args, args.table_size, threads, time_sec=30)
            iteration_runs.append(metrics)
        avg_metrics = {}
        for key in ["tps", "qps", "lat_avg_ms", "lat_p95_ms", "lat_p99_ms"]:
            vals = [r.get(key, 0) for r in iteration_runs if isinstance(r.get(key, 0), (int, float))]
            avg_metrics[f"avg_{key}"] = round(sum(vals) / len(vals), 2) if vals else 0
        avg_metrics["threads"] = threads
        concurrency_results[label] = avg_metrics
        print(f'[OLAP]     TPS={avg_metrics.get("avg_tps",0)}, QPS={avg_metrics.get("avg_qps",0)}, LatAvg={avg_metrics.get("avg_lat_avg_ms",0)}ms')
    all_results["concurrency_scaling"] = concurrency_results

    print('[OLAP] Phase 3b-2: Analytical queries...')
    analytics_results = run_analytical_queries(mysql_args, args.table_size, args.iterations)
    all_results["analytical_queries"] = analytics_results

    output = {
        "benchmark": "olap_concurrency",
        "description": "MySQL concurrency scaling benchmark (sysbench threads 1-64) and analytical query benchmark",
        "reference": "sysbench (https://github.com/akopytov/sysbench) and MySQL SQL benchmarks",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "tps": {"unit": "transactions/sec", "description": "Transactions per second at different concurrency levels"},
            "qps": {"unit": "queries/sec", "description": "Queries per second at different concurrency levels"},
            "latency": {"unit": "milliseconds", "description": "Transaction latency (avg, p95, p99) at different concurrency"},
            "query_time": {"unit": "milliseconds", "description": "Analytical query execution time"},
        },
        "dataset_info": {
            "name": "sysbench sbtest + analytics_data",
            "size": f"{args.table_size} rows",
            "source": "sysbench prepare + generated analytics data"
        },
        "parameters": {
            "table_size": args.table_size,
            "iterations": args.iterations,
            "thread_values": THREAD_VALUES,
        },
        "results": all_results
    }

    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output)
    ], check=True)

    print('[OLAP] Benchmark complete')

if __name__ == '__main__':
    main()
