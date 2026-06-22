#!/usr/bin/env python3
import json
import os
import argparse
import datetime

CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
.header { background: linear-gradient(135deg, #326CE5, #1a73e8); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }
.header h1 { margin: 0; font-size: 28px; }
.header .meta { font-size: 14px; color: #a0c4ff; margin-top: 8px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.section h2 { color: #326CE5; border-bottom: 2px solid #e8eaed; padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #34495e; margin-top: 15px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
th { background: #326CE5; color: white; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #ecf0f1; }
tr:hover { background: #e8f0fe; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin: 15px 0; }
.metric-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; text-align: center; }
.metric-card .label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
.metric-card .value { font-size: 24px; font-weight: bold; color: #326CE5; margin-top: 5px; }
.metric-card .unit { font-size: 11px; color: #95a5a6; }
.metric-card.pass .value { color: #4CAF50; }
.metric-card.fail .value { color: #f44336; }
.bar-chart { margin: 15px 0; }
.bar-row { display: flex; align-items: center; margin: 6px 0; }
.bar-label { width: 200px; font-size: 13px; text-align: right; padding-right: 10px; }
.bar-container { flex: 1; background: #ecf0f1; border-radius: 4px; height: 22px; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { font-size: 12px; color: #326CE5; margin-left: 8px; white-space: nowrap; }
.slo-ref { background: #fff3e0; padding: 12px; border-radius: 6px; margin-top: 16px; }
.slo-ref h3 { margin: 0; font-size: 14px; color: #e65100; }
.slo-ref ul { margin: 8px 0; font-size: 13px; }
.arm64-badge { background: #326CE5; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }
.shunit2-section { background: #e8f5e9; padding: 16px; border-radius: 6px; margin-top: 16px; }
.shunit2-section h2 { color: #2e7d32; }
</style>
"""


def make_bar_chart(title, items, max_val=None, color="#326CE5"):
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
    parser = argparse.ArgumentParser(description="Generate HTML report for Kubernetes ARM64 benchmark results")
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

    pod_startup = benchmarks.get("pod_startup", {})
    api_latency = benchmarks.get("api_latency", {})
    micro = benchmarks.get("micro", {})

    def status_icon(val):
        return "&#x2705;" if val else "&#x274C;"

    vi = env

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kubernetes ARM64 Performance Benchmark Report</title>{CSS}</head><body>

<div class="header">
    <h1>Kubernetes ARM64 Performance Benchmark Report <span class="arm64-badge">ARM64</span></h1>
    <div class="meta">Kubernetes {vi.get("software_version", "N/A")} | {vi.get("architecture", "N/A")} | {vi.get("nodes_ready", "N/A")} nodes | Cluster: {vi.get("cluster_name", "N/A")} | Generated {timestamp}</div>
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
<tr><td>Kubernetes Version</td><td>{vi.get("software_version", "N/A")}</td></tr>
<tr><td>Server Version</td><td>{vi.get("server_version", "N/A")}</td></tr>
<tr><td>kubectl Version</td><td>{vi.get("kubectl_version", "N/A")}</td></tr>
<tr><td>Cluster</td><td>{vi.get("cluster_name", "N/A")} ({vi.get("nodes_ready", "N/A")} nodes)</td></tr>
<tr><td>Install Method</td><td>{vi.get("install_method", "N/A")} (kind)</td></tr>
<tr><td>NEON/ASIMD</td><td>{vi.get("neon_asimd_available", "N/A")}</td></tr>
</table>
</div>
'''

    if summary:
        html += '<div class="metric-grid">'
        if "pod_startup_p99_ms" in summary:
            slo_met = summary.get("pod_startup_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">Pod Startup p99</div><div class="value">{summary['pod_startup_p99_ms']:.0f}</div><div class="unit">ms (SLO: &lt;= 5000ms)</div></div>'''
        if "api_mutating_p99_ms" in summary:
            slo_met = summary.get("api_mutating_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">API Mutating p99</div><div class="value">{summary['api_mutating_p99_ms']:.0f}</div><div class="unit">ms (SLO: &lt;= 1000ms)</div></div>'''
        if "api_read_resource_p99_ms" in summary:
            slo_met = summary.get("api_read_resource_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">API Read p99</div><div class="value">{summary['api_read_resource_p99_ms']:.0f}</div><div class="unit">ms (SLO: &lt;= 1000ms)</div></div>'''
        if "scheduler_throughput_pods_per_sec" in summary:
            slo_met = summary.get("scheduler_throughput_slo_met", False)
            cls = "pass" if slo_met else "fail"
            html += f'''<div class="metric-card {cls}"><div class="label">Scheduler Throughput</div><div class="value">{summary['scheduler_throughput_pods_per_sec']:.1f}</div><div class="unit">pods/sec (&gt;= 100)</div></div>'''
        html += '</div>'

    if pod_startup:
        results = pod_startup.get("results", [])
        iter_results = [r for r in results if isinstance(r.get("iteration"), int)]

        html += '<div class="section"><h2>Pod Startup Latency (Phase 3a)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{pod_startup.get("reference", "")}">Kubernetes SLO</a></p>'
        html += f'<p>{pod_startup.get("description", "")}</p>'

        if iter_results:
            p99_items = [(f"iter {r['iteration']}", r.get("p99_latency_ms", 0)) for r in iter_results]
            html += make_bar_chart("Pod Startup p99 Latency (ms)", p99_items, color="#326CE5")

            html += '<table><tr><th>Iteration</th><th>p50 (ms)</th><th>p90 (ms)</th><th>p95 (ms)</th><th>p99 (ms)</th><th>Success Rate</th><th>SLO Met</th></tr>'
            for r in iter_results:
                p99 = r.get("p99_latency_ms", 0)
                slo = p99 <= 5000
                cls = "pass" if slo else "fail"
                html += f'<tr><td>{r["iteration"]}</td><td>{r.get("p50_latency_ms", 0):.0f}</td><td>{r.get("p90_latency_ms", 0):.0f}</td><td>{r.get("p95_latency_ms", 0):.0f}</td><td>{p99:.0f}</td><td>{r.get("success_rate", 0)}%</td><td class="{cls}-cell">{status_icon(slo)}</td></tr>'
            html += '</table>'

        html += '</div>'

    if api_latency:
        results = api_latency.get("results", [])
        categories = {}
        for r in results:
            cat = r.get("category", "unknown")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r)

        html += '<div class="section"><h2>API Responsiveness (Phase 3b)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{api_latency.get("reference", "")}">Kubernetes SLO</a></p>'
        html += f'<p>{api_latency.get("description", "")}</p>'

        colors = {"mutating": "#326CE5", "mutating-delete": "#e53935", "read-only-resource": "#00BCD4", "read-only-namespace": "#4CAF50"}
        for cat, cat_results in categories.items():
            iter_results = [r for r in cat_results if isinstance(r.get("iteration"), int)]
            if iter_results:
                p99_items = [(f"iter {r['iteration']}", r.get("p99_latency_ms", 0)) for r in iter_results]
                html += make_bar_chart(f"API {cat} p99 Latency (ms)", p99_items, color=colors.get(cat, "#326CE5"))

                html += '<table><tr><th>Iteration</th><th>Category</th><th>Resource</th><th>Verb</th><th>p50 (ms)</th><th>p99 (ms)</th><th>Successful Calls</th></tr>'
                for r in iter_results:
                    html += f'<tr><td>{r["iteration"]}</td><td>{r.get("category", "")}</td><td>{r.get("resource", "")}</td><td>{r.get("verb", "")}</td><td>{r.get("p50_latency_ms", 0):.0f}</td><td>{r.get("p99_latency_ms", 0):.0f}</td><td>{r.get("calls_successful", 0)}/{r.get("calls_total", 20)}</td></tr>'
                html += '</table>'

        html += '</div>'

    if micro:
        results = micro.get("results", [])
        sched_results = [r for r in results if r.get("operation") == "scheduler_throughput" and isinstance(r.get("iteration"), int)]
        kubelet_result = [r for r in results if r.get("operation") == "kubelet_lifecycle"]
        etcd_result = [r for r in results if r.get("operation") == "control_plane_health"]

        html += '<div class="section"><h2>Micro Benchmarks (Phase 3c)</h2>'
        html += f'<p><strong>Reference:</strong> <a href="{micro.get("reference", "")}">Kubernetes perf-tests</a></p>'

        if sched_results:
            tp_items = [(f"iter {r['iteration']}", r.get("throughput_pods_per_sec", 0)) for r in sched_results]
            html += make_bar_chart("Scheduler Throughput (pods/sec)", tp_items, color="#FF9800")
            html += '<table><tr><th>Iteration</th><th>Throughput (pods/sec)</th><th>Pods Scheduled</th><th>Time (s)</th><th>All Ready</th></tr>'
            for r in sched_results:
                html += f'<tr><td>{r["iteration"]}</td><td>{r.get("throughput_pods_per_sec", 0):.2f}</td><td>{r.get("pods_scheduled", 0)}</td><td>{r.get("time_seconds", 0)}</td><td>{status_icon(r.get("all_ready", False))}</td></tr>'
            html += '</table>'

        if kubelet_result:
            r = kubelet_result[0]
            html += '<h3>Kubelet Pod Lifecycle</h3>'
            html += f'<div class="metric-grid">'
            html += f'''<div class="metric-card"><div class="label">Avg Create</div><div class="value">{r.get("avg_pod_create_ms", 0):.0f}</div><div class="unit">ms</div></div>'''
            html += f'''<div class="metric-card"><div class="label">Avg Delete</div><div class="value">{r.get("avg_pod_delete_ms", 0):.0f}</div><div class="unit">ms</div></div>'''
            html += '</div>'

        if etcd_result:
            r = etcd_result[0]
            html += '<h3>Control Plane Health</h3>'
            html += f'<div class="metric-grid">'
            html += f'''<div class="metric-card {'pass' if r.get('api_healthz_ok') else 'fail'}"><div class="label">healthz</div><div class="value">{status_icon(r.get('api_healthz_ok'))}</div><div class="unit">{r.get('namespace_list_latency_ms', 0):.0f} ms list latency</div></div>'''
            html += f'''<div class="metric-card {'pass' if r.get('api_livez_ok') else 'fail'}"><div class="label">livez</div><div class="value">{status_icon(r.get('api_livez_ok'))}</div><div class="unit">{r.get('node_info_latency_ms', 0):.0f} ms node info</div></div>'''
            html += '</div>'

        html += '</div>'

    html += '''
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

<div class="section">
<h2>ARM64 Optimization Highlights</h2>
<table>
<tr><th>Feature</th><th>Impact</th><th>Status</th></tr>
<tr><td>ARM64 NEON/ASIMD</td><td>Vector operations for crypto/hash</td><td>''' + ("Available" if vi.get("neon_asimd_available", "0") != "0" else "Not detected") + '''</td></tr>
<tr><td>Kind ARM64 node image</td><td>Native ARM64 Kubernetes runtime</td><td>kindest/node:v''' + vi.get("software_version", "N/A") + '''</td></tr>
<tr><td>Go compiler ARM64</td><td>Kubernetes components compiled for arm64</td><td>Native binary</td></tr>
<tr><td>Container runtime</td><td>Docker/containerd ARM64 support</td><td>''' + vi.get("install_method", "kind") + '''</td></tr>
</table></div>

<div class="shunit2-section">
<h2>shUnit2 Test Results</h2>
<p>Validation tests are executed via shUnit2. See <code>kubernetes_test.sh</code> for test functions covering all benchmark phases.</p>
<table>
<tr><th>Phase</th><th>Test Functions</th><th>Count</th></tr>
<tr><td>Phase 2: Verify</td><td>testArchitectureIsARM64, testSoftwareIsInstalled, testSoftwareVersionMatches, testVersionInfoJsonExists, testClusterIsResponsive</td><td>5</td></tr>
<tr><td>Phase 3a: Pod Startup</td><td>testBenchmarkPodStartupProducesResults, testBenchmarkPodStartupHasRequiredFields, testBenchmarkPodStartupLatencyBelowSLO, testBenchmarkPodStartupP50LatencyAcceptable</td><td>4</td></tr>
<tr><td>Phase 3b: API Latency</td><td>testBenchmarkApiLatencyProducesResults, testBenchmarkApiLatencyHasRequiredFields, testBenchmarkApiLatencyMutatingBelowSLO, testBenchmarkApiLatencyReadOnlyBelowSLO</td><td>4</td></tr>
<tr><td>Phase 3c: Micro</td><td>testBenchmarkMicroProducesResults, testBenchmarkMicroAllOperationsCompleted, testBenchmarkMicroSchedulerThroughputAboveThreshold</td><td>3</td></tr>
<tr><td>Phase 4: Results</td><td>testAggregatedResultsExist, testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated, testAggregatedResultsContainsAllBenchmarks</td><td>5</td></tr>
</table>
</div>
</body></html>'''

    with open(args.output, 'w') as f:
        f.write(html)
    print(f"[HTML] Report saved to {args.output}")


if __name__ == "__main__":
    main()