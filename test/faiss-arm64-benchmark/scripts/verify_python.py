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
            for line in lines:
                if line.startswith('implementer') or line.startswith('BogoMIPS'):
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

def check_faiss():
    import faiss
    version = getattr(faiss, '__version__', 'unknown')
    return version

def check_numpy():
    import numpy
    return numpy.__version__

def check_blas():
    try:
        import numpy
        config = numpy.show_config()
        return 'detected'
    except Exception:
        return 'unknown'

def main():
    parser = argparse.ArgumentParser(description='Verify Faiss installation on ARM64')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--faiss-version', default='1.14.2')
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
    faiss_version = check_faiss()
    numpy_version = check_numpy()
    blas_status = check_blas()

    import faiss
    simd_support = []
    for attr in ['supportAVX2', 'supportAVX512', 'supportNEON']:
        if hasattr(faiss, attr):
            simd_support.append(f'{attr}={faiss.attr()}')

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
        "faiss_version": faiss_version,
        "numpy_version": numpy_version,
        "blas_status": blas_status,
        "simd_features": simd_support,
        "faiss_expected_version": args.faiss_version,
        "version_match": str(faiss_version) == args.faiss_version
    }

    output_path = os.path.join(args.results_dir, 'version_info.json')
    with open(output_path, 'w') as f:
        json.dump(version_info, f, indent=2)

    print(f'[VERIFY] Version info saved to: {output_path}')
    print(f'[VERIFY] Architecture: {arch}')
    print(f'[VERIFY] CPU: {cpu_model} ({cpu_cores} cores)')
    print(f'[VERIFY] Memory: {version_info["total_memory_gb"]} GB')
    print(f'[VERIFY] Faiss: {faiss_version}')
    print(f'[VERIFY] Python: {python_version}')
    print(f'[VERIFY] NumPy: {numpy_version}')

    if not version_info["version_match"]:
        print(f'[WARN] Faiss version mismatch: expected {args.faiss_version}, got {faiss_version}')

    print('[VERIFY] Verification complete')

if __name__ == '__main__':
    main()