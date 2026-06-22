#!/usr/bin/env python3

import argparse
import json
import os
import sys


CSS = """
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace; background: #f5f5f5; color: #333; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
.header { background: #1a73e8; color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { font-size: 28px; }
.header .meta { font-size: 14px; color: #e0e0e0; margin-top: 10px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { font-size: 20px; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; margin-bottom: 16px; }
.env-table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
.env-table th, .env-table td { padding: 8px 12px; border: 1px solid #ddd; text-align: left; }
.env-table th { background: #e8f0fe; font-weight: 600; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 16px; }
.metric-card { background: #f8f9fa; border: 1px solid #ddd; border-radius: 6px; padding: 16px; }
.metric-card .label { font-size: 12px; color: #666; }
.metric-card .value { font-size: 24px; font-weight: 700; color: #1a73e8; }
.metric-card .unit { font-size: 12px; color: #999; }
.bar-chart { margin-bottom: 16px; }
.bar-row { display: flex; align-items: center; margin-bottom: 6px; }
.bar-label { width: 140px; font-size: 13px; text-align: right; padding-right: 8px; }
.bar-track { flex: 1; background: #e0e0e0; height: 22px; border-radius: 3px; position: relative; }
.bar-fill { height: 100%; background: #1a73e8; border-radius: 3px; min-width: 2px; }
.bar-value { position: absolute; right: 6px; top: 2px; font-size: 11px; color: white; font-weight: 600; }
.results-table { width: 100%; border-collapse: collapse; }
.results-table th, .results-table td { padding: 8px 12px; border: 1px solid #ddd; text-align: left; }
.results-table th { background: #e8f0fe; }
.ok { color: #34a853; font-weight: 600; }
.fail { color: #ea4335; font-weight: 600; }
.ref { font-size: 12px; color: #666; background: #f0f0f0; padding: 8px; border-radius: 4px; margin-top: 8px; }
.shunit-section { background: #e8f5e9; }
.shunit-section h2 { border-bottom-color: #34a853; }
</style>
"""


def make_bar_chart(title, items, max_val=None):
    if not items:
        return f"<h3>{title}</h3><p>No data</p>"
    if max_val is None:
        max_val = max(abs(i.get("value", 0)) for i in items) or 1
    html = f"<h3>{title}</h3><div class='bar-chart'>"
    for item in items:
        val = item.get("value", 0)
        pct = min(abs(val) / max_val * 100, 100)
        html += f"<div class='bar-row'><div class='bar-label'>{item['label']}</div>"
        html += f"<div class='bar-track'><div class='bar-fill' style='width:{pct}%'>"
        html += f"<span class='bar-value'>{val}{item.get('unit', '')}</span></div></div></div>"
    html += "</div>"
    return html


def generate_html_report(results_dir):
    agg_file = os.path.join(results_dir, "all_results.json")
    if not os.path.exists(agg_file):
        print("[HTML] No aggregated results found")
        return

    with open(agg_file, "r") as f:
        data = json.load(f)

    vi = data.get("version_info", {})
    sw = vi.get("software", {})
    benchmarks = data.get("benchmarks", {})

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Apache Flink {sw.get('version', '')} ARM64 Benchmark</title>
{CSS}
</head><body><div class="container">

<div class="header">
<h1>Apache Flink {sw.get('version', '')} ARM64 Performance Benchmark</h1>
<div class="meta">Architecture: {vi.get('architecture', '')} | CPU: {vi.get('cpu_model', '')} ({vi.get('cpu_cores', '')} cores) | Memory: {vi.get('memory_mb', '')} MB | Date: {vi.get('timestamp', '')}</div>
</div>

