#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import statistics
import tempfile


def run_cmd(cmd, timeout=300):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def parse_fio_output(output):
    try:
        data = json.loads(output)
        result = {}
        for job in data.get("jobs", []):
            jobname = job.get("jobname", "unknown")
            read = job.get("read", {})
            write = job.get("write", {})
            result[jobname] = {
                "read_iops": read.get("iops", 0),
                "read_bw_bytes": read.get("bw_bytes", 0),
                "read_bw_kb": read.get("bw", 0),
                "read_lat_ms": read.get("lat_ns", {}).get("mean", 0) / 1e6 if "lat_ns" in read else read.get("lat", {}).get("mean", 0),
                "read_clat_ms": read.get("clat_ns", {}).get("mean", 0) / 1e6 if "clat_ns" in read else read.get("clat", {}).get("mean", 0),
                "write_iops": write.get("iops", 0),
                "write_bw_bytes": write.get("bw_bytes", 0),
                "write_bw_kb": write.get("bw", 0),
                "write_lat_ms": write.get("lat_ns", {}).get("mean", 0) / 1e6 if "lat_ns" in write else write.get("lat", {}).get("mean", 0),
                "write_clat_ms": write.get("clat_ns", {}).get("mean", 0) / 1e6 if "clat_ns" in write else write.get("clat", {}).get("mean", 0),
            }
        return result
    except json.JSONDecodeError:
        return {"raw_output": output}


def generate_fio_config_rbd(pool, image, rw, bs, iodepth, numjobs, runtime, rbd_name):
    ioengine = "rbd"
    config = (
        f"[global]\n"
        f"ioengine={ioengine}\n"
        f"pool={pool}\n"
        f"rbd_name={image}\n"
        f"log_avg_msec=1000\n"
        f"\n"
        f"[{rbd_name}]\n"
        f"rw={rw}\n"
        f"bs={bs}\n"
        f"iodepth={iodepth}\n"
        f"numjobs={numjobs}\n"
        f"runtime={runtime}\n"
        f"time_based=1\n"
        f"group_reporting=1\n"
        f"write_bw_log={rbd_name}\n"
        f"write_iops_log={rbd_name}\n"
        f"write_lat_log={rbd_name}\n"
    )
    return config


def run_fio_rbd(pool, image, rw, bs, iodepth, numjobs, runtime, ceph_conf, ceph_keyring, iteration_label):
    fio_name = f"rbd_{iteration_label}"
    config = generate_fio_config_rbd(pool, image, rw, bs, iodepth, numjobs, runtime, fio_name)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".fio", delete=False) as tf:
        tf.write(config)
        tf.flush()
        config_path = tf.name

    env_prefix = f"CEPH_CONF={ceph_conf} CEPH_KEYRING={ceph_keyring}"
    cmd = f"{env_prefix} fio {config_path} --output-format=json 2>/dev/null"
    out, err, rc = run_cmd(cmd, timeout=runtime + 120)

    os.unlink(config_path)

    if rc != 0:
        return {"error": err or "fio rbd failed", "returncode": rc}

    parsed = parse_fio_output(out)
    if fio_name in parsed and isinstance(parsed[fio_name], dict):
        return parsed[fio_name]
    return parsed


