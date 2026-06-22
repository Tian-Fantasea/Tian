#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import datetime
import tempfile

MICRO_BENCHMARKS = {
    "string_concat_builder": {
        "description": "StringBuilder concatenation (10,000 ops)",
        "code": """
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 10000; i++) {
                sb.append("str").append(i);
            }
            String result = sb.toString();
""",
        "iterations": 100,
        "warmup": 5,
    },
    "array_sort": {
        "description": "Arrays.sort on 100,000-element int array",
        "code": """
            int[] arr = new int[100000];
            for (int i = 0; i < arr.length; i++) arr[i] = 100000 - i;
            Arrays.sort(arr);
""",
        "iterations": 50,
        "warmup": 3,
    },
    "hashmap_operations": {
        "description": "HashMap put/get/iterate (50,000 entries)",
        "code": """
            Map<Integer, String> map = new HashMap<>();
            for (int i = 0; i < 50000; i++) map.put(i, "val" + i);
            for (int i = 0; i < 50000; i++) map.get(i);
            long count = 0;
            for (Map.Entry<Integer, String> e : map.entrySet()) count += e.getKey();
""",
        "iterations": 50,
        "warmup": 3,
    },
    "math_operations": {
        "description": "Math.sqrt/sin/cos/pow (100,000 ops each)",
        "code": """
            double sum = 0;
            for (int i = 0; i < 100000; i++) {
                sum += Math.sqrt(i) + Math.sin(i * 0.01) + Math.cos(i * 0.01) + Math.pow(i, 0.5);
            }
""",
        "iterations": 50,
        "warmup": 3,
    },
    "thread_creation": {
        "description": "Thread creation and start (1,000 threads)",
        "code": """
            Thread[] threads = new Thread[1000];
            for (int i = 0; i < 1000; i++) {
                threads[i] = new Thread(() -> {});
                threads[i].start();
            }
            for (Thread t : threads) t.join();
""",
        "iterations": 10,
        "warmup": 2,
    },
    "object_allocation": {
        "description": "Object allocation rate (1,000,000 simple objects)",
        "code": """
            Object[] objs = new Object[1000000];
            for (int i = 0; i < 1000000; i++) objs[i] = new Object();
""",
        "iterations": 20,
        "warmup": 3,
    },
}

JAVA_TEMPLATE = """
import java.util.*;

public class MicroBenchmark {{
    private static long measure(String name, Runnable action, int iterations, int warmup) {{
        for (int w = 0; w < warmup; w++) {{
            action.run();
        }}
        long[] times = new long[iterations];
        for (int i = 0; i < iterations; i++) {{
            long start = System.nanoTime();
            action.run();
            times[i] = System.nanoTime() - start;
        }}
        long sum = 0;
        long min = Long.MAX_VALUE;
        long max = Long.MIN_VALUE;
        for (long t : times) {{
            sum += t;
            if (t < min) min = t;
            if (t > max) max = t;
        }}
        double avg = sum / (double) iterations;
        double median;
        Arrays.sort(times);
        if (iterations % 2 == 0) {{
            median = (times[iterations/2-1] + times[iterations/2]) / 2.0;
        }} else {{
            median = times[iterations/2];
        }}
        System.out.println(name + ": avg_ns=" + (long)avg + " min_ns=" + min + " max_ns=" + max + " median_ns=" + (long)median + " iterations=" + iterations);
        return (long)avg;
    }}

    public static void main(String[] args) {{
        Set<String> runBenchmarks = new HashSet<>();
        if (args.length == 0) {{
            runBenchmarks.addAll(Arrays.asList({bench_names}));
        }} else {{
            runBenchmarks.addAll(Arrays.asList(args));
        }}

        {benchmark_methods}
    }}
}}
"""

BENCH_METHOD_TEMPLATE = """
        if (runBenchmarks.contains("{bench_name}")) {{
            measure("{bench_name}", () -> {{
                {code}
            }}, {iterations}, {warmup});
        }}
"""


def create_java_source():
    bench_names = ", ".join(f'"{k}"' for k in MICRO_BENCHMARKS.keys())
    methods = []
    for name, config in MICRO_BENCHMARKS.items():
        method = BENCH_METHOD_TEMPLATE.format(
            bench_name=name,
            code=config["code"].strip(),
            iterations=config["iterations"],
            warmup=config["warmup"],
        )
        methods.append(method)
    benchmark_methods = "\n".join(methods)
    source = JAVA_TEMPLATE.format(
        bench_names=bench_names,
        benchmark_methods=benchmark_methods,
    )
    return source


