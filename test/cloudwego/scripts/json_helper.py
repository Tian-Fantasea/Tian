#!/usr/bin/env python3
import argparse
import json
import os
import sys


def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def cmd_write_version_info(filepath, args):
    (
        timestamp, arch, kernel, os_name, cpu_model,
        cores, mem_mb, kitex_ver, hertz_ver,
        go_ver, wrk_ver, taskset_avail,
    ) = args
    cores = int(cores) if cores and cores not in ("unknown", "None", "") else 0
    mem_mb = int(mem_mb) if mem_mb and mem_mb not in ("unknown", "None", "") else 0
    data = load_or_create_json(filepath)
    data["software"] = "cloudwego"
    data["version"] = f"Kitex {kitex_ver} + Hertz {hertz_ver}"
    data["architecture"] = arch
    data["timestamp"] = timestamp
    data["version_info"] = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cores": cores,
        "memory_mb": mem_mb,
        "kitex_version": kitex_ver,
        "hertz_version": hertz_ver,
        "go_version": go_ver,
        "wrk_version": wrk_ver,
        "taskset_available": taskset_avail,
    }
    save_json(filepath, data)
    print(f"[JSON] Version info written to {filepath}")


def cmd_write_results_section(filepath, args):
    section_name, section_json_str = args[0], args[1]
    data = load_or_create_json(filepath)
    try:
        section_data = json.loads(section_json_str)
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON for section {section_name}")
        sys.exit(1)
    data[section_name] = section_data
    save_json(filepath, data)
    print(f"[JSON] Section '{section_name}' written to {filepath}")


def cmd_get(filepath, args):
    data = load_or_create_json(filepath)
    for key in args:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            print("None")
            return
    print(data)


def cmd_field_exists(filepath, args):
    data = load_or_create_json(filepath)
    field = args[0]
    if field in data:
        print("1")
    else:
        print("0")


def cmd_contains(filepath, args):
    data = load_or_create_json(filepath)
    text = json.dumps(data)
    keyword = args[0]
    if keyword in text:
        print("1")
    else:
        print("0")


def main():
    parser = argparse.ArgumentParser(description="JSON helper for CloudWeGo benchmark")
    parser.add_argument("filepath", help="Path to JSON file")
    parser.add_argument("command", help="Command to execute")
    parser.add_argument("args", nargs="*", help="Arguments for the command")
    args = parser.parse_args()

    commands = {
        "write_version_info": cmd_write_version_info,
        "write_results_section": cmd_write_results_section,
        "get": cmd_get,
        "field_exists": cmd_field_exists,
        "contains": cmd_contains,
    }

    if args.command not in commands:
        print(f"[ERROR] Unknown command: {args.command}")
        sys.exit(1)

    commands[args.command](args.filepath, args.args)


if __name__ == "__main__":
    main()
