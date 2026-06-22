#!/usr/bin/env python3
"""
Spark Core Micro-Benchmarks for ARM64
Tests individual Spark engine components to isolate performance characteristics

Reference: Intel HiBench micro-benchmark suite
           https://github.com/intel-hibench/HiBench
           Also inspired by Berkeley AMPLab SparkBench

Performance Metrics:
  - Execution time (ms) per operation
  - Throughput (records/s)
  - Shuffle read/write bytes
  - CPU time vs wall time

Tests:
  1. Sort         - DataFrame/RDD sort performance
  2. Shuffle      - Network shuffle performance (local)
  3. Aggregate    - GroupBy aggregation performance
  4. Join         - Join operation performance (inner, broadcast)
  5. WordCount    - Classic MapReduce pattern
  6. Scan         - Raw data scan/filter throughput
  7. GroupBy      - GroupBy with multiple aggregations
"""

import sys
import os
import json
import time
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, rand, count, sum as _sum, avg, stddev, lit


def run_sort_benchmark(spark, data_size, iterations=3):
    """Benchmark: Sort operation on DataFrame"""
    results = []
    print(f"[MICRO-SORT] Running sort benchmark with {data_size} rows, {iterations} iterations")

    for i in range(iterations):
        df = spark.range(data_size).select(
            col("id"),
            rand().alias("sort_key")
        )
        start = time.time()
        sorted_df = df.sort("sort_key")
        sorted_df.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2)
        })
        print(f"[MICRO-SORT] Iter {i+1}: {elapsed_ms:.2f}ms, {throughput:.0f} rec/s")

    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Sort",
        "description": "Sort DataFrame by random key column",
        "data_size_rows": data_size,
        "iterations": iterations,
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "iterations_detail": results
    }


def run_aggregate_benchmark(spark, data_size, iterations=3):
    """Benchmark: Aggregation (GroupBy + aggregate functions)"""
    results = []
    print(f"[MICRO-AGG] Running aggregate benchmark with {data_size} rows, {iterations} iterations")

    for i in range(iterations):
        df = spark.range(data_size).select(
            col("id"),
            (col("id") % 100).alias("group_key"),
            rand().alias("value1"),
            rand().alias("value2")
        )
        start = time.time()
        agg_df = df.groupBy("group_key").agg(
            count("*").alias("cnt"),
            _sum("value1").alias("sum_v1"),
            avg("value2").alias("avg_v2"),
            stddev("value1").alias("std_v1")
        )
        agg_df.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2)
        })
        print(f"[MICRO-AGG] Iter {i+1}: {elapsed_ms:.2f}ms, {throughput:.0f} rec/s")

    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Aggregate",
        "description": "GroupBy with count/sum/avg/stddev aggregation",
        "data_size_rows": data_size,
        "iterations": iterations,
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "iterations_detail": results
    }


def run_join_benchmark(spark, data_size, iterations=3):
    """Benchmark: Join operations"""
    results = []
    print(f"[MICRO-JOIN] Running join benchmark with {data_size} rows, {iterations} iterations")

    small_size = data_size // 100

    for i in range(iterations):
        large_df = spark.range(data_size).select(
            col("id").alias("large_id"),
            (col("id") % small_size).alias("join_key"),
            rand().alias("large_val")
        )
        small_df = spark.range(small_size).select(
            col("id").alias("join_key"),
            rand().alias("small_val")
        )

        # Sort-merge join
        start = time.time()
        joined = large_df.join(small_df, "join_key")
        joined.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2)
        })
        print(f"[MICRO-JOIN] Iter {i+1}: {elapsed_ms:.2f}ms, {throughput:.0f} rec/s")

    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Join",
        "description": "Sort-merge join of large table (1M rows) with small table (10K rows)",
        "data_size_rows": data_size,
        "iterations": iterations,
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "iterations_detail": results
    }


