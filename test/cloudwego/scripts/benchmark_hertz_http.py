#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import signal
import re


DEFAULT_CONCURRENCIES = [50, 100, 200, 400, 800, 1000]
DEFAULT_DURATION = 30
DEFAULT_THREADS = 4


def run_cmd(cmd, timeout=300, cwd=None):
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def build_hertz_benchmark_server(bench_dir):
    server_dir = os.path.join(bench_dir, "server")
    if not os.path.isdir(server_dir):
        print(f"[HERTZ] server dir not found: {server_dir}")
        return None
    server_bin = os.path.join(server_dir, "hertz_echo_server")
    if os.path.exists(server_bin):
        return server_bin
    out, err, rc = run_cmd(
        f"go build -o {server_bin} .",
        cwd=server_dir, timeout=120
    )
    if rc != 0:
        print(f"[HERTZ] Build server failed: {err}")
        return None
    return server_bin


def start_server(server_bin, port=8000, cpu_set="0-3"):
    if not os.path.exists(server_bin):
        return None
    cmd = f"taskset -c {cpu_set} {server_bin} -port {port}"
    proc = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        preexec_fn=os.setsid
    )
    time.sleep(2)
    return proc


def stop_server(proc):
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def parse_wrk_output(output):
    result = {}
    lines = output.strip().split("\n")
    for line in lines:
        line = line.strip()
        if "requests/sec" in line.lower() or "Requests/sec" in line:
            match = re.search(r"([\d,.]+)\s*requests/sec", line, re.IGNORECASE)
            if match:
                result["qps"] = float(match.group(1).replace(",", ""))
        elif "Transfer/sec" in line or "transfer/sec" in line.lower():
            match = re.search(r"([\d.]+\s*[KMGB]?)\s*transfer/sec", line, re.IGNORECASE)
            if match:
                result["transfer_rate"] = match.group(1)
        elif "Latency" in line and "Stdev" not in line and "Max" not in line:
            match = re.search(r"([\d.]+)\s*(us|ms|s)", line, re.IGNORECASE)
            if match:
                val = float(match.group(1))
                unit = match.group(2).lower()
                if unit == "us":
                    result["avg_latency_us"] = val
                    result["avg_latency_ms"] = round(val / 1000, 3)
                elif unit == "ms":
                    result["avg_latency_ms"] = val
                elif unit == "s":
                    result["avg_latency_ms"] = round(val * 1000, 2)
        elif "50%" in line or "p50" in line.lower():
            match = re.search(r"([\d.]+)\s*(us|ms|s)", line, re.IGNORECASE)
            if match:
                val, unit = float(match.group(1)), match.group(2).lower()
                result["p50_latency_ms"] = round(val / 1000 if unit == "us" else val if unit == "ms" else val * 1000, 3)
        elif "75%" in line:
            match = re.search(r"([\d.]+)\s*(us|ms|s)", line, re.IGNORECASE)
            if match:
                val, unit = float(match.group(1)), match.group(2).lower()
                result["p75_latency_ms"] = round(val / 1000 if unit == "us" else val if unit == "ms" else val * 1000, 3)
        elif "90%" in line:
            match = re.search(r"([\d.]+)\s*(us|ms|s)", line, re.IGNORECASE)
            if match:
                val, unit = float(match.group(1)), match.group(2).lower()
                result["p90_latency_ms"] = round(val / 1000 if unit == "us" else val if unit == "ms" else val * 1000, 3)
        elif "99%" in line:
            match = re.search(r"([\d.]+)\s*(us|ms|s)", line, re.IGNORECASE)
            if match:
                val, unit = float(match.group(1)), match.group(2).lower()
                result["p99_latency_ms"] = round(val / 1000 if unit == "us" else val if unit == "ms" else val * 1000, 3)
        elif "Socket errors" in line:
            result["errors"] = line
    return result


