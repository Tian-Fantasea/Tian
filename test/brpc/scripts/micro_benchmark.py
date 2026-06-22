#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import datetime
import time
import tempfile

MICRO_CPP_TEMPLATE = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <chrono>
#include <thread>
#include <mutex>
#include <vector>
#include <map>
#include <string>
#include <atomic>
#include <algorithm>
#include <numeric>

using namespace std;
using namespace std::chrono;

struct Result {
    string name;
    long avg_ns;
    long min_ns;
    long max_ns;
    long median_ns;
    double ops_per_sec;
    int iterations;
};

Result measure(const char* name, auto func, int warmup, int iters) {
    for (int w = 0; w < warmup; w++) { func(); }
    vector<long> times(iters);
    for (int i = 0; i < iters; i++) {
        auto start = high_resolution_clock::now();
        func();
        auto end = high_resolution_clock::now();
        times[i] = duration_cast<nanoseconds>(end - start).count();
    }
    sort(times.begin(), times.end());
    long sum = accumulate(times.begin(), times.end(), 0L);
    Result r;
    r.name = name;
    r.avg_ns = sum / iters;
    r.min_ns = times.front();
    r.max_ns = times.back();
    r.median_ns = times[iters / 2];
    r.ops_per_sec = (r.avg_ns > 0) ? (1e9 / r.avg_ns) : 0;
    r.iterations = iters;
    printf("%s: avg_ns=%ld min_ns=%ld max_ns=%ld median_ns=%ld ops_per_sec=%.2f iterations=%d\n",
           name, r.avg_ns, r.min_ns, r.max_ns, r.median_ns, r.ops_per_sec, iters);
    return r;
}

