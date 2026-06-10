#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime


def run_flink_sql(flink_home, sql, job_name):
    sql_client = os.path.join(flink_home, "bin", "sql-client.sh")
    cmd = [sql_client, "embedded"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "FLINK_HOME": flink_home},
        )
        full_sql = f"SET 'table.exec.state.ttl' = '3600000';\n{sql}\nQUIT;\n"
        stdout, stderr = proc.communicate(input=full_sql.encode(), timeout=600)
        return proc.returncode, stdout.decode(), stderr.decode()
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1, "", "Timeout"


def generate_tpcds_queries(scale):
    queries = [
        ("q1", "SELECT l_returnflag, l_linestatus, SUM(l_quantity) AS sum_qty, SUM(l_extendedprice) AS sum_base_price, SUM(l_extendedprice * (1 - l_discount)) AS sum_disc_price, SUM(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge, AVG(l_quantity) AS avg_qty, AVG(l_extendedprice) AS avg_price, AVG(l_discount) AS avg_disc, COUNT(*) AS count_order FROM lineitem WHERE l_shipdate <= DATE '1998-12-01' - INTERVAL '90' DAY GROUP BY l_returnflag, l_linestatus ORDER BY l_returnflag, l_linestatus"),
        ("q3", "SELECT l_orderkey, SUM(l_extendedprice * (1 - l_discount)) AS revenue, o_orderdate, o_shippriority FROM customer, orders, lineitem WHERE c_mktsegment = 'BUILDING' AND c_custkey = o_custkey AND l_orderkey = o_orderkey AND o_orderdate < DATE '1995-03-15' AND l_shipdate > DATE '1995-03-15' GROUP BY l_orderkey, o_orderdate, o_shippriority ORDER BY revenue DESC, o_orderdate LIMIT 10"),
        ("q5", "SELECT n_name, SUM(l_extendedprice * (1 - l_discount)) AS revenue FROM customer, orders, lineitem, supplier, nation, region WHERE c_custkey = o_custkey AND l_orderkey = o_orderkey AND l_suppkey = s_suppkey AND c_nationkey = s_nationkey AND s_nationkey = n_nationkey AND n_regionkey = r_regionkey AND r_name = 'ASIA' AND o_orderdate >= DATE '1994-01-01' AND o_orderdate < DATE '1994-01-01' + INTERVAL '1' YEAR GROUP BY n_name ORDER BY revenue DESC"),
        ("q6", "SELECT SUM(l_extendedprice * l_discount) AS revenue FROM lineitem WHERE l_shipdate >= DATE '1994-01-01' AND l_shipdate < DATE '1994-01-01' + INTERVAL '1' YEAR AND l_discount BETWEEN 0.06 - 0.01 AND 0.06 + 0.01 AND l_quantity < 24"),
        ("q7", "SELECT supp_nation, cust_nation, l_year, SUM(l_extendedprice * (1 - l_discount)) AS revenue FROM supplier, lineitem, orders, customer, nation n1, nation n2 WHERE s_suppkey = l_suppkey AND o_orderkey = l_orderkey AND c_custkey = o_custkey AND s_nationkey = n1.n_nationkey AND c_nationkey = n2.n_nationkey AND (n1.n_name = 'FRANCE' AND n2.n_name = 'GERMANY' OR n1.n_name = 'GERMANY' AND n2.n_name = 'FRANCE') AND l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31' GROUP BY supp_nation, cust_nation, l_year ORDER BY supp_nation, cust_nation, l_year"),
        ("q10", "SELECT c_custkey, c_name, SUM(l_extendedprice * (1 - l_discount)) AS revenue, c_acctbal, n_name, c_address, c_phone, c_comment FROM customer, orders, lineitem, nation WHERE c_custkey = o_custkey AND l_orderkey = o_orderkey AND o_orderdate >= DATE '1993-10-01' AND o_orderdate < DATE '1993-10-01' + INTERVAL '3' MONTH AND l_returnflag = 'R' AND c_nationkey = n_nationkey GROUP BY c_custkey, c_name, c_acctbal, c_phone, n_name, c_address, c_comment ORDER BY revenue DESC LIMIT 20"),
    ]
    return queries


