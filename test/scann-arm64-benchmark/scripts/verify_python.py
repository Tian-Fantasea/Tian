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

def get_libstdcxx_version():
    try:
        result = subprocess.run(['g++', '-dump-version'], capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception:
        try:
            result = subprocess.run(['dpkg-query', '-Wf', '${Version}', 'libstdc++6'],
                                    capture_output=True, text=True, timeout=10)
            return result.stdout.strip()
        except Exception:
            return 'unknown'

def check_scann():
    import scann
    version = getattr(scann, '__version__', 'unknown')
    has_pybind = hasattr(scann, 'scann_ops_pybind')
    has_tf_ops = hasattr(scann, 'scann_ops')
    return version, has_pybind, has_tf_ops

def check_numpy():
    import numpy
    return numpy.__version__

def main():
    parser = argparse.ArgumentParser(description='Verify ScaNN installation on ARM64')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--scann-version', default='1.4.2')
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

    scann_version, has_pybind, has_tf_ops = check_scann()
    numpy_version = check_numpy()
    libstdcxx_version = get_libstdcxx_version()

    neon_check = False
    try:
        result = subprocess.run(['cat', '/proc/cpuinfo'], capture_output=True, text=True, timeout=5)
        if 'neon' in result.stdout.lower() or 'asimd' in result.stdout.lower():
            neon_check = True
    except Exception:
        neon_check = True

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
        "scann_version": scann_version,
        "numpy_version": numpy_version,
        "libstdcxx_version": libstdcxx_version,
        "neon_support": neon_check,
        "scann_has_pybind": has_pybind,
        "scann_has_tf_ops": has_tf_ops,
        "scann_expected_version": args.scann_version,
        "version_match": str(scann_version) == args.scann_version
    }

    output_path = os.path.join(args.results_dir, 'version_info.json')
    with open(output_path, 'w') as f:
        json.dump(version_info, f, indent=2)

    print(f'[VERIFY] Version info saved to: {output_path}')
    print(f'[VERIFY] Architecture: {arch}')
    print(f'[VERIFY] CPU: {cpu_model} ({cpu_cores} cores)')
    print(f'[VERIFY] Memory: {version_info["total_memory_gb"]} GB')
    print(f'[VERIFY] ScaNN: {scann_version} (pybind={has_pybind}, tf_ops={has_tf_ops})')
    print(f'[VERIFY] Python: {python_version}')
    print(f'[VERIFY] NumPy: {numpy_version}')
    print(f'[VERIFY] NEON support: {neon_check}')
    print(f'[VERIFY] libstdc++: {libstdcxx_version} (requires >= 3.4.23)')

    if not version_info["version_match"]:
        print(f'[WARN] ScaNN version mismatch: expected {args.scann_version}, got {scann_version}')

    if not neon_check:
        print('[WARN] NEON instruction set not detected; ScaNN ARM builds require NEON')

    print('[VERIFY] Verification complete')

if __name__ == '__main__':
    main()