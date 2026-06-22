#!/usr/bin/env python3
import json
import os
import sys
import datetime


CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #2d4a20, #497537); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #71b443; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #497537; border-bottom: 2px solid #71b443; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #497537; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #f0f8ff; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #497537; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 180px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #497537; margin-left: 8px; white-space: nowrap; }
.phase-tag { display: inline-block; background: #e8f5e9; color: #497537; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px; }
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
    http = all_data.get('primary_benchmark', {})
    tcp = all_data.get('secondary_benchmark', {})
    micro = all_data.get('micro_benchmark', {})
    timestamp = all_data.get('aggregation_timestamp', '')

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Envoy ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>Envoy ARM64 Performance Benchmark Report</h1>
    <div class="meta">Envoy {vi.get('envoy_version', 'N/A')} | {vi.get('architecture', 'N/A')} | Generated {timestamp}</div>
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
<tr><td>Envoy Version</td><td>{vi.get('envoy_version', 'N/A')}</td></tr>
<tr><td>Python</td><td>{vi.get('python_version', 'N/A')}</td></tr>
<tr><td>wrk</td><td>{vi.get('wrk_version', 'N/A')}</td></tr>
<tr><td>Worker Threads</td><td>{vi.get('worker_threads', 'N/A')}</td></tr>
</table>
</div>
'''

    if http:
        html += '<div class="section"><h2>HTTP/L7 Proxy Benchmark</h2>'
        html += '<p><span class="phase-tag">Phase 3a: RPS vs Concurrency</span> <span class="phase-tag">Response Sizes</span></p>'
        rps_items = []
        for result in http.get('results', []):
            if result.get('test') == 'rps_vs_concurrency':
                for d in result.get('data', []):
                    rps_items.append((f"c={d.get('concurrency', 0)}", d.get('avg_rps', 0), '#71b443'))
        if rps_items:
            html += make_bar_chart('HTTP RPS vs Concurrency', rps_items)

        latency_items = []
        for result in http.get('results', []):
            if result.get('test') == 'rps_vs_concurrency':
                for d in result.get('data', []):
                    latency_items.append((f"c={d.get('concurrency', 0)}", d.get('avg_latency_p99_ms', 0), '#ef4444'))
        if latency_items:
            html += make_bar_chart('HTTP P99 Latency (ms) vs Concurrency', latency_items)

        html += '<h3>Detailed HTTP Results</h3><table>'
        html += '<tr><th>Concurrency</th><th>RPS</th><th>P50 (ms)</th><th>P99 (ms)</th></tr>'
        for result in http.get('results', []):
            if result.get('test') == 'rps_vs_concurrency':
                for d in result.get('data', []):
                    html += f'<tr><td>{d.get("concurrency", "N/A")}</td><td>{d.get("avg_rps", 0):.0f}</td>'
                    html += f'<td>{d.get("avg_latency_p50_ms", 0):.2f}</td><td>{d.get("avg_latency_p99_ms", 0):.2f}</td></tr>'
        html += '</table></div>'

    if tcp:
        html += '<div class="section"><h2>TCP/L4 Proxy + Latency Benchmark</h2>'
        html += '<p><span class="phase-tag">Phase 3b: TCP Throughput</span> <span class="phase-tag">Latency Percentiles</span></p>'
        tcp_rps_items = []
        for result in tcp.get('results', []):
            if result.get('test') == 'tcp_throughput_vs_concurrency':
                for d in result.get('data', []):
                    tcp_rps_items.append((f"c={d.get('concurrency', 0)}", d.get('avg_rps', 0), '#3b82f6'))
        if tcp_rps_items:
            html += make_bar_chart('TCP RPS vs Concurrency', tcp_rps_items)

        html += '<h3>Detailed TCP Results</h3><table>'
        html += '<tr><th>Concurrency</th><th>RPS</th><th>P99 (ms)</th></tr>'
        for result in tcp.get('results', []):
            if result.get('test') == 'tcp_throughput_vs_concurrency':
                for d in result.get('data', []):
                    html += f'<tr><td>{d.get("concurrency", "N/A")}</td><td>{d.get("avg_rps", 0):.0f}</td>'
                    html += f'<td>{d.get("avg_latency_p99_ms", 0):.2f}</td></tr>'
        html += '</table></div>'

    if micro:
        html += '<div class="section"><h2>Micro Benchmarks</h2>'
        html += '<p><span class="phase-tag">Phase 3c: ARM64 Crypto</span> <span class="phase-tag">Memory</span></p>'
        arm64_table = '<h3>ARM64 Crypto Extensions</h3><table><tr><th>Feature</th><th>Available</th><th>Envoy Benefit</th></tr>'
        for result in micro.get('results', []):
            if result.get('test') == 'arm64_crypto_detection':
                data = result.get('data', {})
                features = [
                    ("AES", data.get('aes', False), "TLS AES-GCM acceleration (~3x faster)"),
                    ("SHA1/SHA256", data.get('sha1', False) or data.get('sha2', False), "TLS handshake hash (~2x faster)"),
                    ("PMULL", data.get('pmull', False), "RSA modular multiplication for TLS"),
                    ("NEON/ASIMD", data.get('neon', False), "SIMD data processing"),
                ]
                for feat, available, benefit in features:
                    status = "YES" if available else "NO"
                    color = "#10b981" if available else "#ef4444"
                    arm64_table += f'<tr><td>{feat}</td><td style="color:{color};font-weight:bold">{status}</td><td>{benefit}</td></tr>'
        arm64_table += '</table>'
        html += arm64_table

        html += '<h3>Memory Footprint</h3><table><tr><th>Metric</th><th>Value</th></tr>'
        for result in micro.get('results', []):
            if result.get('test') == 'memory_footprint':
                data = result.get('data', {})
                html += f'<tr><td>Initial Memory</td><td>{data.get("initial_memory_mb", 0):.1f} MB</td></tr>'
                html += f'<tr><td>Peak Memory</td><td>{data.get("peak_memory_mb", 0):.1f} MB</td></tr>'
        html += '</table></div>'

    html += '''
<div class="section">
<h2>Benchmark Descriptions & References</h2>
<table>
<tr><th>Benchmark</th><th>Description</th><th>Reference</th></tr>
'''

    if http:
        html += f'<tr><td>HTTP/L7 Proxy</td><td>{http.get("description", "")}</td><td><a href="https://github.com/giltene/wrk2">wrk2</a></td></tr>'
    if tcp:
        html += f'<tr><td>TCP/L4 Proxy</td><td>{tcp.get("description", "")}</td><td><a href="https://github.com/giltene/wrk2">wrk2</a></td></tr>'
    if micro:
        html += f'<tr><td>Micro Ops</td><td>{micro.get("description", "")}</td><td><a href="https://www.envoyproxy.io">Envoy docs</a></td></tr>'

    html += '</table></div></body></html>'

    os.makedirs(os.path.dirname(output_html) or '.', exist_ok=True)
    with open(output_html, 'w') as f:
        f.write(html)

    print(f'[HTML] Report saved to {output_html}')


if __name__ == '__main__':
    main()
