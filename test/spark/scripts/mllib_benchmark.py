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
ML_DATA_SIZE = int(os.environ.get("ML_DATA_SIZE", "10000"))
ITERATIONS = int(os.environ.get("ITERATIONS", "1"))

from pyspark.sql import SparkSession
from pyspark.ml.classification import LogisticRegression, RandomForestClassifier
from pyspark.ml.clustering import KMeans
from pyspark.ml.regression import LinearRegression
from pyspark.ml.recommendation import ALS
from pyspark.ml.evaluation import BinaryClassificationEvaluator, RegressionEvaluator
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.sql.functions import rand, col, floor


def generate_classification_data(spark, num_samples, num_features=20):
    df = spark.range(num_samples).select(
        col("id"), (col("id") % 2).alias("label")
    )
    for i in range(num_features):
        df = df.withColumn(f"feature_{i}", rand())
    assembler = VectorAssembler(
        inputCols=[f"feature_{i}" for i in range(num_features)],
        outputCol="raw_features"
    )
    df = assembler.transform(df)
    scaler = StandardScaler(inputCol="raw_features", outputCol="features")
    df = scaler.fit(df).transform(df)
    return df.select("label", "features")


def generate_regression_data(spark, num_samples, num_features=10):
    df = spark.range(num_samples)
    for i in range(num_features):
        df = df.withColumn(f"feature_{i}", rand())
    df = df.withColumn("label", rand())
    assembler = VectorAssembler(
        inputCols=[f"feature_{i}" for i in range(num_features)],
        outputCol="features"
    )
    df = assembler.transform(df)
    return df.select("label", "features")


def generate_clustering_data(spark, num_samples, num_features=10):
    df = spark.range(num_samples)
    for i in range(num_features):
        df = df.withColumn(f"feature_{i}", rand())
    assembler = VectorAssembler(
        inputCols=[f"feature_{i}" for i in range(num_features)],
        outputCol="features"
    )
    df = assembler.transform(df)
    return df.select("features")


def run_logistic_regression(spark, data_size, iterations):
    results = []
    print(f"[MLLIB-LR] {data_size} samples, {iterations} iterations")
    for i in range(iterations):
        data = generate_classification_data(spark, data_size, 20)
        train, test = data.randomSplit([0.8, 0.2], seed=42)
        start = time.time()
        lr = LogisticRegression(maxIter=100, regParam=0.01)
        model = lr.fit(train)
        train_time_ms = (time.time() - start) * 1000
        start_pred = time.time()
        predictions = model.transform(test)
        pred_count = predictions.count()
        pred_time_ms = (time.time() - start_pred) * 1000
        evaluator = BinaryClassificationEvaluator(metricName="areaUnderROC")
        auc = evaluator.evaluate(predictions)
        results.append({
            "iteration": i + 1,
            "train_time_ms": round(train_time_ms, 2),
            "predict_time_ms": round(pred_time_ms, 2),
            "avg_latency_ms": round(train_time_ms, 2),
            "auc": round(auc, 4)
        })
        print(f"[MLLIB-LR] Iter {i+1}: train={train_time_ms:.2f}ms, predict={pred_time_ms:.2f}ms")
    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "LogisticRegression",
        "description": "Binary classification with 20 features, maxIter=100",
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "avg_latency_ms": round(avg_train, 2)
    }


def run_random_forest(spark, data_size, iterations):
    results = []
    print(f"[MLLIB-RF] {data_size} samples, {iterations} iterations")
    for i in range(iterations):
        data = generate_classification_data(spark, data_size, 20)
        train, test = data.randomSplit([0.8, 0.2], seed=42)
        start = time.time()
        rf = RandomForestClassifier(numTrees=50, maxDepth=10, seed=42)
        model = rf.fit(train)
        train_time_ms = (time.time() - start) * 1000
        start_pred = time.time()
        predictions = model.transform(test)
        pred_count = predictions.count()
        pred_time_ms = (time.time() - start_pred) * 1000
        evaluator = BinaryClassificationEvaluator(metricName="areaUnderROC")
        auc = evaluator.evaluate(predictions)
        results.append({
            "iteration": i + 1,
            "train_time_ms": round(train_time_ms, 2),
            "predict_time_ms": round(pred_time_ms, 2),
            "avg_latency_ms": round(train_time_ms, 2),
            "auc": round(auc, 4)
        })
        print(f"[MLLIB-RF] Iter {i+1}: train={train_time_ms:.2f}ms, predict={pred_time_ms:.2f}ms")
    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "RandomForest",
        "description": "Classification with 50 trees, maxDepth=10",
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "avg_latency_ms": round(avg_train, 2)
    }


