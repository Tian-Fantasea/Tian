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
    lines.append("GCC ARM64 Performance Benchmark Summary")
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
        lines.append(f"GCC Version:        {vi.get('runtime_version', 'N/A')}")
        lines.append(f"GCC Target:         {vi.get('home', 'N/A')}")
        lines.append(f"GCC Dumpversion:    {vi.get('runtime_detail', 'N/A')}")
        lines.append(f"Parallelism:        {vi.get('parallelism', 'N/A')}")
        extra = vi.get('extra_info', {})
        if extra:
            lines.append(f"g++ Available:      {extra.get('gpp_available', 'N/A')}")
            lines.append(f"g++ Version:        {extra.get('gpp_version', 'N/A')}")
            lines.append(f"Opt Levels:         {extra.get('opt_levels', 'N/A')}")
            lines.append(f"Benchmark Programs: {extra.get('benchmark_programs', 'N/A')}")
        lines.append("")

    primary = all_data.get('primary_benchmark', {})
    if primary:
        lines.append("--- Compile Speed Benchmark (Phase 3a) ---")
        lines.append(f"Reference: {primary.get('reference', 'N/A')}")
        for result in primary.get('results', []):
            if result.get('test') == 'compile_throughput_vs_optimization':
                for d in result.get('data', []):
                    opt = d.get('optimization_level', 'N/A')
                    throughput = d.get('avg_throughput_files_per_sec', 0)
                    compile_time = d.get('avg_compile_time_sec', 0)
                    lines.append(f"  -{opt}: {throughput:.2f} files/sec, {compile_time:.4f} sec/file")
            elif result.get('test') == 'c_vs_cpp_compile_time':
                for d in result.get('data', []):
                    if 'language' in d:
                        lines.append(f"  {d['language']} @ O2: {d.get('avg_compile_time_sec', 0):.4f} sec, "
                                     f"{d.get('avg_throughput_files_per_sec', 0):.2f} files/sec")
                    elif 'cpp_vs_c_ratio' in d:
                        lines.append(f"  C++/C compile ratio: {d['cpp_vs_c_ratio']}")
        lines.append("")

    secondary = all_data.get('secondary_benchmark', {})
    if secondary:
        lines.append("--- Generated Code Performance Benchmark (Phase 3b) ---")
        lines.append(f"Reference: {secondary.get('reference', 'N/A')}")
        for result in secondary.get('results', []):
            if result.get('test') == 'execution_throughput_vs_optimization':
                for d in result.get('data', []):
                    bench = d.get('benchmark', 'N/A')
                    opt = d.get('optimization', 'N/A')
                    throughput = d.get('avg_throughput_ops_per_sec', 0)
                    time_ms = d.get('avg_time_ms', 0)
                    lines.append(f"  {bench} -{opt}: {throughput:.2f} ops/sec, {time_ms:.2f} ms")
            elif result.get('test') == 'optimization_speedup':
                for d in result.get('data', []):
                    bench = d.get('benchmark', 'N/A')
                    for key, val in d.items():
                        if key != 'benchmark' and isinstance(val, (int, float)):
                            lines.append(f"  {bench} {key}: {val}")
        lines.append("")

    micro = all_data.get('micro_benchmark', {})
    if micro:
        lines.append("--- Micro Benchmarks (Phase 3c) ---")
        for result in micro.get('results', []):
            if result.get('test') == 'compiler_component_speed':
                for d in result.get('data', []):
                    comp = d.get('component', 'N/A')
                    ms = d.get('avg_time_ms', 0)
                    tp = d.get('avg_throughput_files_per_sec', 0)
                    lines.append(f"  {comp}: {ms:.2f} ms, {tp:.2f} files/sec")
            elif result.get('test') == 'arm64_optimization_detection':
                data = result.get('data', {})
                lines.append("  ARM64 Features:")
                lines.append(f"    NEON:           {data.get('neon', 'N/A')}")
                lines.append(f"    SVE:            {data.get('sve', 'N/A')}")
                lines.append(f"    LSE Atomics:    {data.get('lse_atomics', 'N/A')}")
                lines.append(f"    CRC32:          {data.get('crc32', 'N/A')}")
                lines.append(f"    Auto Vec O3:    {data.get('auto_vectorization_O3', 'N/A')}")
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
