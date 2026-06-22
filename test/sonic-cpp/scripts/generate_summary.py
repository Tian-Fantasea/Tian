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
        print('[SUMMARY] Input JSON not found')
        return

    with open(input_json, 'r') as f:
        all_data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("sonic-cpp ARM64 Performance Benchmark Summary")
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
        lines.append(f"G++ Version:        {vi.get('runtime_version', 'N/A')}")
        lines.append(f"sonic-cpp Version:  {vi.get('version', 'N/A')}")
        lines.append(f"sonic-cpp Home:     {vi.get('home', 'N/A')}")
        lines.append(f"sonic-cpp Git:      {vi.get('runtime_detail', 'N/A')}")
        lines.append(f"Parallelism:        {vi.get('parallelism', 'N/A')}")
        extra = vi.get('extra_info', {})
        if extra:
            lines.append(f"Compile Flags:      {extra.get('compile_flags', 'N/A')}")
            lines.append(f"Compile Test:       {extra.get('compile_test', 'N/A')}")
            lines.append(f"JSON Sizes:         {extra.get('json_sizes', 'N/A')}")
            lines.append(f"Min Parse TP:       {extra.get('minimum_parse_throughput', 'N/A')} MB/s")
            lines.append(f"Min Serialize TP:   {extra.get('minimum_serialize_throughput', 'N/A')} MB/s")
        lines.append("")

    primary = all_data.get('primary_benchmark', {})
    if primary:
        lines.append("--- JSON Parse Throughput (Phase 3a) ---")
        lines.append(f"Reference: {primary.get('reference', 'N/A')}")
        for result in primary.get('results', []):
            if result.get('test') == 'parse_throughput_vs_size':
                for d in result.get('data', []):
                    size = d.get('json_size', 'N/A')
                    tp = d.get('avg_throughput_mb_per_sec', 0)
                    lat = d.get('avg_latency_ms', 0)
                    bytes_sz = d.get('json_bytes', 0)
                    lines.append(f"  {size} ({bytes_sz} bytes): {tp:.2f} MB/s, {lat:.2f} ms")
        lines.append("")

    secondary = all_data.get('secondary_benchmark', {})
    if secondary:
        lines.append("--- JSON Serialize + ParseOnDemand (Phase 3b) ---")
        lines.append(f"Reference: {secondary.get('reference', 'N/A')}")
        for result in secondary.get('results', []):
            test_name = result.get('test', '')
            for d in result.get('data', []):
                size = d.get('json_size', 'N/A')
                tp = d.get('avg_throughput_mb_per_sec', 0)
                lat = d.get('avg_latency_ms', 0)
                if test_name == 'serialize_throughput_vs_size':
                    lines.append(f"  Serialize {size}: {tp:.2f} MB/s, {lat:.2f} ms")
                elif test_name == 'ondemand_key_lookup_vs_size':
                    key = d.get('target_key', 'N/A')
                    lines.append(f"  OnDemand '{key}' {size}: {tp:.2f} MB/s, {lat:.2f} ms")
        lines.append("")

    micro = all_data.get('micro_benchmark', {})
    if micro:
        lines.append("--- Micro Benchmarks (Phase 3c) ---")
        for result in micro.get('results', []):
            if result.get('test') == 'optimization_vs_simd_comparison':
                for d in result.get('data', []):
                    config = d.get('configuration', 'N/A')
                    tp = d.get('avg_throughput_mb_per_sec', 0)
                    lat = d.get('avg_latency_ms', 0)
                    lines.append(f"  {config}: {tp:.2f} MB/s, {lat:.2f} ms")
            elif result.get('test') == 'arm64_simd_detection':
                data = result.get('data', {})
                lines.append("  ARM64 SIMD Features:")
                lines.append(f"    NEON:       {data.get('neon', 'N/A')}")
                lines.append(f"    ASIMD:      {data.get('asimd', 'N/A')}")
                lines.append(f"    SVE:        {data.get('sve', 'N/A')}")
                lines.append(f"    aarch64:    {data.get('aarch64', 'N/A')}")
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
