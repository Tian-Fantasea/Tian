#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime

CSS_STYLE = """
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }
.container { max-width: 960px; margin: 0 auto; padding: 20px; }
.header { background: linear-gradient(135deg, #1a5276, #2e86c1); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { font-size: 28px; margin-bottom: 8px; }
.header .meta { font-size: 14px; opacity: 0.9; }
.env-table { width: 100%; border-collapse: collapse; margin: 20px 0; }
.env-table th, .env-table td { padding: 10px 15px; border: 1px solid #ddd; text-align: left; }
.env-table th { background: #2e86c1; color: white; }
.env-table tr:nth-child(even) { background: #f9f9f9; }
.metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
.metric-card { background: white; border-radius: 8px; padding: 20px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.metric-card .value { font-size: 24px; font-weight: bold; color: #2e86c1; }
.metric-card .label { font-size: 12px; color: #666; margin-top: 5px; }
.metric-card.pass { border-left: 4px solid #27ae60; }
.metric-card.fail { border-left: 4px solid #e74c3c; }
.section { background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #1a5276; margin-bottom: 15px; }
.results-table { width: 100%; border-collapse: collapse; }
.results-table th, .results-table td { padding: 8px 12px; border: 1px solid #ddd; text-align: left; }
.results-table th { background: #1a5276; color: white; }
.status-pass { color: #27ae60; font-weight: bold; }
.status-fail { color: #e74c3c; font-weight: bold; }
.bar-chart { margin: 20px 0; }
.bar-row { display: flex; align-items: center; margin: 5px 0; }
.bar-label { width: 120px; font-size: 12px; text-align: right; padding-right: 10px; }
.bar-track { flex: 1; height: 24px; background: #eee; border-radius: 4px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; font-size: 11px; color: white; font-weight: bold; }
.bar-fill.pass { background: linear-gradient(90deg, #27ae60, #2ecc71); }
.bar-fill.fail { background: linear-gradient(90deg, #e74c3c, #c0392b); }
.bar-fill.neutral { background: linear-gradient(90deg, #2e86c1, #3498db); }
.footer { text-align: center; padding: 20px; color: #666; font-size: 12px; }
</style>
"""

def make_bar_chart(items, max_val, unit=""):
    rows = []
    for item in items:
        label = item["label"]
        value = item["value"]
        threshold = item.get("threshold", 0)
        pct = min(100, int(value / max(max_val, 1) * 100))
        passed = item.get("pass", value >= threshold)
        cls = "pass" if passed else "fail"
        rows.append('<div class="bar-row"><div class="bar-label">{}</div><div class="bar-track"><div class="bar-fill {}" style="width:{}%">{}</div></div></div>'.format(
            label, cls, pct, "{} {}".format(value, unit)
        ))
    return '<div class="bar-chart">{}</div>'.format("\n".join(rows))

