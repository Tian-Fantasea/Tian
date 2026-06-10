#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #1a73e8, #4285f4); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #e8f0fe; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #1a73e8; border-bottom: 2px solid #4285f4; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #4285f4; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #f0f8ff; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #1a73e8; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 180px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #1a73e8; margin-left: 8px; white-space: nowrap; }
.phase-tag { display: inline-block; background: #e8f0fe; color: #1a73e8; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px; }
</style>
"""

def make_bar_chart(title, items, max_val=None):
    if max_val is None:
        max_val = max(v for _, v, _ in items) if items else 1
    if max_val == 0:
        max_val = 1
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
<title>ScaNN ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>ScaNN ARM64 Performance Benchmark Report</h1>
    <div class="meta">ScaNN {vi.get('scann_version', 'N/A')} | {vi.get('architecture', 'N/A')} | Generated {timestamp}</div>
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
<tr><td>ScaNN Version</td><td>{vi.get('scann_version', 'N/A')}</td></tr>
<tr><td>Python</td><td>{vi.get('python_version', 'N/A')}</td></tr>
<tr><td>NumPy</td><td>{vi.get('numpy_version', 'N/A')}</td></tr>
<tr><td>NEON Support</td><td>{vi.get('neon_support', 'N/A')}</td></tr>
<tr><td>libstdc++</td><td>{vi.get('libstdcxx_version', 'N/A')} (requires >= 3.4.23)</td></tr>
<tr><td>Pybind API</td><td>{vi.get('scann_has_pybind', 'N/A')}</td></tr>
<tr><td>TF Ops</td><td>{vi.get('scann_has_tf_ops', 'N/A')}</td></tr>
</table>
</div>
'''

    if ann:
        results = ann.get('results_summary', {})
        params = ann.get('parameters', {})
        k_val = params.get('k', 10)

        html += '<div class="section"><h2>ANN Search Benchmark</h2>'
        html += f'<p><strong>Reference:</strong> <a href="https://ann-benchmarks.com">ann-benchmarks.com</a> and <a href="https://github.com/google-research/google-research/tree/master/scann">ScaNN repo</a></p>'
        html += f'<p>Dataset: {params.get("num_vectors", "N/A")} vectors, {params.get("dimension", "N/A")} dims, k={k_val}</p>'

        html += '<h3>ScaNN Three-Phase Search Pipeline</h3>'
        html += '<p><span class="phase-tag">Phase 1: Partitioning</span> <span class="phase-tag">Phase 2: AH Scoring</span> <span class="phase-tag">Phase 3: Rescoring</span></p>'

        qps_items = []
        for name, res in results.items():
            if isinstance(res, dict) and "qps" in res:
                qps_items.append((name, res.get('qps', 0), '#4285f4'))
        if qps_items:
            html += make_bar_chart('QPS (Queries Per Second)', qps_items)

        recall_items = []
        recall_key = f'recall_at_{k_val}'
        for name, res in results.items():
            if isinstance(res, dict) and recall_key in res:
                recall_items.append((name, res.get(recall_key, 0) * 100, '#34a853'))
        if recall_items:
            html += make_bar_chart(f'Recall@{k_val} (%)', recall_items, max_val=100)

        build_items = []
        for name, res in results.items():
            if isinstance(res, dict) and "build_time_s" in res:
                build_items.append((name, res.get('build_time_s', 0), '#ea4335'))
        if build_items:
            html += make_bar_chart('Build Time (seconds)', build_items)

        sweep_data = results.get('TreeAH_leaves_sweep', {})
        if sweep_data and "error" not in sweep_data:
            html += '<h3>leaves_to_search vs Recall/QPS Trade-off</h3>'
            sweep_recall_items = []
            sweep_qps_items = []
            avg_recall_key = f'avg_recall_at_{k_val}'
            for label, sres in sweep_data.items():
                sweep_recall_items.append((label, sres.get(avg_recall_key, 0) * 100, '#34a853'))
                sweep_qps_items.append((label, sres.get('avg_qps', 0), '#4285f4'))
            if sweep_recall_items:
                html += make_bar_chart(f'Leaves Sweep: Recall@{k_val} (%)', sweep_recall_items, max_val=100)
            if sweep_qps_items:
                html += make_bar_chart('Leaves Sweep: QPS', sweep_qps_items)

            html += '<table><tr><th>leaves_to_search</th><th>num_leaves</th><th>QPS</th><th>Recall@{k_val}</th><th>Latency (us)</th></tr>'
            for label, sres in sweep_data.items():
                html += f'<tr><td>{sres.get("leaves_to_search", "N/A")}</td><td>{sres.get("num_leaves", "N/A")}</td>'
                html += f'<td>{sres.get("avg_qps", "N/A")}</td><td>{sres.get(avg_recall_key, "N/A")}</td>'
                html += f'<td>{sres.get("avg_latency_per_query_us", "N/A")}</td></tr>'
            html += '</table>'

        html += '<h3>Detailed Results per Index Configuration</h3><table>'
        html += f'<tr><th>Config</th><th>QPS</th><th>Recall@{k_val}</th><th>Build Time (s)</th><th>Latency (us)</th><th>Description</th></tr>'
        config_descs = {}
        if ann.get('parameters', {}).get('index_configs'):
            config_descs = ann['parameters']['index_configs']
        for name, res in results.items():
            if name == 'TreeAH_leaves_sweep':
                continue
            if isinstance(res, dict) and "error" in res:
                html += f'<tr><td>{name}</td><td class="status-err">ERROR</td><td colspan="4">{res["error"]}</td></tr>'
            elif isinstance(res, dict) and "qps" in res:
                desc = config_descs.get(name, {}).get('description', '')
                html += f'<tr><td>{name}</td><td>{res.get("qps", "N/A")}</td>'
                html += f'<td>{res.get(recall_key, "N/A")}</td><td>{res.get("build_time_s", "N/A")}</td>'
                html += f'<td>{res.get("latency_per_query_us", "N/A")}</td><td>{desc}</td></tr>'
        html += '</table></div>'

    if micro:
        mresults = micro.get('results', {})
        mparams = micro.get('parameters', {})

        html += '<div class="section"><h2>Micro Benchmarks</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">{micro.get("reference", "N/A")}</a></p>'
        html += f'<p>Dataset: {mparams.get("num_vectors", "N/A")} vectors, {mparams.get("dimension", "N/A")} dims</p>'

        if "build_times" in mresults:
            bt = mresults["build_times"]
            html += '<h3>Build Time Comparison</h3>'
            build_items = [(name, res.get('avg_build_time_s', 0), '#ea4335') for name, res in bt.items()]
            html += make_bar_chart('Build Time (seconds)', build_items)

        if "search_latency_by_batch" in mresults:
            sl = mresults["search_latency_by_batch"]
            html += '<h3>Batch Size vs QPS</h3>'
            batch_items = [(name, res.get('avg_qps', 0), '#4285f4') for name, res in sl.items()]
            html += make_bar_chart('QPS at Different Batch Sizes', batch_items)

            html += '<h3>Batch Size vs Latency</h3>'
            latency_items = [(name, res.get('avg_latency_per_query_us', 0), '#ea4335') for name, res in sl.items()]
            html += make_bar_chart('Latency per Query (us) at Different Batch Sizes', latency_items)

        if "reorder_sweep" in mresults:
            rs = mresults["reorder_sweep"]
            avg_recall_key = f'avg_recall_at_{k_val}'
            html += '<h3>reordering_num_neighbors Sweep</h3>'
            reorder_recall = [(name, res.get(avg_recall_key, 0) * 100, '#34a853') for name, res in rs.items()]
            html += make_bar_chart(f'Recall@{k_val} (%) vs reorder_k', reorder_recall, max_val=100)
            reorder_qps = [(name, res.get('avg_qps', 0), '#4285f4') for name, res in rs.items()]
            html += make_bar_chart('QPS vs reorder_k', reorder_qps)

        if "dims_per_block_sweep" in mresults:
            dpb = mresults["dims_per_block_sweep"]
            dpb_items = [(name, res.get('avg_qps', 0), '#4285f4') for name, res in dpb.items()]
            html += make_bar_chart('QPS vs dimensions_per_block', dpb_items)

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
        html += f'<tr><td>ANN Search</td><td>{ann.get("description", "")}</td><td><a href="https://ann-benchmarks.com">ann-benchmarks.com</a></td></tr>'
    if micro:
        html += f'<tr><td>Micro Operations</td><td>{micro.get("description", "")}</td><td><a href="{micro.get("reference", "")}">ScaNN repo</a></td></tr>'

    html += '</table></div></body></html>'

    output_path = os.path.join(args.results_dir, 'benchmark_report.html')
    with open(output_path, 'w') as f:
        f.write(html)

    print(f'[HTML] Report saved to {output_path}')

if __name__ == '__main__':
    main()