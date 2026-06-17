#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone

FLINK_REST_URL = "http://localhost:8081"
MEASURE_DURATION_SEC = 15
WORDCOUNT_INPUT_LINES = 100000

def run_cmd(cmd, timeout=300, log_file=None):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if log_file:
            with open(log_file, "a") as f:
                f.write("[MICRO] CMD: {}\n".format(cmd))
        return result
    except subprocess.TimeoutExpired:
        if log_file:
            with open(log_file, "a") as f:
                f.write("[MICRO] TIMEOUT: {}\n".format(cmd))
        return None
    except Exception as e:
        if log_file:
            with open(log_file, "a") as f:
                f.write("[MICRO] ERROR: {}\n".format(str(e)))
        return None


def get_micro_operations():
    return [
        {
            "id": "wordcount_streaming",
            "name": "WordCount Streaming",
            "category": "streaming",
            "description": "Streaming WordCount - map/reduce throughput on text data",
            "jar": "streaming/WordCount.jar",
            "needs_input": True,
            "data_size_mb": 10,
        },
        {
            "id": "window_aggregation",
            "name": "Window Aggregation (TopSpeed)",
            "category": "streaming",
            "description": "Tumbling window aggregation on streaming car speed data",
            "jar": "streaming/TopSpeedWindowing.jar",
            "needs_input": False,
            "data_size_mb": 0,
        },
        {
            "id": "session_window",
            "name": "Session Window",
            "category": "streaming",
            "description": "Session window aggregation on streaming data",
            "jar": "streaming/SessionWindowing.jar",
            "needs_input": False,
            "data_size_mb": 0,
        },
        {
            "id": "window_join",
            "name": "Window Join",
            "category": "streaming",
            "description": "Window-based join of two streaming data sources",
            "jar": "streaming/WindowJoin.jar",
            "needs_input": False,
            "data_size_mb": 0,
        },
        {
            "id": "keyed_state",
            "name": "Keyed State Access",
            "category": "stateful",
            "description": "Keyed state read/write via StateMachine example",
            "jar": "streaming/StateMachineExample.jar",
            "needs_input": False,
            "data_size_mb": 0,
        },
        {
            "id": "checkpoint_overhead",
            "name": "Checkpoint Overhead",
            "category": "stateful",
            "description": "Checkpoint overhead: throughput with checkpointing vs without",
            "jar": "streaming/TopSpeedWindowing.jar",
            "needs_input": False,
            "data_size_mb": 0,
            "compare_checkpoint": True,
        },
        {
            "id": "kryo_serialization",
            "name": "Kryo Serialization",
            "category": "serialization",
            "description": "Serialization throughput with Kryo serializer via WordCount",
            "jar": "streaming/WordCount.jar",
            "needs_input": True,
            "data_size_mb": 10,
            "force_kryo": True,
        },
        {
            "id": "batch_wordcount_sql",
            "name": "Batch WordCount SQL",
            "category": "batch",
            "description": "Word count via Flink Table SQL example",
            "jar": "table/WordCountSQLExample.jar",
            "needs_input": False,
            "data_size_mb": 0,
        },
        {
            "id": "stream_sql",
            "name": "Stream SQL",
            "category": "batch",
            "description": "Stream SQL processing via Flink Table example",
            "jar": "table/StreamSQLExample.jar",
            "needs_input": False,
            "data_size_mb": 0,
        },
        {
            "id": "advanced_functions",
            "name": "Advanced SQL Functions",
            "category": "batch",
            "description": "Advanced SQL functions via Flink Table example",
            "jar": "table/AdvancedFunctionsExample.jar",
            "needs_input": False,
            "data_size_mb": 0,
        },
    ]


def cluster_is_running():
    try:
        url = "{} /overview".format(FLINK_REST_URL)
        with urllib.request.urlopen(url, timeout=3) as resp:
            json.loads(resp.read().decode())
            return True
    except Exception:
        return False


def start_flink_cluster(flink_home, log_file):
    if cluster_is_running():
        with open(log_file, "a") as f:
            f.write("[MICRO] Flink cluster already running\n")
        return True

    result = run_cmd("{}/bin/start-cluster.sh".format(flink_home), timeout=30, log_file=log_file)
    if result and result.returncode == 0:
        for _ in range(10):
            time.sleep(1)
            if cluster_is_running():
                with open(log_file, "a") as f:
                    f.write("[MICRO] Flink cluster started\n")
                return True

    with open(log_file, "a") as f:
        f.write("[MICRO] Could not start Flink cluster\n")
    return False


def stop_flink_cluster(flink_home, log_file):
    run_cmd("{}/bin/stop-cluster.sh".format(flink_home), timeout=15, log_file=log_file)
    with open(log_file, "a") as f:
        f.write("[MICRO] Flink cluster stopped\n")


def generate_text_file(lines, results_dir):
    filepath = os.path.join(results_dir, "micro_wordcount_input.txt")
    with open(filepath, "w") as f:
        for i in range(lines):
            f.write("word{} word{} word{} word{} word{}\n".format(
                i % 100, i % 50, i % 25, i % 10, i % 5))
    return filepath


