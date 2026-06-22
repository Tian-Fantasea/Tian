#!/usr/bin/env python3
import json
import sys


def load_json(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def safe_int(value):
    try:
        if isinstance(value, str):
            if value.startswith("0x") or value.startswith("0X"):
                return int(value, 16)
            value = value.replace(",", "")
            return int(float(value))
        return int(value)
    except (ValueError, TypeError):
        return 0


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
            print(1 if safe_int(ops) >= int(threshold) else 0)
        else:
            print(1 if safe_int(value) >= int(threshold) else 0)
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
            print(1 if safe_int(lat) <= int(threshold) else 0)
        else:
            print(1 if safe_int(value) <= int(threshold) else 0)
    except (ValueError, TypeError):
        print(0)


def cmd_avg_throughput(filepath, *keys):
    data = load_json(filepath)
    values = []
    try:
        if not keys:
            if isinstance(data, dict) and "results" in data:
                results = data["results"]
                if isinstance(results, list):
                    for r in results:
                        ops = r.get("ops_per_sec", r.get("avg_ops_sec", r.get("avg_ops_per_sec", 0)))
                        if isinstance(ops, (int, float)) and ops > 0:
                            values.append(float(ops))
                elif isinstance(results, dict):
                    for k, v in results.items():
                        if isinstance(v, dict):
                            ops = v.get("avg_ops_sec", v.get("ops_per_sec", 0))
                            if isinstance(ops, (int, float)) and ops > 0:
                                values.append(float(ops))
            else:
                target = data
                for key in keys:
                    if isinstance(target, dict) and key in target:
                        target = target[key]
                    elif isinstance(target, list) and key.isdigit():
                        target = target[int(key)]
                if isinstance(target, list):
                    for item in target:
                        if isinstance(item, dict):
                            ops = item.get("ops_per_sec", item.get("avg_ops_sec", 0))
                            if isinstance(ops, (int, float)) and ops > 0:
                                values.append(float(ops))
                elif isinstance(target, dict):
                    for k, v in target.items():
                        if isinstance(v, dict):
                            ops = v.get("avg_ops_sec", v.get("ops_per_sec", 0))
                            if isinstance(ops, (int, float)) and ops > 0:
                                values.append(float(ops))
        if values:
            print(round(sum(values) / len(values), 2))
        else:
            print(0)
    except Exception:
        print(0)


def cmd_max_latency(filepath, *keys):
    data = load_json(filepath)
    values = []
    try:
        if not keys:
            if isinstance(data, dict) and "results" in data:
                results = data["results"]
                if isinstance(results, list):
                    for r in results:
                        lat = r.get("latency_avg_ms", r.get("avg_latency_ms", 0))
                        if isinstance(lat, (int, float)) and lat > 0:
                            values.append(float(lat))
                elif isinstance(results, dict):
                    for k, v in results.items():
                        if isinstance(v, dict):
                            lat = v.get("avg_latency_ms", v.get("latency_avg_ms", 0))
                            if isinstance(lat, (int, float)) and lat > 0:
                                values.append(float(lat))
            else:
                target = data
                for key in keys:
                    if isinstance(target, dict) and key in target:
                        target = target[key]
                    elif isinstance(target, list) and key.isdigit():
                        target = target[int(key)]
                if isinstance(target, list):
                    for item in target:
                        if isinstance(item, dict):
                            lat = item.get("latency_avg_ms", item.get("avg_latency_ms", 0))
                            if isinstance(lat, (int, float)) and lat > 0:
                                values.append(float(lat))
                elif isinstance(target, dict):
                    for k, v in target.items():
                        if isinstance(v, dict):
                            lat = v.get("avg_latency_ms", v.get("latency_avg_ms", 0))
                            if isinstance(lat, (int, float)) and lat > 0:
                                values.append(float(lat))
        if values:
            print(round(max(values), 4))
        else:
            print(0)
    except Exception:
        print(0)


def cmd_version(filepath):
    data = load_json(filepath)
    if isinstance(data, dict):
        ver = data.get("rocksdb_version", data.get("expected_version", data.get("software_version", data.get("version", "unknown"))))
        print(ver)
    else:
        print("unknown")


def cmd_contains(filepath, keyword):
    with open(filepath, "r") as f:
        content = f.read()
    print(1 if keyword in content else 0)


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
        "software": "rocksdb",
        "rocksdb_version": rocksdb_ver,
        "db_bench_path": db_bench_path,
        "static_lib_exists": bool(static_lib),
        "arm64_crc32c_detected": bool(arm_crc),
        "neon_asimd_available": bool(neon),
        "benchmark_platform": "ARM64",
        "benchmark_tool": "db_bench + custom YCSB"
    }
    save_json(filepath, data)
    print(f"Version info written to {filepath}")


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <file> <command> [args...]")
        print("Commands: get, field_exists, count_results, throughput_ge, latency_le, avg_throughput, max_latency, version, contains, write_version_info")
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
        'avg_throughput': cmd_avg_throughput,
        'max_latency': cmd_max_latency,
        'version': cmd_version,
        'contains': cmd_contains,
        'write_version_info': cmd_write_version_info,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        sys.exit(1)

    commands[command](filepath, *args)


if __name__ == "__main__":
    main()