int main() {
    printf("=== BRPC ARM64 Micro Benchmarks ===\n");

    measure("mutex_lock_unlock", []{
        mutex m;
        m.lock(); m.unlock();
    }, 5, 100);

    measure("atomic_increment", []{
        atomic<int> v(0);
        v.fetch_add(1, memory_order_relaxed);
    }, 5, 1000);

    measure("thread_create_join", []{
        thread t([]{});
        t.join();
    }, 2, 10);

    measure("string_concat_1k", []{
        string s;
        for (int i = 0; i < 1000; i++) s += "x";
    }, 3, 100);

    measure("vector_push_back_10k", []{
        vector<int> v;
        for (int i = 0; i < 10000; i++) v.push_back(i);
    }, 3, 100);

    measure("map_insert_lookup_10k", []{
        map<int,int> m;
        for (int i = 0; i < 10000; i++) m[i] = i;
        for (int i = 0; i < 10000; i++) m.count(i);
    }, 3, 50);

    measure("memcpy_64k", []{
        char src[65536], dst[65536];
        memset(src, 1, 65536);
        memcpy(dst, src, 65536);
    }, 3, 100);

    measure("sort_100k_ints", []{
        vector<int> v(100000);
        for (int i = 0; i < 100000; i++) v[i] = 100000 - i;
        sort(v.begin(), v.end());
    }, 3, 20);

    measure("new_delete_100k_objects", []{
        for (int i = 0; i < 100000; i++) {
            int* p = new int(i);
            delete p;
        }
    }, 3, 20);

    measure("sqrt_math_100k", []{
        double sum = 0;
        for (int i = 0; i < 100000; i++) sum += sqrt((double)i) + sin(i*0.01);
    }, 3, 50);

    printf("=== DONE ===\n");
    return 0;
}
"""

MICRO_BENCHMARK_NAMES = [
    "mutex_lock_unlock",
    "atomic_increment",
    "thread_create_join",
    "string_concat_1k",
    "vector_push_back_10k",
    "map_insert_lookup_10k",
    "memcpy_64k",
    "sort_100k_ints",
    "new_delete_100k_objects",
    "sqrt_math_100k",
]


def find_compiler():
    for cc in ["g++", "clang++"]:
        try:
            result = subprocess.run([cc, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return cc
        except Exception:
            pass
    return None


def compile_micro_benchmark(source, work_dir, cc):
    src_path = os.path.join(work_dir, "brpc_micro_bench.cpp")
    exe_path = os.path.join(work_dir, "brpc_micro_bench")

    with open(src_path, "w") as f:
        f.write(source)

    cmd = [cc, "-std=c++17", "-O2", "-pthread", src_path, "-o", exe_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"[MICRO] Compilation failed: {result.stderr[:200]}")
            return None
        return exe_path
    except Exception as e:
        print(f"[MICRO] Compilation error: {e}")
        return None


def run_micro_benchmark(exe_path, iterations):
    all_results = {}
    for i in range(iterations):
        print(f"[MICRO] Running iteration {i+1}/{iterations}")
        try:
            proc = subprocess.run(
                [exe_path], capture_output=True, text=True, timeout=120,
            )
            stdout = proc.stdout

            for line in stdout.split("\n"):
                line = line.strip()
                m = re.match(
                    r"(\w+):\s+avg_ns=(\d+)\s+min_ns=(\d+)\s+max_ns=(\d+)\s+median_ns=(\d+)\s+ops_per_sec=([\d.]+)\s+iterations=(\d+)",
                    line,
                )
                if m:
                    name = m.group(1)
                    if name not in all_results:
                        all_results[name] = {
                            "iterations_data": [],
                            "avg_ns_values": [],
                            "ops_per_sec_values": [],
                        }
                    all_results[name]["iterations_data"].append({
                        "avg_ns": int(m.group(2)),
                        "min_ns": int(m.group(3)),
                        "max_ns": int(m.group(4)),
                        "median_ns": int(m.group(5)),
                        "ops_per_sec": float(m.group(6)),
                        "measured_iterations": int(m.group(7)),
                    })
                    all_results[name]["avg_ns_values"].append(int(m.group(2)))
                    all_results[name]["ops_per_sec_values"].append(float(m.group(6)))

        except subprocess.TimeoutExpired:
            print("[MICRO] Timeout in iteration")
        except Exception as e:
            print(f"[MICRO] Error: {e}")

    averaged = {}
    for name, data in all_results.items():
        avg_entry = {"benchmark": name}
        if data["avg_ns_values"]:
            avg_entry["avg_avg_ns"] = round(sum(data["avg_ns_values"]) / len(data["avg_ns_values"]), 2)
        if data["ops_per_sec_values"]:
            avg_entry["avg_ops_per_sec"] = round(sum(data["ops_per_sec_values"]) / len(data["ops_per_sec_values"]), 2)
        avg_entry["iterations"] = len(data["iterations_data"])

        desc_map = {
            "mutex_lock_unlock": "std::mutex lock/unlock overhead",
            "atomic_increment": "std::atomic<int> fetch_add (relaxed) overhead",
            "thread_create_join": "std::thread creation + join overhead",
            "string_concat_1k": "std::string append 1000 chars",
            "vector_push_back_10k": "std::vector<int> push_back 10,000 elements",
            "map_insert_lookup_10k": "std::map<int,int> insert + count 10,000 entries",
            "memcpy_64k": "memcpy 64KB buffer",
            "sort_100k_ints": "std::sort 100,000 ints (descending→ascending)",
            "new_delete_100k_objects": "new/delete 100,000 int objects",
            "sqrt_math_100k": "sqrt+sin 100,000 iterations (FP math)",
        }
        avg_entry["description"] = desc_map.get(name, name)
        averaged[name] = avg_entry

    return averaged


def main():
    parser = argparse.ArgumentParser(description="C++ micro benchmarks for brpc ARM64")
    parser.add_argument("--results-json", required=True, help="Path to results.json")
    parser.add_argument("--section", default="micro_benchmark", help="JSON section name")
    parser.add_argument("--iterations", type=int, default=1, help="Number of iterations")
    args = parser.parse_args()

    work_dir = os.path.dirname(os.path.abspath(args.results_json))
    if not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)

    cc = find_compiler()
    if not cc:
        print("[MICRO] No C++ compiler found (g++/clang++)")
        output = {
            "benchmark": "cpp_micro",
            "description": "C++ micro benchmarks relevant to brpc components (mutex, atomic, thread, string, vector, map, memcpy, sort, alloc, math)",
            "reference": "Custom micro benchmark suite for C++ STL operations on ARM64",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {
                "throughput": {"unit": "ops/sec", "description": "Operations per second"},
                "latency": {"unit": "nanoseconds", "description": "Average ns per operation"},
            },
            "dataset_info": {
                "name": "In-memory synthetic data",
                "size": "varies per benchmark",
                "source": "Generated in benchmark code",
            },
            "parameters": {
                "compiler": "not found",
                "optimization": "-O2",
                "iterations": args.iterations,
            },
            "results": {},
            "error": "No C++ compiler (g++/clang++) available",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        return 1

    exe_path = compile_micro_benchmark(MICRO_CPP_TEMPLATE, work_dir, cc)
    if not exe_path:
        output = {
            "benchmark": "cpp_micro",
            "description": "C++ micro benchmarks (mutex, atomic, thread, string, vector, map, memcpy, sort, alloc, math)",
            "reference": "Custom micro benchmark for C++ STL on ARM64",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {
                "throughput": {"unit": "ops/sec", "description": "Operations per second"},
                "latency": {"unit": "nanoseconds", "description": "Average ns per operation"},
            },
            "dataset_info": {
                "name": "In-memory synthetic",
                "size": "varies",
                "source": "Generated in code",
            },
            "parameters": {
                "compiler": cc,
                "optimization": "-O2",
                "iterations": args.iterations,
            },
            "results": {},
            "error": "Compilation failed",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        return 1

    print(f"[MICRO] Compiled with {cc}, running benchmarks...")
    benchmark_results = run_micro_benchmark(exe_path, args.iterations)

    if not benchmark_results:
        output = {
            "benchmark": "cpp_micro",
            "description": "C++ micro benchmarks",
            "reference": "Custom micro benchmark for ARM64",
            "timestamp": datetime.datetime.now().isoformat(),
            "performance_metrics": {},
            "dataset_info": {},
            "parameters": {
                "compiler": cc,
                "iterations": args.iterations,
            },
            "results": {},
            "error": "No benchmark results collected",
        }
        subprocess.run([
            sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py"),
            args.results_json, "write_results_section", args.section, json.dumps(output),
        ], check=True)
        return 1

    output = {
        "benchmark": "cpp_micro",
        "description": "C++ micro benchmarks relevant to brpc core components: mutex lock/unlock, atomic increment, thread create/join, string concat, vector push, map insert/lookup, memcpy, sort, new/delete allocation, floating-point math",
        "reference": "Custom micro benchmark suite for C++ STL operations on ARM64 (brpc-relevant)",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "throughput": {"unit": "ops/sec", "description": "Operations per second per benchmark"},
            "latency_avg": {"unit": "nanoseconds", "description": "Average ns per operation"},
            "latency_median": {"unit": "nanoseconds", "description": "Median ns per operation"},
        },
        "dataset_info": {
            "name": "In-memory synthetic data",
            "size": "varies per benchmark (1K-100K elements)",
            "source": "Generated in benchmark code",
        },
        "parameters": {
            "compiler": cc,
            "optimization": "-O2",
            "std": "c++17",
            "iterations": args.iterations,
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
