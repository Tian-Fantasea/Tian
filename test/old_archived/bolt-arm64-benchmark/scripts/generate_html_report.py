#!/usr/bin/env python3

import argparse
import json
import os
import sys


def generate_html_bar(values, labels, title, unit, max_val=None):
    if not values:
        return "<p>No data available</p>"
    if max_val is None:
        max_val = max(values) * 1.2 if values else 1
    bars = ""
    for label, val in zip(labels, values):
        pct = (val / max_val) * 100 if max_val > 0 else 0
        bars += f'<div class="bar-row"><span class="bar-label">{label}</span>'
        bars += f'<div class="bar-container"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>'
        bars += f'<span class="bar-value">{val:.1f} {unit}</span></div>'
    return f'<div class="chart"><h4>{title}</h4>{bars}</div>'


def generate_html_report(results_dir):
    all_path = os.path.join(results_dir, "all_results.json")
    if not os.path.exists(all_path):
        print("[HTML] No aggregated results found", file=sys.stderr)
        return

    with open(all_path, "r") as f:
        all_data = json.load(f)

    vi = all_data.get("version_info", {})
    sw = vi.get("software", {})

    env_rows = ""
    env_items = [
        ("Software", f"bbolt v{sw.get('version', 'N/A')}"),
        ("Runtime", f"{sw.get('runtime_language', 'N/A')} {sw.get('runtime_version', 'N/A')}"),
        ("Architecture", vi.get("architecture", "N/A")),
        ("CPU", f"{vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)"),
        ("Memory", f"{vi.get('memory_mb', 'N/A')} MB"),
        ("Kernel", vi.get("kernel", "N/A")),
        ("OS", vi.get("os", "N/A")),
        ("Timestamp", vi.get("timestamp", "N/A")),
    ]
    for label, val in env_items:
        env_rows += f'<tr><td>{label}</td><td>{val}</td></tr>'

    charts = ""
    bench_sections = ""

    for bench in all_data.get("benchmarks", []):
        name = bench.get("benchmark", "unknown")
        desc = bench.get("description", "N/A")
        results = bench.get("results", [])

        if not results:
            continue

        ops_vals = []
        lat_vals = []
        labels = []
        for r in results:
            if isinstance(r, dict):
                wl = r.get("workload", r.get("operation", r.get("key_count", r.get("goroutines", ""))))
                ops = r.get("ops_per_sec", r.get("OpsPerSec", 0))
                lat = r.get("avg_latency_ms", r.get("AvgLatencyMs", 0))
                if ops > 0:
                    ops_vals.append(ops)
                    lat_vals.append(lat)
                    labels.append(str(wl))

        if ops_vals:
            charts += generate_html_bar(ops_vals, labels, f"{name} - Throughput", "ops/s")

        rows = ""
        for r in results:
            if isinstance(r, dict):
                wl = r.get("workload", r.get("operation", r.get("key_count", r.get("goroutines", "N/A"))))
                ops = r.get("ops_per_sec", r.get("OpsPerSec", 0))
                lat = r.get("avg_latency_ms", r.get("AvgLatencyMs", 0))
                dur = r.get("duration_sec", r.get("DurationSec", 0))
                rows += f'<tr><td>{wl}</td><td>{ops:.1f}</td><td>{lat:.2f}</td><td>{dur:.2f}</td></tr>'

        bench_sections += f'''
        <div class="bench-section">
            <h3>{name}</h3>
            <p>{desc}</p>
            <table>
                <tr><th>Workload/Op</th><th>Ops/sec</th><th>Latency(ms)</th><th>Duration(s)</th></tr>
                {rows}
            </table>
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>bbolt ARM64 Performance Benchmark Report</title>
<style>
body { font-family: monospace; max-width: 960px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
h1 { color: #00d4ff; border-bottom: 2px solid #00d4ff; }
h2 { color: #7b68ee; }
h3 { color: #ffd700; }
h4 { color: #98fb98; margin-bottom: 5px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th, td { padding: 8px; text-align: left; border: 1px solid #444; }
th { background: #2d2d44; color: #00d4ff; }
.env-table th { width: 30%; }
.bench-section { margin: 20px 0; padding: 15px; background: #2d2d44; border-radius: 8px; }
.chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 5px 0; }
.bar-label { width: 150px; text-align: right; padding-right: 10px; font-size: 13px; }
.bar-container { flex: 1; background: #333; height: 20px; border-radius: 3px; }
.bar-fill { background: linear-gradient(90deg, #00d4ff, #7b68ee); height: 100%; border-radius: 3px; }
.bar-value { width: 120px; font-size: 13px; }
.card-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
.metric-card { background: #2d2d44; padding: 15px; border-radius: 8px; text-align: center; }
.metric-card .value { font-size: 24px; color: #00d4ff; }
.metric-card .label { font-size: 12px; color: #888; }
</style>
</head>
<body>
<h1>bbolt ARM64 Performance Benchmark Report</h1>

<h2>Environment Information</h2>
<table class="env-table">
<tr><th>Property</th><th>Value</th></tr>
{env_rows}
</table>

<h2>Metric Summary</h2>
<div class="card-grid">
<div class="metric-card"><div class="value">bbolt v{sw.get('version', 'N/A')}</div><div class="label">Software Version</div></div>
<div class="metric-card"><div class="value">{vi.get('architecture', 'N/A')}</div><div class="label">Architecture</div></div>
<div class="metric-card"><div class="value">{vi.get('cpu_cores', 'N/A')} cores</div><div class="label">CPU Cores</div></div>
</div>

<h2>Performance Charts</h2>
{charts}

<h2>Detailed Results</h2>
{bench_sections}

<p style="color:#888; text-align:center; margin-top:40px;">Generated by bbolt ARM64 Performance Benchmark Workflow</p>
</body>
</html>'''

    out_path = os.path.join(results_dir, "benchmark_report.html")
    with open(out_path, "w") as f:
        f.write(html)
    print(f"[HTML] Report saved to {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()
    generate_html_report(args.results_dir)


if __name__ == "__main__":
    main()