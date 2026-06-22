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


def make_bar_chart(items, chart_id, max_val=None, color="#00758f"):
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
    parser = argparse.ArgumentParser(description="Generate HTML report for MySQL benchmarks")
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

    mysql_primary = "#00758f"
    mysql_orange = "#f29111"
    mysql_red = "#e74c3c"
    mysql_green = "#34a853"
    mysql_gray = "#7f8c8d"

    env_fields = [
        ("Architecture", vi.get("architecture", "unknown")),
        ("CPU Model", vi.get("cpu_model", "unknown")),
        ("CPU Cores", str(vi.get("cores", "unknown"))),
        ("Memory", fmt_val(vi.get("memory_mb", 0), "MB", 0)),
        ("Operating System", vi.get("os", "unknown")),
        ("Kernel", vi.get("kernel", "unknown")),
        ("MySQL Version", version),
        ("Sysbench", vi.get("sysbench_version", "unknown")),
        ("Compile Machine", vi.get("compile_machine", "unknown")),
        ("InnoDB Buffer Pool", vi.get("innodb_buffer_pool_size", "unknown")),
        ("Max Connections", vi.get("max_connections", "unknown")),
        ("flush_log_at_trx", vi.get("innodb_flush_log_at_trx_commit", "unknown")),
        ("sync_binlog", vi.get("sync_binlog", "unknown")),
    ]
    env_rows = ""
    for label, value in env_fields:
        env_rows += f"<tr><td class='env-label'>{label}</td><td class='env-value'>{value}</td></tr>\n"

    card_items = []
    oltp = data.get("oltp_benchmark", {})
    oltp_r = oltp.get("results", {})
    if oltp_r:
        rw = oltp_r.get("oltp_read_write", {})
        if rw and "avg_tps" in rw:
            card_items.append(("OLTP Read/Write TPS", f"{rw['avg_tps']}"))
        ps = oltp_r.get("oltp_point_select", {})
        if ps and "avg_tps" in ps:
            card_items.append(("Point Select TPS", f"{ps['avg_tps']}"))
        ro = oltp_r.get("oltp_read_only", {})
        if ro and "avg_qps" in ro:
            card_items.append(("Read-Only QPS", f"{ro['avg_qps']}"))

    metrics_cards = ""
    card_colors = [mysql_primary, mysql_orange, mysql_green, mysql_red]
    for i, (name, value) in enumerate(card_items):
        color = card_colors[i % len(card_colors)]
        metrics_cards += (
            f'<div class="metric-card" style="border-top:3px solid {color};">'
            f'<div class="metric-name">{name}</div>'
            f'<div class="metric-value">{value}</div>'
            f'</div>\n'
        )

    oltp_section = ""
    if oltp:
        tps_items = [(n, r.get("avg_tps", 0)) for n, r in oltp_r.items() if "avg_tps" in r]
        qps_items = [(n, r.get("avg_qps", 0)) for n, r in oltp_r.items() if "avg_qps" in r]
        lat_items = [(n, r.get("avg_latency_p95_ms", 0)) for n, r in oltp_r.items() if "avg_latency_p95_ms" in r]

        charts = make_bar_chart(tps_items, "oltp_tps", color=mysql_primary)
        charts += make_bar_chart(qps_items, "oltp_qps", color=mysql_orange)
        charts += make_bar_chart(lat_items, "oltp_lat", color=mysql_red)

        rows = ""
        for name, res in oltp_r.items():
            rows += (
                f"<tr><td>{name}</td>"
                f"<td>{res.get('avg_tps', 'N/A')}</td>"
                f"<td>{res.get('avg_qps', 'N/A')}</td>"
                f"<td>{res.get('avg_latency_avg_ms', 'N/A')}</td>"
                f"<td>{res.get('avg_latency_p95_ms', 'N/A')}</td>"
                f"<td>{res.get('avg_latency_p99_ms', 'N/A')}</td>"
                f"<td>{res.get('avg_read_per_sec', 'N/A')}</td>"
                f"<td>{res.get('avg_write_per_sec', 'N/A')}</td></tr>\n"
            )

        oltp_section = (
            f'<section id="oltp"><h2>OLTP Benchmark (sysbench)</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/akopytov/sysbench">sysbench</a></p>'
            f'<div class="metrics-grid">{metrics_cards}</div>'
            f'{charts}'
            f'<h3>Detailed Results</h3>'
            f'<table><tr><th>Test</th><th>TPS</th><th>QPS</th><th>Lat Avg</th><th>Lat P95</th><th>Lat P99</th><th>Read/sec</th><th>Write/sec</th></tr>'
            f'{rows}</table></section>'
        )

    olap_section = ""
    olap = data.get("olap_benchmark", {})
    if olap:
        olap_results = olap.get("results", {})
        concurrency = olap_results.get("concurrency_scaling", {})
        analytics = olap_results.get("analytical_queries", {})

        olap_charts = ""
        concurrency_table = ""
        if concurrency:
            tps_t = [(l, r.get("avg_tps", 0)) for l, r in concurrency.items()]
            qps_t = [(l, r.get("avg_qps", 0)) for l, r in concurrency.items()]
            lat_t = [(l, r.get("avg_lat_p95_ms", 0)) for l, r in concurrency.items()]
            olap_charts += make_bar_chart(tps_t, "olap_tps_threads", color=mysql_primary)
            olap_charts += make_bar_chart(qps_t, "olap_qps_threads", color=mysql_orange)
            olap_charts += make_bar_chart(lat_t, "olap_lat_threads", color=mysql_red)

            rows = ""
            for label, res in concurrency.items():
                rows += (
                    f"<tr><td>{res.get('threads', 'N/A')}</td>"
                    f"<td>{res.get('avg_tps', 'N/A')}</td>"
                    f"<td>{res.get('avg_qps', 'N/A')}</td>"
                    f"<td>{res.get('avg_lat_avg_ms', 'N/A')}</td>"
                    f"<td>{res.get('avg_lat_p95_ms', 'N/A')}</td>"
                    f"<td>{res.get('avg_lat_p99_ms', 'N/A')}</td></tr>\n"
                )
            concurrency_table = (
                f'<h3>Concurrency Scaling</h3>'
                f'{olap_charts}'
                f'<table><tr><th>Threads</th><th>TPS</th><th>QPS</th><th>Lat Avg</th><th>Lat P95</th><th>Lat P99</th></tr>{rows}</table>'
            )

        analytics_section = ""
        if analytics:
            aq_items = [(n, r.get("avg_time_ms", 0)) for n, r in analytics.items()]
            analytics_section = make_bar_chart(aq_items, "olap_analytics", color=mysql_green)

            rows = ""
            for name, res in analytics.items():
                sql_preview = res.get("query", "")[:60]
                rows += (
                    f"<tr><td>{name}</td>"
                    f"<td>{res.get('avg_time_ms', 'N/A')}</td>"
                    f"<td>{res.get('min_time_ms', 'N/A')}</td>"
                    f"<td>{res.get('max_time_ms', 'N/A')}</td>"
                    f"<td><code>{sql_preview}...</code></td></tr>\n"
                )
            analytics_section += (
                f'<h3>Analytical Queries</h3>'
                f'<table><tr><th>Query</th><th>Avg (ms)</th><th>Min (ms)</th><th>Max (ms)</th><th>SQL</th></tr>{rows}</table>'
            )

        olap_section = (
            f'<section id="olap"><h2>Concurrency Scaling & Analytical Queries</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://github.com/akopytov/sysbench">sysbench</a></p>'
            f'{concurrency_table}{analytics_section}</section>'
        )

    micro_section = ""
    micro = data.get("micro_benchmark", {})
    if micro:
        mresults = micro.get("results", {})
        micro_content = '<div class="metrics-grid">'

        if "connection_handling" in mresults:
            ch = mresults["connection_handling"]
            max_conn = max(ch.values(), key=lambda x: x.get("connections_per_sec", 0)) if ch else None
            if max_conn:
                micro_content += (
                    f'<div class="metric-card" style="border-top:3px solid {mysql_primary};">'
                    f'<div class="metric-name">Peak Connection Rate</div>'
                    f'<div class="metric-value">{max_conn.get("connections_per_sec", "N/A")}</div>'
                    f'<div class="metric-unit">connections/sec</div></div>'
                )

        if "bulk_insert" in mresults:
            bi = mresults["bulk_insert"]
            max_ins = max(bi.values(), key=lambda x: x.get("insert_rate_per_sec", 0)) if bi else None
            if max_ins:
                micro_content += (
                    f'<div class="metric-card" style="border-top:3px solid {mysql_orange};">'
                    f'<div class="metric-name">Peak Insert Rate</div>'
                    f'<div class="metric-value">{max_ins.get("insert_rate_per_sec", "N/A")}</div>'
                    f'<div class="metric-unit">rows/sec</div></div>'
                )

        micro_content += '</div>'

        if "connection_handling" in mresults:
            conn_items = [(n, r.get("connections_per_sec", 0)) for n, r in mresults["connection_handling"].items()]
            micro_content += make_bar_chart(conn_items, "micro_conn", color=mysql_primary)

        if "bulk_insert" in mresults:
            ins_items = [(n, r.get("insert_rate_per_sec", 0)) for n, r in mresults["bulk_insert"].items()]
            micro_content += make_bar_chart(ins_items, "micro_insert", color=mysql_orange)

        if "engine_comparison" in mresults:
            micro_content += '<h3>Engine Comparison: InnoDB vs MyISAM</h3>'
            micro_content += '<table><tr><th>Engine</th><th>Operation</th><th>Avg Time (ms)</th></tr>'
            for engine, ops in mresults["engine_comparison"].items():
                for op, res in ops.items():
                    micro_content += f"<tr><td>{engine}</td><td>{op}</td><td>{res.get('avg_time_ms', 'N/A')}</td></tr>\n"
            micro_content += '</table>'

        micro_content += '<h3>Detailed Results</h3><table><tr><th>Operation</th><th>Results</th></tr>'
        for op_name, res in mresults.items():
            micro_content += f"<tr><td>{op_name}</td><td>{json.dumps(res)}</td></tr>\n"
        micro_content += '</table>'

        micro_section = (
            f'<section id="micro"><h2>Micro Benchmarks</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://dev.mysql.com/doc/">MySQL docs</a></p>'
            f'{micro_content}</section>'
        )

    compile_machine = vi.get("compile_machine", "unknown")
    arm64_rows = ""
    arm64_items = [
        ("ARM64 Architecture", str(vi.get("architecture", "unknown"))),
        ("Compile Machine", str(compile_machine)),
        ("InnoDB Available", "Yes" if vi.get("innodb_buffer_pool_size") else "Unknown"),
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
        ("MySQL Installation", "testMysqlIsInstalled, testMysqldIsInstalled, testSysbenchIsInstalled"),
        ("ARM64 Build Check", "testCompileMachineIsARM64, testInnoDBBufferPoolConfigured"),
        ("Version Info", "testResultsJsonHasVersionInfo, testResultsJsonHasArchitecture, testResultsJsonHasSoftwareVersion"),
        ("OLTP Benchmark", "testBenchmarkOltInResultsJson, testBenchmarkOltpHasRequiredFields"),
        ("OLAP Benchmark", "testBenchmarkOlapInResultsJson"),
        ("Micro Benchmark", "testBenchmarkMicroInResultsJson"),
        ("Results Validation", "testResultsJsonExists, testResultsJsonContainsAllBenchmarks"),
        ("Report Generation", "testHtmlReportGenerated, testSummaryReportGenerated, testLogFileGenerated"),
    ]
    for cat, tests in test_categories:
        shunit2_rows += f"<tr><td>{cat}</td><td>{tests}</td></tr>\n"

    html = (
        f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MySQL ARM64 Performance Benchmark Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  header {{ background: linear-gradient(135deg, {mysql_primary}, {mysql_orange}); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header .subtitle {{ font-size: 14px; opacity: 0.9; }}
  header .version {{ font-size: 16px; margin-top: 4px; }}
  .env-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: white; border-radius: 8px; overflow: hidden; }}
  .env-table td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
  .env-label {{ width: 30%; font-weight: 600; color: {mysql_primary}; background: #fafafa; }}
  .env-value {{ width: 70%; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }}
  .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; }}
  .metric-name {{ font-size: 12px; color: {mysql_gray}; margin-bottom: 6px; text-transform: uppercase; }}
  .metric-value {{ font-size: 20px; font-weight: 700; color: #333; }}
  .metric-unit {{ font-size: 11px; color: {mysql_gray}; }}
  section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px; }}
  section h2 {{ color: {mysql_primary}; border-bottom: 2px solid {mysql_orange}; padding-bottom: 8px; margin-bottom: 15px; }}
  section h3 {{ color: {mysql_primary}; margin: 15px 0 10px; }}
  .benchmark-ref {{ font-size: 13px; color: {mysql_gray}; margin-bottom: 15px; }}
  .benchmark-ref a {{ color: #4285f4; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 20px; }}
  th {{ background: {mysql_primary}; color: white; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
  .bar-chart {{ margin: 15px 0; }}
  .bar-row {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 150px; font-size: 13px; text-align: right; padding-right: 10px; }}
  .bar-fill {{ height: 22px; border-radius: 3px; display: inline-block; min-width: 2px; }}
  .bar-val {{ font-size: 12px; padding-left: 6px; color: white; }}
  .status-pass {{ background: {mysql_green}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-fail {{ background: {mysql_red}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-unknown {{ background: {mysql_gray}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .arm64-table {{ border: 2px solid {mysql_primary}; }}
  .arm64-table th {{ background: {mysql_primary}; }}
  footer {{ text-align: center; padding: 20px; color: {mysql_gray}; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>MySQL ARM64 Performance Benchmark</h1>
    <div class="subtitle">Database - OLTP, Concurrency Scaling, Analytical & Micro Benchmarks</div>
    <div class="version">MySQL v{version} | {timestamp}</div>
  </header>

  <section id="environment">
    <h2>Environment Information</h2>
    <table class="env-table">
      {env_rows}
    </table>
  </section>

  {oltp_section}

  {olap_section}

  {micro_section}

  {arm64_section}

  <section id="shunit2">
    <h2>shUnit2 Test Validation</h2>
    <p class="benchmark-ref">Automated validation via shUnit2 test suite with ARM64 assertions</p>
    <p>See <code>mysql_test.sh</code> for full test definitions</p>
    <table>
      <tr><th>Test Category</th><th>Tests</th></tr>
      {shunit2_rows}
    </table>
  </section>

  <footer>
    Generated by MySQL ARM64 Performance Benchmark Workflow | {timestamp}
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
