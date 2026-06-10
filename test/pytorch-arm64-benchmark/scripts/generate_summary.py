#!/usr/bin/env python3
import json
import os
import argparse
import datetime

def main():
    parser = argparse.ArgumentParser(description='Generate text summary of benchmark results')
    parser.add_argument('--results-dir', required=True)
    args = parser.parse_args()

    all_results_path = os.path.join(args.results_dir, 'all_results.json')
    if not os.path.exists(all_results_path):
        print('[SUMMARY] all_results.json not found')
        return

    with open(all_results_path, 'r') as f:
        all_data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("PyTorch ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
    lines.append("")

    vi = all_data.get('version_info.json', {})
    if vi:
        lines.append("--- Environment ---")
        lines.append(f"Architecture:      {vi.get('architecture', 'N/A')}")
        lines.append(f"OS:                {vi.get('os', 'N/A')}")
        lines.append(f"Kernel:            {vi.get('kernel', 'N/A')}")
        lines.append(f"CPU:               {vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)")
        lines.append(f"Memory:            {vi.get('total_memory_gb', 'N/A')} GB")
        lines.append(f"PyTorch Version:   {vi.get('pytorch_version', 'N/A')}")
        lines.append(f"Python:            {vi.get('python_version', 'N/A')}")
        lines.append(f"CUDA:              {vi.get('cuda_available', 'N/A')}")
        lines.append(f"torch threads:     {vi.get('torch_num_threads', 'N/A')}")
        lines.append(f"torch.compile:     {vi.get('has_compile', 'N/A')}")
        lines.append(f"SIMD:              {vi.get('simd_info', 'N/A')}")
        lines.append("")

    compute = all_data.get('benchmark_compute.json', {})
    if compute:
        lines.append("--- Operator Compute Benchmark ---")
        lines.append(f"Reference: {compute.get('reference', 'N/A')}")
        for name, res in compute.get('results', {}).items():
            if "error" in res:
                lines.append(f"  {name}: ERROR - {res['error']}")
            elif "tflops" in res:
                lines.append(f"  {name}: {res['avg_time_ms']}ms, {res['tflops']} TFLOPS")
            else:
                lines.append(f"  {name}: {res['avg_time_ms']}ms")
        lines.append("")

    training = all_data.get('benchmark_training.json', {})
    if training:
        lines.append("--- Training & Inference Benchmark ---")
        lines.append(f"Reference: {training.get('reference', 'N/A')}")
        for name, res in training.get('results', {}).items():
            if "error" in res:
                lines.append(f"  {name}: ERROR - {res['error']}")
            else:
                lines.append(f"  {name}: {res['avg_time_ms']}ms, {res['throughput']} {res.get('unit', 'N/A')} ({res.get('mode', 'N/A')})")
        lines.append("")

    micro = all_data.get('benchmark_micro.json', {})
    if micro:
        lines.append("--- Micro Benchmarks ---")
        lines.append(f"Reference: {micro.get('reference', 'N/A')}")
        for op_name, res in micro.get('results', {}).items():
            lines.append(f"  {op_name}: {json.dumps(res)}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_text = '\n'.join(lines)
    output_path = os.path.join(args.results_dir, 'benchmark_summary.txt')
    with open(output_path, 'w') as f:
        f.write(summary_text)

    print(summary_text)
    print(f'[SUMMARY] Saved to {output_path}')

if __name__ == '__main__':
    main()