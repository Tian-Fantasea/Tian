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


def modify_flink_conf(flink_home, key, value):
    conf_file = os.path.join(flink_home, "conf", "flink-conf.yaml")
    lines = []
    with open(conf_file, "r") as f:
        for line in f:
            if line.strip().startswith(f"{key}:"):
                lines.append(f"{key}: {value}\n")
            else:
                lines.append(line)
    found = any(l.strip().startswith(f"{key}:") for l in lines)
    if not found:
        lines.append(f"{key}: {value}\n")
    with open(conf_file, "w") as f:
        f.writelines(lines)


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
        return proc.returncode, elapsed, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1, time.time() - start, "", "Timeout"


def benchmark_state(flink_home, iterations, results_dir):
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    state_tests = [
        {
            "name": "hashmap_state_light",
            "description": "HashMap state backend with light state (100 keys)",
            "checkpoint_interval": "10000",
            "sql": "CREATE TABLE state_source ( key INT, value DOUBLE, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '5' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '50000', 'number-of-rows' = '200000', 'fields.key.kind' = 'random', 'fields.key.min' = '1', 'fields.key.max' = '100' );\nCREATE TABLE state_sink ( key INT, avg_value DOUBLE, ts TIMESTAMP(3) ) WITH ( 'connector' = 'print' );\nINSERT INTO state_sink SELECT key, AVG(value) AS avg_value, ts FROM state_source GROUP BY key, ts;",
        },
        {
            "name": "hashmap_state_heavy",
            "description": "HashMap state backend with heavy state (10000 keys)",
            "checkpoint_interval": "30000",
            "sql": "CREATE TABLE heavy_source ( key INT, value DOUBLE, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '5' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '30000', 'number-of-rows' = '300000', 'fields.key.kind' = 'random', 'fields.key.min' = '1', 'fields.key.max' = '10000' );\nCREATE TABLE heavy_sink ( key INT, avg_value DOUBLE, cnt BIGINT ) WITH ( 'connector' = 'print' );\nINSERT INTO heavy_sink SELECT key, AVG(value) AS avg_value, COUNT(*) AS cnt FROM heavy_source GROUP BY key;",
        },
        {
            "name": "window_state_session",
            "description": "Session window with state accumulation",
            "checkpoint_interval": "20000",
            "sql": "CREATE TABLE session_source ( user_id INT, event STRING, ts TIMESTAMP(3), WATERMARK FOR ts AS ts - INTERVAL '10' SECOND ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '20000', 'number-of-rows' = '150000', 'fields.user_id.kind' = 'random', 'fields.user_id.min' = '1', 'fields.user_id.max' = '500' );\nCREATE TABLE session_sink ( window_start TIMESTAMP(3), window_end TIMESTAMP(3), user_id INT, event_count BIGINT ) WITH ( 'connector' = 'print' );\nINSERT INTO session_sink SELECT window_start, window_end, user_id, COUNT(*) AS event_count FROM TABLE(SESSION(TABLE session_source, DESCRIPTOR(ts), INTERVAL '30' SECOND)) GROUP BY window_start, window_end, user_id;",
        },
    ]

    results = []
    for i in range(iterations):
        print(f"[STATE] Iteration {i + 1}/{iterations}")

        for test in state_tests:
            print(f"[STATE] Running {test['name']}...")
            modify_flink_conf(flink_home, "execution.checkpointing.interval", test["checkpoint_interval"])
            modify_flink_conf(flink_home, "state.backend", "hashmap")
            start_flink_cluster(flink_home)

            rc, elapsed, stdout, stderr = run_sql_job(flink_home, test["sql"], timeout=300)
            checkpoint_size = 0
            try:
                ckpt_dirs = [
                    os.path.join(flink_home, "checkpoints"),
                    "/tmp/flink-checkpoints",
                    os.path.join(flink_home, "flink-standalonesession", "checkpoints"),
                ]
                ckpt_dir_conf = None
                conf_file = os.path.join(flink_home, "conf", "flink-conf.yaml")
                if os.path.exists(conf_file):
                    with open(conf_file, "r") as f:
                        for line in f:
                            if "state.checkpoints.dir" in line:
                                ckpt_dir_conf = line.split(":")[1].strip().strip("'\"")
                                if ckpt_dir_conf.startswith("file:"):
                                    ckpt_dir_conf = ckpt_dir_conf[5:]
                if ckpt_dir_conf:
                    ckpt_dirs.append(ckpt_dir_conf)
                for ckpt_dir in ckpt_dirs:
                    if os.path.exists(ckpt_dir):
                        for root, dirs, files in os.walk(ckpt_dir):
                            for fn in files:
                                checkpoint_size += os.path.getsize(os.path.join(root, fn))
                        if checkpoint_size > 0:
                            break
            except Exception:
                pass

            results.append({
                "iteration": i + 1,
                "name": test["name"],
                "description": test["description"],
                "checkpoint_interval_ms": int(test["checkpoint_interval"]),
                "elapsed_sec": round(elapsed, 3),
                "checkpoint_size_bytes": checkpoint_size,
                "success": rc == 0,
            })
            print(f"[STATE] {test['name']}: {elapsed:.3f}s, ckpt_size={checkpoint_size}")

            stop_flink_cluster(flink_home)

    avg_results = []
    for test in state_tests:
        t_results = [r for r in results if r["name"] == test["name"] and r["success"]]
        if t_results:
            avg_elapsed = sum(r["elapsed_sec"] for r in t_results) / len(t_results)
            avg_ckpt = sum(r["checkpoint_size_bytes"] for r in t_results) / len(t_results)
            avg_results.append({
                "name": test["name"],
                "description": test["description"],
                "checkpoint_interval_ms": int(test["checkpoint_interval"]),
                "avg_elapsed_sec": round(avg_elapsed, 3),
                "avg_checkpoint_size_bytes": round(avg_ckpt, 1),
                "iterations": len(t_results),
            })

    output = {
        "benchmark": "state",
        "description": "Flink state backend & checkpoint performance benchmark",
        "reference": "https://nightlies.apache.org/flink/flink-docs-stable/docs/ops/state/state_backends/",
        "timestamp": timestamp,
        "performance_metrics": {
            "elapsed_sec": {"unit": "s", "description": "Job execution time with checkpointing enabled"},
            "checkpoint_size_bytes": {"unit": "bytes", "description": "Checkpoint size (state size on disk)"},
        },
        "dataset_info": {
            "name": "Flink DataGen state test",
            "size": "150K-300K rows per test",
            "source": "Flink DataGen connector (in-memory)",
        },
        "results": avg_results,
        "raw_results": results,
    }

    out_file = os.path.join(results_dir, "benchmark_state.json")
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[STATE] Results saved to {out_file}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Flink state backend benchmark")
    parser.add_argument("--flink-home", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    benchmark_state(args.flink_home, args.iterations, args.results_dir)


if __name__ == "__main__":
    main()