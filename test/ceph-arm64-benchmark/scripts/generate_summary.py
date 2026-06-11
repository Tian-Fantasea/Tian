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


def format_metric(value, unit="", precision=2):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f} {unit}"
    if isinstance(value, int):
        return f"{value} {unit}"
    return f"{value} {unit}"


def main():
    parser = argparse.ArgumentParser(description="Generate text summary for Ceph benchmarks")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--software-name", default="ceph")
    parser.add_argument("--software-version", default="19.2.0")
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    all_results = load_json_file(os.path.join(args.results_dir, "all_results.json"))
    if not all_results:
        print("[SUMMARY] No aggregated results found")
        return 1

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    env = all_results.get("environment", {})
    key_metrics = all_results.get("key_metrics", {})
    benchmarks = all_results.get("benchmarks", {})

    lines = []
    lines.append("=" * 80)
    lines.append(f"  Ceph ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append(f"  Software:      Ceph v{all_results.get('software_version', args.software_version)}")
    lines.append(f"  Date:          {timestamp}")
    lines.append(f"  Architecture:  {env.get('architecture', 'unknown')}")
    lines.append(f"  CPU:           {env.get('cpu_model', 'unknown')}")
    lines.append(f"  Cores:         {env.get('cores', 'unknown')}")
    lines.append(f"  Memory:        {format_metric(env.get('memory_mb', 0), 'MB', 0)}")
    lines.append(f"  OS:            {env.get('os', 'unknown')}")
    lines.append(f"  Kernel:        {env.get('kernel', 'unknown')}")
    lines.append(f"  Cluster Health: {env.get('cluster_health', 'unknown')}")
    lines.append(f"  OSD Count:     {env.get('osd_count', 0)}")
    lines.append(f"  Mon Count:     {env.get('mon_count', 0)}")
    arm64 = env.get("arm64_features", {})
    if arm64:
        lines.append(f"  ARM64 NEON:    {arm64.get('neon_available', 'unknown')}")
        lines.append(f"  ARM64 CRC32C:  {arm64.get('crc32c_available', 'unknown')}")
    lines.append("=" * 80)

    lines.append("")
    lines.append("  KEY PERFORMANCE METRICS")
    lines.append("-" * 80)
    for metric_name, value in key_metrics.items():
        display_name = metric_name.replace("_", " ").title()
        if isinstance(value, float):
            lines.append(f"  {display_name:40s} : {value:.2f}")
        elif isinstance(value, int):
            lines.append(f"  {display_name:40s} : {value}")
        else:
            lines.append(f"  {display_name:40s} : {value}")
    lines.append("-" * 80)

    if "rados" in benchmarks:
        lines.append("")
        lines.append("  RADOS OBJECT STORAGE BENCHMARKS")
        lines.append("-" * 80)
        rados_r = benchmarks["rados"].get("results", {})

        obj_sweep = rados_r.get("object_size_sweep", [])
        if obj_sweep:
            lines.append("  Write Throughput by Object Size:")
            for e in obj_sweep:
                lines.append(f"    obj_size={e.get('object_size', '?'):>8s}  "
                             f"ops={format_metric(e.get('avg_throughput_ops_sec', 0), 'ops/sec'):.20s}  "
                             f"bw={format_metric(e.get('avg_bandwidth_mb_sec', 0), 'MB/s'):.20s}  "
                             f"lat={format_metric(e.get('avg_latency_ms', 0), 'ms')}")

        conc = rados_r.get("concurrency_scaling", [])
        if conc:
            lines.append("  Write Concurrency Scaling (4M objects):")
            for e in conc:
                lines.append(f"    conc={e.get('concurrency', 0):>4d}  "
                             f"ops={format_metric(e.get('avg_throughput_ops_sec', 0), 'ops/sec'):.20s}  "
                             f"bw={format_metric(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}")

        seq = rados_r.get("sequential_read", [])
        if seq:
            lines.append("  Sequential Read (4M objects):")
            for e in seq:
                lines.append(f"    ops={format_metric(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}  "
                             f"bw={format_metric(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}")

        rand = rados_r.get("random_read", [])
        if rand:
            lines.append("  Random Read (4M objects):")
            for e in rand:
                lines.append(f"    ops={format_metric(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}  "
                             f"bw={format_metric(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}")

    if "rbd" in benchmarks:
        lines.append("")
        lines.append("  RBD BLOCK STORAGE BENCHMARKS")
        lines.append("-" * 80)
        rbd_r = benchmarks["rbd"].get("results", {})

        seq_rw = rbd_r.get("sequential_read_write", [])
        if seq_rw:
            lines.append("  Sequential R/W:")
            for e in seq_rw:
                lines.append(f"    {e.get('rw', '?'):>20s} bs={e.get('block_size', '?'):>6s}  "
                             f"iops={format_metric(e.get('avg_iops', 0), 'IOPS')}  "
                             f"bw={format_metric(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}")

        rand_rw = rbd_r.get("random_read_write", [])
        if rand_rw:
            lines.append("  Random R/W:")
            for e in rand_rw:
                lines.append(f"    {e.get('rw', '?'):>20s} bs={e.get('block_size', '?'):>6s}  "
                             f"iops={format_metric(e.get('avg_iops', 0), 'IOPS')}  "
                             f"lat={format_metric(e.get('avg_latency_ms', 0), 'ms')}")

        iodepth = rbd_r.get("iodepth_scaling", [])
        if iodepth:
            lines.append("  IODEPTH Scaling (random read, 4K):")
            for e in iodepth:
                lines.append(f"    iodepth={e.get('iodepth', 0):>4d}  "
                             f"iops={format_metric(e.get('avg_iops', 0), 'IOPS')}  "
                             f"lat={format_metric(e.get('avg_latency_ms', 0), 'ms')}")

    if "cephfs" in benchmarks:
        lines.append("")
        lines.append("  CephFS FILE STORAGE BENCHMARKS")
        lines.append("-" * 80)
        cephfs_r = benchmarks["cephfs"].get("results", {})

        meta = cephfs_r.get("metadata_operations", [])
        if meta:
            lines.append("  Metadata Operations:")
            for e in meta:
                lines.append(f"    mkdir={format_metric(e.get('mkdir_ops_sec', 0), 'ops/sec'):.20s}  "
                             f"stat={format_metric(e.get('stat_ops_sec', 0), 'ops/sec'):.20s}  "
                             f"ls={format_metric(e.get('ls_ops_sec', 0), 'ops/sec'):.20s}  "
                             f"rmdir={format_metric(e.get('rmdir_ops_sec', 0), 'ops/sec')}")

        sf = cephfs_r.get("small_file_operations", [])
        if sf:
            lines.append("  Small File Operations (4K files):")
            for e in sf:
                lines.append(f"    create={format_metric(e.get('small_file_create_ops_sec', 0), 'ops/sec'):.20s}  "
                             f"read={format_metric(e.get('small_file_read_ops_sec', 0), 'ops/sec'):.20s}  "
                             f"delete={format_metric(e.get('small_file_delete_ops_sec', 0), 'ops/sec')}")

    if "micro" in benchmarks:
        lines.append("")
        lines.append("  MICRO BENCHMARKS")
        lines.append("-" * 80)
        micro_r = benchmarks["micro"].get("results", {})

        ec = micro_r.get("ec_vs_replicated", [])
        if ec:
            lines.append("  EC vs Replicated:")
            for e in ec:
                label = e.get("ec_profile", "?")
                ops = e.get("avg_throughput_ops_sec", "N/A")
                bw = e.get("avg_bandwidth_mb_sec", "N/A")
                eff = e.get("data_efficiency", "?")
                lines.append(f"    {label:>20s}  ops={ops}  bw={bw}  efficiency={eff}")

        comp = micro_r.get("compression_algorithms", [])
        if comp:
            lines.append("  Compression Algorithms:")
            for e in comp:
                algo = e.get("compression_algorithm", "?")
                ops = e.get("avg_throughput_ops_sec", "N/A")
                bw = e.get("avg_bandwidth_mb_sec", "N/A")
                lines.append(f"    {algo:>10s}  ops={ops}  bw={bw}")

        crc = micro_r.get("arm64_crc32c_checksum", {})
        if crc:
            lines.append("  ARM64 CRC32C:")
            lines.append(f"    hardware_crc32c={crc.get('arm64_crc32c_hardware', 'unknown')}")
            lines.append(f"    bluestore_checksum={crc.get('bluestore_checksum_verify', 'unknown')}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  ARM64 OPTIMIZATION HIGHLIGHTS")
    lines.append("=" * 80)
    arm64_opts = env.get("arm64_ceph_optimizations", {})
    if arm64_opts:
        lines.append(f"  ARM64 CRC32C in BlueStore:   {arm64_opts.get('arm64_crc32c_in_bluestore', 'unknown')}")
        lines.append(f"  ARM64 CRC32C detected:       {arm64_opts.get('crc32c_arm64_detected', 'unknown')}")
        lines.append(f"  NEON compression possible:   {arm64_opts.get('neon_compression_possible', 'unknown')}")
        lines.append(f"  BlueStore RocksDB ARM64:     {arm64_opts.get('bluestore_rocksdb_arm64', 'unknown')}")
    else:
        lines.append("  (ARM64 optimization data not available)")
    lines.append("=" * 80)

    output_file = os.path.join(args.results_dir, "benchmark_summary.txt")
    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Text summary saved to {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())