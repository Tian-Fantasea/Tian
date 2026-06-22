#!/usr/bin/env python3
import json
import time
import argparse
import os
import datetime

try:
    from google.protobuf import struct_pb2
    from google.protobuf import wrappers_pb2
    from google.protobuf import timestamp_pb2
except ImportError:
    print("[ERROR] google.protobuf not installed. Install: pip3 install protobuf")
    exit(1)


def create_small_struct():
    msg = struct_pb2.Struct()
    msg.fields["id"].number_value = 42
    msg.fields["name"].string_value = "test_small_msg"
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
    msg.fields["ratio"].number_value = 0.85
    msg.fields["label"].string_value = "medium_benchmark_message"
    return msg


def create_large_struct():
    msg = struct_pb2.Struct()
    for i in range(100):
        msg.fields[f"key_{i}"].string_value = f"long_value_{i}_" + "x" * 50
    msg.fields["score"].number_value = 95.5
    msg.fields["total"].number_value = 1000000
    msg.fields["ratio"].number_value = 0.95
    msg.fields["description"].string_value = "This is a large benchmark message for protobuf serialization testing on ARM64"
    list_val = struct_pb2.ListValue()
    for j in range(50):
        list_val.values.add().string_value = f"item_{j}"
    msg.fields["items"].list_value.CopyFrom(list_val)
    return msg


def benchmark_throughput(message, iterations, ops_per_iter):
    serialized = message.SerializeToString()
    msg_size = len(serialized)
    results = []

    for i in range(iterations):
        start = time.perf_counter()
        for _ in range(ops_per_iter):
            message.SerializeToString()
        elapsed = time.perf_counter() - start
        serialize_ops = ops_per_iter / elapsed
        serialize_bytes = serialize_ops * msg_size

        start = time.perf_counter()
        for _ in range(ops_per_iter):
            msg = struct_pb2.Struct()
            msg.ParseFromString(serialized)
        elapsed_d = time.perf_counter() - start
        deserialize_ops = ops_per_iter / elapsed_d

        results.append({
            "iteration": i + 1,
            "message_size_bytes": msg_size,
            "serialize_ops_per_sec": round(serialize_ops, 2),
            "serialize_bytes_per_sec": round(serialize_bytes, 2),
            "deserialize_ops_per_sec": round(deserialize_ops, 2),
            "serialize_avg_latency_ms": round(1000.0 / serialize_ops, 4),
            "deserialize_avg_latency_ms": round(1000.0 / deserialize_ops, 4),
            "elapsed_sec": round(elapsed, 4),
        })

    return results, msg_size


def main():
    parser = argparse.ArgumentParser(description='Protobuf serialization throughput benchmark')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--ops-per-iter', type=int, default=1000)
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
        "benchmark": "serialization_throughput",
        "description": "Protobuf serialization/deserialization throughput across message sizes (Struct well-known type)",
        "reference": "https://github.com/protocolbuffers/protobuf/tree/main/benchmarks",
        "software": "protobuf",
        "version": pb_ver,
        "architecture": arch,
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "serialize_ops_per_sec": {"unit": "msgs/sec", "description": "Serialization throughput in messages per second"},
            "serialize_bytes_per_sec": {"unit": "bytes/sec", "description": "Serialization throughput in bytes per second"},
            "deserialize_ops_per_sec": {"unit": "msgs/sec", "description": "Deserialization throughput in messages per second"},
        },
        "dataset_info": {
            "name": "protobuf_struct_well_known",
            "size": "variable (small ~50B, medium ~1KB, large ~10KB)",
            "source": "google.protobuf.struct_pb2",
        },
        "results": [],
    }

    message_configs = [
        ("small_struct", create_small_struct),
        ("medium_struct", create_medium_struct),
        ("large_struct", create_large_struct),
    ]

    for msg_type, create_func in message_configs:
        print(f"[SERIALIZE] Benchmarking {msg_type}...")
        msg = create_func()
        iter_results, msg_size = benchmark_throughput(msg, args.iterations, args.ops_per_iter)

        avg_serialize = sum(r["serialize_ops_per_sec"] for r in iter_results) / len(iter_results)
        avg_deserialize = sum(r["deserialize_ops_per_sec"] for r in iter_results) / len(iter_results)
        avg_bytes = sum(r["serialize_bytes_per_sec"] for r in iter_results) / len(iter_results)

        output["results"].append({
            "message_type": msg_type,
            "message_size_bytes": msg_size,
            "iterations": args.iterations,
            "ops_per_iter": args.ops_per_iter,
            "serialize_ops_per_sec": round(avg_serialize, 2),
            "serialize_bytes_per_sec": round(avg_bytes, 2),
            "deserialize_ops_per_sec": round(avg_deserialize, 2),
            "serialize_avg_latency_ms": round(1000.0 / avg_serialize, 4) if avg_serialize > 0 else 0,
            "deserialize_avg_latency_ms": round(1000.0 / avg_deserialize, 4) if avg_deserialize > 0 else 0,
            "iteration_details": iter_results,
        })

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[SERIALIZE] Results saved to {args.output}")


if __name__ == '__main__':
    main()
