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
    return results


def benchmark_compaction_styles(db_bench, results_dir, num_keys, value_size, threads, iterations):
    compaction_styles = {
        "level_compaction": {
            "description": "Leveled compaction (default, LSM tree levels)",
            "args": ["--compaction_style=0"],
        },
        "universal_compaction": {
            "description": "Universal compaction (size-tiered, lower write amplification)",
            "args": ["--compaction_style=1"],
        },
        "fifo_compaction": {
            "description": "FIFO compaction (oldest files dropped, no merging)",
            "args": ["--compaction_style=2"],
        },
    }

    results = {}
    db_base = os.path.join(results_dir, "compaction_db")

    for style_name, style_config in compaction_styles.items():
        print(f"[DBBENCH-COMP] Testing compaction style: {style_name}")

        db_path = f"{db_base}_{style_name}"
        wal_path = f"{db_path}_wal"
        shutil.rmtree(db_path, ignore_errors=True)
        shutil.rmtree(wal_path, ignore_errors=True)

        iter_results = []
        for iter_num in range(iterations):
            print(f"[DBBENCH-COMP]   fillrandom+overwrite iteration {iter_num + 1}/{iterations}")

            out, err, rc = run_db_bench(
                db_bench, db_path, wal_path,
                "fillrandom,overwrite", num_keys, value_size, threads,
                extra_args=style_config["args"], timeout=1800
            )

            parsed = parse_db_bench_output(out)
            for bench_name in ["fillrandom", "overwrite"]:
                if bench_name in parsed:
                    iter_results.append({
                        "bench": bench_name,
                        "compaction": style_name,
                        **parsed[bench_name],
                    })

            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

        fill_ops = [r for r in iter_results if r["bench"] == "fillrandom"]
        over_ops = [r for r in iter_results if r["bench"] == "overwrite"]

        results[style_name] = {
            "description": style_config["description"],
            "fillrandom_avg_ops_sec": round(sum(r["ops_per_sec"] for r in fill_ops) / max(len(fill_ops), 1), 2),
            "overwrite_avg_ops_sec": round(sum(r["ops_per_sec"] for r in over_ops) / max(len(over_ops), 1), 2),
            "fillrandom_avg_lat_ms": round(sum(r["latency_avg_ms"] for r in fill_ops) / max(len(fill_ops), 1), 4),
            "overwrite_avg_lat_ms": round(sum(r["latency_avg_ms"] for r in over_ops) / max(len(over_ops), 1), 4),
        }

    return results


