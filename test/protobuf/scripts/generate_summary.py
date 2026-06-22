#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description='Generate text summary of protobuf benchmark results')
    parser.add_argument('--input', required=True, help='Input results.json file')
    parser.add_argument('--output', required=True, help='Output results.txt file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print('[SUMMARY] results.json not found')
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    env = data.get('environment', {})
    ser = data.get('benchmarks', {}).get('serialization', {})
    lat = data.get('benchmarks', {}).get('latency', {})
    micro = data.get('benchmarks', {}).get('micro', {})
    conc = data.get('benchmarks', {}).get('concurrency', {})
    summary = data.get('summary', {})

    lines = []
    lines.append('=' * 70)
    lines.append('protobuf ARM64 Performance Benchmark Summary')
    lines.append('=' * 70)
    lines.append(f'Generated: {datetime.datetime.now().isoformat()}')
    lines.append('')

    if env:
        lines.append('--- Environment ---')
        lines.append(f'Architecture:          {env.get("architecture", "N/A")}')
        lines.append(f'OS:                    {env.get("os", "N/A")}')
        lines.append(f'Kernel:                {env.get("kernel", "N/A")}')
        lines.append(f'CPU:                   {env.get("cpu_model", "N/A")} ({env.get("cores", "N/A")} cores)')
        lines.append(f'Memory:                {env.get("memory_mb", "N/A")} MB')
        lines.append(f'protobuf Version:      {env.get("protobuf_version", env.get("software_version", "N/A"))}')
        lines.append(f'Python protobuf:       {env.get("python_protobuf_version", "N/A")}')
        lines.append(f'protoc:                {env.get("protoc_version", "N/A")}')
        lines.append(f'Python Version:        {env.get("runtime_version", "N/A")}')
        lines.append(f'Install Method:        {env.get("install_method", "N/A")}')
        lines.append(f'Category:              {env.get("category", "N/A")}')
        lines.append('')

    if ser:
        lines.append('--- Serialization Throughput (Phase 3a) ---')
        lines.append(f'Reference: {ser.get("reference", "N/A")}')
        lines.append(f'Well-known type: Struct (google.protobuf.struct_pb2)')
        lines.append('')
        for r in ser.get("results", []):
            lines.append(f'  {r.get("message_type", "N/A")} ({r.get("message_size_bytes", "N/A")} bytes):')
            lines.append(f'    Serialize:   {r.get("serialize_ops_per_sec", "N/A")} msgs/sec, {r.get("serialize_bytes_per_sec", "N/A")} bytes/sec')
            lines.append(f'    Deserialize: {r.get("deserialize_ops_per_sec", "N/A")} msgs/sec')
            lines.append(f'    Avg latency: serialize={r.get("serialize_avg_latency_ms", "N/A")}ms, deserialize={r.get("deserialize_avg_latency_ms", "N/A")}ms')
        lines.append('')

    if lat:
        lines.append('--- Latency Distribution (Phase 3b) ---')
        lines.append(f'Reference: {lat.get("reference", "N/A")}')
        lines.append('')
        for r in lat.get("results", []):
            lines.append(f'  {r.get("operation", "N/A")} ({r.get("message_size_bytes", "N/A")} bytes):')
            lines.append(f'    Avg:  {r.get("avg_latency_ms", "N/A")}ms')
            lines.append(f'    P50:  {r.get("p50_latency_ms", "N/A")}ms')
            lines.append(f'    P90:  {r.get("p90_latency_ms", "N/A")}ms')
            lines.append(f'    P99:  {r.get("p99_latency_ms", "N/A")}ms')
            lines.append(f'    Min:  {r.get("min_latency_ms", "N/A")}ms')
            lines.append(f'    Max:  {r.get("max_latency_ms", "N/A")}ms')
        lines.append('')

    if micro:
        lines.append('--- Micro Benchmarks (Phase 3c) ---')
        lines.append(f'Reference: {micro.get("reference", "N/A")}')
        lines.append('')
        for r in micro.get("results", []):
            lines.append(f'  {r.get("field_type", "N/A")} ({r.get("message_size_bytes", "N/A")} bytes):')
            lines.append(f'    Serialize:   {r.get("serialize_ops_per_sec", "N/A")} ops/sec')
            lines.append(f'    Deserialize: {r.get("deserialize_ops_per_sec", "N/A")} ops/sec')
        lines.append('')

    if conc:
        lines.append('--- Concurrency Scaling (Phase 3d) ---')
        lines.append(f'Reference: {conc.get("reference", "N/A")}')
        lines.append('')
        for r in conc.get("results", []):
            lines.append(f'  {r.get("mode", "N/A")} threads={r.get("thread_count", "N/A")}:')
            lines.append(f'    Total ops/sec: {r.get("total_ops_per_sec", "N/A")}')
            lines.append(f'    Avg latency:   {r.get("avg_latency_ms", "N/A")}ms')
        lines.append('')

    if summary:
        lines.append('--- Overall Summary ---')
        if 'avg_serialize_ops_small' in summary:
            lines.append(f'  Avg serialize ops (small): {summary["avg_serialize_ops_small"]} msgs/sec')
        if 'avg_deserialize_ops_small' in summary:
            lines.append(f'  Avg deserialize ops (small): {summary["avg_deserialize_ops_small"]} msgs/sec')
        if 'avg_serialize_bytes_small' in summary:
            lines.append(f'  Avg serialize bytes (small): {summary["avg_serialize_bytes_small"]} bytes/sec')
        if 'max_avg_latency_ms' in summary:
            lines.append(f'  Max avg latency: {summary["max_avg_latency_ms"]} ms')
        if 'max_p99_latency_ms' in summary:
            lines.append(f'  Max P99 latency: {summary["max_p99_latency_ms"]} ms')
        if 'avg_micro_serialize_ops' in summary:
            lines.append(f'  Avg micro serialize ops: {summary["avg_micro_serialize_ops"]} ops/sec')
        if 'avg_micro_deserialize_ops' in summary:
            lines.append(f'  Avg micro deserialize ops: {summary["avg_micro_deserialize_ops"]} ops/sec')
        if 'concurrency_scaling_ratio' in summary:
            lines.append(f'  Concurrency scaling (8t vs 1t): {summary["concurrency_scaling_ratio"]}x')

    lines.append('')
    lines.append('=' * 70)
    lines.append('End of Summary')
    lines.append('=' * 70)

    summary_text = '\n'.join(lines)
    with open(args.output, 'w') as f:
        f.write(summary_text)
    print(f'[SUMMARY] Saved to {args.output}')


if __name__ == '__main__':
    main()