def main():
    parser = argparse.ArgumentParser(description="RBD Block Storage Benchmarks")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--ceph-conf", default="/etc/ceph/ceph.conf")
    parser.add_argument("--ceph-keyring", default="/etc/ceph/ceph.client.admin.keyring")
    parser.add_argument("--pool", default="bench_rbd")
    parser.add_argument("--image", default="bench_image")
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    results = {
        "sequential_read_write": [],
        "random_read_write": [],
        "iodepth_scaling": [],
        "block_size_sweep": [],
        "mixed_rw_workloads": []
    }

    print("[RBD] Phase 3b: RBD Block Storage Benchmarks")

    fio_check, _, rc = run_cmd("fio --version 2>/dev/null")
    if rc != 0:
        print("[RBD] ERROR: fio not available. Cannot run RBD benchmarks.")
        bench_output = {
            "benchmark": "rbd_block_storage",
            "description": "RBD block storage benchmarks using FIO rbd engine",
            "reference": "FIO - https://fio.readthedocs.io/ with RBD ioengine",
            "timestamp": timestamp,
            "performance_metrics": {
                "iops": {"unit": "IOPS", "description": "Input/output operations per second"},
                "bandwidth": {"unit": "MB/sec", "description": "Data transfer bandwidth"},
                "latency": {"unit": "ms", "description": "Average operation latency"}
            },
            "dataset_info": {"name": "rbd_10G_image", "size": "10GB RBD image", "source": "Created on ARM64 cluster"},
            "results": results,
            "error": "fio not available"
        }
        output_file = os.path.join(args.results_dir, "benchmark_rbd.json")
        with open(output_file, "w") as f:
            json.dump(bench_output, f, indent=2)
        return 1

    print("[RBD] 1. Sequential read (bs=4M, iodepth=32)")
    iter_results = []
    for it in range(args.iterations):
        print(f"[RBD]   Seq read iteration={it+1}/{args.iterations}")
        r = run_fio_rbd(args.pool, args.image, "read", "4M", 32, 1, 30, args.ceph_conf, args.ceph_keyring, f"seq_read_{it}")
        if "error" not in r:
            iter_results.append(r)
    if iter_results:
        avg_iops = statistics.mean([r.get("read_iops", 0) for r in iter_results])
        avg_bw = statistics.mean([r.get("read_bw_bytes", 0) / (1024*1024) for r in iter_results if r.get("read_bw_bytes", 0) > 0] or [r.get("read_bw_kb", 0) / 1024 for r in iter_results])
        avg_lat = statistics.mean([r.get("read_lat_ms", 0) for r in iter_results])
        results["sequential_read_write"].append({
            "rw": "sequential_read",
            "block_size": "4M",
            "iodepth": 32,
            "iterations": len(iter_results),
            "avg_iops": avg_iops,
            "avg_bandwidth_mb_sec": avg_bw,
            "avg_latency_ms": avg_lat
        })

    print("[RBD] 2. Sequential write (bs=4M, iodepth=32)")
    iter_results = []
    for it in range(args.iterations):
        print(f"[RBD]   Seq write iteration={it+1}/{args.iterations}")
        r = run_fio_rbd(args.pool, args.image, "write", "4M", 32, 1, 30, args.ceph_conf, args.ceph_keyring, f"seq_write_{it}")
        if "error" not in r:
            iter_results.append(r)
    if iter_results:
        avg_iops = statistics.mean([r.get("write_iops", 0) for r in iter_results])
        avg_bw = statistics.mean([r.get("write_bw_bytes", 0) / (1024*1024) for r in iter_results if r.get("write_bw_bytes", 0) > 0] or [r.get("write_bw_kb", 0) / 1024 for r in iter_results])
        avg_lat = statistics.mean([r.get("write_lat_ms", 0) for r in iter_results])
        results["sequential_read_write"].append({
            "rw": "sequential_write",
            "block_size": "4M",
            "iodepth": 32,
            "iterations": len(iter_results),
            "avg_iops": avg_iops,
            "avg_bandwidth_mb_sec": avg_bw,
            "avg_latency_ms": avg_lat
        })

    print("[RBD] 3. Random read (bs=4K, iodepth=64)")
    iter_results = []
    for it in range(args.iterations):
        print(f"[RBD]   Rand read iteration={it+1}/{args.iterations}")
        r = run_fio_rbd(args.pool, args.image, "randread", "4K", 64, 1, 30, args.ceph_conf, args.ceph_keyring, f"rand_read_{it}")
        if "error" not in r:
            iter_results.append(r)
    if iter_results:
        avg_iops = statistics.mean([r.get("read_iops", 0) for r in iter_results])
        avg_lat = statistics.mean([r.get("read_lat_ms", 0) for r in iter_results])
        results["random_read_write"].append({
            "rw": "random_read",
            "block_size": "4K",
            "iodepth": 64,
            "iterations": len(iter_results),
            "avg_iops": avg_iops,
            "avg_latency_ms": avg_lat
        })

    print("[RBD] 4. Random write (bs=4K, iodepth=64)")
    iter_results = []
    for it in range(args.iterations):
        print(f"[RBD]   Rand write iteration={it+1}/{args.iterations}")
        r = run_fio_rbd(args.pool, args.image, "randwrite", "4K", 64, 1, 30, args.ceph_conf, args.ceph_keyring, f"rand_write_{it}")
        if "error" not in r:
            iter_results.append(r)
    if iter_results:
        avg_iops = statistics.mean([r.get("write_iops", 0) for r in iter_results])
        avg_lat = statistics.mean([r.get("write_lat_ms", 0) for r in iter_results])
        results["random_read_write"].append({
            "rw": "random_write",
            "block_size": "4K",
            "iodepth": 64,
            "iterations": len(iter_results),
            "avg_iops": avg_iops,
            "avg_latency_ms": avg_lat
        })

    print("[RBD] 5. IODEPTH scaling (random read, bs=4K)")
    for iodepth in [1, 4, 8, 16, 32, 64, 128]:
        iter_results = []
        for it in range(args.iterations):
            print(f"[RBD]   Rand read iodepth={iodepth}, iteration={it+1}/{args.iterations}")
            r = run_fio_rbd(args.pool, args.image, "randread", "4K", iodepth, 1, 30, args.ceph_conf, args.ceph_keyring, f"iodepth_{iodepth}_{it}")
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            avg_iops = statistics.mean([r.get("read_iops", 0) for r in iter_results])
            avg_lat = statistics.mean([r.get("read_lat_ms", 0) for r in iter_results])
            results["iodepth_scaling"].append({
                "rw": "random_read",
                "block_size": "4K",
                "iodepth": iodepth,
                "iterations": len(iter_results),
                "avg_iops": avg_iops,
                "avg_latency_ms": avg_lat
            })

    print("[RBD] 6. Block size sweep (random read, iodepth=32)")
    for bs in ["4K", "8K", "16K", "32K", "64K", "128K", "256K", "512K", "1M"]:
        iter_results = []
        for it in range(args.iterations):
            print(f"[RBD]   Rand read bs={bs}, iteration={it+1}/{args.iterations}")
            r = run_fio_rbd(args.pool, args.image, "randread", bs, 32, 1, 30, args.ceph_conf, args.ceph_keyring, f"bs_{bs}_{it}")
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            avg_iops = statistics.mean([r.get("read_iops", 0) for r in iter_results])
            avg_bw = statistics.mean([r.get("read_bw_bytes", 0) / (1024*1024) for r in iter_results if r.get("read_bw_bytes", 0) > 0] or [r.get("read_bw_kb", 0) / 1024 for r in iter_results])
            avg_lat = statistics.mean([r.get("read_lat_ms", 0) for r in iter_results])
            results["block_size_sweep"].append({
                "rw": "random_read",
                "block_size": bs,
                "iodepth": 32,
                "iterations": len(iter_results),
                "avg_iops": avg_iops,
                "avg_bandwidth_mb_sec": avg_bw,
                "avg_latency_ms": avg_lat
            })

    print("[RBD] 7. Mixed R/W workloads (70% read / 30% write)")
    mixed_configs = [
        {"rw": "randrw", "rwmixread": 70, "bs": "4K", "iodepth": 32, "label": "small_block_70r_30w"},
        {"rw": "randrw", "rwmixread": 70, "bs": "64K", "iodepth": 32, "label": "medium_block_70r_30w"},
        {"rw": "randrw", "rwmixread": 50, "bs": "4K", "iodepth": 32, "label": "small_block_50r_50w"},
        {"rw": "randrw", "rwmixread": 90, "bs": "4K", "iodepth": 32, "label": "small_block_90r_10w"},
    ]
    for mc in mixed_configs:
        config = (
            f"[global]\n"
            f"ioengine=rbd\n"
            f"pool={args.pool}\n"
            f"rbd_name={args.image}\n"
            f"log_avg_msec=1000\n"
            f"\n"
            f"[rbd_mixed_{mc['label']}]\n"
            f"rw={mc['rw']}\n"
            f"rwmixread={mc['rwmixread']}\n"
            f"bs={mc['bs']}\n"
            f"iodepth={mc['iodepth']}\n"
            f"numjobs=1\n"
            f"runtime=30\n"
            f"time_based=1\n"
            f"group_reporting=1\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".fio", delete=False) as tf:
            tf.write(config)
            tf.flush()
            config_path = tf.name

        env_prefix = f"CEPH_CONF={args.ceph_conf} CEPH_KEYRING={args.ceph_keyring}"
        cmd = f"{env_prefix} fio {config_path} --output-format=json 2>/dev/null"

        iter_results = []
        for it in range(args.iterations):
            print(f"[RBD]   Mixed {mc['label']} iteration={it+1}/{args.iterations}")
            out, err, rc = run_cmd(cmd, timeout=120)
            if rc == 0:
                parsed = parse_fio_output(out)
                job_key = f"rbd_mixed_{mc['label']}"
                if job_key in parsed and isinstance(parsed[job_key], dict):
                    iter_results.append(parsed[job_key])

        os.unlink(config_path)

        if iter_results:
            avg_riops = statistics.mean([r.get("read_iops", 0) for r in iter_results])
            avg_wiops = statistics.mean([r.get("write_iops", 0) for r in iter_results])
            avg_rbw = statistics.mean([r.get("read_bw_bytes", 0) / (1024*1024) for r in iter_results if r.get("read_bw_bytes", 0) > 0] or [r.get("read_bw_kb", 0) / 1024 for r in iter_results])
            avg_wbw = statistics.mean([r.get("write_bw_bytes", 0) / (1024*1024) for r in iter_results if r.get("write_bw_bytes", 0) > 0] or [r.get("write_bw_kb", 0) / 1024 for r in iter_results])
            results["mixed_rw_workloads"].append({
                "label": mc["label"],
                "rw_mix": f"{mc['rwmixread']}%R/{100-mc['rwmixread']}%W",
                "block_size": mc["bs"],
                "iodepth": mc["iodepth"],
                "iterations": len(iter_results),
                "avg_read_iops": avg_riops,
                "avg_write_iops": avg_wiops,
                "avg_read_bw_mb_sec": avg_rbw,
                "avg_write_bw_mb_sec": avg_wbw
            })

    bench_output = {
        "benchmark": "rbd_block_storage",
        "description": "RBD block storage benchmarks using FIO with rbd I/O engine",
        "reference": "FIO RBD engine - https://fio.readthedocs.io/en/latest/fio_doc.html#rbd",
        "timestamp": timestamp,
        "performance_metrics": {
            "iops": {"unit": "IOPS", "description": "Input/output operations per second"},
            "bandwidth_mb_sec": {"unit": "MB/sec", "description": "Data transfer bandwidth"},
            "latency_ms": {"unit": "ms", "description": "Average operation latency"},
            "iodepth": {"unit": "queue_depth", "description": "I/O queue depth per job"}
        },
        "dataset_info": {
            "name": "rbd_10G_image",
            "size": "10GB RBD image on bench_rbd pool",
            "source": "Created on ARM64 Ceph cluster"
        },
        "results": results
    }

    output_file = os.path.join(args.results_dir, "benchmark_rbd.json")
    with open(output_file, "w") as f:
        json.dump(bench_output, f, indent=2)

    print(f"[RBD] Results saved to {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())