#!/usr/bin/env python3
"""
TPC-DS Benchmark Runner for Spark ARM64
Executes TPC-DS queries against generated data and measures performance

Reference: https://www.tpc.org/tpcds/
           Databricks TPC-DS benchmark: https://github.com/databricks/spark-sql-perf
           Amazon EMR Spark benchmarks use TPC-DS at SF=3TB/10TB

Performance Metrics:
  - Query execution time (ms) per query
  - Throughput: queries completed per hour
  - Resource utilization: CPU, memory, shuffle data volume

Dataset: TPC-DS parquet tables at specified scale factor
"""

import sys
import os
import json
import time
import re
from datetime import datetime

from pyspark.sql import SparkSession


TPCDS_QUERIES = {
    "q1": """
        SELECT ss_customer_sk, SUM(ss_quantity) as total_qty,
               SUM(ss_net_paid) as total_paid
        FROM store_sales
        WHERE ss_sold_date_sk BETWEEN 1 AND 30
        GROUP BY ss_customer_sk
        ORDER BY total_paid DESC
        LIMIT 100
    """,
    "q2": """
        SELECT ss_item_sk, AVG(ss_quantity) as avg_qty,
               AVG(ss_sales_price) as avg_price
        FROM store_sales
        GROUP BY ss_item_sk
        ORDER BY avg_price DESC
        LIMIT 100
    """,
    "q3": """
        SELECT d.d_month, SUM(ss.ss_quantity) as total_qty
        FROM store_sales ss
        JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
        GROUP BY d.d_month
        ORDER BY d.d_month
    """,
    "q4": """
        SELECT ss_store_sk, COUNT(*) as cnt,
               SUM(ss_net_paid) as total_sales
        FROM store_sales
        GROUP BY ss_store_sk
        ORDER BY total_sales DESC
        LIMIT 10
    """,
    "q5": """
        SELECT i.i_item_desc, AVG(ss.ss_quantity) as avg_qty
        FROM store_sales ss
        JOIN item i ON ss.ss_item_sk = i.i_item_sk
        GROUP BY i.i_item_desc
        ORDER BY avg_qty DESC
        LIMIT 50
    """,
    "q6": """
        SELECT ss_customer_sk,
               SUM(CASE WHEN ss_quantity > 5 THEN ss_quantity ELSE 0 END) as large_qty,
               SUM(CASE WHEN ss_quantity <= 5 THEN ss_quantity ELSE 0 END) as small_qty
        FROM store_sales
        GROUP BY ss_customer_sk
        ORDER BY large_qty DESC
        LIMIT 100
    """,
    "q7": """
        SELECT d_year, i_item_sk, SUM(ss_net_paid) as total_sales
        FROM store_sales
        JOIN date_dim ON ss_sold_date_sk = date_dim.d_date_sk
        JOIN item ON ss_item_sk = item.i_item_sk
        GROUP BY d_year, i_item_sk
        ORDER BY d_year, total_sales DESC
        LIMIT 100
    """,
    "q8": """
        SELECT ss_store_sk, COUNT(DISTINCT ss_customer_sk) as unique_customers
        FROM store_sales
        GROUP BY ss_store_sk
        ORDER BY unique_customers DESC
        LIMIT 10
    """,
    "q9": """
        SELECT ss_sold_date_sk, SUM(ss_net_paid) as daily_sales
        FROM store_sales
        GROUP BY ss_sold_date_sk
        ORDER BY ss_sold_date_sk
        LIMIT 30
    """,
    "q10": """
        SELECT c_customer_sk, SUM(ss_quantity) as total_qty,
               SUM(ss_net_paid) as total_paid,
               COUNT(*) as order_count
        FROM store_sales ss
        JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
        GROUP BY c_customer_sk
        ORDER BY total_paid DESC
        LIMIT 100
    """,
    "q11": """
        SELECT ss_item_sk, ss_store_sk, SUM(ss_quantity) as qty
        FROM store_sales
        GROUP BY ss_item_sk, ss_store_sk
        ORDER BY qty DESC
        LIMIT 50
    """,
    "q12": """
        SELECT AVG(ss_quantity) as avg_qty,
               AVG(ss_sales_price) as avg_price,
               STDDEV(ss_quantity) as std_qty
        FROM store_sales
    """,
    "q13": """
        SELECT ss_promo_sk, COUNT(*) as cnt,
               SUM(ss_net_paid) as promo_sales
        FROM store_sales
        GROUP BY ss_promo_sk
        ORDER BY promo_sales DESC
        LIMIT 10
    """,
    "q14": """
        SELECT ss_customer_sk,
               SUM(ss_net_paid) / COUNT(*) as avg_order_value
        FROM store_sales
        GROUP BY ss_customer_sk
        HAVING COUNT(*) > 5
        ORDER BY avg_order_value DESC
        LIMIT 100
    """,
    "q15": """
        SELECT d_month, ss_store_sk, SUM(ss_quantity) as total_qty
        FROM store_sales
        JOIN date_dim ON ss_sold_date_sk = date_dim.d_date_sk
        GROUP BY d_month, ss_store_sk
        ORDER BY d_month, total_qty DESC
    """,
}


