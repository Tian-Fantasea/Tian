#!/usr/bin/env python3
import json
import subprocess
import sys
import os
import time
import argparse
import datetime

def run_mysql_query(mysql_args, query, database='sbtest', timeout=30):
    cmd = ['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
           '-P', str(mysql_args['port']), '-e', query]
    if database:
        cmd.extend(['-D', database])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout, result.stderr, result.returncode

def bench_connection_handling(mysql_args, iterations=1):
    results = {}
    batch_sizes = [1, 10, 100, 500]

    for bs in batch_sizes:
        label = f"connect_disconnect_{bs}"
        print(f'[MICRO] Connection handling: {label}')
        run_times = []
        for i in range(iterations):
            start = time.time()
            for j in range(bs):
                subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                                '-P', str(mysql_args['port']), '-e', 'SELECT 1;'],
                               capture_output=True, timeout=10)
            elapsed = time.time() - start
            run_times.append(elapsed)
        avg_time = round(sum(run_times) / len(run_times) * 1000, 4)
        rate = round(bs / (sum(run_times) / len(run_times)), 2)
        results[label] = {"avg_time_ms": avg_time, "connections_per_sec": rate, "batch_size": bs}
    return results

def bench_bulk_insert(mysql_args, iterations=1):
    results = {}
    row_counts = [1000, 5000, 10000]

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'CREATE DATABASE IF NOT EXISTS bench_micro;'], capture_output=True, timeout=10)

    for rc in row_counts:
        label = f"bulk_insert_{rc}"
        print(f'[MICRO] Bulk insert: {label}')
        run_times = []
        for i in range(iterations):
            subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                            '-P', str(mysql_args['port']), '-e',
                            'USE bench_micro; DROP TABLE IF EXISTS bulk_test; '
                            'CREATE TABLE bulk_test (id INT PRIMARY KEY AUTO_INCREMENT, val VARCHAR(100));'],
                           capture_output=True, timeout=10)

            rows = ','.join([f"('row_{j}')" for j in range(rc)])
            insert_sql = f"INSERT INTO bulk_test (val) VALUES {rows};"
            start = time.time()
            subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                            '-P', str(mysql_args['port']), '-e',
                            f'USE bench_micro; {insert_sql}'],
                           capture_output=True, timeout=60)
            elapsed = time.time() - start
            run_times.append(elapsed)
        avg_time = round(sum(run_times) / len(run_times) * 1000, 4)
        rate = round(rc / (sum(run_times) / len(run_times)), 2)
        results[label] = {"avg_time_ms": avg_time, "insert_rate_per_sec": rate, "row_count": rc}

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'DROP DATABASE IF EXISTS bench_micro;'], capture_output=True, timeout=10)
    return results

def bench_simple_queries(mysql_args, iterations=1):
    results = {}

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'CREATE DATABASE IF NOT EXISTS bench_micro;'], capture_output=True, timeout=10)

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'USE bench_micro; '
                    'CREATE TABLE query_test (id INT PRIMARY KEY, name VARCHAR(50), value DECIMAL(10,2)); '
                    + 'INSERT INTO query_test (id, name, value) VALUES ' + ','.join([f'({i}, "name_{i}", {i*1.5:.2f})' for i in range(10000)]) + ';'],
                   capture_output=True, timeout=30)

    queries = {
        "select_by_pk": "SELECT * FROM query_test WHERE id = 500;",
        "select_range": "SELECT * FROM query_test WHERE id BETWEEN 100 AND 200;",
        "select_count": "SELECT COUNT(*) FROM query_test;",
        "select_order_limit": "SELECT * FROM query_test ORDER BY value DESC LIMIT 50;",
        "update_by_pk": "UPDATE query_test SET value = value + 1 WHERE id = 500;",
        "select_like": "SELECT * FROM query_test WHERE name LIKE 'name_5%';",
    }

    for qname, query in queries.items():
        print(f'[MICRO] Simple query: {qname}')
        run_times = []
        for i in range(iterations):
            start = time.time()
            subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                            '-P', str(mysql_args['port']), '-e',
                            f'USE bench_micro; {query}'],
                           capture_output=True, timeout=10)
            elapsed = time.time() - start
            run_times.append(elapsed)
        avg_time = round(sum(run_times) / len(run_times) * 1000, 4)
        results[qname] = {"avg_time_ms": avg_time, "iterations": iterations, "query": query}

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'DROP DATABASE IF EXISTS bench_micro;'], capture_output=True, timeout=10)
    return results

