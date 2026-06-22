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
    print("[ERROR] lz4 Python package not installed. Install: pip install lz4")
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
        return '\n'.join(chunks)[:size_bytes]
    elif data_type == 'binary':
        rng = random.Random(42)
        return bytes([rng.randint(0, 255) for _ in range(size_bytes)])
    elif data_type == 'repeated':
        pattern = b'The quick brown fox jumps over the lazy dog. ' * 100
        if size_bytes <= len(pattern):
            return pattern[:size_bytes]
        result = pattern
        while len(result) < size_bytes:
            result += pattern
        return result[:size_bytes]
    return b'\x00' * size_bytes


def measure_compression(data_bytes, level, iterations=1):
    results = []
    for _ in range(iterations):
        start = time.perf_counter()
        compressed = lz4.frame.compress(data_bytes, compression_level=level)
        elapsed = time.perf_counter() - start
        decompressed = lz4.frame.decompress(compressed)
        assert decompressed == data_bytes, "Decompression verification failed"
        throughput_mb = len(data_bytes) / (elapsed * 1024 * 1024)
        ratio = len(data_bytes) / len(compressed) if len(compressed) > 0 else 0
        results.append({
            'compression_throughput_mb_per_sec': round(throughput_mb, 2),
            'compression_ratio': round(ratio, 4),
            'compressed_size_bytes': len(compressed),
            'elapsed_sec': round(elapsed, 6),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description='lz4 compression throughput benchmark')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--version', default='1.10.0')
    parser.add_argument('--architecture', default='arm64')
    args = parser.parse_args()

    lz4_py_ver = lz4.frame.LZ4F_VERSION_STR if hasattr(lz4.frame, 'LZ4F_VERSION_STR') else 'unknown'

    data_sizes = {
        '4KB': 4 * 1024,
        '64KB': 64 * 1024,
        '256KB': 256 * 1024,
        '1MB': 1024 * 1024,
    }

    compression_levels = [1, 2, 3, 6, 9, 12]

    all_results = []

    for data_name, data_size in data_sizes.items():
        for data_type in ['text', 'binary', 'repeated']:
            data_bytes = generate_test_data(data_size, data_type)
            if isinstance(data_bytes, str):
                data_bytes = data_bytes.encode('utf-8')

            for level in compression_levels:
                iter_results = measure_compression(data_bytes, level, args.iterations)
                avg_throughput = sum(r['compression_throughput_mb_per_sec'] for r in iter_results) / len(iter_results)
                avg_ratio = sum(r['compression_ratio'] for r in iter_results) / len(iter_results)
                avg_elapsed = sum(r['elapsed_sec'] for r in iter_results) / len(iter_results)
                avg_compressed_size = sum(r['compressed_size_bytes'] for r in iter_results) / len(iter_results)

                all_results.append({
                    'data_size': data_name,
                    'data_size_bytes': data_size,
                    'data_type': data_type,
                    'compression_level': level,
                    'compression_throughput_mb_per_sec': round(avg_throughput, 2),
                    'compression_ratio': round(avg_ratio, 4),
                    'compressed_size_bytes': round(avg_compressed_size, 0),
                    'avg_latency_ms': round(avg_elapsed * 1000, 4),
                    'iterations': args.iterations,
                })

    output = {
        'benchmark': 'lz4_compression_throughput',
        'description': 'Compression throughput at various levels and data sizes using lz4.frame API',
        'reference': 'https://github.com/lz4/lz4',
        'software': 'lz4',
        'version': args.version,
        'lz4_py_version': lz4_py_ver,
        'architecture': args.architecture,
        'timestamp': datetime.datetime.now().isoformat(),
        'performance_metrics': {
            'compression_throughput_mb_per_sec': {
                'unit': 'MB/s',
                'description': 'Compression throughput in megabytes per second'
            },
            'compression_ratio': {
                'unit': 'ratio',
                'description': 'Original size divided by compressed size'
            },
            'avg_latency_ms': {
                'unit': 'ms',
                'description': 'Average compression latency per operation'
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
    print(f"[COMPRESSION] Results saved to {args.output}")


if __name__ == '__main__':
    main()
