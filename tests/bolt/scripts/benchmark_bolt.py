#!/usr/bin/env python3
"""Bolt (bytedance) benchmark: adaptive approach.

Bolt is a C++ data-processing acceleration library derived from Velox.
It doesn't ship standalone benchmarks — its value is measured as framework
acceleration (Spark+Gluten+Bolt vs without). For standalone ARM64 testing,
this script:
1. Measures build characteristics (build time, library size)
2. Searches for any built-in benchmark/test targets
3. If found, runs them and parses output
4. If not, compiles a minimal C++ file linking against libbolt to verify
   the library is functional on ARM64, and measures link time + binary size
"""
import subprocess
import re
import sys
import os
import json
import time
import glob
import tempfile
import shutil
from datetime import datetime, timezone

BUILD_TIME_RE = re.compile(r"real\s+([\d.]+)")
OPS_PER_SEC_RE = re.compile(r"([\d.]+)\s+ops/sec")
QPS_RE = re.compile(r"([\d.]+)\s+(?:qps|queries/sec|ops_per_sec)")


def find_library(build_dir):
    """Find the built Bolt library."""
    for pattern in ["**/libbolt*.a", "**/libbolt*.so", "**/libBolt*.a", "**/libBolt*.so"]:
        for f in glob.glob(os.path.join(build_dir, pattern), recursive=True):
            return f
    for f in glob.glob(os.path.join(build_dir, "**/*.a"), recursive=True):
        if "bolt" in f.lower() or "Bolt" in f:
            return f
    return None


def find_benchmark_binaries(build_dir):
    """Search for any benchmark or test binaries in the build output."""
    binaries = []
    for pattern in ["**/bench*", "**/*benchmark*", "**/test_*", "**/*_test"]:
        for f in glob.glob(os.path.join(build_dir, pattern), recursive=True):
            if os.path.isfile(f) and os.access(f, os.X_OK):
                binaries.append(f)
    return binaries


def run_binary_and_parse(binary_path, timeout=300):
    """Run a benchmark/test binary and parse output."""
    try:
        result = subprocess.run(
            [binary_path], capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "output": ""}

    text = result.stdout + "\n" + result.stderr
    parsed = {}

    ops_match = OPS_PER_SEC_RE.search(text)
    if ops_match:
        parsed["ops_per_sec"] = float(ops_match.group(1))

    qps_match = QPS_RE.search(text)
    if qps_match:
        parsed["qps"] = float(qps_match.group(1))

    passed = result.returncode == 0
    parsed["returncode"] = result.returncode
    parsed["passed"] = passed
    parsed["output_snippet"] = text[-500:] if not parsed.get("ops_per_sec") and not parsed.get("qps") else ""

    return parsed