def bench_engine_comparison(mysql_args, iterations=1):
    results = {}

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'CREATE DATABASE IF NOT EXISTS bench_engine;'], capture_output=True, timeout=10)

    engines = ['InnoDB', 'MyISAM']

    for engine in engines:
        print(f'[MICRO] Engine comparison: {engine}')
        table_name = f'test_{engine.lower()}'
        create_sql = f'USE bench_engine; DROP TABLE IF EXISTS {table_name}; '
        create_sql += f'CREATE TABLE {table_name} (id INT PRIMARY KEY, val INT) ENGINE={engine}; '
        create_sql += f'INSERT INTO {table_name} (id, val) VALUES {",".join([f"({i},{i})" for i in range(10000)])};'

        subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                        '-P', str(mysql_args['port']), '-e', create_sql],
                       capture_output=True, timeout=30)

        ops = {
            "select_count": f"SELECT COUNT(*) FROM {table_name};",
            "select_range": f"SELECT * FROM {table_name} WHERE id BETWEEN 1 AND 100;",
            "update_by_pk": f"UPDATE {table_name} SET val = val + 1 WHERE id = 1;",
        }

        engine_results = {}
        for op_name, query in ops.items():
            run_times = []
            for i in range(iterations):
                start = time.time()
                subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                                '-P', str(mysql_args['port']), '-e',
                                f'USE bench_engine; {query}'],
                               capture_output=True, timeout=10)
                elapsed = time.time() - start
                run_times.append(elapsed)
            avg_time = round(sum(run_times) / len(run_times) * 1000, 4)
            engine_results[op_name] = {"avg_time_ms": avg_time}
        results[engine] = engine_results

    subprocess.run(['mysql', '-u', mysql_args['user'], '-p' + mysql_args['password'],
                    '-P', str(mysql_args['port']), '-e',
                    'DROP DATABASE IF EXISTS bench_engine;'], capture_output=True, timeout=10)
    return results

def main():
    parser = argparse.ArgumentParser(description='MySQL Micro Benchmarks')
    parser.add_argument('--results-json', required=True)
    parser.add_argument('--section', default='micro_benchmark')
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
    iterations = args.iterations

    print('[MICRO] MySQL micro benchmarks on ARM64...')

    all_results = {}

    print('[MICRO] Running connection_handling...')
    all_results["connection_handling"] = bench_connection_handling(mysql_args, iterations=iterations)

    print('[MICRO] Running bulk_insert...')
    all_results["bulk_insert"] = bench_bulk_insert(mysql_args, iterations=iterations)

    print('[MICRO] Running simple_queries...')
    all_results["simple_queries"] = bench_simple_queries(mysql_args, iterations=iterations)

    print('[MICRO] Running engine_comparison...')
    all_results["engine_comparison"] = bench_engine_comparison(mysql_args, iterations=iterations)

    output = {
        "benchmark": "micro_operations",
        "description": "MySQL micro benchmarks on ARM64: connection handling, bulk insert, simple queries, engine comparison (InnoDB vs MyISAM)",
        "reference": "MySQL (https://dev.mysql.com/doc/)",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "connection_rate": {"unit": "connections/sec", "description": "Connection handling throughput"},
            "insert_rate": {"unit": "rows/sec", "description": "Bulk insert throughput"},
            "query_latency": {"unit": "milliseconds", "description": "Simple query execution latency"},
        },
        "dataset_info": {
            "name": "bench_micro tables",
            "size": "100-10000 rows",
            "source": "generated test data"
        },
        "parameters": {"iterations": iterations},
        "results": all_results
    }

    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output)
    ], check=True)

    print(f'[MICRO] Results written to {args.results_json} section {args.section}')
    for name, res in all_results.items():
        print(f'[MICRO] {name}: {res}')
    print('[MICRO] Benchmark complete')

if __name__ == '__main__':
    main()
