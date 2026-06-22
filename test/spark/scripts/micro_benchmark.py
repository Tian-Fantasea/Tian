#!/usr/bin/env python3
import sys
import os
import json
import time
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.environ.get(
    "RESULTS_DIR",
    os.path.join(os.path.dirname(SCRIPT_DIR), "results")
)
SPARK_HOME = os.environ.get("SPARK_HOME", os.path.join(os.path.dirname(SCRIPT_DIR), "spark"))
ITERATIONS = int(os.environ.get("ITERATIONS", "1"))
MICRO_DATA_SIZE = int(os.environ.get("MICRO_DATA_SIZE", "100000"))

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, rand, count, sum as _sum, avg, stddev


def run_sort_benchmark(spark, data_size, iterations):
    results = []
    print(f"[MICRO-SORT] data_size={data_size}, iterations={iterations}")
    for i in range(iterations):
        df = spark.range(data_size).select(col("id"), rand().alias("sort_key"))
        start = time.time()
        sorted_df = df.sort("sort_key")
        sorted_df.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2),
            "avg_latency_ms": round(elapsed_ms / data_size, 4)
        })
        print(f"[MICRO-SORT] Iter {i+1}: {elapsed_ms:.2f}ms, {throughput:.0f} rec/s")
    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Sort",
        "description": "Sort DataFrame by random key column",
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_latency_ms": round(avg_ms / data_size, 4)
    }


def run_aggregate_benchmark(spark, data_size, iterations):
    results = []
    print(f"[MICRO-AGG] data_size={data_size}, iterations={iterations}")
    for i in range(iterations):
        df = spark.range(data_size).select(
            col("id"), (col("id") % 100).alias("group_key"),
            rand().alias("value1"), rand().alias("value2")
        )
        start = time.time()
        agg_df = df.groupBy("group_key").agg(
            count("*").alias("cnt"), _sum("value1").alias("sum_v1"),
            avg("value2").alias("avg_v2"), stddev("value1").alias("std_v1")
        )
        agg_df.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2),
            "avg_latency_ms": round(elapsed_ms / data_size, 4)
        })
        print(f"[MICRO-AGG] Iter {i+1}: {elapsed_ms:.2f}ms")
    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Aggregate",
        "description": "GroupBy with count/sum/avg/stddev aggregation",
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_latency_ms": round(avg_ms / data_size, 4)
    }


def run_join_benchmark(spark, data_size, iterations):
    results = []
    small_size = data_size // 100
    print(f"[MICRO-JOIN] data_size={data_size}, iterations={iterations}")
    for i in range(iterations):
        large_df = spark.range(data_size).select(
            col("id").alias("large_id"),
            (col("id") % small_size).alias("join_key"),
            rand().alias("large_val")
        )
        small_df = spark.range(small_size).select(
            col("id").alias("join_key"), rand().alias("small_val")
        )
        start = time.time()
        joined = large_df.join(small_df, "join_key")
        joined.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2),
            "avg_latency_ms": round(elapsed_ms / data_size, 4)
        })
        print(f"[MICRO-JOIN] Iter {i+1}: {elapsed_ms:.2f}ms")
    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Join",
        "description": "Sort-merge join of large table with small table",
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_latency_ms": round(avg_ms / data_size, 4)
    }


def run_scan_benchmark(spark, data_size, iterations):
    results = []
    print(f"[MICRO-SCAN] data_size={data_size}, iterations={iterations}")
    for i in range(iterations):
        df = spark.range(data_size).select(col("id"), rand().alias("value"))
        start = time.time()
        filtered = df.filter(col("value") > 0.5)
        filtered.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2),
            "avg_latency_ms": round(elapsed_ms / data_size, 4)
        })
        print(f"[MICRO-SCAN] Iter {i+1}: {elapsed_ms:.2f}ms")
    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Scan",
        "description": "Full DataFrame scan with single-column filter",
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_latency_ms": round(avg_ms / data_size, 4)
    }


