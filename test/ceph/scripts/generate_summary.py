#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time


def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def format_metric(value, unit="", precision=2):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f} {unit}"
    if isinstance(value, int):
        return f"{value} {unit}"
    return f"{value} {unit}"


def compute_pass_fail(data, thresholds):
    results = {}
    vi = data.get("version_info", {})
    if vi.get("cluster_health") in ("HEALTH_OK", "HEALTH_WARN"):
        results["cluster_health"] = "PASS"
    else:
        results["cluster_health"] = "FAIL"

    rados = data.get("rados_benchmark", {})
    rados_r = rados.get("results", {})
    obj_sweep = rados_r.get("object_size_sweep", [])
    if obj_sweep:
        max_ops = max([e.get("avg_throughput_ops_sec", 0) or 0 for e in obj_sweep], default=0)
        results["rados_write_throughput"] = "PASS" if max_ops >= thresholds.get("minimum_throughput", 1000) else "FAIL"
    else:
        results["rados_write_throughput"] = "N/A"

    rbd = data.get("rbd_benchmark", {})
    rbd_r = rbd.get("results", {})
    rand_rw = rbd_r.get("random_read_write", [])
    if rand_rw:
        max_iops = max([e.get("avg_iops", 0) or 0 for e in rand_rw], default=0)
        results["rbd_random_iops"] = "PASS" if max_iops >= thresholds.get("minimum_iops", 500) else "FAIL"
    else:
        results["rbd_random_iops"] = "N/A"

    cephfs = data.get("cephfs_benchmark", {})
    cephfs_r = cephfs.get("results", {})
    meta = cephfs_r.get("metadata_operations", [])
    if meta:
        avg_mkdir = sum([e.get("mkdir_ops_sec", 0) or 0 for e in meta]) / len(meta) if meta else 0
        results["cephfs_metadata"] = "PASS" if avg_mkdir >= 10 else "FAIL"
    else:
        results["cephfs_metadata"] = "N/A"

    micro = data.get("micro_benchmark", {})
    micro_r = micro.get("results", {})
    crc = micro_r.get("arm64_crc32c_checksum", {})
    if crc:
        hw = crc.get("arm64_crc32c_hardware", False)
        results["arm64_crc32c"] = "PASS" if hw else "FAIL"
    else:
        results["arm64_crc32c"] = "N/A"

    return results


