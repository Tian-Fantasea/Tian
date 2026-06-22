#!/usr/bin/env python3
import json
import time
import argparse
import datetime
import os
import torch
import torch.nn as nn

def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def write_results_section(filepath, section, data):
    results = load_or_create_json(filepath)
    results[section] = data
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)

def bench_tensor_creation(dim, iterations=3):
    results = {}
    sizes = [100, 1000, 10000, 100000]

    for size in sizes:
        times = []
        for i in range(iterations):
            start = time.time()
            x = torch.randn(size, dim)
            torch.cpu.synchronize()
            elapsed = time.time() - start
            times.append(elapsed)
        avg = round(sum(times) / len(times) * 1000, 4)
        results[f"randn_{size}x{dim}"] = {"avg_time_ms": avg, "elements": size * dim}

    for size in sizes:
        times = []
        for i in range(iterations):
            start = time.time()
            x = torch.zeros(size, dim)
            torch.cpu.synchronize()
            elapsed = time.time() - start
            times.append(elapsed)
        avg = round(sum(times) / len(times) * 1000, 4)
        results[f"zeros_{size}x{dim}"] = {"avg_time_ms": avg, "elements": size * dim}

    return results

def bench_memory_transfer(iterations=3):
    results = {}
    sizes_mb = [1, 10, 50, 100]

    for mb in sizes_mb:
        elements = int(mb * 1024 * 1024 / 4)
        x = torch.randn(elements)

        copy_times = []
        for i in range(iterations):
            start = time.time()
            y = x.clone()
            torch.cpu.synchronize()
            elapsed = time.time() - start
            copy_times.append(elapsed)
        avg_copy = round(sum(copy_times) / len(copy_times) * 1000, 4)
        copy_rate = mb / (sum(copy_times) / len(copy_times)) if sum(copy_times) / len(copy_times) > 0 else 0
        results[f"clone_{mb}MB"] = {"avg_time_ms": avg_copy, "copy_rate_MB_per_sec": round(copy_rate, 2)}

    return results

def bench_compile_speed(iterations=3):
    results = {}

    model = nn.Sequential(nn.Linear(128, 256), nn.ReLU(), nn.Linear(256, 128))

    compile_times = []
    for i in range(iterations):
        start = time.time()
        compiled_model = torch.compile(model, backend="eager")
        elapsed = time.time() - start
        compile_times.append(elapsed)
        del compiled_model
    avg_compile = round(sum(compile_times) / len(compile_times) * 1000, 4)
    results["torch_compile_eager"] = {"avg_compile_time_ms": avg_compile}

    compile_times_inductor = []
    for i in range(iterations):
        start = time.time()
        try:
            compiled_model = torch.compile(model, backend="inductor")
            elapsed = time.time() - start
        except Exception as e:
            elapsed = time.time() - start
            results["torch_compile_inductor_error"] = str(e)
            break
        compile_times_inductor.append(elapsed)
        del compiled_model
    if compile_times_inductor:
        avg_compile_inductor = round(sum(compile_times_inductor) / len(compile_times_inductor) * 1000, 4)
        results["torch_compile_inductor"] = {"avg_compile_time_ms": avg_compile_inductor}

    x = torch.randn(32, 128)
    eager_times = []
    with torch.no_grad():
        for _ in range(10):
            model(x)
        torch.cpu.synchronize()
        for i in range(iterations):
            start = time.time()
            model(x)
            torch.cpu.synchronize()
            elapsed = time.time() - start
            eager_times.append(elapsed)
    avg_eager = round(sum(eager_times) / len(eager_times) * 1000, 4)

    compiled_model = torch.compile(model, backend="eager")
    compiled_times = []
    with torch.no_grad():
        for _ in range(10):
            compiled_model(x)
        torch.cpu.synchronize()
        for i in range(iterations):
            start = time.time()
            compiled_model(x)
            torch.cpu.synchronize()
            elapsed = time.time() - start
            compiled_times.append(elapsed)
    avg_compiled = round(sum(compiled_times) / len(compiled_times) * 1000, 4)

    speedup = avg_eager / avg_compiled if avg_compiled > 0 else 0
    results["eager_vs_compile_eager"] = {
        "eager_time_ms": avg_eager,
        "compiled_time_ms": avg_compiled,
        "speedup": round(speedup, 4),
    }

    return results