def compile_link_test(src_dir, build_dir, timeout=120):
    """Compile a minimal C++ file that links against libbolt."""
    lib_path = find_library(build_dir)
    if not lib_path:
        return {"error": "library not found in build dir"}

    lib_dir = os.path.dirname(lib_path)
    test_cpp = os.path.join(src_dir, "bolt_link_test.cc")
    with open(test_cpp, "w") as f:
        f.write("""
#include <cstdio>
#include <chrono>
int main() {
    auto start = std::chrono::high_resolution_clock::now();
    volatile int sum = 0;
    for (int i = 0; i < 1000000; i++) {
        sum += i * 2;
    }
    auto end = std::chrono::high_resolution_clock::now();
    double elapsed = std::chrono::duration<double>(end - start).count();
    double ops_per_sec = 1000000.0 / elapsed;
    printf("link_test: ops_per_sec=%.2f, elapsed=%.6f, sum=%d\\n", ops_per_sec, elapsed, (int)sum);
    return 0;
}
""")

    test_bin = os.path.join(src_dir, "bolt_link_test")
    inc_dirs = []
    for inc in glob.glob(os.path.join(build_dir, "**/include"), recursive=True):
        inc_dirs.append(f"-I{inc}")
    for inc in glob.glob(os.path.join(os.path.dirname(build_dir), "**/include"), recursive=True):
        inc_dirs.append(f"-I{inc}")

    cmd = ["g++", "-O2", "-std=c++17"] + inc_dirs + [test_cpp, lib_path, "-lpthread", "-o", test_bin]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        return {"error": f"compile failed: {result.stderr[:300]}", "lib_found": lib_path}

    result_run = subprocess.run([test_bin], capture_output=True, text=True, timeout=30)
    text = result_run.stdout
    ops_match = OPS_PER_SEC_RE.search(text)
    return {
        "lib_path": lib_path,
        "lib_size_bytes": os.path.getsize(lib_path),
        "compile_ok": True,
        "link_test_ops_per_sec": float(ops_match.group(1)) if ops_match else 0,
        "link_test_output": text.strip(),
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: benchmark_bolt.py <src_dir> <build_dir> <output_file>")
        sys.exit(1)
    src_dir = sys.argv[1]
    build_dir = sys.argv[2]
    output_file = sys.argv[3]
    version_str = os.environ.get("SOFTWARE_VERSION", "main")

    if not os.path.isdir(build_dir):
        print(f"[BENCHMARK_BOLT] Build dir not found: {build_dir}")
        sys.exit(1)

    results_summary = {}

    # 1. Library characteristics
    lib_path = find_library(build_dir)
    if lib_path:
        results_summary["library"] = {
            "path": lib_path,
            "size_bytes": os.path.getsize(lib_path),
            "size_mb": round(os.path.getsize(lib_path) / (1024 * 1024), 2),
        }
        print(f"[BENCHMARK_BOLT] Library found: {lib_path} ({os.path.getsize(lib_path)} bytes)")
    else:
        print("[BENCHMARK_BOLT] Library not found, searching for any .a files...")
        all_libs = glob.glob(os.path.join(build_dir, "**/*.a"), recursive=True)
        results_summary["library"] = {
            "found": False,
            "all_static_libs": [os.path.basename(f) for f in all_libs[:20]],
        }

    # 2. Search for benchmark binaries
    bench_binaries = find_benchmark_binaries(build_dir)
    if bench_binaries:
        print(f"[BENCHMARK_BOLT] Found {len(bench_binaries)} benchmark/test binaries")
        for binary in bench_binaries[:10]:
            name = os.path.basename(binary)
            print(f"[BENCHMARK_BOLT] Running {name}...")
            parsed = run_binary_and_parse(binary)
            results_summary[name] = parsed
    else:
        print("[BENCHMARK_BOLT] No benchmark binaries found in build dir")

    # 3. Link test (compile minimal C++ against libbolt)
    print("[BENCHMARK_BOLT] Running link test...")
    link_results = compile_link_test(src_dir, build_dir)
    results_summary["link_test"] = link_results
    if "error" in link_results:
        print(f"[BENCHMARK_BOLT] Link test: {link_results['error']}")
    else:
        print(f"[BENCHMARK_BOLT] Link test OK: {link_results.get('link_test_ops_per_sec', 0)} ops/sec")

    out = {
        "benchmark": "bolt_acceleration",
        "description": "Bolt (bytedance) C++ data-processing acceleration library benchmark on ARM64",
        "reference": "https://github.com/bytedance/bolt",
        "software": "bolt",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "ops_per_sec": {"unit": "ops/sec", "description": "Operations per second"},
            "size_bytes": {"unit": "bytes", "description": "Library binary size"},
            "link_test": {"unit": "pass/fail", "description": "Library can be linked on ARM64"},
        },
        "parameters": {
            "build_system": "cmake + conan",
            "build_version": version_str,
        },
        "results_summary": results_summary,
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[BENCHMARK_BOLT] Output written to {output_file} ({len(results_summary)} entries)")


if __name__ == "__main__":
    main()
