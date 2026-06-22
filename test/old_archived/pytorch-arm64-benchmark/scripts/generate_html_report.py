#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #ee4c2c, #c05621); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #fde8e0; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #ee4c2c; border-bottom: 2px solid #c05621; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #ee4c2c; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #fde8e0; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #ee4c2c; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 200px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #ee4c2c; margin-left: 8px; white-space: nowrap; }
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
            <div class="bar-value">{value:.4f}</div>
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
    compute = all_data.get('benchmark_compute.json', {})
    training = all_data.get('benchmark_training.json', {})
    micro = all_data.get('benchmark_micro.json', {})
    timestamp = all_data.get('aggregation_timestamp', '')

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PyTorch ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>PyTorch ARM64 Performance Benchmark Report</h1>
    <div class="meta">PyTorch {vi.get('pytorch_version', 'N/A')} | {vi.get('architecture', 'N/A')} | {vi.get('cpu_cores', 'N/A')} cores | Generated {timestamp}</div>
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
<tr><td>PyTorch Version</td><td>{vi.get('pytorch_version', 'N/A')}</td></tr>
<tr><td>Python</td><td>{vi.get('python_version', 'N/A')}</td></tr>
<tr><td>NumPy</td><td>{vi.get('numpy_version', 'N/A')}</td></tr>
<tr><td>CUDA Available</td><td>{vi.get('cuda_available', 'N/A')}</td></tr>
<tr><td>torch Threads</td><td>{vi.get('torch_num_threads', 'N/A')}</td></tr>
<tr><td>torch.compile</td><td>{vi.get('has_compile', 'N/A')}</td></tr>
<tr><td>SIMD</td><td>{json.dumps(vi.get('simd_info', {}))}</td></tr>
</table>
</div>
'''

    if compute:
        results = compute.get('results', {})

        html += '<div class="section"><h2>Operator Compute Benchmark</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{compute.get("reference", "")}">PyTorch ops</a></p>'

        matmul_items = []
        for name, res in results.items():
            if name.startswith("matmul") and "error" not in res:
                matmul_items.append((name, res.get('avg_time_ms', 0), '#ee4c2c'))
        if matmul_items:
            html += make_bar_chart('Matmul Execution Time (ms)', matmul_items)

        matmul_tflops = []
        for name, res in results.items():
            if name.startswith("matmul") and "tflops" in res:
                matmul_tflops.append((name, res.get('tflops', 0), '#34a853'))
        if matmul_tflops:
            html += make_bar_chart('Matmul TFLOPS', matmul_tflops)

        other_items = []
        for name, res in results.items():
            if not name.startswith("matmul") and "error" not in res:
                other_items.append((name, res.get('avg_time_ms', 0), '#4285f4'))
        if other_items:
            html += make_bar_chart('Other Operators Execution Time (ms)', other_items)

        html += '<h3>Detailed Results</h3><table><tr><th>Operator</th><th>Time (ms)</th><th>TFLOPS</th><th>Description</th></tr>'
        configs = compute.get('operator_configs', {})
        for name, res in results.items():
            if "error" in res:
                html += f'<tr><td>{name}</td><td style="color:#e74c3c">ERROR</td><td>-</td><td>{res["error"]}</td></tr>'
            else:
                desc = configs.get(name, {}).get('description', '')
                tflops_val = res.get('tflops', 'N/A')
                html += f'<tr><td>{name}</td><td>{res.get("avg_time_ms", "N/A")}</td><td>{tflops_val}</td><td>{desc}</td></tr>'
        html += '</table></div>'

    if training:
        results = training.get('results', {})
        model_configs = training.get('model_configs', {})

        html += '<div class="section"><h2>Training & Inference Throughput Benchmark</h2>'
        html += f'<p><strong>Reference:</strong> <a href="https://mlcommons.org/en/mlperf-training">MLPerf</a></p>'

        for model_name, model_info in model_configs.items():
            train_items = []
            inf_items = []
            unit = model_info.get('unit', 'N/A')
            for result_name, res in results.items():
                if result_name.startswith(model_name) and "error" not in res:
                    if res.get('mode') == 'training':
                        train_items.append((f"bs={res.get('batch_size', '?')}", res.get('throughput', 0), '#ee4c2c'))
                    elif res.get('mode') == 'inference':
                        inf_items.append((f"bs={res.get('batch_size', '?')}", res.get('throughput', 0), '#4285f4'))

            if train_items:
                html += make_bar_chart(f'{model_name} Training Throughput ({unit})', train_items)
            if inf_items:
                html += make_bar_chart(f'{model_name} Inference Throughput ({unit})', inf_items)

        html += '<h3>Detailed Results</h3>'
        html += '<table><tr><th>Model+Batch</th><th>Mode</th><th>Batch Size</th><th>Time (ms)</th><th>Throughput</th><th>Unit</th></tr>'
        for name, res in results.items():
            if "error" in res:
                html += f'<tr><td>{name}</td><td>{res.get("mode","?")}</td><td>{res.get("batch_size","?")}</td>'
                html += f'<td style="color:#e74c3c">ERROR</td><td>-</td><td>-</td></tr>'
            else:
                html += f'<tr><td>{name}</td><td>{res.get("mode","?")}</td><td>{res.get("batch_size","?")}</td>'
                html += f'<td>{res.get("avg_time_ms","N/A")}</td><td>{res.get("throughput","N/A")}</td><td>{res.get("unit","N/A")}</td></tr>'
        html += '</table></div>'

    if micro:
        mresults = micro.get('results', {})

        html += '<div class="section"><h2>Micro Benchmarks (Memory, Compile, Data)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">PyTorch</a></p>'

        html += '<div class="metric-grid">'

        if "compile_speed" in mresults:
            cs = mresults["compile_speed"]
            if "eager_vs_compile_eager" in cs:
                ev = cs["eager_vs_compile_eager"]
                html += f'''<div class="metric-card">
                    <div class="label">torch.compile Speedup</div>
                    <div class="value">{ev.get("speedup", "N/A")}x</div>
                    <div class="unit">eager vs compiled</div>
                </div>'''

        if "memory_transfer" in mresults:
            mt = mresults["memory_transfer"]
            max_rate_item = max(mt.values(), key=lambda x: x.get('copy_rate_MB_per_sec', 0))
            html += f'''<div class="metric-card">
                <div class="label">Peak Memory Copy Rate</div>
                <div class="value">{max_rate_item.get("copy_rate_MB_per_sec", "N/A")}</div>
                <div class="unit">MB/sec</div>
            </div>'''

        html += '</div>'

        if "tensor_creation" in mresults:
            tc_items = [(name, res.get('avg_time_ms', 0), '#ee4c2c') for name, res in mresults["tensor_creation"].items()]
            html += make_bar_chart('Tensor Creation Time (ms)', tc_items)

        if "memory_transfer" in mresults:
            mt_items = [(name, res.get('copy_rate_MB_per_sec', 0), '#4285f4') for name, res in mresults["memory_transfer"].items()]
            html += make_bar_chart('Memory Copy Rate (MB/sec)', mt_items)

        if "dtype_conversion" in mresults:
            dc_items = [(name, res.get('conversion_rate_Melements_per_sec', 0), '#34a853') for name, res in mresults["dtype_conversion"].items()]
            html += make_bar_chart('dtype Conversion Rate (M elements/sec)', dc_items)

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
    if compute:
        html += f'<tr><td>Operator Compute</td><td>{compute.get("description", "")}</td><td>PyTorch ops</td></tr>'
    if training:
        html += f'<tr><td>Training/Inference</td><td>{training.get("description", "")}</td><td><a href="https://mlcommons.org/en/mlperf-training">MLPerf</a></td></tr>'
    if micro:
        html += f'<tr><td>Micro Operations</td><td>{micro.get("description", "")}</td><td><a href="https://pytorch.org">PyTorch</a></td></tr>'
    html += '</table></div></body></html>'

    output_path = os.path.join(args.results_dir, 'benchmark_report.html')
    with open(output_path, 'w') as f:
        f.write(html)

    print(f'[HTML] Report saved to {output_path}')

if __name__ == '__main__':
    main()