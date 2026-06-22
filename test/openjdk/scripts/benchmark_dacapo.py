#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import datetime

DACAPO_VERSION = "9.12-MR1-bach"
DACAPO_JAR = f"dacapo-{DACAPO_VERSION}.jar"

DACAPO_BENCHMARKS = {
    "h2": {
        "description": "H2 database benchmark - in-memory SQL transactions",
        "category": "database",
    },
    "luindex": {
        "description": "Lucene indexing - text document indexing",
        "category": "search",
    },
    "lusearch-fix": {
        "description": "Lucene search - text search queries",
        "category": "search",
    },
    "pmd": {
        "description": "PMD source code analyzer - Java parsing",
        "category": "compute",
    },
    "sunflow": {
        "description": "Sunflow ray tracing renderer - floating point intensive",
        "category": "compute",
    },
    "tradebeans": {
        "description": "Daytrading with beans - complex business logic",
        "category": "application",
    },
    "xalan": {
        "description": "XSLT transformation - XML processing",
        "category": "compute",
    },
    "avrora": {
        "description": "Avrora microcontroller simulator - simulation",
        "category": "simulation",
    },
}


def download_dacapo(work_dir):
    jar_path = os.path.join(work_dir, DACAPO_JAR)
    if os.path.exists(jar_path) and os.path.getsize(jar_path) > 1000:
        print(f"[DACAPO] Jar already exists: {jar_path}")
        return jar_path

    mirrors = [
        f"https://github.com/dacapobench/dacapobench/releases/download/v{DACAPO_VERSION}/{DACAPO_JAR}",
        "https://dacapobench.sourceforge.net/" + DACAPO_JAR,
        f"https://mirrors.aliyun.com/dacapo/{DACAPO_JAR}",
    ]

    for mirror_url in mirrors:
        print(f"[DACAPO] Trying mirror: {mirror_url}")
        try:
            result = subprocess.run(
                ["curl", "--connect-timeout", "60", "--max-time", "300", "-L", "-o", jar_path, mirror_url],
                capture_output=True, text=True, timeout=360,
            )
            if result.returncode == 0 and os.path.exists(jar_path) and os.path.getsize(jar_path) > 1000:
                print(f"[DACAPO] Downloaded from {mirror_url}")
                return jar_path
        except (subprocess.TimeoutExpired, Exception):
            pass
        os.remove(jar_path) if os.path.exists(jar_path) else None

    for mirror_url in mirrors:
        print(f"[DACAPO] Trying wget mirror: {mirror_url}")
        try:
            result = subprocess.run(
                ["wget", "--timeout=60", "--tries=2", "-q", "-O", jar_path, mirror_url],
                capture_output=True, text=True, timeout=360,
            )
            if result.returncode == 0 and os.path.exists(jar_path) and os.path.getsize(jar_path) > 1000:
                print(f"[DACAPO] Downloaded via wget from {mirror_url}")
                return jar_path
        except (subprocess.TimeoutExpired, Exception):
            pass
        os.remove(jar_path) if os.path.exists(jar_path) else None

    print("[DACAPO] All mirrors failed, cannot download jar")
    return None


def run_dacapo_benchmark(jar_path, benchmark_name, iterations, work_dir):
    results = []
    for i in range(iterations):
        print(f"[DACAPO] Running {benchmark_name} iteration {i+1}/{iterations}")
        cmd = [
            "java", "-jar", jar_path,
            "-n", str(min(iterations, 3)),
            benchmark_name,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
            )
            stdout = proc.stdout
            stderr = proc.stderr

            parsed = {"benchmark": benchmark_name, "iteration": i + 1}

            for line in stdout.split("\n"):
                line = line.strip()
                m = re.search(r"completed\s+in\s+([\d.]+)\s+msec", line)
                if m:
                    parsed["elapsed_ms"] = float(m.group(1))

                m = re.search(r"^====\s+([\w-]+)\s+.*completed.*([\d.]+)\s*msec", line)
                if m and m.group(1) == benchmark_name:
                    parsed["elapsed_ms"] = float(m.group(2))

            elapsed = parsed.get("elapsed_ms", 0)
            if elapsed > 0:
                parsed["throughput_ops_per_sec"] = round(1000.0 / elapsed, 2)

            parsed["raw_stdout"] = stdout[:500] if stdout else ""
            results.append(parsed)

        except subprocess.TimeoutExpired:
            results.append({
                "benchmark": benchmark_name,
                "iteration": i + 1,
                "error": "timeout",
                "elapsed_ms": 600000,
            })
        except Exception as e:
            results.append({
                "benchmark": benchmark_name,
                "iteration": i + 1,
                "error": str(e),
            })

    return results


