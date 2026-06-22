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
        print('[SUMMARY] all_results.json not found, cannot generate summary')
        return

    with open(all_results_path, 'r') as f:
        all_data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("ScaNN ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
    lines.append("")

    vi = all_data.get('version_info.json', {})
    if vi:
        lines.append("--- Environment ---")
        lines.append(f"Architecture:       {vi.get('architecture', 'N/A')}")
        lines.append(f"OS:                 {vi.get('os', 'N/A')}")
        lines.append(f"Kernel:             {vi.get('kernel', 'N/A')}")
        lines.append(f"CPU:                {vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)")
        lines.append(f"Memory:             {vi.get('total_memory_gb', 'N/A')} GB")
        lines.append(f"ScaNN Version:      {vi.get('scann_version', 'N/A')}")
        lines.append(f"Python:             {vi.get('python_version', 'N/A')}")
        lines.append(f"NumPy:              {vi.get('numpy_version', 'N/A')}")
        lines.append(f"NEON Support:       {vi.get('neon_support', 'N/A')}")
        lines.append(f"libstdc++:          {vi.get('libstdcxx_version', 'N/A')}")
        lines.append(f"Pybind API:         {vi.get('scann_has_pybind', 'N/A')}")
        lines.append(f"TF Ops:             {vi.get('scann_has_tf_ops', 'N/A')}")
        lines.append("")

    ann = all_data.get('benchmark_ann.json', {})
    if ann:
        lines.append("--- ANN Search Benchmark ---")
        lines.append(f"Reference: {ann.get('reference', 'N/A')}")
        params = ann.get('parameters', {})
        k_val = params.get('k', 10)
        lines.append(f"Dataset: {params.get('num_vectors', 'N/A')} vectors, {params.get('dimension', 'N/A')} dims, k={k_val}")
        lines.append("")
        results = ann.get('results_summary', {})
        for config_name, res in results.items():
            if isinstance(res, dict) and "error" in res:
                lines.append(f"  {config_name}: ERROR - {res['error']}")
            elif isinstance(res, dict) and "qps" in res:
                recall_key = f"recall_at_{k_val}"
                lines.append(f"  {config_name}:")
                lines.append(f"    QPS:              {res.get('qps', 'N/A')}")
                lines.append(f"    Recall@{k_val}:       {res.get(recall_key, 'N/A')}")
                lines.append(f"    Build time:       {res.get('build_time_s', 'N/A')}s")
                lines.append(f"    Latency/query:    {res.get('latency_per_query_us', 'N/A')} us")
            elif isinstance(res, dict):
                lines.append(f"  {config_name}:")
                for sub_name, sub_res in res.items():
                    if isinstance(sub_res, dict):
                        recall_key = f"avg_recall_at_{k_val}"
                        lines.append(f"    {sub_name}: QPS={sub_res.get('avg_qps', 'N/A')}, Recall@{k_val}={sub_res.get(recall_key, 'N/A')}")
        lines.append("")

    micro = all_data.get('benchmark_micro.json', {})
    if micro:
        lines.append("--- Micro Benchmarks ---")
        lines.append(f"Reference: {micro.get('reference', 'N/A')}")
        mparams = micro.get('parameters', {})
        lines.append(f"Dataset: {mparams.get('num_vectors', 'N/A')} vectors, {mparams.get('dimension', 'N/A')} dims")
        lines.append("")
        results = micro.get('results', {})
        for op_name, res in results.items():
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