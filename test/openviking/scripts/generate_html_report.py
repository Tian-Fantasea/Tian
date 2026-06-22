#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #1a1a2e, #e94560); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #ffc0cb; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #16213e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #1a1a2e; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #fff0f3; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #e94560; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.metric-card.pass .value { color: #4CAF50; }
.metric-card.fail .value { color: #f44336; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 200px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #e94560; margin-left: 8px; white-space: nowrap; }
.arm64-badge { background: #e94560; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }
.shunit2-section { background: #e8f5e9; padding: 16px; border-radius: 6px; margin-top: 16px; }
.shunit2-section h2 { color: #2e7d32; }
</style>
"""


def make_bar_chart(title, items, max_val=None, color="#e94560"):
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
    parser = argparse.ArgumentParser(description="Generate HTML report for OpenViking ARM64 benchmark results")
    parser.add_argument("--input", required=True, help="Input results.json file")
    parser.add_argument("--output", required=True, help="Output results.html file")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("[HTML] results.json not found")
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get("environment", {})
    benchmarks = data.get("benchmarks", {})
    summary = data.get("summary", {})
    timestamp = data.get("timestamp", "")

    locomo = benchmarks.get("locomo", {})
    hotpotqa = benchmarks.get("hotpotqa", {})
    micro = benchmarks.get("micro", {})

    def status_icon(val):
        return "&#x2705;" if val else "&#x274C;"

    vi = env

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenViking ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>OpenViking ARM64 Performance Benchmark Report <span class="arm64-badge">ARM64</span></h1>
    <div class="meta">OpenViking {vi.get("software_version", "N/A")} | {vi.get("architecture", "N/A")} | Python {vi.get("python_version", "N/A")} | Generated {timestamp}</div>
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
<tr><td>OpenViking Version</td><td>{vi.get("software_version", "N/A")}</td></tr>
<tr><td>Python Version</td><td>{vi.get("python_version", "N/A")}</td></tr>
<tr><td>Install Method</td><td>{vi.get("install_method", "N/A")} (pip)</td></tr>
<tr><td>Max Concurrent Emb</td><td>{vi.get("max_concurrent_embedding", "N/A")}</td></tr>
<tr><td>Max Concurrent VLM</td><td>{vi.get("max_concurrent_vlm", "N/A")}</td></tr>
<tr><td>NEON/ASIMD</td><td>{vi.get("neon_asimd_available", "N/A")}</td></tr>
</table>
</div>
'''

    if summary:
        html += '<div class="metric-grid">'
        if "locomo_avg_accuracy_pct" in summary:
            slo_met = summary.get("locomo_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">LoCoMo Accuracy</div><div class="value">{summary['locomo_avg_accuracy_pct']}</div><div class="unit">% (&gt;= 80)</div></div>'''
        if "locomo_avg_latency_ms" in summary:
            html += f'''<div class="metric-card"><div class="label">LoCoMo Latency</div><div class="value">{summary['locomo_avg_latency_ms']}</div><div class="unit">ms (&lt;= 500)</div></div>'''
        if "hotpotqa_avg_accuracy_pct" in summary:
            slo_met = summary.get("hotpotqa_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">HotpotQA Accuracy</div><div class="value">{summary['hotpotqa_avg_accuracy_pct']}</div><div class="unit">% (&gt;= 72)</div></div>'''
        if "embedding_throughput_per_sec" in summary:
            slo_met = summary.get("embedding_throughput_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">Embedding Throughput</div><div class="value">{summary['embedding_throughput_per_sec']}</div><div class="unit">ops/sec (&gt;= 50)</div></div>'''
        if "retrieval_qps" in summary:
            slo_met = summary.get("retrieval_qps_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">Retrieval QPS</div><div class="value">{summary['retrieval_qps']}</div><div class="unit">queries/sec (&gt;= 10)</div></div>'''
        html += '</div>'

    if locomo:
        results = locomo.get("results", [])
        iter_results = [r for r in results if isinstance(r.get("iteration"), int)]

        html += '<div class="section"><h2>LoCoMo User Memory (Phase 3a)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{locomo.get("reference", "")}">LoCoMo / VikingMem</a></p>'
        html += f'<p>{locomo.get("description", "")}</p>'

        if iter_results:
            acc_items = [(f"iter {r['iteration']}", r.get("accuracy_pct", 0)) for r in iter_results]
            html += make_bar_chart("LoCoMo QA Accuracy (%)", acc_items, max_val=100, color="#e94560")

            lat_items = [(f"iter {r['iteration']}", r.get("avg_query_time_ms", 0)) for r in iter_results]
            html += make_bar_chart("LoCoMo Avg Query Latency (ms)", lat_items, color="#e94560")

            html += '<table><tr><th>Iteration</th><th>Accuracy (%)</th><th>Avg Latency (ms)</th><th>p50 (ms)</th><th>p99 (ms)</th></tr>'
            for r in iter_results:
                html += f'<tr><td>{r["iteration"]}</td><td>{r.get("accuracy_pct", "N/A")}</td><td>{r.get("avg_query_time_ms", "N/A")}</td><td>{r.get("p50_latency_ms", "N/A")}</td><td>{r.get("p99_latency_ms", "N/A")}</td></tr>'
            html += '</table>'

        html += '</div>'

    if hotpotqa:
        results = hotpotqa.get("results", [])
        iter_results = [r for r in results if isinstance(r.get("iteration"), int)]

        html += '<div class="section"><h2>HotpotQA Knowledge Base (Phase 3b)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{hotpotqa.get("reference", "")}">HotpotQA</a></p>'
        html += f'<p>{hotpotqa.get("description", "")}</p>'

        if iter_results:
            acc_items = [(f"iter {r['iteration']}", r.get("accuracy_pct", 0)) for r in iter_results]
            html += make_bar_chart("HotpotQA Accuracy (%)", acc_items, max_val=100, color="#326CE5")

            html += '<table><tr><th>Iteration</th><th>Accuracy (%)</th><th>Avg Latency (ms)</th><th>Retrieval (ms)</th><th>p50 (ms)</th></tr>'
            for r in iter_results:
                html += f'<tr><td>{r["iteration"]}</td><td>{r.get("accuracy_pct", "N/A")}</td><td>{r.get("avg_query_time_ms", "N/A")}</td><td>{r.get("avg_retrieval_time_ms", "N/A")}</td><td>{r.get("p50_latency_ms", "N/A")}</td></tr>'
            html += '</table>'

        html += '</div>'

    if micro:
        results = micro.get("results", [])
        emb_results = [r for r in results if r.get("operation") == "embedding_throughput" and isinstance(r.get("iteration"), int)]
        ret_results = [r for r in results if r.get("operation") == "retrieval_latency" and isinstance(r.get("iteration"), int)]
        ctx_results = [r for r in results if r.get("operation") == "context_tier_loading"]
        sess_results = [r for r in results if r.get("operation") == "session_management"]

        html += '<div class="section"><h2>Micro Benchmarks (Phase 3c)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">OpenViking perf-tests</a></p>'

        if emb_results:
            tp_items = [(f"iter {r['iteration']}", r.get("embeddings_per_sec", 0)) for r in emb_results]
            html += make_bar_chart("Embedding Throughput (ops/sec)", tp_items, color="#FF9800")
            html += '<table><tr><th>Iteration</th><th>Throughput (ops/sec)</th><th>Time (s)</th><th>Completed</th></tr>'
            for r in emb_results:
                html += f'<tr><td>{r["iteration"]}</td><td>{r.get("embeddings_per_sec", 0):.2f}</td><td>{r.get("total_time_s", 0)}</td><td>{r.get("embeddings_completed", 0)}</td></tr>'
            html += '</table>'

        if ret_results:
            lat_items = [(f"iter {r['iteration']}", r.get("avg_latency_ms", 0)) for r in ret_results]
            html += make_bar_chart("Retrieval Avg Latency (ms)", lat_items, color="#00BCD4")
            html += '<table><tr><th>Iteration</th><th>QPS</th><th>Avg Latency (ms)</th><th>p50 (ms)</th><th>p99 (ms)</th></tr>'
            for r in ret_results:
                html += f'<tr><td>{r["iteration"]}</td><td>{r.get("queries_per_sec", 0):.2f}</td><td>{r.get("avg_latency_ms", 0):.2f}</td><td>{r.get("p50_latency_ms", 0):.2f}</td><td>{r.get("p99_latency_ms", 0):.2f}</td></tr>'
            html += '</table>'

        if ctx_results:
            html += '<h3>Context Tier Loading</h3>'
            html += '<div class="metric-grid">'
            html += f'''<div class="metric-card"><div class="label">L0 Abstract</div><div class="value">{ctx_results[0].get("L0_avg_ms", 0):.0f}</div><div class="unit">ms</div></div>'''
            html += f'''<div class="metric-card"><div class="label">L1 Overview</div><div class="value">{ctx_results[0].get("L1_avg_ms", 0):.0f}</div><div class="unit">ms</div></div>'''
            html += f'''<div class="metric-card"><div class="label">L2 Detail</div><div class="value">{ctx_results[0].get("L2_avg_ms", 0):.0f}</div><div class="unit">ms</div></div>'''
            html += '</div>'

        if sess_results:
            html += '<h3>Session Management</h3>'
            html += '<div class="metric-grid">'
            html += f'''<div class="metric-card"><div class="label">Avg Session</div><div class="value">{sess_results[0].get("avg_session_time_ms", 0):.0f}</div><div class="unit">ms</div></div>'''
            html += '</div>'

        html += '</div>'

    html += '''
<div class="section">
<h2>ARM64 Optimization Highlights</h2>
<table>
<tr><th>Feature</th><th>Impact</th><th>Status</th></tr>
<tr><td>ARM64 NEON/ASIMD</td><td>Vector ops for embedding computation</td><td>''' + ("Available" if vi.get("neon_asimd_available", "0") != "0" else "Not detected") + '''</td></tr>
<tr><td>Python ARM64 native</td><td>Native interpreter on arm64</td><td>''' + vi.get("python_version", "N/A") + '''</td></tr>
<tr><td>OpenViking pip install</td><td>ARM64 wheel where available</td><td>''' + vi.get("openviking_version", "N/A") + '''</td></tr>
<tr><td>Context tier caching</td><td>3-tier memory hierarchy (L0/L1/L2)</td><td>VikingMem architecture</td></tr>
</table></div>

<div class="shunit2-section">
<h2>shUnit2 Test Results</h2>
<p>Validation tests via shUnit2. See <code>openviking_test.sh</code> for test functions covering all phases.</p>
<table>
<tr><th>Phase</th><th>Test Functions</th><th>Count</th></tr>
<tr><td>Phase 2: Verify</td><td>testArchitectureIsARM64, testSoftwareIsInstalled, testSoftwareVersionMatches, testVersionInfoJsonExists</td><td>4</td></tr>
<tr><td>Phase 3a: LoCoMo</td><td>testBenchmarkLoComoProducesResults, testBenchmarkLoComoHasRequiredFields, testBenchmarkLoComoAccuracyAboveThreshold, testBenchmarkLoComoLatencyBelowThreshold</td><td>4</td></tr>
<tr><td>Phase 3b: HotpotQA</td><td>testBenchmarkHotpotQAProducesResults, testBenchmarkHotpotQAHasRequiredFields, testBenchmarkHotpotQAAccuracyAboveThreshold</td><td>3</td></tr>
<tr><td>Phase 3c: Micro</td><td>testBenchmarkMicroProducesResults, testBenchmarkMicroAllOperationsCompleted, testBenchmarkMicroEmbeddingThroughput</td><td>3</td></tr>
<tr><td>Phase 4: Results</td><td>testAggregatedResultsExist, testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated, testAggregatedResultsContainsAllBenchmarks</td><td>5</td></tr>
</table>
</div>
</body></html>'''

    with open(args.output, 'w') as f:
        f.write(html)
    print(f"[HTML] Report saved to {args.output}")


if __name__ == "__main__":
    main()