def run_scan_benchmark(spark, data_size, iterations=3):
    """Benchmark: Data scan and filter throughput"""
    results = []
    print(f"[MICRO-SCAN] Running scan benchmark with {data_size} rows, {iterations} iterations")

    for i in range(iterations):
        df = spark.range(data_size).select(
            col("id"),
            rand().alias("value")
        )
        start = time.time()
        filtered = df.filter(col("value") > 0.5)
        filtered.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2)
        })
        print(f"[MICRO-SCAN] Iter {i+1}: {elapsed_ms:.2f}ms, {throughput:.0f} rec/s")

    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Scan",
        "description": "Full DataFrame scan with single-column filter",
        "data_size_rows": data_size,
        "iterations": iterations,
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "iterations_detail": results
    }


def run_wordcount_benchmark(spark, data_size, iterations=3):
    """Benchmark: WordCount (classic MapReduce pattern)"""
    results = []
    num_words = data_size
    print(f"[MICRO-WC] Running wordCount benchmark with {num_words} words, {iterations} iterations")

    for i in range(iterations):
        rdd = spark.sparkContext.parallelize(range(num_words), os.cpu_count() or 4)
        start = time.time()
        wc_rdd = rdd.flatMap(lambda x: [f"word_{x % 1000}"] * 10) \
                     .map(lambda w: (w, 1)) \
                     .reduceByKey(lambda a, b: a + b)
        wc_count = wc_rdd.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = num_words / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2)
        })
        print(f"[MICRO-WC] Iter {i+1}: {elapsed_ms:.2f}ms, {throughput:.0f} rec/s")

    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "WordCount",
        "description": "Classic MapReduce word count pattern on RDD",
        "data_size_rows": num_words,
        "iterations": iterations,
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "iterations_detail": results
    }


def run_shuffle_benchmark(spark, data_size, iterations=3):
    """Benchmark: Shuffle (repartition) performance"""
    results = []
    print(f"[MICRO-SHUFFLE] Running shuffle benchmark with {data_size} rows, {iterations} iterations")

    for i in range(iterations):
        df = spark.range(data_size).select(
            col("id"),
            (col("id") % 100).alias("partition_key"),
            rand().alias("value")
        )
        start = time.time()
        repartitioned = df.repartition(100, "partition_key")
        repartitioned.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2)
        })
        print(f"[MICRO-SHUFFLE] Iter {i+1}: {elapsed_ms:.2f}ms, {throughput:.0f} rec/s")

    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Shuffle",
        "description": "Repartition DataFrame by key (shuffle across partitions)",
        "data_size_rows": data_size,
        "iterations": iterations,
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "iterations_detail": results
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: micro_benchmark.py <data_size_rows> <result_dir>")
        sys.exit(1)

    data_size = int(sys.argv[1])
    result_dir = sys.argv[2]
    iterations = 3

    spark = SparkSession.builder \
        .appName("Spark-Micro-Benchmark-ARM64") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", os.cpu_count() or 4) \
        .config("spark.sql.adaptive.enabled", "true") \
        .getOrCreate()

    print(f"[MICRO] Starting micro-benchmarks: data_size={data_size}, iterations={iterations}")
    total_start = time.time()

    all_results = []
    all_results.append(run_sort_benchmark(spark, data_size, iterations))
    all_results.append(run_aggregate_benchmark(spark, data_size, iterations))
    all_results.append(run_join_benchmark(spark, data_size, iterations))
    all_results.append(run_scan_benchmark(spark, data_size, iterations))
    all_results.append(run_wordcount_benchmark(spark, data_size, iterations))
    all_results.append(run_shuffle_benchmark(spark, data_size, iterations))

    total_elapsed_s = time.time() - total_start

    benchmark_result = {
        "benchmark": "Micro-Benchmarks",
        "timestamp": datetime.now().isoformat(),
        "data_size_rows": data_size,
        "iterations": iterations,
        "total_elapsed_s": round(total_elapsed_s, 2),
        "tests": all_results,
        "description": "Core Spark engine operations: sort, aggregate, join, scan, wordCount, shuffle",
        "reference": "Intel HiBench, Berkeley AMPLab SparkBench"
    }

    result_file = os.path.join(result_dir, f"micro_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(result_file, "w") as f:
        json.dump(benchmark_result, f, indent=2)
    print(f"[MICRO] Results saved to {result_file}")
    print(f"[MICRO] Total benchmark time: {total_elapsed_s:.2f}s")

    spark.stop()


if __name__ == "__main__":
    main()