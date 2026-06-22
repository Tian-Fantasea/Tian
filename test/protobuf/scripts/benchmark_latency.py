#!/usr/bin/env python3
import json
import time
import argparse
import os
import datetime
import statistics

try:
    from google.protobuf import struct_pb2
except ImportError:
    print("[ERROR] google.protobuf not installed. Install: pip3 install protobuf")
    exit(1)


def create_small_struct():
    msg = struct_pb2.Struct()
    msg.fields["id"].number_value = 42
    msg.fields["name"].string_value = "test_small"
    msg.fields["active"].bool_value = True
    msg.fields["score"].number_value = 95.5
    msg.fields["tag"].string_value = "benchmark"
    return msg


def create_medium_struct():
    msg = struct_pb2.Struct()
    for i in range(20):
        msg.fields[f"field_{i}"].string_value = f"value_{i}_abcdefghij"
    msg.fields["score"].number_value = 95.5
    msg.fields["active"].bool_value = True
    msg.fields["count"].number_value = 100
    return msg


def create_large_struct():
    msg = struct_pb2.Struct()
    for i in range(100):
        msg.fields[f"key_{i}"].string_value = f"long_value_{i}_" + "x" * 50
    msg.fields["score"].number_value = 95.5
    msg.fields["total"].number_value = 1000000
    return msg


def measure_latency(message, operation, ops_per_iter):
    if operation.startswith("serialize"):
        serialized = message.SerializeToString()
        latencies = []
        for _ in range(ops_per_iter):
            start = time.perf_counter()
            message.SerializeToString()
            latencies.append((time.perf_counter() - start) * 1000.0)
        return latencies, len(serialized)
    else:
        serialized = message.SerializeToString()
        latencies = []
        for _ in range(ops_per_iter):
            msg = struct_pb2.Struct()
            start = time.perf_counter()
            msg.ParseFromString(serialized)
            latencies.append((time.perf_counter() - start) * 1000.0)
        return latencies, len(serialized)


def compute_percentiles(data):
    if not data:
        return {}
    sorted_data = sorted(data)
    n = len(sorted_data)
    return {
        "avg_latency_ms": round(statistics.mean(sorted_data), 4),
        "p50_latency_ms": round(sorted_data[n // 2], 4),
        "p90_latency_ms": round(sorted_data[int(n * 0.9)], 4),
        "p99_latency_ms": round(sorted_data[int(n * 0.99)], 4) if n >= 100 else round(sorted_data[-1], 4),
        "min_latency_ms": round(sorted_data[0], 6),
        "max_latency_ms": round(sorted_data[-1], 4),
        "stddev_ms": round(statistics.stdev(sorted_data), 4) if n > 1 else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description='Protobuf latency distribution benchmark')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--ops-per-iter', type=int, default=10000)
    args = parser.parse_args()

    pb_ver = "unknown"
    try:
        import google.protobuf
        pb_ver = google.protobuf.__version__
    except Exception:
        pass

    arch = "unknown"
    try:
        import platform
        arch = platform.machine()
    except Exception:
        pass

    output = {
        "benchmark": "latency_distribution",
        "description": "Per-operation latency distribution for protobuf serialization/deserialization",
        "reference": "https://github.com/protocolbuffers/protobuf/tree/main/benchmarks",
        "software": "protobuf",
        "version": pb_ver,
        "architecture": arch,
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "avg_latency_ms": {"unit": "ms", "description": "Average latency per operation"},
            "p99_latency_ms": {"unit": "ms", "description": "99th percentile latency per operation"},
            "p50_latency_ms": {"unit": "ms", "description": "50th percentile (median) latency per operation"},
        },
        "dataset_info": {
            "name": "protobuf_struct_well_known",
            "size": "variable",
            "source": "google.protobuf.struct_pb2",
        },
        "results": [],
    }

    configs = [
        ("serialize_small", create_small_struct, "serialize"),
        ("serialize_medium", create_medium_struct, "serialize"),
        ("serialize_large", create_large_struct, "serialize"),
        ("deserialize_small", create_small_struct, "deserialize"),
        ("deserialize_medium", create_medium_struct, "deserialize"),
        ("deserialize_large", create_large_struct, "deserialize"),
    ]

    for op_name, create_func, op_type in configs:
        print(f"[LATENCY] Benchmarking {op_name}...")
        msg = create_func()
        all_latencies = []
        msg_size = 0

        for iteration in range(args.iterations):
            latencies, size = measure_latency(msg, op_type, args.ops_per_iter)
            all_latencies.extend(latencies)
            msg_size = size

        stats = compute_percentiles(all_latencies)
        stats["operation"] = op_name
        stats["message_size_bytes"] = msg_size
        stats["total_ops"] = len(all_latencies)
        stats["iterations"] = args.iterations
        output["results"].append(stats)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[LATENCY] Results saved to {args.output}")


if __name__ == '__main__':
    main()