def compute_averages(results):
    if not results:
        return {}
    avg = {}
    numeric_keys = ["elapsed_ms", "throughput_ops_per_sec"]
    for key in numeric_keys:
        vals = [r.get(key, 0) for r in results if isinstance(r.get(key, 0), (int, float)) and r.get(key, 0) > 0]
        if vals:
            avg[f"avg_{key}"] = round(sum(vals) / len(vals), 2)
    avg["iterations"] = len(results)
    avg["errors"] = sum(1 for r in results if "error" in r)
    return avg


def main():
    parser = argparse.ArgumentParser(description="DaCapo JVM benchmark for OpenJDK ARM64")
    parser.add_argument("--results-json", required=True, help="Path to results.json")
    parser.add_argument("--section", default="dacapo_benchmark", help="JSON section name")
    parser.add_argument("--iterations", type=int, default=1, help="Number of iterations")
    args = parser.parse_args()

    work_dir = os.path.dirname(os.path.abspath(args.results_json))
    if not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)

    jar_path = download_dacapo(work_dir)
    if not jar_path:
        output = {
            "benchmark": "dacapo",
            "description": "DaCapo JVM benchmark suite (classic Java workloads: database, search, parsing, simulation)",
            "reference": "https://dacapobench.sourceforge.net/",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {
                "throughput": {"unit": "ops/sec", "description": "Iterations per second"},
                "latency": {"unit": "milliseconds", "description": "Time per iteration"},
            },
            "dataset_info": {
                "name": "DaCapo benchmark suite v" + DACAPO_VERSION,
                "size": "varies per benchmark (in-memory + disk datasets)",
                "source": "https://dacapobench.sourceforge.net/",
            },
            "parameters": {
                "dacapo_version": DACAPO_VERSION,
                "iterations": args.iterations,
            },
            "results": {},
            "error": "Could not download DaCapo jar from any mirror",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        print("[DACAPO] Benchmark skipped (download failed)")
        return 1

    all_results = {}
    for bench_name, config in DACAPO_BENCHMARKS.items():
        print(f"[DACAPO] Benchmark: {bench_name} - {config['description']}")
        bench_results = run_dacapo_benchmark(jar_path, bench_name, args.iterations, work_dir)
        avg = compute_averages(bench_results)
        avg["description"] = config["description"]
        avg["category"] = config["category"]
        all_results[bench_name] = avg

        elapsed = avg.get("avg_elapsed_ms", "N/A")
        throughput = avg.get("avg_throughput_ops_per_sec", "N/A")
        print(f"[DACAPO] {bench_name}: avg_elapsed={elapsed}ms, avg_throughput={throughput} ops/sec")

    output = {
        "benchmark": "dacapo",
        "description": "DaCapo JVM benchmark suite (classic Java workloads: database, search, parsing, simulation, ray tracing)",
        "reference": "https://dacapobench.sourceforge.net/",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "throughput": {"unit": "ops/sec", "description": "Iterations per second per benchmark"},
            "latency": {"unit": "milliseconds", "description": "Wall-clock time per iteration"},
        },
        "dataset_info": {
            "name": "DaCapo benchmark suite v" + DACAPO_VERSION,
            "size": "varies per benchmark",
            "source": "https://dacapobench.sourceforge.net/",
        },
        "parameters": {
            "dacapo_version": DACAPO_VERSION,
            "iterations": args.iterations,
        },
        "results": all_results,
    }

    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output),
    ], check=True)

    print("[DACAPO] Benchmark complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
