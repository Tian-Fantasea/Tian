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
            continue
        match_checksum = re.match(r"(\w+)\s+:\s+([\d.]+)\s+(GB/s|MB/s|KB/s|B/s)\s+\((\d+)\s+bytes\)", line)
        if match_checksum:
            bench_name = match_checksum.group(1).lower()
            throughput = float(match_checksum.group(2))
            unit = match_checksum.group(3)
            block_size = int(match_checksum.group(4))
            if unit == "GB/s":
                throughput_mb = throughput * 1024
            elif unit == "MB/s":
                throughput_mb = throughput
            elif unit == "KB/s":
                throughput_mb = throughput / 1024
            else:
                throughput_mb = throughput / (1024 * 1024)
            ops_per_sec = throughput_mb * (1024 * 1024) / block_size if block_size > 0 else 0
            results[bench_name] = {
                "ops_per_sec": round(ops_per_sec, 2),
                "throughput_mb_per_sec": round(throughput_mb, 2),
                "throughput_unit": unit,
                "block_size": block_size,
                "latency_avg_ms": round(block_size / (throughput_mb * 1024 * 1024) * 1000, 4) if throughput_mb > 0 else 0,
            }
    return results


def benchmark_write_operations(db_bench, results_dir, num_keys, value_size, threads, iterations):
    write_benchmarks = {
        "fillseq": "Sequential key write (async, best write throughput)",
        "fillrandom": "Random key write (async, realistic write pattern)",
        "overwrite": "Random overwrite (update existing keys, triggers compaction)",
        "fillsync": "Synchronous write (fsync after each write, durability focus)",
    }

    results = {}
    db_base = os.path.join(results_dir, "micro_write_db")

    for bench_name, bench_desc in write_benchmarks.items():
        print(f"[MICRO-WRITE] {bench_name}: {bench_desc}")

        db_path = f"{db_base}_{bench_name}"
        wal_path = f"{db_path}_wal"

        iter_results = []
        for iter_num in range(iterations):
            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

            actual_num = num_keys
            if bench_name == "fillsync":
                actual_num = num_keys // 100

            print(f"[MICRO-WRITE]   iteration {iter_num + 1}/{iterations}")
            out, _, rc = run_db_bench(
                db_bench, db_path, wal_path,
                bench_name, actual_num, value_size, threads,
                timeout=1800
            )

            parsed = parse_db_bench_output(out)
            if bench_name in parsed:
                iter_results.append(parsed[bench_name])

            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

        if iter_results:
            avg_ops = sum(r["ops_per_sec"] for r in iter_results) / len(iter_results)
            avg_lat = sum(r["latency_avg_ms"] for r in iter_results) / len(iter_results)
            results[bench_name] = {
                "description": bench_desc,
                "avg_ops_sec": round(avg_ops, 2),
                "avg_latency_ms": round(avg_lat, 4),
                "iterations": len(iter_results),
            }

    return results


def benchmark_read_operations(db_bench, results_dir, num_keys, value_size, threads, iterations):
    read_benchmarks = {
        "readseq": "Sequential read (full scan, best read throughput)",
        "readrandom": "Random point lookup (typical KV read pattern)",
        "readreverse": "Reverse sequential read (iterator scan backwards)",
        "readmissing": "Random read of non-existent keys (measures filter effectiveness)",
        "seekrandom": "Random seek + next N keys (range scan simulation)",
    }

    results = {}
    db_base = os.path.join(results_dir, "micro_read_db")

    db_path = f"{db_base}_shared"
    wal_path = f"{db_path}_wal"

    for fill_iter in range(iterations):
        shutil.rmtree(db_path, ignore_errors=True)
        shutil.rmtree(wal_path, ignore_errors=True)

    shutil.rmtree(db_path, ignore_errors=True)
    shutil.rmtree(wal_path, ignore_errors=True)

    print(f"[MICRO-READ] Loading database with fillrandom...")
    out_fill, _, _ = run_db_bench(
        db_bench, db_path, wal_path,
        "fillrandom", num_keys, value_size, threads,
        timeout=1800
    )

    for bench_name, bench_desc in read_benchmarks.items():
        print(f"[MICRO-READ] {bench_name}: {bench_desc}")

        iter_results = []
        for iter_num in range(iterations):
            print(f"[MICRO-READ]   iteration {iter_num + 1}/{iterations}")
            extra = ["--use_existing_db"]
            if bench_name == "seekrandom":
                extra.append("--seek_nexts=100")

            out, _, rc = run_db_bench(
                db_bench, db_path, wal_path,
                bench_name, num_keys, value_size, threads,
                extra_args=extra, timeout=1800
            )

            parsed = parse_db_bench_output(out)
            if bench_name in parsed:
                iter_results.append(parsed[bench_name])

        if iter_results:
            avg_ops = sum(r["ops_per_sec"] for r in iter_results) / len(iter_results)
            avg_lat = sum(r["latency_avg_ms"] for r in iter_results) / len(iter_results)
            results[bench_name] = {
                "description": bench_desc,
                "avg_ops_sec": round(avg_ops, 2),
                "avg_latency_ms": round(avg_lat, 4),
                "iterations": len(iter_results),
            }

    shutil.rmtree(db_path, ignore_errors=True)
    shutil.rmtree(wal_path, ignore_errors=True)

    return results


