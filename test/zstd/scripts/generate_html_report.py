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
    html = '<h3>%s</h3><div class="bar-chart">' % title
    for label, value, color in items:
        pct = (value / max_val * 100) if max_val > 0 else 0
        html += '<div class="bar-row">'
        html += '<div class="bar-label">%s</div>' % label
        html += '<div class="bar-container"><div class="bar-fill" style="width:%.1f%%;background:%s"></div></div>' % (pct, color)
        html += '<div class="bar-value">%.2f</div>' % value
        html += '</div>'
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

    zstd_ver = vi.get('runtime_version', 'N/A')
    zstd_path = vi.get('home', 'N/A')
    gcc_ver = vi.get('runtime_detail', 'N/A')

    html = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
    html += '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
    html += '<title>zstd ARM64 Performance Benchmark Report</title>%s</head><body>' % CSS

    html += '<div class="header">'
    html += '<h1>zstd ARM64 Performance Benchmark Report</h1>'
    html += '<div class="meta">zstd %s | %s | Path: %s | GCC: %s | Generated %s</div>' % (zstd_ver, vi.get('architecture', 'N/A'), zstd_path, gcc_ver, timestamp)
    html += '</div>'

    html += '<div class="section"><h2>Environment Information</h2><table>'
    html += '<tr><th>Property</th><th>Value</th></tr>'
    html += '<tr><td>Architecture</td><td>%s</td></tr>' % vi.get('architecture', 'N/A')
    html += '<tr><td>OS</td><td>%s</td></tr>' % vi.get('os', 'N/A')
    html += '<tr><td>Kernel</td><td>%s</td></tr>' % vi.get('kernel', 'N/A')
    html += '<tr><td>CPU</td><td>%s (%s cores)</td></tr>' % (vi.get('cpu_model', 'N/A'), vi.get('cpu_cores', 'N/A'))
    html += '<tr><td>Memory</td><td>%s MB</td></tr>' % vi.get('total_memory_mb', 'N/A')
    html += '<tr><td>zstd Version</td><td>%s</td></tr>' % zstd_ver
    html += '<tr><td>zstd Path</td><td>%s</td></tr>' % zstd_path
    html += '<tr><td>GCC Version</td><td>%s</td></tr>' % gcc_ver
    html += '<tr><td>Parallelism</td><td>%s</td></tr>' % vi.get('parallelism', 'N/A')

    extra = vi.get('extra_info', {})
    if extra:
        html += '<tr><td>GCC Available</td><td>%s</td></tr>' % extra.get('gcc_available', 'N/A')
        html += '<tr><td>Compression Levels</td><td>%s</td></tr>' % extra.get('compression_levels', 'N/A')
        html += '<tr><td>Data Size</td><td>%s MB</td></tr>' % extra.get('data_size_mb', 'N/A')
        html += '<tr><td>Data Types</td><td>%s</td></tr>' % extra.get('data_types', 'N/A')
    html += '</table></div>'

    if primary:
        html += '<div class="section"><h2>Compression Performance</h2>'
        html += '<p><span class="phase-tag">Phase 3a: Throughput vs Level</span> <span class="phase-tag">Compression Ratio</span></p>'

        throughput_items = []
        ratio_items = []
        for result in primary.get('results', []):
            if result.get('test') == 'compression_throughput_vs_level':
                for d in result.get('data', []):
                    level = d.get('compression_level', 1)
                    tp = d.get('avg_compression_throughput_mb_s', 0)
                    throughput_items.append(('Level %s' % level, tp, '#3b82f6'))
                    measurements = d.get('measurements', [])
                    if measurements:
                        ratio = measurements[0].get('avg_compression_ratio', 0)
                        ratio_items.append(('Level %s' % level, ratio, '#f97316'))
            elif result.get('test') == 'compression_ratio_vs_level':
                for d in result.get('data', []):
                    level = d.get('compression_level', 1)
                    ratio = d.get('avg_compression_ratio', 0)
                    ratio_items.append(('Level %s' % level, ratio, '#f97316'))

        if throughput_items:
            html += make_bar_chart('Compression Throughput (MB/s) vs Level', throughput_items)
        if ratio_items:
            html += make_bar_chart('Compression Ratio vs Level', ratio_items)

        html += '<h3>Detailed Compression Results</h3><table>'
        html += '<tr><th>Level</th><th>Throughput (MB/s)</th><th>Time (sec)</th><th>Data Types</th></tr>'
        for result in primary.get('results', []):
            if result.get('test') == 'compression_throughput_vs_level':
                for d in result.get('data', []):
                    meas = d.get('measurements', [])
                    types = ', '.join(m.get('data_type', '') for m in meas)
                    html += '<tr><td>%s</td><td>%.2f</td><td>%.4f</td><td>%s</td></tr>' % (d.get('compression_level', 'N/A'), d.get('avg_compression_throughput_mb_s', 0), d.get('avg_compression_time_sec', 0), types)
        html += '</table>'

        for result in primary.get('results', []):
            if result.get('test') == 'compression_ratio_vs_level':
                html += '<h3>Compression Ratio vs Level</h3><table>'
                html += '<tr><th>Level</th><th>Avg Ratio</th></tr>'
                for d in result.get('data', []):
                    html += '<tr><td>%s</td><td>%.3f</td></tr>' % (d.get('compression_level', 'N/A'), d.get('avg_compression_ratio', 0))
                html += '</table>'

        html += '</div>'

    if secondary:
        html += '<div class="section"><h2>Decompression Performance</h2>'
        html += '<p><span class="phase-tag">Phase 3b: Throughput</span> <span class="phase-tag">Streaming Decompression</span></p>'

        decompress_items = []
        for result in secondary.get('results', []):
            if result.get('test') == 'decompression_throughput_vs_level':
                for d in result.get('data', []):
                    level = d.get('compression_level', 1)
                    tp = d.get('avg_decompression_throughput_mb_s', 0)
                    decompress_items.append(('Level %s' % level, tp, '#10b981'))

        if decompress_items:
            html += make_bar_chart('Decompression Throughput (MB/s) vs Level', decompress_items)

        html += '<h3>Detailed Decompression Results</h3><table>'
        html += '<tr><th>Level</th><th>Decompress (MB/s)</th><th>Time (ms)</th><th>Data Types</th></tr>'
        for result in secondary.get('results', []):
            if result.get('test') == 'decompression_throughput_vs_level':
                for d in result.get('data', []):
                    meas = d.get('measurements', [])
                    types = ', '.join(m.get('data_type', '') for m in meas)
                    html += '<tr><td>%s</td><td>%.2f</td><td>%.2f</td><td>%s</td></tr>' % (d.get('compression_level', 'N/A'), d.get('avg_decompression_throughput_mb_s', 0), d.get('avg_decompression_time_ms', 0), types)
        html += '</table>'

        for result in secondary.get('results', []):
            if result.get('test') == 'streaming_decompression_vs_level':
                html += '<h3>Streaming Decompression vs Level</h3><table>'
                html += '<tr><th>Level</th><th>Streaming (MB/s)</th></tr>'
                for d in result.get('data', []):
                    html += '<tr><td>%s</td><td>%.2f</td></tr>' % (d.get('compression_level', 'N/A'), d.get('avg_streaming_decompress_throughput_mb_s', 0))
                html += '</table>'

        html += '</div>'

    if micro:
        html += '<div class="section"><h2>Micro Benchmarks</h2>'
        html += '<p><span class="phase-tag">Phase 3c: Single-Block API</span> <span class="phase-tag">Dictionary Compression</span> <span class="phase-tag">ARM64 Features</span></p>'

        for result in micro.get('results', []):
            if result.get('test') == 'single_block_api_latency':
                html += '<h3>Single-Block API Latency (1MB block)</h3><table>'
                html += '<tr><th>Level</th><th>Compress (MB/s)</th><th>Decompress (MB/s)</th><th>Ratio</th></tr>'
                for d in result.get('data', []):
                    html += '<tr><td>%s</td><td>%.2f</td><td>%.2f</td><td>%.3f</td></tr>' % (d.get('level', 'N/A'), d.get('avg_compress_throughput_mb_s', 0), d.get('avg_decompress_throughput_mb_s', 0), d.get('avg_ratio', 0))
                html += '</table>'

            elif result.get('test') == 'dictionary_compression':
                d = result.get('data', {})
                if isinstance(d, dict):
                    html += '<h3>Dictionary Compression Performance</h3><table>'
                    html += '<tr><th>Metric</th><th>Value</th></tr>'
                    html += '<tr><td>Sample Size</td><td>%s KB</td></tr>' % d.get('sample_size_kb', 'N/A')
                    html += '<tr><td>Compress Throughput</td><td>%.2f MB/s</td></tr>' % d.get('avg_dict_compress_throughput_mb_s', 0)
                    html += '<tr><td>Compression Ratio</td><td>%.3f</td></tr>' % d.get('avg_dict_ratio', 0)
                    html += '</table>'

            elif result.get('test') == 'arm64_optimization_detection':
                data = result.get('data', {})
                html += '<h3>ARM64 Optimization Feature Detection</h3><table>'
                html += '<tr><th>Feature</th><th>Available</th><th>Impact on zstd</th></tr>'
                features = [
                    ('NEON (SIMD)', data.get('neon', False), 'Accelerated Huffman decoding, ~3x faster'),
                    ('SVE (Scalable Vectors)', data.get('sve', False), 'Future scalable vectorization'),
                    ('LSE Atomics', data.get('lse_atomics', False), 'Faster atomic ops in multi-threaded decompression'),
                    ('CRC32 Instructions', data.get('crc32', False), 'Hardware checksum, ~10x faster verification'),
                    ('zstd NEON Optimization', data.get('zstd_neon_optimization', False), 'zstd ARM64-specific NEON code paths active'),
                ]
                for feat, available, impact in features:
                    status = 'YES' if available else 'NO'
                    cls = 'feature-yes' if available else 'feature-no'
                    html += '<tr><td>%s</td><td class="%s">%s</td><td>%s</td></tr>' % (feat, cls, status, impact)
                html += '</table>'

        html += '</div>'

    html += '<div class="section"><h2>Benchmark Descriptions & References</h2><table>'
    html += '<tr><th>Benchmark</th><th>Description</th><th>Reference</th></tr>'
    if primary:
        html += '<tr><td>Compression</td><td>%s</td><td><a href="https://github.com/inikep/lzbench">lzbench</a></td></tr>' % primary.get("description", "")
    if secondary:
        html += '<tr><td>Decompression</td><td>%s</td><td><a href="https://github.com/inikep/lzbench">lzbench</a></td></tr>' % secondary.get("description", "")
    if micro:
        html += '<tr><td>Micro Ops</td><td>%s</td><td><a href="https://github.com/inikep/lzbench">lzbench</a>, <a href="https://facebook.github.io/zstd">zstd official</a></td></tr>' % micro.get("description", "")
    html += '</table></div></body></html>'

    os.makedirs(os.path.dirname(output_html) or '.', exist_ok=True)
    with open(output_html, 'w') as f:
        f.write(html)

    print('[HTML] Report saved to %s' % output_html)


if __name__ == '__main__':
    main()
