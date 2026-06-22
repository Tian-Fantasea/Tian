#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import datetime
import time

PROTOCOLS = ["baidu_std", "http", "hulu_pbrpc", "sofa_pbrpc"]
PROTOCOL_BENCH_DURATION = 30
PROTOCOL_CONCURRENCY = 64


def find_brpc_binaries():
    search_paths = [
        "/usr/local/bin",
        "/usr/bin",
        "/opt/homebrew/bin",
        os.path.expanduser("~/brpc/output/bin"),
        os.path.expanduser("~/brpc/example"),
    ]
    for env_dir in ["BRPC_HOME", "BRPC_DIR"]:
        env_path = os.environ.get(env_dir)
        if env_path:
            search_paths.append(os.path.join(env_path, "output/bin"))
            search_paths.append(os.path.join(env_path, "example"))

    server_path = None
    client_path = None
    for path in search_paths:
        s = os.path.join(path, "benchmark_server")
        c = os.path.join(path, "benchmark_client")
        if os.path.exists(s) and os.path.isfile(s):
            server_path = s
        if os.path.exists(c) and os.path.isfile(c):
            client_path = c

    return server_path, client_path


def start_benchmark_server(server_path, port=8010):
    cmd = [server_path, f"--port={port}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(3)
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        print(f"[PROTO] Server failed: {stderr[:200]}")
        return None
    print(f"[PROTO] Server started on port {port}")
    return proc


def stop_benchmark_server(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    print("[PROTO] Server stopped")


def run_benchmark_client(client_path, concurrency, duration, port=8010, protocol="baidu_std"):
    cmd = [
        client_path,
        f"--server=127.0.0.1:{port}",
        f"--concurrency={concurrency}",
        f"--duration={duration}",
        f"--protocol={protocol}",
    ]
    if protocol == "http":
        cmd.append("--method=/Echo/Echo")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=duration + 30,
        )
        output = proc.stdout
        metrics = {"protocol": protocol, "concurrency": concurrency}

        m = re.search(r"qps=(\d+)", output)
        if m:
            metrics["qps"] = int(m.group(1))

        m = re.search(r"latency.*?avg=([\d.]+)\s*ms", output)
        if m:
            metrics["avg_latency_ms"] = float(m.group(1))

        m = re.search(r"latency.*?p99=([\d.]+)\s*ms", output)
        if m:
            metrics["p99_latency_ms"] = float(m.group(1))

        m = re.search(r"latency.*?p999=([\d.]+)\s*ms", output)
        if m:
            metrics["p999_latency_ms"] = float(m.group(1))

        m = re.search(r"latency.*?max=([\d.]+)\s*ms", output)
        if m:
            metrics["max_latency_ms"] = float(m.group(1))

        m = re.search(r"error_count=(\d+)", output)
        if m:
            metrics["error_count"] = int(m.group(1))

        metrics["raw_output"] = output[:500] if output else ""
        return metrics

    except subprocess.TimeoutExpired:
        return {"protocol": protocol, "concurrency": concurrency, "error": "timeout"}
    except Exception as e:
        return {"protocol": protocol, "concurrency": concurrency, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="brpc multi-protocol benchmark for ARM64")
    parser.add_argument("--results-json", required=True, help="Path to results.json")
    parser.add_argument("--section", default="protocol_benchmark", help="JSON section name")
    parser.add_argument("--iterations", type=int, default=1, help="Number of iterations")
    args = parser.parse_args()

    work_dir = os.path.dirname(os.path.abspath(args.results_json))
    if not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)

    server_path, client_path = find_brpc_binaries()

    if not server_path or not client_path:
        print("[PROTO] brpc benchmark binaries not found")
        output = {
            "benchmark": "brpc_protocol",
            "description": "brpc multi-protocol comparison benchmark (baidu_std vs HTTP vs hulu_pbrpc vs sofa_pbrpc)",
            "reference": "https://github.com/apache/brpc/tree/master/example",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {
                "qps": {"unit": "requests/sec", "description": "QPS per protocol at fixed concurrency"},
                "latency": {"unit": "milliseconds", "description": "Latency per protocol"},
            },
            "dataset_info": {
                "name": "brpc Echo service (multi-protocol)",
                "size": "1KB payload",
                "source": "brpc built-in benchmark",
            },
            "parameters": {
                "protocols": PROTOCOLS,
                "concurrency": PROTOCOL_CONCURRENCY,
                "duration_sec": PROTOCOL_BENCH_DURATION,
                "iterations": args.iterations,
            },
            "results": {},
            "error": "brpc benchmark binaries not found",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        return 1

    all_results = {}
    server_proc = start_benchmark_server(server_path, port=8010)

    if not server_proc:
        output = {
            "benchmark": "brpc_protocol",
            "description": "brpc multi-protocol comparison benchmark",
            "reference": "https://github.com/apache/brpc/tree/master/example",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {
                "qps": {"unit": "requests/sec", "description": "QPS per protocol"},
                "latency": {"unit": "milliseconds", "description": "Latency per protocol"},
            },
            "dataset_info": {
                "name": "brpc multi-protocol Echo",
                "size": "1KB payload",
                "source": "brpc built-in",
            },
            "parameters": {
                "protocols": PROTOCOLS,
                "concurrency": PROTOCOL_CONCURRENCY,
                "duration_sec": PROTOCOL_BENCH_DURATION,
                "iterations": args.iterations,
            },
            "results": {},
            "error": "benchmark_server failed to start",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        return 1

    try:
        for protocol in PROTOCOLS:
            print(f"[PROTO] Testing protocol={protocol}, concurrency={PROTOCOL_CONCURRENCY}")
            iteration_results = []
            for i in range(args.iterations):
                print(f"[PROTO]   iteration {i+1}/{args.iterations}")
                result = run_benchmark_client(
                    client_path, PROTOCOL_CONCURRENCY, PROTOCOL_BENCH_DURATION,
                    protocol=protocol,
                )
                iteration_results.append(result)

            avg_metrics = {"protocol": protocol, "concurrency": PROTOCOL_CONCURRENCY}
            numeric_keys = ["qps", "avg_latency_ms", "p99_latency_ms", "p999_latency_ms", "max_latency_ms"]
            for key in numeric_keys:
                vals = [r.get(key, 0) for r in iteration_results if isinstance(r.get(key, 0), (int, float)) and r.get(key, 0) > 0]
                if vals:
                    avg_metrics[f"avg_{key}"] = round(sum(vals) / len(vals), 2)

            avg_metrics["iterations"] = args.iterations
            avg_metrics["errors"] = sum(1 for r in iteration_results if "error" in r)
            all_results[protocol] = avg_metrics

            qps = avg_metrics.get("avg_qps", "N/A")
            lat = avg_metrics.get("avg_avg_latency_ms", "N/A")
            print(f"[PROTO] {protocol}: QPS={qps}, avg_lat={lat}ms")

    finally:
        stop_benchmark_server(server_proc)

    output = {
        "benchmark": "brpc_protocol",
        "description": "brpc multi-protocol comparison benchmark (baidu_std, HTTP, hulu_pbrpc, sofa_pbrpc) at concurrency=64 on ARM64",
        "reference": "https://github.com/apache/brpc/tree/master/example",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "qps": {"unit": "requests/sec", "description": "QPS per protocol at fixed concurrency"},
            "latency_avg": {"unit": "milliseconds", "description": "Average latency per protocol"},
            "latency_p99": {"unit": "milliseconds", "description": "P99 latency per protocol"},
        },
        "dataset_info": {
            "name": "brpc Echo service (multi-protocol)",
            "size": "1KB payload",
            "source": "brpc built-in benchmark_server/benchmark_client",
        },
        "parameters": {
            "protocols": PROTOCOLS,
            "concurrency": PROTOCOL_CONCURRENCY,
            "duration_sec": PROTOCOL_BENCH_DURATION,
            "iterations": args.iterations,
        },
        "results": all_results,
    }

    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output),
    ], check=True)

    print("[PROTO] Benchmark complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
