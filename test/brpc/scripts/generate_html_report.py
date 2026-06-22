#!/usr/bin/env python3
import argparse
import json
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


def make_bar_chart(items, chart_id, max_val=None, color="#4CAF50"):
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
    parser = argparse.ArgumentParser(description="Generate HTML report for brpc benchmarks")
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

    brpc_green = "#4CAF50"
    brpc_blue = "#2196F3"
    brpc_dark = "#1a1a2e"
    brpc_red = "#E74C3C"
    brpc_orange = "#FF9800"
    brpc_gray = "#7f8c8d"
    brpc_primary = "#4CAF50"

    rpc = data.get("rpc_benchmark", {})
    proto = data.get("protocol_benchmark", {})
    micro = data.get("micro_benchmark", {})

    rpc_results = rpc.get("results", {}) if isinstance(rpc, dict) else {}
    proto_results = proto.get("results", {}) if isinstance(proto, dict) else {}
    mic_results = micro.get("results", {}) if isinstance(micro, dict) else {}

    env_fields = [
        ("Architecture", vi.get("architecture", "unknown")),
        ("CPU Model", vi.get("cpu_model", "unknown")),
        ("CPU Cores", str(vi.get("cores", "unknown"))),
        ("Memory", fmt_val(vi.get("memory_mb", 0), "MB", 0)),
        ("Operating System", vi.get("os", "unknown")),
        ("Kernel", vi.get("kernel", "unknown")),
        ("brpc Version", vi.get("brpc_version", "unknown")),
        ("Compiler", vi.get("gcc_version", "unknown")),
        ("CMake", vi.get("cmake_version", "unknown")),
        ("Protobuf", vi.get("protobuf_version", "unknown")),
        ("OpenSSL", vi.get("openssl_support", "unknown")),
    ]
    env_rows = ""
    for label, value in env_fields:
        env_rows += f"<tr><td class='env-label'>{label}</td><td class='env-value'>{value}</td></tr>\n"

    card_items = []
    rpc_qps_max = None
    if rpc_results:
        qps_vals = []
        for k, v in rpc_results.items():
            if isinstance(v, dict):
                qps = v.get("avg_qps", 0)
                if isinstance(qps, (int, float)) and qps > 0:
                    qps_vals.append(qps)
        if qps_vals:
            rpc_qps_max = max(qps_vals)
            card_items.append(("RPC Peak QPS", f"{rpc_qps_max:,.0f}", "requests/sec"))

    proto_qps_max = None
    if proto_results:
        qps_vals = []
        for k, v in proto_results.items():
            if isinstance(v, dict):
                qps = v.get("avg_qps", 0)
                if isinstance(qps, (int, float)) and qps > 0:
                    qps_vals.append(qps)
        if qps_vals:
            proto_qps_max = max(qps_vals)
            card_items.append(("Protocol Peak QPS", f"{proto_qps_max:,.0f}", "requests/sec"))

    if mic_results:
        fastest_ops = None
        for v in mic_results.values():
            if isinstance(v, dict):
                ops = v.get("avg_ops_per_sec", 0)
                if isinstance(ops, (int, float)) and ops > 0 and (fastest_ops is None or ops > fastest_ops):
                    fastest_ops = ops
        if fastest_ops:
            card_items.append(("Micro Peak ops/s", f"{fastest_ops:.0f}", "ops/sec"))
        card_items.append(("Micro Benchmarks", str(len(mic_results)), "tests completed"))

    metrics_cards = ""
    card_colors = [brpc_green, brpc_blue, brpc_orange, brpc_red]
    for i, (name, value, unit) in enumerate(card_items):
        color = card_colors[i % len(card_colors)]
        metrics_cards += (
            f'<div class="metric-card" style="border-top:3px solid {color};">'
            f'<div class="metric-name">{name}</div>'
            f'<div class="metric-value">{value}</div>'
            f'<div class="metric-unit">{unit}</div>'
            f'</div>\n'
        )

    rpc_section = ""
    if isinstance(rpc, dict) and rpc_results:
        rpc_bar_items = []
        for k, v in rpc_results.items():
            if isinstance(v, dict):
                conc = v.get("concurrency", 0)
                qps = v.get("avg_qps", 0)
                if isinstance(qps, (int, float)) and qps > 0 and isinstance(conc, (int, float)):
                    rpc_bar_items.append((f"conc={conc}", qps))
        rpc_charts = make_bar_chart(rpc_bar_items, "rpc_qps", color=brpc_primary)
        rpc_rows = ""
        for name, res in rpc_results.items():
            if isinstance(res, dict):
                conc = res.get("concurrency", "N/A")
                qps = res.get("avg_qps", "N/A")
                avg_lat = res.get("avg_avg_latency_ms", "N/A")
                p99_lat = res.get("avg_p99_latency_ms", "N/A")
                errs = res.get("errors", 0)
                status = '<span class="status-pass">OK</span>' if errs == 0 else f'<span class="status-fail">{errs} errors</span>'
                rpc_rows += (
                    f"<tr><td>{conc}</td>"
                    f"<td>{fmt_val(qps, 'req/s')}</td>"
                    f"<td>{fmt_val(avg_lat, 'ms')}</td>"
                    f"<td>{fmt_val(p99_lat, 'ms')}</td>"
                    f"<td>{status}</td></tr>\n"
                )
        rpc_section = (
            f'<section id="rpc"><h2>RPC Benchmark (Primary - baidu_std)</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/apache/brpc/tree/master/example">brpc benchmark_server/benchmark_client</a> - '
            f'baidu_std protocol at various concurrency levels</p>'
            f'<p>{rpc.get("description", "")}</p>'
            f'{rpc_charts}'
            f'<table><tr><th>Concurrency</th><th>QPS</th><th>Avg Lat (ms)</th><th>P99 (ms)</th><th>Status</th></tr>'
            f'{rpc_rows}</table></section>'
        )

    proto_section = ""
    if isinstance(proto, dict) and proto_results:
        proto_bar_items = []
        for k, v in proto_results.items():
            if isinstance(v, dict):
                qps = v.get("avg_qps", 0)
                if isinstance(qps, (int, float)) and qps > 0:
                    proto_bar_items.append((k, qps))
        proto_charts = make_bar_chart(proto_bar_items, "proto_qps", color=brpc_blue)
        proto_rows = ""
        for pname, res in proto_results.items():
            if isinstance(res, dict):
                qps = res.get("avg_qps", "N/A")
                avg_lat = res.get("avg_avg_latency_ms", "N/A")
                p99_lat = res.get("avg_p99_latency_ms", "N/A")
                errs = res.get("errors", 0)
                status = '<span class="status-pass">OK</span>' if errs == 0 else f'<span class="status-fail">{errs} errors</span>'
                proto_rows += (
                    f"<tr><td>{pname}</td>"
                    f"<td>{fmt_val(qps, 'req/s')}</td>"
                    f"<td>{fmt_val(avg_lat, 'ms')}</td>"
                    f"<td>{fmt_val(p99_lat, 'ms')}</td>"
                    f"<td>{status}</td></tr>\n"
                )
        proto_section = (
            f'<section id="protocol"><h2>Protocol Benchmark (Secondary)</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/apache/brpc/tree/master/example">brpc multi-protocol benchmark</a> - '
            f'baidu_std, HTTP, hulu_pbrpc, sofa_pbrpc comparison at conc=64</p>'
            f'<p>{proto.get("description", "")}</p>'
            f'{proto_charts}'
            f'<table><tr><th>Protocol</th><th>QPS</th><th>Avg Lat (ms)</th><th>P99 (ms)</th><th>Status</th></tr>'
            f'{proto_rows}</table></section>'
        )

    micro_section = ""
    if isinstance(micro, dict) and mic_results:
        mic_bar_items = [(k[:20], v.get("avg_ops_per_sec", 0)) for k, v in mic_results.items() if isinstance(v, dict) and isinstance(v.get("avg_ops_per_sec", 0), (int, float)) and v.get("avg_ops_per_sec", 0) > 0]
        mic_charts = make_bar_chart(mic_bar_items, "micro_ops", color=brpc_orange)
        mic_rows = ""
        for mname, res in mic_results.items():
            if isinstance(res, dict):
                desc = res.get("description", "")
                avg_ns = res.get("avg_avg_ns", "N/A")
                ops = res.get("avg_ops_per_sec", "N/A")
                mic_rows += (
                    f"<tr><td>{mname}</td>"
                    f"<td>{desc[:60]}</td>"
                    f"<td>{fmt_val(avg_ns, 'ns')}</td>"
                    f"<td>{fmt_val(ops, 'ops/s')}</td></tr>\n"
                )
        micro_section = (
            f'<section id="micro"><h2>C++ Micro Benchmarks (brpc Components)</h2>'
            f'<p class="benchmark-ref">Reference: Custom micro benchmark suite (mutex, atomic, thread, string, vector, map, memcpy, sort, alloc, math)</p>'
            f'<p>{micro.get("description", "")}</p>'
            f'{mic_charts}'
            f'<table><tr><th>Benchmark</th><th>Description</th><th>Avg ns/op</th><th>ops/sec</th></tr>'
            f'{mic_rows}</table></section>'
        )

    arm64_rows = ""
    arm64_items = [
        ("ARM64 Architecture", str(vi.get("architecture", "unknown"))),
        ("C++ Compiler ARM64", str(vi.get("gcc_version", "unknown"))),
        ("OpenSSL Support", str(vi.get("openssl_support", "unknown"))),
    ]
    for label, value in arm64_items:
        if value.lower() in ("aarch64", "arm64"):
            status = '<span class="status-pass">YES</span>'
        elif value.lower() in ("yes", "true", "1"):
            status = '<span class="status-pass">YES</span>'
        elif value.lower() in ("no", "false", "0"):
            status = '<span class="status-fail">NO</span>'
        elif "aarch64" in value.lower() or "arm64" in value.lower():
            status = '<span class="status-pass">YES</span>'
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
        ("Compiler Verification", "testGccOrClangIsInstalled, testCmakeIsInstalled"),
        ("Dependency Verification", "testProtobufIsInstalled"),
        ("brpc Library", "testBrpcHeadersAvailable, testBrpcLibraryAvailable"),
        ("Version Info", "testResultsJsonHasVersionInfo, testResultsJsonHasArchitecture, testResultsJsonHasSoftwareVersion, testResultsJsonHasCompilerInfo"),
        ("RPC Benchmark", "testBenchmarkRpcInResultsJson, testBenchmarkRpcHasRequiredFields"),
        ("Protocol Benchmark", "testBenchmarkProtocolInResultsJson"),
        ("Micro Benchmark", "testBenchmarkMicroInResultsJson"),
        ("Results Validation", "testResultsJsonExists, testResultsJsonContainsAllBenchmarks"),
        ("Report Generation", "testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated"),
    ]
    for cat, tests in test_categories:
        shunit2_rows += f"<tr><td>{cat}</td><td>{tests}</td></tr>\n"

    threshold_items = [
        "brpc baidu_std QPS &ge; 50,000 at conc=64 on ARM64",
        "brpc baidu_std P99 &le; 2ms at conc=64 on ARM64",
        "brpc HTTP QPS &ge; 30,000 at conc=64 on ARM64",
        "mutex lock/unlock avg_ns &le; 50 on ARM64",
        "atomic increment avg_ns &le; 20 on ARM64",
        "memcpy 64KB avg_ns &le; 30,000 on ARM64",
        "thread create/join avg_ns &le; 50,000 on ARM64",
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
<title>brpc ARM64 Performance Benchmark Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #f5f5f7; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  header {{ background: linear-gradient(135deg, {brpc_dark}, #2c3e50); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header .subtitle {{ font-size: 14px; color: #a5d6a7; }}
  header .version {{ font-size: 16px; margin-top: 4px; }}
  .env-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: white; border-radius: 8px; overflow: hidden; }}
  .env-table td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
  .env-label {{ width: 30%; font-weight: 600; color: {brpc_blue}; background: #fafafa; }}
  .env-value {{ width: 70%; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }}
  .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; }}
  .metric-name {{ font-size: 12px; color: {brpc_gray}; margin-bottom: 6px; text-transform: uppercase; }}
  .metric-value {{ font-size: 20px; font-weight: 700; color: #333; }}
  .metric-unit {{ font-size: 11px; color: {brpc_gray}; }}
  section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px; }}
  section h2 {{ color: {brpc_blue}; border-bottom: 2px solid {brpc_primary}; padding-bottom: 8px; margin-bottom: 15px; }}
  section h3 {{ color: {brpc_blue}; margin: 15px 0 10px; }}
  .benchmark-ref {{ font-size: 13px; color: {brpc_gray}; margin-bottom: 15px; }}
  .benchmark-ref a {{ color: {brpc_blue}; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 20px; }}
  th {{ background: {brpc_blue}; color: white; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
  .bar-chart {{ margin: 15px 0; }}
  .bar-row {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 150px; font-size: 13px; text-align: right; padding-right: 10px; }}
  .bar-fill {{ height: 22px; border-radius: 3px; display: inline-block; min-width: 2px; }}
  .bar-val {{ font-size: 12px; padding-left: 6px; color: white; }}
  .status-pass {{ background: {brpc_green}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-fail {{ background: {brpc_red}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-unknown {{ background: {brpc_gray}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .arm64-table {{ border: 2px solid {brpc_primary}; }}
  .arm64-table th {{ background: {brpc_blue}; }}
  .threshold {{ background: #fff8e1; border-radius: 6px; padding: 15px; margin: 10px 0; }}
  .threshold h3 {{ color: #f57f17; }}
  .threshold ul {{ list-style: none; padding: 0; }}
  .threshold li {{ padding: 4px 0; font-size: 13px; }}
  footer {{ text-align: center; padding: 20px; color: {brpc_gray}; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>brpc ARM64 Performance Benchmark</h1>
    <div class="subtitle">Baidu RPC Framework - High-Performance C++ RPC for Microservices</div>
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

  {rpc_section}

  {proto_section}

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
    <p>See <code>brpc_test.sh</code> for full test definitions</p>
    <table>
      <tr><th>Test Category</th><th>Tests</th></tr>
      {shunit2_rows}
    </table>
  </section>

  <footer>
    Generated by brpc ARM64 Performance Benchmark Workflow | {timestamp}
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
