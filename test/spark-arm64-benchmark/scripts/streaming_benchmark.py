#!/usr/bin/env python3
"""
Spark Structured Streaming Benchmark for ARM64
Measures streaming data processing throughput and latency

Reference: HiBench Streaming benchmarks
           https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html

Performance Metrics:
  - Throughput (records/s)
  - Processing latency per micro-batch (ms)
  - End-to-end processing time (ms)

Dataset: Spark built-in rate source
"""

import sys
import os
import json
import time
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum as _sum, avg, window


def run_streaming_benchmark(spark, rows_per_second, result_dir, duration_seconds=30):
    """Benchmark: Structured Streaming throughput"""
    print(f"[STREAM] Running streaming benchmark at {rows_per_second} rows/s for {duration_seconds}s")

    checkpoint_dir = os.path.join(result_dir, "stream_checkpoint")
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Create rate source streaming DataFrame
    rate_df = spark.readStream \
        .format("rate") \
        .option("rowsPerSecond", rows_per_second) \
        .load()

    # Simple processing: count and aggregate per window
    aggregated = rate_df \
        .withWatermark("timestamp", "5 seconds") \
        .groupBy(window(col("timestamp"), "1 second")) \
        .agg(
            count("*").alias("count"),
            _sum("value").alias("sum_value"),
            avg("value").alias("avg_value")
        )

    # Write to memory sink for measurement
    query = aggregated.writeStream \
        .format("memory") \
        .queryName("stream_benchmark_results") \
        .outputMode("complete") \
        .option("checkpointLocation", checkpoint_dir) \
        .trigger(processingTime="1 second") \
        .start()

    # Collect metrics during streaming
    batch_metrics = []
    start_time = time.time()

    while query.isActive and (time.time() - start_time) < duration_seconds:
        try:
            progress = query.lastProgress
            if progress:
                batch_metrics.append({
                    "batchId": progress.get("batchId", 0),
                    "numInputRows": progress.get("numInputRows", 0),
                    "inputRowsPerSecond": progress.get("inputRowsPerSecond", 0),
                    "processedRowsPerSecond": progress.get("processedRowsPerSecond", 0),
                    "durationMs": progress.get("durationMs", {}),
                    "timestamp": progress.get("timestamp", "")
                })
                print(f"[STREAM] Batch {progress.get('batchId', 0)}: "
                      f"input={progress.get('inputRowsPerSecond', 0):.0f} r/s, "
                      f"processed={progress.get('processedRowsPerSecond', 0):.0f} r/s")
        except Exception:
            pass
        time.sleep(2)

    query.stop()

    total_elapsed_s = time.time() - start_time

    # Compute summary metrics
    if batch_metrics:
        avg_throughput = sum(b["processedRowsPerSecond"] for b in batch_metrics) / len(batch_metrics)
        avg_batch_duration = sum(b["durationMs"].get("triggerExecution", 0) for b in batch_metrics) / len(batch_metrics)
        total_rows = sum(b["numInputRows"] for b in batch_metrics)
    else:
        avg_throughput = 0
        avg_batch_duration = 0
        total_rows = 0

    benchmark_result = {
        "benchmark": "Structured Streaming",
        "timestamp": datetime.now().isoformat(),
        "rows_per_second": rows_per_second,
        "duration_seconds": duration_seconds,
        "total_elapsed_s": round(total_elapsed_s, 2),
        "total_rows_processed": total_rows,
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_batch_duration_ms": round(avg_batch_duration, 2),
        "batch_count": len(batch_metrics),
        "batch_metrics": batch_metrics,
        "description": "Rate source -> windowed aggregation -> memory sink streaming pipeline",
        "reference": "HiBench Streaming, Spark Structured Streaming docs"
    }

    result_file = os.path.join(result_dir, f"streaming_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(result_file, "w") as f:
        json.dump(benchmark_result, f, indent=2)
    print(f"[STREAM] Results saved to {result_file}")

    return benchmark_result


def main():
    if len(sys.argv) < 3:
        print("Usage: streaming_benchmark.py <rows_per_second> <result_dir>")
        sys.exit(1)

    rows_per_second = int(sys.argv[1])
    result_dir = sys.argv[2]

    spark = SparkSession.builder \
        .appName("Spark-Streaming-Benchmark-ARM64") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", os.cpu_count() or 4) \
        .getOrCreate()

    run_streaming_benchmark(spark, rows_per_second, result_dir)
    spark.stop()


if __name__ == "__main__":
    main()