def run_tpcds_benchmark(spark, data_dir, result_dir, scale_factor):
    """Run TPC-DS queries and collect performance metrics"""
    print(f"[TPCDS] Loading TPC-DS data from {data_dir} (SF={scale_factor})")

    for table_name in ["store_sales", "store_returns", "web_sales",
                       "customer", "date_dim", "item"]:
        table_path = os.path.join(data_dir, table_name)
        if os.path.exists(table_path):
            spark.read.parquet(table_path).createOrReplaceTempView(table_name)
            row_count = spark.table(table_name).count()
            print(f"[TPCDS] Loaded table {table_name}: {row_count} rows")
        else:
            print(f"[TPCDS] Warning: table {table_name} not found at {table_path}")

    results = []
    total_start = time.time()
    successful_queries = 0
    total_query_time = 0

    for qname, qsql in TPCDS_QUERIES.items():
        print(f"[TPCDS] Running {qname}...")
        q_start = time.time()
        try:
            df = spark.sql(qsql)
            row_count = df.count()
            df.collect()
            q_elapsed_ms = (time.time() - q_start) * 1000

            metrics = {
                "query": qname,
                "elapsed_ms": round(q_elapsed_ms, 2),
                "row_count": row_count,
                "status": "SUCCESS"
            }

            successful_queries += 1
            total_query_time += q_elapsed_ms
            print(f"[TPCDS] {qname}: {q_elapsed_ms:.2f}ms, {row_count} rows")

        except Exception as e:
            q_elapsed_ms = (time.time() - q_start) * 1000
            metrics = {
                "query": qname,
                "elapsed_ms": round(q_elapsed_ms, 2),
                "row_count": 0,
                "status": f"FAILED: {str(e)[:100]}"
            }
            print(f"[TPCDS] {qname}: FAILED - {str(e)[:100]}")

        results.append(metrics)

    total_elapsed_s = time.time() - total_start

    throughput_qph = successful_queries / total_elapsed_s * 3600 if total_elapsed_s > 0 else 0

    benchmark_result = {
        "benchmark": "TPC-DS",
        "scale_factor_gb": scale_factor,
        "timestamp": datetime.now().isoformat(),
        "total_elapsed_s": round(total_elapsed_s, 2),
        "successful_queries": successful_queries,
        "total_queries": len(TPCDS_QUERIES),
        "throughput_qph": round(throughput_qph, 2),
        "avg_query_time_ms": round(total_query_time / successful_queries, 2) if successful_queries > 0 else 0,
        "queries": results,
        "description": "TPC-DS analytical queries simulating a retail data warehouse workload",
        "reference": "https://www.tpc.org/tpcds/, Databricks spark-sql-perf"
    }

    result_file = os.path.join(result_dir, f"tpcds_results_sf{scale_factor}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(result_file, "w") as f:
        json.dump(benchmark_result, f, indent=2)
    print(f"[TPCDS] Results saved to {result_file}")

    return benchmark_result


def main():
    if len(sys.argv) < 4:
        print("Usage: tpcds_benchmark.py <data_dir> <result_dir> <scale_factor>")
        sys.exit(1)

    data_dir = sys.argv[1]
    result_dir = sys.argv[2]
    scale_factor = int(sys.argv[3])

    spark = SparkSession.builder \
        .appName(f"TPCDS-Benchmark-SF{scale_factor}") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", os.cpu_count() or 4) \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.shuffle.partition.enabled", "true") \
        .config("spark.sql.adaptive.skewJoin.enabled", "true") \
        .config("spark.driver.extraJavaOptions", "-XX:+UseG1GC") \
        .getOrCreate()

    run_tpcds_benchmark(spark, data_dir, result_dir, scale_factor)
    spark.stop()


if __name__ == "__main__":
    main()