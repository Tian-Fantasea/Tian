#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #1a1a2e, #00d4ff); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #b0e0e6; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #1a1a2e; border-bottom: 2px solid #00d4ff; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #2c3e50; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #1a1a2e; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #e8f4f8; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #1a1a2e; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.metric-card.pass .value { color: #4CAF50; }
.metric-card.fail .value { color: #f44336; }
.arm64-badge { background: #00d4ff; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 180px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #1a1a2e; margin-left: 8px; white-space: nowrap; }
.shunit2-section { background: #e8f5e9; padding: 16px; border-radius: 6px; margin-top: 16px; }
.shunit2-section h2 { color: #2e7d32; }
</style>
"""


def make_bar_chart(title, items, max_val=None, color="#00d4ff"):
    if max_val is None:
        max_val = max(v for _, v in items) if items else 1
    if max_val == 0:
        max_val = 1
    html = f'<h3>{title}</h3><div class="bar-chart">'
    for label, value in items:
        pct = (value / max_val * 100) if max_val > 0 else 0
        html += f'''<div class="bar-row">
            <div class="bar-label">{label}</div>
            <div class="bar-container"><div class="bar-fill" style="width:{pct:.1f}%;background:{color}"></div></div>
            <div class="bar-value">{value:.1f}</div>
        </div>'''
    html += '</div>'
    return html


def main():
    parser = argparse.ArgumentParser(description='Generate HTML report for bbolt ARM64 benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.html file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print('[HTML] results.json not found')
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get('environment', {})
    ycsb = data.get('benchmarks', {}).get('ycsb', {})
    throughput = data.get('benchmarks', {}).get('throughput', {})
    micro = data.get('benchmarks', {}).get('micro', {})
    concurrency = data.get('benchmarks', {}).get('concurrency', {})
    summary = data.get('summary', {})
    timestamp = data.get('timestamp', '')

    vi = env
    bbolt_ver = vi.get('bbolt_version', vi.get('software_version', 'N/A'))
    go_ver = vi.get('go_version', vi.get('runtime_version', 'N/A'))

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>bbolt ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>bbolt ARM64 Performance Benchmark Report <span class="arm64-badge">ARM64</span></h1>
    <div class="meta">bbolt v{bbolt_ver} | {vi.get("architecture", "N/A")} | {go_ver} | Generated {timestamp}</div>
</div>

<div class="section">
<h2>Environment Information</h2>
<table>
<tr><th>Property</th><th>Value</th></tr>
<tr><td>Architecture</td><td>{vi.get("architecture", "N/A")}</td></tr>
<tr><td>OS</td><td>{vi.get("os", "N/A")}</td></tr>
<tr><td>Kernel</td><td>{vi.get("kernel", "N/A")}</td></tr>
<tr><td>CPU</td><td>{vi.get("cpu_model", "N/A")} ({vi.get("cores", "N/A")} cores)</td></tr>
<tr><td>Memory</td><td>{vi.get("memory_mb", "N/A")} MB</td></tr>
<tr><td>bbolt Version</td><td>{bbolt_ver}</td></tr>
<tr><td>Go Version</td><td>{go_ver}</td></tr>
<tr><td>Install Method</td><td>{vi.get("install_method", "N/A")}</td></tr>
</table>
</div>
'''

    if summary:
        html += '<div class="metric-grid">'
        if 'avg_ycsb_ops_per_sec' in summary:
            html += f'''<div class="metric-card"><div class="label">YCSB Avg Ops</div><div class="value">{summary["avg_ycsb_ops_per_sec"]}</div><div class="unit">ops/sec</div></div>'''
        if 'avg_ycsb_latency_ms' in summary:
            html += f'''<div class="metric-card"><div class="label">YCSB Avg Latency</div><div class="value">{summary["avg_ycsb_latency_ms"]}</div><div class="unit">ms</div></div>'''
        if 'avg_throughput_write_ops' in summary:
            html += f'''<div class="metric-card"><div class="label">Throughput Write</div><div class="value">{summary["avg_throughput_write_ops"]}</div><div class="unit">ops/sec</div></div>'''
        if 'avg_micro_ops_per_sec' in summary:
            html += f'''<div class="metric-card"><div class="label">Micro Avg Ops</div><div class="value">{summary["avg_micro_ops_per_sec"]}</div><div class="unit">ops/sec</div></div>'''
        if 'avg_concurrency_ops_per_sec' in summary:
            html += f'''<div class="metric-card"><div class="label">Concurrency Avg</div><div class="value">{summary["avg_concurrency_ops_per_sec"]}</div><div class="unit">ops/sec</div></div>'''
        html += '</div>'

    if ycsb:
        results = ycsb.get('results', [])
        html += '<div class="section"><h2>YCSB Benchmark (Phase 3a)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{ycsb.get("reference", "")}">{ycsb.get("reference", "N/A")}</a></p>'

        ops_items = []
        lat_items = []
        for r in results:
            if isinstance(r, dict):
                wl = r.get('workload', 'N/A')
                ops = r.get('ops_per_sec', r.get('OpsPerSec', 0))
                lat = r.get('avg_latency_ms', r.get('AvgLatencyMs', 0))
                ops_items.append((wl, ops))
                lat_items.append((wl, lat))
        if ops_items:
            html += make_bar_chart('YCSB Throughput (ops/sec)', ops_items, color="#00d4ff")
        if lat_items:
            html += make_bar_chart('YCSB Avg Latency (ms)', lat_items, color="#e67e22")

        html += '<table><tr><th>Workload</th><th>Read Ratio</th><th>Ops/sec</th><th>Avg Latency (ms)</th><th>P50 (ms)</th><th>P99 (ms)</th><th>Duration (s)</th></tr>'
        for r in results:
            if isinstance(r, dict):
                html += f'<tr><td>{r.get("workload", "N/A")}</td><td>{r.get("read_ratio", "N/A")}</td>'
                html += f'<td>{r.get("ops_per_sec", r.get("OpsPerSec", 0)):.1f}</td>'
                html += f'<td>{r.get("avg_latency_ms", r.get("AvgLatencyMs", 0)):.2f}</td>'
                html += f'<td>{r.get("p50_latency_ms", 0):.2f}</td>'
                html += f'<td>{r.get("p99_latency_ms", 0):.2f}</td>'
                html += f'<td>{r.get("duration_sec", 0):.2f}</td></tr>'
        html += '</table></div>'

    if throughput:
        results = throughput.get('results', [])
        html += '<div class="section"><h2>Throughput Scaling (Phase 3b)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{throughput.get("reference", "")}">{throughput.get("reference", "N/A")}</a></p>'

        write_items = []
        for r in results:
            if isinstance(r, dict):
                kc = r.get('key_count', 'N/A')
                w_ops = r.get('write_ops_per_sec', r.get('WriteOpsSec', 0))
                write_items.append((f"keys={kc}", w_ops))
        if write_items:
            html += make_bar_chart('Write Throughput (ops/sec)', write_items, color="#27ae60")

        html += '<table><tr><th>Key Count</th><th>Write ops/sec</th><th>Read ops/sec</th><th>Scan ops/sec</th><th>Avg Latency (ms)</th></tr>'
        for r in results:
            if isinstance(r, dict):
                html += f'<tr><td>{r.get("key_count", "N/A")}</td>'
                html += f'<td>{r.get("write_ops_per_sec", r.get("WriteOpsSec", 0)):.1f}</td>'
                html += f'<td>{r.get("read_ops_per_sec", r.get("ReadOpsSec", 0)):.1f}</td>'
                html += f'<td>{r.get("scan_ops_per_sec", r.get("ScanOpsSec", 0)):.1f}</td>'
                html += f'<td>{r.get("avg_latency_ms", r.get("AvgLatencyMs", 0)):.2f}</td></tr>'
        html += '</table></div>'

    if micro:
        results = micro.get('results', [])
        html += '<div class="section"><h2>Micro Benchmarks (Phase 3c)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">{micro.get("reference", "N/A")}</a></p>'

        op_items = []
        for r in results:
            if isinstance(r, dict):
                op = r.get('operation', 'N/A')
                ops = r.get('ops_per_sec', r.get('OpsPerSec', 0))
                op_items.append((op, ops))
        if op_items:
            html += make_bar_chart('Micro Ops/sec by Operation', op_items, color="#3498db")

        html += '<table><tr><th>Operation</th><th>Ops/sec</th><th>Avg Latency (ms)</th><th>Total Ops</th><th>Duration (s)</th></tr>'
        for r in results:
            if isinstance(r, dict):
                html += f'<tr><td>{r.get("operation", "N/A")}</td>'
                html += f'<td>{r.get("ops_per_sec", r.get("OpsPerSec", 0)):.1f}</td>'
                html += f'<td>{r.get("avg_latency_ms", r.get("AvgLatencyMs", 0)):.2f}</td>'
                html += f'<td>{r.get("total_ops", 0)}</td>'
                html += f'<td>{r.get("duration_sec", 0):.2f}</td></tr>'
        html += '</table></div>'

    if concurrency:
        results = concurrency.get('results', [])
        html += '<div class="section"><h2>Concurrency Scaling (Phase 3d)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{concurrency.get("reference", "")}">{concurrency.get("reference", "N/A")}</a></p>'

        batch_items = []
        read_items = []
        for r in results:
            if isinstance(r, dict):
                gr = r.get('goroutines', 'N/A')
                mode = r.get('mode', 'N/A')
                ops = r.get('ops_per_sec', r.get('OpsPerSec', 0))
                label = f"{mode} g={gr}"
                if mode == 'batch_write':
                    batch_items.append((label, ops))
                elif mode == 'concurrent_read':
                    read_items.append((label, ops))
        if batch_items:
            html += make_bar_chart('Batch Write by Goroutines (ops/sec)', batch_items, color="#e67e22")
        if read_items:
            html += make_bar_chart('Concurrent Read by Goroutines (ops/sec)', read_items, color="#00d4ff")

        html += '<table><tr><th>Goroutines</th><th>Mode</th><th>Ops/sec</th><th>Avg Latency (ms)</th><th>Total Ops</th><th>Duration (s)</th></tr>'
        for r in results:
            if isinstance(r, dict):
                html += f'<tr><td>{r.get("goroutines", "N/A")}</td><td>{r.get("mode", "N/A")}</td>'
                html += f'<td>{r.get("ops_per_sec", r.get("OpsPerSec", 0)):.1f}</td>'
                html += f'<td>{r.get("avg_latency_ms", r.get("AvgLatencyMs", 0)):.2f}</td>'
                html += f'<td>{r.get("total_ops", 0)}</td>'
                html += f'<td>{r.get("duration_sec", 0):.2f}</td></tr>'
        html += '</table></div>'

    html += f'''
<div class="section">
<h2>ARM64 Optimization Highlights</h2>
<table>
<tr><th>Feature</th><th>Impact</th><th>Status</th></tr>
<tr><td>Go ARM64 native</td><td>Go compiler generates ARM64 machine code</td><td>{go_ver}</td></tr>
<tr><td>bbolt v{bbolt_ver}</td><td>Embedded KV store with B+tree</td><td>Go module</td></tr>
<tr><td>mmap I/O</td><td>Memory-mapped file access for zero-copy reads</td><td>bbolt internal</td></tr>
<tr><td>Goroutine scheduling</td><td>Concurrent read access via goroutines</td><td>Go runtime</td></tr>
</table></div>

<div class="shunit2-section">
<h2>shUnit2 Test Results</h2>
<p>Validation tests via shUnit2. See <code>bolt_test.sh</code> for test functions covering all phases.</p>
<table>
<tr><th>Phase</th><th>Test Functions</th><th>Count</th></tr>
<tr><td>Phase 2: Verify</td><td>testArchitectureIsARM64, testGoIsInstalled, testGoVersionSufficient, testSoftwareIsInstalled, testVersionInfoJsonExists</td><td>5</td></tr>
<tr><td>Phase 3a: YCSB</td><td>testBenchmarkYcsbProducesResults, testBenchmarkYcsbHasRequiredFields, testBenchmarkYcsbThroughputAboveThreshold, testBenchmarkYcsbLatencyBelowThreshold</td><td>4</td></tr>
<tr><td>Phase 3b: Throughput</td><td>testBenchmarkThroughputProducesResults, testBenchmarkThroughputScalingShowsProgression, testBenchmarkThroughputOpsPerSecAboveThreshold</td><td>3</td></tr>
<tr><td>Phase 3c: Micro</td><td>testBenchmarkMicroProducesResults, testBenchmarkMicroAllOperationsCompleted, testBenchmarkMicroContainsOperations</td><td>3</td></tr>
<tr><td>Phase 3d: Concurrency</td><td>testBenchmarkConcurrencyProducesResults, testBenchmarkConcurrencyScalingShowsProgression</td><td>2</td></tr>
<tr><td>Phase 4: Results</td><td>testAggregatedResultsExist, testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated, testAggregatedResultsContainsAllBenchmarks</td><td>5</td></tr>
</table>
<p><strong>Total: 23 test* functions</strong></p>
</div>
</body></html>'''

    with open(args.output, 'w') as f:
        f.write(html)
    print(f'[HTML] Report saved to {args.output}')


if __name__ == '__main__':
    main()
