#!/usr/bin/env python3
import sys
import os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.environ.get(
    "RESULTS_DIR",
    os.path.join(os.path.dirname(SCRIPT_DIR), "results")
)

from pyspark.sql import SparkSession


def generate_tpcs_data(spark, scale_factor, output_dir):
    print(f"[TPCDS-DATAGEN] Generating TPC-DS data at SF={scale_factor}GB to {output_dir}")

    tables = [
        "store_sales", "store_returns", "web_sales", "web_returns",
        "catalog_sales", "catalog_returns", "inventory",
        "customer", "customer_address", "customer_demographics",
        "date_dim", "time_dim", "item", "promotion",
        "warehouse", "ship_mode", "income_band", "call_center",
        "web_page", "web_site", "store", "reason",
        "household_demographics", "catalog_page"
    ]

    rows_per_table = {
        "store_sales":      scale_factor * 4000000,
        "store_returns":    scale_factor * 400000,
        "web_sales":        scale_factor * 800000,
        "web_returns":      scale_factor * 80000,
        "catalog_sales":    scale_factor * 800000,
        "catalog_returns":  scale_factor * 80000,
        "inventory":        scale_factor * 200000,
        "customer":         scale_factor * 100000,
        "customer_address": scale_factor * 50000,
        "customer_demographics": 20000,
        "date_dim":         73049,
        "time_dim":         86400,
        "item":             scale_factor * 10000,
        "promotion":        1000,
        "warehouse":        20,
        "ship_mode":        35,
        "income_band":      20,
        "call_center":      42,
        "web_page":         2000,
        "web_site":         40,
        "store":            scale_factor * 12,
        "reason":           65,
        "household_demographics": 7200,
        "catalog_page":     10000,
    }

    start_time = time.time()
    total_rows = 0

    for table_name in tables:
        table_rows = rows_per_table.get(table_name, scale_factor * 1000)
        print(f"[TPCDS-DATAGEN] Generating table: {table_name} ({table_rows} rows)")

        if table_name == "store_sales":
            df = spark.range(table_rows).selectExpr(
                f"id as ss_sold_date_sk",
                f"cast(id % 73049 as int) as ss_sold_time_sk",
                f"cast(id % {int(scale_factor*100000)} as int) as ss_customer_sk",
                f"cast(id % {int(scale_factor*10000)} as int) as ss_item_sk",
                f"cast(id % 12 as int) as ss_store_sk",
                f"cast(id % 5 as int) as ss_promo_sk",
                f"cast(rand() * 1000 as double) as ss_quantity",
                f"cast(rand() * 100 as decimal(7,2)) as ss_sales_price",
                f"cast(rand() * 50 as decimal(7,2)) as ss_net_paid"
            )
        elif table_name == "customer":
            df = spark.range(table_rows).selectExpr(
                f"id as c_customer_sk",
                f"cast(id % 10000 as string) as c_customer_id",
                f"cast(id % {int(scale_factor*50000)} as int) as c_current_addr_sk",
                f"concat('customer_', id) as c_first_name",
                f"concat('last_', id % 100) as c_last_name"
            )
        elif table_name == "date_dim":
            df = spark.range(table_rows).selectExpr(
                f"id as d_date_sk",
                f"date_add('2000-01-01', cast(id as int)) as d_date",
                f"concat('date_', id) as d_date_id",
                f"cast(id % 7 as int) as d_day_of_week",
                f"cast(id % 12 as int) as d_month"
            )
        elif table_name == "item":
            df = spark.range(table_rows).selectExpr(
                f"id as i_item_sk",
                f"concat('item_', id) as i_item_id",
                f"cast(rand() * 100 as double) as i_current_price",
                f"concat('item_name_', id % 1000) as i_item_desc"
            )
        else:
            df = spark.range(table_rows).selectExpr(
                f"id as {table_name[0]}_sk",
                f"concat('{table_name}_', id) as {table_name[0]}_id"
            )

        df.write.mode("overwrite").parquet(os.path.join(output_dir, table_name))
        total_rows += table_rows
        print(f"[TPCDS-DATAGEN] Table {table_name} written ({table_rows} rows)")

    elapsed = time.time() - start_time
    print(f"[TPCDS-DATAGEN] Data generation completed: {total_rows} total rows in {elapsed:.2f}s")
    return total_rows


def main():
    if len(sys.argv) < 3:
        print("Usage: tpcds_datagen.py <scale_factor_gb> <output_dir>")
        sys.exit(1)

    scale_factor = int(sys.argv[1])
    output_dir = sys.argv[2]

    spark = SparkSession.builder \
        .appName(f"TPCDS-DataGen-SF{scale_factor}") \
        .master("local[*]") \
        .config("spark.sql.parquet.compression.codec", "snappy") \
        .getOrCreate()

    generate_tpcs_data(spark, scale_factor, output_dir)
    spark.stop()


if __name__ == "__main__":
    main()
