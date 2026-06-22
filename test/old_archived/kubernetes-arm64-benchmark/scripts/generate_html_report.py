#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime


def generate_bar_svg(values, labels, title, width=400, height=200, bar_color="#4CAF50", threshold=None, threshold_label=""):
    max_val = max(values) if values else 100
    if threshold and threshold > max_val:
        max_val = threshold
    max_val = max(max_val, 1)

    bar_width = 30
    spacing = 15
    num_bars = len(values)
    chart_width = num_bars * (bar_width + spacing) + 60
    if chart_width < width:
        chart_width = width
    chart_height = height - 40

    svg_parts = []
    svg_parts.append(f'<svg width="{chart_width}" height="{height}" xmlns="http://www.w3.org/2000/svg">')
    svg_parts.append(f'<rect width="{chart_width}" height="{height}" fill="#f8f9fa" rx="4"/>')
    svg_parts.append(f'<text x="{chart_width // 2}" y="20" font-size="12" font-family="monospace" text-anchor="middle" fill="#333">{title}</text>')

    for i, (val, label) in enumerate(zip(values, labels)):
        x = 30 + i * (bar_width + spacing)
        bar_h = (val / max_val) * chart_height * 0.8
        y = chart_height - bar_h + 30

        color = bar_color
        if threshold and val > threshold:
            color = "#f44336"

        svg_parts.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" fill="{color}" rx="2"/>')
        svg_parts.append(f'<text x="{x + bar_width // 2}" y="{chart_height + 35}" font-size="9" font-family="monospace" text-anchor="middle" fill="#666">{label}</text>')
        svg_parts.append(f'<text x="{x + bar_width // 2}" y="{y - 5}" font-size="8" font-family="monospace" text-anchor="middle" fill="#333">{val:.0f}</text>')

    if threshold:
        th_y = chart_height - (threshold / max_val) * chart_height * 0.8 + 30
        svg_parts.append(f'<line x1="25" y1="{th_y}" x2="{chart_width - 10}" y2="{th_y}" stroke="#FF5722" stroke-width="1.5" stroke-dasharray="4,4"/>')
        svg_parts.append(f'<text x="{chart_width - 8}" y="{th_y - 3}" font-size="8" font-family="monospace" fill="#FF5722">{threshold_label}</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_comparison_bar_svg(benchmark_data, metric_key, title, threshold=None, threshold_label=""):
    results = benchmark_data.get("results", [])
    iterations = [r for r in results if isinstance(r.get("iteration"), int)]

    values = []
    labels = []
    for r in iterations:
        val = r.get(metric_key, 0)
        values.append(val)
        labels.append(f"iter{r.get('iteration', '?')}")

    return generate_bar_svg(values, labels, title, threshold=threshold, threshold_label=threshold_label)


def main():
    parser = argparse.ArgumentParser(description="Generate HTML report with charts for Kubernetes ARM64 benchmark")
    parser.add_argument("--results-dir", required=True)
    args = parser.parse_args()

    results_dir = args.results_dir
    agg_file = os.path.join(results_dir, "all_results.json")

    try:
        with open(agg_file, 'r') as f:
            data = json.load(f)
    except Exception:
        print("[HTML] No aggregated results found")
        return

    summary = data.get("summary", {})
    version_info = data.get("version_info", {})
    benchmarks = data.get("benchmarks", {})

    pod_startup = benchmarks.get("pod_startup", {})
    api_latency = benchmarks.get("api_latency", {})
    micro = benchmarks.get("micro", {})
    stress = benchmarks.get("stress", {})

    pod_startup_svg = ""
    if pod_startup.get("results"):
        pod_startup_svg = generate_comparison_bar_svg(
            pod_startup, "p99_latency_ms",
            "Pod Startup Latency (p99)",
            threshold=5000, threshold_label="SLO: 5s"
        )

    api_svg_mutating = ""
    api_svg_read = ""
    if api_latency.get("results"):
        mutating_iters = [r for r in api_latency["results"]
                          if r.get("category") == "mutating" and isinstance(r.get("iteration"), int)]
        if mutating_iters:
            values = [r.get("p99_latency_ms", 0) for r in mutating_iters]
            labels = [f"iter{r['iteration']}" for r in mutating_iters]
            api_svg_mutating = generate_bar_svg(
                values, labels, "API Mutating Calls p99 Latency",
                threshold=1000, threshold_label="SLO: 1s", bar_color="#2196F3"
            )

        read_iters = [r for r in api_latency["results"]
                      if r.get("category") == "read-only-resource" and isinstance(r.get("iteration"), int)]
        if read_iters:
            values = [r.get("p99_latency_ms", 0) for r in read_iters]
            labels = [f"iter{r['iteration']}" for r in read_iters]
            api_svg_read = generate_bar_svg(
                values, labels, "API Read-Only Calls p99 Latency",
                threshold=1000, threshold_label="SLO: 1s", bar_color="#00BCD4"
            )

    sched_svg = ""
    if micro.get("results"):
        sched_iters = [r for r in micro["results"]
                       if r.get("operation") == "scheduler_throughput" and isinstance(r.get("iteration"), int)]
        if sched_iters:
            values = [r.get("throughput_pods_per_sec", 0) for r in sched_iters]
            labels = [f"iter{r['iteration']}" for r in sched_iters]
            sched_svg = generate_bar_svg(
                values, labels, "Scheduler Throughput (pods/sec)",
                bar_color="#FF9800"
            )

    stress_svg = ""
    if stress.get("results"):
        values = [r.get("throughput_pods_per_sec", 0) for r in stress["results"]]
        labels = [f"{r.get('concurrency', '?')} pods" for r in stress["results"]]
        stress_svg = generate_bar_svg(
            values, labels, "Stress Test Throughput by Concurrency",
            bar_color="#9C27B0"
        )

    def status_icon(val):
        return "&#x2705;" if val else "&#x274C;"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kubernetes ARM64 Performance Benchmark Report</title>
<style>
body { font-family: 'Segoe UI', monospace; margin: 0; padding: 20px; background: #f0f2f5; color: #333; }
.container { max-width: 1100px; margin: 0 auto; }
.header { background: linear-gradient(135deg, #326CE5, #1a73e8); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .subtitle { font-size: 14px; opacity: 0.85; margin-top: 8px; }
.card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
.card h2 { margin: 0 0 12px 0; font-size: 18px; color: #1a73e8; border-bottom: 2px solid #e8eaed; padding-bottom: 8px; }
.metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.metric-card { background: #f8f9fa; border-radius: 6px; padding: 16px; text-align: center; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #333; }
.metric-card .label { font-size: 12px; color: #666; margin-top: 4px; }
.metric-card .slo { font-size: 11px; color: #888; margin-top: 2px; }
.metric-card.pass .value { color: #4CAF50; }
.metric-card.fail .value { color: #f44336; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th { background: #e8eaed; padding: 10px; text-align: left; font-size: 13px; }
td { padding: 10px; font-size: 13px; border-bottom: 1px solid #eee; }
.pass-cell { color: #4CAF50; font-weight: bold; }
.fail-cell { color: #f44336; font-weight: bold; }
.env-table td:first-child { font-weight: bold; width: 200px; color: #555; }
.chart-container { margin: 16px 0; }
.slo-ref { background: #fff3e0; padding: 12px; border-radius: 6px; margin-top: 16px; }
.slo-ref h3 { margin: 0; font-size: 14px; color: #e65100; }
.slo-ref ul { margin: 8px 0; font-size: 13px; }
.shunit2-section { background: #e8f5e9; padding: 16px; border-radius: 6px; margin-top: 16px; }
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Kubernetes ARM64 Performance Benchmark</h1>
<div class="subtitle">Version {version_info.get('software_version', 'unknown')} | {version_info.get('architecture', 'unknown')} | {data.get('timestamp', 'unknown')}</div>
</div>

<div class="card">
<h2>Environment Information</h2>
<table class="env-table">
<tr><td>Architecture</td><td>{version_info.get('architecture', 'N/A')}</td></tr>
<tr><td>CPU</td><td>{version_info.get('cpu_model', 'N/A')}</td></tr>
<tr><td>Cores</td><td>{version_info.get('cores', 'N/A')}</td></tr>
<tr><td>Memory</td><td>{version_info.get('memory_mb', 'N/A')} MB</td></tr>
<tr><td>OS</td><td>{version_info.get('os', 'N/A')}</td></tr>
<tr><td>Kernel</td><td>{version_info.get('kernel', 'N/A')}</td></tr>
<tr><td>Kubernetes Version</td><td>{version_info.get('software_version', 'N/A')}</td></tr>
<tr><td>Server Version</td><td>{version_info.get('server_version', 'N/A')}</td></tr>
<tr><td>Install Method</td><td>{version_info.get('install_method', 'N/A')} (kind)</td></tr>
<tr><td>Cluster</td><td>{version_info.get('cluster_name', 'N/A')} ({version_info.get('nodes_ready', 0)} nodes)</td></tr>
</table>
</div>

<div class="card">
<h2>Key Performance Metrics</h2>
<div class="metrics-grid">
<div class="metric-card {'pass' if summary.get('pod_startup_slo_met') else 'fail' if 'pod_startup_slo_met' in summary else ''}">
<div class="value">{summary.get('pod_startup_p99_ms', 0):.0f} ms</div>
<div class="label">Pod Startup p99</div>
<div class="slo">SLO: &lt;= 5000ms</div>
</div>
<div class="metric-card {'pass' if summary.get('api_mutating_slo_met') else 'fail' if 'api_mutating_slo_met' in summary else ''}">
<div class="value">{summary.get('api_mutating_p99_ms', 0):.0f} ms</div>
<div class="label">API Mutating p99</div>
<div class="slo">SLO: &lt;= 1000ms</div>
</div>
<div class="metric-card {'pass' if summary.get('api_read_resource_slo_met') else 'fail' if 'api_read_resource_slo_met' in summary else ''}">
<div class="value">{summary.get('api_read_resource_p99_ms', 0):.0f} ms</div>
<div class="label">API Read p99</div>
<div class="slo">SLO: &lt;= 1000ms</div>
</div>
<div class="metric-card {'pass' if summary.get('scheduler_throughput_slo_met') else 'fail' if 'scheduler_throughput_slo_met' in summary else ''}">
<div class="value">{summary.get('scheduler_throughput_pods_per_sec', 0):.1f}</div>
<div class="label">Scheduler Throughput</div>
<div class="slo">Threshold: &gt;= 100 pods/sec</div>
</div>
</div>
</div>

<div class="card">
<h2>Pod Startup Latency (Primary Benchmark)</h2>
<p>Measures time from pod creation to containers running &amp; ready. Kubernetes official SLO: p99 &lt;= 5 seconds.</p>
<div class="chart-container">{pod_startup_svg}</div>
{('<table><tr><th>Iteration</th><th>p50 (ms)</th><th>p90 (ms)</th><th>p95 (ms)</th><th>p99 (ms)</th><th>Success Rate</th><th>SLO Met</th></tr>' + ''.join(f'<tr><td>{r.get("iteration", "?")}</td><td>{r.get("p50_latency_ms", 0):.0f}</td><td>{r.get("p90_latency_ms", 0):.0f}</td><td>{r.get("p95_latency_ms", 0):.0f}</td><td>{r.get("p99_latency_ms", 0):.0f}</td><td>{r.get("success_rate", 0)}%</td><td class="{("pass" if r.get("p99_latency_ms", 0) <= 5000 else "fail")}-cell">{status_icon(r.get("p99_latency_ms", 0) <= 5000)}</td></tr>' for r in pod_startup.get("results", []) if isinstance(r.get("iteration"), int)) + '</table>') if pod_startup.get("results") else '<p>No data available</p>'}
</div>

<div class="card">
<h2>API Responsiveness (Secondary Benchmark)</h2>
<p>Measures latency of mutating and read-only API calls. SLO: mutating p99 &lt;= 1s, read-only (resource) p99 &lt;= 1s, read-only (namespace) p99 &lt;= 30s.</p>
<div class="chart-container">{api_svg_mutating}</div>
<div class="chart-container">{api_svg_read}</div>
</div>

<div class="card">
<h2>Micro Benchmarks</h2>
<div class="chart-container">{sched_svg}</div>
{('<table><tr><th>Operation</th><th>Key Metric</th><th>Value</th></tr>' + ''.join(f'<tr><td>{r.get("operation", "?")}</td><td>{"throughput_pods_per_sec" if r.get("operation") == "scheduler_throughput" else "avg_pod_create_ms" if r.get("operation") == "kubelet_lifecycle" else "namespace_list_latency_ms"}</td><td>{r.get("throughput_pods_per_sec", r.get("avg_pod_create_ms", r.get("namespace_list_latency_ms", "N/A")))}</td></tr>' for r in micro.get("results", [])) + '</table>') if micro.get("results") else '<p>No data available</p>'}
</div>

<div class="card">
<h2>Stress Test</h2>
<p>Measures cluster stability under increasing pod density.</p>
<div class="chart-container">{stress_svg}</div>
{('<table><tr><th>Concurrency</th><th>Pods Running</th><th>Startup Time</th><th>Throughput</th><th>Cluster Stable</th></tr>' + ''.join(f'<tr><td>{r.get("concurrency", "?")}</td><td>{r.get("pods_running", "?")}/{r.get("pods_requested", "?")}</td><td>{r.get("startup_time_seconds", 0):.1f}s</td><td>{r.get("throughput_pods_per_sec", 0):.1f} pods/s</td><td class="{("pass" if r.get("stable") else "fail")}-cell">{status_icon(r.get("stable"))}</td></tr>' for r in stress.get("results", [])) + '</table>') if stress.get("results") else '<p>No data available</p>'}
</div>

<div class="slo-ref">
<h3>Kubernetes Official Scalability SLOs (Reference)</h3>
<ul>
<li>Pod startup latency p99: &lt;= 5 seconds (excluding image pull time)</li>
<li>Mutating API call latency p99: &lt;= 1 second</li>
<li>Read-only API call (resource scope) p99: &lt;= 1 second</li>
<li>Read-only API call (namespace/cluster scope) p99: &lt;= 30 seconds</li>
</ul>
<p><small>Source: https://github.com/kubernetes/community/blob/master/sig-scalability/slos/slos.md</small></p>
</div>

<div class="shunit2-section">
<h2>shUnit2 Test Results</h2>
<p>Validation tests are executed via shUnit2. See <code>kubernetes_arm64_perf_test.sh</code> for 24 test functions covering all benchmark phases.</p>
<table>
<tr><th>Phase</th><th>Test Functions</th><th>Count</th></tr>
<tr><td>Phase 2: Verify</td><td>testArchitectureIsARM64, testKubectlIsInstalled, testKindIsInstalled, testKubernetesVersionMatches, testKubernetesClusterIsResponsive, testVersionInfoJsonExists, testVersionInfoHasArchitecture, testVersionInfoHasKubernetesVersion</td><td>8</td></tr>
<tr><td>Phase 3a: Pod Startup</td><td>testBenchmarkPodStartupProducesResults, testBenchmarkPodStartupHasRequiredFields, testBenchmarkPodStartupLatencyBelowSLO, testBenchmarkPodStartupP50LatencyAcceptable</td><td>4</td></tr>
<tr><td>Phase 3b: API Latency</td><td>testBenchmarkApiLatencyProducesResults, testBenchmarkApiLatencyHasRequiredFields, testBenchmarkApiLatencyMutatingBelowSLO, testBenchmarkApiLatencyReadOnlyBelowSLO</td><td>4</td></tr>
<tr><td>Phase 3c: Micro</td><td>testBenchmarkMicroProducesResults, testBenchmarkMicroAllOperationsCompleted, testBenchmarkMicroSchedulerThroughputAboveThreshold</td><td>3</td></tr>
<tr><td>Phase 3d: Stress</td><td>testBenchmarkStressProducesResults, testBenchmarkStressClusterStable</td><td>2</td></tr>
<tr><td>Phase 4: Results</td><td>testAggregatedResultsExist, testHtmlReportGenerated, testSummaryReportGenerated, testAggregatedResultsContainsAllBenchmarks</td><td>4</td></tr>
</table>
</div>
</div>
</body>
</html>"""

    output_file = os.path.join(results_dir, "benchmark_report.html")
    with open(output_file, 'w') as f:
        f.write(html)

    print(f"[HTML] Report saved to {output_file}")


if __name__ == "__main__":
    main()