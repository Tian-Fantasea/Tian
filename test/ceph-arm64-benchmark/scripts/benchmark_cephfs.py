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
                "write_iops": write.get("iops", 0),
                "write_bw_bytes": write.get("bw_bytes", 0),
                "write_bw_kb": write.get("bw", 0),
                "write_lat_ms": write.get("lat_ns", {}).get("mean", 0) / 1e6 if "lat_ns" in write else write.get("lat", {}).get("mean", 0),
            }
        return result
    except json.JSONDecodeError:
        return {"raw_output": output}


def generate_fio_config_localfs(mount_point, rw, bs, iodepth, numjobs, runtime, job_name, rw_mixread=None):
    config = (
        f"[global]\n"
        f"ioengine=libaio\n"
        f"directory={mount_point}\n"
        f"direct=1\n"
        f"log_avg_msec=1000\n"
        f"\n"
        f"[{job_name}]\n"
        f"rw={rw}\n"
    )
    if rw_mixread is not None:
        config += f"rwmixread={rw_mixread}\n"
    config += (
        f"bs={bs}\n"
        f"iodepth={iodepth}\n"
        f"numjobs={numjobs}\n"
        f"runtime={runtime}\n"
        f"time_based=1\n"
        f"group_reporting=1\n"
        f"size=1G\n"
        f"nrfiles=1\n"
    )
    return config


def run_fio_cephfs(mount_point, rw, bs, iodepth, numjobs, runtime, iteration_label, rw_mixread=None):
    fio_name = f"cephfs_{iteration_label}"
    config = generate_fio_config_localfs(mount_point, rw, bs, iodepth, numjobs, runtime, fio_name, rw_mixread)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".fio", delete=False) as tf:
        tf.write(config)
        tf.flush()
        config_path = tf.name

    cmd = f"fio {config_path} --output-format=json 2>/dev/null"
    out, err, rc = run_cmd(cmd, timeout=runtime + 120)

    os.unlink(config_path)

    if rc != 0:
        return {"error": err or "fio cephfs failed", "returncode": rc}

    parsed = parse_fio_output(out)
    if fio_name in parsed and isinstance(parsed[fio_name], dict):
        return parsed[fio_name]
    return parsed


def run_metadata_benchmark(mount_point, data_size):
    results = {}

    print("[CEPHFS]   Metadata: mkdir throughput")
    test_dir = os.path.join(mount_point, "bench_meta_mkdir")
    os.makedirs(test_dir, exist_ok=True)
    cmd = f"for i in $(seq 1 {data_size}); do mkdir -p {test_dir}/dir_$i; done"
    start = time.time()
    _, _, rc = run_cmd(cmd, timeout=300)
    elapsed = time.time() - start
    results["mkdir_ops_sec"] = data_size / elapsed if elapsed > 0 else 0

    print("[CEPHFS]   Metadata: stat throughput")
    cmd = f"for i in $(seq 1 {data_size}); do stat {test_dir}/dir_$i > /dev/null 2>&1; done"
    start = time.time()
    _, _, rc = run_cmd(cmd, timeout=300)
    elapsed = time.time() - start
    results["stat_ops_sec"] = data_size / elapsed if elapsed > 0 else 0

    print("[CEPHFS]   Metadata: ls throughput")
    cmd = f"ls {test_dir} > /dev/null 2>&1"
    start = time.time()
    _, _, rc = run_cmd(cmd, timeout=60)
    elapsed = time.time() - start
    results["ls_ops_sec"] = 1 / elapsed if elapsed > 0 else 0

    print("[CEPHFS]   Metadata: rmdir throughput")
    cmd = f"for i in $(seq 1 {data_size}); do rmdir {test_dir}/dir_$i 2>/dev/null; done"
    start = time.time()
    _, _, rc = run_cmd(cmd, timeout=300)
    elapsed = time.time() - start
    results["rmdir_ops_sec"] = data_size / elapsed if elapsed > 0 else 0

    run_cmd(f"rm -rf {test_dir}", timeout=60)

    return results


