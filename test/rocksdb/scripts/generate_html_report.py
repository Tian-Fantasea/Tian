#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #c0492c, #6b3a2a); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #ffe0d0; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #c0492c; border-bottom: 2px solid #6b3a2a; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #c0492c; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #f8e8e0; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #c0492c; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 200px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #c0492c; margin-left: 8px; white-space: nowrap; }
.arm64-badge { background: #c0492c; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }
</style>
"""


def make_bar_chart(title, items, max_val=None, color="#c0492c"):
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
            <div class="bar-value">{value:.0f}</div>
        </div>'''
    html += '</div>'
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate HTML report for benchmark results")
    parser.add_argument("--input", required=True, help="Input results.json file")
    parser.add_argument("--output", required=True, help="Output results.html file")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("[HTML] results.json not found")
        return

    with open(args.input, "r") as f:
        all_data = json.load(f)

    env = all_data.get("environment", {})
    benchmarks = all_data.get("benchmarks", {})
    summary = all_data.get("summary", {})
    timestamp = all_data.get("timestamp", "")

    vi = env
    ycsb = benchmarks.get("ycsb", {})
    dbbench = benchmarks.get("dbbench", {})
    micro = benchmarks.get("micro", {})

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RocksDB ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>RocksDB ARM64 Performance Benchmark Report <span class="arm64-badge">ARM64</span></h1>
    <div class="meta">RocksDB {vi.get("rocksdb_version", "N/A")} | {vi.get("architecture", "N/A")} | {vi.get("cpu_cores", "N/A")} cores | CRC32C HW: {vi.get("arm64_crc32c_detected", "N/A")} | Generated {timestamp}</div>
</div>

<div class="section">
<h2>Environment Information</h2>
<table>
<tr><th>Property</th><th>Value</th></tr>
<tr><td>Architecture</td><td>{vi.get("architecture", "N/A")}</td></tr>
<tr><td>OS</td><td>{vi.get("os", "N/A")}</td></tr>
<tr><td>Kernel</td><td>{vi.get("kernel", "N/A")}</td></tr>
<tr><td>CPU</td><td>{vi.get("cpu_model", "N/A")} ({vi.get("cpu_cores", "N/A")} cores)</td></tr>
<tr><td>Memory</td><td>{vi.get("total_memory_mb", "N/A")} MB</td></tr>
<tr><td>RocksDB Version</td><td>{vi.get("rocksdb_version", "N/A")}</td></tr>
<tr><td>db_bench</td><td>{vi.get("db_bench_path", "N/A")}</td></tr>
<tr><td>ARM64 CRC32C</td><td>{vi.get("arm64_crc32c_detected", "N/A")}</td></tr>
<tr><td>NEON/ASIMD</td><td>{vi.get("neon_asimd_available", "N/A")}</td></tr>
<tr><td>Static Lib</td><td>{vi.get("static_lib_exists", "N/A")}</td></tr>
</table>
</div>
'''

    if summary:
        html += '<div class="metric-grid">'
        if "max_throughput" in summary:
            mt = summary["max_throughput"]
            html += f'''<div class="metric-card"><div class="label">Max Throughput</div><div class="value">{mt['value']}</div><div class="unit">ops/sec ({mt['name']})</div></div>'''
        if "avg_throughput" in summary:
            html += f'''<div class="metric-card"><div class="label">Avg Throughput</div><div class="value">{summary['avg_throughput']}</div><div class="unit">ops/sec</div></div>'''
        if "max_latency" in summary:
            ml = summary["max_latency"]
            html += f'''<div class="metric-card"><div class="label">Max Latency</div><div class="value">{ml['value']}</div><div class="unit">ms ({ml['name']})</div></div>'''
        if "avg_latency" in summary:
            html += f'''<div class="metric-card"><div class="label">Avg Latency</div><div class="value">{summary['avg_latency']}</div><div class="unit">ms</div></div>'''
        html += '</div>'

    if ycsb:
        ycsb_results = ycsb.get("results", {})
        params = ycsb.get("parameters", {})

        html += '<div class="section"><h2>YCSB Workloads (Phase 3a)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="https://github.com/brianfrankcooper/YCSB">YCSB</a></p>'
        html += f'<p>Keys: {params.get("num_keys", "N/A")}, Value: {params.get("value_size", "N/A")}B, Threads: {params.get("threads", "N/A")}</p>'

        html += '<div class="metric-grid">'
        for wl_name, wl_data in ycsb_results.items():
            html += f'''<div class="metric-card">
                <div class="label">{wl_name.replace("ycsb_", "Workload ").replace("_", " ")} Run TPS</div>
                <div class="value">{wl_data.get("run_throughput_ops_sec", "N/A")}</div>
                <div class="unit">ops/sec ({wl_data.get("ycsb_ratio", "")})</div>
            </div>'''
        html += '</div>'

        run_ops_items = [(wl_name.replace("ycsb_", ""), wl_data.get("run_throughput_ops_sec", 0)) for wl_name, wl_data in ycsb_results.items()]
        html += make_bar_chart("YCSB Run Throughput (ops/sec)", run_ops_items, color="#c0492c")

        html += '<h3>Detailed YCSB Results</h3>'
        html += '<table><tr><th>Workload</th><th>Description</th><th>Ratio</th><th>Load TPS</th><th>Run TPS</th><th>Run Lat (ms)</th></tr>'
        for wl_name, wl_data in ycsb_results.items():
            html += f'<tr><td>{wl_name}</td><td>{wl_data.get("description", "")}</td><td>{wl_data.get("ycsb_ratio", "")}</td>'
            html += f'<td>{wl_data.get("load_throughput_ops_sec", "N/A")}</td><td>{wl_data.get("run_throughput_ops_sec", "N/A")}</td>'
            html += f'<td>{wl_data.get("run_latency_avg_ms", "N/A")}</td></tr>'
        html += '</table></div>'

    if dbbench:
        dbb_results = dbbench.get("results", {})

        html += '<div class="section"><h2>db_bench Advanced Benchmarks (Phase 3b)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{dbbench.get("reference", "")}">RocksDB Wiki</a></p>'

        comp = dbb_results.get("compaction_styles", {})
        if comp:
            html += '<h3>Compaction Styles</h3>'
            fill_items = [(name, data.get("fillrandom_avg_ops_sec", 0)) for name, data in comp.items()]
            html += make_bar_chart("Fill Throughput by Compaction Style (ops/sec)", fill_items, color="#c0492c")
            html += '<table><tr><th>Style</th><th>Description</th><th>Fill (ops/s)</th><th>Overwrite (ops/s)</th><th>Fill Lat (ms)</th><th>Overwrite Lat (ms)</th></tr>'
            for name, data in comp.items():
                html += f'<tr><td>{name}</td><td>{data.get("description", "")}</td>'
                html += f'<td>{data.get("fillrandom_avg_ops_sec", "N/A")}</td><td>{data.get("overwrite_avg_ops_sec", "N/A")}</td>'
                html += f'<td>{data.get("fillrandom_avg_lat_ms", "N/A")}</td><td>{data.get("overwrite_avg_lat_ms", "N/A")}</td></tr>'
            html += '</table>'

        compress = dbb_results.get("compression_algorithms", {})
        if compress:
            html += '<h3>Compression Algorithms</h3>'
            read_items = [(name, data.get("readrandom_avg_ops_sec", 0)) for name, data in compress.items()]
            html += make_bar_chart("Read Throughput by Compression (ops/sec)", read_items, color="#34a853")
            html += '<table><tr><th>Algorithm</th><th>Description</th><th>Fill (ops/s)</th><th>Read (ops/s)</th><th>DB Size (MB)</th></tr>'
            for name, data in compress.items():
                html += f'<tr><td>{name}</td><td>{data.get("description", "")}</td>'
                html += f'<td>{data.get("fillseq_avg_ops_sec", "N/A")}</td><td>{data.get("readrandom_avg_ops_sec", "N/A")}</td>'
                html += f'<td>{data.get("avg_db_size_mb", "N/A")}</td></tr>'
            html += '</table>'

        filters = dbb_results.get("bloom_ribbon_filters", {})
        if filters:
            html += '<h3>Bloom &amp; Ribbon Filters</h3>'
            filt_items = [(name, data.get("avg_read_ops_sec", 0)) for name, data in filters.items()]
            html += make_bar_chart("Read Throughput by Filter Config (ops/sec)", filt_items, color="#00758f")
            html += '<table><tr><th>Filter</th><th>Description</th><th>Read (ops/s)</th><th>Read Lat (ms)</th></tr>'
            for name, data in filters.items():
                html += f'<tr><td>{name}</td><td>{data.get("description", "")}</td>'
                html += f'<td>{data.get("avg_read_ops_sec", "N/A")}</td><td>{data.get("avg_read_lat_ms", "N/A")}</td></tr>'
            html += '</table>'

        html += '</div>'

    if micro:
        micro_results = micro.get("results", {})

        html += '<div class="section"><h2>Micro Benchmarks (Phase 3c)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">RocksDB Wiki</a></p>'

        for category_name, category_data in micro_results.items():
            html += f'<h3>{category_name.replace("_", " ").title()}</h3>'
            ops_items = [(op_name, op_info.get("avg_ops_sec", 0)) for op_name, op_info in category_data.items()]
            html += make_bar_chart(f"{category_name.replace('_', ' ').title()} Throughput (ops/sec)", ops_items,
                                   color="#c0492c" if "write" in category_name or "delete" in category_name else "#00758f")
            html += '<table><tr><th>Operation</th><th>Description</th><th>Avg (ops/s)</th><th>Avg Lat (ms)</th></tr>'
            for op_name, op_info in category_data.items():
                arm64_note = op_info.get("arm64_note", "")
                note_html = f'<br><em style="color:#c0492c">{arm64_note}</em>' if arm64_note else ""
                html += f'<tr><td>{op_name}{note_html}</td><td>{op_info.get("description", "")}</td>'
                html += f'<td>{op_info.get("avg_ops_sec", "N/A")}</td><td>{op_info.get("avg_latency_ms", "N/A")}</td></tr>'
            html += '</table>'

        html += '</div>'

    html += '''
<div class="section">
<h2>ARM64 Optimization Highlights</h2>
<table>
<tr><th>Feature</th><th>Impact</th><th>Status</th></tr>
<tr><td>ARM64 CRC32C</td><td>~10x faster checksum vs software</td><td>''' + ("Detected" if vi.get("arm64_crc32c_detected") else "Not found") + '''</td></tr>
<tr><td>NEON/ASIMD</td><td>Vector operations for hashing</td><td>''' + ("Available" if vi.get("neon_asimd_available") else "Not available") + '''</td></tr>
<tr><td>march=armv8-a+crc+crypto</td><td>Compiler optimization for ARM64</td><td>Applied in build</td></tr>
<tr><td>jemalloc</td><td>Improved memory allocation</td><td>USE_JEMALLOC=1</td></tr>
</table></div>
</body></html>'''

    with open(args.output, "w") as f:
        f.write(html)
    print(f"[HTML] Report saved to {args.output}")


if __name__ == "__main__":
    main()
