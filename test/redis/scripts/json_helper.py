#!/usr/bin/env python3
import json
import sys
import os


def cmd_get(filepath, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                print("0")
                return
        if isinstance(data, (int, float)):
            print(data)
        elif isinstance(data, str):
            print(data)
        elif isinstance(data, list):
            print(len(data))
        else:
            print(json.dumps(data))
    except Exception:
        print("0")


def cmd_field_exists(filepath, field):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        if isinstance(data, dict) and field in data:
            print("1")
        else:
            print("0")
    except Exception:
        print("0")


def cmd_count_results(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        if isinstance(data, dict) and 'results' in data:
            print(len(data['results']))
        elif isinstance(data, list):
            print(len(data))
        else:
            print("0")
    except Exception:
        print("0")


def cmd_throughput_ge(filepath, threshold, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        val = data
        for key in keys:
            if isinstance(val, dict) and key in val:
                val = val[key]
            elif isinstance(val, list) and key.isdigit():
                val = val[int(key)]
            else:
                print("0")
                return
        if isinstance(val, (int, float)) and val >= float(threshold):
            print("1")
        else:
            print("0")
    except Exception:
        print("0")


def cmd_latency_le(filepath, threshold, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        val = data
        for key in keys:
            if isinstance(val, dict) and key in val:
                val = val[key]
            elif isinstance(val, list) and key.isdigit():
                val = val[int(key)]
            else:
                print("0")
                return
        if isinstance(val, (int, float)) and val <= float(threshold):
            print("1")
        else:
            print("0")
    except Exception:
        print("0")


def cmd_contains(filepath, keyword):
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        if keyword in content:
            print("1")
        else:
            print("0")
    except Exception:
        print("0")


def cmd_version(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        if isinstance(data, dict):
            if 'software_version' in data:
                print(data['software_version'])
            elif 'version' in data:
                print(data['version'])
            else:
                print("unknown")
        else:
            print("unknown")
    except Exception:
        print("unknown")


def cmd_write_version_info(filepath, timestamp, arch, kernel, os_name,
                           cpu_model, cores, mem_mb, software_version,
                           compiler_ver, runtime_ver, install_path,
                           max_connections, thread_pool_size):
    data = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cpu_cores": int(cores),
        "memory_mb": int(mem_mb),
        "software": "redis",
        "software_version": software_version,
        "compiler_version": compiler_ver,
        "runtime_version": runtime_ver,
        "install_path": install_path,
        "max_connections": int(max_connections),
        "thread_pool_size": int(thread_pool_size),
        "benchmark_platform": "ARM64",
        "benchmark_tool": "redis-benchmark + custom YCSB"
    }
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Version info written to {filepath}")


def cmd_sum_fields(filepath, *field_names):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        total = 0.0
        for name in field_names:
            if isinstance(data, dict) and name in data:
                val = data[name]
                if isinstance(val, (int, float)):
                    total += val
        print(total)
    except Exception:
        print("0")


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <filepath> <command> [args...]")
        print("Commands: get, field_exists, count_results, throughput_ge,")
        print("  latency_le, contains, version, write_version_info, sum_fields")
        sys.exit(1)

    filepath = sys.argv[1]
    command = sys.argv[2]
    args = sys.argv[3:]

    commands = {
        'get': cmd_get,
        'field_exists': cmd_field_exists,
        'count_results': cmd_count_results,
        'throughput_ge': cmd_throughput_ge,
        'latency_le': cmd_latency_le,
        'contains': cmd_contains,
        'version': cmd_version,
        'write_version_info': cmd_write_version_info,
        'sum_fields': cmd_sum_fields,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        sys.exit(1)

    commands[command](filepath, *args)


if __name__ == '__main__':
    main()