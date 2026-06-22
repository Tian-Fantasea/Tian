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
    lines.append("zstd ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append("Generated: %s" % datetime.datetime.now(datetime.timezone.utc).isoformat())
    lines.append("")

    vi = all_data.get('version_info', {})
    if vi:
        lines.append("--- Environment ---")
        lines.append("Architecture:       %s" % vi.get('architecture', 'N/A'))
        lines.append("OS:                 %s" % vi.get('os', 'N/A'))
        lines.append("Kernel:             %s" % vi.get('kernel', 'N/A'))
        lines.append("CPU:                %s (%s cores)" % (vi.get('cpu_model', 'N/A'), vi.get('cpu_cores', 'N/A')))
        lines.append("Memory:             %s MB" % vi.get('total_memory_mb', 'N/A'))
        lines.append("zstd Version:       %s" % vi.get('runtime_version', 'N/A'))
        lines.append("zstd Path:          %s" % vi.get('home', 'N/A'))
        lines.append("GCC Version:        %s" % vi.get('runtime_detail', 'N/A'))
        lines.append("Parallelism:        %s" % vi.get('parallelism', 'N/A'))
        extra = vi.get('extra_info', {})
        if extra:
            lines.append("GCC Available:      %s" % extra.get('gcc_available', 'N/A'))
            lines.append("Compression Levels: %s" % extra.get('compression_levels', 'N/A'))
            lines.append("Data Size:          %s MB" % extra.get('data_size_mb', 'N/A'))
            lines.append("Data Types:         %s" % extra.get('data_types', 'N/A'))
        lines.append("")

    primary = all_data.get('primary_benchmark', {})
    if primary:
        lines.append("--- Compression Performance Benchmark (Phase 3a) ---")
        lines.append("Reference: %s" % primary.get('reference', 'N/A'))
        for result in primary.get('results', []):
            if result.get('test') == 'compression_throughput_vs_level':
                for d in result.get('data', []):
                    level = d.get('compression_level', 'N/A')
                    throughput = d.get('avg_compression_throughput_mb_s', 0)
                    time_sec = d.get('avg_compression_time_sec', 0)
                    lines.append("  Level %s: %.2f MB/s, %.4f sec" % (level, throughput, time_sec))
            elif result.get('test') == 'compression_ratio_vs_level':
                for d in result.get('data', []):
                    level = d.get('compression_level', 'N/A')
                    ratio = d.get('avg_compression_ratio', 0)
                    lines.append("  Level %s ratio: %.3f" % (level, ratio))
        lines.append("")

    secondary = all_data.get('secondary_benchmark', {})
    if secondary:
        lines.append("--- Decompression Performance Benchmark (Phase 3b) ---")
        lines.append("Reference: %s" % secondary.get('reference', 'N/A'))
        for result in secondary.get('results', []):
            if result.get('test') == 'decompression_throughput_vs_level':
                for d in result.get('data', []):
                    level = d.get('compression_level', 'N/A')
                    throughput = d.get('avg_decompression_throughput_mb_s', 0)
                    time_ms = d.get('avg_decompression_time_ms', 0)
                    lines.append("  Level %s: %.2f MB/s, %.2f ms" % (level, throughput, time_ms))
            elif result.get('test') == 'streaming_decompression_vs_level':
                for d in result.get('data', []):
                    level = d.get('compression_level', 'N/A')
                    throughput = d.get('avg_streaming_decompress_throughput_mb_s', 0)
                    lines.append("  Level %s streaming: %.2f MB/s" % (level, throughput))
        lines.append("")

    micro = all_data.get('micro_benchmark', {})
    if micro:
        lines.append("--- Micro Benchmarks (Phase 3c) ---")
        for result in micro.get('results', []):
            if result.get('test') == 'single_block_api_latency':
                for d in result.get('data', []):
                    level = d.get('level', 'N/A')
                    c_tp = d.get('avg_compress_throughput_mb_s', 0)
                    d_tp = d.get('avg_decompress_throughput_mb_s', 0)
                    ratio = d.get('avg_ratio', 0)
                    lines.append("  API Level %s: %.2f MB/s compress, %.2f MB/s decompress, ratio %.3f" % (level, c_tp, d_tp, ratio))
            elif result.get('test') == 'dictionary_compression':
                d = result.get('data', {})
                if isinstance(d, dict):
                    lines.append("  Dict compress: %.2f MB/s, ratio %.3f" % (d.get('avg_dict_compress_throughput_mb_s', 0), d.get('avg_dict_ratio', 0)))
            elif result.get('test') == 'arm64_optimization_detection':
                data = result.get('data', {})
                lines.append("  ARM64 Features:")
                lines.append("    NEON:           %s" % data.get('neon', 'N/A'))
                lines.append("    SVE:            %s" % data.get('sve', 'N/A'))
                lines.append("    LSE Atomics:    %s" % data.get('lse_atomics', 'N/A'))
                lines.append("    CRC32:          %s" % data.get('crc32', 'N/A'))
                lines.append("    zstd NEON Opt:  %s" % data.get('zstd_neon_optimization', 'N/A'))
        lines.append("")

    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_text = '\n'.join(lines)
    os.makedirs(os.path.dirname(output_txt) or '.', exist_ok=True)
    with open(output_txt, 'w') as f:
        f.write(summary_text)

    print(summary_text)
    print('[SUMMARY] Saved to %s' % output_txt)


if __name__ == '__main__':
    main()
