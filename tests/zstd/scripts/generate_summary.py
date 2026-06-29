#!/usr/bin/env python3
import sys
import json
from datetime import datetime, timezone


def generate_summary(input_json, output_file):
    with open(input_json) as f:
        data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("  ZSTD Source Build & Performance Benchmark Report")
    lines.append("=" * 70)
    lines.append(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"  Test Time: {data.get('test_time', data.get('timestamp', 'N/A'))}")
    lines.append("")

    env = data.get("environment", {})
    if env:
        lines.append("  --- Environment ---")
        lines.append(f"  Architecture:      {env.get('architecture', 'N/A')}")
        lines.append(f"  Model:             {env.get('Model', 'N/A')}")
        lines.append(f"  CPU Model:         {env.get('cpu_model', 'N/A')}")
        lines.append(f"  CPU Cores:         {env.get('cpu_cores', 'N/A')}")
        lines.append(f"  ZSTD Version:      {env.get('software_version', 'N/A')}")
        lines.append(f"  Python Version:    {env.get('python_version', 'N/A')}")
        lines.append(f"  GCC Version:       {env.get('gcc_version', 'N/A')}")
        lines.append(f"  OS:                {env.get('os', 'N/A')}")
        lines.append(f"  Kernel:            {env.get('kernel', 'N/A')}")
        lines.append("")

    compression = data.get("primary_benchmark", {})
    if compression:
        lines.append("  --- Compression Benchmark (Primary) ---")
        lines.append(f"  Description:       {compression.get('description', 'N/A')}")
        lines.append(f"  Reference:         {compression.get('reference', 'N/A')}")
        params = compression.get("parameters", {})
        lines.append(f"  Data size:         {params.get('data_size_bytes', 'N/A')} bytes")
        lines.append(f"  Default level:     {params.get('default_compression_level', 'N/A')}")
        lines.append(f"  Iterations:        {params.get('iterations', 'N/A')}")
        lines.append("")
        results = compression.get("results_summary", {})
        for data_type, res in results.items():
            if isinstance(res, dict):
                lines.append(f"  {data_type} (level 3):")
                lines.append(f"    Compress speed:     {res.get('compress_speed_mbs', 'N/A')} MB/s")
                lines.append(f"    Decompress speed:   {res.get('decompress_speed_mbs', 'N/A')} MB/s")
                lines.append(f"    Compression ratio:  {res.get('compression_ratio', 'N/A')}")
                lines.append(f"    Original size:      {res.get('original_size_bytes', 'N/A')} bytes")
                lines.append(f"    Compressed size:    {res.get('compressed_size_bytes', 'N/A')} bytes")
                lines.append("")

        level_sweep = compression.get("level_sweep", {})
        if level_sweep:
            lines.append("  --- Compression Level Sweep ---")
            lines.append("  Level | Compress MB/s | Decompress MB/s | Ratio  | Latency us")
            lines.append("  ------|---------------|-----------------|--------|----------")
            for level_str, res in sorted(level_sweep.items(), key=lambda x: int(x[0])):
                if isinstance(res, dict):
                    lines.append(f"  {level_str:>5} | {res.get('compress_speed_mbs', 'N/A'):>13} | "
                                 f"{res.get('decompress_speed_mbs', 'N/A'):>15} | "
                                 f"{res.get('compression_ratio', 'N/A'):>6} | "
                                 f"{res.get('compress_latency_us', 'N/A')}")
            lines.append("")

    micro = data.get("micro_benchmark", {})
    if micro:
        mparams = micro.get("parameters", {})
        lines.append("  --- Micro Benchmarks ---")
        lines.append(f"  Description:       {micro.get('description', 'N/A')}")
        lines.append(f"  Block sizes:       {mparams.get('block_sizes', 'N/A')}")
        lines.append(f"  Compression level: {mparams.get('compression_level', 'N/A')}")
        lines.append(f"  Iterations:        {mparams.get('iterations', 'N/A')}")
        lines.append("")
        results = micro.get("results", {})
        if isinstance(results, dict):
            block_cd = results.get("block_compress_decompress", {})
            if block_cd:
                lines.append("  Block Compress/Decompress (level 3):")
                for bs, res in block_cd.items():
                    if isinstance(res, dict):
                        lines.append(f"    {bs} bytes:")
                        lines.append(f"      Compress:   {res.get('compress_speed_mbs', 'N/A')} MB/s, {res.get('compress_latency_us', 'N/A')} us")
                        lines.append(f"      Decompress: {res.get('decompress_speed_mbs', 'N/A')} MB/s, {res.get('decompress_latency_us', 'N/A')} us")
                        lines.append(f"      Ratio:      {res.get('compression_ratio', 'N/A')}")
                lines.append("")

            mt = results.get("multithread_scaling", {})
            if mt:
                lines.append("  Multithread Scaling (level 3, 64KB blocks):")
                for tc, res in mt.items():
                    if isinstance(res, dict):
                        lines.append(f"    {tc}: compress {res.get('compress_speed_mbs', 'N/A')} MB/s, "
                                     f"decompress {res.get('decompress_speed_mbs', 'N/A')} MB/s")
                lines.append("")

    lines.append("=" * 70)
    lines.append("  Report generated by ZSTD Source Build & Performance Benchmark Workflow")
    lines.append("=" * 70)

    summary = "\n".join(lines)
    with open(output_file, "w") as f:
        f.write(summary)
    print(summary)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_summary.py <input_json> <output_file>")
        sys.exit(1)

    input_json = sys.argv[1]
    output_file = sys.argv[2]
    generate_summary(input_json, output_file)
