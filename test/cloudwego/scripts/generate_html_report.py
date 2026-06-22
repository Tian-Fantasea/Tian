#!/usr/bin/env python3
import argparse
import json
import math
import os
import sys
import time


def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def fmt_val(value, unit="", precision=2):
    if value is None or value == 0:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f} {unit}"
    if isinstance(value, int):
        return f"{value} {unit}"
    return f"{value}"


def make_bar_chart(items, chart_id, max_val=None, color="#4A90D9"):
    if not items:
        return "<p>No data available</p>"
    if max_val is None:
        max_val = max([v for _, v in items], default=1)
    if max_val == 0:
        max_val = 1
    rows = []
    for label, value in items:
        pct = (value / max_val * 100) if max_val > 0 else 0
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{label}</span>'
            f'<div class="bar-fill" style="width:{pct:.1f}%;background:{color};">'
            f'<span class="bar-val">{fmt_val(value)}</span></div></div>'
        )
    return f'<div id="{chart_id}" class="bar-chart">{"".join(rows)}</div>'


def main():
    parser = argparse.ArgumentParser(description="Generate HTML report for CloudWeGo benchmarks")
    parser.add_argument("--input", required=True, help="Path to results.json")
    parser.add_argument("--output", required=True, help="Path to results.html")
    args = parser.parse_args()

    data = load_or_create_json(args.input)
    if not data:
        with open(args.output, "w") as f:
            f.write("<html><body><h1>Error: No results.json found</h1></body></html>")
        return 1

    vi = data.get("version_info", {})
    timestamp = data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    version = data.get("version", "unknown")

    cwg_dark = "#1a1a2e"
    cwg_blue = "#0f3460"
    cwg_primary = "#4A90D9"
    cwg_red = "#E74C3C"
    cwg_green = "#27AE60"
    cwg_orange = "#F39C12"
    cwg_gray = "#7f8c8d"

    kitex = data.get("kitex_benchmark", {})
    hertz = data.get("hertz_benchmark", {})
    micro = data.get("micro_benchmark", {})
    stress = data.get("stress_benchmark", {})

    kitex_r = kitex.get("results", []) if isinstance(kitex, dict) else []
    hertz_r = hertz.get("results", []) if isinstance(hertz, dict) else []
    micro_r = micro.get("results", []) if isinstance(micro, dict) else []
    stress_r = stress.get("results", []) if isinstance(stress, dict) else []

    kitex_qps_max = max((r.get("qps", 0) for r in kitex_r if "qps" in r), default=0)
    hertz_qps_max = max((r.get("qps", 0) for r in hertz_r if "qps" in r), default=0)

    env_fields = [
        ("Architecture", vi.get("architecture", "unknown")),
        ("CPU Model", vi.get("cpu_model", "unknown")),
        ("CPU Cores", str(vi.get("cores", "unknown"))),
        ("Memory", fmt_val(vi.get("memory_mb", 0), "MB", 0)),
        ("Operating System", vi.get("os", "unknown")),
        ("Kernel", vi.get("kernel", "unknown")),
        ("Go Version", vi.get("go_version", "unknown")),
        ("Kitex Version", vi.get("kitex_version", "unknown")),
        ("Hertz Version", vi.get("hertz_version", "unknown")),
        ("wrk Available", vi.get("wrk_version", "unknown")),
    ]
    env_rows = ""
    for label, value in env_fields:
        env_rows += f"<tr><td class='env-label'>{label}</td><td class='env-value'>{value}</td></tr>\n"

    card_items = []
    if kitex_qps_max > 0:
        card_items.append(("Kitex Peak QPS", f"{kitex_qps_max:,.0f}", "requests/sec"))
    if hertz_qps_max > 0:
        card_items.append(("Hertz Peak QPS", f"{hertz_qps_max:,.0f}", "requests/sec"))
    card_items.append(("Micro Benchmarks", str(len(micro_r)), "operations tested"))
    if stress_r:
        max_conc = max((r.get("concurrency", 0) for r in stress_r), default=0)
        card_items.append(("Stress Max Conc", str(max_conc), "concurrent connections"))

    metrics_cards = ""
    card_colors = [cwg_primary, cwg_red, cwg_green, cwg_orange]
    for i, (name, value, unit) in enumerate(card_items):
        color = card_colors[i % len(card_colors)]
        metrics_cards += (
            f'<div class="metric-card" style="border-top:3px solid {color};">'
            f'<div class="metric-name">{name}</div>'
            f'<div class="metric-value">{value}</div>'
            f'<div class="metric-unit">{unit}</div>'
            f'</div>\n'
        )

    kitex_section = ""
    if isinstance(kitex, dict) and kitex_r:
        kitex_conc_qps = [(str(r.get("concurrency", "?")), r.get("qps", 0)) for r in kitex_r if "concurrency" in r and "qps" in r]
        kitex_charts = make_bar_chart(kitex_conc_qps, "kitex_qps", color=cwg_primary)
        kitex_rows = ""
        for r in kitex_r:
            if "concurrency" in r:
                kitex_rows += (
                    f"<tr><td>{r.get('concurrency', 'N/A')}</td>"
                    f"<td>{r.get('qps', 0):,.0f}</td>"
                    f"<td>{r.get('avg_latency_ms', 0):.2f}</td>"
                    f"<td>{r.get('p99_latency_ms', 0):.2f}</td>"
                    f"<td>{r.get('p999_latency_ms', 0):.2f}</td></tr>\n"
                )
            elif "operation" in r:
                kitex_rows += (
                    f"<tr><td>{r.get('operation', 'N/A')}</td>"
                    f"<td>{r.get('ops_per_sec', 0):,.0f}</td>"
                    f"<td>{r.get('ns_per_op', 0):.1f}</td>"
                    f"<td>-</td><td>-</td></tr>\n"
                )
        kitex_section = (
            f'<section id="kitex"><h2>Kitex RPC Benchmark (Primary)</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/cloudwego/kitex-benchmark">kitex-benchmark</a></p>'
            f'<p>{kitex.get("description", "")}</p>'
            f'{kitex_charts}'
            f'<table><tr><th>Concurrency</th><th>QPS</th><th>Avg Lat (ms)</th><th>P99 (ms)</th><th>P999 (ms)</th></tr>'
            f'{kitex_rows}</table></section>'
        )

    hertz_section = ""
    if isinstance(hertz, dict) and hertz_r:
        hertz_conc_qps = [(str(r.get("concurrency", "?")), r.get("qps", 0)) for r in hertz_r if "concurrency" in r and "qps" in r]
        hertz_charts = make_bar_chart(hertz_conc_qps, "hertz_qps", color=cwg_red)
        hertz_rows = ""
        for r in hertz_r:
            if "concurrency" in r:
                hertz_rows += (
                    f"<tr><td>{r.get('concurrency', 'N/A')}</td>"
                    f"<td>{r.get('qps', 0):,.0f}</td>"
                    f"<td>{r.get('avg_latency_ms', 0):.2f}</td>"
                    f"<td>{r.get('p50_latency_ms', 'N/A')}</td>"
                    f"<td>{r.get('p99_latency_ms', 'N/A')}</td></tr>\n"
                )
            elif "operation" in r:
                hertz_rows += (
                    f"<tr><td>{r.get('operation', 'N/A')}</td>"
                    f"<td>{r.get('ops_per_sec', 0):,.0f}</td>"
                    f"<td>{r.get('ns_per_op', 0):.1f}</td>"
                    f"<td>-</td><td>-</td></tr>\n"
                )
        hertz_section = (
            f'<section id="hertz"><h2>Hertz HTTP Benchmark (Secondary)</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/cloudwego/hertz-benchmark">hertz-benchmark</a></p>'
            f'<p>{hertz.get("description", "")}</p>'
            f'{hertz_charts}'
            f'<table><tr><th>Concurrency</th><th>QPS</th><th>Avg Lat (ms)</th><th>P50 (ms)</th><th>P99 (ms)</th></tr>'
            f'{hertz_rows}</table></section>'
        )

    micro_section = ""
    if isinstance(micro, dict) and micro_r:
        micro_by_component = {}
        for r in micro_r:
            comp = r.get("component", "unknown")
            if comp not in micro_by_component:
                micro_by_component[comp] = []
            micro_by_component[comp].append(r)

        micro_items = []
        for comp, results in sorted(micro_by_component.items()):
            for r in results:
                op = r.get("operation", comp)
                ops = r.get("ops_per_sec", 0)
                if ops > 0:
                    micro_items.append((op[:30], ops))

        micro_charts = make_bar_chart(micro_items[:15], "micro_ops", color=cwg_green)
        micro_rows = ""
        for r in micro_r[:25]:
            micro_rows += (
                f"<tr><td>{r.get('component', 'N/A')}</td>"
                f"<td>{r.get('operation', 'N/A')}</td>"
                f"<td>{r.get('ns_per_op', 0):.1f}</td>"
                f"<td>{r.get('ops_per_sec', 0):,.0f}</td>"
                f"<td>{r.get('allocs_per_op', 'N/A')}</td>"
                f"<td>{r.get('bytes_per_op', 'N/A')}</td></tr>\n"
            )
        micro_section = (
            f'<section id="micro"><h2>Micro Benchmarks</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/cloudwego">CloudWeGo</a></p>'
            f'<p>{micro.get("description", "")}</p>'
            f'{micro_charts}'
            f'<table><tr><th>Component</th><th>Operation</th><th>ns/op</th><th>ops/sec</th><th>Allocs/op</th><th>B/op</th></tr>'
            f'{micro_rows}</table></section>'
        )

    stress_section = ""
    if isinstance(stress, dict) and stress_r:
        stress_conc_qps = [(str(r.get("concurrency", "?")), r.get("qps", 0)) for r in stress_r if "concurrency" in r and "qps" in r]
        stress_charts = make_bar_chart(stress_conc_qps, "stress_qps", color=cwg_orange)
        stress_rows = ""
        for r in stress_r:
            if "concurrency" in r:
                stress_rows += (
                    f"<tr><td>{r.get('concurrency', 'N/A')}</td>"
                    f"<td>{r.get('qps', 0):,.0f}</td>"
                    f"<td>{r.get('avg_latency_ms', 0):.2f}</td>"
                    f"<td>{r.get('p99_latency_ms', 'N/A')}</td></tr>\n"
                )
        stress_section = (
            f'<section id="stress"><h2>Stress Benchmark</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/cloudwego/kitex-benchmark">kitex-benchmark</a></p>'
            f'<p>{stress.get("description", "")}</p>'
            f'{stress_charts}'
            f'<table><tr><th>Concurrency</th><th>QPS</th><th>Avg Lat (ms)</th><th>P99 (ms)</th></tr>'
            f'{stress_rows}</table></section>'
        )

    arm64_rows = ""
    arm64_items = [
        ("ARM64 Architecture", str(vi.get("architecture", "unknown"))),
        ("Go ARM64 Build", str(vi.get("go_version", "unknown"))),
        ("taskset Available", str(vi.get("taskset_available", "unknown"))),
    ]
    for label, value in arm64_items:
        if value.lower() in ("aarch64", "arm64", "true", "yes", "1"):
            status = '<span class="status-pass">YES</span>'
        elif value.lower() in ("false", "no", "0"):
            status = '<span class="status-fail">NO</span>'
        else:
            status = f'<span class="status-unknown">{value}</span>'
        arm64_rows += f"<tr><td>{label}</td><td>{status}</td></tr>\n"

    arm64_section = (
        f'<section id="arm64"><h2>ARM64 Optimization Highlights</h2>'
        f'<table class="arm64-table"><tr><th>Feature</th><th>Status</th></tr>{arm64_rows}</table></section>'
    )

    shunit2_rows = ""
    test_categories = [
        ("Architecture Validation", "testArchitectureIsARM64"),
        ("Go Installation", "testGoIsInstalled, testGoVersionIsAcceptable"),
        ("Tool Verification", "testWrkIsInstalled"),
        ("Benchmark Repos", "testKitexBenchRepoExists, testHertzBenchRepoExists"),
        ("Version Info", "testResultsJsonHasVersionInfo, testResultsJsonHasArchitecture, testResultsJsonHasSoftwareVersion"),
        ("Kitex Benchmark", "testBenchmarkKitexInResultsJson, testBenchmarkKitexHasRequiredFields"),
        ("Hertz Benchmark", "testBenchmarkHertzInResultsJson"),
        ("Micro Benchmark", "testBenchmarkMicroInResultsJson"),
        ("Results Validation", "testResultsJsonExists, testResultsJsonContainsAllBenchmarks"),
        ("Report Generation", "testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated"),
    ]
    for cat, tests in test_categories:
        shunit2_rows += f"<tr><td>{cat}</td><td>{tests}</td></tr>\n"

    threshold_items = [
        "Kitex Thrift QPS &ge; 50,000 at conc=100 on ARM64",
        "Hertz HTTP QPS &ge; 30,000 at conc=100 on ARM64",
        "Kitex P99 latency &le; 5ms at conc=100 on ARM64",
        "Hertz P99 latency &le; 3ms at conc=100 on ARM64",
        "Sonic JSON &ge; 50MB/s serialization on ARM64",
        "Netpoll throughput &ge; go net on ARM64",
    ]
    threshold_rows = ""
    for item in threshold_items:
        threshold_rows += f"<li>{item}</li>\n"

    html = (
        f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CloudWeGo ARM64 Performance Benchmark Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #f5f5f7; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  header {{ background: linear-gradient(135deg, {cwg_dark}, {cwg_blue}); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header .subtitle {{ font-size: 14px; color: #a0c4ff; }}
  header .version {{ font-size: 16px; margin-top: 4px; }}
  .env-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: white; border-radius: 8px; overflow: hidden; }}
  .env-table td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
  .env-label {{ width: 30%; font-weight: 600; color: {cwg_blue}; background: #fafafa; }}
  .env-value {{ width: 70%; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }}
  .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; }}
  .metric-name {{ font-size: 12px; color: {cwg_gray}; margin-bottom: 6px; text-transform: uppercase; }}
  .metric-value {{ font-size: 20px; font-weight: 700; color: #333; }}
  .metric-unit {{ font-size: 11px; color: {cwg_gray}; }}
  section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px; }}
  section h2 {{ color: {cwg_blue}; border-bottom: 2px solid {cwg_primary}; padding-bottom: 8px; margin-bottom: 15px; }}
  section h3 {{ color: {cwg_blue}; margin: 15px 0 10px; }}
  .benchmark-ref {{ font-size: 13px; color: {cwg_gray}; margin-bottom: 15px; }}
  .benchmark-ref a {{ color: #4285f4; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 20px; }}
  th {{ background: {cwg_blue}; color: white; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
  .bar-chart {{ margin: 15px 0; }}
  .bar-row {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 150px; font-size: 13px; text-align: right; padding-right: 10px; }}
  .bar-fill {{ height: 22px; border-radius: 3px; display: inline-block; min-width: 2px; }}
  .bar-val {{ font-size: 12px; padding-left: 6px; color: white; }}
  .status-pass {{ background: {cwg_green}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-fail {{ background: {cwg_red}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-unknown {{ background: {cwg_gray}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .arm64-table {{ border: 2px solid {cwg_primary}; }}
  .arm64-table th {{ background: {cwg_blue}; }}
  .threshold {{ background: #fff8e1; border-radius: 6px; padding: 15px; margin: 10px 0; }}
  .threshold h3 {{ color: #f57f17; }}
  .threshold ul {{ list-style: none; padding: 0; }}
  .threshold li {{ padding: 4px 0; font-size: 13px; }}
  footer {{ text-align: center; padding: 20px; color: {cwg_gray}; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>CloudWeGo ARM64 Performance Benchmark</h1>
    <div class="subtitle">Kitex RPC + Hertz HTTP + Netpoll + Sonic JSON - High-Performance Microservice Frameworks</div>
    <div class="version">{version} | {timestamp}</div>
  </header>

  <section id="environment">
    <h2>Environment Information</h2>
    <table class="env-table">
      {env_rows}
    </table>
  </section>

  <section id="key-metrics">
    <h2>Key Performance Metrics</h2>
    <div class="metrics-grid">
      {metrics_cards}
    </div>
  </section>

  {kitex_section}

  {hertz_section}

  {micro_section}

  {stress_section}

  {arm64_section}

  <div class="threshold">
    <h3>ARM64 Threshold Reference</h3>
    <ul>
      {threshold_rows}
    </ul>
  </div>

  <section id="shunit2">
    <h2>shUnit2 Test Validation</h2>
    <p class="benchmark-ref">Automated validation via shUnit2 test suite with ARM64 assertions</p>
    <p>See <code>cloudwego_test.sh</code> for full test definitions</p>
    <table>
      <tr><th>Test Category</th><th>Tests</th></tr>
      {shunit2_rows}
    </table>
  </section>

  <footer>
    Generated by CloudWeGo ARM64 Performance Benchmark Workflow | {timestamp}
  </footer>
</div>
</body>
</html>'''
    )

    with open(args.output, "w") as f:
        f.write(html)

    print(f"[HTML] Report saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