def run_wrk_benchmark(server_proc, duration, concurrencies, threads):
    all_results = []
    for conc in concurrencies:
        print(f"[HERTZ] Running wrk with concurrency={conc}, threads={threads}, duration={duration}s")
        cmd = f"taskset -c 4-19 wrk -t{threads} -c{conc} -d{duration}s http://127.0.0.1:8000/"
        out, err, rc = run_cmd(cmd, timeout=duration + 30)
        if rc == 0 and out:
            parsed = parse_wrk_output(out)
            if parsed:
                parsed["concurrency"] = conc
                parsed["threads"] = threads
                parsed["duration_sec"] = duration
                all_results.append(parsed)
        else:
            print(f"[HERTZ] wrk failed at conc={conc}: {err[:200]}")
    return all_results


def run_hertz_go_benchmark(iterations):
    print("[HERTZ] Using Go testing benchmark (built-in) for Hertz...")
    all_results = []
    bench_cmds = [
        ("Hertz_Echo_Netpoll", "github.com/cloudwego/hertz/pkg/app/server"),
        ("Hertz_Binding_JSON", "github.com/cloudwego/hertz/pkg/app"),
    ]
    for bench_name, pkg in bench_cmds:
        for iter_num in range(1, iterations + 1):
            print(f"[HERTZ] {bench_name} iteration {iter_num}/{iterations}")
            cmd = f"go test -bench=Benchmark -benchmem -count=1 {pkg}"
            out, err, rc = run_cmd(cmd, timeout=300)
            if rc == 0 and out:
                for line in out.split("\n"):
                    if "Benchmark" in line and "ns/op" in line:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            name = parts[0]
                            try:
                                ns_per_op = float(parts[2].replace("ns/op", ""))
                                ops_per_sec = 1e9 / ns_per_op if ns_per_op > 0 else 0
                                all_results.append({
                                    "operation": name,
                                    "ns_per_op": ns_per_op,
                                    "ops_per_sec": round(ops_per_sec, 2),
                                })
                            except ValueError:
                                continue
    return all_results


def main():
    parser = argparse.ArgumentParser(description="Hertz HTTP throughput/latency benchmark")
    parser.add_argument('--results-json', required=True)
    parser.add_argument('--section', default='hertz_benchmark')
    parser.add_argument('--hertz-bench-dir', required=True)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--data-scale', type=int, default=1)
    args = parser.parse_args()

    bench_dir = args.hertz_bench_dir
    iterations = args.iterations
    duration = DEFAULT_DURATION * args.data_scale
    concurrencies = DEFAULT_CONCURRENCIES[:3] if args.data_scale == 1 else DEFAULT_CONCURRENCIES

    server_bin = build_hertz_benchmark_server(bench_dir)
    server_proc = None
    results = []

    try:
        if server_bin:
            server_proc = start_server(server_bin, port=8000, cpu_set="0-3")
            if server_proc:
                for iter_num in range(1, iterations + 1):
                    print(f"[HERTZ] Iteration {iter_num}/{iterations}")
                    iter_results = run_wrk_benchmark(
                        server_proc, duration, concurrencies,
                        DEFAULT_THREADS
                    )
                    for r in iter_results:
                        r["iteration"] = iter_num
                    results.extend(iter_results)
            else:
                print("[HERTZ] Server failed to start, using Go built-in benchmark")
                results = run_hertz_go_benchmark(iterations)
        else:
            print("[HERTZ] No server binary, using Go built-in benchmark")
            results = run_hertz_go_benchmark(iterations)
    finally:
        stop_server(server_proc)

    output = {
        "benchmark": "hertz_http_throughput_latency",
        "description": "Hertz HTTP framework throughput and latency benchmark using wrk load generator (Echo scenario)",
        "reference": "https://github.com/cloudwego/hertz-benchmark",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "performance_metrics": {
            "qps": {"unit": "requests/sec", "description": "HTTP throughput in requests per second"},
            "avg_latency_ms": {"unit": "ms", "description": "Average HTTP request latency"},
            "p99_latency_ms": {"unit": "ms", "description": "P99 HTTP request latency"},
            "p50_latency_ms": {"unit": "ms", "description": "P50 (median) HTTP request latency"},
        },
        "dataset_info": {
            "name": "echo_payload",
            "size": "~1KB",
            "source": "hertz-benchmark Echo scenario",
        },
        "results": results,
    }
    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output)
    ], check=True)


if __name__ == "__main__":
    main()
