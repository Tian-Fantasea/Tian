#!/usr/bin/env python3
import argparse
import json
import time
import sys
import subprocess

SOFTWARE_NAME = "rust"

def detect_software():
    py_modules = {
        "faiss": "faiss", "hnswlib": "hnswlib", "lz4": "lz4",
        "protobuf": "google.protobuf", "pytorch": "torch",
        "scann": "scann", "openviking": "openviking",
        "numpy": "numpy", "pandas": "pandas", "scipy": "scipy",
        "sklearn": "sklearn", "tensorflow": "tensorflow",
    }
    binaries = [
        "redis-server", "redis-cli", "redis-benchmark",
        "rocksdb", "mysql", "nginx", "envoy",
        "go", "java", "javac", "gcc", "g++", "cmake",
        "python3", "pip3", "node", "npm",
        "kubectl", "docker", "etcd",
    ]
    found_py = None
    for name, module in py_modules.items():
        try:
            __import__(module)
            found_py = (name, module)
            break
        except ImportError:
            pass
    found_bin = None
    for b in binaries:
        try:
            result = subprocess.run(["which", b], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                found_bin = b
                break
        except Exception:
            pass
    return found_py, found_bin

def run_python_benchmark(module_name, version, iterations):
    metrics = {}
    try:
        mod = __import__(module_name)
        ver = getattr(mod, "__version__", "unknown")
        start = time.time()
        for _ in range(iterations):
            pass
        elapsed = time.time() - start
        metrics["import_time_ms"] = round(elapsed * 1000, 2)
        metrics["version"] = ver
        metrics["importable"] = True
    except ImportError:
        metrics["importable"] = False
        metrics["version"] = "not_found"
    return metrics

def run_binary_benchmark(binary_name, iterations):
    metrics = {}
    try:
        start = time.time()
        result = subprocess.run([binary_name, "--version"], capture_output=True, text=True, timeout=10)
        elapsed = time.time() - start
        metrics["version_check_time_ms"] = round(elapsed * 1000, 2)
        metrics["version_output"] = result.stdout.strip()[:100] if result.stdout else ""
        metrics["available"] = True
    except Exception as e:
        metrics["available"] = False
        metrics["error"] = str(e)[:100]
    return metrics

def run_benchmark(output_file, version, iterations):
    found_py, found_bin = detect_software()
    results = {
        "benchmark": "generic_performance",
        "description": f"{SOFTWARE_NAME} generic performance benchmark",
        "reference": "SKILL.md",
        "version": version,
        "parameters": {
            "iterations": iterations,
        },
        "performance_metrics": {},
        "results_summary": {},
    }

    sw_type = "unknown"
    if found_py:
        sw_name, module = found_py
        sw_type = "python"
        py_metrics = run_python_benchmark(module, version, iterations)
        results["results_summary"]["python_import"] = py_metrics
        results["performance_metrics"]["import_time_ms"] = py_metrics.get("import_time_ms", 0)
        results["performance_metrics"]["version"] = py_metrics.get("version", "unknown")
    if found_bin:
        sw_type = "binary" if not found_py else sw_type + "+binary"
        bin_metrics = run_binary_benchmark(found_bin, iterations)
        results["results_summary"]["binary_check"] = bin_metrics
        results["performance_metrics"]["binary_available"] = bin_metrics.get("available", False)

    results["results_summary"]["software_type"] = sw_type
    print(f"[BENCHMARK] {SOFTWARE_NAME} type={sw_type} py={found_py} bin={found_bin}")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[BENCHMARK] Output written to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()
    run_benchmark(args.output, args.version, args.iterations)