def run_smallfile_benchmark(mount_point, data_size):
    results = {}
    smallfile_path = os.path.join(mount_point, "bench_smallfile")
    os.makedirs(smallfile_path, exist_ok=True)

    print("[CEPHFS]   Small file: create throughput")
    cmd = f"for i in $(seq 1 {data_size}); do dd if=/dev/zero of={smallfile_path}/file_$i bs=4K count=1 > /dev/null 2>&1; done"
    start = time.time()
    _, _, rc = run_cmd(cmd, timeout=600)
    elapsed = time.time() - start
    results["small_file_create_ops_sec"] = data_size / elapsed if elapsed > 0 else 0

    print("[CEPHFS]   Small file: read throughput")
    cmd = f"for i in $(seq 1 {data_size}); do cat {smallfile_path}/file_$i > /dev/null 2>&1; done"
    start = time.time()
    _, _, rc = run_cmd(cmd, timeout=600)
    elapsed = time.time() - start
    results["small_file_read_ops_sec"] = data_size / elapsed if elapsed > 0 else 0

    print("[CEPHFS]   Small file: delete throughput")
    cmd = f"for i in $(seq 1 {data_size}); do rm -f {smallfile_path}/file_$i 2>/dev/null; done"
    start = time.time()
    _, _, rc = run_cmd(cmd, timeout=600)
    elapsed = time.time() - start
    results["small_file_delete_ops_sec"] = data_size / elapsed if elapsed > 0 else 0

    run_cmd(f"rm -rf {smallfile_path}", timeout=60)

    return results


