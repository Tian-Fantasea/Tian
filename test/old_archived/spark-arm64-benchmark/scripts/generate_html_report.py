#!/usr/bin/env python3
"""
Generate HTML report with embedded charts from aggregated benchmark results
Uses inline SVG/CSS for visualization (no external JS dependencies required)
"""

import sys
import json
import os


CSS_TEMPLATE = """
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 1200px; margin: 20px auto; background: #f5f5f5; }
    .header { background: #333; color: #fff; padding: 20px; border-radius: 8px; text-align: center; }
    .header h1 { margin: 0; font-size: 24px; }
    .header h2 { margin: 5px 0 0; font-size: 16px; color: #aaa; }
    .section { background: #fff; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .section h2 { color: #333; border-bottom: 2px solid #e74c3c; padding-bottom: 10px; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
    .metric-box { background: #ecf0f1; padding: 12px; border-radius: 6px; text-align: center; }
    .metric-box .label { font-size: 12px; color: #7f8c8d; }
    .metric-box .value { font-size: 20px; font-weight: bold; color: #2c3e50; }
    .metric-box .unit { font-size: 12px; color: #7f8c8d; }
    .chart-container { margin: 20px 0; }
    .chart-title { font-size: 14px; color: #555; margin-bottom: 5px; }
    table { width: 100%; border-collapse: collapse; margin: 10px 0; }
    th { background: #34495e; color: white; padding: 8px 12px; text-align: left; font-size: 13px; }
    td { padding: 6px 12px; border-bottom: 1px solid #ddd; font-size: 13px; }
    tr:hover td { background: #f0f0f0; }
    .success { color: #27ae60; }
    .failed { color: #e74c3c; }
    .bar-chart { display: flex; align-items: flex-end; height: 300px; gap: 8px; padding: 10px; background: #fafafa; border: 1px solid #ddd; border-radius: 4px; }
    .bar { display: flex; flex-direction: column; align-items: center; flex: 1; max-width: 60px; }
    .bar-fill { background: #3498db; border-radius: 3px 3px 0 0; min-height: 2px; transition: height 0.3s; }
    .bar-label { font-size: 11px; color: #555; margin-top: 4px; }
    .bar-value { font-size: 10px; color: #333; margin-bottom: 2px; }
    .env-table td:nth-child(1) { font-weight: bold; color: #2c3e50; width: 40%; }
</style>
"""


def make_bar_chart(title, data_items, max_val=None):
    """Generate a simple bar chart as HTML"""
    if not data_items:
        return ""

    if max_val is None:
        max_val = max(v for _, v in data_items) if data_items else 1
    if max_val == 0:
        max_val = 1

    bars = []
    for label, value in data_items:
        height_pct = (value / max_val) * 100
        bars.append(f"""
            <div class="bar">
                <div class="bar-value">{value:.1f}</div>
                <div class="bar-fill" style="height: {height_pct}%;"></div>
                <div class="bar-label">{label}</div>
            </div>
        """)

    return f"""
    <div class="chart-container">
        <div class="chart-title">{title}</div>
        <div class="bar-chart">
            {"".join(bars)}
        </div>
    </div>
    """


