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
STREAM_RATE = int(os.environ.get("STREAM_RATE", "10000"))
STREAM_DURATION = int(os.environ.get("STREAM_DURATION", "10"))

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum as _sum, avg, window


def run_streaming_benchmark(rows_per_second, result_dir, duration_seconds):
    os.makedirs(result_dir, exist_ok=True)

    spark = SparkSession.builder \
        .appName("Spark-Streaming-Benchmark-ARM64") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", os.cpu_count() or 4) \
        .getOrCreate()

    print(f"[STREAM] Running streaming benchmark at {rows_per_second} rows/s for {duration_seconds}s")

    checkpoint_dir = os.path.join(result_dir, "stream_checkpoint")
    os.makedirs(checkpoint_dir, exist_ok=True)

    rate_df = spark.readStream \
        .format("rate") \
        .option("rowsPerSecond", rows_per_second) \
        .load()

    aggregated = rate_df \
        .withWatermark("timestamp", "5 seconds") \
        .groupBy(window(col("timestamp"), "1 second")) \
        .agg(
            count("*").alias("count"),
            _sum("value").alias("sum_value"),
            avg("value").alias("avg_value")
        )

    query = aggregated.writeStream \
        .format("memory") \
        .queryName("stream_benchmark_results") \
        .outputMode("complete") \
        .option("checkpointLocation", checkpoint_dir) \
        .trigger(processingTime="1 second") \
        .start()

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
                    "avg_latency_ms": progress.get("durationMs", {}).get("triggerExecution", 0),
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

    if batch_metrics:
        avg_throughput = sum(b["processedRowsPerSecond"] for b in batch_metrics) / len(batch_metrics)
        avg_batch_duration = sum(b.get("avg_latency_ms", 0) for b in batch_metrics) / len(batch_metrics)
        total_rows = sum(b["numInputRows"] for b in batch_metrics)
    else:
        avg_throughput = 0
        avg_batch_duration = 0
        total_rows = 0

    benchmark_result = {
        "benchmark": "Structured Streaming",
        "description": "Rate source -> windowed aggregation -> memory sink streaming pipeline",
        "reference": "HiBench Streaming, Spark Structured Streaming documentation",
        "software": "spark",
        "version": spark.version,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "avg_throughput_records_per_s": {
                "unit": "records/s",
                "description": "Average streaming processing throughput"
            },
            "avg_latency_ms": {
                "unit": "ms",
                "description": "Average batch processing latency"
            }
        },
        "dataset_info": {
            "name": "Spark rate source",
            "size": f"{rows_per_second} rows/s for {duration_seconds}s",
            "source": "Spark built-in rate source"
        },
        "rows_per_second": rows_per_second,
        "duration_seconds": duration_seconds,
        "total_elapsed_s": round(total_elapsed_s, 2),
        "total_rows_processed": total_rows,
        "avg_throughput_records_per_s": round(avg_throughput, 2),
        "avg_latency_ms": round(avg_batch_duration, 2),
        "average_latency_ms": round(avg_batch_duration, 2),
        "results": batch_metrics
    }

    output_file = os.path.join(result_dir, "benchmark_secondary.json")
    with open(output_file, "w") as f:
        json.dump(benchmark_result, f, indent=2)
    print(f"[STREAM] Results saved to {output_file}")

    spark.stop()
    return benchmark_result


def main():
    rows_per_second = int(sys.argv[1]) if len(sys.argv) > 1 else STREAM_RATE
    result_dir = sys.argv[2] if len(sys.argv) > 2 else RESULTS_DIR

    run_streaming_benchmark(rows_per_second, result_dir, STREAM_DURATION)


if __name__ == "__main__":
    main()
