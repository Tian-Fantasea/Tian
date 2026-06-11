#!/usr/bin/env python3
import json
import sys
import os


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
            print(f"Key '{key}' not found")
            return None
    print(data if data is not None else "null")


def cmd_field_exists(filepath, field):
    data = load_json(filepath)
    if isinstance(data, dict):
        print(1 if field in data else 0)
    elif isinstance(data, list):
        found = any(field in item if isinstance(item, dict) else False for item in data)
        print(1 if found else 0)
    else:
        print(0)


def cmd_count_results(filepath):
    data = load_json(filepath)
    results = data.get("results", data)
    if isinstance(results, list):
        print(len(results))
    elif isinstance(results, dict):
        print(len(results))
    else:
        print(0)


def cmd_throughput_ge(filepath, threshold, *keys):
    data = load_json(filepath)
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit():
            value = value[int(key)]
        else:
            print(0)
            return
    try:
        numeric_val = float(value)
        print(1 if numeric_val >= float(threshold) else 0)
    except (TypeError, ValueError):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    metric = item
                    for k in keys:
                        if isinstance(metric, dict) and k in metric:
                            metric = metric[k]
                        else:
                            break
                    try:
                        if float(metric) >= float(threshold):
                            print(1)
                            return
                    except (TypeError, ValueError):
                        continue
        print(0)


def cmd_latency_le(filepath, threshold, *keys):
    data = load_json(filepath)
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit():
            value = value[int(key)]
        else:
            print(0)
            return
    try:
        numeric_val = float(value)
        print(1 if numeric_val <= float(threshold) else 0)
    except (TypeError, ValueError):
        print(0)


def cmd_version(filepath):
    data = load_json(filepath)
    version = data.get("software_version", data.get("version", "unknown"))
    print(version)


def cmd_contains(filepath, keyword):
    with open(filepath, "r") as f:
        content = f.read()
    print(1 if keyword in content else 0)


def cmd_write_version_info(filepath, timestamp, arch, kernel, os_name, cpu_model,
                            cores, mem_mb, software_name, software_version,
                            extra1, extra2, extra3, extra4):
    data = {
        "timestamp": timestamp.replace("\n", "").replace("\t", ""),
        "architecture": arch.replace("\n", "").replace("\t", ""),
        "kernel": kernel.replace("\n", "").replace("\t", ""),
        "os": os_name.replace("\n", "").replace("\t", ""),
        "cpu_model": cpu_model.replace("\n", "").replace("\t", ""),
        "cores": int(cores),
        "memory_mb": int(mem_mb),
        "software_name": software_name.replace("\n", "").replace("\t", ""),
        "software_version": software_version.replace("\n", "").replace("\t", ""),
        "extra_info": {
            "field1": extra1.replace("\n", "").replace("\t", "") if extra1 else "",
            "field2": extra2.replace("\n", "").replace("\t", "") if extra2 else "",
            "field3": int(extra3) if extra3 and extra3.isdigit() else 0,
            "field4": int(extra4) if extra4 and extra4.isdigit() else 0,
        }
    }
    save_json(filepath, data)
    print(f"Version info written to {filepath}")


def cmd_write_ceph_conf(filepath, fsid, cluster_name, hostname, mon_id):
    data = {
        "fsid": fsid.replace("\n", "").replace("\t", ""),
        "cluster_name": cluster_name.replace("\n", "").replace("\t", ""),
        "mon_host": hostname.replace("\n", "").replace("\t", ""),
        "mon_id": mon_id.replace("\n", "").replace("\t", "")
    }
    save_json(filepath, data)
    print(f"Ceph conf data written to {filepath}")


def cmd_write_ceph_conf_file(conf_path, fsid, mon_id, mon_host, mon_ip):
    lines = [
        "[global]",
        f"fsid = {fsid.replace(chr(10), '').replace(chr(9), '')}",
        f"mon initial members = {mon_id.replace(chr(10), '').replace(chr(9), '')}",
        f"mon host = {mon_host.replace(chr(10), '').replace(chr(9), '')}",
        "osd pool default size = 1",
        "osd pool default min size = 1",
        "osd pool default pg num = 128",
        "osd pool default pgp num = 128",
        "osd object store = bluestore",
        "bluefs buffered read = true",
        f"[mon.{mon_id.replace(chr(10), '').replace(chr(9), '')}]",
        f"host = {mon_host.replace(chr(10), '').replace(chr(9), '')}",
        f"mon addr = {mon_ip.replace(chr(10), '').replace(chr(9), '')}:6789",
        "[osd]",
        "osd memory target = 1073741824",
        "osd op threads = 8",
        f"[mgr.{mon_id.replace(chr(10), '').replace(chr(9), '')}]",
        f"host = {mon_host.replace(chr(10), '').replace(chr(9), '')}",
    ]
    with open(conf_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Ceph conf file written to {conf_path}")


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <file> <command> [args...]")
        print("Commands: get, field_exists, count_results, throughput_ge, latency_le, version, contains, write_version_info, write_ceph_conf, write_ceph_conf_file")
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
        threshold = args[0] if args else "0"
        keys = args[1:]
        cmd_throughput_ge(filepath, threshold, *keys)
    elif command == "latency_le":
        threshold = args[0] if args else "999999"
        keys = args[1:]
        cmd_latency_le(filepath, threshold, *keys)
    elif command == "version":
        cmd_version(filepath)
    elif command == "contains":
        cmd_contains(filepath, args[0] if args else "")
    elif command == "write_version_info":
        cmd_write_version_info(filepath, *args)
    elif command == "write_ceph_conf":
        cmd_write_ceph_conf(filepath, *args)
    elif command == "write_ceph_conf_file":
        cmd_write_ceph_conf_file(*args)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()