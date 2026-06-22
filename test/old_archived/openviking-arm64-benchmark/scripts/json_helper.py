#!/usr/bin/env python3
import json
import sys


def get_value(data, keys):
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            try:
                idx = int(key)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def cmd_get(filepath, *keys):
    with open(filepath) as f:
        data = json.load(f)
    val = get_value(data, list(keys))
    if val is None:
        print("None")
    else:
        print(val)


def cmd_field_exists(filepath, field):
    with open(filepath) as f:
        data = json.load(f)
    exists = 1 if field in data else 0
    print(exists)


def cmd_count_results(filepath):
    with open(filepath) as f:
        data = json.load(f)
    results = data.get("results", [])
    print(len(results))


def cmd_throughput_ge(filepath, threshold, metric_name, *parent_keys):
    with open(filepath) as f:
        data = json.load(f)
    keys = list(parent_keys) + [metric_name]
    val = get_value(data, keys)
    if val is None:
        print(0)
        return
    try:
        numeric_val = float(val)
        if numeric_val >= float(threshold):
            print(1)
        else:
            print(0)
    except (ValueError, TypeError):
        print(0)


def cmd_latency_le(filepath, threshold, metric_name, *parent_keys):
    with open(filepath) as f:
        data = json.load(f)
    keys = list(parent_keys) + [metric_name]
    val = get_value(data, keys)
    if val is None:
        print(0)
        return
    try:
        numeric_val = float(val)
        if numeric_val <= float(threshold):
            print(1)
        else:
            print(0)
    except (ValueError, TypeError):
        print(0)


def cmd_version(filepath):
    with open(filepath) as f:
        data = json.load(f)
    ver = data.get("software_version", "unknown")
    print(ver)


def cmd_contains(filepath, keyword):
    with open(filepath) as f:
        content = f.read()
    found = 1 if keyword in content else 0
    print(found)


def cmd_write_version_info(filepath, timestamp, arch, kernel, os_name, cpu_model,
                           cores, mem_mb, software_version, scala_ver,
                           java_ver, install_path, max_concurrent_emb,
                           max_concurrent_vlm):
    data = {
        "timestamp": timestamp,
        "environment": {
            "architecture": arch,
            "kernel": kernel,
            "os": os_name,
            "cpu_model": cpu_model,
            "cores": int(cores),
            "memory_mb": int(mem_mb)
        },
        "software": {
            "name": "openviking",
            "version": software_version,
            "install_path": install_path
        },
        "runtime": {
            "java_version": java_ver,
            "scala_version": scala_ver,
            "max_concurrent_embedding": int(max_concurrent_emb),
            "max_concurrent_vlm": int(max_concurrent_vlm)
        }
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <file> <command> [args...]")
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
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        sys.exit(1)

    commands[command](filepath, *args)


if __name__ == "__main__":
    main()