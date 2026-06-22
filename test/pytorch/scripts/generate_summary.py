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


def format_metric(value, unit="", precision=2):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f} {unit}"
    if isinstance(value, int):
        return f"{value} {unit}"
    return f"{value} {unit}"


def main():
    parser = argparse.ArgumentParser(description="Generate text summary for PyTorch benchmarks")
    parser.add_argument("--input", required=True, help="Path to results.json")
    parser.add_argument("--output", required=True, help="Path to results.txt")
    args = parser.parse_args()

    data = load_or_create_json(args.input)
    if not data:
        with open(args.output, "w") as f:
            f.write("ERROR: No results.json found\n")
        return 1

    vi = data.get("version_info", {})
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    version = data.get("version", "unknown")

    lines = []
    lines.append("=" * 80)
    lines.append("  PyTorch ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append(f"  Software:      PyTorch v{version}")
    lines.append(f"  Date:          {timestamp}")
    lines.append(f"  Architecture:  {vi.get('architecture', 'unknown')}")
    lines.append(f"  CPU:           {vi.get('cpu_model', 'unknown')} ({vi.get('cores', 'unknown')} cores)")
    lines.append(f"  Memory:        {format_metric(vi.get('memory_mb', 0), 'MB', 0)}")
    lines.append(f"  OS:            {vi.get('os', 'unknown')}")
    lines.append(f"  Kernel:        {vi.get('kernel', 'unknown')}")
    lines.append(f"  Python:        {vi.get('python_version', 'unknown')}")
    lines.append(f"  NumPy:         {vi.get('numpy_version', 'unknown')}")
    lines.append(f"  CUDA:          {vi.get('cuda_available', 'unknown')}")
    lines.append(f"  torch threads: {vi.get('torch_num_threads', 'unknown')}")
    lines.append(f"  torch.compile: {vi.get('has_compile', 'unknown')}")
    arm64 = vi.get("arm64_features", {})
    if arm64:
        lines.append(f"  ARM64 NEON:    {arm64.get('neon_available', 'unknown')}")
    lines.append("=" * 80)

    compute = data.get("compute_benchmark", {})
    if compute:
        lines.append("")
        lines.append("  OPERATOR COMPUTE BENCHMARK")
        lines.append("-" * 80)
        lines.append(f"  Reference: {compute.get('reference', 'N/A')}")
        for name, res in compute.get("results", {}).items():
            if "error" in res:
                lines.append(f"    {name}: ERROR - {res['error']}")
            elif "tflops" in res:
                lines.append(f"    {name}: {res['avg_time_ms']}ms, {res['tflops']} TFLOPS")
            else:
                lines.append(f"    {name}: {res['avg_time_ms']}ms")

    training = data.get("training_benchmark", {})
    if training:
        lines.append("")
        lines.append("  TRAINING & INFERENCE BENCHMARK")
        lines.append("-" * 80)
        lines.append(f"  Reference: {training.get('reference', 'N/A')}")
        for name, res in training.get("results", {}).items():
            if "error" in res:
                lines.append(f"    {name}: ERROR - {res['error']}")
            else:
                lines.append(f"    {name}: {res['avg_time_ms']}ms, {res['throughput']} {res.get('unit', 'N/A')} ({res.get('mode', 'N/A')})")

    micro = data.get("micro_benchmark", {})
    if micro:
        lines.append("")
        lines.append("  MICRO BENCHMARKS")
        lines.append("-" * 80)
        lines.append(f"  Reference: {micro.get('reference', 'N/A')}")
        for op_name, res in micro.get("results", {}).items():
            lines.append(f"    {op_name}: {json.dumps(res)}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  ARM64 OPTIMIZATION HIGHLIGHTS")
    lines.append("=" * 80)
    arm64 = vi.get("arm64_features", {})
    if arm64:
        lines.append(f"  ARM64 Architecture:   {arm64.get('is_arm64', 'unknown')}")
        lines.append(f"  NEON Available:       {arm64.get('neon_available', 'unknown')}")
        lines.append(f"  CUDA Available:       {arm64.get('cuda_available', 'unknown')}")
    else:
        lines.append("  (ARM64 optimization data not available)")
    lines.append("=" * 80)

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Text summary saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
