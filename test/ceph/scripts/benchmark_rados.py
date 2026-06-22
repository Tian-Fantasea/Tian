#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import statistics


def run_cmd(cmd, timeout=300):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}


def write_results_section(filepath, section, data):
    results = load_or_create_json(filepath)
    results[section] = data
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)


def parse_rados_bench_output(output):
    result = {}
    lines = output.strip().split("\n")
    for line in lines:
        if "sec" in line and "ops" in line and "bytes" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "ops/sec":
                    try:
                        result["throughput_ops_sec"] = float(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                if p.startswith("MB/sec") or p == "bandwidth":
                    try:
                        bw_val = parts[i - 1]
                        result["bandwidth_mb_sec"] = float(bw_val)
                    except (ValueError, IndexError):
                        pass
                if "lat" in p.lower() or "avg" in p.lower():
                    try:
                        result["avg_latency_ms"] = float(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
        if "Total" in line or "total" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "ops/sec":
                    try:
                        result["total_throughput_ops_sec"] = float(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                if "avg" in p.lower() and "lat" in p.lower():
                    try:
                        result["total_avg_latency_ms"] = float(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
    result.setdefault("raw_output", output)
    return result


def run_rados_bench(ceph_conf, ceph_keyring, pool, op_type, obj_size, concurrency, duration):
    cmd = (
        f"rados -c {ceph_conf} --keyring {ceph_keyring} "
        f"bench {duration} {op_type} "
        f"-b {obj_size} -t {concurrency} -p {pool} "
        f"--no-cleanup 2>/dev/null"
    )
    out, err, rc = run_cmd(cmd, timeout=duration + 60)
    if rc != 0:
        return {"error": err or "rados bench failed", "returncode": rc}
    return parse_rados_bench_output(out)


def run_rados_bench_seq(ceph_conf, ceph_keyring, pool, obj_size, concurrency, duration):
    return run_rados_bench(ceph_conf, ceph_keyring, pool, "seq", obj_size, concurrency, duration)


def run_rados_bench_rand(ceph_conf, ceph_keyring, pool, obj_size, concurrency, duration):
    cmd = (
        f"rados -c {ceph_conf} --keyring {ceph_keyring} "
        f"bench {duration} rand "
        f"-b {obj_size} -t {concurrency} -p {pool} "
        f"--no-cleanup 2>/dev/null"
    )
    out, err, rc = run_cmd(cmd, timeout=duration + 60)
    if rc != 0:
        return {"error": err or "rados rand bench failed", "returncode": rc}
    return parse_rados_bench_output(out)


def main():
    parser = argparse.ArgumentParser(description="RADOS Object Storage Benchmarks")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--results-json", required=True)
    parser.add_argument("--section", default="rados_benchmark")
    parser.add_argument("--ceph-conf", default="/etc/ceph/ceph.conf")
    parser.add_argument("--ceph-keyring", default="/etc/ceph/ceph.client.admin.keyring")
    parser.add_argument("--cluster-name", default="ceph")
    parser.add_argument("--pool", default="bench_rados")
    parser.add_argument("--object-sizes", default="4K,16K,64K,256K,1M,4M,16M,64M")
    parser.add_argument("--concurrency", default="1,4,16,32,64,128")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    obj_sizes = [s.strip() for s in args.object_sizes.split(",")]
    conc_levels = [int(c.strip()) for c in args.concurrency.split(",")]

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    results = {
        "object_size_sweep": [],
        "concurrency_scaling": [],
        "sequential_read": [],
        "random_read": [],
        "mixed_workloads": []
    }

    print("[RADOS] Phase 3a: RADOS Object Storage Benchmarks")

    print("[RADOS] 1. Write throughput by object size (concurrency=16)")
    for obj_size in obj_sizes:
        iter_results = []
        for it in range(args.iterations):
            print(f"[RADOS]   Write obj_size={obj_size}, iteration={it+1}/{args.iterations}")
            r = run_rados_bench(args.ceph_conf, args.ceph_keyring, args.pool, "write", obj_size, 16, args.duration)
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            avg_ops = statistics.mean([r.get("throughput_ops_sec", 0) or r.get("total_throughput_ops_sec", 0) for r in iter_results])
            avg_bw = statistics.mean([r.get("bandwidth_mb_sec", 0) or 0 for r in iter_results])
            avg_lat = statistics.mean([r.get("avg_latency_ms", 0) or r.get("total_avg_latency_ms", 0) for r in iter_results])
            results["object_size_sweep"].append({
                "object_size": obj_size,
                "op_type": "write",
                "concurrency": 16,
                "iterations": len(iter_results),
                "avg_throughput_ops_sec": avg_ops,
                "avg_bandwidth_mb_sec": avg_bw,
                "avg_latency_ms": avg_lat,
                "min_throughput_ops_sec": min([r.get("throughput_ops_sec", 0) or r.get("total_throughput_ops_sec", 0) for r in iter_results]),
                "max_throughput_ops_sec": max([r.get("throughput_ops_sec", 0) or r.get("total_throughput_ops_sec", 0) for r in iter_results])
            })
            print(f"[RADOS]     avg_ops={avg_ops:.1f} ops/sec, bw={avg_bw:.2f} MB/s, lat={avg_lat:.2f} ms")

    print("[RADOS] 2. Concurrency scaling (obj_size=4M, write)")
    for conc in conc_levels:
        iter_results = []
        for it in range(args.iterations):
            print(f"[RADOS]   Write concurrency={conc}, iteration={it+1}/{args.iterations}")
            r = run_rados_bench(args.ceph_conf, args.ceph_keyring, args.pool, "write", "4M", conc, args.duration)
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            avg_ops = statistics.mean([r.get("throughput_ops_sec", 0) or r.get("total_throughput_ops_sec", 0) for r in iter_results])
            avg_bw = statistics.mean([r.get("bandwidth_mb_sec", 0) or 0 for r in iter_results])
            avg_lat = statistics.mean([r.get("avg_latency_ms", 0) or r.get("total_avg_latency_ms", 0) for r in iter_results])
            results["concurrency_scaling"].append({
                "object_size": "4M",
                "op_type": "write",
                "concurrency": conc,
                "iterations": len(iter_results),
                "avg_throughput_ops_sec": avg_ops,
                "avg_bandwidth_mb_sec": avg_bw,
                "avg_latency_ms": avg_lat
            })
            print(f"[RADOS]     conc={conc}: avg_ops={avg_ops:.1f}, bw={avg_bw:.2f} MB/s, lat={avg_lat:.2f} ms")

    print("[RADOS] 3. Sequential read (obj_size=4M, concurrency=16)")
    iter_results = []
    for it in range(args.iterations):
        print(f"[RADOS]   Seq read iteration={it+1}/{args.iterations}")
        r = run_rados_bench_seq(args.ceph_conf, args.ceph_keyring, args.pool, "4M", 16, args.duration)
        if "error" not in r:
            iter_results.append(r)
    if iter_results:
        avg_ops = statistics.mean([r.get("throughput_ops_sec", 0) or r.get("total_throughput_ops_sec", 0) for r in iter_results])
        avg_bw = statistics.mean([r.get("bandwidth_mb_sec", 0) or 0 for r in iter_results])
        results["sequential_read"].append({
            "object_size": "4M",
            "concurrency": 16,
            "iterations": len(iter_results),
            "avg_throughput_ops_sec": avg_ops,
            "avg_bandwidth_mb_sec": avg_bw
        })

    print("[RADOS] 4. Random read (obj_size=4M, concurrency=16)")
    iter_results = []
    for it in range(args.iterations):
        print(f"[RADOS]   Rand read iteration={it+1}/{args.iterations}")
        r = run_rados_bench_rand(args.ceph_conf, args.ceph_keyring, args.pool, "4M", 16, args.duration)
        if "error" not in r:
            iter_results.append(r)
    if iter_results:
        avg_ops = statistics.mean([r.get("throughput_ops_sec", 0) or r.get("total_throughput_ops_sec", 0) for r in iter_results])
        avg_bw = statistics.mean([r.get("bandwidth_mb_sec", 0) or 0 for r in iter_results])
        avg_lat = statistics.mean([r.get("avg_latency_ms", 0) or r.get("total_avg_latency_ms", 0) for r in iter_results])
        results["random_read"].append({
            "object_size": "4M",
            "concurrency": 16,
            "iterations": len(iter_results),
            "avg_throughput_ops_sec": avg_ops,
            "avg_bandwidth_mb_sec": avg_bw,
            "avg_latency_ms": avg_lat
        })

    print("[RADOS] 5. Mixed workloads (read+write at various ratios)")
    mixed_configs = [
        {"obj_size": "4K", "op": "write", "conc": 32, "label": "small_objects_write_heavy"},
        {"obj_size": "4K", "op": "seq", "conc": 32, "label": "small_objects_seq_read"},
        {"obj_size": "64K", "op": "write", "conc": 32, "label": "medium_objects_write"},
        {"obj_size": "64K", "op": "rand", "conc": 32, "label": "medium_objects_random_read"},
        {"obj_size": "4M", "op": "write", "conc": 16, "label": "large_objects_write"},
        {"obj_size": "4M", "op": "seq", "conc": 16, "label": "large_objects_seq_read"},
    ]
    for mc in mixed_configs:
        iter_results = []
        for it in range(args.iterations):
            print(f"[RADOS]   Mixed {mc['label']} iteration={it+1}/{args.iterations}")
            r = run_rados_bench(args.ceph_conf, args.ceph_keyring, args.pool, mc["op"], mc["obj_size"], mc["conc"], args.duration)
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            avg_ops = statistics.mean([r.get("throughput_ops_sec", 0) or r.get("total_throughput_ops_sec", 0) for r in iter_results])
            avg_bw = statistics.mean([r.get("bandwidth_mb_sec", 0) or 0 for r in iter_results])
            results["mixed_workloads"].append({
                "label": mc["label"],
                "object_size": mc["obj_size"],
                "op_type": mc["op"],
                "concurrency": mc["conc"],
                "iterations": len(iter_results),
                "avg_throughput_ops_sec": avg_ops,
                "avg_bandwidth_mb_sec": avg_bw
            })

    bench_output = {
        "benchmark": "rados_object_storage",
        "description": "RADOS object storage benchmarks using rados bench tool",
        "reference": "Ceph rados bench - https://docs.ceph.com/en/latest/man/8/rados/#bench",
        "timestamp": timestamp,
        "performance_metrics": {
            "throughput_ops_sec": {"unit": "ops/sec", "description": "Object operations per second"},
            "bandwidth_mb_sec": {"unit": "MB/sec", "description": "Data transfer bandwidth"},
            "latency_ms": {"unit": "ms", "description": "Average operation latency"},
            "concurrency": {"unit": "clients", "description": "Number of concurrent client operations"}
        },
        "dataset_info": {
            "name": "rados_bench_generated",
            "size": f"{len(obj_sizes)} object sizes x {max(conc_levels)} concurrency",
            "source": "Generated by rados bench tool on ARM64"
        },
        "results": results
    }

    write_results_section(args.results_json, args.section, bench_output)

    print(f"[RADOS] Results saved to {args.results_json} under section '{args.section}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
