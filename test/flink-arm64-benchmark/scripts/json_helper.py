#!/usr/bin/env python3

import json
import sys


def write_version_info(args):
    (outfile, timestamp, arch, kernel, os_name, cpu_model,
     cores, mem_mb, sw_version, scala_ver, java_ver,
     install_path, task_slots, parallelism) = args[:14]
    data = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cpu_cores": int(cores),
        "memory_mb": int(mem_mb),
        "software": {
            "name": "Apache Flink",
            "version": sw_version,
            "scala_version": scala_ver,
            "java_version": java_ver,
            "install_path": install_path,
            "arm64_native": True,
            "task_slots": int(task_slots),
            "parallelism_default": int(parallelism)
        }
    }
    with open(outfile, "w") as f:
        json.dump(data, f, indent=2)


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <json_file> <command> [args...]", file=sys.stderr)
        sys.exit(1)

    json_file = sys.argv[1]
    command = sys.argv[2]

    if command == "write_version_info":
        write_version_info(sys.argv[1:])
        return

    try:
        with open(json_file, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {json_file}: {e}", file=sys.stderr)
        sys.exit(2)

    if command == "get":
        keys = sys.argv[3:]
        obj = data
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key, None)
            elif isinstance(obj, list) and key.isdigit():
                obj = obj[int(key)] if int(key) < len(obj) else None
            else:
                obj = None
        if obj is None:
            print("")
        else:
            print(obj)

    elif command == "field_exists":
        field = sys.argv[3]
        if isinstance(data, dict):
            print("1" if field in data else "0")
        else:
            print("0")

    elif command == "count_results":
        results = data.get("results", [])
        print(len(results))

    elif command == "throughput_ge":
        threshold = float(sys.argv[3])
        key1 = sys.argv[4] if len(sys.argv) > 4 else "records_per_sec"
        key2 = sys.argv[5] if len(sys.argv) > 5 else "throughput"
        results = data.get("results", [])
        if results and isinstance(results[0], dict):
            tp = results[0].get(key1, results[0].get(key2, 0))
            print("1" if tp >= threshold else "0")
        else:
            print("0")

    elif command == "latency_le":
        threshold = float(sys.argv[3])
        key1 = sys.argv[4] if len(sys.argv) > 4 else "avg_latency_ms"
        key2 = sys.argv[5] if len(sys.argv) > 5 else "latency_ms"
        results = data.get("results", [])
        if results and isinstance(results[0], dict):
            lat = results[0].get(key1, results[0].get(key2, 99999))
            print("1" if lat <= threshold else "0")
        else:
            print("1")

    elif command == "version":
        ver = data.get("software", {}).get("version", "")
        print(ver)

    elif command == "contains":
        text = json.dumps(data)
        keyword = sys.argv[3]
        print("1" if keyword in text else "0")

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()