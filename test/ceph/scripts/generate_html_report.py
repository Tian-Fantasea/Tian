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


def generate_bar_chart_css(data_items, label_key, value_key, chart_id, max_width_pct=100, color="#e74c3c"):
    if not data_items:
        return "<p>No data available</p>"
    max_val = max([item.get(value_key, 0) or 0 for item in data_items], default=1)
    if max_val == 0:
        max_val = 1
    rows = []
    for item in data_items:
        label = item.get(label_key, "?")
        val = item.get(value_key, 0) or 0
        pct = (val / max_val) * max_width_pct
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{label}</span>'
            f'<div class="bar-fill" style="width:{pct:.1f}%;background:{color};">'
            f'<span class="bar-val">{fmt_val(val)}</span></div></div>'
        )
    return f'<div id="{chart_id}" class="bar-chart">{"".join(rows)}</div>'


def main():
    parser = argparse.ArgumentParser(description="Generate HTML report for Ceph benchmarks")
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

    ceph_primary = "#e74c3c"
    ceph_secondary = "#c0392b"
    ceph_dark = "#a93226"
    ceph_accent = "#f39c12"
    ceph_blue = "#2980b9"
    ceph_green = "#27ae60"
    ceph_gray = "#7f8c8d"

    env_fields = [
        ("Architecture", vi.get("architecture", "unknown")),
        ("CPU Model", vi.get("cpu_model", "unknown")),
        ("CPU Cores", str(vi.get("cores", "unknown"))),
        ("Memory", fmt_val(vi.get("memory_mb", 0), "MB", 0)),
        ("Operating System", vi.get("os", "unknown")),
        ("Kernel", vi.get("kernel", "unknown")),
        ("Ceph Version", version),
        ("Cluster Health", vi.get("cluster_health", "unknown")),
        ("OSD Count", str(vi.get("osd_count", 0))),
        ("Monitor Count", str(vi.get("mon_count", 0))),
    ]
    env_rows = ""
    for label, value in env_fields:
        env_rows += f"<tr><td class='env-label'>{label}</td><td class='env-value'>{value}</td></tr>\n"

    metrics_cards = ""
    card_colors = [ceph_primary, ceph_blue, ceph_green, ceph_accent, ceph_secondary, ceph_dark]
    card_items = []

    rados = data.get("rados_benchmark", {})
    rados_r = rados.get("results", {})
    obj_sweep = rados_r.get("object_size_sweep", [])
    if obj_sweep:
        max_ops = max([e.get("avg_throughput_ops_sec", 0) or 0 for e in obj_sweep], default=0)
        card_items.append(("RADOS Max Write Throughput", f"{max_ops:.0f} ops/sec"))

    rbd = data.get("rbd_benchmark", {})
    rbd_r = rbd.get("results", {})
    rand_rw = rbd_r.get("random_read_write", [])
    if rand_rw:
        max_iops = max([e.get("avg_iops", 0) or 0 for e in rand_rw], default=0)
        card_items.append(("RBD Max Random IOPS", f"{max_iops:.0f} IOPS"))

    cephfs = data.get("cephfs_benchmark", {})
    cephfs_r = cephfs.get("results", {})
    meta = cephfs_r.get("metadata_operations", [])
    if meta:
        avg_mkdir = sum([e.get("mkdir_ops_sec", 0) or 0 for e in meta]) / len(meta)
        card_items.append(("CephFS mkdir ops/sec", f"{avg_mkdir:.0f}"))

    micro = data.get("micro_benchmark", {})
    micro_r = micro.get("results", {})
    ec = micro_r.get("ec_vs_replicated", [])
    if ec:
        card_items.append(("EC Profiles Tested", str(len(ec))))

    for i, (name, value) in enumerate(card_items):
        color = card_colors[i % len(card_colors)]
        metrics_cards += (
            f'<div class="metric-card" style="border-top:3px solid {color};">'
            f'<div class="metric-name">{name}</div>'
            f'<div class="metric-value">{value}</div>'
            f'</div>\n'
        )

    rados_section = ""
    if rados:
        obj_sweep = rados_r.get("object_size_sweep", [])
        conc_scaling = rados_r.get("concurrency_scaling", [])

        obj_chart = generate_bar_chart_css(obj_sweep, "object_size", "avg_throughput_ops_sec", "rados_obj_size", color=ceph_primary)
        conc_chart = generate_bar_chart_css(conc_scaling, "concurrency", "avg_bandwidth_mb_sec", "rados_concurrency", color=ceph_blue)

        rados_tables = ""
        if obj_sweep:
            rows = ""
            for e in obj_sweep:
                rows += (
                    f"<tr><td>{e.get('object_size', '?')}</td>"
                    f"<td>{fmt_val(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}</td>"
                    f"<td>{fmt_val(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}</td>"
                    f"<td>{fmt_val(e.get('avg_latency_ms', 0), 'ms')}</td>"
                    f"<td>{e.get('iterations', 0)}</td></tr>\n"
                )
            rados_tables += (
                f'<h3>Write Throughput by Object Size</h3>'
                f'{obj_chart}'
                f'<table><tr><th>Object Size</th><th>Throughput</th><th>Bandwidth</th><th>Latency</th><th>Iterations</th></tr>'
                f'{rows}</table>'
            )

        if conc_scaling:
            rows = ""
            for e in conc_scaling:
                rows += (
                    f"<tr><td>{e.get('concurrency', 0)}</td>"
                    f"<td>{fmt_val(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}</td>"
                    f"<td>{fmt_val(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}</td>"
                    f"<td>{fmt_val(e.get('avg_latency_ms', 0), 'ms')}</td></tr>\n"
                )
            rados_tables += (
                f'<h3>Concurrency Scaling (4M objects, write)</h3>'
                f'{conc_chart}'
                f'<table><tr><th>Concurrency</th><th>Throughput</th><th>Bandwidth</th><th>Latency</th></tr>'
                f'{rows}</table>'
            )

        rados_section = (
            f'<section id="rados"><h2>RADOS Object Storage</h2>'
            f'<p class="benchmark-ref">Benchmark: rados bench | '
            f'<a href="https://docs.ceph.com/en/latest/man/8/rados/">rados bench documentation</a></p>'
            f'{rados_tables}</section>'
        )

    rbd_section = ""
    if rbd:
        seq_rw = rbd_r.get("sequential_read_write", [])
        rand_rw = rbd_r.get("random_read_write", [])
        iodepth = rbd_r.get("iodepth_scaling", [])

        iodepth_chart = generate_bar_chart_css(iodepth, "iodepth", "avg_iops", "rbd_iodepth", color=ceph_blue)

        rbd_tables = ""
        if seq_rw:
            rows = ""
            for e in seq_rw:
                rows += (
                    f"<tr><td>{e.get('rw', '?')}</td>"
                    f"<td>{e.get('block_size', '?')}</td>"
                    f"<td>{fmt_val(e.get('avg_iops', 0), 'IOPS')}</td>"
                    f"<td>{fmt_val(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}</td>"
                    f"<td>{fmt_val(e.get('avg_latency_ms', 0), 'ms')}</td></tr>\n"
                )
            rbd_tables += (
                f'<h3>Sequential Read/Write</h3>'
                f'<table><tr><th>Operation</th><th>Block Size</th><th>IOPS</th><th>Bandwidth</th><th>Latency</th></tr>'
                f'{rows}</table>'
            )

        if rand_rw:
            rows = ""
            for e in rand_rw:
                rows += (
                    f"<tr><td>{e.get('rw', '?')}</td>"
                    f"<td>{e.get('block_size', '?')}</td>"
                    f"<td>{fmt_val(e.get('avg_iops', 0), 'IOPS')}</td>"
                    f"<td>{fmt_val(e.get('avg_latency_ms', 0), 'ms')}</td></tr>\n"
                )
            rbd_tables += (
                f'<h3>Random Read/Write</h3>'
                f'<table><tr><th>Operation</th><th>Block Size</th><th>IOPS</th><th>Latency</th></tr>'
                f'{rows}</table>'
            )

        if iodepth:
            rows = ""
            for e in iodepth:
                rows += (
                    f"<tr><td>{e.get('iodepth', 0)}</td>"
                    f"<td>{fmt_val(e.get('avg_iops', 0), 'IOPS')}</td>"
                    f"<td>{fmt_val(e.get('avg_latency_ms', 0), 'ms')}</td></tr>\n"
                )
            rbd_tables += (
                f'<h3>IODEPTH Scaling (random read, 4K)</h3>'
                f'{iodepth_chart}'
                f'<table><tr><th>IODEPTH</th><th>IOPS</th><th>Latency</th></tr>{rows}</table>'
            )

        rbd_section = (
            f'<section id="rbd"><h2>RBD Block Storage</h2>'
            f'<p class="benchmark-ref">Benchmark: FIO with rbd I/O engine | '
            f'<a href="https://fio.readthedocs.io/en/latest/fio_doc.html#rbd">FIO RBD documentation</a></p>'
            f'{rbd_tables}</section>'
        )

    cephfs_section = ""
    if cephfs:
        meta = cephfs_r.get("metadata_operations", [])
        sf = cephfs_r.get("small_file_operations", [])

        cephfs_tables = ""
        if meta:
            rows = ""
            for e in meta:
                rows += (
                    f"<tr><td>{e.get('iteration', 0)}</td>"
                    f"<td>{fmt_val(e.get('mkdir_ops_sec', 0), 'ops/sec', 0)}</td>"
                    f"<td>{fmt_val(e.get('stat_ops_sec', 0), 'ops/sec', 0)}</td>"
                    f"<td>{fmt_val(e.get('ls_ops_sec', 0), 'ops/sec', 2)}</td>"
                    f"<td>{fmt_val(e.get('rmdir_ops_sec', 0), 'ops/sec', 0)}</td></tr>\n"
                )
            cephfs_tables += (
                f'<h3>Metadata Operations</h3>'
                f'<table><tr><th>Iteration</th><th>mkdir</th><th>stat</th><th>ls</th><th>rmdir</th></tr>'
                f'{rows}</table>'
            )

        if sf:
            rows = ""
            for e in sf:
                rows += (
                    f"<tr><td>{e.get('iteration', 0)}</td>"
                    f"<td>{fmt_val(e.get('small_file_create_ops_sec', 0), 'ops/sec', 0)}</td>"
                    f"<td>{fmt_val(e.get('small_file_read_ops_sec', 0), 'ops/sec', 0)}</td>"
                    f"<td>{fmt_val(e.get('small_file_delete_ops_sec', 0), 'ops/sec', 0)}</td></tr>\n"
                )
            cephfs_tables += (
                f'<h3>Small File Operations (4K)</h3>'
                f'<table><tr><th>Iteration</th><th>Create</th><th>Read</th><th>Delete</th></tr>'
                f'{rows}</table>'
            )

        cephfs_section = (
            f'<section id="cephfs"><h2>CephFS File Storage</h2>'
            f'<p class="benchmark-ref">Benchmark: FIO libaio + metadata ops | '
            f'<a href="https://docs.ceph.com/en/latest/cephfs/">CephFS documentation</a></p>'
            f'{cephfs_tables}</section>'
        )

    micro_section = ""
    if micro:
        ec = micro_r.get("ec_vs_replicated", [])
        comp = micro_r.get("compression_algorithms", [])
        crc = micro_r.get("arm64_crc32c_checksum", {})

        ec_chart = generate_bar_chart_css(ec, "ec_profile", "avg_throughput_ops_sec", "ec_compare", color=ceph_accent)
        comp_chart = generate_bar_chart_css(comp, "compression_algorithm", "avg_throughput_ops_sec", "comp_compare", color=ceph_green)

        micro_tables = ""
        if ec:
            rows = ""
            for e in ec:
                skip = e.get("skip", False)
                status = '<span class="status-skip">SKIP</span>' if skip else '<span class="status-pass">OK</span>'
                rows += (
                    f"<tr><td>{e.get('ec_profile', '?')}</td>"
                    f"<td>{e.get('k', '?')}/{e.get('m', '?')}</td>"
                    f"<td>{e.get('data_efficiency', '?')}</td>"
                    f"<td>{fmt_val(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}</td>"
                    f"<td>{fmt_val(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}</td>"
                    f"<td>{status}</td></tr>\n"
                )
            micro_tables += (
                f'<h3>Erasure Coding vs Replicated</h3>'
                f'{ec_chart}'
                f'<table><tr><th>Profile</th><th>k/m</th><th>Efficiency</th><th>Throughput</th><th>Bandwidth</th><th>Status</th></tr>'
                f'{rows}</table>'
            )

        if comp:
            rows = ""
            for e in comp:
                rows += (
                    f"<tr><td>{e.get('compression_algorithm', '?')}</td>"
                    f"<td>{fmt_val(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}</td>"
                    f"<td>{fmt_val(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}</td>"
                    f"<td>{e.get('compress_ratio', 'N/A')}</td></tr>\n"
                )
            micro_tables += (
                f'<h3>Compression Algorithm Comparison</h3>'
                f'{comp_chart}'
                f'<table><tr><th>Algorithm</th><th>Throughput</th><th>Bandwidth</th><th>Ratio</th></tr>'
                f'{rows}</table>'
            )

        if crc:
            crc_rows = ""
            for k, v in crc.items():
                if k != "raw_output":
                    crc_rows += f"<tr><td>{k}</td><td>{v}</td></tr>\n"
            micro_tables += (
                f'<h3>ARM64 CRC32C Checksum</h3>'
                f'<table><tr><th>Feature</th><th>Value</th></tr>{crc_rows}</table>'
            )

        micro_section = (
            f'<section id="micro"><h2>Micro Benchmarks</h2>'
            f'<p class="benchmark-ref">OSD perf, EC vs replicated, compression, ARM64 CRC32C, RBD cache</p>'
            f'{micro_tables}</section>'
        )

    arm64 = vi.get("arm64_features", {})
    arm64_rows = ""
    arm64_items = [
        ("Architecture", str(arm64.get("is_arm64", "unknown"))),
        ("NEON/SIMD Available", str(arm64.get("neon_available", "unknown"))),
        ("ARM64 CRC32C Available", str(arm64.get("crc32c_available", "unknown"))),
    ]
    for label, value in arm64_items:
        if value.lower() in ("true", "yes", "1"):
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
        ("Ceph Installation", "testCephIsInstalled"),
        ("Version Info", "testResultsJsonHasVersionInfo, testResultsJsonHasArchitecture, testResultsJsonHasSoftwareVersion"),
        ("RADOS Benchmarks", "testBenchmarkRadosInResultsJson, testBenchmarkRadosHasRequiredFields"),
        ("RBD Benchmarks", "testBenchmarkRbdInResultsJson"),
        ("CephFS Benchmarks", "testBenchmarkCephfsInResultsJson"),
        ("Micro Benchmarks", "testBenchmarkMicroInResultsJson, testBenchmarkMicroAllOperationsCompleted"),
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
<title>Ceph ARM64 Performance Benchmark Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  header {{ background: linear-gradient(135deg, {ceph_primary}, {ceph_dark}); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header .subtitle {{ font-size: 14px; opacity: 0.9; }}
  header .version {{ font-size: 16px; margin-top: 4px; }}
  .env-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: white; border-radius: 8px; overflow: hidden; }}
  .env-table td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
  .env-label {{ width: 30%; font-weight: 600; color: {ceph_dark}; background: #fafafa; }}
  .env-value {{ width: 70%; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }}
  .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; }}
  .metric-name {{ font-size: 12px; color: {ceph_gray}; margin-bottom: 6px; text-transform: uppercase; }}
  .metric-value {{ font-size: 20px; font-weight: 700; color: #333; }}
  section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px; }}
  section h2 {{ color: {ceph_secondary}; border-bottom: 2px solid {ceph_primary}; padding-bottom: 8px; margin-bottom: 15px; }}
  section h3 {{ color: {ceph_dark}; margin: 15px 0 10px; }}
  .benchmark-ref {{ font-size: 13px; color: {ceph_gray}; margin-bottom: 15px; }}
  .benchmark-ref a {{ color: {ceph_blue}; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 20px; }}
  th {{ background: {ceph_secondary}; color: white; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
  .bar-chart {{ margin: 15px 0; }}
  .bar-row {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 120px; font-size: 13px; text-align: right; padding-right: 10px; }}
  .bar-fill {{ height: 22px; border-radius: 3px; display: inline-block; min-width: 2px; }}
  .bar-val {{ font-size: 12px; padding-left: 6px; color: white; }}
  .status-pass {{ background: {ceph_green}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-fail {{ background: {ceph_primary}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-skip {{ background: {ceph_accent}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-unknown {{ background: {ceph_gray}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .arm64-table {{ border: 2px solid {ceph_accent}; }}
  .arm64-table th {{ background: {ceph_accent}; }}
  footer {{ text-align: center; padding: 20px; color: {ceph_gray}; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Ceph ARM64 Performance Benchmark</h1>
    <div class="subtitle">Distributed Storage System - Object, Block, and File Storage</div>
    <div class="version">Ceph v{version} | {timestamp}</div>
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

  {rados_section}

  {rbd_section}

  {cephfs_section}

  {micro_section}

  {arm64_section}

  <section id="shunit2">
    <h2>shUnit2 Test Validation</h2>
    <p class="benchmark-ref">Automated validation via shUnit2 test suite with ARM64 assertions</p>
    <p>See <code>ceph_test.sh</code> for full test definitions</p>
    <table>
      <tr><th>Test Category</th><th>Tests</th></tr>
      {shunit2_rows}
    </table>
  </section>

  <footer>
    Generated by Ceph ARM64 Performance Benchmark Workflow | {timestamp}
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