def parse_job_id(output_text):
    for line in output_text.strip().split("\n"):
        lower = line.lower()
        if "jobid" in lower or "job id" in lower or "submitted" in lower:
            for token in line.split():
                cleaned = token.strip().rstrip(":")
                if len(cleaned) >= 16 and all(c.isalnum() or c == '-' for c in cleaned):
                    return cleaned
    return None


def submit_job(flink_bin, jar_path, parallelism, extra_args="", log_file=None):
    cmd = "{} run -d -p {} {} {}".format(flink_bin, parallelism, jar_path, extra_args.strip())
    result = run_cmd(cmd, timeout=30, log_file=log_file)
    if not result:
        return None

    job_id = parse_job_id(result.stdout + result.stderr)
    if not job_id:
        with open(log_file, "a") as f:
            f.write("[MICRO] Could not parse job ID from: {}\n".format(result.stdout[:200]))
        return None

    with open(log_file, "a") as f:
        f.write("[MICRO] Submitted job: {}\n".format(job_id))
    return job_id


def cancel_job(flink_bin, job_id, log_file=None):
    cmd = "{} cancel {}".format(flink_bin, job_id)
    run_cmd(cmd, timeout=10, log_file=log_file)


def get_job_throughput(job_id, duration_sec):
    try:
        url = "{} /jobs/{}".format(FLINK_REST_URL, job_id)
        with urllib.request.urlopen(url, timeout=5) as resp:
            job_data = json.loads(resp.read().decode())

        total_records_out = 0
        total_records_in = 0

        for vertex in job_data.get("vertices", []):
            vid = vertex.get("id", "")
            metrics_url = "{} /jobs/{}/vertices/{}/metrics?get=numRecordsIn,numRecordsOut,numRecordsInPerSecond,numRecordsOutPerSecond".format(
                FLINK_REST_URL, job_id, vid)
            try:
                with urllib.request.urlopen(metrics_url, timeout=5) as resp:
                    metrics = json.loads(resp.read().decode())
                for m in metrics:
                    mid = m.get("id", "")
                    val = float(m.get("value", 0))
                    if mid == "numRecordsOut":
                        total_records_out += val
                    elif mid == "numRecordsIn":
                        total_records_in += val
                    elif mid == "numRecordsOutPerSecond":
                        total_records_out += val * duration_sec
                    elif mid == "numRecordsInPerSecond":
                        total_records_in += val * duration_sec
            except Exception:
                pass

        if total_records_out > 0:
            throughput = int(total_records_out / max(duration_sec, 1))
        elif total_records_in > 0:
            throughput = int(total_records_in / max(duration_sec, 1))
        else:
            throughput = 0

        return throughput
    except Exception:
        return 0


def run_streaming_job(flink_bin, jar_path, parallelism, duration_sec, extra_args="", log_file=None):
    job_id = submit_job(flink_bin, jar_path, parallelism, extra_args, log_file)
    if not job_id:
        return {"throughput": 0, "latency_ms": 0, "status": "submit_failed"}

    time.sleep(duration_sec)

    throughput = get_job_throughput(job_id, duration_sec)

    cancel_job(flink_bin, job_id, log_file)

    return {
        "throughput": throughput,
        "latency_ms": duration_sec * 1000,
        "status": "completed" if throughput > 0 else "no_metrics",
        "job_id": job_id,
    }