def compile_and_run(java_source, work_dir, iterations):
    src_path = os.path.join(work_dir, "MicroBenchmark.java")
    with open(src_path, "w") as f:
        f.write(java_source)

    compile_result = subprocess.run(
        ["javac", src_path],
        capture_output=True, text=True, timeout=60,
    )
    if compile_result.returncode != 0:
        print(f"[MICRO] Compilation failed: {compile_result.stderr}")
        return None

    class_dir = work_dir

    all_results = {}
    for bench_name, config in MICRO_BENCHMARKS.items():
        print(f"[MICRO] Running {bench_name}: {config['description']}")
        iteration_data = []
        for i in range(iterations):
            try:
                proc = subprocess.run(
                    ["java", "-cp", class_dir, "MicroBenchmark", bench_name],
                    capture_output=True, text=True, timeout=120,
                )
                stdout = proc.stdout
                parsed = {"benchmark": bench_name, "iteration": i + 1}

                m = re.search(rf'{bench_name}:\s+avg_ns=(\d+)\s+min_ns=(\d+)\s+max_ns=(\d+)\s+median_ns=(\d+)\s+iterations=(\d+)', stdout)
                if m:
                    parsed["avg_ns"] = int(m.group(1))
                    parsed["min_ns"] = int(m.group(2))
                    parsed["max_ns"] = int(m.group(3))
                    parsed["median_ns"] = int(m.group(4))
                    parsed["measured_iterations"] = int(m.group(5))
                    if parsed["avg_ns"] > 0:
                        parsed["ops_per_sec"] = round(1e9 / parsed["avg_ns"], 2)

                parsed["description"] = config["description"]
                iteration_data.append(parsed)

            except subprocess.TimeoutExpired:
                iteration_data.append({
                    "benchmark": bench_name,
                    "iteration": i + 1,
                    "error": "timeout",
                })
            except Exception as e:
                iteration_data.append({
                    "benchmark": bench_name,
                    "iteration": i + 1,
                    "error": str(e),
                })

        avg = compute_averages(iteration_data)
        avg["description"] = config["description"]
        avg["warmup_iterations"] = config["warmup"]
        avg["measured_iterations"] = config["iterations"]
        all_results[bench_name] = avg

        avg_ns = avg.get("avg_avg_ns", "N/A")
        ops = avg.get("avg_ops_per_sec", "N/A")
        print(f"[MICRO] {bench_name}: avg_ns={avg_ns}, ops/sec={ops}")

    return all_results


def compute_averages(results):
    if not results:
        return {}
    avg = {}
    numeric_keys = ["avg_ns", "min_ns", "max_ns", "median_ns", "ops_per_sec"]
    for key in numeric_keys:
        vals = [r.get(key, 0) for r in results if isinstance(r.get(key, 0), (int, float)) and r.get(key, 0) > 0]
        if vals:
            avg[f"avg_{key}"] = round(sum(vals) / len(vals), 2)
    avg["iterations"] = len(results)
    avg["errors"] = sum(1 for r in results if "error" in r)
    return avg


def main():
    parser = argparse.ArgumentParser(description="JVM micro benchmarks for OpenJDK ARM64")
    parser.add_argument("--results-json", required=True, help="Path to results.json")
    parser.add_argument("--section", default="micro_benchmark", help="JSON section name")
    parser.add_argument("--iterations", type=int, default=1, help="Number of iterations")
    args = parser.parse_args()

    work_dir = os.path.dirname(os.path.abspath(args.results_json))
    if not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)

    if not os.path.exists("/usr/bin/javac") and not os.path.exists("/usr/local/bin/javac"):
        try:
            result = subprocess.run(["javac", "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print("[MICRO] javac not available, skipping micro benchmarks")
                output = {
                    "benchmark": "jvm_micro",
                    "description": "JVM micro benchmarks (String, Array, HashMap, Math, Thread, Object allocation)",
                    "reference": "Custom micro benchmark suite for JVM basic operations",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "performance_metrics": {
                        "throughput": {"unit": "ops/sec", "description": "Operations per second"},
                        "latency": {"unit": "nanoseconds", "description": "Time per operation (ns/op)"},
                    },
                    "dataset_info": {
                        "name": "In-memory synthetic data",
                        "size": "varies per benchmark",
                        "source": "Generated in benchmark code",
                    },
                    "parameters": {
                        "iterations": args.iterations,
                        "warmup": 3,
                    },
                    "results": {},
                    "error": "javac not available (JRE-only system, cannot compile micro benchmarks)",
                }
                subprocess.run([
                    sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
                    args.results_json, "write_results_section", args.section, json.dumps(output),
                ], check=True)
                print("[MICRO] Benchmark skipped (no javac)")
                return 1
        except Exception:
            pass

    java_source = create_java_source()
    benchmark_results = compile_and_run(java_source, work_dir, args.iterations)

    if not benchmark_results:
        output = {
            "benchmark": "jvm_micro",
            "description": "JVM micro benchmarks (String, Array, HashMap, Math, Thread, Object allocation)",
            "reference": "Custom micro benchmark suite for JVM basic operations",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {
                "throughput": {"unit": "ops/sec", "description": "Operations per second"},
                "latency": {"unit": "nanoseconds", "description": "Time per operation (ns/op)"},
            },
            "dataset_info": {
                "name": "In-memory synthetic data",
                "size": "varies per benchmark",
                "source": "Generated in benchmark code",
            },
            "parameters": {
                "iterations": args.iterations,
            },
            "results": {},
            "error": "Could not compile or run micro benchmarks",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        return 1

    output = {
        "benchmark": "jvm_micro",
        "description": "JVM micro benchmarks (StringBuilder concat, Array sort, HashMap ops, Math ops, Thread creation, Object allocation)",
        "reference": "Custom micro benchmark suite for JVM basic operations on ARM64",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "throughput": {"unit": "ops/sec", "description": "Operations per second per micro benchmark"},
            "latency": {"unit": "nanoseconds", "description": "Average nanoseconds per operation"},
            "median_latency": {"unit": "nanoseconds", "description": "Median nanoseconds per operation"},
        },
        "dataset_info": {
            "name": "In-memory synthetic data",
            "size": "varies per benchmark (10K-1M elements)",
            "source": "Generated in benchmark code",
        },
        "parameters": {
            "iterations": args.iterations,
            "warmup_per_benchmark": 3,
        },
        "results": benchmark_results,
    }

    subprocess.run([
        sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
        args.results_json, "write_results_section", args.section, json.dumps(output),
    ], check=True)

    print("[MICRO] Benchmark complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
