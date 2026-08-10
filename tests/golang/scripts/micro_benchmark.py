#!/usr/bin/env python3
import subprocess
import re
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_go import run_go_bench, PACKAGES

BENCH_RE = re.compile(
    r"^(Benchmark[\w/]+)(?:-(\d+))?\s+(\d+)\s+([\d.]+)\s+ns/op",
    re.MULTILINE
)

THREAD_LEVELS = [1, 2, 4, 8, "all"]


def get_max_threads():
    try:
        return int(os.cpu_count() or 4)
    except Exception:
        return 4


def bench_thread_scaling(goroot, iterations):
    max_threads = get_max_threads()
    cpu_list = ",".join(str(t if t != "all" else max_threads) for t in THREAD_LEVELS)
    benchtime = os.environ.get("BENCH_TIME", "1x")
    results = {}
    for pkg in ["encoding/json", "strconv", "crypto/sha256"]:
        for _ in range(iterations):
            env = os.environ.copy()
            env["GOROOT"] = goroot
            env["PATH"] = os.path.join(goroot, "bin") + ":" + env.get("PATH", "")
            env["CGO_ENABLED"] = "0"
            env["GOPATH"] = "/tmp/go_bench_gopath"

            src_dir = os.path.join(goroot, "src", pkg)
            if not os.path.isdir(src_dir):
                continue
            cmd = [
                os.path.join(goroot, "bin", "go"),
                "test", "-bench=.", "-benchmem", "-count=1",
                "-run=^$", "-timeout=300s", f"-cpu={cpu_list}",
                f"-benchtime={benchtime}",
            ]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=src_dir, env=env,
            )
            try:
                stdout_data, stderr_data = proc.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_data, stderr_data = proc.communicate()
                print(f"[MICRO][WARN] timeout for {pkg}, using partial output")
            text = stdout_data + "\n" + stderr_data
            for m in BENCH_RE.finditer(text):
                name = m.group(1)
                cpu = int(m.group(2)) if m.group(2) else 1
                ns = float(m.group(4))
                ops = round(1e9 / ns, 2) if ns > 0 else 0
                key = f"{name}"
                if key not in results:
                    results[key] = {}
                results[key][f"cpu_{cpu}"] = {"ns_per_op": round(ns, 2), "ops_per_sec": ops}
            print(f"[MICRO] {pkg} done")
    return results


def main():
    if len(sys.argv) < 4:
        print("Usage: micro_benchmark.py <goroot> <output_file> [iterations]")
        sys.exit(1)
    goroot = sys.argv[1]
    output_file = sys.argv[2]
    iterations = int(sys.argv[3]) if len(sys.argv) >= 4 else 1

    version_str = os.environ.get("SOFTWARE_VERSION", "go1.26.5")
    max_threads = get_max_threads()

    print("[MICRO] Running thread_scaling...")
    ts_results = bench_thread_scaling(goroot, iterations)

    out = {
        "benchmark": "micro_operations",
        "description": f"Go micro: GOMAXPROCS thread scaling (cpu={THREAD_LEVELS}) on ARM64",
        "reference": "https://github.com/golang/go",
        "software": "golang",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "ns_per_op": {"unit": "ns", "description": "Nanoseconds per operation"},
            "ops_per_sec": {"unit": "ops/sec", "description": "Operations per second"},
        },
        "parameters": {
            "thread_levels": THREAD_LEVELS,
            "max_threads": max_threads,
            "iterations": iterations,
            "packages": ["encoding/json", "strconv", "crypto/sha256"],
            "benchtime": os.environ.get("BENCH_TIME", "1x"),
        },
        "results": {
            "thread_scaling": ts_results,
        },
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[MICRO] Output written to {output_file}")


if __name__ == "__main__":
    main()