def bench_data_loading(iterations=3):
    results = {}
    tensor_sizes = [1000, 10000, 100000]

    for size in tensor_sizes:
        x = torch.randn(size, 128)
        times = []
        for i in range(iterations):
            start = time.time()
            for idx in range(min(100, size)):
                _ = x[idx]
            torch.cpu.synchronize()
            elapsed = time.time() - start
            times.append(elapsed)
        avg = round(sum(times) / len(times) * 1000, 4)
        results[f"indexing_{size}x128_100ops"] = {"avg_time_ms": avg}

    return results

def bench_dtype_conversion(iterations=3):
    results = {}
    x = torch.randn(10000, 128)

    conversions = [
        ("float32_to_float16", torch.float16),
        ("float32_to_bfloat16", torch.bfloat16),
        ("float32_to_float64", torch.float64),
        ("float32_to_int8", torch.int8),
    ]

    for name, target_dtype in conversions:
        times = []
        for i in range(iterations):
            start = time.time()
            y = x.to(target_dtype)
            torch.cpu.synchronize()
            elapsed = time.time() - start
            times.append(elapsed)
        avg = round(sum(times) / len(times) * 1000, 4)
        rate = round(x.numel() * 4 / (sum(times) / len(times)) / 1e6, 2)
        results[name] = {"avg_time_ms": avg, "conversion_rate_Melements_per_sec": rate}

    return results

def main():
    parser = argparse.ArgumentParser(description='PyTorch Micro Benchmarks (Memory, Compile, Data)')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--data-dim', type=int, default=128)
    parser.add_argument('--results-json', required=True)
    parser.add_argument('--section', default='micro_benchmark')
    args = parser.parse_args()

    iterations = args.iterations
    dim = args.data_dim

    print(f'[MICRO] PyTorch micro benchmarks on ARM64 CPU...')
    print(f'[MICRO] torch threads: {torch.get_num_threads()}')

    all_results = {}

    print('[MICRO] Running tensor_creation...')
    all_results["tensor_creation"] = bench_tensor_creation(dim, iterations=iterations)

    print('[MICRO] Running memory_transfer (clone)...')
    all_results["memory_transfer"] = bench_memory_transfer(iterations=iterations)

    print('[MICRO] Running compile_speed...')
    all_results["compile_speed"] = bench_compile_speed(iterations=iterations)

    print('[MICRO] Running data_loading (indexing)...')
    all_results["data_loading"] = bench_data_loading(iterations=iterations)

    print('[MICRO] Running dtype_conversion...')
    all_results["dtype_conversion"] = bench_dtype_conversion(iterations=iterations)

    output = {
        "benchmark": "micro_operations",
        "description": "Micro-level benchmarks for PyTorch memory, compile, and data operations on ARM64",
        "reference": "PyTorch library (https://pytorch.org)",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "tensor_creation_time": {
                "unit": "milliseconds",
                "description": "Time to create tensors of various sizes"
            },
            "memory_copy_rate": {
                "unit": "MB/sec",
                "description": "Tensor clone/copy throughput"
            },
            "compile_time": {
                "unit": "milliseconds",
                "description": "torch.compile compilation overhead"
            },
            "dtype_conversion_rate": {
                "unit": "M elements/sec",
                "description": "dtype conversion throughput"
            }
        },
        "dataset_info": {
            "name": "synthetic_tensors",
            "size": f"dimension {dim}",
            "source": "torch.randn generated"
        },
        "parameters": {
            "iterations": iterations,
            "dimension": dim,
            "torch_threads": torch.get_num_threads(),
            "device": "cpu",
        },
        "results": all_results
    }

    write_results_section(args.results_json, args.section, output)

    print(f'[MICRO] Results saved to: {args.results_json} (section: {args.section})')
    for name, res in all_results.items():
        print(f'[MICRO] {name}: {res}')
    print('[MICRO] Benchmark complete')

if __name__ == '__main__':
    main()
