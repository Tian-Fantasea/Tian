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
            elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
                data = data[int(key)]
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
        results = data.get("results", [])
        print(len(results))
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
            elif isinstance(val, list) and key.isdigit() and int(key) < len(val):
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
            elif isinstance(val, list) and key.isdigit() and int(key) < len(val):
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
                           cpu_model, cores, mem_mb, software_version,
                           server_version, kubectl_version, cluster_name,
                           nodes_ready, data_scale):
    data = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cores": int(cores) if cores else 0,
        "memory_mb": int(mem_mb) if mem_mb else 0,
        "software_name": "kubernetes",
        "software_version": software_version,
        "server_version": server_version,
        "kubectl_version": kubectl_version,
        "cluster_name": cluster_name,
        "nodes_ready": int(nodes_ready) if nodes_ready else 0,
        "data_scale": int(data_scale) if data_scale else 1,
        "install_method": "kind",
        "language": "go",
        "arm64_native": True
    }
    with open(filepath, 'w') as f:
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