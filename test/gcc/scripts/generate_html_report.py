#!/usr/bin/env python3
import json
import os
import sys
import datetime


CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #1a3a5c, #2d5a8c); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #7ab3d4; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #2d5a8c; border-bottom: 2px solid #7ab3d4; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #2d5a8c; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #f0f8ff; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #2d5a8c; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 180px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #2d5a8c; margin-left: 8px; white-space: nowrap; }
.phase-tag { display: inline-block; background: #e8f4f8; color: #2d5a8c; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px; }
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

    gcc_ver = vi.get('runtime_version', 'N/A')
    gcc_target = vi.get('home', 'N/A')

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GCC ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>GCC ARM64 Performance Benchmark Report</h1>
    <div class="meta">GCC {gcc_ver} | {vi.get('architecture', 'N/A')} | Target: {gcc_target} | Generated {timestamp}</div>
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
<tr><td>GCC Version</td><td>{gcc_ver}</td></tr>
<tr><td>GCC Target</td><td>{gcc_target}</td></tr>
<tr><td>GCC Dumpversion</td><td>{vi.get('runtime_detail', 'N/A')}</td></tr>
<tr><td>Parallelism</td><td>{vi.get('parallelism', 'N/A')}</td></tr>
'''

    extra = vi.get('extra_info', {})
    if extra:
        html += f'<tr><td>g++ Available</td><td>{extra.get("gpp_available", "N/A")}</td></tr>'
        html += f'<tr><td>g++ Version</td><td>{extra.get("gpp_version", "N/A")}</td></tr>'
        html += f'<tr><td>Opt Levels</td><td>{extra.get("opt_levels", "N/A")}</td></tr>'
        html += f'<tr><td>Benchmark Programs</td><td>{extra.get("benchmark_programs", "N/A")}</td></tr>'

    html += '</table></div>'

    if primary:
        html += '<div class="section"><h2>Compile Speed Benchmark</h2>'
        html += '<p><span class="phase-tag">Phase 3a: Throughput vs Optimization</span> <span class="phase-tag">C vs C++ Comparison</span></p>'

        throughput_items = []
        for result in primary.get('results', []):
            if result.get('test') == 'compile_throughput_vs_optimization':
                for d in result.get('data', []):
                    opt = d.get('optimization_level', 'O0')
                    tp = d.get('avg_throughput_files_per_sec', 0)
                    throughput_items.append((f'-{opt}', tp, '#7ab3d4'))

        if throughput_items:
            html += make_bar_chart('Compile Throughput (files/sec) vs Optimization Level', throughput_items)

        html += '<h3>Detailed Compile Speed Results</h3><table>'
        html += '<tr><th>Opt Level</th><th>Throughput (files/sec)</th><th>Compile Time (sec)</th><th>Source Types</th></tr>'
        for result in primary.get('results', []):
            if result.get('test') == 'compile_throughput_vs_optimization':
                for d in result.get('data', []):
                    meas = d.get('measurements', [])
                    types = ', '.join(m.get('source_type', '') for m in meas)
                    html += f'<tr><td>-{d.get("optimization_level", "N/A")}</td>'
                    html += f'<td>{d.get("avg_throughput_files_per_sec", 0):.2f}</td>'
                    html += f'<td>{d.get("avg_compile_time_sec", 0):.4f}</td>'
                    html += f'<td>{types}</td></tr>'
        html += '</table>'

        for result in primary.get('results', []):
            if result.get('test') == 'c_vs_cpp_compile_time':
                html += '<h3>C vs C++ Compile Time at -O2</h3><table>'
                html += '<tr><th>Language</th><th>Compile Time (sec)</th><th>Throughput (files/sec)</th><th>Source Count</th></tr>'
                for d in result.get('data', []):
                    if 'language' in d:
                        html += f'<tr><td>{d["language"]}</td><td>{d.get("avg_compile_time_sec", 0):.4f}</td>'
                        html += f'<td>{d.get("avg_throughput_files_per_sec", 0):.2f}</td><td>{d.get("source_count", "N/A")}</td></tr>'
                    elif 'cpp_vs_c_ratio' in d:
                        html += f'<tr><td colspan="4"><strong>C++/C ratio: {d["cpp_vs_c_ratio"]} '
                        html += f'({d.get("note", "")})</strong></td></tr>'
                html += '</table>'

        html += '</div>'

    if secondary:
        html += '<div class="section"><h2>Generated Code Performance</h2>'
        html += '<p><span class="phase-tag">Phase 3b: Execution Throughput</span> <span class="phase-tag">Optimization Speedup</span></p>'

        bench_names = {}
        for result in secondary.get('results', []):
            if result.get('test') == 'execution_throughput_vs_optimization':
                for d in result.get('data', []):
                    name = d.get('benchmark', 'unknown')
                    if name not in bench_names:
                        bench_names[name] = []
                    bench_names[name].append(d)

        for bench_name, entries in bench_names.items():
            items = [(f'-{e.get("optimization", "O0")}', e.get('avg_throughput_ops_per_sec', 0), '#3b82f6')
                     for e in entries]
            html += make_bar_chart(f'{bench_name} Throughput (ops/sec)', items)

        html += '<h3>Detailed Execution Results</h3><table>'
        html += '<tr><th>Program</th><th>Optimization</th><th>Time (ms)</th><th>Throughput (ops/sec)</th></tr>'
        for result in secondary.get('results', []):
            if result.get('test') == 'execution_throughput_vs_optimization':
                for d in result.get('data', []):
                    html += f'<tr><td>{d.get("benchmark", "N/A")}</td><td>-{d.get("optimization", "N/A")}</td>'
                    html += f'<td>{d.get("avg_time_ms", 0):.2f}</td><td>{d.get("avg_throughput_ops_per_sec", 0):.2f}</td></tr>'
        html += '</table>'

        for result in secondary.get('results', []):
            if result.get('test') == 'optimization_speedup':
                html += '<h3>Optimization Speedup vs -O0 Baseline</h3><table>'
                html += '<tr><th>Benchmark</th><th>Speedup Metric</th><th>Value</th></tr>'
                for d in result.get('data', []):
                    bench = d.get('benchmark', 'N/A')
                    for key, val in d.items():
                        if key != 'benchmark' and isinstance(val, (int, float)):
                            html += f'<tr><td>{bench}</td><td>{key}</td><td>{val}</td></tr>'
                html += '</table>'

        html += '</div>'

    if micro:
        html += '<div class="section"><h2>Micro Benchmarks</h2>'
        html += '<p><span class="phase-tag">Phase 3c: Compiler Components</span> <span class="phase-tag">ARM64 Features</span></p>'

        for result in micro.get('results', []):
            if result.get('test') == 'compiler_component_speed':
                html += '<h3>Compiler Component Speed</h3><table>'
                html += '<tr><th>Component</th><th>Time (ms)</th><th>Throughput (files/sec)</th></tr>'
                for d in result.get('data', []):
                    html += f'<tr><td>{d.get("component", "N/A")}</td>'
                    html += f'<td>{d.get("avg_time_ms", 0):.2f}</td>'
                    html += f'<td>{d.get("avg_throughput_files_per_sec", 0):.2f}</td></tr>'
                html += '</table>'

            elif result.get('test') == 'arm64_optimization_detection':
                data = result.get('data', {})
                html += '<h3>ARM64 Optimization Feature Detection</h3><table>'
                html += '<tr><th>Feature</th><th>Available</th><th>Impact on GCC Code Generation</th></tr>'
                features = [
                    ('NEON (SIMD)', data.get('neon', False), 'Auto-vectorization for loops, ~3x for parallel ops'),
                    ('SVE (Scalable Vectors)', data.get('sve', False), 'Variable-length vectorization, future-proof'),
                    ('LSE Atomics', data.get('lse_atomics', False), 'Faster atomic ops, critical for multi-threaded code'),
                    ('CRC32 Instructions', data.get('crc32', False), 'Hardware CRC, ~10x faster checksum'),
                    ('Auto-vectorization O3', data.get('auto_vectorization_O3', False), 'GCC -O3 loop vectorization'),
                ]
                for feat, available, impact in features:
                    status = 'YES' if available else 'NO'
                    cls = 'feature-yes' if available else 'feature-no'
                    html += f'<tr><td>{feat}</td><td class="{cls}">{status}</td><td>{impact}</td></tr>'
                html += '</table>'

        html += '</div>'

    html += '''
<div class="section">
<h2>Benchmark Descriptions & References</h2>
<table>
<tr><th>Benchmark</th><th>Description</th><th>Reference</th></tr>
'''

    if primary:
        html += f'<tr><td>Compile Speed</td><td>{primary.get("description", "")}</td>'
        html += f'<td><a href="https://www.csibe.org">CSiBE</a></td></tr>'
    if secondary:
        html += f'<tr><td>Generated Code</td><td>{secondary.get("description", "")}</td>'
        html += f'<td><a href="https://www.spec.org/cpu2017/">SPEC CPU 2017</a></td></tr>'
    if micro:
        html += f'<tr><td>Micro Ops</td><td>{micro.get("description", "")}</td>'
        html += f'<td><a href="https://gcc.gnu.org/onlinedocs/gccint/">GCC Internals</a></td></tr>'

    html += '</table></div></body></html>'

    os.makedirs(os.path.dirname(output_html) or '.', exist_ok=True)
    with open(output_html, 'w') as f:
        f.write(html)

    print(f'[HTML] Report saved to {output_html}')


if __name__ == '__main__':
    main()
