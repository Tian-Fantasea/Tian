#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
import datetime


def run_cmd(cmd, timeout=60):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def run_wrk(url, duration, concurrency, threads=None):
    if threads is None:
        threads = min(concurrency, 4)
    cmd = f"wrk -d {duration}s -c {concurrency} -t {threads} --latency {url}"
    out, err, rc = run_cmd(cmd, timeout=duration + 30)
    return out, err, rc


def parse_wrk_output(output):
    result = {
        "rps": 0.0,
        "latency_p50_ms": 0.0,
        "latency_p90_ms": 0.0,
        "latency_p99_ms": 0.0,
        "latency_p999_ms": 0.0,
        "transfer_per_sec_kb": 0.0,
    }
    if not output:
        return result
    for line in output.split("\n"):
        line = line.strip()
        if "requests/sec" in line:
            for p in line.split():
                try:
                    result["rps"] = float(p)
                    break
                except ValueError:
                    continue
        elif "50%" in line and len(line.split()) >= 2:
            val_str = line.split()[1]
            try:
                if "ms" in val_str:
                    result["latency_p50_ms"] = float(val_str.replace("ms", ""))
                elif "us" in val_str:
                    result["latency_p50_ms"] = float(val_str.replace("us", "")) / 1000.0
            except ValueError:
                pass
        elif "90%" in line and len(line.split()) >= 2:
            val_str = line.split()[1]
            try:
                if "ms" in val_str:
                    result["latency_p90_ms"] = float(val_str.replace("ms", ""))
                elif "us" in val_str:
                    result["latency_p90_ms"] = float(val_str.replace("us", "")) / 1000.0
            except ValueError:
                pass
        elif "99%" in line and "99.9%" not in line and len(line.split()) >= 2:
            val_str = line.split()[1]
            try:
                if "ms" in val_str:
                    result["latency_p99_ms"] = float(val_str.replace("ms", ""))
                elif "us" in val_str:
                    result["latency_p99_ms"] = float(val_str.replace("us", "")) / 1000.0
            except ValueError:
                pass
        elif "99.9%" in line and len(line.split()) >= 2:
            val_str = line.split()[1]
            try:
                if "ms" in val_str:
                    result["latency_p999_ms"] = float(val_str.replace("ms", ""))
                elif "us" in val_str:
                    result["latency_p999_ms"] = float(val_str.replace("us", "")) / 1000.0
            except ValueError:
                pass
    return result


def benchmark_tcp_throughput(envoy_port, concurrency_levels, duration, iterations):
    results = []
    for c in concurrency_levels:
        iter_results = []
        for it in range(iterations):
            url = f"http://127.0.0.1:{envoy_port}/"
            out, err, rc = run_wrk(url, duration, c)
            parsed = parse_wrk_output(out)
            parsed["iteration"] = it + 1
            parsed["concurrency"] = c
            iter_results.append(parsed)
        avg_rps = sum(r["rps"] for r in iter_results) / len(iter_results) if iter_results else 0
        avg_p99 = sum(r["latency_p99_ms"] for r in iter_results) / len(iter_results) if iter_results else 0
        results.append({
            "concurrency": c,
            "avg_rps": avg_rps,
            "avg_latency_p99_ms": avg_p99,
            "iterations": iter_results
        })
    return results


def benchmark_latency_percentiles(envoy_port, duration, iterations):
    results = []
    url = f"http://127.0.0.1:{envoy_port}/"
    for it in range(iterations):
        out, err, rc = run_wrk(url, duration, 64)
        parsed = parse_wrk_output(out)
        parsed["iteration"] = it + 1
        results.append(parsed)
    return {
        "p50_values": [r["latency_p50_ms"] for r in results],
        "p90_values": [r["latency_p90_ms"] for r in results],
        "p99_values": [r["latency_p99_ms"] for r in results],
        "p999_values": [r["latency_p999_ms"] for r in results],
        "avg_rps": sum(r["rps"] for r in results) / len(results) if results else 0,
        "iterations": results
    }


def main():
    results_dir = os.environ.get("RESULTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
    envoy_port = int(os.environ.get("ENVOY_PORT", "10000"))
    duration = int(os.environ.get("DURATION", "5"))
    iterations = int(os.environ.get("ITERATIONS", "1"))
    concurrency_str = os.environ.get("CONCURRENCY", "1,16,64")
    concurrency_levels = [int(c) for c in concurrency_str.split(",")]

    if not os.path.isfile("/usr/local/bin/wrk") and not os.path.isfile("/usr/bin/wrk"):
        print("[TCP] wrk not available, generating fallback results")
        fallback = {
            "benchmark": "tcp_proxy",
            "description": "TCP/L4 proxy + latency percentile benchmarks (wrk not available - fallback)",
            "reference": "wrk/wrk2 HTTP load testing, Envoy admin stats API",
            "software": "envoy",
            "version": os.environ.get("SOFTWARE_VERSION", "1.38.2"),
            "architecture": "arm64",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "performance_metrics": {
                "rps": {"unit": "req/sec", "description": "Requests per second"},
                "latency_p99_ms": {"unit": "ms", "description": "99th percentile latency"},
            },
            "dataset_info": {
                "name": "synthetic_tcp_http",
                "size": "variable",
                "source": "local backend server"
            },
            "results": [
                {"test": "tcp_throughput_vs_concurrency", "description": "Fallback", "data": []}
            ]
        }
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, 'benchmark_secondary.json'), 'w') as f:
            json.dump(fallback, f, indent=2)
        print("[TCP] Fallback results saved")
        return

    all_results = {
        "benchmark": "tcp_proxy",
        "description": "TCP/L4 proxy + latency percentile benchmarks",
        "reference": "wrk/wrk2 HTTP load testing, Envoy admin stats API",
        "software": "envoy",
        "version": os.environ.get("SOFTWARE_VERSION", "1.38.2"),
        "architecture": "arm64",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "performance_metrics": {
            "rps": {"unit": "req/sec", "description": "Requests per second"},
            "latency_p50_ms": {"unit": "ms", "description": "50th percentile latency"},
            "latency_p99_ms": {"unit": "ms", "description": "99th percentile latency"},
            "latency_p999_ms": {"unit": "ms", "description": "99.9th percentile latency"},
        },
        "dataset_info": {
            "name": "synthetic_tcp_http",
            "size": "variable",
            "source": "local backend server"
        },
        "results": []
    }

    print("[3b] TCP proxy throughput vs concurrency...")
    tcp_results = benchmark_tcp_throughput(envoy_port, concurrency_levels, duration, iterations)
    all_results["results"].append({
        "test": "tcp_throughput_vs_concurrency",
        "description": "TCP proxy throughput at different concurrency levels",
        "data": tcp_results
    })

    print("[3b] Latency percentile distribution...")
    latency_results = benchmark_latency_percentiles(envoy_port, duration, iterations)
    all_results["results"].append({
        "test": "latency_percentiles",
        "description": "Latency percentile distribution at 64 concurrency",
        "data": latency_results
    })

    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, 'benchmark_secondary.json')
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"[3b] TCP proxy results saved to {output_path}")


if __name__ == '__main__':
    main()
