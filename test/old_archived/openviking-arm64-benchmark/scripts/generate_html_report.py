#!/usr/bin/env python3
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_css():
    return """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
.container { max-width: 960px; margin: 0 auto; }
h1 { color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }
h2 { color: #16213e; margin-top: 30px; }
.metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
.metric-card { background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.metric-card .label { font-size: 12px; color: #666; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #1a1a2e; }
.metric-card .unit { font-size: 14px; color: #888; }
table { width: 100%; border-collapse: collapse; margin: 15px 0; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
th { background: #1a1a2e; color: white; }
tr:nth-child(even) { background: #f9f9f9; }
.pass { color: #27ae60; font-weight: bold; }
.fail { color: #e74c3c; font-weight: bold; }
.skip { color: #f39c12; font-weight: bold; }
.env-table { background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.chart-container { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 20px 0; }
.bar-chart { display: flex; align-items: flex-end; height: 200px; gap: 8px; }
.bar { background: #e94560; border-radius: 4px 4px 0 0; min-width: 40px; position: relative; }
.bar-label { position: absolute; bottom: -20px; width: 100%; text-align: center; font-size: 11px; color: #666; }
.bar-value { position: absolute; top: -20px; width: 100%; text-align: center; font-size: 12px; font-weight: bold; }
.test-result { padding: 5px 10px; border-radius: 4px; margin: 3px 0; }
.test-pass { background: #d4edda; border: 1px solid #c3e6cb; }
.test-fail { background: #f8d7da; border: 1px solid #f5c6cb; }
.test-skip { background: #fff3cd; border: 1px solid #ffeeba; }
"""


