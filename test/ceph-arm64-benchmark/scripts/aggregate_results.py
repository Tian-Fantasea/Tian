#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time


def load_json_file(filepath):
    if not os.path.isfile(filepath):
        return None
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def main():
    parser = argparse.ArgumentParser(description="Aggregate Ceph benchmark JSON results")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--software-name", default="ceph")
    parser.add_argument("--software-version", default="19.2.0")
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    version_info = load_json_file(os.path.join(args.results_dir, "version_info.json"))
    rados_data = load_json_file(os.path.join(args.results_dir, "benchmark_rados.json"))
    rbd_data = load_json_file(os.path.join(args.results_dir, "benchmark_rbd.json"))
    cephfs_data = load_json_file(os.path.join(args.results_dir, "benchmark_cephfs.json"))
    micro_data = load_json_file(os.path.join(args.results_dir, "micro_benchmark.json"))

    aggregated = {
        "software_name": args.software_name,
        "software_version": args.software_version,
        "timestamp": timestamp,
        "environment": version_info if version_info else {
            "architecture": "unknown",
            "software_version": args.software_version
        },
        "benchmarks": {}
    }

    if rados_data:
        aggregated["benchmarks"]["rados"] = rados_data

    if rbd_data:
        aggregated["benchmarks"]["rbd"] = rbd_data

    if cephfs_data:
        aggregated["benchmarks"]["cephfs"] = cephfs_data

    if micro_data:
        aggregated["benchmarks"]["micro"] = micro_data

    key_metrics = {}

    if rados_data:
        results_r = rados_data.get("results", {})
        obj_sweep = results_r.get("object_size_sweep", [])
        if obj_sweep:
            max_write_bw = max(
                [e.get("avg_bandwidth_mb_sec", 0) for e in obj_sweep if e.get("avg_bandwidth_mb_sec", 0) > 0],
                default=0
            )
            max_write_ops = max(
                [e.get("avg_throughput_ops_sec", 0) for e in obj_sweep if e.get("avg_throughput_ops_sec", 0) > 0],
                default=0
            )
            key_metrics["rados_max_write_bw_mb_sec"] = max_write_bw
            key_metrics["rados_max_write_ops_sec"] = max_write_ops

        conc_scaling = results_r.get("concurrency_scaling", [])
        if conc_scaling:
            max_conc_bw = max(
                [e.get("avg_bandwidth_mb_sec", 0) for e in conc_scaling],
                default=0
            )
            key_metrics["rados_max_concurrency_bw_mb_sec"] = max_conc_bw

        seq_read = results_r.get("sequential_read", [])
        if seq_read:
            avg_seq_bw = sum([e.get("avg_bandwidth_mb_sec", 0) for e in seq_read]) / len(seq_read) if seq_read else 0
            key_metrics["rados_seq_read_bw_mb_sec"] = avg_seq_bw

        rand_read = results_r.get("random_read", [])
        if rand_read:
            avg_rand_ops = sum([e.get("avg_throughput_ops_sec", 0) for e in rand_read]) / len(rand_read) if rand_read else 0
            key_metrics["rados_rand_read_ops_sec"] = avg_rand_ops

    if rbd_data:
        results_b = rbd_data.get("results", {})
        rand_rw = results_b.get("random_read_write", [])
        if rand_rw:
            max_rand_iops = max(
                [e.get("avg_iops", 0) for e in rand_rw if e.get("avg_iops", 0) > 0],
                default=0
            )
            key_metrics["rbd_max_random_iops"] = max_rand_iops

        iodepth_scale = results_b.get("iodepth_scaling", [])
        if iodepth_scale:
            max_iodepth_iops = max(
                [e.get("avg_iops", 0) for e in iodepth_scale],
                default=0
            )
            key_metrics["rbd_max_iodepth_iops"] = max_iodepth_iops

        seq_rw = results_b.get("sequential_read_write", [])
        if seq_rw:
            max_seq_bw = max(
                [e.get("avg_bandwidth_mb_sec", 0) for e in seq_rw],
                default=0
            )
            key_metrics["rbd_max_seq_bw_mb_sec"] = max_seq_bw

    if cephfs_data:
        results_f = cephfs_data.get("results", {})
        meta_ops = results_f.get("metadata_operations", [])
        if meta_ops:
            avg_mkdir = sum([e.get("mkdir_ops_sec", 0) for e in meta_ops]) / len(meta_ops) if meta_ops else 0
            avg_stat = sum([e.get("stat_ops_sec", 0) for e in meta_ops]) / len(meta_ops) if meta_ops else 0
            key_metrics["cephfs_mkdir_ops_sec"] = avg_mkdir
            key_metrics["cephfs_stat_ops_sec"] = avg_stat

        small_files = results_f.get("small_file_operations", [])
        if small_files:
            avg_create = sum([e.get("small_file_create_ops_sec", 0) for e in small_files]) / len(small_files) if small_files else 0
            key_metrics["cephfs_small_file_create_ops_sec"] = avg_create

    if micro_data:
        results_m = micro_data.get("results", {})
        ec_data = results_m.get("ec_vs_replicated", [])
        if ec_data:
            key_metrics["ec_profiles_tested"] = len(ec_data)

        comp_data = results_m.get("compression_algorithms", [])
        if comp_data:
            key_metrics["compression_algos_tested"] = len(comp_data)

        crc_data = results_m.get("arm64_crc32c_checksum", {})
        if crc_data:
            key_metrics["arm64_crc32c_available"] = crc_data.get("arm64_crc32c_hardware", False)

    aggregated["key_metrics"] = key_metrics

    output_file = os.path.join(args.results_dir, "all_results.json")
    with open(output_file, "w") as f:
        json.dump(aggregated, f, indent=2)

    print(f"[AGGREGATE] Aggregated results saved to {output_file}")
    print(f"[AGGREGATE] Key metrics: {len(key_metrics)} metrics extracted")
    for k, v in key_metrics.items():
        print(f"[AGGREGATE]   {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())