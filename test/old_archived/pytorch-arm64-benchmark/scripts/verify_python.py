#!/usr/bin/env python3
import json
import platform
import subprocess
import sys
import os
import argparse
import datetime

def get_cpu_info():
    try:
        with open('/proc/cpuinfo', 'r') as f:
            lines = f.readlines()
        model = ''
        cores = 0
        for line in lines:
            if line.startswith('model name') or line.startswith('Model Name'):
                model = line.split(':')[1].strip()
            if line.startswith('cpu cores') or line.startswith('CPU cores'):
                cores = int(line.split(':')[1].strip())
            if line.startswith('processor'):
                cores = max(cores, 1)
        num_processors = sum(1 for l in lines if l.startswith('processor'))
        if cores == 0:
            cores = num_processors
        if model == '':
            model = 'ARM64 CPU (' + str(num_processors) + ' cores)'
        return model, cores
    except Exception:
        return platform.processor() or 'Unknown ARM64', os.cpu_count() or 0

def get_memory_info():
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal'):
                    return int(line.split()[1]) * 1024
    except Exception:
        return 0

def get_os_info():
    try:
        with open('/etc/os-release', 'r') as f:
            info = {}
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=')
                    info[k] = v.strip('"')
            return info.get('PRETTY_NAME', platform.platform())
    except Exception:
        return platform.platform()

def check_pytorch():
    import torch
    version = torch.__version__
    cuda_available = torch.cuda.is_available()
    mps_available = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False
    num_threads = torch.get_num_threads()
    simd_info = {}
    if hasattr(torch._C, '_get_cpu_feature_flags'):
        flags = torch._C._get_cpu_feature_flags()
        simd_info = {"neon": "NEON" in str(flags), "asimd": "ASIMD" in str(flags)}
    has_compile = hasattr(torch, 'compile')
    return version, cuda_available, mps_available, num_threads, simd_info, has_compile

def check_numpy():
    import numpy
    return numpy.__version__

def main():
    parser = argparse.ArgumentParser(description='Verify PyTorch installation on ARM64')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--pytorch-version', default='2.7.0')
    args = parser.parse_args()

    arch = platform.machine()
    if arch not in ('aarch64', 'arm64'):
        print(f'[ERROR] Expected ARM64 architecture, got: {arch}')
        sys.exit(1)

    print('[VERIFY] Collecting environment information...')

    cpu_model, cpu_cores = get_cpu_info()
    total_memory = get_memory_info()
    os_name = get_os_info()
    kernel = platform.release()
    python_version = platform.python_version()

    pt_version, cuda_avail, mps_avail, num_threads, simd_info, has_compile = check_pytorch()
    numpy_version = check_numpy()

    import torch
    dtype_support = {
        "float32": True,
        "float64": True,
        "float16": hasattr(torch, 'float16'),
        "bfloat16": hasattr(torch, 'bfloat16'),
        "int8": hasattr(torch, 'int8'),
    }

    version_info = {
        "timestamp": datetime.datetime.now().isoformat(),
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cpu_cores": cpu_cores,
        "total_memory_bytes": total_memory,
        "total_memory_gb": round(total_memory / (1024**3), 2) if total_memory else 0,
        "python_version": python_version,
        "pytorch_version": pt_version,
        "numpy_version": numpy_version,
        "cuda_available": cuda_avail,
        "mps_available": mps_avail,
        "torch_num_threads": num_threads,
        "simd_info": simd_info,
        "has_compile": has_compile,
        "dtype_support": dtype_support,
        "pytorch_expected_version": args.pytorch_version,
        "version_match": pt_version.startswith(args.pytorch_version.split('+')[0]),
    }

    output_path = os.path.join(args.results_dir, 'version_info.json')
    with open(output_path, 'w') as f:
        json.dump(version_info, f, indent=2)

    print(f'[VERIFY] Version info saved to: {output_path}')
    print(f'[VERIFY] Architecture: {arch}')
    print(f'[VERIFY] CPU: {cpu_model} ({cpu_cores} cores)')
    print(f'[VERIFY] Memory: {version_info["total_memory_gb"]} GB')
    print(f'[VERIFY] PyTorch: {pt_version}')
    print(f'[VERIFY] CUDA: {cuda_avail}, MPS: {mps_avail}')
    print(f'[VERIFY] Threads: {num_threads}')
    print(f'[VERIFY] torch.compile: {has_compile}')
    print(f'[VERIFY] SIMD: {simd_info}')
    print(f'[VERIFY] Python: {python_version}')
    print(f'[VERIFY] NumPy: {numpy_version}')

    if not version_info["version_match"]:
        print(f'[WARN] PyTorch version mismatch: expected {args.pytorch_version}, got {pt_version}')

    if cuda_avail:
        print('[INFO] CUDA detected on ARM64 — GPU benchmarks may also be applicable')

    print('[VERIFY] Verification complete')

if __name__ == '__main__':
    main()