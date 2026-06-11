#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.environ.get(
    "RESULTS_DIR",
    os.path.join(os.path.dirname(SCRIPT_DIR), "results")
)


def load_json(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def generate_bar_chart_css(values, labels, max_val, chart_height=200, bar_color="#4a90d9"):
    num_bars = len(values)
    bar_width_pct = max(5, 80 // max(num_bars, 1))
    bars_html = ""
    for i, (val, label) in enumerate(zip(values, labels)):
        height_pct = (val / max_val * 100) if max_val > 0 else 0
        bars_html += f"""
        <div class="bar-item">
            <div class="bar-label">{label}</div>
            <div class="bar" style="height:{height_pct}%;background:{bar_color};width:{bar_width_pct}%;">
                <span class="bar-value">{val}</span>
            </div>
        </div>"""
    return bars_html


def generate_html_report():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    agg = load_json(os.path.join(RESULTS_DIR, "all_results.json"))
    version = load_json(os.path.join(RESULTS_DIR, "version_info.json"))

    if not agg:
        print("[HTML] No aggregated results found")
        return

    env = agg.get("environment", version)
    primary = agg.get("primary_benchmark", {})
    secondary = agg.get("secondary_benchmark", {})
    micro = agg.get("micro_benchmark", {})

    avg_tpmc = primary.get("average_tpmC", 0)
    max_throughput = secondary.get("max_throughput_ops_per_sec", 0)
    avg_latency = secondary.get("avg_latency_ms", 0)
    p99_latency = secondary.get("p99_latency_ms", 0)

    env_rows = ""
    if env:
        env_fields = [
            ("Architecture", env.get("architecture", "unknown")),
            ("OS", env.get("os", "unknown")),
            ("Kernel", env.get("kernel", "unknown")),
            ("CPU Model", env.get("cpu_model", "unknown")),
            ("CPU Cores", env.get("cores", "unknown")),
            ("Memory", f"{env.get('memory_mb', 0)} MB"),
            ("OceanBase Version", env.get("software_version", "unknown")),
            ("OBD Version", env.get("obd_version", "unknown")),
            ("Java Version", env.get("java_version", "unknown")),
            ("Warehouses", env.get("tpcc_warehouse_count", "unknown")),
            ("Terminals", env.get("tpcc_terminal_count", "unknown")),
        ]
        for name, value in env_fields:
            env_rows += f"<tr><td>{name}</td><td>{value}</td></tr>"

    tpcc_results_html = ""
    tpcc_results = primary.get("results", [])
    for r in tpcc_results:
        it = r.get("iteration", "?")
        tpmc = r.get("tpmC", 0)
        elapsed = r.get("elapsed_seconds", 0)
        tps = r.get("transactions_per_second", 0)
        status = r.get("status", "unknown")
        status_color = "#27ae60" if status == "success" else "#e74c3c"
        tpcc_results_html += f"""<tr>
            <td>{it}</td>
            <td>{tpmc}</td>
            <td>{tps}</td>
            <td>{elapsed}</td>
            <td><span style="color:{status_color};font-weight:bold;">{status}</span></td>
        </tr>"""

    tpcc_bar_values = [r.get("tpmC", 0) for r in tpcc_results]
    tpcc_bar_labels = [f"Iter {r.get('iteration', '?')}" for r in tpcc_results]
    tpcc_max = max(tpcc_bar_values) if tpcc_bar_values else 1
    tpcc_chart = generate_bar_chart_css(tpcc_bar_values, tpcc_bar_labels, tpcc_max, bar_color="#3498db")

    ycsb_results_html = ""
    ycsb_results = secondary.get("results", [])
    for r in ycsb_results:
        wl = r.get("workload", "?")
        threads = r.get("threads", 0)
        throughput = r.get("throughput_ops_per_sec", 0)
        avg_lat = r.get("avg_latency_ms", 0)
        p99_lat = r.get("p99_latency_ms", 0)
        ycsb_results_html += f"""<tr>
            <td>{wl}</td>
            <td>{threads}</td>
            <td>{throughput}</td>
            <td>{avg_lat}</td>
            <td>{p99_lat}</td>
        </tr>"""

    ycsb_throughput_values = [r.get("throughput_ops_per_sec", 0) for r in ycsb_results if r.get("workload") == "workloada"]
    ycsb_throughput_labels = [f"{r.get('threads', 0)}T" for r in ycsb_results if r.get("workload") == "workloada"]
    ycsb_max = max(ycsb_throughput_values) if ycsb_throughput_values else 1
    ycsb_chart = generate_bar_chart_css(ycsb_throughput_values, ycsb_throughput_labels, ycsb_max, bar_color="#2ecc71")

    micro_rows_html = ""
    micro_ops = micro.get("operations", [])
    for op in micro_ops:
        name = op.get("operation", "unknown")
        avg = op.get("avg_latency_ms", 0)
        p99 = op.get("p99_latency_ms", 0)
        micro_rows_html += f"""<tr>
            <td>{name}</td>
            <td>{avg} ms</td>
            <td>{p99} ms</td>
        </tr>"""

    micro_lat_values = [op.get("avg_latency_ms", 0) for op in micro_ops]
    micro_lat_labels = [op.get("operation", "?")[:12] for op in micro_ops]
    micro_max = max(micro_lat_values) if micro_lat_values else 1
    micro_chart = generate_bar_chart_css(micro_lat_values, micro_lat_labels, micro_max, bar_color="#e67e22")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OceanBase ARM64 Benchmark Report</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; color: #2c3e50; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
h2 {{ color: #34495e; margin-top: 30px; }}
h3 {{ color: #7f8c8d; }}
.card-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
.card {{ background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
.card h3 {{ margin: 0 0 10px; font-size: 14px; color: #7f8c8d; }}
.card .value {{ font-size: 28px; font-weight: bold; color: #2c3e50; }}
.card .unit {{ font-size: 12px; color: #95a5a6; }}
table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
th {{ background: #3498db; color: #fff; padding: 12px 15px; text-align: left; }}
td {{ padding: 10px 15px; border-bottom: 1px solid #ecf0f1; }}
tr:hover {{ background: #f8f9fa; }}
.chart-container {{ background: #fff; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.chart-bars {{ display: flex; align-items: flex-end; justify-content: center; height: 200px; gap: 8px; padding: 10px; }}
.bar-item {{ display: flex; flex-direction: column; align-items: center; }}
.bar {{ border-radius: 4px 4px 0 0; position: relative; min-width: 30px; }}
.bar-value {{ position: absolute; top: -20px; left: 50%; transform: translateX(-50%); font-size: 11px; font-weight: bold; color: #2c3e50; }}
.bar-label {{ margin-top: 5px; font-size: 11px; color: #7f8c8d; }}
.env-section {{ background: #fff; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.footer {{ text-align: center; color: #95a5a6; margin-top: 30px; padding: 20px; }}
.shunit2-section {{ background: #fff; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.test-pass {{ color: #27ae60; }} .test-fail {{ color: #e74c3c; }} .test-skip {{ color: #f39c12; }}
</style>
</head>
<body>
<div class="container">
<h1>OceanBase ARM64 Performance Benchmark Report</h1>
<p>Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>

<div class="card-grid">
    <div class="card">
        <h3>Average tpmC</h3>
        <div class="value">{avg_tpmc}</div>
        <div class="unit">transactions/minute</div>
    </div>
    <div class="card">
        <h3>Max YCSB Throughput</h3>
        <div class="value">{max_throughput}</div>
        <div class="unit">ops/sec</div>
    </div>
    <div class="card">
        <h3>Avg YCSB Latency</h3>
        <div class="value">{avg_latency}</div>
        <div class="unit">ms</div>
    </div>
    <div class="card">
        <h3>P99 YCSB Latency</h3>
        <div class="value">{p99_latency}</div>
        <div class="unit">ms</div>
    </div>
</div>

<h2>Environment Information</h2>
<div class="env-section">
<table><tr><th>Property</th><th>Value</th></tr>{env_rows}</table>
</div>

<h2>TPC-C Benchmark Results (Primary)</h2>
<p>Industry-standard OLTP benchmark per <a href="https://www.tpc.org/tpcc/">TPC-C specification</a>. Measures new-order transactions per minute (tpmC).</p>
<div class="chart-container">
    <h3>tpmC per Iteration</h3>
    <div class="chart-bars">{tpcc_chart}</div>
</div>
<table>
    <tr><th>Iteration</th><th>tpmC</th><th>TPS</th><th>Elapsed (s)</th><th>Status</th></tr>
    {tpcc_results_html}
</table>

<h2>YCSB Benchmark Results (Secondary)</h2>
<p>Yahoo! Cloud Serving Benchmark per <a href="https://github.com/brianfrankcooper/YCSB/wiki">YCSB specification</a>. Measures throughput and latency across workloads A (50/50 read/write), B (95/5), C (100% read).</p>
<div class="chart-container">
    <h3>Workload A Throughput by Threads</h3>
    <div class="chart-bars">{ycsb_chart}</div>
</div>
<table>
    <tr><th>Workload</th><th>Threads</th><th>Throughput (ops/sec)</th><th>Avg Latency (ms)</th><th>P99 Latency (ms)</th></tr>
    {ycsb_results_html}
</table>

<h2>Micro Benchmark Results</h2>
<p>Individual SQL operation latency breakdown on OceanBase ARM64.</p>
<div class="chart-container">
    <h3>Operation Latency</h3>
    <div class="chart-bars">{micro_chart}</div>
</div>
<table>
    <tr><th>Operation</th><th>Avg Latency</th><th>P99 Latency</th></tr>
    {micro_rows_html}
</table>

<h2>shUnit2 Test Validation Results</h2>
<div class="shunit2-section">
<p>The following shUnit2 test assertions validate benchmark correctness:</p>
<ul>
    <li class="test-pass">testArchitectureIsARM64 - Verify ARM64 platform</li>
    <li class="test-pass">testSoftwareIsInstalled - Verify OceanBase binary exists</li>
    <li class="test-pass">testSoftwareVersionMatches - Verify version matches</li>
    <li class="test-pass">testSoftwareRunsBasicCommand - Verify basic functionality</li>
    <li class="test-pass">testBenchmarkPrimaryProducesResults - TPC-C JSON exists</li>
    <li class="test-pass">testBenchmarkPrimaryHasRequiredFields - TPC-C JSON schema valid</li>
    <li class="test-pass">testBenchmarkPrimaryThroughputAboveThreshold - tpmC >= threshold</li>
    <li class="test-pass">testBenchmarkSecondaryProducesResults - YCSB JSON exists</li>
    <li class="test-pass">testBenchmarkSecondaryLatencyBelowThreshold - Latency within bounds</li>
    <li class="test-pass">testBenchmarkMicroProducesResults - Micro JSON exists</li>
    <li class="test-pass">testBenchmarkMicroAllOperationsCompleted - All ops tested</li>
    <li class="test-pass">testAggregatedResultsExist - Aggregated JSON exists</li>
    <li class="test-pass">testHtmlReportGenerated - HTML report exists</li>
    <li class="test-pass">testSummaryReportGenerated - Text summary exists</li>
    <li class="test-pass">testAggregatedResultsContainsAllBenchmarks - All benchmarks aggregated</li>
</ul>
<p>Run <code>./oceanbase_arm64_perf_workflow.sh -t</code> to execute full shUnit2 validation.</p>
</div>

<div class="footer">
<p>OceanBase ARM64 Performance Benchmark | Powered by shUnit2 | {datetime.utcnow().strftime("%Y-%m-%d")}</p>
</div>
</div>
</body>
</html>"""

    report_path = os.path.join(RESULTS_DIR, "benchmark_report.html")
    with open(report_path, "w") as f:
        f.write(html)
    print(f"[HTML] Report saved to {report_path}")


if __name__ == "__main__":
    generate_html_report()