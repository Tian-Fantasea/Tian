#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import random
import time
import sys
from concurrent.futures import ThreadPoolExecutor

try:
    import lz4.frame
    import lz4.block
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


def compress_task(data, level):
    compressed = lz4.frame.compress(data, compression_level=level)
    decompressed = lz4.frame.decompress(compressed)
    assert decompressed == data, "Verification failed"
    return len(data)


def decompress_task(compressed, original_size):
    decompressed = lz4.frame.decompress(compressed)
    assert len(decompressed) == original_size, "Decompression size mismatch"
    return original_size


def measure_concurrency(data, level, thread_count, iterations=1, mode='compress'):
    total_ops = 0
    total_bytes = 0
    latencies = []

    if mode == 'compress':
        tasks_per_iter = thread_count
        for _ in range(iterations):
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [executor.submit(compress_task, data, level) for _ in range(tasks_per_iter)]
                bytes_processed = sum(f.result() for f in futures)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
            total_ops += tasks_per_iter
            total_bytes += bytes_processed
    elif mode == 'decompress':
        compressed = lz4.frame.compress(data, compression_level=level)
        tasks_per_iter = thread_count
        for _ in range(iterations):
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [executor.submit(decompress_task, compressed, len(data)) for _ in range(tasks_per_iter)]
                bytes_processed = sum(f.result() for f in futures)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
            total_ops += tasks_per_iter
            total_bytes += bytes_processed

    avg_elapsed = sum(latencies) / len(latencies) if latencies else 0
    throughput_mb = total_bytes / (sum(latencies) * 1024 * 1024) if sum(latencies) > 0 else 0
    ops_per_sec = total_ops / sum(latencies) if sum(latencies) > 0 else 0

    return {
        'mode': mode,
        'thread_count': thread_count,
        'compression_level': level,
        'total_ops': total_ops,
        'total_ops_per_sec': round(ops_per_sec, 2),
        'total_throughput_mb_per_sec': round(throughput_mb, 2),
        'avg_latency_ms': round(avg_elapsed * 1000, 4),
        'data_size_bytes': len(data),
        'iterations': iterations,
    }


def main():
    parser = argparse.ArgumentParser(description='lz4 concurrency scaling benchmark')
    parser.add_argument('--output', required=True)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--version', default='1.10.0')
    parser.add_argument('--architecture', default='arm64')
    args = parser.parse_args()

    lz4_py_ver = lz4.frame.LZ4F_VERSION_STR if hasattr(lz4.frame, 'LZ4F_VERSION_STR') else 'unknown'

    data = generate_test_data(256 * 1024, 'text')
    thread_counts = [1, 2, 4, 8]
    all_results = []

    for tc in thread_counts:
        r_compress = measure_concurrency(data, level=1, thread_count=tc,
                                          iterations=args.iterations, mode='compress')
        all_results.append(r_compress)

        r_decompress = measure_concurrency(data, level=1, thread_count=tc,
                                             iterations=args.iterations, mode='decompress')
        all_results.append(r_decompress)

    for tc in thread_counts:
        r_hc = measure_concurrency(data, level=9, thread_count=tc,
                                    iterations=args.iterations, mode='compress')
        r_hc['mode'] = 'compress_hc'
        all_results.append(r_hc)

    output = {
        'benchmark': 'lz4_concurrency_scaling',
        'description': 'Multi-thread compression/decompression scaling benchmark using ThreadPoolExecutor with lz4.frame API',
        'reference': 'https://github.com/lz4/lz4',
        'software': 'lz4',
        'version': args.version,
        'lz4_py_version': lz4_py_ver,
        'architecture': args.architecture,
        'timestamp': datetime.datetime.now().isoformat(),
        'performance_metrics': {
            'total_throughput_mb_per_sec': {
                'unit': 'MB/s',
                'description': 'Total throughput across all threads'
            },
            'total_ops_per_sec': {
                'unit': 'ops/sec',
                'description': 'Total operations per second across all threads'
            },
            'avg_latency_ms': {
                'unit': 'ms',
                'description': 'Average latency for a batch of parallel operations'
            },
        },
        'dataset_info': {
            'name': 'synthetic_benchmark_data',
            'size': '256KB',
            'source': 'Generated in-memory text data'
        },
        'results': all_results,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[CONCURRENCY] Results saved to {args.output}")


if __name__ == '__main__':
    main()
