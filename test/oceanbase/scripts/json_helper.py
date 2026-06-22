#!/usr/bin/env python3
import json
import sys
import os
from datetime import datetime


def load_json(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)


def get_nested(data, keys):
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)]
        else:
            return None
    return data


def cmd_get(filepath, *keys):
    data = load_json(filepath)
    result = get_nested(data, keys)
    if result is None:
        print("NULL")
    else:
        print(result)


def cmd_field_exists(filepath, field):
    data = load_json(filepath)
    if isinstance(data, dict):
        print(1 if field in data else 0)
    elif isinstance(data, list):
        print(1 if any(field in item for item in data if isinstance(item, dict)) else 0)
    else:
        print(0)


def cmd_count_results(filepath):
    data = load_json(filepath)
    if isinstance(data, dict) and "results" in data:
        print(len(data["results"]))
    elif isinstance(data, list):
        print(len(data))
    else:
        print(0)


def cmd_throughput_ge(filepath, threshold, *keys):
    data = load_json(filepath)
    value = get_nested(data, keys)
    if value is None:
        print(0)
    else:
        try:
            print(1 if float(value) >= float(threshold) else 0)
        except (ValueError, TypeError):
            print(0)


def cmd_latency_le(filepath, threshold, *keys):
    data = load_json(filepath)
    value = get_nested(data, keys)
    if value is None:
        print(0)
    else:
        try:
            print(1 if float(value) <= float(threshold) else 0)
        except (ValueError, TypeError):
            print(0)


def cmd_version(filepath):
    data = load_json(filepath)
    if isinstance(data, dict):
        ver = data.get("software_version", data.get("version", "unknown"))
        print(ver)
    else:
        print("unknown")


def cmd_contains(filepath, keyword):
    with open(filepath, "r") as f:
        content = f.read()
    print(1 if keyword in content else 0)


def cmd_write_version_info(filepath, timestamp, arch, kernel, os_name, cpu_model,
                           cores, mem_mb, sw_version, obd_version, java_ver,
                           ob_home, warehouse_count, terminal_count):
    data = {
        "timestamp": str(timestamp),
        "architecture": str(arch),
        "kernel": str(kernel),
        "os": str(os_name),
        "cpu_model": str(cpu_model),
        "cores": int(cores),
        "memory_mb": int(mem_mb),
        "software_name": "oceanbase",
        "software_version": str(sw_version),
        "obd_version": str(obd_version),
        "java_version": str(java_ver),
        "oceanbase_home": str(ob_home),
        "tpcc_warehouse_count": int(warehouse_count),
        "tpcc_terminal_count": int(terminal_count)
    }
    save_json(filepath, data)


def cmd_avg_throughput(filepath, *keys):
    data = load_json(filepath)
    results = data.get("results", [])
    if not results:
        print(0)
        return
    values = []
    for r in results:
        val = get_nested(r, keys)
        if val is not None:
            try:
                values.append(float(val))
            except (ValueError, TypeError):
                pass
    if values:
        print(sum(values) / len(values))
    else:
        print(0)


def cmd_max_latency(filepath, *keys):
    data = load_json(filepath)
    results = data.get("results", [])
    if not results:
        print(0)
        return
    values = []
    for r in results:
        val = get_nested(r, keys)
        if val is not None:
            try:
                values.append(float(val))
            except (ValueError, TypeError):
                pass
    if values:
        print(max(values))
    else:
        print(0)


def cmd_merge_jsons(output_path, *input_paths):
    merged = {
        "software_name": "oceanbase",
        "benchmarks": []
    }
    for ip in input_paths:
        if os.path.exists(ip):
            data = load_json(ip)
            if isinstance(data, dict) and "benchmark" in data:
                merged["benchmarks"].append(data)
    save_json(output_path, merged)


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <filepath> <command> [args...]")
        sys.exit(1)

    filepath = sys.argv[1]
    command = sys.argv[2]
    args = sys.argv[3:]

    commands = {
        "get": lambda: cmd_get(filepath, *args),
        "field_exists": lambda: cmd_field_exists(filepath, args[0] if args else ""),
        "count_results": lambda: cmd_count_results(filepath),
        "throughput_ge": lambda: cmd_throughput_ge(filepath, args[0], *args[1:]),
        "latency_le": lambda: cmd_latency_le(filepath, args[0], *args[1:]),
        "version": lambda: cmd_version(filepath),
        "contains": lambda: cmd_contains(filepath, args[0] if args else ""),
        "write_version_info": lambda: cmd_write_version_info(filepath, *args),
        "avg_throughput": lambda: cmd_avg_throughput(filepath, *args),
        "max_latency": lambda: cmd_max_latency(filepath, *args),
        "merge_jsons": lambda: cmd_merge_jsons(filepath, *args),
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        sys.exit(1)

    commands[command]()


if __name__ == "__main__":
    main()