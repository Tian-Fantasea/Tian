#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import random
import time
import sys

try:
    import lz4.frame
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False
    print("[ERROR] lz4 Python package not installed")
    sys.exit(1)


def generate_test_data(size_bytes, data_type='text'):
    if data_type == 'text':
        words = ['benchmark', 'compression', 'algorithm', 'performance', 'throughput',
                 'latency', 'arm64', 'aarch64', 'neoverse', 'implementation',
                 'encoding', 'decoding', 'stream', 'block', 'frame', 'ratio',
                 'speed', 'fast', 'efficient', 'optimal', 'lossless', 'codec',
                 'dictionary', 'context', 'reference', 'corpus', 'silesia', 'enwik',
                 'test', 'data', 'sample', 'verify', 'measure', 'compare', 'scale']
        rng = random.Random(42)
        chunks = []
        remaining = size_bytes
        while remaining > 0:
            chunk_size = min(remaining, rng.randint(20, 200))
            chunk = ' '.join(rng.choices(words, k=rng.randint(3, 15)))
            chunks.append(chunk)
            remaining -= len(chunk) + 1
        return '\n'.join(chunks)[:size_bytes].encode('utf-8')
    elif data_type == 'binary':
        rng = random.Random(42)
        return bytes([rng.randint(0, 255) for _ in range(size_bytes)])
    elif data_type == 'repeated':
        pattern = b'The quick brown fox jumps over the lazy dog. ' * 100
        result = pattern
        while len(result) < size_bytes:
            result += pattern
        return result[:size_bytes]
    return b'\x00' * size_bytes


def measure_decompression(data_bytes, level, iterations=1):
    compressed = lz4.frame.compress(data_bytes, compression_level=level)
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        decompressed = lz4.frame.decompress(compressed)
        elapsed = time.perf_counter() - start
        assert decompressed == data_bytes, "Decompression verification failed"
        latencies.append(elapsed)

    avg_elapsed = sum(latencies) / len(latencies)
    sorted_lat = sorted(latencies)
    p50 = sorted_lat[len(sorted_lat) // 2]
    p90_idx = int(len(sorted_lat) * 0.9)
    p99_idx = int(len(sorted_lat) * 0.99) if len(sorted_lat) > 10 else len(sorted_lat) - 1
    p90 = sorted_lat[min(p90_idx, len(sorted_lat) - 1)]
    p99 = sorted_lat[min(p99_idx, len(sorted_lat) - 1)]

    throughput_mb = len(data_bytes) / (avg_elapsed * 1024 * 1024)

    return {
        'decompression_throughput_mb_per_sec': round(throughput_mb, 2),
        'avg_latency_ms': round(avg_elapsed * 1000, 4),
        'p50_latency_ms': round(p50 * 1000, 4),
        'p90_latency_ms': round(p90 * 1000, 4),
        'p99_latency_ms': round(p99 * 1000, 4),
        'min_latency_ms': round(min(latencies) * 1000, 6),
        'max_latency_ms': round(max(latencies) * 1000, 4),
        'original_size_bytes': len(data_bytes),
        'compressed_size_bytes': len(compressed),
        'compression_level': level,
        'iterations': iterations,
    }


def main():
    parser = argparse.ArgumentParser(description='lz4 decompression throughput benchmark')
    parser.add_argument('--output', required=True)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--version', default='1.10.0')
    parser.add_argument('--architecture', default='arm64')
    args = parser.parse_args()

    lz4_py_ver = lz4.frame.LZ4F_VERSION_STR if hasattr(lz4.frame, 'LZ4F_VERSION_STR') else 'unknown'

    data_configs = [
        ('4KB_text', 4 * 1024, 'text', 1),
        ('4KB_binary', 4 * 1024, 'binary', 1),
        ('64KB_text', 64 * 1024, 'text', 1),
        ('64KB_text_HC6', 64 * 1024, 'text', 6),
        ('256KB_text', 256 * 1024, 'text', 1),
        ('256KB_text_HC9', 256 * 1024, 'text', 9),
        ('1MB_text', 1024 * 1024, 'text', 1),
        ('1MB_text_HC12', 1024 * 1024, 'text', 12),
        ('1MB_repeated', 1024 * 1024, 'repeated', 1),
        ('1MB_binary', 1024 * 1024, 'binary', 1),
    ]

    all_results = []

    for name, size, dtype, level in data_configs:
        data_bytes = generate_test_data(size, dtype)
        result = measure_decompression(data_bytes, level, args.iterations)
        result['data_name'] = name
        result['data_type'] = dtype
        all_results.append(result)

    output = {
        'benchmark': 'lz4_decompression_throughput',
        'description': 'Decompression throughput and latency at various data sizes and compression levels using lz4.frame API',
        'reference': 'https://github.com/lz4/lz4',
        'software': 'lz4',
        'version': args.version,
        'lz4_py_version': lz4_py_ver,
        'architecture': args.architecture,
        'timestamp': datetime.datetime.now().isoformat(),
        'performance_metrics': {
            'decompression_throughput_mb_per_sec': {
                'unit': 'MB/s',
                'description': 'Decompression throughput in megabytes per second'
            },
            'avg_latency_ms': {
                'unit': 'ms',
                'description': 'Average decompression latency per operation'
            },
            'p99_latency_ms': {
                'unit': 'ms',
                'description': '99th percentile decompression latency'
            },
        },
        'dataset_info': {
            'name': 'synthetic_benchmark_data',
            'size': '4KB-1MB',
            'source': 'Generated in-memory (text/binary/repeated patterns)'
        },
        'results': all_results,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[DECOMPRESSION] Results saved to {args.output}")


if __name__ == '__main__':
    main()
