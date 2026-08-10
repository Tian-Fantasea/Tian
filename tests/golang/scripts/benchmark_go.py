#!/usr/bin/env python3
import subprocess
import re
import sys
import os
import json
from datetime import datetime, timezone

PACKAGES = [
    "encoding/json",
    "strconv",
    "crypto/sha256",
    "bytes",
    "strings",
    "math",
]

BENCH_RE = re.compile(
    r"^(Benchmark[\w/]+)(?:-\d+)?\s+(\d+)\s+([\d.]+)\s+ns/op"
    r"(?:\s+([\d.]+)\s+MB/s)?"
    r"(?:\s+([\d.]+)\s+B/op)?"
    r"(?:\s+([\d.]+)\s+allocs/op)?",
    re.MULTILINE
)


def run_go_bench(goroot, pkg, cpu_list="1"):
    src_dir = os.path.join(goroot, "src", pkg)
    if not os.path.isdir(src_dir):
        print(f"[BENCHMARK_GO] Package dir not found: {src_dir}")
        return []

    env = os.environ.copy()
    env["GOROOT"] = goroot
    env["PATH"] = os.path.join(goroot, "bin") + ":" + env.get("PATH", "")
    env["CGO_ENABLED"] = "0"
    env["GOPATH"] = "/tmp/go_bench_gopath"

    benchtime = os.environ.get("BENCH_TIME", "1x")
    cmd = [
        os.path.join(goroot, "bin", "go"),
        "test",
        f"-bench=.",
        "-benchmem",
        f"-count=1",
        "-run=^$",
        "-timeout=300s",
        f"-benchtime={benchtime}",
    ]
    if cpu_list:
        cmd.append(f"-cpu={cpu_list}")

    print(f"[BENCHMARK_GO] Running go test -bench in {pkg} (cpu={cpu_list}, benchtime={benchtime})...")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=src_dir, env=env,
    )
    try:
        stdout_data, stderr_data = proc.communicate(timeout=360)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout_data, stderr_data = proc.communicate()
        print(f"[BENCHMARK_GO][WARN] go test timed out for {pkg}, using partial output")
    text = stdout_data + "\n" + stderr_data
    if proc.returncode != 0:
        print(f"[BENCHMARK_GO][DEBUG] go test failed for {pkg}: {stderr_data[:500]}")

    benchmarks = []
    for m in BENCH_RE.finditer(text):
        name = m.group(1)
        iterations = int(m.group(2))
        ns_per_op = float(m.group(3))
        mb_per_sec = float(m.group(4)) if m.group(4) else 0.0
        b_per_op = float(m.group(5)) if m.group(5) else 0.0
        allocs = float(m.group(6)) if m.group(6) else 0.0
        ops_per_sec = round(1e9 / ns_per_op, 2) if ns_per_op > 0 else 0
        benchmarks.append({
            "name": name,
            "package": pkg,
            "iterations": iterations,
            "ns_per_op": round(ns_per_op, 2),
            "ops_per_sec": ops_per_sec,
            "mb_per_sec": round(mb_per_sec, 2),
            "bytes_per_op": round(b_per_op, 2),
            "allocs_per_op": round(allocs, 2),
        })
    return benchmarks


def main():
    if len(sys.argv) < 4:
        print("Usage: benchmark_go.py <goroot> <output_file> [iterations]")
        sys.exit(1)
    goroot = sys.argv[1]
    output_file = sys.argv[2]
    iterations = int(sys.argv[3]) if len(sys.argv) >= 4 else 1

    if not os.path.exists(os.path.join(goroot, "bin", "go")):
        print(f"[BENCHMARK_GO] go binary not found at {goroot}/bin/go")
        sys.exit(1)

    version_str = os.environ.get("SOFTWARE_VERSION", "go1.26.5")
    all_results = {}

    for pkg in PACKAGES:
        runs = []
        for _ in range(iterations):
            benches = run_go_bench(goroot, pkg, cpu_list="1")
            runs.extend(benches)
        for b in runs:
            key = b["name"]
            if key not in all_results:
                all_results[key] = b
            else:
                existing = all_results[key]
                existing["ns_per_op"] = round((existing["ns_per_op"] + b["ns_per_op"]) / 2, 2)
                existing["ops_per_sec"] = round((existing["ops_per_sec"] + b["ops_per_sec"]) / 2, 2)

    out = {
        "benchmark": "go_stdlib",
        "description": f"Go stdlib benchmarks (go test -bench) across {len(PACKAGES)} packages on ARM64",
        "reference": "https://github.com/golang/go",
        "software": "golang",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "ns_per_op": {"unit": "ns", "description": "Nanoseconds per operation"},
            "ops_per_sec": {"unit": "ops/sec", "description": "Operations per second"},
            "mb_per_sec": {"unit": "MB/s", "description": "Throughput in MB/s"},
            "allocs_per_op": {"unit": "allocs", "description": "Allocations per operation"},
        },
        "parameters": {
            "packages": PACKAGES,
            "iterations": iterations,
            "cpu": 1,
            "cgo_enabled": False,
            "benchtime": os.environ.get("BENCH_TIME", "1x"),
        },
        "results_summary": all_results,
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[BENCHMARK_GO] Output written to {output_file} ({len(all_results)} benchmarks)")
    for name, res in sorted(all_results.items()):
        print(f"  {name}: {res['ns_per_op']} ns/op, {res['ops_per_sec']} ops/sec")


if __name__ == "__main__":
    main()
