#!/usr/bin/env python3
import json
import os
import sys
import datetime


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_summary.py <input_json> <output_txt>")
        sys.exit(1)

    input_json = sys.argv[1]
    output_txt = sys.argv[2]

    if not os.path.exists(input_json):
        print('[SUMMARY] Input JSON not found, cannot generate summary')
        return

    with open(input_json, 'r') as f:
        all_data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("ScaNN ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    lines.append("")

    vi = all_data.get('version_info', {})
    if vi:
        lines.append("--- Environment ---")
        lines.append(f"Architecture:       {vi.get('architecture', 'N/A')}")
        lines.append(f"OS:                 {vi.get('os', 'N/A')}")
        lines.append(f"Kernel:             {vi.get('kernel', 'N/A')}")
        lines.append(f"CPU:                {vi.get('cpu_model', 'N/A')} ({vi.get('cpu_cores', 'N/A')} cores)")
        lines.append(f"Memory:             {vi.get('total_memory_mb', 'N/A')} MB")
        lines.append(f"ScaNN Version:      {vi.get('scann_version', 'N/A')}")
        lines.append(f"Python:             {vi.get('python_version', 'N/A')}")
        lines.append(f"NumPy:              {vi.get('numpy_version', 'N/A')}")
        lines.append(f"NEON Support:       {vi.get('neon_support', 'N/A')}")
        lines.append("")

    ann = all_data.get('primary_benchmark', {})
    if ann:
        lines.append("--- ANN Search Benchmark ---")
        lines.append(f"Reference: {ann.get('reference', 'N/A')}")
        results = ann.get('results_summary', {})
        k_val = 10
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
        lines.append("")

    micro = all_data.get('micro_benchmark', {})
    if micro:
        lines.append("--- Micro Benchmarks ---")
        lines.append(f"Reference: {micro.get('reference', 'N/A')}")
        mresults = micro.get('results', {})
        for op_name, res in mresults.items():
            if isinstance(res, dict):
                lines.append(f"  {op_name}: {json.dumps(res)}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_text = '\n'.join(lines)
    os.makedirs(os.path.dirname(output_txt) or '.', exist_ok=True)
    with open(output_txt, 'w') as f:
        f.write(summary_text)

    print(summary_text)
    print(f'[SUMMARY] Saved to {output_txt}')


if __name__ == '__main__':
    main()
