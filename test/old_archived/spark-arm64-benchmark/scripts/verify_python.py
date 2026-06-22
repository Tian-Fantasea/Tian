#!/usr/bin/env python3
"""Spark Python verification script - tests basic functionality on ARM64"""

from pyspark.sql import SparkSession
import sys

def main():
    spark = SparkSession.builder \
        .appName("SparkARM64Verify") \
        .master("local[2]") \
        .getOrCreate()

    sc = spark.sparkContext

    # Test 1: RDD creation and count
    rdd = sc.parallelize(range(1, 1001), 2)
    count = rdd.count()
    print(f"[VERIFY] RDD count result: {count} (expected: 1000)")

    # Test 2: DataFrame creation and SQL
    df = spark.range(1, 1000)
    df.createOrReplaceTempView("verify_table")
    result = spark.sql("SELECT COUNT(*) as cnt FROM verify_table").collect()
    print(f"[VERIFY] SQL count result: {result[0]['cnt']} (expected: 999)")

    # Test 3: Spark version
    print(f"[VERIFY] Spark version: {spark.version}")

    # Test 4: Simple aggregation
    agg_result = rdd.reduce(lambda a, b: a + b)
    print(f"[VERIFY] RDD sum result: {agg_result} (expected: 500500)")

    # Test 5: DataFrame aggregation
    df_agg = spark.range(1, 1000).groupBy().sum("id")
    sum_val = df_agg.collect()[0]["sum(id)"]
    print(f"[VERIFY] DataFrame sum result: {sum_val}")

    spark.stop()
    print("[VERIFY] All Python tests PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())