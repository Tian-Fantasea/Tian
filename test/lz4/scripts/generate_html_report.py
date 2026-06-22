#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #1a5276, #2e86c1); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #d4e6f1; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #1a5276; border-bottom: 2px solid #2e86c1; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #2c3e50; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #2e86c1; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #e8f4f8; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #1a5276; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.metric-card.pass .value { color: #4CAF50; }
.metric-card.fail .value { color: #f44336; }
.arm64-badge { background: #2e86c1; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 180px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #1a5276; margin-left: 8px; white-space: nowrap; }
.shunit2-section { background: #e3f2fd; padding: 16px; border-radius: 6px; margin-top: 16px; }
.shunit2-section h2 { color: #1565c0; }
</style>
"""


def make_bar_chart(title, items, max_val=None, color="#2e86c1"):
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
    parser = argparse.ArgumentParser(description='Generate HTML report for lz4 ARM64 benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.html file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print('[HTML] results.json not found')
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get('environment', {})
    comp = data.get('benchmarks', {}).get('compression', {})
    decomp = data.get('benchmarks', {}).get('decompression', {})
    micro = data.get('benchmarks', {}).get('micro', {})
    conc = data.get('benchmarks', {}).get('concurrency', {})
    summary = data.get('summary', {})
    timestamp = data.get('timestamp', '')

    vi = env
    lz4_ver = vi.get('lz4_version', vi.get('software_version', 'N/A'))

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>lz4 ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>lz4 ARM64 Performance Benchmark Report <span class="arm64-badge">ARM64</span></h1>
    <div class="meta">lz4 v{lz4_ver} | {vi.get("architecture", "N/A")} | Python lz4 {vi.get("lz4_py_version", "N/A")} | Generated {timestamp}</div>
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
<tr><td>lz4 Version</td><td>{lz4_ver}</td></tr>
<tr><td>Python lz4</td><td>{vi.get("lz4_py_version", "N/A")}</td></tr>
<tr><td>lz4 CLI</td><td>{vi.get("lz4_cli_version", "N/A")}</td></tr>
<tr><td>Install Method</td><td>{vi.get("install_method", "N/A")}</td></tr>
<tr><td>Category</td><td>{vi.get("category", "N/A")}</td></tr>
<tr><td>Language</td><td>{vi.get("language", "N/A")}</td></tr>
</table>
</div>
'''

    if summary:
        html += '<div class="metric-grid">'
        if 'avg_compression_throughput_mb' in summary:
            html += f'''<div class="metric-card"><div class="label">Compression Avg</div><div class="value">{summary["avg_compression_throughput_mb"]}</div><div class="unit">MB/s</div></div>'''
        if 'avg_compression_ratio' in summary:
            html += f'''<div class="metric-card"><div class="label">Compression Ratio</div><div class="value">{summary["avg_compression_ratio"]}x</div><div class="unit">ratio</div></div>'''
        if 'avg_decompression_throughput_mb' in summary:
            html += f'''<div class="metric-card"><div class="label">Decompression Avg</div><div class="value">{summary["avg_decompression_throughput_mb"]}</div><div class="unit">MB/s</div></div>'''
        if 'decompress_vs_compress_ratio' in summary:
            html += f'''<div class="metric-card"><div class="label">Decompress/Compress</div><div class="value">{summary["decompress_vs_compress_ratio"]}x</div><div class="unit">speedup</div></div>'''
        if 'avg_compress_ops_per_sec' in summary:
            html += f'''<div class="metric-card"><div class="label">Block Compress</div><div class="value">{summary["avg_compress_ops_per_sec"]}</div><div class="unit">ops/sec</div></div>'''
        if 'avg_decompress_ops_per_sec' in summary:
            html += f'''<div class="metric-card"><div class="label">Block Decompress</div><div class="value">{summary["avg_decompress_ops_per_sec"]}</div><div class="unit">ops/sec</div></div>'''
        if 'max_avg_decompression_latency_ms' in summary:
            html += f'''<div class="metric-card"><div class="label">Max Avg Latency</div><div class="value">{summary["max_avg_decompression_latency_ms"]}</div><div class="unit">ms</div></div>'''
        if 'concurrency_scaling_ratio' in summary:
            html += f'''<div class="metric-card"><div class="label">MT Scaling</div><div class="value">{summary["concurrency_scaling_ratio"]}x</div><div class="unit">8t vs 1t</div></div>'''
        html += '</div>'

    if comp:
        results = comp.get('results', [])
        level1_1mb = [r for r in results if r.get("compression_level") == 1 and r.get("data_size") == "1MB"]
        level_items = []
        for level in [1, 2, 3, 6, 9, 12]:
            level_r = [r for r in results if r.get("compression_level") == level and r.get("data_size") == "1MB" and r.get("data_type") == "text"]
            if level_r:
                level_items.append((f"Level {level}", level_r[0].get("compression_throughput_mb_per_sec", 0)))

        html += '<div class="section"><h2>Compression Throughput (Phase 3a)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{comp.get("reference", "")}">{comp.get("reference", "N/A")}</a></p>'

        if level_items:
            html += make_bar_chart('Compression Throughput by Level (1MB text, MB/s)', level_items, color="#2e86c1")

        ratio_items = [(f"L{r.get('compression_level')}", r.get("compression_ratio", 0))
                       for r in results if r.get("data_size") == "1MB" and r.get("data_type") == "text"]
        if ratio_items:
            html += make_bar_chart('Compression Ratio by Level (1MB text)', ratio_items, color="#27ae60")

        html += '<table><tr><th>Size</th><th>Type</th><th>Level</th><th>Throughput (MB/s)</th><th>Ratio</th><th>Latency (ms)</th></tr>'
        for r in results:
            if r.get("data_type") == "text":
                html += f'<tr><td>{r.get("data_size", "N/A")}</td><td>{r.get("data_type", "N/A")}</td>'
                html += f'<td>{r.get("compression_level", "N/A")}</td>'
                html += f'<td>{r.get("compression_throughput_mb_per_sec", 0):.2f}</td>'
                html += f'<td>{r.get("compression_ratio", 0):.4f}</td>'
                html += f'<td>{r.get("avg_latency_ms", 0):.4f}</td></tr>'
        html += '</table></div>'

    if decomp:
        results = decomp.get('results', [])
        html += '<div class="section"><h2>Decompression Throughput (Phase 3b)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{decomp.get("reference", "")}">{decomp.get("reference", "N/A")}</a></p>'

        decomp_items = [(r.get("data_name", "N/A"), r.get("decompression_throughput_mb_per_sec", 0)) for r in results]
        if decomp_items:
            html += make_bar_chart('Decompression Throughput (MB/s)', decomp_items, color="#27ae60")

        html += '<table><tr><th>Dataset</th><th>Throughput (MB/s)</th><th>Avg (ms)</th><th>P50 (ms)</th><th>P90 (ms)</th><th>P99 (ms)</th></tr>'
        for r in results:
            html += f'<tr><td>{r.get("data_name", "N/A")}</td>'
            html += f'<td>{r.get("decompression_throughput_mb_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("avg_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("p50_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("p90_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("p99_latency_ms", 0):.4f}</td></tr>'
        html += '</table></div>'

    if micro:
        results = micro.get('results', [])
        html += '<div class="section"><h2>Micro Benchmarks (Phase 3c)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">{micro.get("reference", "N/A")}</a></p>'

        ops_items = [(r.get("operation", "N/A"), r.get("ops_per_sec", 0)) for r in results]
        if ops_items:
            html += make_bar_chart('Block-level Ops/sec', ops_items, color="#2e86c1")

        html += '<table><tr><th>Operation</th><th>Size</th><th>Ops/sec</th><th>Latency (ms)</th><th>Throughput (MB/s)</th></tr>'
        for r in results:
            html += f'<tr><td>{r.get("operation", "N/A")}</td><td>{r.get("block_size_name", "N/A")}</td>'
            html += f'<td>{r.get("ops_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("avg_latency_ms", 0):.4f}</td>'
            html += f'<td>{r.get("throughput_mb_per_sec", 0):.2f}</td></tr>'
        html += '</table></div>'

    if conc:
        results = conc.get('results', [])
        html += '<div class="section"><h2>Concurrency Scaling (Phase 3d)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{conc.get("reference", "")}">{conc.get("reference", "N/A")}</a></p>'

        compress_scale = [(f'{r.get("mode", "N/A")} t={r.get("thread_count", "N/A")}',
                           r.get("total_throughput_mb_per_sec", 0)) for r in results]
        if compress_scale:
            html += make_bar_chart('Throughput by thread count (MB/s)', compress_scale, color="#2e86c1")

        html += '<table><tr><th>Mode</th><th>Threads</th><th>Total Throughput (MB/s)</th><th>Total Ops/sec</th><th>Avg Latency (ms)</th></tr>'
        for r in results:
            html += f'<tr><td>{r.get("mode", "N/A")}</td><td>{r.get("thread_count", "N/A")}</td>'
            html += f'<td>{r.get("total_throughput_mb_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("total_ops_per_sec", 0):.2f}</td>'
            html += f'<td>{r.get("avg_latency_ms", 0):.4f}</td></tr>'
        html += '</table></div>'

    html += f'''
<div class="section">
<h2>ARM64 Optimization Highlights</h2>
<table>
<tr><th>Feature</th><th>Impact</th><th>Status</th></tr>
<tr><td>LZ4 Block Format</td><td>ARM64 NEON-optimized memcpy/memmove for fast copy operations</td><td>v{lz4_ver}</td></tr>
<tr><td>LZ4 Frame Format</td><td>Streaming compression with ARM64-optimized block processing</td><td>v{lz4_ver}</td></tr>
<tr><td>LZ4 HC</td><td>High compression mode with ARM64 hash table optimizations</td><td>v{lz4_ver}</td></tr>
<tr><td>Multi-threading</td><td>v1.10.0 introduces multi-core compression/decompression (ThreadPoolExecutor)</td><td>v{lz4_ver}</td></tr>
<tr><td>Level 2</td><td>New mid-way compression level filling gap between fast and HC</td><td>v{lz4_ver}</td></tr>
<tr><td>Dictionary Compression</td><td>Stable dictionary support for small data compression</td><td>v{lz4_ver}</td></tr>
<tr><td>Async I/O Decompression</td><td>v1.10.0 overlap I/O with decompression for +60% speed improvement</td><td>v{lz4_ver}</td></tr>
</table></div>

<div class="shunit2-section">
<h2>shUnit2 Test Results</h2>
<p>Validation tests via shUnit2. See <code>lz4_test.sh</code> for test functions covering all phases.</p>
<table>
<tr><th>Phase</th><th>Test Functions</th><th>Count</th></tr>
<tr><td>Phase 2: Verify</td><td>testArchitectureIsARM64, testLz4IsInstalled, testLz4VersionMatches, testPythonLz4BindingsAvailable, testVersionInfoJsonExists</td><td>5</td></tr>
<tr><td>Phase 3a: Compression</td><td>testBenchmarkCompressionProducesResults, testBenchmarkCompressionHasRequiredFields, testBenchmarkCompressionThroughputAboveThreshold, testBenchmarkCompressionRatioAboveThreshold</td><td>4</td></tr>
<tr><td>Phase 3b: Decompression</td><td>testBenchmarkDecompressionProducesResults, testBenchmarkDecompressionThroughputAboveThreshold, testBenchmarkDecompressionLatencyBelowThreshold</td><td>3</td></tr>
<tr><td>Phase 3c: Micro</td><td>testBenchmarkMicroProducesResults, testBenchmarkMicroAllOperationsCompleted, testBenchmarkMicroCompressOpsAboveThreshold, testBenchmarkMicroDecompressOpsAboveThreshold</td><td>4</td></tr>
<tr><td>Phase 3d: Concurrency</td><td>testBenchmarkConcurrencyProducesResults, testBenchmarkConcurrencyShowsProgression, testBenchmarkConcurrencyThroughputAboveThreshold</td><td>3</td></tr>
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
