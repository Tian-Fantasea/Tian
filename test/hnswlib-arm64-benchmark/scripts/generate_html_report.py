#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #2c3e50, #27ae60); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #ecf0f1; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #2c3e50; border-bottom: 2px solid #27ae60; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #27ae60; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #f0f8ff; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #2c3e50; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 160px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #2c3e50; margin-left: 8px; white-space: nowrap; }
.tab-container { margin: 15px 0; }
.tab-buttons { display: flex; gap: 5px; margin-bottom: 10px; }
.tab-btn { padding: 8px 16px; border: 1px solid #ddd; border-radius: 4px; background: #ecf0f1; cursor: pointer; font-size: 13px; }
.tab-btn.active { background: #27ae60; color: white; border-color: #27ae60; }
.tab-content { display: none; }
.tab-content.active { display: block; }
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
<title>hnswlib ARM64 Performance Benchmark Report</title>{CSS}
<script>
function switchTab(tabId) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    document.getElementById('btn-' + tabId).classList.add('active');
}}
</script></head><body>

<div class="header">
    <h1>hnswlib ARM64 Performance Benchmark Report</h1>
    <div class="meta">hnswlib {vi.get('hnswlib_version', 'N/A')} | {vi.get('architecture', 'N/A')} | Generated {timestamp}</div>
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
<tr><td>hnswlib Version</td><td>{vi.get('hnswlib_version', 'N/A')}</td></tr>
<tr><td>Python</td><td>{vi.get('python_version', 'N/A')}</td></tr>
<tr><td>NumPy</td><td>{vi.get('numpy_version', 'N/A')}</td></tr>
</table>
</div>
'''

    if ann:
        results = ann.get('results_summary', {})
        params = ann.get('parameters', {})
        k_val = params.get('k', 10)
        ef_values = params.get('ef_search_values', [10, 50, 100, 200, 500])

        html += '<div class="section"><h2>ANN Search Benchmark</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{ann.get("reference", "")}">{ann.get("reference", "N/A")}</a></p>'
        html += f'<p>Dataset: {params.get("num_vectors", "N/A")} vectors, {params.get("dimension", "N/A")} dims, k={k_val}</p>'

        for ef in ef_values:
            metric_items = []
            for name, res in results.items():
                if "error" not in res:
                    ef_sweep = res.get('avg_ef_sweep', {})
                    ef_data = ef_sweep.get(ef, {})
                    metric_items.append((name, ef_data.get('qps', 0), '#3498db'))
            if metric_items:
                html += make_bar_chart(f'QPS at ef_search={ef}', metric_items)

        recall_items_best = []
        for name, res in results.items():
            if "error" not in res:
                ef_sweep = res.get('avg_ef_sweep', {})
                max_ef = max(ef_sweep.keys()) if ef_sweep else 0
                best_recall = ef_sweep.get(max_ef, {}).get(f'recall_at_{k_val}', 0) * 100
                recall_items_best.append((name, best_recall, '#27ae60'))
        if recall_items_best:
            html += make_bar_chart(f'Best Recall@{k_val} (%) at max ef_search', recall_items_best, max_val=100)

        build_items = []
        for name, res in results.items():
            if "error" not in res:
                build_items.append((name, res.get('avg_build_time_s', 0), '#e67e22'))
        if build_items:
            html += make_bar_chart('Build Time (seconds)', build_items)

        html += '<h3>ef_search vs Recall/QPS Trade-off</h3>'
        html += '<div class="tab-container"><div class="tab-buttons">'
        for idx, name in enumerate(results.keys()):
            tab_id = f'ef-tab-{idx}'
            html += f'<div class="tab-btn" id="btn-{tab_id}" onclick="switchTab(\'{tab_id}\')">{name}</div>'
        html += '</div>'

        for idx, (name, res) in enumerate(results.items()):
            tab_id = f'ef-tab-{idx}'
            active_class = 'active' if idx == 0 else ''
            html += f'<div class="tab-content {active_class}" id="{tab_id}">'
            html += '<table><tr><th>ef_search</th><th>QPS</th><th>Recall@{k_val}</th><th>Latency (us)</th></tr>'
            ef_sweep = res.get('avg_ef_sweep', {})
            for ef, ef_res in sorted(ef_sweep.items()):
                recall_key = f'recall_at_{k_val}'
                html += f'<tr><td>{ef}</td><td>{ef_res.get("qps", "N/A")}</td>'
                html += f'<td>{ef_res.get(recall_key, "N/A")}</td><td>{ef_res.get("latency_per_query_us", "N/A")}</td></tr>'
            html += '</table></div>'
        html += '</div>'

        html += '<h3>Detailed Results per Index Configuration</h3><table>'
        html += '<tr><th>Config</th><th>Build Time (s)</th><th>Index Size (bytes)</th><th>Best Recall</th><th>Best QPS</th></tr>'
        for name, res in results.items():
            if "error" in res:
                html += f'<tr><td>{name}</td><td class="status-err">ERROR</td><td colspan="3">{res["error"]}</td></tr>'
            else:
                ef_sweep = res.get('avg_ef_sweep', {})
                best_ef = max(ef_sweep.keys()) if ef_sweep else 0
                best_recall = ef_sweep.get(best_ef, {}).get(f'recall_at_{k_val}', 'N/A')
                best_qps_entry = max(ef_sweep.values(), key=lambda x: x.get('qps', 0)) if ef_sweep else {}
                html += f'<tr><td>{name}</td><td>{res.get("avg_build_time_s", "N/A")}</td>'
                html += f'<td>{res.get("avg_index_size_bytes", "N/A")}</td>'
                html += f'<td>{best_recall}</td><td>{best_qps_entry.get("qps", "N/A")}</td></tr>'
        html += '</table></div>'

    if micro:
        mresults = micro.get('results', {})
        mparams = micro.get('parameters', {})

        html += '<div class="section"><h2>Micro Benchmarks</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">{micro.get("reference", "N/A")}</a></p>'
        html += f'<p>Dataset: {mparams.get("num_vectors", "N/A")} vectors, {mparams.get("dimension", "N/A")} dims</p>'

        html += '<div class="metric-grid">'
        key_metrics = {
            "index_construction": ("avg_add_rate_per_sec", "vectors/sec"),
            "incremental_insert": ("avg_add_rate_per_sec", "vectors/sec"),
            "serialization_save_load": ("avg_save_time_s", "s"),
            "pickle_serialization": ("avg_pickle_time_s", "s"),
        }
        for op_name, (key, unit) in key_metrics.items():
            if op_name in mresults:
                val = mresults[op_name].get(key, 0)
                html += f'''<div class="metric-card">
                    <div class="label">{op_name}</div>
                    <div class="value">{val}</div>
                    <div class="unit">{unit}</div>
                </div>'''
        html += '</div>'

        if "batch_search_multithread" in mresults:
            mt = mresults["batch_search_multithread"]
            mt_items = []
            for thread_label, mt_res in mt.items():
                mt_items.append((thread_label, mt_res.get('avg_qps', 0), '#3498db'))
            if mt_items:
                html += make_bar_chart('Multi-threaded Search QPS', mt_items)

        if "ef_parameter_sweep" in mresults:
            sweep = mresults["ef_parameter_sweep"]
            sweep_items = []
            for ef_label, sweep_res in sweep.items():
                sweep_items.append((ef_label, sweep_res.get('avg_recall', 0) * 100, '#27ae60'))
            if sweep_items:
                html += make_bar_chart('ef Parameter Sweep: Recall (%)', sweep_items, max_val=100)

            sweep_qps_items = []
            for ef_label, sweep_res in sweep.items():
                sweep_qps_items.append((ef_label, sweep_res.get('avg_qps', 0), '#3498db'))
            if sweep_qps_items:
                html += make_bar_chart('ef Parameter Sweep: QPS', sweep_qps_items)

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