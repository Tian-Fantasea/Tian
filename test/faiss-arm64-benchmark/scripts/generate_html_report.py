#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #2c3e50, #3498db); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #ecf0f1; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #3498db; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #f0f8ff; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #2c3e50; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 150px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #2c3e50; margin-left: 8px; white-space: nowrap; }
.status-ok { color: #27ae60; }
.status-warn { color: #e67e22; }
.status-err { color: #e74c3c; }
</style>
"""

def make_bar_chart(title, items, max_val=None):
    if max_val is None:
        max_val = max(v for _, v, _ in items) if items else 1
    html = f'<h3>{title}</h3><div class="bar-chart">'
    for label, value, color in items:
        pct = (value / max_val * 100) if max_val > 0 else 0
        html += f'''<div class="bar-row">
            <div class="bar-label">{label}</div>
            <div class="bar-container"><div class="bar-fill" style="width:{pct:.1f}%;background:{color}"></div></div>
            <div class="bar-value">{value:.2f}</div>
        </div>'''
    html += '</div>'
    return html

def main():
    parser = argparse.ArgumentParser(description='Generate HTML report for benchmark results')
    parser.add_argument('--results-dir', required=True)
    args = parser.parse_args()

    all_results_path = os.path.join(args.results_dir, 'all_results.json')
    if not os.path.exists(all_results_path):
        print('[HTML] all_results.json not found')
        return

    with open(all_results_path, 'r') as f:
        all_data = json.load(f)

    vi = all_data.get('version_info.json', {})
    ann = all_data.get('benchmark_ann.json', {})
    micro = all_data.get('benchmark_micro.json', {})
    timestamp = all_data.get('aggregation_timestamp', '')

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Faiss ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>Faiss ARM64 Performance Benchmark Report</h1>
    <div class="meta">Faiss {vi.get('faiss_version', 'N/A')} | {vi.get('architecture', 'N/A')} | Generated {timestamp}</div>
</div>

<div class="section">
<h2>Environment Information</h2>
<table>
<tr><th>Property</th><th>Value</th></tr>
<tr><td>Architecture</td><td>{vi.get('architecture', 'N/A')}</td></tr>
<tr><td>OS</td><td>{vi.get('os', 'N/A')}</td></tr>
<tr><td>Kernel</td><td>{vi.get('kernel', 'N/A')}</td></tr>
<tr><td>CPU</td><td>{vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)</td></tr>
<tr><td>Memory</td><td>{vi.get('total_memory_gb', 'N/A')} GB</td></tr>
<tr><td>Faiss Version</td><td>{vi.get('faiss_version', 'N/A')}</td></tr>
<tr><td>Python</td><td>{vi.get('python_version', 'N/A')}</td></tr>
<tr><td>NumPy</td><td>{vi.get('numpy_version', 'N/A')}</td></tr>
<tr><td>BLAS</td><td>{vi.get('blas_status', 'N/A')}</td></tr>
</table>
</div>
'''

    if ann:
        results = ann.get('results_summary', {})
        params = ann.get('parameters', {})
        k_val = params.get('k', 10)

        html += '<div class="section"><h2>ANN Search Benchmark</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{ann.get("reference", "")}">{ann.get("reference", "N/A")}</a></p>'
        html += f'<p>Dataset: {params.get("num_vectors", "N/A")} vectors, {params.get("dimension", "N/A")} dims, k={k_val}</p>'

        metric_items = []
        for name, res in results.items():
            if "error" not in res:
                metric_items.append((name, res.get('qps', 0), '#3498db'))
        if metric_items:
            html += make_bar_chart('QPS (Queries Per Second)', metric_items)

        recall_items = []
        recall_key = f'recall_at_{k_val}'
        for name, res in results.items():
            if "error" not in res:
                recall_items.append((name, res.get(recall_key, 0) * 100, '#27ae60'))
        if recall_items:
            html += make_bar_chart(f'Recall@{k_val} (%)', recall_items, max_val=100)

        build_items = []
        for name, res in results.items():
            if "error" not in res:
                build_items.append((name, res.get('build_time_s', 0), '#e67e22'))
        if build_items:
            html += make_bar_chart('Build Time (seconds)', build_items)

        html += '<h3>Detailed Results</h3><table><tr><th>Index</th><th>QPS</th>'
        html += f'<th>Recall@{k_val}</th><th>Build Time (s)</th><th>Latency (us)</th><th>Index Size (bytes)</th></tr>'
        for name, res in results.items():
            if "error" in res:
                html += f'<tr><td>{name}</td><td class="status-err">ERROR</td><td colspan="4">{res["error"]}</td></tr>'
            else:
                html += f'<tr><td>{name}</td><td>{res.get("qps", "N/A")}</td>'
                html += f'<td>{res.get(recall_key, "N/A")}</td><td>{res.get("build_time_s", "N/A")}</td>'
                html += f'<td>{res.get("latency_per_query_us", "N/A")}</td><td>{res.get("index_size_bytes", "N/A")}</td></tr>'
        html += '</table></div>'

    if micro:
        mresults = micro.get('results', {})
        mparams = micro.get('parameters', {})

        html += '<div class="section"><h2>Micro Benchmarks</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">{micro.get("reference", "N/A")}</a></p>'
        html += f'<p>Dataset: {mparams.get("num_vectors", "N/A")} vectors, {mparams.get("dimension", "N/A")} dims</p>'

        html += '<div class="metric-grid">'
        for op_name, res in mresults.items():
            primary_key = next((k for k in res if k not in ('avg_time_s',)), 'avg_time_s')
            primary_val = res.get(primary_key, 0)
            unit = ''
            if 'qps' in primary_key.lower() or 'rate' in primary_key.lower():
                unit = '/sec'
            elif 'latency' in primary_key.lower():
                unit = 'us'
            elif 'time' in primary_key.lower():
                unit = 's'
            html += f'''<div class="metric-card">
                <div class="label">{op_name}</div>
                <div class="value">{primary_val}</div>
                <div class="unit">{unit}</div>
            </div>'''
        html += '</div>'

        html += '<h3>Detailed Results</h3><table><tr><th>Operation</th><th>Results</th></tr>'
        for op_name, res in mresults.items():
            html += f'<tr><td>{op_name}</td><td>{json.dumps(res)}</td></tr>'
        html += '</table></div>'

    html += '''
<div class="section">
<h2>Benchmark Descriptions & References</h2>
<table>
<tr><th>Benchmark</th><th>Description</th><th>Reference</th></tr>
'''

    if ann:
        html += f'<tr><td>ANN Search</td><td>{ann.get("description", "")}</td><td><a href="{ann.get("reference", "")}">{ann.get("reference", "")}</a></td></tr>'
    if micro:
        html += f'<tr><td>Micro Operations</td><td>{micro.get("description", "")}</td><td><a href="{micro.get("reference", "")}">{micro.get("reference", "")}</a></td></tr>'

    html += '</table></div></body></html>'

    output_path = os.path.join(args.results_dir, 'benchmark_report.html')
    with open(output_path, 'w') as f:
        f.write(html)

    print(f'[HTML] Report saved to {output_path}')

if __name__ == '__main__':
    main()