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
        "latency_avg_ms": 0.0,
        "latency_p50_ms": 0.0,
        "latency_p90_ms": 0.0,
        "latency_p99_ms": 0.0,
        "latency_p999_ms": 0.0,
        "latency_max_ms": 0.0,
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
        elif "Transfer/sec" in line:
            for p in line.split():
                try:
                    result["transfer_per_sec_kb"] = float(p)
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
        elif "Latency" in line and "avg" not in line.lower() and "max" not in line.lower() and "stdev" not in line.lower():
            parts = line.split()
            if len(parts) >= 2:
                val_str = parts[1]
                try:
                    if "ms" in val_str:
                        result["latency_avg_ms"] = float(val_str.replace("ms", ""))
                    elif "us" in val_str:
                        result["latency_avg_ms"] = float(val_str.replace("us", "")) / 1000.0
                except ValueError:
                    pass
    return result


def benchmark_rps_vs_concurrency(envoy_port, concurrency_levels, duration, iterations):
    url = f"http://127.0.0.1:{envoy_port}/"
    results = []
    for c in concurrency_levels:
        iter_results = []
        for it in range(iterations):
            out, err, rc = run_wrk(url, duration, c)
            parsed = parse_wrk_output(out)
            parsed["iteration"] = it + 1
            parsed["concurrency"] = c
            iter_results.append(parsed)
        avg_rps = sum(r["rps"] for r in iter_results) / len(iter_results)
        avg_p50 = sum(r["latency_p50_ms"] for r in iter_results) / len(iter_results)
        avg_p99 = sum(r["latency_p99_ms"] for r in iter_results) / len(iter_results)
        results.append({
            "concurrency": c,
            "avg_rps": avg_rps,
            "avg_latency_p50_ms": avg_p50,
            "avg_latency_p99_ms": avg_p99,
            "iterations": iter_results
        })
    return results


def benchmark_response_sizes(envoy_port, data_size, duration, iterations):
    sizes = [data_size, data_size * 10, data_size * 100]
    results = []
    for sz in sizes:
        url = f"http://127.0.0.1:{envoy_port}/?size={sz}"
        iter_results = []
        for it in range(iterations):
            out, err, rc = run_wrk(url, duration, 64)
            parsed = parse_wrk_output(out)
            parsed["iteration"] = it + 1
            parsed["response_size_bytes"] = sz
            iter_results.append(parsed)
        avg_rps = sum(r["rps"] for r in iter_results) / len(iter_results) if iter_results else 0
        avg_p99 = sum(r["latency_p99_ms"] for r in iter_results) / len(iter_results) if iter_results else 0
        results.append({
            "response_size_bytes": sz,
            "avg_rps": avg_rps,
            "avg_latency_p99_ms": avg_p99,
            "iterations": iter_results
        })
    return results


def main():
    results_dir = os.environ.get("RESULTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
    envoy_port = int(os.environ.get("ENVOY_PORT", "10000"))
    backend_port = int(os.environ.get("BACKEND_PORT", "8080"))
    duration = int(os.environ.get("DURATION", "5"))
    iterations = int(os.environ.get("ITERATIONS", "1"))
    concurrency_str = os.environ.get("CONCURRENCY", "1,16,64")
    data_size = int(os.environ.get("DATA_SIZE", "1000"))
    concurrency_levels = [int(c) for c in concurrency_str.split(",")]

    if not os.path.isfile("/usr/local/bin/wrk") and not os.path.isfile("/usr/bin/wrk"):
        print("[HTTP] wrk not available, generating fallback results")
        fallback = {
            "benchmark": "http_proxy",
            "description": "HTTP/L7 proxy performance benchmarks (wrk not available - fallback)",
            "reference": "wrk/wrk2 industry-standard HTTP load testing (https://github.com/giltene/wrk2)",
            "software": "envoy",
            "version": os.environ.get("SOFTWARE_VERSION", "1.38.2"),
            "architecture": "arm64",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "performance_metrics": {
                "rps": {"unit": "req/sec", "description": "Requests per second throughput"},
                "latency_p50_ms": {"unit": "ms", "description": "50th percentile latency"},
                "latency_p99_ms": {"unit": "ms", "description": "99th percentile latency"},
            },
            "dataset_info": {
                "name": "synthetic_http_responses",
                "size": f"{data_size} bytes",
                "source": "local backend server"
            },
            "results_summary": {
                "rps_vs_concurrency": [
                    {"concurrency": c, "avg_rps": 0, "avg_latency_p99_ms": 0} for c in concurrency_levels
                ]
            },
            "results": [
                {"test": "rps_vs_concurrency", "description": "Fallback - wrk not available", "data": []}
            ]
        }
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, 'benchmark_primary.json'), 'w') as f:
            json.dump(fallback, f, indent=2)
        print("[HTTP] Fallback results saved")
        return

    all_results = {
        "benchmark": "http_proxy",
        "description": "HTTP/L7 proxy performance benchmarks using wrk",
        "reference": "wrk/wrk2 industry-standard HTTP load testing (https://github.com/giltene/wrk2)",
        "software": "envoy",
        "version": os.environ.get("SOFTWARE_VERSION", "1.38.2"),
        "architecture": "arm64",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "performance_metrics": {
            "rps": {"unit": "req/sec", "description": "Requests per second throughput"},
            "latency_p50_ms": {"unit": "ms", "description": "50th percentile latency"},
            "latency_p99_ms": {"unit": "ms", "description": "99th percentile latency"},
            "latency_p999_ms": {"unit": "ms", "description": "99.9th percentile latency"},
        },
        "dataset_info": {
            "name": "synthetic_http_responses",
            "size": f"{data_size} bytes",
            "source": "local backend server"
        },
        "results": []
    }

    print("[3a] RPS vs Concurrency scaling...")
    rps_results = benchmark_rps_vs_concurrency(envoy_port, concurrency_levels, duration, iterations)
    all_results["results"].append({
        "test": "rps_vs_concurrency",
        "description": "HTTP RPS at different concurrency levels",
        "data": rps_results
    })
    all_results["results_summary"] = {"rps_vs_concurrency": rps_results}

    print("[3a] Response size impact...")
    size_results = benchmark_response_sizes(envoy_port, data_size, duration, iterations)
    all_results["results"].append({
        "test": "response_size_impact",
        "description": "HTTP RPS and latency for different response sizes",
        "data": size_results
    })

    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, 'benchmark_primary.json')
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"[3a] HTTP proxy results saved to {output_path}")


if __name__ == '__main__':
    main()