def main():
    parser = argparse.ArgumentParser(description="Generate text summary for Ceph benchmarks")
    parser.add_argument("--input", required=True, help="Path to results.json")
    parser.add_argument("--output", required=True, help="Path to results.txt")
    args = parser.parse_args()

    data = load_or_create_json(args.input)
    if not data:
        with open(args.output, "w") as f:
            f.write("ERROR: No results.json found\n")
        return 1

    thresholds = {
        "minimum_throughput": 1000,
        "minimum_iops": 500,
        "maximum_latency_ms": 50,
    }
    pass_fail = compute_pass_fail(data, thresholds)

    vi = data.get("version_info", {})
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    lines = []
    lines.append("=" * 80)
    lines.append("  Ceph ARM64 Performance Benchmark Summary")
    lines.append("=" * 80)
    lines.append(f"  Software:      Ceph v{data.get('version', 'unknown')}")
    lines.append(f"  Date:          {timestamp}")
    lines.append(f"  Architecture:  {vi.get('architecture', 'unknown')}")
    lines.append(f"  CPU:           {vi.get('cpu_model', 'unknown')}")
    lines.append(f"  Cores:         {vi.get('cores', 'unknown')}")
    lines.append(f"  Memory:        {format_metric(vi.get('memory_mb', 0), 'MB', 0)}")
    lines.append(f"  OS:            {vi.get('os', 'unknown')}")
    lines.append(f"  Kernel:        {vi.get('kernel', 'unknown')}")
    lines.append(f"  Cluster Health: {vi.get('cluster_health', 'unknown')}")
    lines.append(f"  OSD Count:     {vi.get('osd_count', 0)}")
    lines.append(f"  Mon Count:     {vi.get('mon_count', 0)}")
    arm64 = vi.get("arm64_features", {})
    if arm64:
        lines.append(f"  ARM64 NEON:    {arm64.get('neon_available', 'unknown')}")
        lines.append(f"  ARM64 CRC32C:  {arm64.get('crc32c_available', 'unknown')}")
    lines.append("=" * 80)

    lines.append("")
    lines.append("  PASS/FAIL STATUS")
    lines.append("-" * 80)
    for name, status in pass_fail.items():
        display = name.replace("_", " ").title()
        lines.append(f"  {display:40s} : {status}")
    lines.append("-" * 80)

    rados = data.get("rados_benchmark", {})
    if rados:
        lines.append("")
        lines.append("  RADOS OBJECT STORAGE BENCHMARKS")
        lines.append("-" * 80)
        rados_r = rados.get("results", {})
        obj_sweep = rados_r.get("object_size_sweep", [])
        if obj_sweep:
            lines.append("  Write Throughput by Object Size:")
            for e in obj_sweep:
                lines.append(f"    obj_size={e.get('object_size', '?'):>8s}  "
                             f"ops={format_metric(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}  "
                             f"bw={format_metric(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}  "
                             f"lat={format_metric(e.get('avg_latency_ms', 0), 'ms')}")

        conc = rados_r.get("concurrency_scaling", [])
        if conc:
            lines.append("  Concurrency Scaling (4M objects):")
            for e in conc:
                lines.append(f"    conc={e.get('concurrency', 0):>4d}  "
                             f"ops={format_metric(e.get('avg_throughput_ops_sec', 0), 'ops/sec')}  "
                             f"bw={format_metric(e.get('avg_bandwidth_mb_sec', 0), 'MB/s')}")

    rbd = data.get("rbd_benchmark", {})
    if rbd:
        lines.append("")
        lines.append("  RBD BLOCK STORAGE BENCHMARKS")
        lines.append("-" * 80)
        rbd_r = rbd.get("results", {})
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

    cephfs = data.get("cephfs_benchmark", {})
    if cephfs:
        lines.append("")
        lines.append("  CephFS FILE STORAGE BENCHMARKS")
        lines.append("-" * 80)
        cephfs_r = cephfs.get("results", {})
        meta = cephfs_r.get("metadata_operations", [])
        if meta:
            lines.append("  Metadata Operations:")
            for e in meta:
                lines.append(f"    mkdir={format_metric(e.get('mkdir_ops_sec', 0), 'ops/sec')}  "
                             f"stat={format_metric(e.get('stat_ops_sec', 0), 'ops/sec')}  "
                             f"ls={format_metric(e.get('ls_ops_sec', 0), 'ops/sec')}  "
                             f"rmdir={format_metric(e.get('rmdir_ops_sec', 0), 'ops/sec')}")

    micro = data.get("micro_benchmark", {})
    if micro:
        lines.append("")
        lines.append("  MICRO BENCHMARKS")
        lines.append("-" * 80)
        micro_r = micro.get("results", {})
        ec = micro_r.get("ec_vs_replicated", [])
        if ec:
            lines.append("  EC vs Replicated:")
            for e in ec:
                lines.append(f"    {e.get('ec_profile', '?'):>20s}  ops={e.get('avg_throughput_ops_sec', 'N/A')}  bw={e.get('avg_bandwidth_mb_sec', 'N/A')}  efficiency={e.get('data_efficiency', '?')}")

        comp = micro_r.get("compression_algorithms", [])
        if comp:
            lines.append("  Compression Algorithms:")
            for e in comp:
                lines.append(f"    {e.get('compression_algorithm', '?'):>10s}  ops={e.get('avg_throughput_ops_sec', 'N/A')}  bw={e.get('avg_bandwidth_mb_sec', 'N/A')}")

        crc = micro_r.get("arm64_crc32c_checksum", {})
        if crc:
            lines.append("  ARM64 CRC32C:")
            lines.append(f"    hardware_crc32c={crc.get('arm64_crc32c_hardware', 'unknown')}")
            lines.append(f"    bluestore_checksum={crc.get('bluestore_checksum_verify', 'unknown')}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  ARM64 OPTIMIZATION HIGHLIGHTS")
    lines.append("=" * 80)
    arm64 = vi.get("arm64_features", {})
    if arm64:
        lines.append(f"  ARM64 Architecture:        {arm64.get('is_arm64', 'unknown')}")
        lines.append(f"  NEON/SIMD Available:       {arm64.get('neon_available', 'unknown')}")
        lines.append(f"  ARM64 CRC32C Available:    {arm64.get('crc32c_available', 'unknown')}")
    else:
        lines.append("  (ARM64 optimization data not available)")
    lines.append("=" * 80)

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"[SUMMARY] Text summary saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
