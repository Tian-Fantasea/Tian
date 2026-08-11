#!/usr/bin/env python3
"""brpc micro: payload size sweep + connection count sweep."""
import subprocess
import re
import sys
import os
import json
import time
import signal
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_rpc import start_server, stop_server, run_client, QPS_RE, LAT_P_RE

PAYLOAD_SIZES = [64, 256, 1024, 4096]
CONNECTION_COUNTS = [1, 10, 50, 100]


def bench_payload_sweep(client_bin, port, duration, iterations):
    results = {}
    for ps in PAYLOAD_SIZES:
        label = f"payload_{ps}"
        runs = []
        for _ in range(iterations):
            cmd = [client_bin, "-server", f"127.0.0.1:{port}", "-num_threads", "32", "-duration", str(duration)]
            r = {"qps": 0.0, "p99_us": 0.0}
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 60)
            text = result.stdout + "\n" + result.stderr
            qps_match = QPS_RE.search(text)
            if qps_match:
                r["qps"] = round(float(qps_match.group(1)), 2)
            for m in LAT_P_RE.finditer(text):
                if int(m.group(1)) == 99:
                    val = float(m.group(2))
                    unit = m.group(3).lower()
                    r["p99_us"] = round(val * 1000 if unit == "ms" else val, 2)
            runs.append(r)
        avg_qps = round(sum(r["qps"] for r in runs) / len(runs), 2)
        avg_p99 = round(sum(r["p99_us"] for r in runs) / len(runs), 2)
        results[label] = {"qps": avg_qps, "p99_us": avg_p99}
        print(f"[MICRO] {label}: QPS={avg_qps}, p99={avg_p99}us")
    return results


def bench_connection_sweep(client_bin, port, duration, iterations):
    results = {}
    for cc in CONNECTION_COUNTS:
        label = f"connections_{cc}"
        runs = []
        for _ in range(iterations):
            cmd = [client_bin, "-server", f"127.0.0.1:{port}", "-num_threads", "32", "-duration", str(duration), "-connection_count", str(cc)]
            r = {"qps": 0.0}
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 60)
            text = result.stdout + "\n" + result.stderr
            qps_match = QPS_RE.search(text)
            if qps_match:
                r["qps"] = round(float(qps_match.group(1)), 2)
            runs.append(r)
        avg_qps = round(sum(r["qps"] for r in runs) / len(runs), 2)
        results[label] = {"qps": avg_qps}
        print(f"[MICRO] {label}: QPS={avg_qps}")
    return results


def main():
    if len(sys.argv) < 5:
        print("Usage: micro_benchmark.py <server_bin> <client_bin> <output_file> [duration] [iterations]")
        sys.exit(1)
    server_bin = sys.argv[1]
    client_bin = sys.argv[2]
    output_file = sys.argv[3]
    duration = int(sys.argv[4]) if len(sys.argv) >= 5 else 15
    iterations = int(sys.argv[5]) if len(sys.argv) >= 6 else 1
    version_str = os.environ.get("SOFTWARE_VERSION", "1.17.0")
    port = 8300 + os.getpid() % 1000

    proc = start_server(server_bin, port)
    if proc is None:
        sys.exit(1)

    try:
        print("[MICRO] Running payload_sweep...")
        ps_results = bench_payload_sweep(client_bin, port, duration, iterations)
        print("[MICRO] Running connection_sweep...")
        cc_results = bench_connection_sweep(client_bin, port, duration, iterations)
    finally:
        stop_server(proc)

    out = {
        "benchmark": "micro_operations",
        "description": f"brpc micro: payload size sweep + connection count sweep on ARM64",
        "reference": "https://github.com/apache/brpc",
        "software": "brpc",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "qps": {"unit": "queries/sec", "description": "RPC queries per second"},
            "p99_us": {"unit": "us", "description": "99th percentile latency"},
        },
        "parameters": {
            "payload_sizes": PAYLOAD_SIZES,
            "connection_counts": CONNECTION_COUNTS,
            "duration_per_test": duration,
            "iterations": iterations,
        },
        "results": {
            "payload_sweep": ps_results,
            "connection_sweep": cc_results,
        },
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[MICRO] Output written to {output_file}")


if __name__ == "__main__":
    main()
