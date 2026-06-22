#!/usr/bin/env python3
import json
import time
import argparse
import datetime
import os
import numpy as np
import torch

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

OPERATOR_CONFIGS = {
    "matmul_fp32_128": {
        "op": "matmul",
        "dtype": "float32",
        "m": 128, "n": 128, "k": 128,
        "description": "Matrix multiply 128x128 @ 128x128, float32",
    },
    "matmul_fp32_512": {
        "op": "matmul",
        "dtype": "float32",
        "m": 512, "n": 512, "k": 512,
        "description": "Matrix multiply 512x512 @ 512x512, float32",
    },
    "matmul_fp32_1024": {
        "op": "matmul",
        "dtype": "float32",
        "m": 1024, "n": 1024, "k": 1024,
        "description": "Matrix multiply 1024x1024 @ 1024x1024, float32",
    },
    "matmul_bf16_1024": {
        "op": "matmul",
        "dtype": "bfloat16",
        "m": 1024, "n": 1024, "k": 1024,
        "description": "Matrix multiply 1024x1024 @ 1024x1024, bfloat16",
    },
    "conv2d_fp32_resnet_block": {
        "op": "conv2d",
        "dtype": "float32",
        "in_channels": 64, "out_channels": 64, "kernel_size": 3,
        "input_shape": (1, 64, 56, 56),
        "description": "Conv2d 3x3, 64->64 channels, 56x56 input (ResNet block)",
    },
    "conv2d_fp32_large": {
        "op": "conv2d",
        "dtype": "float32",
        "in_channels": 256, "out_channels": 512, "kernel_size": 3,
        "input_shape": (1, 256, 28, 28),
        "description": "Conv2d 3x3, 256->512 channels, 28x28 input (large conv)",
    },
    "attention_fp32_128": {
        "op": "attention",
        "dtype": "float32",
        "seq_len": 128, "hidden_dim": 768, "num_heads": 12,
        "description": "Multi-head attention, seq=128, dim=768, 12 heads",
    },
    "attention_fp32_512": {
        "op": "attention",
        "dtype": "float32",
        "seq_len": 512, "hidden_dim": 768, "num_heads": 12,
        "description": "Multi-head attention, seq=512, dim=768, 12 heads",
    },
    "einsum_fp32": {
        "op": "einsum",
        "dtype": "float32",
        "batch": 64, "m": 128, "k": 128, "n": 128,
        "description": "Batched einsum (bik,bkj->bij), 64 batches",
    },
    "reduction_fp32": {
        "op": "reduction",
        "dtype": "float32",
        "shape": (10000, 128),
        "description": "Sum reduction over dim=0, shape 10000x128",
    },
    "softmax_fp32": {
        "op": "softmax",
        "dtype": "float32",
        "shape": (128, 768),
        "description": "Softmax over dim=-1, shape 128x768",
    },
}

def benchmark_matmul(m, n, k, dtype, iterations):
    dtype_t = getattr(torch, dtype)
    a = torch.randn(m, k, dtype=dtype_t)
    b = torch.randn(k, n, dtype=dtype_t)

    for _ in range(5):
        c = torch.mm(a, b)
    torch.cpu.synchronize()

    times = []
    for i in range(iterations):
        start = time.time()
        c = torch.mm(a, b)
        torch.cpu.synchronize()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    flops = 2.0 * m * n * k
    tflops = flops / avg_time / 1e12
    return round(avg_time * 1000, 4), round(tflops, 4)

