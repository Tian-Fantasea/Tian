#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import datetime

RENAISSANCE_VERSION = "0.15.0"
RENAISSANCE_JAR = f"renaissance-gpl-{RENAISSANCE_VERSION}.jar"

RENAISSANCE_BENCHMARKS = {
    "akka-uct": {
        "description": "Akka Universal Consensus Test - actor model throughput",
        "category": "concurrency",
    },
    "future-genetic": {
        "description": "Genetic algorithm using Scala futures - concurrent computation",
        "category": "concurrency",
    },
    "scala-kmeans": {
        "description": "K-means clustering using Scala - iterative computation",
        "category": "compute",
    },
    "scrabble": {
        "description": "Scrabble word game using Scala collections - data processing",
        "category": "compute",
    },
    "philosophers": {
        "description": "Dining philosophers using STM - concurrency control",
        "category": "concurrency",
    },
    "reactors": {
        "description": "Reactor-based event processing - reactive streams",
        "category": "concurrency",
    },
    "mnemonics": {
        "description": "Password hashing computation - CPU-bound operation",
        "category": "compute",
    },
}


def download_renaissance(work_dir):
    jar_path = os.path.join(work_dir, RENAISSANCE_JAR)
    if os.path.exists(jar_path) and os.path.getsize(jar_path) > 1000:
        print(f"[RENAISSANCE] Jar already exists: {jar_path}")
        return jar_path

    mirrors = [
        f"https://github.com/renaissance-benchmarks/renaissance/releases/download/v{RENAISSANCE_VERSION}/{RENAISSANCE_JAR}",
        f"https://mirrors.aliyun.com/github-raw/renaissance-benchmarks/renaissance/releases/download/v{RENAISSANCE_VERSION}/{RENAISSANCE_JAR}",
        f"https://repo1.maven.org/maven2/io/github/renaissance-benchmarks/renaissance-gpl/{RENAISSANCE_VERSION}/{RENAISSANCE_JAR}",
    ]

    for mirror_url in mirrors:
        print(f"[RENAISSANCE] Trying mirror: {mirror_url}")
        try:
            result = subprocess.run(
                ["curl", "--connect-timeout", "60", "--max-time", "300", "-L", "-o", jar_path, mirror_url],
                capture_output=True, text=True, timeout=360,
            )
            if result.returncode == 0 and os.path.exists(jar_path) and os.path.getsize(jar_path) > 1000:
                print(f"[RENAISSANCE] Downloaded from {mirror_url}")
                return jar_path
        except (subprocess.TimeoutExpired, Exception):
            pass
        os.remove(jar_path) if os.path.exists(jar_path) else None

    for mirror_url in mirrors:
        print(f"[RENAISSANCE] Trying wget mirror: {mirror_url}")
        try:
            result = subprocess.run(
                ["wget", "--timeout=60", "--tries=2", "-q", "-O", jar_path, mirror_url],
                capture_output=True, text=True, timeout=360,
            )
            if result.returncode == 0 and os.path.exists(jar_path) and os.path.getsize(jar_path) > 1000:
                print(f"[RENAISSANCE] Downloaded via wget from {mirror_url}")
                return jar_path
        except (subprocess.TimeoutExpired, Exception):
            pass
        os.remove(jar_path) if os.path.exists(jar_path) else None

    print("[RENAISSANCE] All mirrors failed, cannot download jar")
    return None