def generate_html_report(input_json, output_file):
    """Generate complete HTML report"""
    with open(input_json) as f:
        data = json.load(f)

    sections = []

    # Header
    sections.append(f"""
    <div class="header">
        <h1>Apache Spark ARM64 Performance Benchmark Report</h1>
        <h2>Generated: {data.get('timestamp', 'N/A')}</h2>
    </div>
    """)

    # Environment
    env = data.get("benchmarks", {}).get("environment", {})
    if env:
        rows = []
        for key, label in [("architecture", "Architecture"), ("cpu_model", "CPU Model"),
                           ("cpu_cores", "CPU Cores"), ("memory_mb", "Memory (MB)"),
                           ("spark_version", "Spark Version"), ("java_version", "Java Version"),
                           ("python_version", "Python Version"), ("os", "Operating System"),
                           ("kernel", "Kernel"), ("spark_cores_config", "Configured Cores"),
                           ("spark_memory_config", "Configured Memory")]:
            rows.append(f"<tr><td>{label}</td><td>{env.get(key, 'N/A')}</td></tr>")
        sections.append(f"""
        <div class="section"><h2>Environment Information</h2>
        <table class="env-table">{"".join(rows)}</table></div>
        """)

    # TPC-DS
    tpcds = data.get("benchmarks", {}).get("TPC-DS", {})
    if tpcds:
        sections.append(f"""
        <div class="section"><h2>TPC-DS Benchmark (SF={tpcds.get('scale_factor_gb', 'N/A')}GB)</h2>
        <p>{tpcds.get('description', '')}</p>
        <div class="metric-grid">
            <div class="metric-box"><div class="label">Successful Queries</div><div class="value">{tpcds.get('successful_queries', 'N/A')}</div><div class="unit">/ {tpcds.get('total_queries', 'N/A')}</div></div>
            <div class="metric-box"><div class="label">Total Time</div><div class="value">{tpcds.get('total_elapsed_s', 'N/A')}</div><div class="unit">seconds</div></div>
            <div class="metric-box"><div class="label">Throughput</div><div class="value">{tpcds.get('throughput_qph', 'N/A')}</div><div class="unit">queries/hour</div></div>
            <div class="metric-box"><div class="label">Avg Query Time</div><div class="value">{tpcds.get('avg_query_time_ms', 'N/A')}</div><div class="unit">ms</div></div>
        </div>
        {make_bar_chart("TPC-DS Query Execution Time (ms)", [(q['query'], q.get('elapsed_ms', 0)) for q in tpcds.get('queries', [])])}
        <table><tr><th>Query</th><th>Time (ms)</th><th>Rows</th><th>Status</th></tr>
        {"".join(f"<tr><td>{q['query']}</td><td>{q.get('elapsed_ms', 'N/A')}</td><td>{q.get('row_count', 'N/A')}</td><td class='{q.get('status', '').startswith('SUCCESS') and 'success' or 'failed'}'>{q.get('status', 'N/A')}</td></tr>" for q in tpcds.get('queries', []))}
        </table></div>
        """)

    # Micro-Benchmarks
    micro = data.get("benchmarks", {}).get("Micro-Benchmarks", {})
    if micro:
        test_boxes = []
        for test in micro.get("tests", []):
            test_boxes.append(f"""
            <div class="metric-box"><div class="label">{test['test']}</div>
            <div class="value">{test.get('avg_elapsed_ms', 'N/A')}</div><div class="unit">ms avg</div></div>
            <div class="metric-box"><div class="label">{test['test']}</div>
            <div class="value">{test.get('avg_throughput_records_per_s', 'N/A')}</div><div class="unit">rec/s avg</div></div>
            """)
        sections.append(f"""
        <div class="section"><h2>Micro-Benchmarks</h2>
        <p>{micro.get('description', '')}</p>
        <div class="metric-grid">
            <div class="metric-box"><div class="label">Data Size</div><div class="value">{micro.get('data_size_rows', 'N/A')}</div><div class="unit">rows</div></div>
            <div class="metric-box"><div class="label">Total Time</div><div class="value">{micro.get('total_elapsed_s', 'N/A')}</div><div class="unit">seconds</div></div>
            {"".join(test_boxes)}
        </div>
        {make_bar_chart("Micro-Benchmark Average Time (ms)", [(t['test'], t.get('avg_elapsed_ms', 0)) for t in micro.get('tests', [])])}
        {make_bar_chart("Micro-Benchmark Throughput (records/s)", [(t['test'], t.get('avg_throughput_records_per_s', 0)) for t in micro.get('tests', [])])}
        </div>
        """)

    # MLlib
    mllib = data.get("benchmarks", {}).get("MLlib", {})
    if mllib:
        sections.append(f"""
        <div class="section"><h2>MLlib Benchmarks</h2>
        <p>{mllib.get('description', '')}</p>
        <div class="metric-grid">
            <div class="metric-box"><div class="label">Data Size</div><div class="value">{mllib.get('data_size_samples', 'N/A')}</div><div class="unit">samples</div></div>
            <div class="metric-box"><div class="label">Total Time</div><div class="value">{mllib.get('total_elapsed_s', 'N/A')}</div><div class="unit">seconds</div></div>
        </div>
        {make_bar_chart("MLlib Training Time (ms)", [(t['test'], t.get('avg_train_time_ms', 0)) for t in mllib.get('tests', [])])}
        {make_bar_chart("MLlib Prediction Time (ms)", [(t['test'], t.get('avg_predict_time_ms', 0)) for t in mllib.get('tests', [])])}
        <table><tr><th>Algorithm</th><th>Train (ms)</th><th>Predict (ms)</th><th>Description</th></tr>
        {"".join(f"<tr><td>{t['test']}</td><td>{t.get('avg_train_time_ms', 'N/A')}</td><td>{t.get('avg_predict_time_ms', 'N/A')}</td><td>{t.get('description', 'N/A')}</td></tr>" for t in mllib.get('tests', []))}
        </table></div>
        """)

    # Streaming
    streaming = data.get("benchmarks", {}).get("Structured Streaming", {})
    if streaming:
        sections.append(f"""
        <div class="section"><h2>Structured Streaming Benchmark</h2>
        <p>{streaming.get('description', '')}</p>
        <div class="metric-grid">
            <div class="metric-box"><div class="label">Input Rate</div><div class="value">{streaming.get('rows_per_second', 'N/A')}</div><div class="unit">rows/s</div></div>
            <div class="metric-box"><div class="label">Avg Throughput</div><div class="value">{streaming.get('avg_throughput_records_per_s', 'N/A')}</div><div class="unit">rec/s</div></div>
            <div class="metric-box"><div class="label">Avg Batch Duration</div><div class="value">{streaming.get('avg_batch_duration_ms', 'N/A')}</div><div class="unit">ms</div></div>
            <div class="metric-box"><div class="label">Total Rows</div><div class="value">{streaming.get('total_rows_processed', 'N/A')}</div><div class="unit">rows</div></div>
        </div>
        </div>
        """)

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spark ARM64 Benchmark Report</title>
    {CSS_TEMPLATE}
</head>
<body>
    {"".join(sections)}
    <div class="section">
        <p style="text-align: center; color: #888; font-size: 12px;">
            Generated by Spark ARM64 Performance Benchmark Workflow &mdash; Apache Spark
        </p>
    </div>
</body>
</html>
    """

    with open(output_file, "w") as f:
        f.write(html)
    print(f"[REPORT] HTML report generated: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_html_report.py <input_json> <output_file>")
        sys.exit(1)

    input_json = sys.argv[1]
    output_file = sys.argv[2]
    generate_html_report(input_json, output_file)