def benchmark_delete_operations(db_bench, results_dir, num_keys, value_size, threads, iterations):
    delete_benchmarks = {
        "deleteseq": "Delete keys in sequential order",
        "deleterandom": "Delete keys in random order",
    }

    results = {}
    db_base = os.path.join(results_dir, "micro_delete_db")

    for bench_name, bench_desc in delete_benchmarks.items():
        print(f"[MICRO-DELETE] {bench_name}: {bench_desc}")

        db_path = f"{db_base}_{bench_name}"
        wal_path = f"{db_path}_wal"

        iter_results = []
        for iter_num in range(iterations):
            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

            out_fill, _, _ = run_db_bench(
                db_bench, db_path, wal_path,
                "fillrandom", num_keys, value_size, threads,
                timeout=1800
            )

            out_del, _, _ = run_db_bench(
                db_bench, db_path, wal_path,
                bench_name, num_keys, value_size, threads,
                extra_args=["--use_existing_db"], timeout=1800
            )

            parsed = parse_db_bench_output(out_del)
            if bench_name in parsed:
                iter_results.append(parsed[bench_name])

            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

        if iter_results:
            avg_ops = sum(r["ops_per_sec"] for r in iter_results) / len(iter_results)
            avg_lat = sum(r["latency_avg_ms"] for r in iter_results) / len(iter_results)
            results[bench_name] = {
                "description": bench_desc,
                "avg_ops_sec": round(avg_ops, 2),
                "avg_latency_ms": round(avg_lat, 4),
                "iterations": len(iter_results),
            }

    return results


def benchmark_mixed_operations(db_bench, results_dir, num_keys, value_size, threads, iterations):
    mixed_benchmarks = {
        "readrandomwriterandom": "Mixed random read + random write (YCSB-A style, 50/50)",
        "readwhilewriting": "Read while concurrent writing (read under write pressure)",
        "updaterandom": "Read-modify-write (atomic update pattern)",
        "mergerandom": "Merge operator (incremental update without full read)",
    }

    results = {}
    db_base = os.path.join(results_dir, "micro_mixed_db")

    db_path = f"{db_base}_shared"
    wal_path = f"{db_path}_wal"

    shutil.rmtree(db_path, ignore_errors=True)
    shutil.rmtree(wal_path, ignore_errors=True)

    print(f"[MICRO-MIXED] Loading database with fillrandom...")
    out_fill, _, _ = run_db_bench(
        db_bench, db_path, wal_path,
        "fillrandom", num_keys, value_size, threads,
        timeout=1800
    )

    for bench_name, bench_desc in mixed_benchmarks.items():
        print(f"[MICRO-MIXED] {bench_name}: {bench_desc}")

        iter_results = []
        for iter_num in range(iterations):
            print(f"[MICRO-MIXED]   iteration {iter_num + 1}/{iterations}")

            extra = ["--use_existing_db"]
            if bench_name == "mergerandom":
                extra.append("--merge_operator=uint64add")

            out, _, rc = run_db_bench(
                db_bench, db_path, wal_path,
                bench_name, num_keys, value_size, threads,
                extra_args=extra, timeout=1800
            )

            parsed = parse_db_bench_output(out)
            if bench_name in parsed:
                iter_results.append(parsed[bench_name])

        if iter_results:
            avg_ops = sum(r["ops_per_sec"] for r in iter_results) / len(iter_results)
            avg_lat = sum(r["latency_avg_ms"] for r in iter_results) / len(iter_results)
            results[bench_name] = {
                "description": bench_desc,
                "avg_ops_sec": round(avg_ops, 2),
                "avg_latency_ms": round(avg_lat, 4),
                "iterations": len(iter_results),
            }

    shutil.rmtree(db_path, ignore_errors=True)
    shutil.rmtree(wal_path, ignore_errors=True)

    return results