def run_kmeans(spark, data_size, iterations):
    results = []
    print(f"[MLLIB-KM] {data_size} samples, {iterations} iterations")
    for i in range(iterations):
        data = generate_clustering_data(spark, data_size, 10)
        start = time.time()
        km = KMeans(k=5, maxIter=50, seed=42)
        model = km.fit(data)
        train_time_ms = (time.time() - start) * 1000
        start_pred = time.time()
        predictions = model.transform(data)
        pred_count = predictions.count()
        pred_time_ms = (time.time() - start_pred) * 1000
        cost = model.summary.trainingCost
        results.append({
            "iteration": i + 1,
            "train_time_ms": round(train_time_ms, 2),
            "predict_time_ms": round(pred_time_ms, 2),
            "avg_latency_ms": round(train_time_ms, 2),
            "training_cost": round(cost, 4)
        })
        print(f"[MLLIB-KM] Iter {i+1}: train={train_time_ms:.2f}ms")
    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "KMeans",
        "description": "Clustering with k=5, maxIter=50, 10 features",
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "avg_latency_ms": round(avg_train, 2)
    }


def run_als(spark, data_size, iterations):
    results = []
    print(f"[MLLIB-ALS] {data_size} ratings, {iterations} iterations")
    num_users = data_size // 10
    num_items = 100
    for i in range(iterations):
        ratings = spark.range(data_size).select(
            floor(rand() * num_users).alias("userId"),
            floor(rand() * num_items).alias("itemId"),
            (rand() * 5).alias("rating")
        )
        start = time.time()
        als = ALS(maxIter=10, regParam=0.01, userCol="userId", itemCol="itemId", ratingCol="rating")
        model = als.fit(ratings)
        train_time_ms = (time.time() - start) * 1000
        start_pred = time.time()
        predictions = model.transform(ratings)
        pred_count = predictions.count()
        pred_time_ms = (time.time() - start_pred) * 1000
        results.append({
            "iteration": i + 1,
            "train_time_ms": round(train_time_ms, 2),
            "predict_time_ms": round(pred_time_ms, 2),
            "avg_latency_ms": round(train_time_ms, 2)
        })
        print(f"[MLLIB-ALS] Iter {i+1}: train={train_time_ms:.2f}ms")
    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "ALS",
        "description": "Collaborative filtering recommendation, maxIter=10",
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "avg_latency_ms": round(avg_train, 2)
    }


def main():
    data_size = int(sys.argv[1]) if len(sys.argv) > 1 else ML_DATA_SIZE
    result_dir = sys.argv[2] if len(sys.argv) > 2 else RESULTS_DIR

    os.makedirs(result_dir, exist_ok=True)

    spark = SparkSession.builder \
        .appName("Spark-MLlib-Benchmark-ARM64") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", os.cpu_count() or 4) \
        .getOrCreate()

    print(f"[MLLIB] Starting MLlib benchmarks: data_size={data_size}, iterations={ITERATIONS}")
    total_start = time.time()

    all_results = []
    all_results.append(run_logistic_regression(spark, data_size, ITERATIONS))
    all_results.append(run_random_forest(spark, data_size, ITERATIONS))
    all_results.append(run_kmeans(spark, data_size, ITERATIONS))
    all_results.append(run_als(spark, data_size, ITERATIONS))

    total_elapsed_s = time.time() - total_start
    avg_latency_ms = sum(r["avg_latency_ms"] for r in all_results) / len(all_results)

    benchmark_result = {
        "benchmark": "MLlib",
        "description": "ML algorithms: LogisticRegression, RandomForest, KMeans, ALS",
        "reference": "HiBench ML benchmarks, Spark MLlib documentation",
        "software": "spark",
        "version": spark.version,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "avg_latency_ms": {
                "unit": "ms",
                "description": "Average training latency per ML algorithm"
            },
            "avg_train_time_ms": {
                "unit": "ms",
                "description": "Average model training time"
            }
        },
        "dataset_info": {
            "name": "Generated synthetic",
            "size": f"{data_size} samples",
            "source": "Spark range() + rand()"
        },
        "data_size_samples": data_size,
        "total_elapsed_s": round(total_elapsed_s, 2),
        "avg_latency_ms": round(avg_latency_ms, 2),
        "results": all_results
    }

    output_file = os.path.join(result_dir, "mllib_benchmark.json")
    with open(output_file, "w") as f:
        json.dump(benchmark_result, f, indent=2)
    print(f"[MLLIB] Results saved to {output_file}")

    spark.stop()


if __name__ == "__main__":
    main()
