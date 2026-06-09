#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import time
import threading
from datetime import datetime


def start_flink_cluster(flink_home):
    start_cmd = os.path.join(flink_home, "bin", "start-cluster.sh")
    subprocess.run([start_cmd], env={**os.environ, "FLINK_HOME": flink_home}, capture_output=True)
    time.sleep(15)


def stop_flink_cluster(flink_home):
    stop_cmd = os.path.join(flink_home, "bin", "stop-cluster.sh")
    subprocess.run([stop_cmd], env={**os.environ, "FLINK_HOME": flink_home}, capture_output=True)
    time.sleep(5)


def submit_streaming_job(flink_home, jar_path, args_list, timeout=300):
    flink_cmd = os.path.join(flink_home, "bin", "flink")
    cmd = [flink_cmd, "run", jar_path] + args_list
    start = time.time()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ)
        stdout, stderr = proc.communicate(timeout=timeout)
        elapsed = time.time() - start
        return proc.returncode, elapsed, stdout.decode(), stderr.decode()
    except subprocess.TimeoutExpired:
        proc.kill()
        elapsed = time.time() - start
        return -1, elapsed, "", "Timeout"


def benchmark_streaming_throughput(flink_home, iterations, results_dir):
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    wordcount_jar = os.path.join(flink_home, "examples", "streaming", "WordCount.jar")
    results = []

    configs = [
        ("single_slot", {"parallelism": 1}),
        ("half_slots", {"parallelism": max(1, int(os.environ.get("NPROC", "4")) // 2)}),
        ("all_slots", {"parallelism": int(os.environ.get("NPROC", "4")))}),
    ]

    for i in range(iterations):
        print(f"[STREAMING] Iteration {i + 1}/{iterations}")
        start_flink_cluster(flink_home)

        for config_name, params in configs:
            p = params["parallelism"]
            print(f"[STREAMING] Config: {config_name}, parallelism={p}")
            rc, elapsed, stdout, stderr = submit_streaming_job(
                flink_home, wordcount_jar, ["-p", str(p)], timeout=120
            )

            records = 0
            try:
                for line in stdout.strip().split("\n"):
                    if line.strip() and not line.startswith("+") and "(" in line:
                        records += 1
            except Exception:
                pass

            results.append({
                "iteration": i + 1,
                "config": config_name,
                "parallelism": p,
                "elapsed_sec": round(elapsed, 3),
                "records_processed": records,
                "records_per_sec": round(records / elapsed, 1) if elapsed > 0 and records > 0 else 0,
                "success": rc == 0,
            })
            print(f"[STREAMING] {config_name}: {elapsed:.3f}s, {records} records")

        stop_flink_cluster(flink_home)

    avg_results = []
    for config_name, params in configs:
        c_results = [r for r in results if r["config"] == config_name and r["success"]]
        if c_results:
            avg_elapsed = sum(r["elapsed_sec"] for r in c_results) / len(c_results)
            avg_rps = sum(r["records_per_sec"] for r in c_results) / len(c_results)
            avg_results.append({
                "config": config_name,
                "parallelism": params["parallelism"],
                "avg_elapsed_sec": round(avg_elapsed, 3),
                "avg_records_per_sec": round(avg_rps, 1),
                "avg_latency_ms": round(avg_elapsed * 1000 / max(1, avg_rps), 1),
                "iterations": len(c_results),
            })

    output = {
        "benchmark": "streaming",
        "description": "Flink streaming throughput and latency at various parallelism levels",
        "reference": "https://nightlies.apache.org/flink/flink-docs-stable/docs/ops/metrics/",
        "timestamp": timestamp,
        "performance_metrics": {
            "records_per_sec": {"unit": "records/s", "description": "Streaming throughput"},
            "avg_latency_ms": {"unit": "ms", "description": "Average processing latency per record"},
            "elapsed_sec": {"unit": "s", "description": "Total job execution time"},
        },
        "dataset_info": {
            "name": "WordCount streaming",
            "size": "in-memory generated",
            "source": "Flink builtin WordCount.jar example",
        },
        "results": avg_results,
        "raw_results": results,
    }

    out_file = os.path.join(results_dir, "benchmark_streaming.json")
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[STREAMING] Results saved to {out_file}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Flink streaming throughput benchmark")
    parser.add_argument("--flink-home", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    benchmark_streaming_throughput(args.flink_home, args.iterations, args.results_dir)


if __name__ == "__main__":
    main()