def generate_bar_svg(values, labels, title, max_val=None):
    if not values:
        return "<p>No data available</p>"
    max_val = max_val or max(values)
    chart_height = 180
    bar_width = max(30, min(60, 400 // len(values)))
    total_width = len(values) * (bar_width + 8) + 40
    svg_parts = [f'<svg width="{total_width}" height="{chart_height + 60}" viewBox="0 0 {total_width} {chart_height + 60}">']
    svg_parts.append(f'<text x="{total_width // 2}" y="15" font-size="14" font-weight="bold" text-anchor="middle">{title}</text>')
    svg_parts.append(f'<line x1="30" y1="{chart_height + 20}" x2="{total_width - 10}" y2="{chart_height + 20}" stroke="#ccc"/>')
    for i, (val, label) in enumerate(zip(values, labels)):
        bar_height = (val / max_val) * chart_height if max_val > 0 else 0
        x = 30 + i * (bar_width + 8)
        y = chart_height + 20 - bar_height
        svg_parts.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" fill="#e94560" rx="3"/>')
        svg_parts.append(f'<text x="{x + bar_width // 2}" y="{y - 5}" font-size="10" text-anchor="middle" font-weight="bold">{val:.1f}</text>')
        svg_parts.append(f'<text x="{x + bar_width // 2}" y="{chart_height + 35}" font-size="10" text-anchor="middle">{label}</text>')
    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def main():
    results_dir = sys.argv[1]
    software_version = sys.argv[2]

    agg_path = os.path.join(results_dir, "all_results.json")
    version_path = os.path.join(results_dir, "version_info.json")
    locomo_path = os.path.join(results_dir, "benchmark_locomo.json")
    hotpotqa_path = os.path.join(results_dir, "benchmark_hotpotqa.json")
    micro_path = os.path.join(results_dir, "micro_benchmark.json")
    stress_path = os.path.join(results_dir, "stress_benchmark.json")

    data = {}
    if os.path.exists(agg_path):
        with open(agg_path) as f:
            data = json.load(f)

    version_info = {}
    if os.path.exists(version_path):
        with open(version_path) as f:
            version_info = json.load(f)

    locomo_data = {}
    if os.path.exists(locomo_path):
        with open(locomo_path) as f:
            locomo_data = json.load(f)

    hotpotqa_data = {}
    if os.path.exists(hotpotqa_path):
        with open(hotpotqa_path) as f:
            hotpotqa_data = json.load(f)

    micro_data = {}
    if os.path.exists(micro_path):
        with open(micro_path) as f:
            micro_data = json.load(f)

    stress_data = {}
    if os.path.exists(stress_path):
        with open(stress_path) as f:
            stress_data = json.load(f)

    env = version_info.get("environment", {})
    sw = version_info.get("software", {})

    html_parts = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append("<html lang='en'><head><meta charset='UTF-8'>")
    html_parts.append(f"<title>OpenViking {software_version} ARM64 Benchmark Report</title>")
    html_parts.append(f"<style>{generate_css()}</style>")
    html_parts.append("</head><body>")
    html_parts.append("<div class='container'>")

    html_parts.append(f"<h1>OpenViking {software_version} ARM64 Performance Benchmark</h1>")
    html_parts.append(f"<p>Generated: {__import__('time').strftime('%Y-%m-%d %H:%M:%S UTC', __import__('time').gmttime())}</p>")

    html_parts.append("<h2>Environment Information</h2>")
    html_parts.append("<div class='env-table'><table>")
    env_items = [
        ("Architecture", env.get("architecture", "N/A")),
        ("OS", env.get("os", "N/A")),
        ("Kernel", env.get("kernel", "N/A")),
        ("CPU Model", env.get("cpu_model", "N/A")),
        ("CPU Cores", env.get("cores", "N/A")),
        ("Memory", f"{env.get('memory_mb', 'N/A')} MB"),
        ("Software Version", sw.get("version", software_version)),
    ]
    for key, val in env_items:
        html_parts.append(f"<tr><th>{key}</th><td>{val}</td></tr>")
    html_parts.append("</table></div>")

    html_parts.append("<h2>Metric Summary</h2>")
    html_parts.append("<div class='metric-grid'>")

    if locomo_data:
        summary = locomo_data.get("summary", {})
        html_parts.append("<div class='metric-card'>")
        html_parts.append("<div class='label'>LoCoMo Accuracy</div>")
        html_parts.append(f"<div class='value'>{summary.get('avg_accuracy_pct', 'N/A')}</div>")
        html_parts.append("<div class='unit'>%</div>")
        html_parts.append("</div>")
        html_parts.append("<div class='metric-card'>")
        html_parts.append("<div class='label'>LoCoMo Avg Latency</div>")
        html_parts.append(f"<div class='value'>{summary.get('avg_query_time_ms', 'N/A')}</div>")
        html_parts.append("<div class='unit'>ms</div>")
        html_parts.append("</div>")

    if hotpotqa_data:
        summary = hotpotqa_data.get("summary", {})
        html_parts.append("<div class='metric-card'>")
        html_parts.append("<div class='label'>HotpotQA Accuracy</div>")
        html_parts.append(f"<div class='value'>{summary.get('avg_accuracy_pct', 'N/A')}</div>")
        html_parts.append("<div class='unit'>%</div>")
        html_parts.append("</div>")

    if micro_data:
        results = micro_data.get("results", [])
        emb_results = [r for r in results if r.get("operation") == "embedding_throughput"]
        if emb_results:
            avg_thr = sum(r.get("embeddings_per_sec", 0) for r in emb_results) / len(emb_results)
            html_parts.append("<div class='metric-card'>")
            html_parts.append("<div class='label'>Embedding Throughput</div>")
            html_parts.append(f"<div class='value'>{avg_thr:.1f}</div>")
            html_parts.append("<div class='unit'>ops/sec</div>")
            html_parts.append("</div>")

        ret_results = [r for r in results if r.get("operation") == "retrieval_latency"]
        if ret_results:
            avg_qps = sum(r.get("queries_per_sec", 0) for r in ret_results) / len(ret_results)
            html_parts.append("<div class='metric-card'>")
            html_parts.append("<div class='label'>Retrieval QPS</div>")
            html_parts.append(f"<div class='value'>{avg_qps:.1f}</div>")
            html_parts.append("<div class='unit'>queries/sec</div>")
            html_parts.append("</div>")

    html_parts.append("</div>")

    if locomo_data and locomo_data.get("results"):
        html_parts.append("<h2>LoCoMo User Memory Benchmark</h2>")
        html_parts.append("<div class='chart-container'>")
        results = locomo_data.get("results", [])
        accuracies = [r.get("accuracy_pct", 0) for r in results]
        labels = [f"Iter {r.get('iteration', i+1)}" for i, r in enumerate(results)]
        html_parts.append(generate_bar_svg(accuracies, labels, "LoCoMo QA Accuracy (%)", max_val=100))
        html_parts.append("</div>")
        html_parts.append("<table><tr><th>Iteration</th><th>Accuracy (%)</th><th>Avg Latency (ms)</th><th>P50 (ms)</th><th>P99 (ms)</th></tr>")
        for r in results:
            html_parts.append(f"<tr><td>{r.get('iteration', 'N/A')}</td><td>{r.get('accuracy_pct', 'N/A')}</td><td>{r.get('avg_query_time_ms', 'N/A')}</td><td>{r.get('p50_latency_ms', 'N/A')}</td><td>{r.get('p99_latency_ms', 'N/A')}</td></tr>")
        html_parts.append("</table>")
        html_parts.append(f"<p><em>Reference: {locomo_data.get('reference', 'N/A')}</em></p>")

    if hotpotqa_data and hotpotqa_data.get("results"):
        html_parts.append("<h2>HotpotQA Knowledge Base Benchmark</h2>")
        html_parts.append("<div class='chart-container'>")
        results = hotpotqa_data.get("results", [])
        accuracies = [r.get("accuracy_pct", 0) for r in results]
        labels = [f"Iter {r.get('iteration', i+1)}" for i, r in enumerate(results)]
        html_parts.append(generate_bar_svg(accuracies, labels, "HotpotQA Accuracy (%)", max_val=100))
        html_parts.append("</div>")
        html_parts.append("<table><tr><th>Iteration</th><th>Accuracy (%)</th><th>Avg Latency (ms)</th><th>Retrieval (ms)</th><th>P50 (ms)</th></tr>")
        for r in results:
            html_parts.append(f"<tr><td>{r.get('iteration', 'N/A')}</td><td>{r.get('accuracy_pct', 'N/A')}</td><td>{r.get('avg_query_time_ms', 'N/A')}</td><td>{r.get('avg_retrieval_time_ms', 'N/A')}</td><td>{r.get('p50_latency_ms', 'N/A')}</td></tr>")
        html_parts.append("</table>")
        html_parts.append(f"<p><em>Reference: {hotpotqa_data.get('reference', 'N/A')}</em></p>")

    if micro_data and micro_data.get("results"):
        html_parts.append("<h2>Micro Benchmarks</h2>")
        results = micro_data.get("results", [])
        operations = {}
        for r in results:
            op = r.get("operation", "unknown")
            if op not in operations:
                operations[op] = []
            operations[op].append(r)
        for op_name, op_results in operations.items():
            html_parts.append(f"<h3>{op_name}</h3>")
            html_parts.append("<table><tr>")
            keys = list(op_results[0].keys())
            for k in keys:
                html_parts.append(f"<th>{k}</th>")
            html_parts.append("</tr>")
            for r in op_results:
                html_parts.append("<tr>")
                for k in keys:
                    val = r.get(k, "N/A")
                    html_parts.append(f"<td>{val}</td>")
                html_parts.append("</tr>")
            html_parts.append("</table>")

    if stress_data and stress_data.get("results"):
        html_parts.append("<h2>Stress Test Results</h2>")
        html_parts.append("<div class='chart-container'>")
        results = stress_data.get("results", [])
        qps_vals = [r.get("qps", 0) for r in results]
        conc_labels = [f"C={r.get('concurrency', 'N/A')}" for r in results]
        html_parts.append(generate_bar_svg(qps_vals, conc_labels, "QPS by Concurrency Level"))
        html_parts.append("</div>")
        html_parts.append("<table><tr><th>Concurrency</th><th>QPS</th><th>Avg Latency (ms)</th><th>P99 (ms)</th><th>Errors</th><th>Error Rate (%)</th></tr>")
        for r in results:
            html_parts.append(f"<tr><td>{r.get('concurrency', 'N/A')}</td><td>{r.get('qps', 'N/A')}</td><td>{r.get('avg_latency_ms', 'N/A')}</td><td>{r.get('p99_latency_ms', 'N/A')}</td><td>{r.get('errors', 'N/A')}</td><td>{r.get('error_rate_pct', 'N/A')}</td></tr>")
        html_parts.append("</table>")

    html_parts.append("<h2>shUnit2 Test Results</h2>")
    html_parts.append("<div>")
    test_names = [
        ("testArchitectureIsARM64", "ARM64 Architecture"),
        ("testSoftwareIsInstalled", "Software Installed"),
        ("testSoftwareVersionMatches", "Version Matches"),
        ("testPythonVersionSufficient", "Python Version"),
        ("testVersionInfoJsonExists", "Version Info JSON"),
        ("testBenchmarkPrimaryProducesResults", "LoCoMo Results Exist"),
        ("testBenchmarkPrimaryHasRequiredFields", "LoCoMo Fields Valid"),
        ("testBenchmarkPrimaryAccuracyAboveThreshold", "LoCoMo Accuracy Threshold"),
        ("testBenchmarkPrimaryLatencyBelowThreshold", "LoCoMo Latency Threshold"),
        ("testBenchmarkSecondaryProducesResults", "HotpotQA Results Exist"),
        ("testBenchmarkSecondaryHasRequiredFields", "HotpotQA Fields Valid"),
        ("testBenchmarkSecondaryAccuracyAboveThreshold", "HotpotQA Accuracy Threshold"),
        ("testBenchmarkMicroProducesResults", "Micro Results Exist"),
        ("testBenchmarkMicroAllOperationsCompleted", "Micro Operations Complete"),
        ("testBenchmarkMicroEmbeddingThroughput", "Embedding Throughput"),
        ("testBenchmarkStressProducesResults", "Stress Results Exist"),
        ("testAggregatedResultsExist", "Aggregated Results"),
        ("testHtmlReportGenerated", "HTML Report"),
        ("testSummaryReportGenerated", "Summary Report"),
        ("testAggregatedResultsContainsAllBenchmarks", "All Benchmarks Present"),
    ]
    for test_func, test_desc in test_names:
        html_parts.append(f"<div class='test-result test-skip'>{test_func}: {test_desc} (results pending)</div>")
    html_parts.append("</div>")

    html_parts.append("</div></body></html>")

    output_path = os.path.join(results_dir, "benchmark_report.html")
    with open(output_path, "w") as f:
        f.write("\n".join(html_parts))
    print(f"[REPORT] HTML report written to {output_path}")


if __name__ == "__main__":
    main()