def run_renaissance_benchmark(jar_path, benchmark_name, iterations, work_dir):
    results = []
    for i in range(iterations):
        print(f"[RENAISSANCE] Running {benchmark_name} iteration {i+1}/{iterations}")
        json_output = os.path.join(work_dir, f"renaissance_{benchmark_name}_{i}.json")
        cmd = [
            "java", "-jar", jar_path,
            "--json", json_output,
            "--iterations", "1",
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
                if "completed" in line.lower() and "ms" in line.lower():
                    parts = line.split()
                    for j, p in enumerate(parts):
                        if p.endswith("ms"):
                            try:
                                parsed["elapsed_ms"] = float(p.replace("ms", ""))
                            except ValueError:
                                pass

            if os.path.exists(json_output):
                try:
                    with open(json_output) as f:
                        rj = json.load(f)
                    for bench_result in rj.get("benchmarks", []):
                        if bench_result.get("name") == benchmark_name:
                            metrics = bench_result.get("results", {})
                            for k, v in metrics.items():
                                parsed[k] = v
                except (json.JSONDecodeError, Exception):
                    pass
                os.remove(json_output) if os.path.exists(json_output) else None

            warmup_ms = parsed.get("warmup_ms", 0)
            iteration_ms = parsed.get("iteration_ms", 0)
            elapsed_ms = parsed.get("elapsed_ms", 0)
            parsed["total_ms"] = elapsed_ms if elapsed_ms > 0 else iteration_ms

            parsed["raw_stdout"] = stdout[:500] if stdout else ""
            results.append(parsed)

        except subprocess.TimeoutExpired:
            results.append({
                "benchmark": benchmark_name,
                "iteration": i + 1,
                "error": "timeout",
                "total_ms": 600000,
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
    numeric_keys = ["total_ms", "elapsed_ms", "warmup_ms", "iteration_ms"]
    for key in numeric_keys:
        vals = [r.get(key, 0) for r in results if isinstance(r.get(key, 0), (int, float)) and r.get(key, 0) > 0]
        if vals:
            avg[f"avg_{key}"] = round(sum(vals) / len(vals), 2)
    avg["iterations"] = len(results)
    avg["errors"] = sum(1 for r in results if "error" in r)
    return avg


def main():
    parser = argparse.ArgumentParser(description="Renaissance JVM benchmark for OpenJDK ARM64")
    parser.add_argument("--results-json", required=True, help="Path to results.json")
    parser.add_argument("--section", default="renaissance_benchmark", help="JSON section name")
    parser.add_argument("--iterations", type=int, default=1, help="Number of iterations")
    args = parser.parse_args()

    work_dir = os.path.dirname(os.path.abspath(args.results_json))
    if not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)

    jar_path = download_renaissance(work_dir)
    if not jar_path:
        output = {
            "benchmark": "renaissance",
            "description": "Renaissance JVM benchmark suite (modern workloads: actors, futures, STM, reactive)",
            "reference": "https://renaissance-benchmarks.github.io/",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {
                "throughput": {"unit": "ops/sec", "description": "Operations per second"},
                "latency": {"unit": "milliseconds", "description": "Elapsed time per iteration"},
            },
            "dataset_info": {
                "name": "Renaissance benchmark suite",
                "size": "varies per benchmark",
                "source": "https://github.com/renaissance-benchmarks/renaissance",
            },
            "parameters": {
                "renaissance_version": RENAISSANCE_VERSION,
                "iterations": args.iterations,
            },
            "results": {},
            "error": "Could not download Renaissance jar from any mirror",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        print("[RENAISSANCE] Benchmark skipped (download failed)")
        return 1

    all_results = {}
    for bench_name, config in RENAISSANCE_BENCHMARKS.items():
        print(f"[RENAISSANCE] Benchmark: {bench_name} - {config['description']}")
        bench_results = run_renaissance_benchmark(jar_path, bench_name, args.iterations, work_dir)
        avg = compute_averages(bench_results)
        avg["description"] = config["description"]
        avg["category"] = config["category"]
        all_results[bench_name] = avg

        elapsed = avg.get("avg_total_ms", "N/A")
        print(f"[RENAISSANCE] {bench_name}: avg_elapsed={elapsed}ms")

    output = {
        "benchmark": "renaissance",
        "description": "Renaissance JVM benchmark suite (modern workloads: actors, futures, STM, reactive streams, clustering)",
        "reference": "https://renaissance-benchmarks.github.io/",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "throughput": {"unit": "ops/sec", "description": "Operations per second per benchmark"},
            "latency": {"unit": "milliseconds", "description": "Elapsed wall-clock time per iteration"},
            "warmup": {"unit": "milliseconds", "description": "JIT warmup time per benchmark"},
        },
        "dataset_info": {
            "name": "Renaissance benchmark suite v" + RENAISSANCE_VERSION,
            "size": "varies per benchmark (in-memory datasets)",
            "source": "https://github.com/renaissance-benchmarks/renaissance",
        },
        "parameters": {
            "renaissance_version": RENAISSANCE_VERSION,
            "iterations": args.iterations,
        },
        "results": all_results,
    }

    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output),
    ], check=True)

    print("[RENAISSANCE] Benchmark complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
