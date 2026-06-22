#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import random
import time
import sys

try:
    import lz4.block
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
    return b'\x00' * size_bytes


def measure_block_compress(data, iterations=1):
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        compressed = lz4.block.compress(data, mode='default', acceleration=1)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

    avg = sum(latencies) / len(latencies)
    sorted_lat = sorted(latencies)
    p99_idx = int(len(sorted_lat) * 0.99) if len(sorted_lat) > 10 else len(sorted_lat) - 1
    p99 = sorted_lat[min(p99_idx, len(sorted_lat) - 1)]
    ops_per_sec = 1.0 / avg if avg > 0 else 0
    throughput_mb = len(data) / (avg * 1024 * 1024) if avg > 0 else 0

    return {
        'operation': 'block_compress_default',
        'ops_per_sec': round(ops_per_sec, 2),
        'avg_latency_ms': round(avg * 1000, 4),
        'p99_latency_ms': round(p99 * 1000, 4),
        'throughput_mb_per_sec': round(throughput_mb, 2),
        'compressed_size_bytes': len(compressed),
        'original_size_bytes': len(data),
        'iterations': iterations,
    }


def measure_block_decompress(data, iterations=1):
    compressed = lz4.block.compress(data, mode='default', acceleration=1, store_size=True)
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        decompressed = lz4.block.decompress(compressed)
        elapsed = time.perf_counter() - start
        assert len(decompressed) == len(data), "Decompression size mismatch"
        latencies.append(elapsed)

    avg = sum(latencies) / len(latencies)
    sorted_lat = sorted(latencies)
    p99_idx = int(len(sorted_lat) * 0.99) if len(sorted_lat) > 10 else len(sorted_lat) - 1
    p99 = sorted_lat[min(p99_idx, len(sorted_lat) - 1)]
    ops_per_sec = 1.0 / avg if avg > 0 else 0
    throughput_mb = len(data) / (avg * 1024 * 1024) if avg > 0 else 0

    return {
        'operation': 'block_decompress_default',
        'ops_per_sec': round(ops_per_sec, 2),
        'avg_latency_ms': round(avg * 1000, 4),
        'p99_latency_ms': round(p99 * 1000, 4),
        'throughput_mb_per_sec': round(throughput_mb, 2),
        'original_size_bytes': len(data),
        'iterations': iterations,
    }


def measure_compress_fast(data, acceleration=1, iterations=1):
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        compressed = lz4.block.compress(data, mode='default', acceleration=acceleration)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

    avg = sum(latencies) / len(latencies)
    ops_per_sec = 1.0 / avg if avg > 0 else 0
    throughput_mb = len(data) / (avg * 1024 * 1024) if avg > 0 else 0

    return {
        'operation': f'block_compress_fast_acc{acceleration}',
        'ops_per_sec': round(ops_per_sec, 2),
        'avg_latency_ms': round(avg * 1000, 4),
        'throughput_mb_per_sec': round(throughput_mb, 2),
        'acceleration': acceleration,
        'iterations': iterations,
    }


def measure_compress_hc(data, compression=9, iterations=1):
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        compressed = lz4.block.compress(data, mode='high_compression', compression=compression)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

    avg = sum(latencies) / len(latencies)
    ops_per_sec = 1.0 / avg if avg > 0 else 0
    ratio = len(data) / len(compressed) if len(compressed) > 0 else 0
    throughput_mb = len(data) / (avg * 1024 * 1024) if avg > 0 else 0

    return {
        'operation': f'block_compress_hc_lvl{compression}',
        'ops_per_sec': round(ops_per_sec, 2),
        'avg_latency_ms': round(avg * 1000, 4),
        'throughput_mb_per_sec': round(throughput_mb, 2),
        'compression_level': compression,
        'compression_ratio': round(ratio, 4),
        'iterations': iterations,
    }


def main():
    parser = argparse.ArgumentParser(description='lz4 micro benchmark - per-function latency')
    parser.add_argument('--output', required=True)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--version', default='1.10.0')
    parser.add_argument('--architecture', default='arm64')
    args = parser.parse_args()

    lz4_py_ver = lz4.frame.LZ4F_VERSION_STR if hasattr(lz4.frame, 'LZ4F_VERSION_STR') else 'unknown'

    block_sizes = [4 * 1024, 64 * 1024, 256 * 1024]
    all_results = []

    for block_size in block_sizes:
        data = generate_test_data(block_size, 'text')

        r_compress = measure_block_compress(data, args.iterations)
        r_compress['block_size'] = block_size
        r_compress['block_size_name'] = f'{block_size // 1024}KB'
        all_results.append(r_compress)

        r_decompress = measure_block_decompress(data, args.iterations)
        r_decompress['block_size'] = block_size
        r_decompress['block_size_name'] = f'{block_size // 1024}KB'
        all_results.append(r_decompress)

    data_64k = generate_test_data(64 * 1024, 'text')

    for accel in [1, 2, 4, 8]:
        r_fast = measure_compress_fast(data_64k, acceleration=accel, iterations=args.iterations)
        r_fast['block_size'] = 64 * 1024
        r_fast['block_size_name'] = '64KB'
        all_results.append(r_fast)

    for hc_level in [3, 6, 9, 12]:
        r_hc = measure_compress_hc(data_64k, compression=hc_level, iterations=args.iterations)
        r_hc['block_size'] = 64 * 1024
        r_hc['block_size_name'] = '64KB'
        all_results.append(r_hc)

    output = {
        'benchmark': 'lz4_micro_benchmark',
        'description': 'Per-function block-level LZ4 compression/decompression latency and throughput',
        'reference': 'https://github.com/lz4/lz4',
        'software': 'lz4',
        'version': args.version,
        'lz4_py_version': lz4_py_ver,
        'architecture': args.architecture,
        'timestamp': datetime.datetime.now().isoformat(),
        'performance_metrics': {
            'ops_per_sec': {
                'unit': 'ops/sec',
                'description': 'Operations per second for single block compress/decompress'
            },
            'avg_latency_ms': {
                'unit': 'ms',
                'description': 'Average per-operation latency'
            },
            'throughput_mb_per_sec': {
                'unit': 'MB/s',
                'description': 'Data throughput per operation'
            },
        },
        'dataset_info': {
            'name': 'synthetic_benchmark_data',
            'size': '4KB-256KB',
            'source': 'Generated in-memory text data'
        },
        'results': all_results,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[MICRO] Results saved to {args.output}")


if __name__ == '__main__':
    main()
