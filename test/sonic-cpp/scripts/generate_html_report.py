#!/usr/bin/env python3
import json
import os
import sys
import datetime


CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #ff6b35, #f7931e); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #ffe0b2; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #ff6b35; border-bottom: 2px solid #f7931e; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #ff6b35; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #fff3e0; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #ff6b35; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 180px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #ff6b35; margin-left: 8px; white-space: nowrap; }
.phase-tag { display: inline-block; background: #fff3e0; color: #ff6b35; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px; }
.feature-yes { color: #10b981; font-weight: bold; }
.feature-no { color: #ef4444; font-weight: bold; }
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
    if len(sys.argv) < 3:
        print("Usage: generate_html_report.py <input_json> <output_html>")
        sys.exit(1)

    input_json = sys.argv[1]
    output_html = sys.argv[2]

    if not os.path.exists(input_json):
        print('[HTML] Input JSON not found')
        return

    with open(input_json, 'r') as f:
        all_data = json.load(f)

    vi = all_data.get('version_info', {})
    primary = all_data.get('primary_benchmark', {})
    secondary = all_data.get('secondary_benchmark', {})
    micro = all_data.get('micro_benchmark', {})
    timestamp = all_data.get('aggregation_timestamp', '')

    sonic_ver = vi.get('version', 'N/A')
    gpp_ver = vi.get('runtime_version', 'N/A')

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>sonic-cpp ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>sonic-cpp ARM64 Performance Benchmark Report</h1>
    <div class="meta">sonic-cpp {sonic_ver} | {vi.get('architecture', 'N/A')} | g++ {gpp_ver} | Generated {timestamp}</div>
</div>

<div class="section">
<h2>Environment Information</h2>
<table>
<tr><th>Property</th><th>Value</th></tr>
<tr><td>Architecture</td><td>{vi.get('architecture', 'N/A')}</td></tr>
<tr><td>OS</td><td>{vi.get('os', 'N/A')}</td></tr>
<tr><td>Kernel</td><td>{vi.get('kernel', 'N/A')}</td></tr>
<tr><td>CPU</td><td>{vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)</td></tr>
<tr><td>Memory</td><td>{vi.get('total_memory_mb', 'N/A')} MB</td></tr>
<tr><td>G++</td><td>{gpp_ver}</td></tr>
<tr><td>sonic-cpp</td><td>{sonic_ver}</td></tr>
<tr><td>sonic-cpp Home</td><td>{vi.get('home', 'N/A')}</td></tr>
<tr><td>sonic-cpp Git</td><td>{vi.get('runtime_detail', 'N/A')}</td></tr>
'''

    extra = vi.get('extra_info', {})
    if extra:
        html += f'<tr><td>Compile Flags</td><td>{extra.get("compile_flags", "N/A")}</td></tr>'
        html += f'<tr><td>Compile Test</td><td>{extra.get("compile_test", "N/A")}</td></tr>'
        html += f'<tr><td>JSON Sizes</td><td>{extra.get("json_sizes", "N/A")}</td></tr>'

    html += '</table></div>'

    if primary:
        html += '<div class="section"><h2>JSON Parse Throughput Benchmark</h2>'
        html += '<p><span class="phase-tag">Phase 3a: Parse vs Size</span></p>'

        parse_items = []
        for result in primary.get('results', []):
            if result.get('test') == 'parse_throughput_vs_size':
                for d in result.get('data', []):
                    size = d.get('json_size', 'unknown')
                    tp = d.get('avg_throughput_mb_per_sec', 0)
                    parse_items.append((f'{size} ({d.get("json_bytes", 0)}B)', tp, '#ff6b35'))

        if parse_items:
            html += make_bar_chart('Parse Throughput (MB/s)', parse_items)

        html += '<h3>Detailed Parse Results</h3><table>'
        html += '<tr><th>JSON Size</th><th>Bytes</th><th>Throughput (MB/s)</th><th>Latency (ms)</th></tr>'
        for result in primary.get('results', []):
            if result.get('test') == 'parse_throughput_vs_size':
                for d in result.get('data', []):
                    html += f'<tr><td>{d.get("json_size", "N/A")}</td><td>{d.get("json_bytes", 0)}</td>'
                    html += f'<td>{d.get("avg_throughput_mb_per_sec", 0):.2f}</td>'
                    html += f'<td>{d.get("avg_latency_ms", 0):.2f}</td></tr>'
        html += '</table></div>'

    if secondary:
        html += '<div class="section"><h2>JSON Serialize & ParseOnDemand</h2>'
        html += '<p><span class="phase-tag">Phase 3b: Serialize</span> <span class="phase-tag">ParseOnDemand</span></p>'

        ser_items = []
        od_items = []
        for result in secondary.get('results', []):
            if result.get('test') == 'serialize_throughput_vs_size':
                for d in result.get('data', []):
                    ser_items.append((d.get('json_size', 'unknown'), d.get('avg_throughput_mb_per_sec', 0), '#f7931e'))
            elif result.get('test') == 'ondemand_key_lookup_vs_size':
                for d in result.get('data', []):
                    od_items.append((f'{d.get("json_size", "unknown")} "{d.get("target_key", "")}"',
                                     d.get('avg_throughput_mb_per_sec', 0), '#3b82f6'))

        if ser_items:
            html += make_bar_chart('Serialize Throughput (MB/s)', ser_items)
        if od_items:
            html += make_bar_chart('ParseOnDemand Throughput (MB/s)', od_items)

        html += '<h3>Detailed Serialize Results</h3><table>'
        html += '<tr><th>Size</th><th>Throughput (MB/s)</th><th>Latency (ms)</th></tr>'
        for result in secondary.get('results', []):
            if result.get('test') == 'serialize_throughput_vs_size':
                for d in result.get('data', []):
                    html += f'<tr><td>{d.get("json_size", "N/A")}</td><td>{d.get("avg_throughput_mb_per_sec", 0):.2f}</td>'
                    html += f'<td>{d.get("avg_latency_ms", 0):.2f}</td></tr>'
        html += '</table>'

        html += '<h3>ParseOnDemand Results</h3><table>'
        html += '<tr><th>Size</th><th>Target Key</th><th>Throughput (MB/s)</th><th>Latency (ms)</th></tr>'
        for result in secondary.get('results', []):
            if result.get('test') == 'ondemand_key_lookup_vs_size':
                for d in result.get('data', []):
                    html += f'<tr><td>{d.get("json_size", "N/A")}</td><td>{d.get("target_key", "N/A")}</td>'
                    html += f'<td>{d.get("avg_throughput_mb_per_sec", 0):.2f}</td>'
                    html += f'<td>{d.get("avg_latency_ms", 0):.2f}</td></tr>'
        html += '</table></div>'

    if micro:
        html += '<div class="section"><h2>Micro Benchmarks</h2>'
        html += '<p><span class="phase-tag">Phase 3c: SIMD Detection</span> <span class="phase-tag">Optimization Comparison</span></p>'

        for result in micro.get('results', []):
            if result.get('test') == 'arm64_simd_detection':
                data = result.get('data', {})
                html += '<h3>ARM64 SIMD Feature Detection</h3><table>'
                html += '<tr><th>Feature</th><th>Available</th><th>Impact on sonic-cpp</th></tr>'
                features = [
                    ('NEON', data.get('neon', False), 'SIMD whitespace skip, escaped char find (~2-4x faster)'),
                    ('ASIMD (Advanced SIMD)', data.get('asimd', False), 'ARMv8 advanced SIMD, same as NEON on aarch64'),
                    ('SVE (Scalable Vectors)', data.get('sve', False), 'Variable-length SIMD, future optimization path'),
                    ('aarch64', data.get('aarch64', False), '64-bit ARM execution mode'),
                ]
                for feat, available, impact in features:
                    status = 'YES' if available else 'NO'
                    cls = 'feature-yes' if available else 'feature-no'
                    html += f'<tr><td>{feat}</td><td class="{cls}">{status}</td><td>{impact}</td></tr>'
                html += '</table>'

            elif result.get('test') == 'optimization_vs_simd_comparison':
                comp_data = result.get('data', [])
                if comp_data:
                    html += '<h3>Parse Throughput vs Compile Configuration</h3>'

                    items = [(d.get('configuration', 'unknown'), d.get('avg_throughput_mb_per_sec', 0), '#ff6b35')
                             for d in comp_data]
                    html += make_bar_chart('Throughput by Configuration (MB/s)', items)

                    html += '<table>'
                    html += '<tr><th>Configuration</th><th>Compile Flags</th><th>Throughput (MB/s)</th><th>Latency (ms)</th></tr>'
                    for d in comp_data:
                        html += f'<tr><td>{d.get("configuration", "N/A")}</td><td>{d.get("compile_flags", "N/A")}</td>'
                        html += f'<td>{d.get("avg_throughput_mb_per_sec", 0):.2f}</td>'
                        html += f'<td>{d.get("avg_latency_ms", 0):.2f}</td></tr>'
                    html += '</table>'

        html += '</div>'

    html += '''
<div class="section">
<h2>Benchmark Descriptions & References</h2>
<table>
<tr><th>Benchmark</th><th>Description</th><th>Reference</th></tr>
'''

    if primary:
        html += f'<tr><td>JSON Parse</td><td>{primary.get("description", "")}</td>'
        html += f'<td><a href="https://github.com/miloyip/nativejson-benchmark">nativejson-benchmark</a></td></tr>'
    if secondary:
        html += f'<tr><td>JSON Serialize</td><td>{secondary.get("description", "")}</td>'
        html += f'<td><a href="https://github.com/miloyip/nativejson-benchmark">nativejson-benchmark</a></td></tr>'
    if micro:
        html += f'<tr><td>Micro Ops</td><td>{micro.get("description", "")}</td>'
        html += f'<td><a href="https://github.com/bytedance/sonic-cpp">sonic-cpp SIMD</a></td></tr>'

    html += '</table></div></body></html>'

    os.makedirs(os.path.dirname(output_html) or '.', exist_ok=True)
    with open(output_html, 'w') as f:
        f.write(html)

    print(f'[HTML] Report saved to {output_html}')


if __name__ == '__main__':
    main()