def main():
    parser = argparse.ArgumentParser(description="CephFS File Storage Benchmarks")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--mount-point", default="/mnt/cephfs")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--data-size", type=int, default=1000)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    results = {
        "metadata_operations": [],
        "small_file_operations": [],
        "sequential_io": [],
        "random_io": [],
        "mixed_io": []
    }

    print("[CEPHFS] Phase 3c: CephFS File Storage Benchmarks")

    mount_check, _, rc = run_cmd(f"mountpoint -q {args.mount_point} 2>/dev/null || stat {args.mount_point} 2>/dev/null")
    if rc != 0 and not os.path.isdir(args.mount_point):
        print(f"[CEPHFS] WARNING: Mount point {args.mount_point} not accessible. Some tests may fail.")
    else:
        print(f"[CEPHFS] Mount point: {args.mount_point}")

    print("[CEPHFS] 1. Metadata operations benchmark")
    for it in range(args.iterations):
        print(f"[CEPHFS]   Metadata iteration={it+1}/{args.iterations}")
        meta_r = run_metadata_benchmark(args.mount_point, args.data_size)
        if meta_r:
            results["metadata_operations"].append({
                "iteration": it + 1,
                **meta_r
            })

    print("[CEPHFS] 2. Small file operations benchmark")
    for it in range(args.iterations):
        print(f"[CEPHFS]   Smallfile iteration={it+1}/{args.iterations}")
        sf_r = run_smallfile_benchmark(args.mount_point, args.data_size)
        if sf_r:
            results["small_file_operations"].append({
                "iteration": it + 1,
                **sf_r
            })

    print("[CEPHFS] 3. Sequential I/O (libaio on CephFS)")
    seq_configs = [
        {"rw": "read", "bs": "1M", "iodepth": 32, "label": "seq_read_1M"},
        {"rw": "write", "bs": "1M", "iodepth": 32, "label": "seq_write_1M"},
        {"rw": "read", "bs": "4M", "iodepth": 16, "label": "seq_read_4M"},
        {"rw": "write", "bs": "4M", "iodepth": 16, "label": "seq_write_4M"},
    ]
    for sc in seq_configs:
        iter_results = []
        for it in range(args.iterations):
            print(f"[CEPHFS]   {sc['label']} iteration={it+1}/{args.iterations}")
            r = run_fio_cephfs(args.mount_point, sc["rw"], sc["bs"], sc["iodepth"], 1, 30, f"{sc['label']}_{it}")
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            iops_key = "read_iops" if "read" in sc["rw"] else "write_iops"
            bw_key = "read_bw_bytes" if "read" in sc["rw"] else "write_bw_bytes"
            bw_kb_key = "read_bw_kb" if "read" in sc["rw"] else "write_bw_kb"
            lat_key = "read_lat_ms" if "read" in sc["rw"] else "write_lat_ms"
            avg_iops = statistics.mean([r.get(iops_key, 0) for r in iter_results])
            avg_bw = statistics.mean([r.get(bw_key, 0) / (1024*1024) for r in iter_results if r.get(bw_key, 0) > 0] or [r.get(bw_kb_key, 0) / 1024 for r in iter_results])
            avg_lat = statistics.mean([r.get(lat_key, 0) for r in iter_results])
            results["sequential_io"].append({
                "label": sc["label"],
                "rw": sc["rw"],
                "block_size": sc["bs"],
                "iodepth": sc["iodepth"],
                "iterations": len(iter_results),
                "avg_iops": avg_iops,
                "avg_bandwidth_mb_sec": avg_bw,
                "avg_latency_ms": avg_lat
            })

    print("[CEPHFS] 4. Random I/O")
    rand_configs = [
        {"rw": "randread", "bs": "4K", "iodepth": 32, "label": "rand_read_4K"},
        {"rw": "randwrite", "bs": "4K", "iodepth": 32, "label": "rand_write_4K"},
        {"rw": "randread", "bs": "64K", "iodepth": 32, "label": "rand_read_64K"},
        {"rw": "randwrite", "bs": "64K", "iodepth": 32, "label": "rand_write_64K"},
    ]
    for rc_config in rand_configs:
        iter_results = []
        for it in range(args.iterations):
            print(f"[CEPHFS]   {rc_config['label']} iteration={it+1}/{args.iterations}")
            r = run_fio_cephfs(args.mount_point, rc_config["rw"], rc_config["bs"], rc_config["iodepth"], 1, 30, f"{rc_config['label']}_{it}")
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            iops_key = "read_iops" if "read" in rc_config["rw"] else "write_iops"
            bw_key = "read_bw_bytes" if "read" in rc_config["rw"] else "write_bw_bytes"
            bw_kb_key = "read_bw_kb" if "read" in rc_config["rw"] else "write_bw_kb"
            lat_key = "read_lat_ms" if "read" in rc_config["rw"] else "write_lat_ms"
            avg_iops = statistics.mean([r.get(iops_key, 0) for r in iter_results])
            avg_bw = statistics.mean([r.get(bw_key, 0) / (1024*1024) for r in iter_results if r.get(bw_key, 0) > 0] or [r.get(bw_kb_key, 0) / 1024 for r in iter_results])
            avg_lat = statistics.mean([r.get(lat_key, 0) for r in iter_results])
            results["random_io"].append({
                "label": rc_config["label"],
                "rw": rc_config["rw"],
                "block_size": rc_config["bs"],
                "iodepth": rc_config["iodepth"],
                "iterations": len(iter_results),
                "avg_iops": avg_iops,
                "avg_bandwidth_mb_sec": avg_bw,
                "avg_latency_ms": avg_lat
            })

    print("[CEPHFS] 5. Mixed I/O (70% read / 30% write)")
    mixed_configs = [
        {"rw": "randrw", "rwmixread": 70, "bs": "4K", "iodepth": 32, "label": "mixed_70r30w_4K"},
        {"rw": "randrw", "rwmixread": 50, "bs": "4K", "iodepth": 32, "label": "mixed_50r50w_4K"},
        {"rw": "randrw", "rwmixread": 70, "bs": "64K", "iodepth": 32, "label": "mixed_70r30w_64K"},
    ]
    for mc in mixed_configs:
        iter_results = []
        for it in range(args.iterations):
            print(f"[CEPHFS]   {mc['label']} iteration={it+1}/{args.iterations}")
            r = run_fio_cephfs(args.mount_point, mc["rw"], mc["bs"], mc["iodepth"], 1, 30, f"{mc['label']}_{it}", mc["rwmixread"])
            if "error" not in r:
                iter_results.append(r)
        if iter_results:
            avg_riops = statistics.mean([r.get("read_iops", 0) for r in iter_results])
            avg_wiops = statistics.mean([r.get("write_iops", 0) for r in iter_results])
            avg_rbw = statistics.mean([r.get("read_bw_bytes", 0) / (1024*1024) for r in iter_results if r.get("read_bw_bytes", 0) > 0] or [r.get("read_bw_kb", 0) / 1024 for r in iter_results])
            avg_wbw = statistics.mean([r.get("write_bw_bytes", 0) / (1024*1024) for r in iter_results if r.get("write_bw_bytes", 0) > 0] or [r.get("write_bw_kb", 0) / 1024 for r in iter_results])
            results["mixed_io"].append({
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
        "benchmark": "cephfs_file_storage",
        "description": "CephFS file storage benchmarks using FIO libaio and metadata operations",
        "reference": "FIO libaio - https://fio.readthedocs.io/ + CephFS metadata ops",
        "timestamp": timestamp,
        "performance_metrics": {
            "metadata_ops_sec": {"unit": "ops/sec", "description": "Metadata operations per second (mkdir/stat/ls/rmdir)"},
            "iops": {"unit": "IOPS", "description": "File I/O operations per second"},
            "bandwidth_mb_sec": {"unit": "MB/sec", "description": "Data transfer bandwidth"},
            "latency_ms": {"unit": "ms", "description": "Average operation latency"}
        },
        "dataset_info": {
            "name": "cephfs_mount_data",
            "size": f"{args.data_size} metadata ops + FIO generated data",
            "source": "Generated on ARM64 CephFS mount"
        },
        "results": results
    }

    output_file = os.path.join(args.results_dir, "benchmark_cephfs.json")
    with open(output_file, "w") as f:
        json.dump(bench_output, f, indent=2)

    print(f"[CEPHFS] Results saved to {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())