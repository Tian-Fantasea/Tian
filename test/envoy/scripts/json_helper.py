#!/usr/bin/env python3
import json
import sys
import os


def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def navigate(data, keys):
    for key in keys:
        if isinstance(data, dict):
            if key in data:
                data = data[key]
            else:
                return None
        elif isinstance(data, list):
            try:
                idx = int(key)
                if 0 <= idx < len(data):
                    data = data[idx]
                else:
                    return None
            except ValueError:
                return None
        else:
            return None
    return data


def cmd_get(data, keys):
    val = navigate(data, keys)
    if val is None:
        print("NULL")
    elif isinstance(val, (dict, list)):
        print(json.dumps(val))
    else:
        print(val)


def cmd_field_exists(data, keys):
    keys_list = keys if isinstance(keys, list) else [keys]
    val = navigate(data, keys_list)
    print(1 if val is not None else 0)


def cmd_count_results(data):
    results = data.get("results", None)
    if results is None:
        for key in ["results_summary", "results_detailed", "performance_metrics"]:
            if key in data:
                val = data[key]
                if isinstance(val, dict):
                    print(len(val))
                    return
                elif isinstance(val, list):
                    print(len(val))
                    return
        print(0)
        return
    if isinstance(results, list):
        print(len(results))
    elif isinstance(results, dict):
        print(len(results))
    else:
        print(0)


def cmd_throughput_ge(data, threshold, keys):
    keys_list = keys if isinstance(keys, list) else keys.split()
    val = navigate(data, keys_list)
    if val is None:
        print(0)
        return
    try:
        numeric_val = float(val)
        print(1 if numeric_val >= float(threshold) else 0)
    except (ValueError, TypeError):
        if isinstance(val, dict):
            for v in val.values():
                try:
                    if float(v) >= float(threshold):
                        print(1)
                        return
                except (ValueError, TypeError):
                    continue
            print(0)
        else:
            print(0)


def cmd_latency_le(data, threshold, keys):
    keys_list = keys if isinstance(keys, list) else keys.split()
    val = navigate(data, keys_list)
    if val is None:
        print(0)
        return
    try:
        numeric_val = float(val)
        print(1 if numeric_val <= float(threshold) else 0)
    except (ValueError, TypeError):
        if isinstance(val, dict):
            for v in val.values():
                try:
                    if float(v) <= float(threshold):
                        print(1)
                        return
                except (ValueError, TypeError):
                    continue
            print(0)
        else:
            print(0)


def cmd_avg_throughput(data, keys):
    keys_list = keys if isinstance(keys, list) else keys.split()
    val = navigate(data, keys_list)
    if val is None:
        print("NULL")
        return
    if isinstance(val, (dict, list)):
        nums = []
        items = val.values() if isinstance(val, dict) else val
        for v in items:
            try:
                nums.append(float(v))
            except (ValueError, TypeError):
                if isinstance(v, dict):
                    for vv in v.values():
                        try:
                            nums.append(float(vv))
                        except (ValueError, TypeError):
                            continue
        if nums:
            print(round(sum(nums) / len(nums), 2))
        else:
            print("NULL")
    else:
        try:
            print(float(val))
        except (ValueError, TypeError):
            print("NULL")


def cmd_max_latency(data, keys):
    keys_list = keys if isinstance(keys, list) else keys.split()
    val = navigate(data, keys_list)
    if val is None:
        print("NULL")
        return
    if isinstance(val, (dict, list)):
        nums = []
        items = val.values() if isinstance(val, dict) else val
        for v in items:
            try:
                nums.append(float(v))
            except (ValueError, TypeError):
                if isinstance(v, dict):
                    for vv in v.values():
                        try:
                            nums.append(float(vv))
                        except (ValueError, TypeError):
                            continue
        if nums:
            print(round(max(nums), 2))
        else:
            print("NULL")
    else:
        try:
            print(float(val))
        except (ValueError, TypeError):
            print("NULL")


def cmd_version(data):
    ver = data.get("software_version", data.get("version", "unknown"))
    print(ver)


def cmd_contains(data, keyword):
    json_str = json.dumps(data)
    print(1 if keyword in json_str else 0)


