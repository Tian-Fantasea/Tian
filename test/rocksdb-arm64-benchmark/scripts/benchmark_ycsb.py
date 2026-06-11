#!/usr/bin/env python3
import subprocess
import json
import os
import sys
import argparse
import re
import shutil
import datetime


def run_db_bench(db_bench, db_path, wal_path, benchmarks, num_keys, value_size,
                 threads, extra_args=None, timeout=600):
    cmd = [
        db_bench,
        f"--benchmarks={benchmarks}",
        f"--num={num_keys}",
        f"--value_size={value_size}",
        f"--threads={threads}",
        f"--db={db_path}",
        f"--wal_dir={wal_path}",
    ]
    if extra_args:
        cmd.extend(extra_args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def parse_db_bench_output(output):
    results = {}
    for line in output.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("DB path"):
            continue
        match = re.match(r"(\w+)\s+:\s+([\d.]+)\s+micros/op\s+([\d.]+)\s+ops/sec;", line)
        if match:
            bench_name = match.group(1).lower()
            micros_per_op = float(match.group(2))
            ops_per_sec = float(match.group(3))
            results[bench_name] = {
                "micros_per_op": micros_per_op,
                "ops_per_sec": ops_per_sec,
                "latency_avg_ms": round(micros_per_op / 1000, 4),
            }
        match2 = re.match(r"(\w+)\s+:\s+([\d.]+)\s+ops/sec;", line)
        if match2 and match2.group(1).lower() not in results:
            bench_name = match2.group(1).lower()
            ops_per_sec = float(match2.group(2))
            results[bench_name] = {"ops_per_sec": ops_per_sec}
    return results


def run_ycsb_workloads(db_bench, results_dir, num_keys, value_size, threads, iterations):
    ycsb_workloads = {
        "ycsb_workload_a_update_heavy": {
            "description": "YCSB Workload A: 50% read / 50% update (update-heavy)",
            "ycsb_ratio": "50/50",
            "bench_sequence": ["fillrandom", "readrandomwriterandom"],
            "read_pct": 50,
            "update_pct": 50,
        },
        "ycsb_workload_b_read_heavy": {
            "description": "YCSB Workload B: 95% read / 5% update (read-heavy)",
            "ycsb_ratio": "95/5",
            "bench_sequence": ["fillrandom", "readwhilewriting"],
            "read_pct": 95,
            "update_pct": 5,
        },
        "ycsb_workload_c_read_only": {
            "description": "YCSB Workload C: 100% read (read-only)",
            "ycsb_ratio": "100/0",
            "bench_sequence": ["fillrandom", "readrandom"],
            "read_pct": 100,
            "update_pct": 0,
        },
        "ycsb_workload_d_read_latest": {
            "description": "YCSB Workload D: 95% read latest / 5% insert",
            "ycsb_ratio": "95/5",
            "bench_sequence": ["fillrandom", "readtocache"],
            "read_pct": 95,
            "update_pct": 5,
        },
        "ycsb_workload_e_short_range_scan": {
            "description": "YCSB Workload E: 95% short range scan / 5% insert",
            "ycsb_ratio": "95/5",
            "bench_sequence": ["fillrandom", "seekrandom"],
            "read_pct": 95,
            "update_pct": 5,
        },
        "ycsb_workload_f_read_modify_write": {
            "description": "YCSB Workload F: 50% read-modify-write (RMW)",
            "ycsb_ratio": "50/50",
            "bench_sequence": ["fillrandom", "updaterandom"],
            "read_pct": 50,
            "update_pct": 50,
        },
    }

    all_results = {}
    db_base = os.path.join(results_dir, "ycsb_db")

    for wl_name, wl_config in ycsb_workloads.items():
        print(f"[YCSB] Running {wl_name}: {wl_config['description']}")

        db_path = f"{db_base}_{wl_name}"
        wal_path = f"{db_path}_wal"
        shutil.rmtree(db_path, ignore_errors=True)
        shutil.rmtree(wal_path, ignore_errors=True)

        wl_results = {}
        for bench in wl_config["bench_sequence"]:
            iter_results = []
            for iter_num in range(iterations):
                print(f"[YCSB]   {bench} iteration {iter_num + 1}/{iterations}")

                if bench == "fillrandom":
                    db_path_iter = db_path
                    wal_path_iter = wal_path
                else:
                    db_path_iter = db_path
                    wal_path_iter = wal_path

                extra = []
                if bench != "fillrandom":
                    extra.append(f"--use_existing_db")

                out, err, rc = run_db_bench(
                    db_bench, db_path_iter, wal_path_iter,
                    bench, num_keys, value_size, threads,
                    extra_args=extra, timeout=1800
                )

                parsed = parse_db_bench_output(out)
                if parsed and bench in parsed:
                    iter_results.append(parsed[bench])

            if iter_results:
                avg_ops = sum(r.get("ops_per_sec", 0) for r in iter_results) / len(iter_results)
                avg_lat = sum(r.get("latency_avg_ms", 0) for r in iter_results) / len(iter_results)
                avg_micros = sum(r.get("micros_per_op", 0) for r in iter_results) / len(iter_results)
                best_ops = max(r.get("ops_per_sec", 0) for r in iter_results)
                wl_results[bench] = {
                    "avg_ops_per_sec": round(avg_ops, 2),
                    "avg_latency_ms": round(avg_lat, 4),
                    "avg_micros_per_op": round(avg_micros, 4),
                    "best_ops_per_sec": round(best_ops, 2),
                    "iterations": len(iter_results),
                    "per_iteration": iter_results,
                }

        if wl_results:
            load_ops = wl_results.get("fillrandom", {}).get("avg_ops_per_sec", 0)
            read_ops = 0
            for k in wl_results:
                if k != "fillrandom":
                    read_ops = wl_results[k].get("avg_ops_per_sec", 0)
                    read_lat = wl_results[k].get("avg_latency_ms", 0)
                    break

            all_results[wl_name] = {
                "description": wl_config["description"],
                "ycsb_ratio": wl_config["ycsb_ratio"],
                "read_pct": wl_config["read_pct"],
                "update_pct": wl_config["update_pct"],
                "load_throughput_ops_sec": round(load_ops, 2),
                "run_throughput_ops_sec": round(read_ops, 2),
                "run_latency_avg_ms": round(read_lat, 4) if read_ops else 0,
                "benchmark_details": wl_results,
            }

        shutil.rmtree(db_path, ignore_errors=True)
        shutil.rmtree(wal_path, ignore_errors=True)

    return all_results


def main():
    parser = argparse.ArgumentParser(description="YCSB benchmark using db_bench")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--db-bench", required=True)
    parser.add_argument("--num-keys", type=int, default=1000000)
    parser.add_argument("--value-size", type=int, default=256)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    print("[YCSB] Starting YCSB benchmark suite (6 workloads)...")
    print(f"[YCSB] Config: keys={args.num_keys}, value_size={args.value_size}, "
          f"threads={args.threads}, iterations={args.iterations}")

    results = run_ycsb_workloads(
        args.db_bench, args.results_dir,
        args.num_keys, args.value_size, args.threads, args.iterations
    )

    output = {
        "benchmark": "ycsb_workloads",
        "description": "YCSB (Yahoo! Cloud Serving Benchmark) standard workloads A-F mapped to RocksDB db_bench operations",
        "reference": "https://github.com/brianfrankcooper/YCSB",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "ops_per_sec": {
                "unit": "ops/sec",
                "description": "Operations per second throughput"
            },
            "latency_avg_ms": {
                "unit": "ms",
                "description": "Average operation latency"
            },
            "micros_per_op": {
                "unit": "microseconds",
                "description": "Microseconds per operation"
            }
        },
        "dataset_info": {
            "name": "synthetic_random_keys",
            "size": f"{args.num_keys} keys x {args.value_size} bytes",
            "source": "db_bench generated"
        },
        "parameters": {
            "num_keys": args.num_keys,
            "value_size": args.value_size,
            "threads": args.threads,
            "iterations": args.iterations,
        },
        "results": results,
    }

    output_path = os.path.join(args.results_dir, "benchmark_ycsb.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[YCSB] Results saved to: {output_path}")
    for wl_name, wl_data in results.items():
        print(f"[YCSB]   {wl_name}: load={wl_data['load_throughput_ops_sec']} ops/sec, "
              f"run={wl_data['run_throughput_ops_sec']} ops/sec")


if __name__ == "__main__":
    main()