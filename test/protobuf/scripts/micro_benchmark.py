#!/usr/bin/env python3
import json
import time
import argparse
import os
import datetime

try:
    from google.protobuf import wrappers_pb2
    from google.protobuf import struct_pb2
    from google.protobuf import timestamp_pb2
except ImportError:
    print("[ERROR] google.protobuf not installed. Install: pip3 install protobuf")
    exit(1)


def benchmark_wrapper(msg, iterations, ops_per_iter):
    serialized = msg.SerializeToString()
    msg_size = len(serialized)

    serialize_results = []
    deserialize_results = []

    for i in range(iterations):
        start = time.perf_counter()
        for _ in range(ops_per_iter):
            msg.SerializeToString()
        elapsed = time.perf_counter() - start
        serialize_results.append(ops_per_iter / elapsed)

        start = time.perf_counter()
        for _ in range(ops_per_iter):
            new_msg = type(msg)()
            new_msg.ParseFromString(serialized)
        elapsed = time.perf_counter() - start
        deserialize_results.append(ops_per_iter / elapsed)

    avg_serialize = sum(serialize_results) / len(serialize_results)
    avg_deserialize = sum(deserialize_results) / len(deserialize_results)

    return {
        "serialize_ops_per_sec": round(avg_serialize, 2),
        "deserialize_ops_per_sec": round(avg_deserialize, 2),
        "message_size_bytes": msg_size,
        "serialize_avg_latency_ms": round(1000.0 / avg_serialize, 4) if avg_serialize > 0 else 0,
        "deserialize_avg_latency_ms": round(1000.0 / avg_deserialize, 4) if avg_deserialize > 0 else 0,
    }


def benchmark_list_value(iterations, ops_per_iter):
    msg = struct_pb2.ListValue()
    for i in range(100):
        msg.values.add().string_value = f"item_{i}_abcdefghij"
    return benchmark_wrapper(msg, iterations, ops_per_iter)


def benchmark_nested_struct(iterations, ops_per_iter):
    msg = struct_pb2.Struct()
    for i in range(5):
        inner = struct_pb2.Struct()
        inner.fields["sub_id"].number_value = i
        inner.fields["sub_name"].string_value = f"inner_{i}"
        msg.fields[f"nested_{i}"].struct_value.CopyFrom(inner)
    msg.fields["count"].number_value = 5
    msg.fields["label"].string_value = "nested_benchmark"
    return benchmark_wrapper(msg, iterations, ops_per_iter)


def benchmark_timestamp(iterations, ops_per_iter):
    msg = timestamp_pb2.Timestamp()
    msg.seconds = 1700000000
    msg.nanos = 500000000
    serialized = msg.SerializeToString()
    msg_size = len(serialized)

    serialize_results = []
    deserialize_results = []

    for i in range(iterations):
        start = time.perf_counter()
        for _ in range(ops_per_iter):
            msg.SerializeToString()
        elapsed = time.perf_counter() - start
        serialize_results.append(ops_per_iter / elapsed)

        start = time.perf_counter()
        for _ in range(ops_per_iter):
            new_msg = timestamp_pb2.Timestamp()
            new_msg.ParseFromString(serialized)
        elapsed = time.perf_counter() - start
        deserialize_results.append(ops_per_iter / elapsed)

    avg_serialize = sum(serialize_results) / len(serialize_results)
    avg_deserialize = sum(deserialize_results) / len(deserialize_results)

    return {
        "serialize_ops_per_sec": round(avg_serialize, 2),
        "deserialize_ops_per_sec": round(avg_deserialize, 2),
        "message_size_bytes": msg_size,
        "serialize_avg_latency_ms": round(1000.0 / avg_serialize, 4) if avg_serialize > 0 else 0,
        "deserialize_avg_latency_ms": round(1000.0 / avg_deserialize, 4) if avg_deserialize > 0 else 0,
    }


def main():
    parser = argparse.ArgumentParser(description='Protobuf micro benchmark per field type')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--ops-per-iter', type=int, default=5000)
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
        "benchmark": "micro_operations",
        "description": "Per-field-type serialization/deserialization micro benchmark using well-known wrapper types",
        "reference": "https://github.com/protocolbuffers/protobuf/tree/main/benchmarks",
        "software": "protobuf",
        "version": pb_ver,
        "architecture": arch,
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "serialize_ops_per_sec": {"unit": "ops/sec", "description": "Serialize throughput per field type"},
            "deserialize_ops_per_sec": {"unit": "ops/sec", "description": "Deserialize throughput per field type"},
        },
        "dataset_info": {
            "name": "protobuf_wrapper_well_known",
            "size": "single-field messages",
            "source": "google.protobuf.wrappers_pb2, struct_pb2, timestamp_pb2",
        },
        "results": [],
    }

    field_configs = [
        ("int32", lambda: wrappers_pb2.Int32Value(value=42)),
        ("int64", lambda: wrappers_pb2.Int64Value(value=1234567890)),
        ("float", lambda: wrappers_pb2.FloatValue(value=3.14)),
        ("double", lambda: wrappers_pb2.DoubleValue(value=3.141592653589793)),
        ("string", lambda: wrappers_pb2.StringValue(value="benchmark_test_string_abcdefghij")),
        ("bytes", lambda: wrappers_pb2.BytesValue(value=b"benchmark_bytes_data_\x00\x01\x02\x03")),
        ("bool", lambda: wrappers_pb2.BoolValue(value=True)),
        ("uint32", lambda: wrappers_pb2.UInt32Value(value=100)),
        ("uint64", lambda: wrappers_pb2.UInt64Value(value=999999999)),
    ]

    for field_type, create_func in field_configs:
        print(f"[MICRO] Benchmarking {field_type}...")
        msg = create_func()
        result = benchmark_wrapper(msg, args.iterations, args.ops_per_iter)
        result["operation"] = f"{field_type}_serialize_deserialize"
        result["field_type"] = field_type
        output["results"].append(result)

    print("[MICRO] Benchmarking list_value (repeated)...")
    result = benchmark_list_value(args.iterations, args.ops_per_iter)
    result["operation"] = "list_value_serialize_deserialize"
    result["field_type"] = "repeated_string"
    output["results"].append(result)

    print("[MICRO] Benchmarking nested_struct (embedded)...")
    result = benchmark_nested_struct(args.iterations, args.ops_per_iter)
    result["operation"] = "nested_struct_serialize_deserialize"
    result["field_type"] = "embedded_struct"
    output["results"].append(result)

    print("[MICRO] Benchmarking timestamp (complex)...")
    result = benchmark_timestamp(args.iterations, args.ops_per_iter)
    result["operation"] = "timestamp_serialize_deserialize"
    result["field_type"] = "timestamp_complex"
    output["results"].append(result)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[MICRO] Results saved to {args.output}")


if __name__ == '__main__':
    main()
