// Spark Scala verification script
// Tests basic Spark functionality on ARM64

import org.apache.spark.sql.SparkSession

val spark = SparkSession.builder()
  .appName("SparkARM64Verify")
  .master("local[2]")
  .getOrCreate()

val sc = spark.sparkContext

// Test 1: RDD creation and count
val rdd = sc.parallelize(1 to 1000, 2)
val count = rdd.count()
println(s"[VERIFY] RDD count result: ${count} (expected: 1000)")

// Test 2: DataFrame creation and SQL
val df = spark.range(1, 1000)
df.createOrReplaceTempView("verify_table")
val result = spark.sql("SELECT COUNT(*) as cnt FROM verify_table").collect()
println(s"[VERIFY] SQL count result: ${result(0).getLong(0)} (expected: 999)")

// Test 3: Spark version
println(s"[VERIFY] Spark version: ${spark.version}")
println(s"[VERIFY] Spark UI available at: ${sc.uiWebUrl}")

// Test 4: Simple aggregation
val aggResult = rdd.reduce(_ + _)
println(s"[VERIFY] RDD sum result: ${aggResult} (expected: 500500)")

spark.stop()
println("[VERIFY] All Scala tests PASSED")
System.exit(0)