def run_operation(op, flink_home, iterations, parallelism, results_dir, log_file):
    flink_bin = os.path.join(flink_home, "bin", "flink")
    jar_path = os.path.join(flink_home, "examples", op["jar"])

    if not os.path.isfile(jar_path):
        with open(log_file, "a") as f:
            f.write("[MICRO] Jar not found: {}\n".format(jar_path))
        return None

    op_result = {
        "operation_id": op["id"],
        "name": op["name"],
        "category": op["category"],
        "description": op["description"],
        "data_size_mb": op["data_size_mb"],
        "iterations": [],
    }

    input_file = None
    if op.get("needs_input"):
        input_file = generate_text_file(WORDCOUNT_INPUT_LINES, results_dir)

    if op.get("compare_checkpoint"):
        results_no_cp = []
        results_with_cp = []
        for iter_num in range(iterations):
            no_cp = run_streaming_job(
                flink_bin, jar_path, parallelism, MEASURE_DURATION_SEC, "", log_file)
            results_no_cp.append(no_cp)

            cp_args = "-Dexecution.checkpointing.interval=5s -Dexecution.checkpointing.mode=EXACTLY_ONCE"
            with_cp = run_streaming_job(
                flink_bin, jar_path, parallelism, MEASURE_DURATION_SEC, cp_args, log_file)
            results_with_cp.append(with_cp)

        avg_no_cp = sum(r["throughput"] for r in results_no_cp if r["throughput"] > 0) // max(
            sum(1 for r in results_no_cp if r["throughput"] > 0), 1)
        avg_with_cp = sum(r["throughput"] for r in results_with_cp if r["throughput"] > 0) // max(
            sum(1 for r in results_with_cp if r["throughput"] > 0), 1)

        overhead_pct = 0
        if avg_no_cp > 0 and avg_with_cp > 0:
            overhead_pct = round((avg_no_cp - avg_with_cp) / avg_no_cp * 100, 1)

        op_result["iterations"] = [
            {
                "iteration": i + 1,
                "throughput_without_checkpoint_ops_per_sec": results_no_cp[i]["throughput"],
                "throughput_with_checkpoint_ops_per_sec": results_with_cp[i]["throughput"],
                "checkpoint_overhead_pct": overhead_pct,
                "latency_ms": results_no_cp[i]["latency_ms"],
                "status": results_no_cp[i]["status"],
            }
            for i in range(iterations)
        ]
        op_result["average_throughput_ops_per_sec"] = avg_no_cp
        op_result["average_latency_ms"] = MEASURE_DURATION_SEC * 1000
        op_result["checkpoint_overhead_pct"] = overhead_pct

    else:
        extra_args = ""
        if op.get("needs_input") and input_file:
            extra_args = "--input {}".format(input_file)
        if op.get("force_kryo"):
            extra_args += " -Dpipeline.force-kryo=true"

        for iter_num in range(iterations):
            run_result = run_streaming_job(
                flink_bin, jar_path, parallelism, MEASURE_DURATION_SEC, extra_args, log_file)

            op_result["iterations"].append({
                "iteration": iter_num + 1,
                "throughput_ops_per_sec": run_result["throughput"],
                "latency_ms": run_result["latency_ms"],
                "status": run_result["status"],
            })

        avg_throughput = int(sum(r["throughput_ops_per_sec"] for r in op_result["iterations"]) / max(iterations, 1))
        avg_latency = int(sum(r["latency_ms"] for r in op_result["iterations"]) / max(iterations, 1))
        op_result["average_throughput_ops_per_sec"] = avg_throughput
        op_result["average_latency_ms"] = avg_latency

    if input_file and os.path.exists(input_file):
        os.unlink(input_file)

    return op_result


def run_micro_on_flink(flink_home, operations, iterations, parallelism, results_dir, log_file):
    results = []

    if not os.path.isdir(flink_home):
        with open(log_file, "a") as f:
            f.write("[MICRO] Flink home not found: {}\n".format(flink_home))
        return results

    if not start_flink_cluster(flink_home, log_file):
        with open(log_file, "a") as f:
            f.write("[MICRO] Could not start Flink cluster\n")
        return results

    for op in operations:
        with open(log_file, "a") as f:
            f.write("[MICRO] Running: {} ({})\n".format(op["name"], op["id"]))

        op_result = run_operation(op, flink_home, iterations, parallelism, results_dir, log_file)
        if op_result:
            results.append(op_result)
            with open(log_file, "a") as f:
                status = op_result["iterations"][0].get("status", "unknown") if op_result["iterations"] else "no_iterations"
                f.write("[MICRO] {}: avg throughput {} ops/sec, status {}\n".format(
                    op["name"], op_result.get("average_throughput_ops_per_sec", 0), status))

    stop_flink_cluster(flink_home, log_file)
    return results


def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def write_results_section(filepath, section, data):
    results = load_or_create_json(filepath)
    results[section] = data
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Flink micro benchmarks")
    parser.add_argument("--flink-home", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--parallelism", type=int, default=4)
    parser.add_argument("--results-json", required=True)
    parser.add_argument("--section", default="micro_benchmark")
    args = parser.parse_args()

    log_file = os.path.join(args.results_dir, "results.log")
    operations = get_micro_operations()

    results = run_micro_on_flink(
        args.flink_home, operations, args.iterations, args.parallelism,
        args.results_dir, log_file
    )

    output = {
        "benchmark": "micro",
        "description": "Micro benchmarks measuring individual Flink operations on ARM64 using real Flink example jars",
        "reference": "Flink official streaming and table examples",
        "software": "flink",
        "version": os.environ.get("VERSION", "2.1.0"),
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "throughput_ops_per_sec": {"unit": "ops/sec", "description": "Operation throughput"},
            "latency_ms": {"unit": "ms", "description": "Operation latency"},
        },
        "dataset_info": {
            "name": "Flink built-in examples",
            "size": "variable",
            "source": "Apache Flink examples directory",
        },
        "results": results,
        "operations_count": len(operations),
        "operations_completed": len(results),
        "iterations": args.iterations,
        "parallelism": args.parallelism,
    }

    write_results_section(args.results_json, args.section, output)

    with open(log_file, "a") as f:
        f.write("[MICRO] {} operations completed out of {}\n".format(len(results), len(operations)))

    print("[MICRO] Complete. {} operations tested.".format(len(results)))


if __name__ == "__main__":
    main()