def benchmark_hash_checksum(db_bench, results_dir, iterations):
    checksum_benchmarks = {
        "crc32c": "CRC32C checksum (ARM64 optimized with hardware instruction)",
        "xxhash": "xxHash checksum (fast non-cryptographic hash)",
    }

    results = {}
    for bench_name, bench_desc in checksum_benchmarks.items():
        print(f"[MICRO-CHECKSUM] {bench_name}: {bench_desc}")

        iter_results = []
        for iter_num in range(iterations):
            out, _, rc = run_db_bench(
                db_bench, "/tmp/micro_checksum_db", "/tmp/micro_checksum_db_wal",
                bench_name, 1000000, 4096, 1,
                timeout=120
            )
            if rc != 0:
                print(f"[MICRO-CHECKSUM] {bench_name} iteration {iter_num + 1} returned rc={rc}, stderr preview: {out[:200] if out else '(empty)'}")

            parsed = parse_db_bench_output(out)
            matched_name = bench_name.lower()
            if matched_name in parsed:
                iter_results.append(parsed[matched_name])
            else:
                print(f"[MICRO-CHECKSUM] {bench_name} not found in parsed output, keys: {list(parsed.keys())}")

        if iter_results:
            avg_ops = sum(r["ops_per_sec"] for r in iter_results) / len(iter_results)
            avg_lat = sum(r["latency_avg_ms"] for r in iter_results) / len(iter_results)
            results[bench_name] = {
                "description": bench_desc,
                "avg_ops_sec": round(avg_ops, 2),
                "avg_latency_ms": round(avg_lat, 4),
                "arm64_note": "CRC32C uses ARM64 CRC32 hardware instructions when available" if bench_name == "crc32c" else "",
                "iterations": len(iter_results),
            }

    return results


def main():
    parser = argparse.ArgumentParser(description="RocksDB micro benchmarks")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--db-bench", required=True)
    parser.add_argument("--num-keys", type=int, default=1000000)
    parser.add_argument("--value-size", type=int, default=256)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    print("[MICRO] Starting RocksDB micro benchmarks...")

    write_results = benchmark_write_operations(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.threads if hasattr(args, 'threads') else 16, args.iterations
    )

    read_results = benchmark_read_operations(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.threads if hasattr(args, 'threads') else 16, args.iterations
    )

    delete_results = benchmark_delete_operations(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.threads if hasattr(args, 'threads') else 16, args.iterations
    )

    mixed_results = benchmark_mixed_operations(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.threads if hasattr(args, 'threads') else 16, args.iterations
    )

    checksum_results = benchmark_hash_checksum(
        args.db_bench, args.results_dir, args.iterations
    )

    output = {
        "benchmark": "micro_operations",
        "description": "RocksDB micro-level benchmarks: individual write/read/delete/mixed/hash operations",
        "reference": "https://github.com/facebook/rocksdb/wiki/Benchmarking",
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
            "iterations": args.iterations,
        },
        "results": {
            "write_operations": write_results,
            "read_operations": read_results,
            "delete_operations": delete_results,
            "mixed_operations": mixed_results,
            "hash_checksum": checksum_results,
        },
    }

    output_path = os.path.join(args.results_dir, "micro_benchmark.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[MICRO] Results saved to: {output_path}")


if __name__ == "__main__":
    main()