def generate_html(data):
    env = data.get("environment", {})
    summary = data.get("summary", {})
    thresholds = data.get("thresholds", {})
    primary = data.get("primary_benchmark", {})
    secondary = data.get("secondary_benchmark", {})
    micro = data.get("micro_benchmark", {})

    tpcds_t = summary.get("tpcds_avg_throughput_ops_per_sec", 0)
    stream_t = summary.get("streaming_avg_throughput_events_per_sec", 0)
    stream_l = summary.get("streaming_avg_latency_ms", 0)
    overall_pass = summary.get("overall_pass", False)

    overall_status = "PASS" if overall_pass else "FAIL"
    overall_color = "#27ae60" if overall_pass else "#e74c3c"

    env_rows = ""
    env_fields = [
        ("OS", env.get("os", "unknown")),
        ("Kernel", env.get("kernel", "unknown")),
        ("Architecture", env.get("architecture", "arm64")),
        ("CPU", env.get("cpu_model", "unknown")),
        ("Cores", env.get("cores", "unknown")),
        ("Memory", "{} MB".format(env.get("memory_mb", "unknown"))),
        ("Java", env.get("java_version", "unknown")),
        ("Flink Version", data.get("version", "unknown")),
    ]
    for label, value in env_fields:
        env_rows += "<tr><td>{}</td><td>{}</td></tr>".format(label, value)

    metric_cards = ""
    cards = [
        ("TPC-DS Throughput", "{} ops/sec".format(tpcds_t), summary.get("tpcds_pass", False)),
        ("Streaming Throughput", "{} events/sec".format(stream_t), summary.get("streaming_pass", False)),
        ("Streaming Latency", "{} ms".format(stream_l), stream_l <= thresholds.get("streaming_max_latency_ms", 500)),
    ]
    for label, value, passed in cards:
        cls = "pass" if passed else "fail"
        metric_cards += '<div class="metric-card {}"><div class="value">{}</div><div class="label">{}</div></div>'.format(cls, value, label)

    primary_results_rows = ""
    if primary.get("results"):
        for r in primary.get("results", []):
            avg_t = r.get("average_throughput_ops_per_sec", 0)
            avg_e = r.get("average_elapsed_ms", 0)
            primary_results_rows += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                r.get("query_id", ""), r.get("description", ""), avg_t, avg_e
            )

    secondary_results_rows = ""
    if secondary.get("results"):
        for r in secondary.get("results", []):
            avg_t = r.get("average_throughput_events_per_sec", 0)
            avg_l = r.get("average_latency_ms", 0)
            secondary_results_rows += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                r.get("job_id", ""), r.get("description", ""), avg_t, avg_l
            )

    micro_results_rows = ""
    if micro.get("results"):
        for r in micro.get("results", []):
            avg_t = r.get("average_throughput_ops_per_sec", 0)
            avg_l = r.get("average_latency_ms", 0)
            micro_results_rows += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                r.get("name", ""), r.get("category", ""), avg_t, avg_l, r.get("data_size_mb", 0)
            )

    throughput_chart_items = [
        {"label": "TPC-DS", "value": tpcds_t, "threshold": thresholds.get("tpcds_min_throughput_ops_per_sec", 500), "pass": summary.get("tpcds_pass", False)},
        {"label": "Streaming", "value": stream_t, "threshold": thresholds.get("streaming_min_throughput_events_per_sec", 10000), "pass": summary.get("streaming_pass", False)},
    ]
    max_throughput = max(tpcds_t, stream_t, 1) * 1.2
    throughput_chart = make_bar_chart(throughput_chart_items, max_throughput, "ops/s")

    micro_ops = summary.get("micro_operations", {})
    micro_chart_items = []
    max_micro = 1
    for op_id, op_data in micro_ops.items():
        t = op_data.get("throughput", 0)
        max_micro = max(max_micro, t)
        micro_chart_items.append({"label": op_data.get("name", op_id), "value": t, "threshold": 50000, "pass": t >= 50000})
    max_micro = max_micro * 1.2
    micro_chart = make_bar_chart(micro_chart_items, max_micro, "ops/s") if micro_chart_items else "<p>No micro benchmark data.</p>"

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Flink ARM64 Performance Benchmark Report</title>
{css}
</head>
<body>
<div class="container">
<div class="header">
<h1>Apache Flink ARM64 Performance Benchmark</h1>
<div class="meta">Version: {version} | Architecture: {arch} | Date: {timestamp} | Status: <strong style="color:{overall_color}">{overall_status}</strong></div>
</div>

<h2>Environment</h2>
<table class="env-table">{env_rows}</table>

<div class="metrics-grid">{metric_cards}</div>

<div class="section">
<h2>Throughput Comparison</h2>
{throughput_chart}
</div>

<div class="section">
<h2>TPC-DS Results (Primary Benchmark)</h2>
<p>Reference: TPC-DS specification, HiBench</p>
<table class="results-table">
<tr><th>Query</th><th>Description</th><th>Avg Throughput (ops/sec)</th><th>Avg Elapsed (ms)</th></tr>
{primary_rows}
</table>
</div>

<div class="section">
<h2>Streaming Results (Secondary Benchmark)</h2>
<p>Reference: Nexmark, Flink official examples</p>
<table class="results-table">
<tr><th>Job</th><th>Description</th><th>Avg Throughput (events/sec)</th><th>Avg Latency (ms)</th></tr>
{secondary_rows}
</table>
</div>

<div class="section">
<h2>Micro Benchmark Results</h2>
{micro_chart}
<table class="results-table">
<tr><th>Operation</th><th>Category</th><th>Avg Throughput (ops/sec)</th><th>Avg Latency (ms)</th><th>Data Size (MB)</th></tr>
{micro_rows}
</table>
</div>

<div class="footer">
Generated by flink ARM64 performance benchmark on {timestamp}
</div>
</div>
</body>
</html>""".format(
        css=CSS_STYLE,
        version=data.get("version", "unknown"),
        arch=data.get("architecture", "arm64"),
        timestamp=data.get("timestamp", "unknown"),
        overall_status=overall_status,
        overall_color=overall_color,
        env_rows=env_rows,
        metric_cards=metric_cards,
        throughput_chart=throughput_chart,
        primary_rows=primary_results_rows,
        secondary_rows=secondary_results_rows,
        micro_chart=micro_chart,
        micro_rows=micro_results_rows,
    )

    return html

def main():
    parser = argparse.ArgumentParser(description="Generate HTML report")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    html = generate_html(data)

    with open(args.output, "w") as f:
        f.write(html)

    print("[HTML] Report written to {}".format(args.output))

if __name__ == "__main__":
    main()