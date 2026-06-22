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


def make_bar_chart(items, chart_id, max_val=None, color="#E76F00"):
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
    parser = argparse.ArgumentParser(description="Generate HTML report for OpenJDK benchmarks")
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

    ojdk_orange = "#E76F00"
    ojdk_blue = "#5382A1"
    ojdk_dark = "#1a1a2e"
    ojdk_red = "#E74C3C"
    ojdk_green = "#27AE60"
    ojdk_gray = "#7f8c8d"
    ojdk_primary = "#E76F00"

    renaissance = data.get("renaissance_benchmark", {})
    dacapo = data.get("dacapo_benchmark", {})
    micro = data.get("micro_benchmark", {})

    ren_results = renaissance.get("results", {}) if isinstance(renaissance, dict) else {}
    dac_results = dacapo.get("results", {}) if isinstance(dacapo, dict) else {}
    mic_results = micro.get("results", {}) if isinstance(micro, dict) else {}

    env_fields = [
        ("Architecture", vi.get("architecture", "unknown")),
        ("CPU Model", vi.get("cpu_model", "unknown")),
        ("CPU Cores", str(vi.get("cores", "unknown"))),
        ("Memory", fmt_val(vi.get("memory_mb", 0), "MB", 0)),
        ("Operating System", vi.get("os", "unknown")),
        ("Kernel", vi.get("kernel", "unknown")),
        ("OpenJDK Version", vi.get("openjdk_version", "unknown")),
        ("JVM Name", vi.get("jvm_name", "unknown")),
        ("JVM Vendor", vi.get("jvm_vendor", "unknown")),
        ("Default GC", vi.get("gc_default", "unknown")),
        ("JIT Compiler", vi.get("jit_compiler", "unknown")),
    ]
    env_rows = ""
    for label, value in env_fields:
        env_rows += f"<tr><td class='env-label'>{label}</td><td class='env-value'>{value}</td></tr>\n"

    card_items = []
    ren_elapsed_min = None
    if ren_results:
        elapsed_vals = [v.get("avg_total_ms", 0) for v in ren_results.values() if isinstance(v, dict) and v.get("avg_total_ms", 0) > 0]
        if elapsed_vals:
            ren_elapsed_min = min(elapsed_vals)
            card_items.append(("Renaissance Min", f"{ren_elapsed_min:.1f}", "ms elapsed"))

    dac_throughput_max = None
    if dac_results:
        tps_vals = [v.get("avg_throughput_ops_per_sec", 0) for v in dac_results.values() if isinstance(v, dict) and v.get("avg_throughput_ops_per_sec", 0) > 0]
        if tps_vals:
            dac_throughput_max = max(tps_vals)
            card_items.append(("DaCapo Peak TPS", f"{dac_throughput_max:.1f}", "ops/sec"))

    if mic_results:
        fastest_ops = None
        for v in mic_results.values():
            if isinstance(v, dict):
                ops = v.get("avg_ops_per_sec", 0)
                if ops > 0 and (fastest_ops is None or ops > fastest_ops):
                    fastest_ops = ops
        if fastest_ops:
            card_items.append(("Micro Peak ops/s", f"{fastest_ops:.0f}", "ops/sec"))
        card_items.append(("Micro Benchmarks", str(len(mic_results)), "tests completed"))

    metrics_cards = ""
    card_colors = [ojdk_primary, ojdk_red, ojdk_green, ojdk_blue]
    for i, (name, value, unit) in enumerate(card_items):
        color = card_colors[i % len(card_colors)]
        metrics_cards += (
            f'<div class="metric-card" style="border-top:3px solid {color};">'
            f'<div class="metric-name">{name}</div>'
            f'<div class="metric-value">{value}</div>'
            f'<div class="metric-unit">{unit}</div>'
            f'</div>\n'
        )

    renaissance_section = ""
    if isinstance(renaissance, dict) and ren_results:
        ren_bar_items = [(k[:15], v.get("avg_total_ms", 0)) for k, v in ren_results.items() if isinstance(v, dict) and v.get("avg_total_ms", 0) > 0]
        ren_charts = make_bar_chart(ren_bar_items, "renaissance_elapsed", color=ojdk_primary)
        ren_rows = ""
        for bench_name, res in ren_results.items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                elapsed = res.get("avg_total_ms", "N/A")
                errs = res.get("errors", 0)
                status = '<span class="status-pass">OK</span>' if errs == 0 else f'<span class="status-fail">{errs} errors</span>'
                ren_rows += (
                    f"<tr><td>{bench_name}</td>"
                    f"<td>{desc[:50]}</td>"
                    f"<td>{fmt_val(elapsed, 'ms')}</td>"
                    f"<td>{status}</td></tr>\n"
                )
        renaissance_section = (
            f'<section id="renaissance"><h2>Renaissance Benchmark (Primary)</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://renaissance-benchmarks.github.io/">Renaissance Benchmark Suite</a> - '
            f'Modern JVM workloads (actors, futures, STM, reactive streams)</p>'
            f'<p>{renaissance.get("description", "")}</p>'
            f'{ren_charts}'
            f'<table><tr><th>Benchmark</th><th>Description</th><th>Avg Elapsed (ms)</th><th>Status</th></tr>'
            f'{ren_rows}</table></section>'
        )

    dacapo_section = ""
    if isinstance(dacapo, dict) and dac_results:
        dac_bar_items = [(k[:15], v.get("avg_throughput_ops_per_sec", 0)) for k, v in dac_results.items() if isinstance(v, dict) and v.get("avg_throughput_ops_per_sec", 0) > 0]
        dac_charts = make_bar_chart(dac_bar_items, "dacapo_throughput", color=ojdk_blue)
        dac_rows = ""
        for bench_name, res in dac_results.items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                elapsed = res.get("avg_elapsed_ms", "N/A")
                throughput = res.get("avg_throughput_ops_per_sec", "N/A")
                errs = res.get("errors", 0)
                status = '<span class="status-pass">OK</span>' if errs == 0 else f'<span class="status-fail">{errs} errors</span>'
                dac_rows += (
                    f"<tr><td>{bench_name}</td>"
                    f"<td>{desc[:50]}</td>"
                    f"<td>{fmt_val(elapsed, 'ms')}</td>"
                    f"<td>{fmt_val(throughput, 'ops/s')}</td>"
                    f"<td>{status}</td></tr>\n"
                )
        dacapo_section = (
            f'<section id="dacapo"><h2>DaCapo Benchmark (Secondary)</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://dacapobench.sourceforge.net/">DaCapo Benchmark Suite</a> - '
            f'Classic Java workloads (database, search, parsing, ray tracing)</p>'
            f'<p>{dacapo.get("description", "")}</p>'
            f'{dac_charts}'
            f'<table><tr><th>Benchmark</th><th>Description</th><th>Avg Elapsed (ms)</th><th>Throughput (ops/s)</th><th>Status</th></tr>'
            f'{dac_rows}</table></section>'
        )

    micro_section = ""
    if isinstance(micro, dict) and mic_results:
        mic_bar_items = [(k[:20], v.get("avg_ops_per_sec", 0)) for k, v in mic_results.items() if isinstance(v, dict) and v.get("avg_ops_per_sec", 0) > 0]
        mic_charts = make_bar_chart(mic_bar_items, "micro_ops", color=ojdk_green)
        mic_rows = ""
        for bench_name, res in mic_results.items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                avg_ns = res.get("avg_avg_ns", "N/A")
                ops = res.get("avg_ops_per_sec", "N/A")
                mic_rows += (
                    f"<tr><td>{bench_name}</td>"
                    f"<td>{desc[:60]}</td>"
                    f"<td>{fmt_val(avg_ns, 'ns')}</td>"
                    f"<td>{fmt_val(ops, 'ops/s')}</td></tr>\n"
                )
        micro_section = (
            f'<section id="micro"><h2>JVM Micro Benchmarks</h2>'
            f'<p class="benchmark-ref">Reference: Custom micro benchmark suite (String, Array, HashMap, Math, Thread, Allocation)</p>'
            f'<p>{micro.get("description", "")}</p>'
            f'{mic_charts}'
            f'<table><tr><th>Benchmark</th><th>Description</th><th>Avg ns/op</th><th>ops/sec</th></tr>'
            f'{mic_rows}</table></section>'
        )

    arm64_rows = ""
    arm64_items = [
        ("ARM64 Architecture", str(vi.get("architecture", "unknown"))),
        ("HotSpot JIT Available", str(vi.get("jit_compiler", "unknown"))),
        ("Default GC", str(vi.get("gc_default", "unknown"))),
    ]
    for label, value in arm64_items:
        if value.lower() in ("aarch64", "arm64"):
            status = '<span class="status-pass">YES</span>'
        elif "HotSpot" in value or "G1" in value:
            status = '<span class="status-pass">YES</span>'
        elif value.lower() in ("unknown", "none"):
            status = '<span class="status-unknown">UNKNOWN</span>'
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
        ("Java Installation", "testJavaIsInstalled, testJavacIsInstalled"),
        ("OpenJDK Verification", "testOpenjdkIsInstalled, testJvmIsHotspot"),
        ("Version Info", "testResultsJsonHasVersionInfo, testResultsJsonHasArchitecture, testResultsJsonHasSoftwareVersion, testResultsJsonHasJvmName, testResultsJsonHasGcDefault"),
        ("Renaissance Benchmark", "testBenchmarkRenaissanceInResultsJson, testBenchmarkRenaissanceHasRequiredFields"),
        ("DaCapo Benchmark", "testBenchmarkDacapoInResultsJson, testBenchmarkDacapoHasRequiredFields"),
        ("Micro Benchmark", "testBenchmarkMicroInResultsJson"),
        ("Results Validation", "testResultsJsonExists, testResultsJsonContainsAllBenchmarks"),
        ("Report Generation", "testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated"),
    ]
    for cat, tests in test_categories:
        shunit2_rows += f"<tr><td>{cat}</td><td>{tests}</td></tr>\n"

    threshold_items = [
        "Renaissance akka-uct elapsed &le; 5s on ARM64",
        "Renaissance scala-kmeans elapsed &le; 10s on ARM64",
        "DaCapo h2 elapsed &le; 500ms on ARM64",
        "DaCapo lusearch-fix elapsed &le; 200ms on ARM64",
        "StringBuilder concat avg_ns &le; 100,000 on ARM64",
        "Math operations avg_ns &le; 50,000,000 on ARM64",
        "HashMap ops avg_ns &le; 10,000,000 on ARM64",
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
<title>OpenJDK ARM64 Performance Benchmark Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #f5f5f7; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  header {{ background: linear-gradient(135deg, {ojdk_dark}, #2c3e50); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header .subtitle {{ font-size: 14px; color: #ffcc80; }}
  header .version {{ font-size: 16px; margin-top: 4px; }}
  .env-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: white; border-radius: 8px; overflow: hidden; }}
  .env-table td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
  .env-label {{ width: 30%; font-weight: 600; color: {ojdk_blue}; background: #fafafa; }}
  .env-value {{ width: 70%; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }}
  .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; }}
  .metric-name {{ font-size: 12px; color: {ojdk_gray}; margin-bottom: 6px; text-transform: uppercase; }}
  .metric-value {{ font-size: 20px; font-weight: 700; color: #333; }}
  .metric-unit {{ font-size: 11px; color: {ojdk_gray}; }}
  section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px; }}
  section h2 {{ color: {ojdk_blue}; border-bottom: 2px solid {ojdk_primary}; padding-bottom: 8px; margin-bottom: 15px; }}
  section h3 {{ color: {ojdk_blue}; margin: 15px 0 10px; }}
  .benchmark-ref {{ font-size: 13px; color: {ojdk_gray}; margin-bottom: 15px; }}
  .benchmark-ref a {{ color: {ojdk_blue}; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 20px; }}
  th {{ background: {ojdk_blue}; color: white; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
  .bar-chart {{ margin: 15px 0; }}
  .bar-row {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 150px; font-size: 13px; text-align: right; padding-right: 10px; }}
  .bar-fill {{ height: 22px; border-radius: 3px; display: inline-block; min-width: 2px; }}
  .bar-val {{ font-size: 12px; padding-left: 6px; color: white; }}
  .status-pass {{ background: {ojdk_green}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-fail {{ background: {ojdk_red}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-unknown {{ background: {ojdk_gray}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .arm64-table {{ border: 2px solid {ojdk_primary}; }}
  .arm64-table th {{ background: {ojdk_blue}; }}
  .threshold {{ background: #fff8e1; border-radius: 6px; padding: 15px; margin: 10px 0; }}
  .threshold h3 {{ color: #f57f17; }}
  .threshold ul {{ list-style: none; padding: 0; }}
  .threshold li {{ padding: 4px 0; font-size: 13px; }}
  footer {{ text-align: center; padding: 20px; color: {ojdk_gray}; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>OpenJDK ARM64 Performance Benchmark</h1>
    <div class="subtitle">Renaissance + DaCapo + JVM Micro Benchmarks - High-Performance Java Runtime</div>
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

  {renaissance_section}

  {dacapo_section}

  {micro_section}

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
    <p>See <code>openjdk_test.sh</code> for full test definitions</p>
    <table>
      <tr><th>Test Category</th><th>Tests</th></tr>
      {shunit2_rows}
    </table>
  </section>

  <footer>
    Generated by OpenJDK ARM64 Performance Benchmark Workflow | {timestamp}
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