def run_wordcount_benchmark(spark, data_size, iterations):
    results = []
    print(f"[MICRO-WC] data_size={data_size}, iterations={iterations}")
    for i in range(iterations):
        rdd = spark.sparkContext.parallelize(range(data_size), os.cpu_count() or 4)
        start = time.time()
        wc_rdd = rdd.flatMap(lambda x: [f"word_{x % 1000}"] * 10) \
                     .map(lambda w: (w, 1)) \
                     .reduceByKey(lambda a, b: a + b)
        wc_rdd.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2),
            "avg_latency_ms": round(elapsed_ms / data_size, 4)
        })
        print(f"[MICRO-WC] Iter {i+1}: {elapsed_ms:.2f}ms")
    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "WordCount",
        "description": "Classic MapReduce word count pattern on RDD",
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_latency_ms": round(avg_ms / data_size, 4)
    }


def run_shuffle_benchmark(spark, data_size, iterations):
    results = []
    print(f"[MICRO-SHUFFLE] data_size={data_size}, iterations={iterations}")
    for i in range(iterations):
        df = spark.range(data_size).select(
            col("id"), (col("id") % 100).alias("partition_key"), rand().alias("value")
        )
        start = time.time()
        repartitioned = df.repartition(100, "partition_key")
        repartitioned.count()
        elapsed_ms = (time.time() - start) * 1000
        throughput = data_size / (elapsed_ms / 1000)
        results.append({
            "iteration": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "throughput_records_per_s": round(throughput, 2),
            "avg_latency_ms": round(elapsed_ms / data_size, 4)
        })
        print(f"[MICRO-SHUFFLE] Iter {i+1}: {elapsed_ms:.2f}ms")
    avg_ms = sum(r["elapsed_ms"] for r in results) / len(results)
    avg_throughput = sum(r["throughput_records_per_s"] for r in results) / len(results)
    return {
        "test": "Shuffle",
        "description": "Repartition DataFrame by key (shuffle across partitions)",
        "avg_elapsed_ms": round(avg_ms, 2),
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_latency_ms": round(avg_ms / data_size, 4)
    }


def main():
    data_size = int(sys.argv[1]) if len(sys.argv) > 1 else MICRO_DATA_SIZE
    result_dir = sys.argv[2] if len(sys.argv) > 2 else RESULTS_DIR

    os.makedirs(result_dir, exist_ok=True)

    spark = SparkSession.builder \
        .appName("Spark-Micro-Benchmark-ARM64") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", os.cpu_count() or 4) \
        .config("spark.sql.adaptive.enabled", "true") \
        .getOrCreate()

    print(f"[MICRO] Starting micro-benchmarks: data_size={data_size}, iterations={ITERATIONS}")
    total_start = time.time()

    all_results = []
    all_results.append(run_sort_benchmark(spark, data_size, ITERATIONS))
    all_results.append(run_aggregate_benchmark(spark, data_size, ITERATIONS))
    all_results.append(run_join_benchmark(spark, data_size, ITERATIONS))
    all_results.append(run_scan_benchmark(spark, data_size, ITERATIONS))
    all_results.append(run_wordcount_benchmark(spark, data_size, ITERATIONS))
    all_results.append(run_shuffle_benchmark(spark, data_size, ITERATIONS))

    total_elapsed_s = time.time() - total_start
    avg_latency_ms = sum(r["avg_latency_ms"] for r in all_results) / len(all_results)

    benchmark_result = {
        "benchmark": "Micro-Benchmarks",
        "description": "Core Spark engine operations: sort, aggregate, join, scan, wordCount, shuffle",
        "reference": "Intel HiBench, Berkeley AMPLab SparkBench",
        "software": "spark",
        "version": spark.version,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "avg_latency_ms": {
                "unit": "ms",
                "description": "Average latency per micro operation per record"
            },
            "avg_throughput_records_per_s": {
                "unit": "records/s",
                "description": "Average throughput across all micro operations"
            }
        },
        "dataset_info": {
            "name": "Generated",
            "size": f"{data_size} rows",
            "source": "Spark range() + rand()"
        },
        "data_size_rows": data_size,
        "iterations": ITERATIONS,
        "total_elapsed_s": round(total_elapsed_s, 2),
        "avg_latency_ms": round(avg_latency_ms, 4),
        "results": all_results
    }

    output_file = os.path.join(result_dir, "micro_benchmark.json")
    with open(output_file, "w") as f:
        json.dump(benchmark_result, f, indent=2)
    print(f"[MICRO] Results saved to {output_file}")

    spark.stop()


if __name__ == "__main__":
    main()
