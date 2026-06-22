#!/usr/bin/env python3
import argparse
import json
import os
import time


def format_throughput(value):
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    else:
        return f"{value:.1f}"


def generate_svg_bar_chart(data_pairs, title, width=500, height=300, bar_color='#dc382d', label_color='#333'):
    max_val = max(v for _, v in data_pairs) if data_pairs else 1
    chart_height = height - 60
    chart_width = width - 80
    bar_width = max(15, chart_width // (len(data_pairs) + 1) - 5)
    svg_parts = []
    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="8"/>')
    svg_parts.append(f'<text x="{width//2}" y="25" font-size="14" font-weight="bold" text-anchor="middle" fill="{label_color}">{title}</text>')
    svg_parts.append(f'<line x1="60" y1="{height-30}" x2="{width-20}" y2="{height-30}" stroke="#ccc" stroke-width="1"/>')
    for i, (label, value) in enumerate(data_pairs):
        x = 60 + i * (chart_width // max(1, len(data_pairs))) + bar_width // 2
        bar_h = (value / max_val) * chart_height if max_val > 0 else 0
        y = height - 30 - bar_h
        svg_parts.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" fill="{bar_color}" rx="3"/>')
        svg_parts.append(f'<text x="{x + bar_width//2}" y="{height-18}" font-size="10" text-anchor="middle" fill="#666">{label}</text>')
        svg_parts.append(f'<text x="{x + bar_width//2}" y="{y-5}" font-size="9" text-anchor="middle" fill="#333">{format_throughput(value)}</text>')
    svg_parts.append('</svg>')
    return '\n'.join(svg_parts)


def generate_svg_line_chart(data_points, title, width=500, height=250, line_color='#dc382d'):
    if not data_points:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="50"><text x="250" y="30" font-size="12" text-anchor="middle" fill="#999">No data</text></svg>'
    max_val = max(v for _, v in data_points)
    min_val = min(v for _, v in data_points)
    chart_height = height - 60
    chart_width = width - 80
    svg_parts = []
    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="8"/>')
    svg_parts.append(f'<text x="{width//2}" y="25" font-size="14" font-weight="bold" text-anchor="middle" fill="#333">{title}</text>')
    svg_parts.append(f'<line x1="60" y1="{height-30}" x2="{width-20}" y2="{height-30}" stroke="#ccc" stroke-width="1"/>')
    svg_parts.append(f'<line x1="60" y1="40" x2="60" y2="{height-30}" stroke="#ccc" stroke-width="1"/>')
    val_range = max_val - min_val if max_val != min_val else 1
    path_points = []
    for i, (label, value) in enumerate(data_points):
        x = 60 + (i / max(1, len(data_points) - 1)) * chart_width if len(data_points) > 1 else 60 + chart_width // 2
        y = height - 30 - ((value - min_val) / val_range) * chart_height
        path_points.append(f'{x},{y}')
        svg_parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{line_color}"/>')
        svg_parts.append(f'<text x="{x}" y="{height-18}" font-size="9" text-anchor="middle" fill="#666">{label}</text>')
    if len(path_points) > 1:
        svg_parts.append(f'<polyline points="{" ".join(path_points)}" fill="none" stroke="{line_color}" stroke-width="2"/>')
    svg_parts.append('</svg>')
    return '\n'.join(svg_parts)


def main():
    parser = argparse.ArgumentParser(description='Generate HTML report from benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.html file')
    parser.add_argument('--software-version', default='8.0.2', help='Redis version')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("[HTML] No aggregated results found.")
        return

    with open(args.input, 'r') as f:
        all_data = json.load(f)

    env = all_data.get('environment', {})
    benchmarks = all_data.get('benchmarks', {})
    summary = all_data.get('summary', {})

    redis_ver = env.get('software_version', args.software_version)
    arch = env.get('architecture', 'ARM64')
    cpu = env.get('cpu_model', 'Unknown')
    cores = env.get('cpu_cores', 'N/A')
    mem = env.get('memory_mb', 'N/A')
    timestamp = env.get('timestamp', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))

    ycsb_data = benchmarks.get('ycsb', {})
    throughput_data = benchmarks.get('throughput', {})
    micro_data = benchmarks.get('micro', {})
    stress_data = benchmarks.get('stress', {})

    throughput_by_op_chart_data = []
    if throughput_data and 'summary' in throughput_data:
        for op, vals in throughput_data['summary'].items():
            if isinstance(vals, dict) and 'avg_throughput' in vals:
                throughput_by_op_chart_data.append((op, vals['avg_throughput']))

    concurrency_chart_data = []
    if stress_data and 'summary_by_concurrency' in stress_data:
        for c, vals in stress_data['summary_by_concurrency'].items():
            if isinstance(vals, dict) and 'avg_throughput' in vals:
                concurrency_chart_data.append((str(c), vals['avg_throughput']))

    micro_chart_data = []
    if micro_data and 'results' in micro_data:
        for r in micro_data['results']:
            if isinstance(r, dict) and 'operation' in r and 'avg_throughput' in r:
                micro_chart_data.append((r['operation'], r['avg_throughput']))

    latency_chart_data = []
    if micro_data and 'results' in micro_data:
        for r in micro_data['results']:
            if isinstance(r, dict) and 'operation' in r and 'p99_latency_ms' in r:
                latency_chart_data.append((r['operation'], r['p99_latency_ms']))

    throughput_chart_svg = generate_svg_bar_chart(throughput_by_op_chart_data, 'Redis Throughput by Operation (ops/sec)', width=700, height=350)
    micro_throughput_svg = generate_svg_bar_chart(micro_chart_data, 'Micro Benchmark Throughput (ops/sec)', width=700, height=350)
    latency_svg = generate_svg_bar_chart(latency_chart_data, 'Micro Benchmark P99 Latency (ms)', width=700, height=350, bar_color='#e74c3c')
    concurrency_svg = generate_svg_line_chart(concurrency_chart_data, 'Throughput vs Concurrency (ops/sec)', width=700, height=300)

    ycsb_rows_html = ''
    ycsb_results = ycsb_data.get('results', [])
    for r in ycsb_results:
        workload = r.get('workload', 'N/A')
        tp = r.get('overall_throughput', r.get('ops_per_sec', 0))
        iteration = r.get('iteration', 'N/A')
        read_ops = r.get('read_ops', 'N/A')
        write_ops = r.get('write_ops', 'N/A')
        elapsed = r.get('elapsed_sec', 'N/A')
        ycsb_rows_html += f'<tr><td>{iteration}</td><td>{workload}</td><td>{format_throughput(tp)}</td><td>{read_ops}</td><td>{write_ops}</td><td>{elapsed}s</td></tr>'

    throughput_rows_html = ''
    throughput_results = throughput_data.get('results', [])
    for r in throughput_results:
        op = r.get('operation', r.get('test_name', 'N/A'))
        clients = r.get('num_clients', 'N/A')
        tp = r.get('throughput', 0)
        lat = r.get('avg_latency_ms', 'N/A')
        iteration = r.get('iteration', 'N/A')
        throughput_rows_html += f'<tr><td>{iteration}</td><td>{op}</td><td>{clients}</td><td>{format_throughput(tp)}</td><td>{lat} ms</td></tr>'

    micro_rows_html = ''
    micro_results = micro_data.get('results', [])
    for r in micro_results:
        op = r.get('operation', 'N/A')
        tp = r.get('avg_throughput', 0)
        avg_lat = r.get('avg_latency_ms', 0)
        p50 = r.get('p50_latency_ms', 0)
        p99 = r.get('p99_latency_ms', 0)
        micro_rows_html += f'<tr><td>{op}</td><td>{format_throughput(tp)}</td><td>{avg_lat} ms</td><td>{p50} ms</td><td>{p99} ms</td></tr>'

    stress_rows_html = ''
    stress_results = stress_data.get('results', [])
    for r in stress_results:
        c = r.get('concurrency', 'N/A')
        tp = r.get('throughput', 0)
        lat = r.get('avg_latency_ms', 0)
        iteration = r.get('iteration', 'N/A')
        stress_rows_html += f'<tr><td>{iteration}</td><td>{c}</td><td>{format_throughput(tp)}</td><td>{lat} ms</td></tr>'

    max_tp_html = ''
    if 'max_throughput' in summary:
        mt = summary['max_throughput']
        max_tp_html = f'<div class="metric-card"><h3>Max Throughput</h3><p class="metric-value">{format_throughput(mt["value"])}</p><p class="metric-unit">ops/sec ({mt["name"]})</p></div>'
    avg_tp_html = ''
    if 'avg_throughput' in summary:
        avg_tp_html = f'<div class="metric-card"><h3>Avg Throughput</h3><p class="metric-value">{format_throughput(summary["avg_throughput"])}</p><p class="metric-unit">ops/sec</p></div>'
    max_lat_html = ''
    if 'max_latency' in summary:
        ml = summary['max_latency']
        max_lat_html = f'<div class="metric-card"><h3>Max Latency</h3><p class="metric-value">{ml["value"]:.3f}</p><p class="metric-unit">ms ({ml["name"]})</p></div>'
    avg_lat_html = ''
    if 'avg_latency' in summary:
        avg_lat_html = f'<div class="metric-card"><h3>Avg Latency</h3><p class="metric-value">{summary["avg_latency"]:.3f}</p><p class="metric-unit">ms</p></div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Redis {redis_ver} ARM64 Performance Benchmark Report</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; padding: 20px; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
.header {{ background: linear-gradient(135deg, #dc382d 0%, #a82e24 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 28px; margin-bottom: 5px; }}
.header .subtitle {{ font-size: 14px; opacity: 0.9; }}
.env-table {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
.env-table h2 {{ font-size: 18px; margin-bottom: 15px; color: #dc382d; }}
.env-table table {{ width: 100%; border-collapse: collapse; }}
.env-table td, .env-table th {{ padding: 8px 12px; border-bottom: 1px solid #eee; text-align: left; }}
.env-table th {{ background: #f8f8f8; font-weight: 600; width: 30%; }}
.metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
.metric-card {{ background: white; border-radius: 8px; padding: 20px; text-align: center; border: 1px solid #eee; }}
.metric-card h3 {{ font-size: 12px; color: #888; margin-bottom: 5px; text-transform: uppercase; }}
.metric-value {{ font-size: 28px; font-weight: bold; color: #dc382d; }}
.metric-unit {{ font-size: 11px; color: #999; }}
.section {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
.section h2 {{ font-size: 18px; margin-bottom: 10px; color: #dc382d; }}
.section h3 {{ font-size: 14px; color: #666; margin-bottom: 5px; }}
.chart-container {{ text-align: center; margin: 15px 0; overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
th {{ background: #f8f8f8; padding: 8px 10px; font-weight: 600; text-align: left; border-bottom: 2px solid #dc382d; }}
td {{ padding: 6px 10px; border-bottom: 1px solid #eee; }}
tr:hover td {{ background: #f8f0f0; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.badge-pass {{ background: #d4edda; color: #155724; }}
.badge-warn {{ background: #fff3cd; color: #856404; }}
.badge-fail {{ background: #f8d7da; color: #721c24; }}
.footer {{ text-align: center; padding: 15px; color: #888; font-size: 12px; }}
.ref {{ font-size: 12px; color: #888; margin-top: 5px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Redis {redis_ver} ARM64 Performance Benchmark</h1>
<div class="subtitle">Platform: {arch} | CPU: {cpu} | Cores: {cores} | Memory: {mem} MB | Date: {timestamp}</div>
</div>

<div class="env-table">
<h2>Environment Information</h2>
<table>
<tr><th>Architecture</th><td>{arch}</td></tr>
<tr><th>CPU Model</th><td>{cpu}</td></tr>
<tr><th>CPU Cores</th><td>{cores}</td></tr>
<tr><th>Memory</th><td>{mem} MB</td></tr>
<tr><th>Operating System</th><td>{env.get('os', 'N/A')}</td></tr>
<tr><th>Kernel</th><td>{env.get('kernel', 'N/A')}</td></tr>
<tr><th>Redis Version</th><td>{redis_ver}</td></tr>
<tr><th>Compiler</th><td>{env.get('compiler_version', 'N/A')}</td></tr>
<tr><th>Benchmark Tool</th><td>{env.get('benchmark_tool', 'redis-benchmark + custom YCSB')}</td></tr>
</table>
</div>

<div class="metrics-grid">
{max_tp_html}
{avg_tp_html}
{max_lat_html}
{avg_lat_html}
</div>

<div class="section">
<h2>3a: YCSB Benchmark Results</h2>
<p>Yahoo! Cloud Serving Benchmark - industry-standard KV store benchmark</p>
<div class="ref">Reference: https://github.com/brianfrankcooper/YCSB</div>
<table>
<tr><th>Iteration</th><th>Workload</th><th>Throughput</th><th>Read Ops</th><th>Write Ops</th><th>Elapsed</th></tr>
{ycsb_rows_html}
</table>
</div>

<div class="section">
<h2>3b: Throughput at Various Load Levels</h2>
<p>Redis throughput by operation type and client concurrency</p>
<div class="ref">Reference: redis-benchmark (built-in)</div>
<div class="chart-container">{throughput_chart_svg}</div>
<table>
<tr><th>Iteration</th><th>Operation</th><th>Clients</th><th>Throughput</th><th>Avg Latency</th></tr>
{throughput_rows_html}
</table>
</div>

<div class="section">
<h2>3c: Micro Benchmark Results</h2>
<p>Individual command performance on ARM64 - latency and throughput</p>
<div class="ref">Reference: redis-benchmark with custom latency analysis</div>
<div class="chart-container">{micro_throughput_svg}</div>
<div class="chart-container">{latency_svg}</div>
<table>
<tr><th>Operation</th><th>Throughput</th><th>Avg Latency</th><th>P50 Latency</th><th>P99 Latency</th></tr>
{micro_rows_html}
</table>
</div>

<div class="section">
<h2>3d: Concurrency Scaling Stress Test</h2>
<p>Throughput and latency as client concurrency increases from 1 to 200</p>
<div class="ref">Reference: redis-benchmark with varying client counts</div>
<div class="chart-container">{concurrency_svg}</div>
<table>
<tr><th>Iteration</th><th>Concurrency</th><th>Throughput</th><th>Avg Latency</th></tr>
{stress_rows_html}
</table>
</div>

<div class="footer">
<p>Redis ARM64 Performance Benchmark Report | Generated: {timestamp}</p>
<p>Benchmark Suite: redis-benchmark + YCSB | Platform: {arch}</p>
</div>
</div>
</body>
</html>"""

    with open(args.output, 'w') as f:
        f.write(html)
    print(f"[HTML] Report written to {args.output}")


if __name__ == '__main__':
    main()
