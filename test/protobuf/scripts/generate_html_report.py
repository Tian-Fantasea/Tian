#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #2c3e50, #e67e22); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #ecf0f1; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #2c3e50; border-bottom: 2px solid #e67e22; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #e67e22; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #f0f8ff; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #2c3e50; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.metric-card.pass .value { color: #4CAF50; }
.metric-card.fail .value { color: #f44336; }
.arm64-badge { background: #e67e22; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 180px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #2c3e50; margin-left: 8px; white-space: nowrap; }
.shunit2-section { background: #fff3e0; padding: 16px; border-radius: 6px; margin-top: 16px; }
.shunit2-section h2 { color: #e65100; }
</style>
"""


def make_bar_chart(title, items, max_val=None, color="#e67e22"):
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
            <div class="bar-value">{value:.2f}</div>
        </div>'''
    html += '</div>'
    return html


def main():
    parser = argparse.ArgumentParser(description='Generate HTML report for protobuf ARM64 benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.html file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print('[HTML] results.json not found')
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get('environment', {})
    ser = data.get('benchmarks', {}).get('serialization', {})
    lat = data.get('benchmarks', {}).get('latency', {})
    micro = data.get('benchmarks', {}).get('micro', {})
    conc = data.get('benchmarks', {}).get('concurrency', {})
    summary = data.get('summary', {})
    timestamp = data.get('timestamp', '')

    vi = env
    pb_ver = vi.get('protobuf_version', vi.get('software_version', 'N/A'))

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>protobuf ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>protobuf ARM64 Performance Benchmark Report <span class="arm64-badge">ARM64</span></h1>
    <div class="meta">protobuf v{pb_ver} | {vi.get("architecture", "N/A")} | Python {vi.get("runtime_version", "N/A")} | Generated {timestamp}</div>
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
<tr><td>protobuf Version</td><td>{pb_ver}</td></tr>
<tr><td>Python protobuf</td><td>{vi.get("python_protobuf_version", "N/A")}</td></tr>
<tr><td>protoc</td><td>{vi.get("protoc_version", "N/A")}</td></tr>
<tr><td>Install Method</td><td>{vi.get("install_method", "N/A")}</td></tr>
<tr><td>Category</td><td>{vi.get("category", "N/A")}</td></tr>
</table>
</div>
'''

    if summary:
        html += '<div class="metric-grid">'
        if 'avg_serialize_ops_small' in summary:
            html += f'''<div class="metric-card"><div class="label">Serialize (small)</div><div class="value">{summary["avg_serialize_ops_small"]}</div><div class="unit">msgs/sec</div></div>'''
        if 'avg_deserialize_ops_small' in summary:
            html += f'''<div class="metric-card"><div class="label">Deserialize (small)</div><div class="value">{summary["avg_deserialize_ops_small"]}</div><div class="unit">msgs/sec</div></div>'''
        if 'avg_serialize_bytes_small' in summary:
            html += f'''<div class="metric-card"><div class="label">Bytes/sec (small)</div><div class="value">{summary["avg_serialize_bytes_small"]}</div><div class="unit">bytes/sec</div></div>'''
        if 'max_avg_latency_ms' in summary:
            html += f'''<div class="metric-card"><div class="label">Max Avg Latency</div><div class="value">{summary["max_avg_latency_ms"]}</div><div class="unit">ms</div></div>'''
        if 'max_p99_latency_ms' in summary:
            html += f'''<div class="metric-card"><div class="label">Max P99 Latency</div><div class="value">{summary["max_p99_latency_ms"]}</div><div class="unit">ms</div></div>'''
        if 'avg_micro_serialize_ops' in summary:
            html += f'''<div class="metric-card"><div class="label">Avg Micro Serialize</div><div class="value">{summary["avg_micro_serialize_ops"]}</div><div class="unit">ops/sec</div></div>'''
        if 'avg_micro_deserialize_ops' in summary:
            html += f'''<div class="metric-card"><div class="label">Avg Micro Deserialize</div><div class="value">{summary["avg_micro_deserialize_ops"]}</div><div class="unit">ops/sec</div></div>'''
        if 'concurrency_scaling_ratio' in summary:
            html += f'''<div class="metric-card"><div class="label">MT Scaling</div><div class="value">{summary["concurrency_scaling_ratio"]}x</div><div class="unit">8t vs 1t</div></div>'''
        html += '</div>'

    if ser:
        results = ser.get('results', [])
        html += '<div class="section"><h2>Serialization Throughput (Phase 3a)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{ser.get("reference", "")}">{ser.get("reference", "N/A")}</a></p>'
        html += f'<p>Well-known type: <code>google.protobuf.Struct</code></p>'

        ser_items = [(r.get("message_type", "N/A"), r.get("serialize_ops_per_sec", 0)) for r in results]
        deser_items = [(r.get("message_type", "N/A"), r.get("deserialize_ops_per_sec", 0)) for r in results]
        if ser_items:
            html += make_bar_chart('Serialize Throughput (msgs/sec)', ser_items, color="#e67e22")
        if deser_items:
            html += make_bar_chart('Deserialize Throughput (msgs/sec)', deser_items, color="#3498db")

        html += '<table><tr><th>Message Type</th><th>Size (bytes)</th><th>Serialize (msgs/sec)</th><th>Serialize (bytes/sec)</th><th>Deserialize (msgs/sec)</th><th>Serialize Latency (ms)</th><th>Deserialize Latency (ms)</th></tr>'
        for r in results:
            html += f'<tr><td>{r.get("message_type", "N/A")}</td><td>{r.get("message_size_bytes", "N/A")}</td>'
            html += f'<td>{r.get("serialize_ops_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("serialize_bytes_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("deserialize_ops_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("serialize_avg_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("deserialize_avg_latency_ms", 0):.4f}</td></tr>'
        html += '</table></div>'

    if lat:
        results = lat.get('results', [])
        html += '<div class="section"><h2>Latency Distribution (Phase 3b)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{lat.get("reference", "")}">{lat.get("reference", "N/A")}</a></p>'

        avg_items = [(r.get("operation", "N/A"), r.get("avg_latency_ms", 0)) for r in results]
        p99_items = [(r.get("operation", "N/A"), r.get("p99_latency_ms", 0)) for r in results]
        if avg_items:
            html += make_bar_chart('Avg Latency (ms)', avg_items, color="#e67e22")
        if p99_items:
            html += make_bar_chart('P99 Latency (ms)', p99_items, color="#e74c3c")

        html += '<table><tr><th>Operation</th><th>Size (bytes)</th><th>Avg (ms)</th><th>P50 (ms)</th><th>P90 (ms)</th><th>P99 (ms)</th><th>Min (ms)</th><th>Max (ms)</th><th>StdDev (ms)</th></tr>'
        for r in results:
            html += f'<tr><td>{r.get("operation", "N/A")}</td><td>{r.get("message_size_bytes", "N/A")}</td>'
            html += f'<td>{r.get("avg_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("p50_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("p90_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("p99_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("min_latency_ms", 0):.6f}</td>'
            html += f'<td>{r.get("max_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("stddev_ms", 0):.4f}</td></tr>'
        html += '</table></div>'

    if micro:
        results = micro.get('results', [])
        html += '<div class="section"><h2>Micro Benchmarks (Phase 3c)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">{micro.get("reference", "N/A")}</a></p>'
        html += '<p>Per-field-type benchmark using well-known wrapper types</p>'

        ser_items = [(r.get("field_type", "N/A"), r.get("serialize_ops_per_sec", 0)) for r in results]
        deser_items = [(r.get("field_type", "N/A"), r.get("deserialize_ops_per_sec", 0)) for r in results]
        if ser_items:
            html += make_bar_chart('Serialize ops/sec per field type', ser_items, color="#e67e22")
        if deser_items:
            html += make_bar_chart('Deserialize ops/sec per field type', deser_items, color="#3498db")

        html += '<table><tr><th>Field Type</th><th>Size (bytes)</th><th>Serialize (ops/sec)</th><th>Deserialize (ops/sec)</th><th>Serialize Latency (ms)</th><th>Deserialize Latency (ms)</th></tr>'
        for r in results:
            html += f'<tr><td>{r.get("field_type", "N/A")}</td><td>{r.get("message_size_bytes", "N/A")}</td>'
            html += f'<td>{r.get("serialize_ops_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("deserialize_ops_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("serialize_avg_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("deserialize_avg_latency_ms", 0):.4f}</td></tr>'
        html += '</table></div>'

    if conc:
        results = conc.get('results', [])
        html += '<div class="section"><h2>Concurrency Scaling (Phase 3d)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{conc.get("reference", "")}">{conc.get("reference", "N/A")}</a></p>'

        ser_items = [(f'{r.get("mode", "N/A")} t={r.get("thread_count", "N/A")}', r.get("total_ops_per_sec", 0)) for r in results]
        if ser_items:
            html += make_bar_chart('Throughput by thread count (ops/sec)', ser_items, color="#27ae60")

        html += '<table><tr><th>Mode</th><th>Threads</th><th>Total ops/sec</th><th>Avg Latency (ms)</th><th>Wall Time (s)</th><th>Total Ops</th></tr>'
        for r in results:
            html += f'<tr><td>{r.get("mode", "N/A")}</td><td>{r.get("thread_count", "N/A")}</td>'
            html += f'<td>{r.get("total_ops_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("avg_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("wall_time_sec", 0):.4f}</td>'
            html += f'<td>{r.get("total_ops", "N/A")}</td></tr>'
        html += '</table></div>'

    html += f'''
<div class="section">
<h2>ARM64 Optimization Highlights</h2>
<table>
<tr><th>Feature</th><th>Impact</th><th>Status</th></tr>
<tr><td>protobuf C++ runtime</td><td>ARM64-native compiled library with optimized wire format encoding</td><td>v{pb_ver}</td></tr>
<tr><td>Python C extension</td><td>protobuf Python uses C extension for fast serialization on ARM64</td><td>{vi.get("python_protobuf_version", "N/A")}</td></tr>
<tr><td>protoc compiler</td><td>ARM64-native proto compiler for code generation</td><td>{vi.get("protoc_version", "N/A")}</td></tr>
<tr><td>Well-known types</td><td>Pre-compiled types always available without protoc</td><td>struct_pb2, wrappers_pb2, timestamp_pb2</td></tr>
<tr><td>Varint encoding</td><td>Efficient variable-length integer encoding for small values</td><td>Built-in</td></tr>
</table></div>

<div class="shunit2-section">
<h2>shUnit2 Test Results</h2>
<p>Validation tests via shUnit2. See <code>protobuf_test.sh</code> for test functions covering all phases.</p>
<table>
<tr><th>Phase</th><th>Test Functions</th><th>Count</th></tr>
<tr><td>Phase 2: Verify</td><td>testArchitectureIsARM64, testProtocIsInstalled, testProtobufPythonIsInstalled, testProtobufVersionMatches, testVersionInfoJsonExists</td><td>5</td></tr>
<tr><td>Phase 3a: Serialization</td><td>testBenchmarkSerializationProducesResults, testBenchmarkSerializationHasRequiredFields, testBenchmarkSerializationThroughputAboveThreshold, testBenchmarkSerializationBytesPerSecAboveThreshold</td><td>4</td></tr>
<tr><td>Phase 3b: Latency</td><td>testBenchmarkLatencyProducesResults, testBenchmarkLatencyAvgBelowThreshold, testBenchmarkLatencyP99BelowThreshold</td><td>3</td></tr>
<tr><td>Phase 3c: Micro</td><td>testBenchmarkMicroProducesResults, testBenchmarkMicroAllOperationsCompleted, testBenchmarkMicroSerializeOpsAboveThreshold, testBenchmarkMicroDeserializeOpsAboveThreshold</td><td>4</td></tr>
<tr><td>Phase 3d: Concurrency</td><td>testBenchmarkConcurrencyProducesResults, testBenchmarkConcurrencyScalingShowsProgression, testBenchmarkConcurrencyThroughputAboveThreshold</td><td>3</td></tr>
<tr><td>Phase 4: Results</td><td>testAggregatedResultsExist, testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated, testAggregatedResultsContainsAllBenchmarks</td><td>5</td></tr>
</table>
<p><strong>Total: 24 test* functions</strong></p>
</div>
</body></html>'''

    with open(args.output, 'w') as f:
        f.write(html)
    print(f'[HTML] Report saved to {args.output}')


if __name__ == '__main__':
    main()
