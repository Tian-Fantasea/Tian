#!/usr/bin/env python3
import subprocess
import sys
import os
import json


def run_kv_benchmark(benchmark_bin, output_file, num_ops, value_size, iterations, port):
    cmd = [benchmark_bin, "kv", str(iterations), output_file,
            str(num_ops), str(value_size), str(port)]
    print(f"[BENCHMARK_KV] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"[BENCHMARK_KV] Error: {result.stderr}")
        return False
    print(result.stdout)
    print(f"[BENCHMARK_KV] Output written to {output_file}")
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: benchmark_kv.py <benchmark_bin> <output_file> "
              "[num_ops] [value_size] [iterations] [port]")
        sys.exit(1)

    benchmark_bin = sys.argv[1]
    output_file = sys.argv[2]
    num_ops = int(sys.argv[3]) if len(sys.argv) >= 4 else 100000
    value_size = int(sys.argv[4]) if len(sys.argv) >= 5 else 256
    iterations = int(sys.argv[5]) if len(sys.argv) >= 6 else 1
    port = int(sys.argv[6]) if len(sys.argv) >= 7 else 16379

    if not os.path.exists(benchmark_bin):
        print(f"[BENCHMARK_KV] Benchmark binary not found: {benchmark_bin}")
        sys.exit(1)

    success = run_kv_benchmark(benchmark_bin, output_file, num_ops,
                                value_size, iterations, port)

    if success and os.path.exists(output_file):
        try:
            with open(output_file) as f:
                data = json.load(f)
            print(f"[BENCHMARK_KV] Validation: benchmark={data.get('benchmark')}, "
                  f"workloads={list(data.get('results_summary', {}).keys())}")
        except Exception as e:
            print(f"[BENCHMARK_KV] Validation failed: {e}")
    else:
        print("[BENCHMARK_KV] No output file generated")


if __name__ == "__main__":
    main()