def benchmark_compression_algos(db_bench, results_dir, num_keys, value_size, threads, iterations):
    compression_configs = {
        "no_compression": {
            "description": "No compression (baseline)",
            "args": ["--compression_type=none"],
        },
        "snappy": {
            "description": "Snappy compression (fast, moderate ratio)",
            "args": ["--compression_type=snappy"],
        },
        "lz4": {
            "description": "LZ4 compression (very fast, moderate ratio)",
            "args": ["--compression_type=lz4"],
        },
        "zstd": {
            "description": "ZSTD compression (good ratio, moderate speed)",
            "args": ["--compression_type=zstd"],
        },
        "zlib": {
            "description": "Zlib compression (high ratio, slower)",
            "args": ["--compression_type=zlib"],
        },
    }

    results = {}
    db_base = os.path.join(results_dir, "compression_db")

    for comp_name, comp_config in compression_configs.items():
        print(f"[DBBENCH-COMPRESS] Testing compression: {comp_name}")

        db_path = f"{db_base}_{comp_name}"
        wal_path = f"{db_path}_wal"
        shutil.rmtree(db_path, ignore_errors=True)
        shutil.rmtree(wal_path, ignore_errors=True)

        iter_results = []
        for iter_num in range(iterations):
            print(f"[DBBENCH-COMPRESS]   fillseq+readrandom iteration {iter_num + 1}/{iterations}")

            out, err, rc = run_db_bench(
                db_bench, db_path, wal_path,
                "fillseq,readrandom", num_keys, value_size, threads,
                extra_args=comp_config["args"], timeout=1800
            )

            parsed = parse_db_bench_output(out)

            db_size_mb = 0
            if os.path.isdir(db_path):
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(db_path):
                    for fn in filenames:
                        fp = os.path.join(dirpath, fn)
                        total_size += os.path.getsize(fp)
                db_size_mb = round(total_size / (1024 * 1024), 2)

            for bench_name in ["fillseq", "readrandom"]:
                if bench_name in parsed:
                    iter_results.append({
                        "bench": bench_name,
                        "compression": comp_name,
                        "db_size_mb": db_size_mb,
                        **parsed[bench_name],
                    })

            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

        fill_ops = [r for r in iter_results if r["bench"] == "fillseq"]
        read_ops = [r for r in iter_results if r["bench"] == "readrandom"]
        avg_db_size = round(sum(r["db_size_mb"] for r in iter_results) / max(len(iter_results), 1), 2)

        results[comp_name] = {
            "description": comp_config["description"],
            "fillseq_avg_ops_sec": round(sum(r["ops_per_sec"] for r in fill_ops) / max(len(fill_ops), 1), 2),
            "readrandom_avg_ops_sec": round(sum(r["ops_per_sec"] for r in read_ops) / max(len(read_ops), 1), 2),
            "avg_db_size_mb": avg_db_size,
        }

    return results


def benchmark_bloom_filters(db_bench, results_dir, num_keys, value_size, threads, iterations):
    filter_configs = {
        "no_filter": {
            "description": "No bloom filter (baseline)",
            "args": ["--bloom_bits=0"],
        },
        "bloom_6bits": {
            "description": "Bloom filter 6 bits/key (standard false positive rate ~1.4%)",
            "args": ["--bloom_bits=6"],
        },
        "bloom_10bits": {
            "description": "Bloom filter 10 bits/key (lower false positive rate ~0.84%)",
            "args": ["--bloom_bits=10"],
        },
        "bloom_16bits": {
            "description": "Bloom filter 16 bits/key (very low false positive rate ~0.03%)",
            "args": ["--bloom_bits=16"],
        },
        "ribbon_filter": {
            "description": "Ribbon filter (better space efficiency than bloom, v10.7+)",
            "args": ["--ribbon_filter=true"],
        },
    }

    results = {}
    db_base = os.path.join(results_dir, "filter_db")

    for filt_name, filt_config in filter_configs.items():
        print(f"[DBBENCH-FILTER] Testing filter: {filt_name}")

        db_path = f"{db_base}_{filt_name}"
        wal_path = f"{db_path}_wal"

        iter_results = []
        for iter_num in range(iterations):
            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

            print(f"[DBBENCH-FILTER]   fillrandom+readrandom iteration {iter_num + 1}/{iterations}")

            out_fill, _, _ = run_db_bench(
                db_bench, db_path, wal_path,
                "fillrandom", num_keys, value_size, threads,
                extra_args=filt_config["args"], timeout=1800
            )
            parsed_fill = parse_db_bench_output(out_fill)

            out_read, _, _ = run_db_bench(
                db_bench, db_path, wal_path,
                "readrandom", num_keys, value_size, threads,
                extra_args=filt_config["args"] + ["--use_existing_db"], timeout=1800
            )
            parsed_read = parse_db_bench_output(out_read)

            fill_ops_val = parsed_fill.get("fillrandom", {}).get("ops_per_sec", 0)
            read_ops_val = parsed_read.get("readrandom", {}).get("ops_per_sec", 0)
            read_lat_val = parsed_read.get("readrandom", {}).get("latency_avg_ms", 0)
            iter_results.append({
                "fill_ops_sec": fill_ops_val,
                "read_ops_sec": read_ops_val,
                "read_lat_ms": read_lat_val,
            })

            shutil.rmtree(db_path, ignore_errors=True)
            shutil.rmtree(wal_path, ignore_errors=True)

        results[filt_name] = {
            "description": filt_config["description"],
            "avg_read_ops_sec": round(sum(r["read_ops_sec"] for r in iter_results) / max(len(iter_results), 1), 2),
            "avg_read_lat_ms": round(sum(r["read_lat_ms"] for r in iter_results) / max(len(iter_results), 1), 4),
            "iterations": len(iter_results),
        }

    return results


