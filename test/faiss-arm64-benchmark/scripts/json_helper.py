#!/usr/bin/env python3

import json
import sys


def safe_int(val):
    try:
        return int(val)
    except ValueError:
        try:
            return int(val, 16)
        except ValueError:
            return 0


def write_version_info(outfile, data_args):
    (timestamp, arch, kernel, os_name, cpu_model,
     cores, mem_mb, sw_version, runtime_lang,
     runtime_ver, faiss_ver, numpy_ver, blas, parallelism) = data_args[:14]
    data = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cpu_cores": safe_int(cores),
        "memory_mb": safe_int(mem_mb),
        "software": {
            "name": "faiss",
            "version": sw_version,
            "runtime_language": runtime_lang,
            "runtime_version": runtime_ver,
            "faiss_version": faiss_ver,
            "numpy_version": numpy_ver,
            "blas_status": blas,
            "install_path": "pip (venv)",
            "arm64_native": True,
            "parallelism_default": safe_int(parallelism)
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
        write_version_info(json_file, sys.argv[3:])
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
        found = False
        if isinstance(data, dict):
            found = field in data
        elif isinstance(data, list):
            found = any(field in item for item in data if isinstance(item, dict))
        print("1" if found else "0")

    elif command == "count_results":
        results = data.get("results", data.get("results_summary", data.get("results_detailed", [])))
        if isinstance(results, dict):
            print(len(results))
        elif isinstance(results, list):
            print(len(results))
        else:
            print("0")

    elif command == "count_raw_results":
        results = data.get("results", data.get("results_detailed", data.get("results_summary", [])))
        if isinstance(results, dict):
            print(len(results))
        elif isinstance(results, list):
            print(len(results))
        else:
            print("0")

    elif command == "success_count":
        results = data.get("results", data.get("results_summary", data.get("results_detailed", [])))
        if isinstance(results, dict):
            success = sum(1 for v in results.values() if isinstance(v, dict) and "error" not in v)
            print(success)
        elif isinstance(results, list):
            success = sum(1 for r in results if isinstance(r, dict) and r.get("status", "ok") != "error")
            print(success)
        else:
            print("0")

    elif command == "throughput_ge":
        threshold = float(sys.argv[3])
        key1 = sys.argv[4] if len(sys.argv) > 4 else "qps"
        key2 = sys.argv[5] if len(sys.argv) > 5 else "ops_per_sec"
        results = data.get("results", data.get("results_summary", []))
        if isinstance(results, dict):
            for v in results.values():
                if isinstance(v, dict):
                    tp = v.get(key1, v.get(key2, 0))
                    if isinstance(tp, (int, float)) and tp >= threshold:
                        print("1")
                        return
            print("0")
        elif isinstance(results, list) and results and isinstance(results[0], dict):
            tp = results[0].get(key1, results[0].get(key2, 0))
            print("1" if isinstance(tp, (int, float)) and tp >= threshold else "0")
        else:
            print("0")

    elif command == "latency_le":
        threshold = float(sys.argv[3])
        key1 = sys.argv[4] if len(sys.argv) > 4 else "latency_per_query_us"
        key2 = sys.argv[5] if len(sys.argv) > 5 else "avg_latency_us"
        results = data.get("results", data.get("results_summary", []))
        if isinstance(results, dict):
            for v in results.values():
                if isinstance(v, dict):
                    lat = v.get(key1, v.get(key2, 99999))
                    if isinstance(lat, (int, float)) and lat <= threshold:
                        print("1")
                        return
            print("0")
        elif isinstance(results, list) and results and isinstance(results[0], dict):
            lat = results[0].get(key1, results[0].get(key2, 99999))
            print("1" if isinstance(lat, (int, float)) and lat <= threshold else "0")
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