#!/usr/bin/env python3
import json
import time
import argparse
import os
import datetime
import threading

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


def worker_serialize(message, serialized, ops_count, results_list, thread_id):
    local_count = 0
    start = time.perf_counter()
    for _ in range(ops_count):
        message.SerializeToString()
        local_count += 1
    elapsed = time.perf_counter() - start
    results_list.append({
        "thread_id": thread_id,
        "ops_completed": local_count,
        "elapsed_sec": round(elapsed, 4),
        "ops_per_sec": round(local_count / elapsed, 2) if elapsed > 0 else 0,
    })


def worker_deserialize(serialized, ops_count, results_list, thread_id):
    local_count = 0
    start = time.perf_counter()
    for _ in range(ops_count):
        msg = struct_pb2.Struct()
        msg.ParseFromString(serialized)
        local_count += 1
    elapsed = time.perf_counter() - start
    results_list.append({
        "thread_id": thread_id,
        "ops_completed": local_count,
        "elapsed_sec": round(elapsed, 4),
        "ops_per_sec": round(local_count / elapsed, 2) if elapsed > 0 else 0,
    })


def run_concurrency_benchmark(message, thread_counts, iterations, ops_per_thread):
    serialized = message.SerializeToString()
    msg_size = len(serialized)
    all_results = []

    for thread_count in thread_counts:
        for iteration in range(iterations):
            total_ops = thread_count * ops_per_thread
            results_list = []
            threads = []

            start = time.perf_counter()
            for t in range(thread_count):
                t_obj = threading.Thread(
                    target=worker_serialize,
                    args=(message, serialized, ops_per_thread, results_list, t)
                )
                threads.append(t_obj)
                t_obj.start()

            for t_obj in threads:
                t_obj.join()
            wall_time = time.perf_counter() - start

            total_completed = sum(r["ops_completed"] for r in results_list)
            total_ops_per_sec = round(total_completed / wall_time, 2) if wall_time > 0 else 0

            all_results.append({
                "thread_count": thread_count,
                "iteration": iteration + 1,
                "ops_per_thread": ops_per_thread,
                "total_ops": total_completed,
                "wall_time_sec": round(wall_time, 4),
                "total_ops_per_sec": total_ops_per_sec,
                "avg_latency_ms": round(wall_time * 1000.0 / total_completed, 4) if total_completed > 0 else 0,
                "message_size_bytes": msg_size,
                "mode": "serialize",
            })

    for thread_count in thread_counts:
        for iteration in range(iterations):
            total_ops = thread_count * ops_per_thread
            results_list = []
            threads = []

            start = time.perf_counter()
            for t in range(thread_count):
                t_obj = threading.Thread(
                    target=worker_deserialize,
                    args=(serialized, ops_per_thread, results_list, t)
                )
                threads.append(t_obj)
                t_obj.start()

            for t_obj in threads:
                t_obj.join()
            wall_time = time.perf_counter() - start

            total_completed = sum(r["ops_completed"] for r in results_list)
            total_ops_per_sec = round(total_completed / wall_time, 2) if wall_time > 0 else 0

            all_results.append({
                "thread_count": thread_count,
                "iteration": iteration + 1,
                "ops_per_thread": ops_per_thread,
                "total_ops": total_completed,
                "wall_time_sec": round(wall_time, 4),
                "total_ops_per_sec": total_ops_per_sec,
                "avg_latency_ms": round(wall_time * 1000.0 / total_completed, 4) if total_completed > 0 else 0,
                "message_size_bytes": msg_size,
                "mode": "deserialize",
            })

    return all_results


def main():
    parser = argparse.ArgumentParser(description='Protobuf concurrency scaling benchmark')
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

    thread_counts = [1, 2, 4, 8]

    output = {
        "benchmark": "concurrency_scaling",
        "description": "Protobuf serialization/deserialization throughput scaling with concurrent threads",
        "reference": "https://github.com/protocolbuffers/protobuf/tree/main/benchmarks",
        "software": "protobuf",
        "version": pb_ver,
        "architecture": arch,
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "total_ops_per_sec": {"unit": "ops/sec", "description": "Total throughput across all threads"},
            "avg_latency_ms": {"unit": "ms", "description": "Average latency per operation"},
        },
        "dataset_info": {
            "name": "protobuf_struct_well_known",
            "size": "small (~50 bytes)",
            "source": "google.protobuf.struct_pb2",
        },
        "results": [],
    }

    print("[CONCURRENCY] Running concurrency scaling benchmark...")
    msg = create_small_struct()
    raw_results = run_concurrency_benchmark(msg, thread_counts, args.iterations, args.ops_per_iter)

    for mode in ["serialize", "deserialize"]:
        for tc in thread_counts:
            mode_tc_results = [r for r in raw_results if r["thread_count"] == tc and r["mode"] == mode]
            if not mode_tc_results:
                continue
            avg_ops = sum(r["total_ops_per_sec"] for r in mode_tc_results) / len(mode_tc_results)
            avg_lat = sum(r["avg_latency_ms"] for r in mode_tc_results) / len(mode_tc_results)
            total_ops = sum(r["total_ops"] for r in mode_tc_results)
            avg_wall = sum(r["wall_time_sec"] for r in mode_tc_results) / len(mode_tc_results)

            output["results"].append({
                "thread_count": tc,
                "mode": mode,
                "iterations": args.iterations,
                "ops_per_thread": args.ops_per_iter,
                "total_ops": total_ops,
                "total_ops_per_sec": round(avg_ops, 2),
                "avg_latency_ms": round(avg_lat, 4),
                "wall_time_sec": round(avg_wall, 4),
                "message_size_bytes": mode_tc_results[0].get("message_size_bytes", 0),
            })

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[CONCURRENCY] Results saved to {args.output}")


if __name__ == '__main__':
    main()