def benchmark_concurrency_scaling(db_bench, results_dir, num_keys, value_size, iterations):
    thread_counts = [1, 2, 4, 8, 16, 32, 64]

    results = {}
    db_base = os.path.join(results_dir, "concurrency_db")

    for tc in thread_counts:
        print(f"[DBBENCH-CONC] Testing threads={tc}")

        db_path = f"{db_base}_t{tc}"
        wal_path = f"{db_path}_wal"
        shutil.rmtree(db_path, ignore_errors=True)
        shutil.rmtree(wal_path, ignore_errors=True)

        out_fill, _, _ = run_db_bench(
            db_bench, db_path, wal_path,
            "fillrandom", num_keys, value_size, tc,
            timeout=1800
        )
        parsed_fill = parse_db_bench_output(out_fill)

        out_read, _, _ = run_db_bench(
            db_bench, db_path, wal_path,
            "readrandom", num_keys, value_size, tc,
            extra_args=["--use_existing_db"], timeout=1800
        )
        parsed_read = parse_db_bench_output(out_read)

        fill_ops = parsed_fill.get("fillrandom", {}).get("ops_per_sec", 0)
        read_ops = parsed_read.get("readrandom", {}).get("ops_per_sec", 0)
        read_lat = parsed_read.get("readrandom", {}).get("latency_avg_ms", 0)

        results[f"threads_{tc}"] = {
            "threads": tc,
            "fillrandom_ops_sec": round(fill_ops, 2),
            "readrandom_ops_sec": round(read_ops, 2),
            "readrandom_lat_ms": round(read_lat, 4),
        }

        shutil.rmtree(db_path, ignore_errors=True)
        shutil.rmtree(wal_path, ignore_errors=True)

    return results


def main():
    parser = argparse.ArgumentParser(description="db_bench compaction, compression, filter benchmarks")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--db-bench", required=True)
    parser.add_argument("--num-keys", type=int, default=1000000)
    parser.add_argument("--value-size", type=int, default=256)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    print("[DBBENCH] Starting db_bench compaction, compression, filter, and concurrency benchmarks...")

    compaction_results = benchmark_compaction_styles(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.threads, args.iterations
    )

    compression_results = benchmark_compression_algos(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.threads, args.iterations
    )

    filter_results = benchmark_bloom_filters(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.threads, args.iterations
    )

    concurrency_results = benchmark_concurrency_scaling(
        args.db_bench, args.results_dir, args.num_keys, args.value_size,
        args.iterations
    )

    output = {
        "benchmark": "db_bench_advanced",
        "description": "RocksDB db_bench advanced benchmarks: compaction styles, compression algorithms, bloom/ribbon filters, concurrency scaling",
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
            "db_size_mb": {
                "unit": "MB",
                "description": "Database size on disk (reflects compression ratio)"
            },
            "filter_effectiveness": {
                "unit": "ops/sec improvement",
                "description": "Read throughput improvement from bloom/ribbon filters"
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
        "results": {
            "compaction_styles": compaction_results,
            "compression_algorithms": compression_results,
            "bloom_ribbon_filters": filter_results,
            "concurrency_scaling": concurrency_results,
        },
    }

    output_path = os.path.join(args.results_dir, "benchmark_dbbench.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[DBBENCH] Results saved to: {output_path}")


if __name__ == "__main__":
    main()