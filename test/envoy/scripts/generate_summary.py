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
    lines.append("Envoy ARM64 Performance Benchmark Summary")
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
        lines.append(f"Envoy Version:      {vi.get('envoy_version', 'N/A')}")
        lines.append(f"Python:             {vi.get('python_version', 'N/A')}")
        lines.append(f"wrk:                {vi.get('wrk_version', 'N/A')}")
        lines.append("")

    http = all_data.get('primary_benchmark', {})
    if http:
        lines.append("--- HTTP/L7 Proxy Benchmark ---")
        lines.append(f"Reference: {http.get('reference', 'N/A')}")
        for result in http.get('results', []):
            test_name = result.get('test', '')
            data = result.get('data', [])
            if test_name == "rps_vs_concurrency" and isinstance(data, list):
                for d in data:
                    lines.append(f"  c={d.get('concurrency', 'N/A')}: RPS={d.get('avg_rps', 0):.0f}, P99={d.get('avg_latency_p99_ms', 0):.2f}ms")
        lines.append("")

    tcp = all_data.get('secondary_benchmark', {})
    if tcp:
        lines.append("--- TCP/L4 Proxy + Latency Benchmark ---")
        lines.append(f"Reference: {tcp.get('reference', 'N/A')}")
        for result in tcp.get('results', []):
            test_name = result.get('test', '')
            data = result.get('data', [])
            if test_name == "tcp_throughput_vs_concurrency" and isinstance(data, list):
                for d in data:
                    lines.append(f"  c={d.get('concurrency', 'N/A')}: RPS={d.get('avg_rps', 0):.0f}, P99={d.get('avg_latency_p99_ms', 0):.2f}ms")
            elif test_name == "latency_percentiles" and isinstance(data, dict):
                lines.append(f"  Avg P50: {sum(data.get('p50_values', [0])) / max(len(data.get('p50_values', [0])), 1):.2f}ms")
                lines.append(f"  Avg P99: {sum(data.get('p99_values', [0])) / max(len(data.get('p99_values', [0])), 1):.2f}ms")
        lines.append("")

    micro = all_data.get('micro_benchmark', {})
    if micro:
        lines.append("--- Micro Benchmarks ---")
        for result in micro.get('results', []):
            test_name = result.get('test', '')
            data = result.get('data', {})
            if test_name == "arm64_crypto_detection":
                lines.append(f"  AES:  {data.get('aes', 'N/A')}")
                lines.append(f"  SHA1: {data.get('sha1', 'N/A')}")
                lines.append(f"  SHA2: {data.get('sha2', 'N/A')}")
                lines.append(f"  NEON: {data.get('neon', 'N/A')}")
                lines.append(f"  PMULL: {data.get('pmull', 'N/A')}")
            elif test_name == "memory_footprint":
                lines.append(f"  Initial memory: {data.get('initial_memory_mb', 0):.1f} MB")
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
