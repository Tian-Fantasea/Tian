#!/usr/bin/env python3
import json
import sys
import os


def _navigate(data, keys):
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list):
            try:
                idx = int(key)
                data = data[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return data


def cmd_get(filepath, keys):
    with open(filepath, 'r') as f:
        data = json.load(f)
    val = _navigate(data, keys)
    if val is None:
        print("0")
        return
    if isinstance(val, bool):
        print("1" if val else "0")
    elif isinstance(val, (int, float)):
        print(val)
    else:
        print(val)


def cmd_field_exists(filepath, field):
    with open(filepath, 'r') as f:
        data = json.load(f)
    if isinstance(data, dict) and field in data:
        print("1")
    elif isinstance(data, list):
        try:
            int(field)
            print("1")
        except ValueError:
            print("0")
    else:
        print("0")


def cmd_count_results(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    results = data.get("results", [])
    if isinstance(results, list):
        print(len(results))
    else:
        print("0")


def _collect_numeric(data, keys):
    vals = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                nested = item
                for k in keys[:-1]:
                    if isinstance(nested, dict) and k in nested:
                        nested = nested[k]
                    elif isinstance(nested, list):
                        try:
                            nested = nested[int(k)]
                        except (ValueError, IndexError):
                            nested = None
                    else:
                        nested = None
                if isinstance(nested, dict) and keys[-1] in nested:
                    v = nested[keys[-1]]
                    if isinstance(v, (int, float)):
                        vals.append(v)
                elif isinstance(nested, list):
                    for sub in nested:
                        if isinstance(sub, dict) and keys[-1] in sub:
                            v = sub[keys[-1]]
                            if isinstance(v, (int, float)):
                                vals.append(v)
    elif isinstance(data, dict):
        for result_key in data:
            result_val = data[result_key]
            if isinstance(result_val, list):
                for item in result_val:
                    if isinstance(item, dict):
                        nested = item
                        if isinstance(nested, dict) and "data" in nested:
                            data_arr = nested["data"]
                            if isinstance(data_arr, list):
                                for d in data_arr:
                                    if isinstance(d, dict) and keys[-1] in d:
                                        v = d[keys[-1]]
                                        if isinstance(v, (int, float)):
                                            vals.append(v)
    return vals


def cmd_throughput_ge(filepath, threshold, keys):
    with open(filepath, 'r') as f:
        data = json.load(f)
    key_list = keys if isinstance(keys, list) else keys.split()
    vals = _collect_numeric(data, key_list)
    if not vals:
        avg = 0.0
    else:
        avg = sum(vals) / len(vals)
    if avg >= float(threshold):
        print("1")
    else:
        print("0")


def cmd_latency_le(filepath, threshold, keys):
    with open(filepath, 'r') as f:
        data = json.load(f)
    key_list = keys if isinstance(keys, list) else keys.split()
    vals = _collect_numeric(data, key_list)
    if not vals:
        max_val = 0.0
    else:
        max_val = max(vals)
    if max_val <= float(threshold):
        print("1")
    else:
        print("0")


def cmd_avg_throughput(filepath, keys):
    with open(filepath, 'r') as f:
        data = json.load(f)
    key_list = keys if isinstance(keys, list) else keys.split()
    vals = _collect_numeric(data, key_list)
    if not vals:
        print("0")
    else:
        avg = sum(vals) / len(vals)
        print(f"{avg:.2f}")


def cmd_max_latency(filepath, keys):
    with open(filepath, 'r') as f:
        data = json.load(f)
    key_list = keys if isinstance(keys, list) else keys.split()
    vals = _collect_numeric(data, key_list)
    if not vals:
        print("0")
    else:
        print(f"{max(vals):.2f}")


def cmd_version(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    ver = data.get("version", "unknown")
    print(ver)


def cmd_contains(filepath, keyword):
    with open(filepath, 'r') as f:
        content = f.read()
    if keyword in content:
        print("1")
    else:
        print("0")


def cmd_write_version_info(filepath, timestamp, arch, kernel, os_name,
                           cpu_model, cores, mem_mb, software_name,
                           software_version, runtime_version, home_dir,
                           runtime_detail, parallelism, **kwargs):
    data = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cpu_cores": int(cores) if cores.isdigit() else cores,
        "total_memory_mb": int(mem_mb) if str(mem_mb).isdigit() else mem_mb,
        "software": software_name,
        "version": software_version,
        "runtime_version": runtime_version,
        "home": home_dir,
        "runtime_detail": runtime_detail,
        "parallelism": int(parallelism) if str(parallelism).isdigit() else parallelism,
    }

    extra_pairs = kwargs.get("extra", [])
    if extra_pairs:
        extra_dict = {}
        for pair in extra_pairs:
            if ":" in pair:
                k, v = pair.split(":", 1)
                extra_dict[k] = v
        data["extra_info"] = extra_dict

    output = kwargs.get("output", filepath)
    os.makedirs(os.path.dirname(output) or '.', exist_ok=True)
    with open(output, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"[VERSION_INFO] Written to {output}")


def main():
    if len(sys.argv) < 3:
        print("Usage: json_helper.py <file> <command> [args...]")
        sys.exit(1)

    filepath = sys.argv[1]
    command = sys.argv[2]

    if command == "get":
        keys = sys.argv[3:]
        cmd_get(filepath, keys)
    elif command == "field_exists":
        cmd_field_exists(filepath, sys.argv[3])
    elif command == "count_results":
        cmd_count_results(filepath)
    elif command == "throughput_ge":
        threshold = sys.argv[3]
        keys = sys.argv[4:]
        cmd_throughput_ge(filepath, threshold, keys)
    elif command == "latency_le":
        threshold = sys.argv[3]
        keys = sys.argv[4:]
        cmd_latency_le(filepath, threshold, keys)
    elif command == "avg_throughput":
        keys = sys.argv[3:]
        cmd_avg_throughput(filepath, keys)
    elif command == "max_latency":
        keys = sys.argv[3:]
        cmd_max_latency(filepath, keys)
    elif command == "version":
        cmd_version(filepath)
    elif command == "contains":
        cmd_contains(filepath, sys.argv[3])
    elif command == "write_version_info":
        args = sys.argv[3:]
        i = 0
        positional = []
        kwargs = {}
        while i < len(args):
            if args[i] == "--output":
                kwargs["output"] = args[i + 1]
                i += 2
            elif args[i] == "--extra":
                kwargs.setdefault("extra", []).append(args[i + 1])
                i += 2
            else:
                positional.append(args[i])
                i += 1
        cmd_write_version_info(filepath, *positional, **kwargs)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
