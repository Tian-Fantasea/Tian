#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import time
from datetime import datetime


def start_flink_cluster(flink_home):
    subprocess.run(
        [os.path.join(flink_home, "bin", "start-cluster.sh")],
        env={**os.environ, "FLINK_HOME": flink_home},
        capture_output=True,
    )
    time.sleep(15)


def stop_flink_cluster(flink_home):
    subprocess.run(
        [os.path.join(flink_home, "bin", "stop-cluster.sh")],
        env={**os.environ, "FLINK_HOME": flink_home},
        capture_output=True,
    )
    time.sleep(5)


def run_sql_job(flink_home, sql, timeout=300):
    sql_client = os.path.join(flink_home, "bin", "sql-client.sh")
    full_input = sql + "\nQUIT;\n"
    start = time.time()
    try:
        proc = subprocess.Popen(
            [sql_client, "embedded"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "FLINK_HOME": flink_home},
        )
        stdout, stderr = proc.communicate(input=full_input.encode(), timeout=timeout)
        elapsed = time.time() - start
        return proc.returncode, elapsed, stdout.decode(), stderr.decode()
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1, time.time() - start, "", "Timeout"


def benchmark_micro(flink_home, iterations, results_dir):
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    nproc = int(os.environ.get("NPROC", "4"))

    micro_tests = [
        {
            "name": "source_sink_throughput",
            "description": "DataGen source -> Print sink throughput",
            "sql": f"CREATE TABLE datagen_source ( id INT, data STRING, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '5' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '100000', 'number-of-rows' = '500000', 'fields.id.kind' = 'sequence', 'fields.id.start' = '1', 'fields.id.end' = '500000', 'fields.data.length' = '50' );\nCREATE TABLE print_sink ( id INT, data STRING, ts TIMESTAMP(3) ) WITH ( 'connector' = 'print' );\nINSERT INTO print_sink SELECT id, data, ts FROM datagen_source;",
        },
        {
            "name": "window_aggregate",
            "description": "Tumbling window aggregation performance",
            "sql": f"CREATE TABLE window_source ( key INT, value DOUBLE, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '5' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '50000', 'number-of-rows' = '300000', 'fields.key.kind' = 'random', 'fields.key.min' = '1', 'fields.key.max' = '100', 'fields.value.kind' = 'random', 'fields.value.min' = '0', 'fields.value.max' = '1000' );\nCREATE TABLE agg_sink ( window_start TIMESTAMP(3), window_end TIMESTAMP(3), key INT, sum_value DOUBLE, count_records BIGINT ) WITH ( 'connector' = 'print' );\nINSERT INTO agg_sink SELECT window_start, window_end, key, SUM(value) AS sum_value, COUNT(*) AS count_records FROM TABLE(TUMBLE(TABLE window_source, DESCRIPTOR(ts), INTERVAL '10' SECOND)) GROUP BY window_start, window_end, key;",
        },
        {
            "name": "join_performance",
            "description": "Inner join between two DataGen streams",
            "sql": f"CREATE TABLE left_stream ( id INT, name STRING, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '5' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '20000', 'number-of-rows' = '100000' );\nCREATE TABLE right_stream ( id INT, score DOUBLE, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '5' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '20000', 'number-of-rows' = '100000' );\nCREATE TABLE join_sink ( id INT, name STRING, score DOUBLE ) WITH ( 'connector' = 'print' );\nINSERT INTO join_sink SELECT l.id, l.name, r.score FROM left_stream l JOIN right_stream r ON l.id = r.id;",
        },
        {
            "name": "filter_project",
            "description": "Simple filter and projection pipeline",
            "sql": f"CREATE TABLE raw_source ( id INT, category STRING, amount DOUBLE, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '5' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '100000', 'number-of-rows' = '500000', 'fields.category.length' = '5' );\nCREATE TABLE filtered_sink ( id INT, category STRING, amount DOUBLE ) WITH ( 'connector' = 'print' );\nINSERT INTO filtered_sink SELECT id, category, amount FROM raw_source WHERE amount > 500;",
        },
    ]

    results = []
    for i in range(iterations):
        print(f"[MICRO] Iteration {i + 1}/{iterations}")
        start_flink_cluster(flink_home)

        for test in micro_tests:
            print(f"[MICRO] Running {test['name']}...")
            rc, elapsed, stdout, stderr = run_sql_job(flink_home, test["sql"], timeout=300)
            rows = 0
            try:
                for line in stdout.strip().split("\n"):
                    if line.strip() and "INSERT" in line:
                        parts = line.split()
                        for p in parts:
                            if ":" in p and p.split(":")[0].isdigit():
                                rows = int(p.split(":")[0])
                                break
            except Exception:
                pass

            results.append({
                "iteration": i + 1,
                "name": test["name"],
                "description": test["description"],
                "elapsed_sec": round(elapsed, 3),
                "rows_processed": rows,
                "rows_per_sec": round(rows / elapsed, 1) if elapsed > 0 and rows > 0 else 0,
                "success": rc == 0,
            })
            print(f"[MICRO] {test['name']}: {elapsed:.3f}s")

        stop_flink_cluster(flink_home)

    avg_results = []
    for test in micro_tests:
        t_results = [r for r in results if r["name"] == test["name"] and r["success"]]
        if t_results:
            avg_elapsed = sum(r["elapsed_sec"] for r in t_results) / len(t_results)
            avg_rps = sum(r["rows_per_sec"] for r in t_results) / len(t_results)
            avg_results.append({
                "name": test["name"],
                "description": test["description"],
                "avg_elapsed_sec": round(avg_elapsed, 3),
                "avg_rows_per_sec": round(avg_rps, 1),
                "iterations": len(t_results),
            })

    output = {
        "benchmark": "micro",
        "description": "Flink micro-level operation benchmarks (source/sink, window, join, filter)",
        "reference": "https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/overview/",
        "timestamp": timestamp,
        "performance_metrics": {
            "rows_per_sec": {"unit": "rows/s", "description": "Processing throughput per operation"},
            "elapsed_sec": {"unit": "s", "description": "Operation execution time"},
        },
        "dataset_info": {
            "name": "Flink DataGen generated",
            "size": "100K-500K rows per test",
            "source": "Flink DataGen connector (in-memory)",
        },
        "results": avg_results,
        "raw_results": results,
    }

    out_file = os.path.join(results_dir, "micro_benchmark.json")
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[MICRO] Results saved to {out_file}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Flink micro benchmarks")
    parser.add_argument("--flink-home", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    benchmark_micro(args.flink_home, args.iterations, args.results_dir)


if __name__ == "__main__":
    main()