#!/usr/bin/env python3
"""
Spark MLlib Benchmarks for ARM64
Evaluates performance of common ML algorithms

Reference: HiBench ML benchmarks, Spark MLlib documentation
           https://spark.apache.org/docs/latest/ml-guide.html

Performance Metrics:
  - Training time (s)
  - Inference/prediction time (ms)
  - Model accuracy metrics (where applicable)

Algorithms:
  1. LogisticRegression  - Binary classification
  2. RandomForest         - Classification with ensemble
  3. KMeans              - Clustering
  4. LinearRegression    - Regression
  5. ALS                 - Collaborative filtering (recommendation)
"""

import sys
import os
import json
import time
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.ml.classification import LogisticRegression, RandomForestClassifier
from pyspark.ml.clustering import KMeans
from pyspark.ml.regression import LinearRegression
from pyspark.ml.recommendation import ALS
from pyspark.ml.evaluation import BinaryClassificationEvaluator, RegressionEvaluator
from pyspark.ml.feature import VectorAssembler, StandardScaler


def generate_classification_data(spark, num_samples, num_features=20):
    """Generate synthetic binary classification data"""
    df = spark.range(num_samples).select(
        col("id"),
        (col("id") % 2).alias("label")
    )
    from pyspark.sql.functions import rand, col
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
    """Generate synthetic regression data"""
    df = spark.range(num_samples)
    from pyspark.sql.functions import rand, col
    for i in range(num_features):
        df = df.withColumn(f"feature_{i}", rand())
    df = df.withColumn("label", rand())
    assembler = VectorAssembler(
        inputCols=[f"feature_{i}" for i in range(num_features)],
        outputCol="features"
    )
    df = assembler.transform(df)
    return df.select("label", "features")


def generate_clustering_data(spark, num_samples, num_features=10, k=5):
    """Generate synthetic clustering data"""
    df = spark.range(num_samples)
    from pyspark.sql.functions import rand, col
    for i in range(num_features):
        df = df.withColumn(f"feature_{i}", rand())
    assembler = VectorAssembler(
        inputCols=[f"feature_{i}" for i in range(num_features)],
        outputCol="features"
    )
    df = assembler.transform(df)
    return df.select("features")


def run_logistic_regression(spark, data_size, iterations=3):
    """Benchmark: Logistic Regression classification"""
    results = []
    print(f"[MLLIB-LR] Running LogisticRegression benchmark, {data_size} samples, {iterations} iterations")

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
            "auc": round(auc, 4),
            "prediction_count": pred_count
        })
        print(f"[MLLIB-LR] Iter {i+1}: train={train_time_ms:.2f}ms, predict={pred_time_ms:.2f}ms, AUC={auc:.4f}")

    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "LogisticRegression",
        "description": "Binary classification with 20 features, maxIter=100",
        "data_size_samples": data_size,
        "iterations": iterations,
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "iterations_detail": results
    }


def run_random_forest(spark, data_size, iterations=3):
    """Benchmark: RandomForest classification"""
    results = []
    print(f"[MLLIB-RF] Running RandomForest benchmark, {data_size} samples, {iterations} iterations")

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
            "auc": round(auc, 4),
            "prediction_count": pred_count
        })
        print(f"[MLLIB-RF] Iter {i+1}: train={train_time_ms:.2f}ms, predict={pred_time_ms:.2f}ms, AUC={auc:.4f}")

    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "RandomForest",
        "description": "Classification with 50 trees, maxDepth=10",
        "data_size_samples": data_size,
        "iterations": iterations,
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "iterations_detail": results
    }


def run_kmeans(spark, data_size, iterations=3):
    """Benchmark: KMeans clustering"""
    results = []
    print(f"[MLLIB-KM] Running KMeans benchmark, {data_size} samples, {iterations} iterations")

    for i in range(iterations):
        data = generate_clustering_data(spark, data_size, 10, k=5)

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
            "training_cost": round(cost, 4)
        })
        print(f"[MLLIB-KM] Iter {i+1}: train={train_time_ms:.2f}ms, predict={pred_time_ms:.2f}ms, cost={cost:.4f}")

    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "KMeans",
        "description": "Clustering with k=5, maxIter=50, 10 features",
        "data_size_samples": data_size,
        "iterations": iterations,
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "iterations_detail": results
    }


