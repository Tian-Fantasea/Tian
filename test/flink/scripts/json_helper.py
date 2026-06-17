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
    return data


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


def cmd_qps_avg(args):
    values = []
    with open(args.file) as f:
        data = json.load(f)
    if "results" in data and isinstance(data["results"], list):
        for item in data["results"]:
            if isinstance(item, dict) and "qps" in item:
                try:
                    values.append(float(item["qps"]))
                except (ValueError, TypeError):
                    pass
    if values:
        avg = sum(values) / len(values)
        print(int(avg))
    else:
        key_path = args.keys if hasattr(args, "keys") else []
        if key_path:
            results = navigate(data, key_path)
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        for k in ["qps", "throughput", "throughput_ops_per_sec", "throughput_events_per_sec"]:
                            if k in item:
                                try:
                                    values.append(float(item[k]))
                                except (ValueError, TypeError):
                                    pass
            if values:
                avg = sum(values) / len(values)
                print(int(avg))
            else:
                print(0)
        else:
            print(0)


def cmd_write_version_info(args):
    d = {
        "timestamp": args.values[0],
        "architecture": args.values[1],
        "kernel": args.values[2],
        "os": args.values[3],
        "cpu_model": args.values[4],
        "cores": int(args.values[5]) if args.values[5] != "unknown" else 0,
        "memory_mb": int(args.values[6]) if args.values[6] != "unknown" else 0,
        "software": args.values[7],
        "version": args.values[8],
        "java_version": args.values[9],
        "flink_home": args.values[10],
        "flink_found": int(args.values[11]) if args.values[11] else 0,
        "parallelism": int(args.values[12]) if args.values[12] else 4,
    }
    results = load_or_create_json(args.file)
    results["software"] = d["software"]
    results["version"] = d["version"]
    results["architecture"] = d["architecture"]
    results["timestamp"] = d["timestamp"]
    results["version_info"] = d
    with open(args.file, "w") as f:
        json.dump(results, f, indent=2)


def cmd_json_summary(args):
    with open(args.file) as f:
        data = json.load(f)
    summary = {}
    if "results" in data and isinstance(data["results"], list):
        for item in data["results"]:
            if isinstance(item, dict):
                for k, v in item.items():
                    if isinstance(v, (int, float)):
                        if k not in summary:
                            summary[k] = []
                        summary[k].append(v)
    for k, v in summary.items():
        avg = sum(v) / len(v) if v else 0
        summary[k] = {"avg": avg, "min": min(v), "max": max(v), "count": len(v)}
    json.dump(summary, open(args.output, "w"), indent=2)


def main():
    parser = argparse.ArgumentParser(description="JSON helper for shUnit2 assertions")
    parser.add_argument("file", help="JSON file to operate on")
    subparsers = parser.add_subparsers(dest="subparser", help="Commands", required=True)

    sp_get = subparsers.add_parser("get", help="Get value by key path")
    sp_get.add_argument("keys", nargs="+", help="Key path (e.g., results 0 tpmC)")

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
    sp_avg.add_argument("keys", nargs="+", help="Key path to throughput values")

    sp_max = subparsers.add_parser("max_latency", help="Max latency across results")
    sp_max.add_argument("keys", nargs="+", help="Key path to latency values")

    sp_version = subparsers.add_parser("version", help="Get software version")

    sp_contains = subparsers.add_parser("contains", help="Check if JSON contains keyword")
    sp_contains.add_argument("keyword", help="Keyword to search")

    sp_qps_avg = subparsers.add_parser("qps_avg", help="Average QPS across results")
    sp_qps_avg.add_argument("keys", nargs="*", help="Key path to QPS values")

    sp_write_vi = subparsers.add_parser("write_version_info", help="Write version info into results.json section")
    sp_write_vi.add_argument("values", nargs=13, help="Values: timestamp arch kernel os cpu core memory software ver java_ver flink_home flink_found parallelism")

    sp_json_summary = subparsers.add_parser("json_summary", help="Generate JSON summary")
    sp_json_summary.add_argument("--output", required=True, help="Output file")

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
    elif args.subparser == "qps_avg":
        cmd_qps_avg(args)
    elif args.subparser == "write_version_info":
        cmd_write_version_info(args)
    elif args.subparser == "json_summary":
        cmd_json_summary(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()