def create_datagen_tables(flink_home, scale):
    base_rows = scale * 100000
    create_sqls = [
        f"CREATE TABLE lineitem ( l_orderkey INT, l_partkey INT, l_suppkey INT, l_linenumber INT, l_quantity DOUBLE, l_extendedprice DOUBLE, l_discount DOUBLE, l_tax DOUBLE, l_returnflag STRING, l_linestatus STRING, l_shipdate DATE, l_commitdate DATE, l_receiptdate DATE, l_shipinstruct STRING, l_shipmode STRING, l_comment STRING ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '{base_rows}', 'number-of-rows' = '{base_rows * 6}' );",
        f"CREATE TABLE orders ( o_orderkey INT, o_custkey INT, o_orderstatus STRING, o_totalprice DOUBLE, o_orderdate DATE, o_orderpriority STRING, o_clerk STRING, o_shippriority INT, o_comment STRING ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '{base_rows // 6}', 'number-of-rows' = '{base_rows}' );",
        f"CREATE TABLE customer ( c_custkey INT, c_name STRING, c_address STRING, c_nationkey INT, c_phone STRING, c_acctbal DOUBLE, c_mktsegment STRING, c_comment STRING ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '{base_rows // 60}', 'number-of-rows' = '{base_rows // 6}' );",
        f"CREATE TABLE supplier ( s_suppkey INT, s_name STRING, s_address STRING, s_nationkey INT, s_phone STRING, s_acctbal DOUBLE, s_comment STRING ) WITH ( 'connector' = 'datagen', 'rows-per-second' = '{base_rows // 600}', 'number-of-rows' = '{base_rows // 60}' );",
        f"CREATE TABLE nation ( n_nationkey INT, n_name STRING, n_regionkey INT, n_comment STRING ) WITH ( 'connector' = 'datagen', 'number-of-rows' = '25' );",
        f"CREATE TABLE region ( r_regionkey INT, r_name STRING, r_comment STRING ) WITH ( 'connector' = 'datagen', 'number-of-rows' = '5' );",
    ]
    return create_sqls


def benchmark_tpcds(flink_home, scale, iterations, results_dir):
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    queries = generate_tpcds_queries(scale)
    create_sqls = create_datagen_tables(flink_home, scale)

    results = []
    start_cluster = os.path.join(flink_home, "bin", "start-cluster.sh")
    stop_cluster = os.path.join(flink_home, "bin", "stop-cluster.sh")

    for i in range(iterations):
        print(f"[TPCDS] Iteration {i + 1}/{iterations}")
        subprocess.run([start_cluster], env={**os.environ, "FLINK_HOME": flink_home}, capture_output=True)
        time.sleep(15)

        all_sql = ";\n".join(create_sqls) + ";\n"
        for q_name, q_sql in queries:
            q_start = time.time()
            full_sql = all_sql + q_sql + ";"
            rc, stdout, stderr = run_flink_sql(flink_home, full_sql, f"tpcds_{q_name}")
            q_elapsed = time.time() - q_start
            records = 0
            try:
                lines = stdout.strip().split("\n")
                border_count = 0
                past_header = False
                for l in lines:
                    l_stripped = l.strip()
                    if l_stripped.startswith("+") and "-" in l_stripped:
                        border_count += 1
                        if border_count == 2:
                            past_header = True
                        if border_count >= 3:
                            past_header = False
                    elif l_stripped.startswith("|") and past_header:
                        records += 1
                if records == 0:
                    import re
                    m = re.search(r"(\d+)\s+rows?\s+returned", stdout)
                    if m:
                        records = int(m.group(1))
            except Exception:
                pass
            results.append({
                "iteration": i + 1,
                "query": q_name,
                "elapsed_sec": round(q_elapsed, 3),
                "records_output": records,
                "records_per_sec": round(records / q_elapsed, 1) if q_elapsed > 0 and records > 0 else 0,
                "success": rc == 0,
            })
            print(f"[TPCDS] {q_name}: {q_elapsed:.3f}s, {records} records")

        subprocess.run([stop_cluster], env={**os.environ, "FLINK_HOME": flink_home}, capture_output=True)
        time.sleep(5)

    avg_results = []
    for q_name, _ in queries:
        q_results = [r for r in results if r["query"] == q_name and r["success"]]
        if q_results:
            avg_elapsed = sum(r["elapsed_sec"] for r in q_results) / len(q_results)
            avg_rps = sum(r["records_per_sec"] for r in q_results) / len(q_results)
            avg_results.append({
                "query": q_name,
                "avg_elapsed_sec": round(avg_elapsed, 3),
                "avg_records_per_sec": round(avg_rps, 1),
                "iterations": len(q_results),
            })

    output = {
        "benchmark": "tpcds",
        "description": "TPC-DS SQL queries on Flink Table API/SQL with DataGen source",
        "reference": "https://www.tpc.org/tpcds/default5.asp",
        "timestamp": timestamp,
        "performance_metrics": {
            "elapsed_sec": {"unit": "s", "description": "Query execution time"},
            "records_per_sec": {"unit": "records/s", "description": "Output throughput"},
        },
        "dataset_info": {
            "name": "TPC-DS DataGen",
            "size": f"scale={scale}",
            "source": "Flink DataGen connector (in-memory)",
        },
        "results": avg_results,
        "raw_results": results,
    }

    out_file = os.path.join(results_dir, "benchmark_tpcds.json")
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[TPCDS] Results saved to {out_file}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Flink TPC-DS benchmark")
    parser.add_argument("--flink-home", required=True)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    benchmark_tpcds(args.flink_home, args.scale, args.iterations, args.results_dir)


if __name__ == "__main__":
    main()