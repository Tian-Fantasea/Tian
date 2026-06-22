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


def make_bar_chart(items, chart_id, max_val=None, color="#ee4c2c"):
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
    parser = argparse.ArgumentParser(description="Generate HTML report for PyTorch benchmarks")
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

    pt_primary = "#ee4c2c"
    pt_dark = "#c05621"
    pt_blue = "#4285f4"
    pt_green = "#34a853"
    pt_gray = "#7f8c8d"

    env_fields = [
        ("Architecture", vi.get("architecture", "unknown")),
        ("CPU Model", vi.get("cpu_model", "unknown")),
        ("CPU Cores", str(vi.get("cores", "unknown"))),
        ("Memory", fmt_val(vi.get("memory_mb", 0), "MB", 0)),
        ("Operating System", vi.get("os", "unknown")),
        ("Kernel", vi.get("kernel", "unknown")),
        ("PyTorch Version", version),
        ("Python", vi.get("python_version", "unknown")),
        ("NumPy", vi.get("numpy_version", "unknown")),
        ("CUDA Available", str(vi.get("cuda_available", "unknown"))),
        ("torch Threads", str(vi.get("torch_num_threads", "unknown"))),
        ("torch.compile", str(vi.get("has_compile", "unknown"))),
    ]
    env_rows = ""
    for label, value in env_fields:
        env_rows += f"<tr><td class='env-label'>{label}</td><td class='env-value'>{value}</td></tr>\n"

    card_items = []
    compute = data.get("compute_benchmark", {})
    compute_r = compute.get("results", {})
    matmul_items = [(n, r.get("avg_time_ms", 0)) for n, r in compute_r.items() if n.startswith("matmul") and "error" not in r]
    if matmul_items:
        best_matmul = min(matmul_items, key=lambda x: x[1])
        card_items.append(("Best Matmul Time", f"{best_matmul[1]}ms"))

    training = data.get("training_benchmark", {})
    training_r = training.get("results", {})
    train_throughputs = [(n, r.get("throughput", 0)) for n, r in training_r.items() if r.get("mode") == "training" and "error" not in r]
    if train_throughputs:
        best_train = max(train_throughputs, key=lambda x: x[1])
        card_items.append(("Best Training Throughput", f"{best_train[1]} {training_r[best_train[0]].get('unit', 'N/A')}"))

    metrics_cards = ""
    card_colors = [pt_primary, pt_blue, pt_green, pt_dark]
    for i, (name, value) in enumerate(card_items):
        color = card_colors[i % len(card_colors)]
        metrics_cards += (
            f'<div class="metric-card" style="border-top:3px solid {color};">'
            f'<div class="metric-name">{name}</div>'
            f'<div class="metric-value">{value}</div>'
            f'</div>\n'
        )

    compute_section = ""
    if compute:
        matmul_chart = make_bar_chart(matmul_items, "compute_matmul", color=pt_primary)
        matmul_tflops = [(n, r.get("tflops", 0)) for n, r in compute_r.items() if n.startswith("matmul") and "tflops" in r]
        tflops_chart = make_bar_chart(matmul_tflops, "compute_tflops", color=pt_green)
        other_items = [(n, r.get("avg_time_ms", 0)) for n, r in compute_r.items() if not n.startswith("matmul") and "error" not in r]
        other_chart = make_bar_chart(other_items, "compute_other", color=pt_blue)

        compute_tables = ""
        if matmul_items:
            rows = ""
            for n, r in compute_r.items():
                if n.startswith("matmul") and "error" not in r:
                    rows += f"<tr><td>{n}</td><td>{r.get('avg_time_ms', 'N/A')}</td><td>{r.get('tflops', 'N/A')}</td></tr>\n"
            compute_tables += f'<h3>Matmul Results</h3>{matmul_chart}{tflops_chart}<table><tr><th>Operator</th><th>Time (ms)</th><th>TFLOPS</th></tr>{rows}</table>'
        if other_items:
            rows = ""
            for n, r in compute_r.items():
                if not n.startswith("matmul") and "error" not in r:
                    rows += f"<tr><td>{n}</td><td>{r.get('avg_time_ms', 'N/A')}</td><td>-</td></tr>\n"
            compute_tables += f'<h3>Other Operators</h3>{other_chart}<table><tr><th>Operator</th><th>Time (ms)</th></tr>{rows}</table>'

        compute_section = (
            f'<section id="compute"><h2>Operator Compute Benchmark</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://pytorch.org/docs/stable/torch.html">PyTorch ops</a></p>'
            f'{compute_tables}</section>'
        )

    training_section = ""
    if training:
        model_configs = training.get("model_configs", {})
        training_tables = ""
        for model_name, model_info in model_configs.items():
            unit = model_info.get("unit", "N/A")
            train_items = [(f"bs={r.get('batch_size', '?')}", r.get("throughput", 0)) for n, r in training_r.items() if n.startswith(model_name) and r.get("mode") == "training" and "error" not in r]
            inf_items = [(f"bs={r.get('batch_size', '?')}", r.get("throughput", 0)) for n, r in training_r.items() if n.startswith(model_name) and r.get("mode") == "inference" and "error" not in r]
            if train_items:
                training_tables += make_bar_chart([(l, v) for l, v in train_items], f"train_{model_name}", color=pt_primary)
            if inf_items:
                training_tables += make_bar_chart([(l, v) for l, v in inf_items], f"inf_{model_name}", color=pt_blue)

        rows = ""
        for name, res in training_r.items():
            if "error" in res:
                rows += f'<tr><td>{name}</td><td>{res.get("mode","?")}</td><td>{res.get("batch_size","?")}</td><td style="color:#e74c3c">ERROR</td><td>-</td><td>-</td></tr>\n'
            else:
                rows += f'<tr><td>{name}</td><td>{res.get("mode","?")}</td><td>{res.get("batch_size","?")}</td><td>{res.get("avg_time_ms","N/A")}</td><td>{res.get("throughput","N/A")}</td><td>{res.get("unit","N/A")}</td></tr>\n'
        training_tables += f'<h3>Detailed Results</h3><table><tr><th>Model+Batch</th><th>Mode</th><th>Batch</th><th>Time (ms)</th><th>Throughput</th><th>Unit</th></tr>{rows}</table>'

        training_section = (
            f'<section id="training"><h2>Training & Inference Throughput</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://mlcommons.org/en/mlperf-training">MLPerf</a></p>'
            f'{training_tables}</section>'
        )

    micro_section = ""
    micro = data.get("micro_benchmark", {})
    if micro:
        mresults = micro.get("results", {})
        micro_tables = ""

        if "compile_speed" in mresults:
            cs = mresults["compile_speed"]
            if "eager_vs_compile_eager" in cs:
                ev = cs["eager_vs_compile_eager"]
                micro_tables += f'<div class="metric-card" style="border-top:3px solid {pt_green};"><div class="metric-name">torch.compile Speedup</div><div class="metric-value">{ev.get("speedup", "N/A")}x</div></div>'

        if "tensor_creation" in mresults:
            tc_items = [(name, res.get("avg_time_ms", 0)) for name, res in mresults["tensor_creation"].items()]
            micro_tables += make_bar_chart(tc_items, "micro_tensor", color=pt_primary)

        if "memory_transfer" in mresults:
            mt_items = [(name, res.get("copy_rate_MB_per_sec", 0)) for name, res in mresults["memory_transfer"].items()]
            micro_tables += make_bar_chart(mt_items, "micro_memory", color=pt_blue)

        if "dtype_conversion" in mresults:
            dc_items = [(name, res.get("conversion_rate_Melements_per_sec", 0)) for name, res in mresults["dtype_conversion"].items()]
            micro_tables += make_bar_chart(dc_items, "micro_dtype", color=pt_green)

        rows = ""
        for op_name, res in mresults.items():
            rows += f'<tr><td>{op_name}</td><td>{json.dumps(res)}</td></tr>\n'
        micro_tables += f'<h3>Detailed Results</h3><table><tr><th>Operation</th><th>Results</th></tr>{rows}</table>'

        micro_section = (
            f'<section id="micro"><h2>Micro Benchmarks</h2>'
            f'<p class="benchmark-ref">Reference: <a href="https://pytorch.org">PyTorch</a></p>'
            f'{micro_tables}</section>'
        )

    arm64 = vi.get("arm64_features", {})
    arm64_rows = ""
    arm64_items = [
        ("ARM64 Architecture", str(arm64.get("is_arm64", "unknown"))),
        ("NEON Available", str(arm64.get("neon_available", "unknown"))),
        ("CUDA Available", str(arm64.get("cuda_available", "unknown"))),
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
        ("PyTorch Installation", "testPytorchIsInstalled"),
        ("Version Info", "testResultsJsonHasVersionInfo, testResultsJsonHasArchitecture, testResultsJsonHasSoftwareVersion"),
        ("Compute Benchmark", "testBenchmarkComputeInResultsJson, testBenchmarkComputeHasRequiredFields"),
        ("Training Benchmark", "testBenchmarkTrainingInResultsJson"),
        ("Micro Benchmark", "testBenchmarkMicroInResultsJson, testBenchmarkMicroAllOperationsCompleted"),
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
<title>PyTorch ARM64 Performance Benchmark Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  header {{ background: linear-gradient(135deg, {pt_primary}, {pt_dark}); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header .subtitle {{ font-size: 14px; opacity: 0.9; }}
  header .version {{ font-size: 16px; margin-top: 4px; }}
  .env-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: white; border-radius: 8px; overflow: hidden; }}
  .env-table td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
  .env-label {{ width: 30%; font-weight: 600; color: {pt_dark}; background: #fafafa; }}
  .env-value {{ width: 70%; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }}
  .metric-card {{ background: white; padding: 15px; border-radius: 6px; text-align: center; }}
  .metric-name {{ font-size: 12px; color: {pt_gray}; margin-bottom: 6px; text-transform: uppercase; }}
  .metric-value {{ font-size: 20px; font-weight: 700; color: #333; }}
  section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px; }}
  section h2 {{ color: {pt_dark}; border-bottom: 2px solid {pt_primary}; padding-bottom: 8px; margin-bottom: 15px; }}
  section h3 {{ color: {pt_dark}; margin: 15px 0 10px; }}
  .benchmark-ref {{ font-size: 13px; color: {pt_gray}; margin-bottom: 15px; }}
  .benchmark-ref a {{ color: {pt_blue}; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 20px; }}
  th {{ background: {pt_primary}; color: white; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
  .bar-chart {{ margin: 15px 0; }}
  .bar-row {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 150px; font-size: 13px; text-align: right; padding-right: 10px; }}
  .bar-fill {{ height: 22px; border-radius: 3px; display: inline-block; min-width: 2px; }}
  .bar-val {{ font-size: 12px; padding-left: 6px; color: white; }}
  .status-pass {{ background: {pt_green}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-fail {{ background: {pt_primary}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .status-unknown {{ background: {pt_gray}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
  .arm64-table {{ border: 2px solid {pt_primary}; }}
  .arm64-table th {{ background: {pt_primary}; }}
  footer {{ text-align: center; padding: 20px; color: {pt_gray}; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>PyTorch ARM64 Performance Benchmark</h1>
    <div class="subtitle">Deep Learning Framework - Operator Compute, Training, and Micro Benchmarks</div>
    <div class="version">PyTorch v{version} | {timestamp}</div>
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

  {compute_section}

  {training_section}

  {micro_section}

  {arm64_section}

  <section id="shunit2">
    <h2>shUnit2 Test Validation</h2>
    <p class="benchmark-ref">Automated validation via shUnit2 test suite with ARM64 assertions</p>
    <p>See <code>pytorch_test.sh</code> for full test definitions</p>
    <table>
      <tr><th>Test Category</th><th>Tests</th></tr>
      {shunit2_rows}
    </table>
  </section>

  <footer>
    Generated by PyTorch ARM64 Performance Benchmark Workflow | {timestamp}
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
