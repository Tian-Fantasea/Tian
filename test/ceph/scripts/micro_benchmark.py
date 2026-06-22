#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import statistics


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


def run_cmd(cmd, timeout=300):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def parse_rados_bench_output(output):
    result = {}
    lines = output.strip().split("\n")
    for line in lines:
        if "sec" in line and "ops" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "ops/sec":
                    try:
                        result["throughput_ops_sec"] = float(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                if "MB/sec" in p:
                    try:
                        result["bandwidth_mb_sec"] = float(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                if "lat" in p.lower():
                    try:
                        result["avg_latency_ms"] = float(parts[i - 1])
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


def run_osd_performance_test(ceph_conf, ceph_keyring, cluster_name, duration):
    results = {}

    print("[MICRO]   OSD performance: per-OSD throughput")
    perf_out, _, rc = run_cmd(f"ceph -c {ceph_conf} osd perf --format json 2>/dev/null", timeout=15)
    if rc == 0 and perf_out:
        try:
            perf_data = json.loads(perf_out)
            osd_perf_list = perf_data.get("osd_perf_infos", [])
            results["osd_perf"] = []
            for osd_entry in osd_perf_list:
                results["osd_perf"].append({
                    "osd": osd_entry.get("id", -1),
                    "perf_stats": osd_entry.get("perf_stats", {})
                })
        except json.JSONDecodeError:
            results["osd_perf_raw"] = perf_out

    print("[MICRO]   OSD dump: latency stats")
    dump_out, _, rc = run_cmd(f"ceph -c {ceph_conf} osd dump --format json 2>/dev/null", timeout=15)
    if rc == 0 and dump_out:
        try:
            dump_data = json.loads(dump_out)
            results["osd_count"] = len(dump_data.get("osds", []))
        except json.JSONDecodeError:
            pass

    return results


def run_ec_vs_replicated_test(ceph_conf, ceph_keyring, cluster_name, duration):
    results = []
    ec_profiles = [
        {"name": "ec_2_1", "k": 2, "m": 1, "plugin": "isa"},
        {"name": "ec_4_2", "k": 4, "m": 2, "plugin": "isa"},
        {"name": "ec_8_3", "k": 8, "m": 3, "plugin": "isa"},
    ]

    for ec in ec_profiles:
        pool_name = f"bench_ec_{ec['name']}"

        print(f"[MICRO]   Creating EC pool: {pool_name} (k={ec['k']}, m={ec['m']})")
        _, _, rc = run_cmd(
            f"ceph -c {ceph_conf} osd pool create {pool_name} 64 64 erasure {ec['plugin']} {ec['k']} {ec['m']} 2>/dev/null",
            timeout=30
        )
        if rc != 0:
            _, _, rc2 = run_cmd(
                f"ceph -c {ceph_conf} osd pool create {pool_name} 64 64 erasure 2>/dev/null",
                timeout=30
            )

        if rc != 0 and rc2 != 0:
            results.append({
                "ec_profile": ec["name"],
                "k": ec["k"],
                "m": ec["m"],
                "error": "pool creation failed",
                "skip": True
            })
            continue

        rados_out, _, rc = run_rados_bench(ceph_conf, ceph_keyring, pool_name, "write", "4M", 16, duration)
        ec_result = {
            "ec_profile": ec["name"],
            "k": ec["k"],
            "m": ec["m"],
            "data_efficiency": f"{ec['k']}/{ec['k']+ec['m']} = {ec['k']/(ec['k']+ec['m'])*100:.0f}%"
        }
        if "error" not in rados_out:
            ec_result["avg_throughput_ops_sec"] = rados_out.get("throughput_ops_sec", 0)
            ec_result["avg_bandwidth_mb_sec"] = rados_out.get("bandwidth_mb_sec", 0)
        else:
            ec_result["error"] = rados_out.get("error", "rados bench failed")

        results.append(ec_result)

        run_cmd(f"ceph -c {ceph_conf} osd pool delete {pool_name} {pool_name} --yes-i-really-really-mean-it 2>/dev/null", timeout=30)

    rep_pool = "bench_rados"
    print(f"[MICRO]   Replicated pool baseline: {rep_pool} (3x replication)")
    rep_out, _, rc = run_rados_bench(ceph_conf, ceph_keyring, rep_pool, "write", "4M", 16, duration)
    rep_result = {"ec_profile": "replicated_3x", "k": 1, "m": 0, "data_efficiency": "1/3 = 33%"}
    if "error" not in rep_out:
        rep_result["avg_throughput_ops_sec"] = rep_out.get("throughput_ops_sec", 0)
        rep_result["avg_bandwidth_mb_sec"] = rep_out.get("bandwidth_mb_sec", 0)
    results.append(rep_result)

    return results


def run_compression_test(ceph_conf, ceph_keyring, cluster_name, duration):
    results = []

    compression_algos = ["none", "lz4", "snappy", "zstd"]

    for algo in compression_algos:
        pool_name = f"bench_compress_{algo}"

        print(f"[MICRO]   Creating compression pool: {pool_name} (algo={algo})")
        _, _, rc = run_cmd(
            f"ceph -c {ceph_conf} osd pool create {pool_name} 64 64 replicated 2>/dev/null",
            timeout=30
        )

        if algo != "none":
            run_cmd(
                f"ceph -c {ceph_conf} osd pool set {pool_name} compression_algorithm {algo} 2>/dev/null",
                timeout=10
            )
            run_cmd(
                f"ceph -c {ceph_conf} osd pool set {pool_name} compression_mode aggressive 2>/dev/null",
                timeout=10
            )

        rados_out, _, rc = run_rados_bench(ceph_conf, ceph_keyring, pool_name, "write", "4M", 16, duration)
        comp_result = {"compression_algorithm": algo}

        if "error" not in rados_out:
            comp_result["avg_throughput_ops_sec"] = rados_out.get("throughput_ops_sec", 0)
            comp_result["avg_bandwidth_mb_sec"] = rados_out.get("bandwidth_mb_sec", 0)
        else:
            comp_result["error"] = rados_out.get("error", "benchmark failed")

        df_out, _, df_rc = run_cmd(f"rados -c {ceph_conf} --keyring {ceph_keyring} df --format json 2>/dev/null", timeout=15)
        if df_rc == 0 and df_out:
            try:
                df_data = json.loads(df_out)
                for pool_df in df_data.get("pools", []):
                    if pool_df.get("name") == pool_name:
                        comp_result["stored_bytes"] = pool_df.get("stored", 0)
                        comp_result["compress_bytes"] = pool_df.get("compress_bytes", 0)
                        comp_result["compress_ratio"] = pool_df.get("compress_ratio", "unknown")
                        break
            except json.JSONDecodeError:
                pass

        results.append(comp_result)

        run_cmd(f"ceph -c {ceph_conf} osd pool delete {pool_name} {pool_name} --yes-i-really-really-mean-it 2>/dev/null", timeout=30)

    return results


def run_arm64_crc32c_test(ceph_conf, ceph_keyring, cluster_name, duration):
    results = {}

    print("[MICRO]   ARM64 CRC32C checksum performance comparison")

    pool_name = "bench_crc32c"
    _, _, rc = run_cmd(
        f"ceph -c {ceph_conf} osd pool create {pool_name} 64 64 replicated 2>/dev/null",
        timeout=30
    )

    checksum_out, _, chk_rc = run_cmd(
        f"ceph -c {ceph_conf} config get osd bluestore_checksum_verify_on_read 2>/dev/null",
        timeout=10
    )
    results["bluestore_checksum_verify"] = checksum_out if chk_rc == 0 else "unknown"

    crc_info, _, _ = run_cmd("cat /proc/cpuinfo 2>/dev/null | grep -i crc | head -1")
    results["arm64_crc32c_hardware"] = "crc32" in crc_info.lower() or len(crc_info) > 0

    rados_out, _, rc = run_rados_bench(ceph_conf, ceph_keyring, pool_name, "write", "4K", 32, duration)
    if "error" not in rados_out:
        results["small_object_write_throughput_ops_sec"] = rados_out.get("throughput_ops_sec", 0)

    rados_seq_out, _, rc = run_rados_bench(ceph_conf, ceph_keyring, pool_name, "seq", "4K", 32, duration)
    if "error" not in rados_seq_out:
        results["small_object_seq_read_throughput_ops_sec"] = rados_seq_out.get("throughput_ops_sec", 0)

    run_cmd(f"ceph -c {ceph_conf} osd pool delete {pool_name} {pool_name} --yes-i-really-really-mean-it 2>/dev/null", timeout=30)

    return results


def run_rbd_cache_test(ceph_conf, ceph_keyring, cluster_name):
    results = {}

    print("[MICRO]   RBD caching performance")

    cache_configs = [
        {"rbd_cache": "true", "rbd_cache_max": "32", "label": "cache_enabled_32MB"},
        {"rbd_cache": "false", "label": "cache_disabled"},
        {"rbd_cache": "true", "rbd_cache_max": "64", "label": "cache_enabled_64MB"},
    ]

    for cc in cache_configs:
        pool_name = f"bench_rbd_cache_{cc['label']}"
        _, _, rc = run_cmd(
            f"ceph -c {ceph_conf} osd pool create {pool_name} 64 64 replicated 2>/dev/null",
            timeout=30
        )
        run_cmd(f"rbd create bench_cache_img --size 5G --pool {pool_name} 2>/dev/null", timeout=30)

        fio_config = (
            f"[global]\n"
            f"ioengine=rbd\n"
            f"pool={pool_name}\n"
            f"rbd_name=bench_cache_img\n"
            f"rbd_cache={cc['rbd_cache']}\n"
        )
        if "rbd_cache_max" in cc:
            fio_config += f"rbd_cache_max={cc['rbd_cache_max']}\n"
        fio_config += (
            f"\n"
            f"[rbd_cache_test]\n"
            f"rw=randread\n"
            f"bs=4K\n"
            f"iodepth=32\n"
            f"numjobs=1\n"
            f"runtime=30\n"
            f"time_based=1\n"
            f"group_reporting=1\n"
        )

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".fio", delete=False) as tf:
            tf.write(fio_config)
            tf.flush()
            config_path = tf.name

        cmd = f"CEPH_CONF={ceph_conf} CEPH_KEYRING={ceph_keyring} fio {config_path} --output-format=json 2>/dev/null"
        out, err, rc = run_cmd(cmd, timeout=120)
        os.unlink(config_path)

        cache_result = {"label": cc["label"], "rbd_cache": cc["rbd_cache"]}
        if rc == 0:
            try:
                fio_data = json.loads(out)
                for job in fio_data.get("jobs", []):
                    read = job.get("read", {})
                    cache_result["iops"] = read.get("iops", 0)
                    cache_result["latency_ms"] = read.get("lat_ns", {}).get("mean", 0) / 1e6 if "lat_ns" in read else read.get("lat", {}).get("mean", 0)
            except json.JSONDecodeError:
                cache_result["error"] = "fio output parse error"
        else:
            cache_result["error"] = err or "fio failed"

        results[cc["label"]] = cache_result

        run_cmd(f"rbd remove bench_cache_img --pool {pool_name} 2>/dev/null", timeout=30)
        run_cmd(f"ceph -c {ceph_conf} osd pool delete {pool_name} {pool_name} --yes-i-really-really-mean-it 2>/dev/null", timeout=30)

    return results


def main():
    parser = argparse.ArgumentParser(description="Micro Benchmarks for Ceph on ARM64")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--results-json", required=True)
    parser.add_argument("--section", default="micro_benchmark")
    parser.add_argument("--ceph-conf", default="/etc/ceph/ceph.conf")
    parser.add_argument("--ceph-keyring", default="/etc/ceph/ceph.client.admin.keyring")
    parser.add_argument("--cluster-name", default="ceph")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--duration", type=int, default=30)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    results = {
        "osd_performance": [],
        "ec_vs_replicated": [],
        "compression_algorithms": [],
        "arm64_crc32c_checksum": {},
        "rbd_cache_configs": {}
    }

    print("[MICRO] Phase 3d: Micro Benchmarks (OSD/EC/Compression/CRC32C)")

    print("[MICRO] 1. OSD performance stats")
    for it in range(args.iterations):
        print(f"[MICRO]   OSD perf iteration={it+1}/{args.iterations}")
        osd_r = run_osd_performance_test(args.ceph_conf, args.ceph_keyring, args.cluster_name, args.duration)
        if osd_r:
            results["osd_performance"].append(osd_r)

    print("[MICRO] 2. Erasure Coding vs Replicated")
    ec_r = run_ec_vs_replicated_test(args.ceph_conf, args.ceph_keyring, args.cluster_name, args.duration)
    if ec_r:
        results["ec_vs_replicated"] = ec_r

    print("[MICRO] 3. Compression algorithm comparison")
    comp_r = run_compression_test(args.ceph_conf, args.ceph_keyring, args.cluster_name, args.duration)
    if comp_r:
        results["compression_algorithms"] = comp_r

    print("[MICRO] 4. ARM64 CRC32C checksum performance")
    crc_r = run_arm64_crc32c_test(args.ceph_conf, args.ceph_keyring, args.cluster_name, args.duration)
    if crc_r:
        results["arm64_crc32c_checksum"] = crc_r

    print("[MICRO] 5. RBD cache configuration impact")
    cache_r = run_rbd_cache_test(args.ceph_conf, args.ceph_keyring, args.cluster_name)
    if cache_r:
        results["rbd_cache_configs"] = cache_r

    bench_output = {
        "benchmark": "ceph_micro",
        "description": "Ceph micro benchmarks: OSD perf, EC vs replicated, compression, ARM64 CRC32C, RBD cache",
        "reference": "Ceph documentation - https://docs.ceph.com/en/latest/",
        "timestamp": timestamp,
        "performance_metrics": {
            "osd_latency_ms": {"unit": "ms", "description": "Per-OSD commit/apply latency"},
            "throughput_ops_sec": {"unit": "ops/sec", "description": "Object operations per second"},
            "bandwidth_mb_sec": {"unit": "MB/sec", "description": "Data transfer bandwidth"},
            "compression_ratio": {"unit": "ratio", "description": "Data compression ratio"},
            "data_efficiency": {"unit": "percent", "description": "Storage space efficiency (k/(k+m) for EC, 1/n for replication)"},
            "iops": {"unit": "IOPS", "description": "RBD I/O operations per second"}
        },
        "dataset_info": {
            "name": "ceph_micro_generated",
            "size": "Various pools created dynamically for each test",
            "source": "Generated on ARM64 Ceph cluster"
        },
        "results": results
    }

    write_results_section(args.results_json, args.section, bench_output)

    print(f"[MICRO] Results saved to {args.results_json} section '{args.section}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
