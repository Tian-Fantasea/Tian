#!/usr/bin/env python3
import json
import sys
import os


def safe_int(val):
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    s = str(val).strip()
    if s.startswith("0x") or s.startswith("0X"):
        try:
            return int(s, 16)
        except ValueError:
            return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def navigate(data, keys):
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
            data = data[int(key)]
        else:
            return None
    return data


def cmd_get(filepath, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        result = navigate(data, keys)
        if result is None:
            print("0")
        elif isinstance(result, (int, float)):
            print(result)
        elif isinstance(result, str):
            print(result)
        elif isinstance(result, list):
            print(len(result))
        else:
            print(json.dumps(result))
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
        results = data.get("results", [])
        print(len(results))
    except Exception:
        print("0")


def cmd_throughput_ge(filepath, threshold, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        val = navigate(data, keys)
        if val is not None and isinstance(val, (int, float)) and val >= float(threshold):
            print("1")
        else:
            print("0")
    except Exception:
        print("0")


def cmd_latency_le(filepath, threshold, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        val = navigate(data, keys)
        if val is not None and isinstance(val, (int, float)) and val <= float(threshold):
            print("1")
        else:
            print("0")
    except Exception:
        print("0")


def cmd_avg_throughput(filepath, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        results = data.get("results", [])
        if not results:
            print("0")
            return
        values = []
        for r in results:
            val = navigate(r, list(keys)) if keys else None
            if val is not None and isinstance(val, (int, float)):
                values.append(float(val))
        if values:
            print(round(sum(values) / len(values), 2))
        else:
            print("0")
    except Exception:
        print("0")


def cmd_max_latency(filepath, *keys):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        results = data.get("results", [])
        if not results:
            print("0")
            return
        values = []
        for r in results:
            val = navigate(r, list(keys)) if keys else None
            if val is not None and isinstance(val, (int, float)):
                values.append(float(val))
        if values:
            print(round(max(values), 2))
        else:
            print("0")
    except Exception:
        print("0")


def cmd_version(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        print(data.get("software_version", "unknown"))
    except Exception:
        print("unknown")


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


def cmd_write_version_info(filepath, timestamp, arch, kernel, os_name,
                            cpu_model, cores, mem_mb, software_name,
                            software_version, runtime_ver1, runtime_ver2,
                            install_path, nodes_ready, data_scale,
                            *extra_args):
    data = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cores": safe_int(cores),
        "memory_mb": safe_int(mem_mb),
        "software_name": software_name,
        "software_version": software_version,
        "kubectl_version": runtime_ver1,
        "server_version": runtime_ver2,
        "cluster_name": install_path,
        "nodes_ready": safe_int(nodes_ready),
        "data_scale": safe_int(data_scale),
    }

    output_path = filepath
    i = 0
    while i < len(extra_args):
        arg = extra_args[i]
        if arg == "--output":
            if i + 1 < len(extra_args):
                output_path = extra_args[i + 1]
                i += 2
            else:
                i += 1
        elif arg == "--extra":
            if i + 1 < len(extra_args):
                kv = extra_args[i + 1]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    data[k] = v
                i += 2
            else:
                i += 1
        else:
            i += 1

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def cmd_write_benchmark_result(filepath, benchmark_name, description,
                               reference, performance_metrics, dataset_info,
                               results):
    data = {
        "benchmark": benchmark_name,
        "description": description,
        "reference": reference,
        "timestamp": results[0].get("timestamp", "") if results else "",
        "performance_metrics": performance_metrics,
        "dataset_info": dataset_info,
        "results": results
    }
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <filepath> <command> [args...]")
        sys.exit(1)

    filepath = sys.argv[1]
    command = sys.argv[2]
    args = sys.argv[3:]

    commands = {
        "get": cmd_get,
        "field_exists": cmd_field_exists,
        "count_results": cmd_count_results,
        "throughput_ge": cmd_throughput_ge,
        "latency_le": cmd_latency_le,
        "avg_throughput": cmd_avg_throughput,
        "max_latency": cmd_max_latency,
        "version": cmd_version,
        "contains": cmd_contains,
        "write_version_info": cmd_write_version_info,
        "write_benchmark_result": cmd_write_benchmark_result,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        sys.exit(1)

    commands[command](filepath, *args)


if __name__ == "__main__":
    main()