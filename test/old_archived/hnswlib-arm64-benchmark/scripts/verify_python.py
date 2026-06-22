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

def check_hnswlib():
    import hnswlib
    return getattr(hnswlib, '__version__', 'unknown')

def check_numpy():
    import numpy
    return numpy.__version__

def main():
    parser = argparse.ArgumentParser(description='Verify hnswlib installation on ARM64')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--hnswlib-version', default='0.8.0')
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
    hnswlib_version = check_hnswlib()
    numpy_version = check_numpy()

    import hnswlib
    p = hnswlib.Index(space='l2', dim=8)
    p.init_index(max_elements=10, ef_construction=200, M=16)
    index_props = {
        "space": p.space,
        "dim": p.dim,
        "M": p.M,
        "ef_construction": p.ef_construction,
        "max_elements": p.max_elements,
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
        "hnswlib_version": hnswlib_version,
        "numpy_version": numpy_version,
        "hnswlib_expected_version": args.hnswlib_version,
        "version_match": str(hnswlib_version) == args.hnswlib_version,
        "index_properties": index_props,
    }

    output_path = os.path.join(args.results_dir, 'version_info.json')
    with open(output_path, 'w') as f:
        json.dump(version_info, f, indent=2)

    print(f'[VERIFY] Version info saved to: {output_path}')
    print(f'[VERIFY] Architecture: {arch}')
    print(f'[VERIFY] CPU: {cpu_model} ({cpu_cores} cores)')
    print(f'[VERIFY] Memory: {version_info["total_memory_gb"]} GB')
    print(f'[VERIFY] hnswlib: {hnswlib_version}')
    print(f'[VERIFY] Python: {python_version}')
    print(f'[VERIFY] NumPy: {numpy_version}')
    print(f'[VERIFY] Index props: M={index_props["M"]}, ef_construction={index_props["ef_construction"]}')

    if not version_info["version_match"]:
        print(f'[WARN] hnswlib version mismatch: expected {args.hnswlib_version}, got {hnswlib_version}')

    print('[VERIFY] Verification complete')

if __name__ == '__main__':
    main()