def run_linear_regression(spark, data_size, iterations=3):
    """Benchmark: Linear Regression"""
    results = []
    print(f"[MLLIB-LRREG] Running LinearRegression benchmark, {data_size} samples, {iterations} iterations")

    for i in range(iterations):
        data = generate_regression_data(spark, data_size, 10)
        train, test = data.randomSplit([0.8, 0.2], seed=42)

        start = time.time()
        lr = LinearRegression(maxIter=100, regParam=0.01)
        model = lr.fit(train)
        train_time_ms = (time.time() - start) * 1000

        start_pred = time.time()
        predictions = model.transform(test)
        pred_count = predictions.count()
        pred_time_ms = (time.time() - start_pred) * 1000

        evaluator = RegressionEvaluator(metricName="rmse")
        rmse = evaluator.evaluate(predictions)

        results.append({
            "iteration": i + 1,
            "train_time_ms": round(train_time_ms, 2),
            "predict_time_ms": round(pred_time_ms, 2),
            "rmse": round(rmse, 4)
        })
        print(f"[MLLIB-LRREG] Iter {i+1}: train={train_time_ms:.2f}ms, predict={pred_time_ms:.2f}ms, RMSE={rmse:.4f}")

    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "LinearRegression",
        "description": "Regression with 10 features, maxIter=100",
        "data_size_samples": data_size,
        "iterations": iterations,
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "iterations_detail": results
    }


def run_als(spark, data_size, iterations=3):
    """Benchmark: ALS Collaborative Filtering"""
    results = []
    print(f"[MLLIB-ALS] Running ALS benchmark, {data_size} ratings, {iterations} iterations")

    num_users = data_size // 10
    num_items = 100

    for i in range(iterations):
        from pyspark.sql.functions import rand, col, floor
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
            "num_users": num_users,
            "num_items": num_items
        })
        print(f"[MLLIB-ALS] Iter {i+1}: train={train_time_ms:.2f}ms, predict={pred_time_ms:.2f}ms")

    avg_train = sum(r["train_time_ms"] for r in results) / len(results)
    avg_pred = sum(r["predict_time_ms"] for r in results) / len(results)
    return {
        "test": "ALS",
        "description": "Collaborative filtering recommendation, maxIter=10",
        "data_size_samples": data_size,
        "iterations": iterations,
        "avg_train_time_ms": round(avg_train, 2),
        "avg_predict_time_ms": round(avg_pred, 2),
        "iterations_detail": results
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: mllib_benchmark.py <data_size_samples> <result_dir>")
        sys.exit(1)

    data_size = int(sys.argv[1])
    result_dir = sys.argv[2]

    spark = SparkSession.builder \
        .appName("Spark-MLlib-Benchmark-ARM64") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", os.cpu_count() or 4) \
        .getOrCreate()

    print(f"[MLLIB] Starting MLlib benchmarks: data_size={data_size}")
    total_start = time.time()

    all_results = []
    all_results.append(run_logistic_regression(spark, data_size))
    all_results.append(run_random_forest(spark, data_size))
    all_results.append(run_kmeans(spark, data_size))
    all_results.append(run_linear_regression(spark, data_size))
    all_results.append(run_als(spark, data_size))

    total_elapsed_s = time.time() - total_start

    benchmark_result = {
        "benchmark": "MLlib",
        "timestamp": datetime.now().isoformat(),
        "data_size_samples": data_size,
        "total_elapsed_s": round(total_elapsed_s, 2),
        "tests": all_results,
        "description": "ML algorithms: LogisticRegression, RandomForest, KMeans, LinearRegression, ALS",
        "reference": "HiBench ML benchmarks, Spark MLlib documentation"
    }

    result_file = os.path.join(result_dir, f"mllib_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(result_file, "w") as f:
        json.dump(benchmark_result, f, indent=2)
    print(f"[MLLIB] Results saved to {result_file}")

    spark.stop()


if __name__ == "__main__":
    main()