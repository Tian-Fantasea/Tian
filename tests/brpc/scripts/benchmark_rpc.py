#!/usr/bin/env python3
"""brpc benchmark: start echo_s++ server, run echo_c++ client, parse QPS + latency.

brpc ships example/echo_c++ (client) + example/echo_s++ (server) as the canonical
RPC echo benchmark pair. The client output includes QPS and latency percentiles.

This script:
1. Starts echo_s++ server in background on a specified port
2. Waits for server to be ready (check HTTP /vars endpoint)
3. Runs echo_c++ client at different thread counts
4. Parses QPS, avg/p50/p90/p99/p999 latency
5. Stops server
"""
import subprocess
import re
import sys
import os
import json
import time
import signal
import tempfile
from datetime import datetime, timezone

THREAD_LEVELS = [1, 4, 16, 32, 64]

QPS_RE = re.compile(r"qps[=\s]+([\d.]+)", re.IGNORECASE)
LAT_AVG_RE = re.compile(r"latency[^=]*=?\s*([\d.]+)\s*(us|ms)", re.IGNORECASE)
LAT_P_RE = re.compile(r"p(\d+)[=\s]+([\d.]+)\s*(us|ms)", re.IGNORECASE)


def start_server(server_bin, port, server_args=None):
    """Start echo_s++ server in background."""
    cmd = [server_bin, "-port", str(port)]
    if server_args:
        cmd.extend(server_args)
    print(f"[BENCHMARK_RPC] Starting echo_s++ on port {port}...")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    # Wait for server to be ready (check HTTP /vars endpoint)
    for _ in range(60):
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", f"http://127.0.0.1:{port}/vars"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                print(f"[BENCHMARK_RPC] Server ready on port {port}")
                return proc
        except Exception:
            pass
        time.sleep(1)
    print(f"[BENCHMARK_RPC] Server did not become ready on port {port}")
    proc.kill()
    return None


def stop_server(proc):
    """Stop the server process."""
    if proc is not None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass


def run_client(client_bin, port, threads, duration=30, extra_args=None):
    """Run echo_c++ client and parse output."""
    cmd = [client_bin, "-server", f"127.0.0.1:{port}", "-num_threads", str(threads), "-duration", str(duration)]
    if extra_args:
        cmd.extend(extra_args)
    print(f"[BENCHMARK_RPC] Running echo_c++ client (threads={threads}, duration={duration}s)...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 60)
    text = result.stdout + "\n" + result.stderr

    parsed = {"qps": 0.0, "avg_latency_us": 0.0, "p50_us": 0.0, "p90_us": 0.0, "p99_us": 0.0, "p999_us": 0.0}

    qps_match = QPS_RE.search(text)
    if qps_match:
        parsed["qps"] = round(float(qps_match.group(1)), 2)

    lat_match = LAT_AVG_RE.search(text)
    if lat_match:
        val = float(lat_match.group(1))
        unit = lat_match.group(2).lower()
        parsed["avg_latency_us"] = round(val * 1000 if unit == "ms" else val, 2)

    for m in LAT_P_RE.finditer(text):
        pct = int(m.group(1))
        val = float(m.group(2))
        unit = m.group(3).lower()
        us_val = round(val * 1000 if unit == "ms" else val, 2)
        if pct == 50:
            parsed["p50_us"] = us_val
        elif pct == 90:
            parsed["p90_us"] = us_val
        elif pct == 99:
            parsed["p99_us"] = us_val
        elif pct == 999:
            parsed["p999_us"] = us_val

    if parsed["qps"] == 0:
        print(f"[BENCHMARK_RPC][DEBUG] threads={threads} parse failed. Raw (last 1000):")
        print(text[-1000:])

    return parsed


def main():
    if len(sys.argv) < 5:
        print("Usage: benchmark_rpc.py <server_bin> <client_bin> <output_file> [duration] [iterations]")
        sys.exit(1)
    server_bin = sys.argv[1]
    client_bin = sys.argv[2]
    output_file = sys.argv[3]
    duration = int(sys.argv[4]) if len(sys.argv) >= 5 else 30
    iterations = int(sys.argv[5]) if len(sys.argv) >= 6 else 1

    if not os.path.exists(server_bin):
        print(f"[BENCHMARK_RPC] echo_s++ not found: {server_bin}")
        sys.exit(1)
    if not os.path.exists(client_bin):
        print(f"[BENCHMARK_RPC] echo_c++ not found: {client_bin}")
        sys.exit(1)

    version_str = os.environ.get("SOFTWARE_VERSION", "1.17.0")
    port = 8200 + os.getpid() % 1000

    proc = start_server(server_bin, port)
    if proc is None:
        sys.exit(1)

    results_summary = {}
    try:
        for threads in THREAD_LEVELS:
            label = f"threads_{threads}"
            runs = []
            for _ in range(iterations):
                r = run_client(client_bin, port, threads, duration)
                runs.append(r)
            avg_qps = round(sum(r["qps"] for r in runs) / len(runs), 2)
            avg_lat = round(sum(r["avg_latency_us"] for r in runs) / len(runs), 2)
            avg_p50 = round(sum(r["p50_us"] for r in runs) / len(runs), 2)
            avg_p90 = round(sum(r["p90_us"] for r in runs) / len(runs), 2)
            avg_p99 = round(sum(r["p99_us"] for r in runs) / len(runs), 2)
            avg_p999 = round(sum(r["p999_us"] for r in runs) / len(runs), 2)
            results_summary[label] = {
                "qps": avg_qps, "avg_latency_us": avg_lat,
                "p50_us": avg_p50, "p90_us": avg_p90,
                "p99_us": avg_p99, "p999_us": avg_p999,
            }
            print(f"  {label}: QPS={avg_qps}, p99={avg_p99}us")
    finally:
        stop_server(proc)

    out = {
        "benchmark": "rpc_echo",
        "description": f"brpc RPC echo benchmark (echo_c++ client → echo_s++ server, {duration}s per test) on ARM64",
        "reference": "https://github.com/apache/brpc",
        "software": "brpc",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "qps": {"unit": "queries/sec", "description": "RPC queries per second"},
            "avg_latency_us": {"unit": "us", "description": "Average RPC latency"},
            "p99_us": {"unit": "us", "description": "99th percentile latency"},
        },
        "parameters": {
            "thread_levels": THREAD_LEVELS,
            "duration_per_test": duration,
            "iterations": iterations,
            "server_port": port,
            "echo_protocol": "brpc baidu_std",
        },
        "results_summary": results_summary,
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[BENCHMARK_RPC] Output written to {output_file} ({len(results_summary)} thread levels)")


if __name__ == "__main__":
    main()