def benchmark_conv2d(in_channels, out_channels, kernel_size, input_shape, dtype, iterations):
    dtype_t = getattr(torch, dtype)
    x = torch.randn(*input_shape, dtype=dtype_t)
    conv = torch.nn.Conv2d(in_channels, out_channels, kernel_size, padding=kernel_size//2, bias=False)

    for _ in range(5):
        y = conv(x)
    torch.cpu.synchronize()

    times = []
    for i in range(iterations):
        start = time.time()
        y = conv(x)
        torch.cpu.synchronize()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    return round(avg_time * 1000, 4)

def benchmark_attention(seq_len, hidden_dim, num_heads, dtype, iterations):
    dtype_t = getattr(torch, dtype)
    head_dim = hidden_dim // num_heads
    q = torch.randn(1, seq_len, hidden_dim, dtype=dtype_t)
    k = torch.randn(1, seq_len, hidden_dim, dtype=dtype_t)
    v = torch.randn(1, seq_len, hidden_dim, dtype=dtype_t)

    for _ in range(5):
        attn_output = torch.nn.functional.scaled_dot_product_attention(q, k, v)
    torch.cpu.synchronize()

    times = []
    for i in range(iterations):
        start = time.time()
        attn_output = torch.nn.functional.scaled_dot_product_attention(q, k, v)
        torch.cpu.synchronize()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    return round(avg_time * 1000, 4)

def benchmark_einsum(batch, m, k, n, dtype, iterations):
    dtype_t = getattr(torch, dtype)
    a = torch.randn(batch, m, k, dtype=dtype_t)
    b = torch.randn(batch, k, n, dtype=dtype_t)

    for _ in range(5):
        c = torch.einsum('bik,bkj->bij', a, b)
    torch.cpu.synchronize()

    times = []
    for i in range(iterations):
        start = time.time()
        c = torch.einsum('bik,bkj->bij', a, b)
        torch.cpu.synchronize()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    flops = 2.0 * batch * m * k * n
    tflops = flops / avg_time / 1e12
    return round(avg_time * 1000, 4), round(tflops, 4)

def benchmark_reduction(shape, dtype, iterations):
    dtype_t = getattr(torch, dtype)
    x = torch.randn(*shape, dtype=dtype_t)

    for _ in range(5):
        y = x.sum(dim=0)
    torch.cpu.synchronize()

    times = []
    for i in range(iterations):
        start = time.time()
        y = x.sum(dim=0)
        torch.cpu.synchronize()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    return round(avg_time * 1000, 4)

def benchmark_softmax(shape, dtype, iterations):
    dtype_t = getattr(torch, dtype)
    x = torch.randn(*shape, dtype=dtype_t)

    for _ in range(5):
        y = torch.nn.functional.softmax(x, dim=-1)
    torch.cpu.synchronize()

    times = []
    for i in range(iterations):
        start = time.time()
        y = torch.nn.functional.softmax(x, dim=-1)
        torch.cpu.synchronize()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    return round(avg_time * 1000, 4)

def run_operator(config_name, config, iterations):
    op = config["op"]
    dtype = config["dtype"]

    if op == "matmul":
        avg_ms, tflops = benchmark_matmul(config["m"], config["n"], config["k"], dtype, iterations)
        return {"avg_time_ms": avg_ms, "tflops": tflops}
    elif op == "conv2d":
        avg_ms = benchmark_conv2d(config["in_channels"], config["out_channels"],
                                  config["kernel_size"], config["input_shape"], dtype, iterations)
        return {"avg_time_ms": avg_ms}
    elif op == "attention":
        avg_ms = benchmark_attention(config["seq_len"], config["hidden_dim"], config["num_heads"], dtype, iterations)
        return {"avg_time_ms": avg_ms}
    elif op == "einsum":
        avg_ms, tflops = benchmark_einsum(config["batch"], config["m"], config["k"], config["n"], dtype, iterations)
        return {"avg_time_ms": avg_ms, "tflops": tflops}
    elif op == "reduction":
        avg_ms = benchmark_reduction(config["shape"], dtype, iterations)
        return {"avg_time_ms": avg_ms}
    elif op == "softmax":
        avg_ms = benchmark_softmax(config["shape"], dtype, iterations)
        return {"avg_time_ms": avg_ms}

def main():
    parser = argparse.ArgumentParser(description='PyTorch Operator-Level Compute Benchmark')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--data-dim', type=int, default=128)
    parser.add_argument('--results-json', required=True)
    parser.add_argument('--section', default='compute_benchmark')
    args = parser.parse_args()

    iterations = args.iterations

    print(f'[COMPUTE] PyTorch operator benchmark on ARM64 CPU...')
    print(f'[COMPUTE] torch threads: {torch.get_num_threads()}')

    all_results = {}

    for config_name, config in OPERATOR_CONFIGS.items():
        print(f'[COMPUTE] {config_name}: {config["description"]}')
        try:
            result = run_operator(config_name, config, iterations)
            all_results[config_name] = result
            if "tflops" in result:
                print(f'[COMPUTE]   time={result["avg_time_ms"]}ms, TFLOPS={result["tflops"]}')
            else:
                print(f'[COMPUTE]   time={result["avg_time_ms"]}ms')
        except Exception as e:
            print(f'[COMPUTE] ERROR: {e}')
            all_results[config_name] = {"error": str(e)}

    output = {
        "benchmark": "operator_compute",
        "description": "PyTorch core operator compute benchmark on ARM64 CPU (matmul, conv2d, attention, einsum, reduction, softmax)",
        "reference": "PyTorch built-in operators (https://pytorch.org/docs/stable/torch.html)",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "execution_time": {
                "unit": "milliseconds",
                "description": "Operator execution time"
            },
            "tflops": {
                "unit": "TFLOPS",
                "description": "Floating point operations per second (where applicable)"
            }
        },
        "dataset_info": {
            "name": "synthetic_tensors",
            "size": "various tensor sizes per operator",
            "source": "torch.randn generated"
        },
        "parameters": {
            "iterations": iterations,
            "torch_threads": torch.get_num_threads(),
            "device": "cpu",
        },
        "results": all_results,
        "operator_configs": {name: cfg for name, cfg in OPERATOR_CONFIGS.items()}
    }

    write_results_section(args.results_json, args.section, output)

    print(f'[COMPUTE] Results saved to section "{args.section}" in: {args.results_json}')
    print('[COMPUTE] Benchmark complete')

if __name__ == '__main__':
    main()
