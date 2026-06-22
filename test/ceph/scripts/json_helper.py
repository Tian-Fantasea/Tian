#!/usr/bin/env python3
import json
import sys
import os
import argparse


def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def navigate(data, keys):
    if not keys:
        return data
    for key in keys:
        if isinstance(data, dict):
            if key in data:
                data = data[key]
            else:
                return None
        elif isinstance(data, list):
            try:
                idx = int(key)
                data = data[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    if isinstance(data, (dict, list)):
        return data
    return None


def cmd_get(args):
    with open(args.file) as f:
        data = json.load(f)
    result = navigate(data, args.keys)
    if result is None:
        print("NULL")
    elif isinstance(result, dict) or isinstance(result, list):
        print(json.dumps(result, indent=2))
    else:
        print(result)


def cmd_field_exists(args):
    keys = args.keys
    if len(keys) == 0:
        print(0)
        return
    with open(args.file) as f:
        data = json.load(f)
    result = navigate(data, keys)
    if result is None:
        print(0)
    else:
        print(1)


def cmd_count_results(args):
    with open(args.file) as f:
        data = json.load(f)
    if "results" in data and isinstance(data["results"], list):
        print(len(data["results"]))
    else:
        count = 0
        for v in data.values():
            if isinstance(v, list):
                count += len(v)
        print(count)


def cmd_throughput_ge(args):
    threshold = int(args.threshold)
    with open(args.file) as f:
        data = json.load(f)
    value = navigate(data, args.keys)
    if value is None:
        print(0)
        return
    try:
        val = int(value)
    except (ValueError, TypeError):
        try:
            val = float(value)
            val = int(val)
        except (ValueError, TypeError):
            print(0)
            return
    if val >= threshold:
        print(1)
    else:
        print(0)


def cmd_latency_le(args):
    threshold = int(args.threshold)
    with open(args.file) as f:
        data = json.load(f)
    value = navigate(data, args.keys)
    if value is None:
        print(0)
        return
    try:
        val = int(value)
    except (ValueError, TypeError):
        try:
            val = float(value)
            val = int(val)
        except (ValueError, TypeError):
            print(0)
            return
    if val <= threshold:
        print(1)
    else:
        print(0)


def cmd_avg_throughput(args):
    values = []
    with open(args.file) as f:
        data = json.load(f)
    results = navigate(data, args.keys)
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                last_key = args.keys[-1] if args.keys else None
                if last_key and last_key in item:
                    try:
                        values.append(float(item[last_key]))
                    except (ValueError, TypeError):
                        pass
    if values:
        avg = sum(values) / len(values)
        print(int(avg))
    else:
        print(0)


def cmd_max_latency(args):
    values = []
    with open(args.file) as f:
        data = json.load(f)
    results = navigate(data, args.keys)
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                last_key = args.keys[-1] if args.keys else None
                if last_key and last_key in item:
                    try:
                        values.append(float(item[last_key]))
                    except (ValueError, TypeError):
                        pass
    if values:
        print(int(max(values)))
    else:
        print(0)


def cmd_version(args):
    with open(args.file) as f:
        data = json.load(f)
    if "version" in data:
        print(data["version"])
    else:
        print("unknown")


def cmd_contains(args):
    with open(args.file) as f:
        content = f.read()
    if args.keyword in content:
        print(1)
    else:
        print(0)


def cmd_write_version_info(args):
    v = args.values
    d = {
        "timestamp": v[0],
        "architecture": v[1],
        "kernel": v[2],
        "os": v[3],
        "cpu_model": v[4],
        "cores": int(v[5]) if v[5] not in ("unknown", "") else 0,
        "memory_mb": int(v[6]) if v[6] not in ("unknown", "") else 0,
        "software_name": v[7],
        "software_version": v[8],
        "ceph_version": v[9],
        "ceph_conf_path": v[10],
        "ceph_found": int(v[11]) if v[11] else 0,
        "parallelism": int(v[12]) if v[12] else 4,
        "cluster_health": v[13] if len(v) > 13 else "unknown",
        "osd_count": int(v[14]) if len(v) > 14 and v[14] not in ("unknown", "") else 0,
        "mon_count": int(v[15]) if len(v) > 15 and v[15] not in ("unknown", "") else 0,
        "neon_available": int(v[16]) if len(v) > 16 else 0,
        "crc32c_available": int(v[17]) if len(v) > 17 else 0,
    }
    arm64 = {
        "is_arm64": d["architecture"] in ("aarch64", "arm64"),
        "neon_available": bool(d["neon_available"]),
        "crc32c_available": bool(d["crc32c_available"]),
    }
    d["arm64_features"] = arm64
    results = load_or_create_json(args.file)
    results["software"] = d["software_name"]
    results["version"] = d["software_version"]
    results["architecture"] = d["architecture"]
    results["timestamp"] = d["timestamp"]
    results["version_info"] = d
    with open(args.file, "w") as f:
        json.dump(results, f, indent=2)


def cmd_write_results_section(args):
    results = load_or_create_json(args.file)
    section_data = json.loads(args.data)
    results[args.section] = section_data
    with open(args.file, "w") as f:
        json.dump(results, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="JSON helper for shUnit2 assertions")
    parser.add_argument("file", help="JSON file to operate on")
    subparsers = parser.add_subparsers(dest="subparser", help="Commands")

    sp_get = subparsers.add_parser("get", help="Get value by key path")
    sp_get.add_argument("keys", nargs="+", help="Key path")

    sp_field_exists = subparsers.add_parser("field_exists", help="Check if field exists")
    sp_field_exists.add_argument("keys", nargs="+", help="Key path")

    sp_count = subparsers.add_parser("count_results", help="Count results array")

    sp_throughput_ge = subparsers.add_parser("throughput_ge", help="Check throughput >= threshold")
    sp_throughput_ge.add_argument("threshold", help="Minimum threshold")
    sp_throughput_ge.add_argument("keys", nargs="+", help="Key path to throughput value")

    sp_latency_le = subparsers.add_parser("latency_le", help="Check latency <= threshold")
    sp_latency_le.add_argument("threshold", help="Maximum threshold")
    sp_latency_le.add_argument("keys", nargs="+", help="Key path to latency value")

    sp_avg = subparsers.add_parser("avg_throughput", help="Average throughput across results")
    sp_avg.add_argument("keys", nargs="+", help="Key path")

    sp_max = subparsers.add_parser("max_latency", help="Max latency across results")
    sp_max.add_argument("keys", nargs="+", help="Key path")

    sp_version = subparsers.add_parser("version", help="Get software version")

    sp_contains = subparsers.add_parser("contains", help="Check if JSON contains keyword")
    sp_contains.add_argument("keyword", help="Keyword to search")

    sp_write_vi = subparsers.add_parser("write_version_info", help="Write version info into results.json section")
    sp_write_vi.add_argument("values", nargs="+", help="Version info values")

    sp_write_section = subparsers.add_parser("write_results_section", help="Write benchmark data into a section")
    sp_write_section.add_argument("--section", required=True, help="Section name in results.json")
    sp_write_section.add_argument("--data", required=True, help="JSON string of benchmark data")

    args = parser.parse_args()

    if args.subparser == "get":
        cmd_get(args)
    elif args.subparser == "field_exists":
        cmd_field_exists(args)
    elif args.subparser == "count_results":
        cmd_count_results(args)
    elif args.subparser == "throughput_ge":
        cmd_throughput_ge(args)
    elif args.subparser == "latency_le":
        cmd_latency_le(args)
    elif args.subparser == "avg_throughput":
        cmd_avg_throughput(args)
    elif args.subparser == "max_latency":
        cmd_max_latency(args)
    elif args.subparser == "version":
        cmd_version(args)
    elif args.subparser == "contains":
        cmd_contains(args)
    elif args.subparser == "write_version_info":
        cmd_write_version_info(args)
    elif args.subparser == "write_results_section":
        cmd_write_results_section(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