def cmd_write_version_info(data, args):
    timestamp = args[0] if len(args) > 0 else ""
    architecture = args[1] if len(args) > 1 else ""
    kernel = args[2] if len(args) > 2 else ""
    os_name = args[3] if len(args) > 3 else ""
    cpu_model = args[4] if len(args) > 4 else ""
    cpu_cores = args[5] if len(args) > 5 else "4"
    memory_mb = args[6] if len(args) > 6 else "0"
    software_name = args[7] if len(args) > 7 else ""
    software_version = args[8] if len(args) > 8 else ""
    envoy_version = args[9] if len(args) > 9 else ""
    python_version = args[10] if len(args) > 10 else ""
    wrk_version = args[11] if len(args) > 11 else "not available"
    envoy_binary = args[12] if len(args) > 12 else "/usr/local/bin/envoy"
    worker_threads = args[13] if len(args) > 13 else "4"

    version_info = {
        "timestamp": timestamp,
        "architecture": architecture,
        "kernel": kernel,
        "os": os_name,
        "cpu_model": cpu_model,
        "cpu_cores": int(cpu_cores) if cpu_cores.isdigit() else cpu_cores,
        "total_memory_mb": int(memory_mb) if memory_mb.isdigit() else memory_mb,
        "software_name": software_name,
        "software_version": software_version,
        "envoy_version": envoy_version,
        "python_version": python_version,
        "wrk_version": wrk_version,
        "envoy_binary": envoy_binary,
        "worker_threads": int(worker_threads) if worker_threads.isdigit() else worker_threads,
    }
    save_json(filepath, version_info)


def cmd_write_envoy_http_config(data, args):
    port = args[0] if len(args) > 0 else "10000"
    admin_port = args[1] if len(args) > 1 else "9901"
    backend_port = args[2] if len(args) > 2 else "8080"
    backend_host = args[3] if len(args) > 3 else "127.0.0.1"
    config = f"""static_resources:
  listeners:
  - name: listener_http
    address:
      socket_address:
        address: 0.0.0.0
        port_value: {port}
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          '@type': type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          codec_type: AUTO
          route_config:
            name: local_route
            virtual_hosts:
            - name: backend
              domains: ["*"]
              routes:
              - match:
                  prefix: "/"
                route:
                  cluster: backend_cluster
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              '@type': type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
  clusters:
  - name: backend_cluster
    connect_timeout: 0.25s
    type: STATIC
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: backend_cluster
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: {backend_host}
                port_value: {backend_port}
admin:
  address:
    socket_address:
      address: 0.0.0.0
      port_value: {admin_port}
"""
    with open(filepath, 'w') as f:
        f.write(config)


filepath = ""
data = None

if len(sys.argv) >= 2:
    filepath = sys.argv[1]
    if os.path.exists(filepath):
        try:
            data = load_json(filepath)
        except (json.JSONDecodeError, IOError):
            data = {}
    else:
        data = {}

if len(sys.argv) < 3:
    print("Usage: json_helper.py <file> <command> [args...]")
    sys.exit(1)

command = sys.argv[2]
args = sys.argv[3:]

if command == "get":
    cmd_get(data, args)
elif command == "field_exists":
    cmd_field_exists(data, args)
elif command == "count_results":
    cmd_count_results(data)
elif command == "throughput_ge":
    threshold = args[0]
    keys = args[1:]
    cmd_throughput_ge(data, threshold, keys)
elif command == "latency_le":
    threshold = args[0]
    keys = args[1:]
    cmd_latency_le(data, threshold, keys)
elif command == "avg_throughput":
    cmd_avg_throughput(data, args)
elif command == "max_latency":
    cmd_max_latency(data, args)
elif command == "version":
    cmd_version(data)
elif command == "contains":
    keyword = args[0]
    cmd_contains(data, keyword)
elif command == "write_version_info":
    cmd_write_version_info(data, args)
elif command == "write_envoy_http_config":
    cmd_write_envoy_http_config(data, args)
else:
    print(f"Unknown command: {command}")
    sys.exit(1)