<div class="section"><h2>Environment Information</h2>
<table class="env-table">
<tr><th>Software</th><td>Apache Flink {sw.get('version', '')}</td></tr>
<tr><th>Scala Version</th><td>{sw.get('scala_version', '')}</td></tr>
<tr><th>Java Version</th><td>{sw.get('java_version', '')}</td></tr>
<tr><th>Architecture</th><td>{vi.get('architecture', '')}</td></tr>
<tr><th>OS</th><td>{vi.get('os', '')}</td></tr>
<tr><th>Kernel</th><td>{vi.get('kernel', '')}</td></tr>
<tr><th>CPU</th><td>{vi.get('cpu_model', '')} ({vi.get('cpu_cores', '')} cores)</td></tr>
<tr><th>Memory</th><td>{vi.get('memory_mb', '')} MB</td></tr>
<tr><th>Task Slots</th><td>{sw.get('task_slots', '')}</td></tr>
<tr><th>Parallelism</th><td>{sw.get('parallelism_default', '')}</td></tr>
<tr><th>ARM64 Native</th><td>{'Yes' if sw.get('arm64_native') else 'No'}</td></tr>
</table></div>
"""

    tpcds = benchmarks.get("tpcds", {})
    tpcds_results = tpcds.get("results", [])
    if tpcds_results:
        html += "<div class='section'><h2>TPC-DS SQL Benchmark</h2>"
        html += f"<div class='ref'>Reference: <a href='{tpcds.get('reference', '')}'>{tpcds.get('reference', '')}</a></div>"
        html += "<div class='metric-grid'>"
        fastest = min(tpcds_results, key=lambda r: r.get("avg_elapsed_sec", 9999))
        html += f"<div class='metric-card'><div class='label'>Fastest Query</div><div class='value'>{fastest.get('avg_elapsed_sec', 0)}s</div><div class='unit'>{fastest.get('query', '')}</div></div>"
        highest_rps = max(tpcds_results, key=lambda r: r.get("avg_records_per_sec", 0))
        html += f"<div class='metric-card'><div class='label'>Highest Throughput</div><div class='value'>{highest_rps.get('avg_records_per_sec', 0)}</div><div class='unit'>records/s</div></div>"
        html += "</div>"
        html += make_bar_chart("Query Execution Time (avg)", [
            {"label": r.get("query", ""), "value": round(r.get("avg_elapsed_sec", 0), 2), "unit": "s"}
            for r in tpcds_results
        ])
        html += "<table class='results-table'><tr><th>Query</th><th>Avg Time (s)</th><th>Avg Throughput (records/s)</th><th>Iterations</th><th>Status</th></tr>"
        for r in tpcds_results:
            status = "<span class='ok'>OK</span>" if r.get("iterations", 0) > 0 else "<span class='fail'>FAIL</span>"
            html += f"<tr><td>{r.get('query', '')}</td><td>{r.get('avg_elapsed_sec', '')}</td><td>{r.get('avg_records_per_sec', '')}</td><td>{r.get('iterations', '')}</td><td>{status}</td></tr>"
        html += "</table></div>"

    streaming = benchmarks.get("streaming", {})
    s_results = streaming.get("results", [])
    if s_results:
        html += "<div class='section'><h2>Streaming Throughput Benchmark</h2>"
        html += f"<div class='ref'>Reference: <a href='{streaming.get('reference', '')}'>{streaming.get('reference', '')}</a></div>"
        html += "<div class='metric-grid'>"
        max_rps = max(s_results, key=lambda r: r.get("avg_records_per_sec", 0))
        html += f"<div class='metric-card'><div class='label'>Peak Throughput</div><div class='value'>{max_rps.get('avg_records_per_sec', 0)}</div><div class='unit'>records/s (p={max_rps.get('parallelism', '')})</div></div>"
        min_lat = min(s_results, key=lambda r: r.get("avg_latency_ms", 99999))
        html += f"<div class='metric-card'><div class='label'>Min Latency</div><div class='value'>{min_lat.get('avg_latency_ms', 0)}</div><div class='unit'>ms</div></div>"
        html += "</div>"
        html += make_bar_chart("Throughput by Parallelism", [
            {"label": f"p={r.get('parallelism', '')}", "value": round(r.get("avg_records_per_sec", 0), 1), "unit": "r/s"}
            for r in s_results
        ])
        html += "<table class='results-table'><tr><th>Config</th><th>Parallelism</th><th>Avg Time (s)</th><th>Avg Throughput</th><th>Avg Latency (ms)</th></tr>"
        for r in s_results:
            html += f"<tr><td>{r.get('config', '')}</td><td>{r.get('parallelism', '')}</td><td>{r.get('avg_elapsed_sec', '')}</td><td>{r.get('avg_records_per_sec', '')}</td><td>{r.get('avg_latency_ms', '')}</td></tr>"
        html += "</table></div>"

    micro = benchmarks.get("micro", {})
    m_results = micro.get("results", [])
    if m_results:
        html += "<div class='section'><h2>Micro Benchmark</h2>"
        html += f"<div class='ref'>Reference: <a href='{micro.get('reference', '')}'>{micro.get('reference', '')}</a></div>"
        html += make_bar_chart("Micro Operation Throughput", [
            {"label": r.get("name", ""), "value": round(r.get("avg_rows_per_sec", 0), 1), "unit": "r/s"}
            for r in m_results
        ])
        html += "<table class='results-table'><tr><th>Operation</th><th>Description</th><th>Avg Time (s)</th><th>Avg Throughput</th></tr>"
        for r in m_results:
            html += f"<tr><td>{r.get('name', '')}</td><td>{r.get('description', '')}</td><td>{r.get('avg_elapsed_sec', '')}</td><td>{r.get('avg_rows_per_sec', '')}</td></tr>"
        html += "</table></div>"

    state = benchmarks.get("state", {})
    st_results = state.get("results", [])
    if st_results:
        html += "<div class='section'><h2>State Backend Benchmark</h2>"
        html += f"<div class='ref'>Reference: <a href='{state.get('reference', '')}'>{state.get('reference', '')}</a></div>"
        html += "<table class='results-table'><tr><th>Test</th><th>Description</th><th>Checkpoint Interval</th><th>Avg Time (s)</th><th>Avg Checkpoint Size (MB)</th></tr>"
        for r in st_results:
            ckpt_mb = round(r.get("avg_checkpoint_size_bytes", 0) / 1024 / 1024, 2)
            html += f"<tr><td>{r.get('name', '')}</td><td>{r.get('description', '')}</td><td>{r.get('checkpoint_interval_ms', '')}ms</td><td>{r.get('avg_elapsed_sec', '')}</td><td>{ckpt_mb}</td></tr>"
        html += "</table></div>"

    html += """
<div class="section shunit-section"><h2>shUnit2 Test Results</h2>
<p>Run <code>flink_arm64_perf_test.sh</code> to see detailed shUnit2 validation results.</p>
<p>Tests cover: architecture check, installation, version, cluster start, WordCount, benchmark output validation, threshold assertions.</p>
</div>

<div class="section"><h2>References</h2>
<ul>
<li><a href="https://www.tpc.org/tpcds/default5.asp">TPC-DS Benchmark Specification</a></li>
<li><a href="https://nightlies.apache.org/flink/flink-docs-stable/docs/ops/metrics/">Flink Metrics Documentation</a></li>
<li><a href="https://nightlies.apache.org/flink/flink-docs-stable/docs/ops/state/state_backends/">Flink State Backends</a></li>
<li><a href="https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/overview/">Flink DataStream Operators</a></li>
<li><a href="https://github.com/kward/shunit2">shUnit2 Testing Framework</a></li>
</ul>
</div>

</div></body></html>"""

    out_file = os.path.join(results_dir, "benchmark_report.html")
    with open(out_file, "w") as f:
        f.write(html)
    print(f"[HTML] Report saved to {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate HTML benchmark report")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    generate_html_report(args.results_dir)


if __name__ == "__main__":
    main()