#!/usr/bin/env python3
import json
import sys


def load_json(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def cmd_get(filepath, *keys):
    data = load_json(filepath)
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)]
        else:
            print("null")
            return
    if isinstance(data, (dict, list)):
        print(json.dumps(data))
    else:
        print(data)


def cmd_field_exists(filepath, field):
    data = load_json(filepath)
    if isinstance(data, dict):
        print(1 if field in data else 0)
    else:
        print(0)


def cmd_count_results(filepath):
    data = load_json(filepath)
    if isinstance(data, dict) and "results" in data:
        results = data["results"]
        if isinstance(results, dict):
            print(len(results))
        elif isinstance(results, list):
            print(len(results))
        else:
            print(0)
    else:
        print(0)


def cmd_throughput_ge(filepath, threshold, *keys):
    data = load_json(filepath)
    try:
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and key.isdigit():
                value = value[int(key)]
            else:
                print(0)
                return
        if isinstance(value, dict):
            ops = value.get("avg_ops_sec", value.get("ops_per_sec", value.get("avg_ops_per_sec", 0)))
            print(1 if float(ops) >= float(threshold) else 0)
        else:
            print(1 if float(value) >= float(threshold) else 0)
    except (ValueError, TypeError):
        print(0)


def cmd_latency_le(filepath, threshold, *keys):
    data = load_json(filepath)
    try:
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and key.isdigit():
                value = value[int(key)]
            else:
                print(0)
                return
        if isinstance(value, dict):
            lat = value.get("avg_latency_ms", value.get("latency_avg_ms", value.get("avg_lat_ms", float("inf"))))
            print(1 if float(lat) <= float(threshold) else 0)
        else:
            print(1 if float(value) <= float(threshold) else 0)
    except (ValueError, TypeError):
        print(0)


def cmd_version(filepath):
    data = load_json(filepath)
    if isinstance(data, dict):
        ver = data.get("rocksdb_version", data.get("expected_version", data.get("version", "unknown")))
        print(ver)
    else:
        print("unknown")


def cmd_contains(filepath, keyword):
    data = load_json(filepath)
    text = json.dumps(data)
    print(1 if keyword in text else 0)


def cmd_write_version_info(filepath, timestamp, arch, kernel, os_name, cpu_model,
                           cores, mem_mb, rocksdb_ver, db_bench_path, static_lib,
                           arm_crc, neon):
    data = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cpu_cores": int(cores),
        "total_memory_mb": int(mem_mb),
        "rocksdb_version": rocksdb_ver,
        "db_bench_path": db_bench_path,
        "static_lib_exists": bool(static_lib),
        "arm64_crc32c_detected": bool(arm_crc),
        "neon_asimd_available": bool(neon),
    }
    save_json(filepath, data)
    print(f"Version info written to {filepath}")


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <file> <command> [args...]")
        print("Commands: get, field_exists, count_results, throughput_ge, latency_le, version, contains, write_version_info")
        sys.exit(1)

    filepath = sys.argv[1]
    command = sys.argv[2]
    args = sys.argv[3:]

    if command == "get":
        cmd_get(filepath, *args)
    elif command == "field_exists":
        cmd_field_exists(filepath, args[0] if args else "")
    elif command == "count_results":
        cmd_count_results(filepath)
    elif command == "throughput_ge":
        cmd_throughput_ge(filepath, args[0], *args[1:])
    elif command == "latency_le":
        cmd_latency_le(filepath, args[0], *args[1:])
    elif command == "version":
        cmd_version(filepath)
    elif command == "contains":
        cmd_contains(filepath, args[0] if args else "")
    elif command == "write_version_info":
        cmd_write_version_info(filepath, *args)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()