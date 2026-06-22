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


def check_arm64_crypto():
    out, _ = run_cmd("cat /proc/cpuinfo 2>/dev/null | grep 'Features' | head -1")
    has_aes = "aes" in out.lower()
    has_sha1 = "sha1" in out.lower()
    has_sha2 = "sha2" in out.lower()
    has_pmull = "pmull" in out.lower()
    has_crc32 = "crc32" in out.lower()
    has_neon = "neon" in out.lower() or "asimd" in out.lower()
    return {
        "aes": has_aes,
        "sha1": has_sha1,
        "sha2": has_sha2,
        "pmull": has_pmull,
        "crc32": has_crc32,
        "neon": has_neon,
        "arm64_crypto_extensions_available": has_aes or has_sha1 or has_sha2
    }


def benchmark_memory_footprint(envoy_bin, envoy_port):
    results = {
        "initial_memory_mb": 0.0,
        "peak_memory_mb": 0.0,
        "after_load_memory_mb": 0.0,
    }
    out, _, rc = run_cmd("ps aux | grep envoy | grep -v grep | head -1 | tr -s ' ' | cut -d' ' -f6")
    try:
        results["initial_memory_mb"] = float(out) / 1024.0 if out else 0.0
    except ValueError:
        pass
    results["peak_memory_mb"] = max(results["initial_memory_mb"], results["after_load_memory_mb"])
    return results


def benchmark_envoy_stats(admin_port):
    try:
        import urllib.request
        url = f"http://127.0.0.1:{admin_port}/stats?format=json"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read().decode())
        stats = {}
        for s in data.get("stats", []):
            name = s.get("name", "")
            value = s.get("value", "")
            if "downstream_cx" in name or "upstream_cx" in name or "rq" in name:
                try:
                    stats[name] = int(value) if "." not in value else float(value)
                except (ValueError, TypeError):
                    pass
        return stats
    except Exception:
        return {}


def main():
    results_dir = os.environ.get("RESULTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
    envoy_bin = os.environ.get("ENVOY_BIN", "/usr/local/bin/envoy")
    envoy_port = int(os.environ.get("ENVOY_PORT", "10000"))
    admin_port = int(os.environ.get("ENVOY_ADMIN_PORT", "9901"))
    software_version = os.environ.get("SOFTWARE_VERSION", "1.38.2")

    all_results = {
        "benchmark": "micro_operations",
        "description": "Micro benchmarks: ARM64 crypto detection, Envoy stats, memory footprint",
        "reference": "Envoy BoringSSL ARM64 AES/SHA acceleration, wrk HTTP load testing",
        "software": "envoy",
        "version": software_version,
        "architecture": "arm64",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "performance_metrics": {
            "memory_mb": {"unit": "MB", "description": "Memory footprint"},
            "arm64_crypto": {"unit": "boolean", "description": "ARM64 cryptographic extension availability"},
        },
        "dataset_info": {
            "name": "envoy_runtime_stats",
            "size": "variable",
            "source": "Envoy admin API + /proc/cpuinfo"
        },
        "results": []
    }

    print("[3c] ARM64 crypto detection...")
    crypto_info = check_arm64_crypto()
    all_results["results"].append({
        "test": "arm64_crypto_detection",
        "description": "ARM64 cryptographic extension detection for TLS acceleration",
        "data": crypto_info
    })

    print("[3c] Envoy admin stats snapshot...")
    stats = benchmark_envoy_stats(admin_port)
    all_results["results"].append({
        "test": "envoy_stats",
        "description": "Envoy admin interface stats snapshot",
        "data": stats
    })

    print("[3c] Memory footprint...")
    memory_results = benchmark_memory_footprint(envoy_bin, envoy_port)
    all_results["results"].append({
        "test": "memory_footprint",
        "description": "Envoy memory usage baseline",
        "data": memory_results
    })

    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, 'micro_benchmark.json')
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"[3c] Micro benchmark results saved to {output_path}")


if __name__ == '__main__':
    main()
