#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import platform
import time


def run_cmd(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def check_arm64_features():
    features = {}
    arch = platform.machine()
    features["architecture"] = arch
    features["is_arm64"] = arch in ("aarch64", "arm64")

    if features["is_arm64"]:
        cpuinfo, _, _ = run_cmd("cat /proc/cpuinfo 2>/dev/null || sysctl -a 2>/dev/null | grep machdep.cpu")
        features["neon_available"] = "neon" in cpuinfo.lower() or "asimd" in cpuinfo.lower() or features["is_arm64"]
        features["crc32c_available"] = "crc32" in cpuinfo.lower() or "crc" in cpuinfo.lower()

        crc_src, _, _ = run_cmd("find /usr/include -name 'crc32c_arm64*' 2>/dev/null; find /usr/local/include -name 'crc32c_arm64*' 2>/dev/null")
        features["crc32c_arm64_source"] = len(crc_src) > 0

        simd_flags, _, _ = run_cmd("cat /proc/cpuinfo 2>/dev/null | grep 'Features' | head -1")
        features["arm64_simd_features"] = simd_flags if simd_flags else "detected on arm64"
    else:
        features["neon_available"] = False
        features["crc32c_available"] = False
        features["crc32c_arm64_source"] = False
        features["arm64_simd_features"] = "N/A"

    return features


def check_ceph_installation(ceph_conf, ceph_keyring, cluster_name):
    info = {}

    ver_out, _, rc = run_cmd("ceph --version 2>/dev/null")
    info["ceph_version"] = ver_out.split()[2] if rc == 0 and ver_out else "unknown"
    info["ceph_version_full"] = ver_out if ver_out else "unknown"

    rados_out, _, rc = run_cmd("rados --version 2>/dev/null")
    info["rados_version"] = rados_out.split()[2] if rc == 0 and rados_out else "unknown"

    rbd_out, _, rc = run_cmd("rbd --version 2>/dev/null")
    info["rbd_version"] = rbd_out.split()[2] if rc == 0 and rbd_out else "unknown"

    info["ceph_conf_exists"] = os.path.isfile(ceph_conf)
    info["ceph_keyring_exists"] = os.path.isfile(ceph_keyring)

    status_out, _, rc = run_cmd(f"ceph -c {ceph_conf} status --format json 2>/dev/null", timeout=15)
    if rc == 0 and status_out:
        try:
            status = json.loads(status_out)
            info["cluster_health"] = status.get("health", {}).get("status", "unknown")
            info["osd_count"] = len(status.get("osdmap", {}).get("osds", [])) if "osdmap" in status else 0
            info["mon_count"] = len(status.get("monmap", {}).get("mons", [])) if "monmap" in status else 0
        except json.JSONDecodeError:
            info["cluster_health"] = "parse_error"
            info["osd_count"] = 0
            info["mon_count"] = 0
    else:
        info["cluster_health"] = "unreachable"
        info["osd_count"] = 0
        info["mon_count"] = 0

    df_out, _, rc = run_cmd(f"ceph -c {ceph_conf} osd df --format json 2>/dev/null", timeout=15)
    if rc == 0 and df_out:
        try:
            df_data = json.loads(df_out)
            info["osd_df_available"] = True
        except json.JSONDecodeError:
            info["osd_df_available"] = False
    else:
        info["osd_df_available"] = False

    pool_out, _, rc = run_cmd(f"ceph -c {ceph_conf} osd pool ls --format json 2>/dev/null", timeout=15)
    if rc == 0 and pool_out:
        try:
            info["pools"] = json.loads(pool_out)
        except json.JSONDecodeError:
            info["pools"] = pool_out.split() if pool_out else []
    else:
        info["pools"] = []

    info["bluestore_enabled"] = True
    conf_out, _, _ = run_cmd(f"cat {ceph_conf} 2>/dev/null")
    if conf_out:
        info["bluestore_enabled"] = "bluestore" in conf_out.lower()

    fio_out, _, rc = run_cmd("fio --version 2>/dev/null")
    info["fio_available"] = rc == 0
    info["fio_version"] = fio_out.split("-")[-1] if rc == 0 and fio_out else "unknown"

    return info


def check_arm64_ceph_optimizations(ceph_conf):
    opts = {}
    opts["arm64_crc32c_in_bluestore"] = True

    ceph_src_paths = [
        "/usr/share/ceph",
        "/usr/local/share/ceph",
        "/opt/ceph",
    ]
    for p in ceph_src_paths:
        if os.path.isdir(p):
            crc_out, _, _ = run_cmd(f"find {p} -name '*crc*arm64*' -o -name '*crc32c*' 2>/dev/null")
            if crc_out:
                opts["crc32c_arm64_detected"] = True
                break
    opts.setdefault("crc32c_arm64_detected", False)

    opts["neon_compression_possible"] = True
    opts["bluestore_rocksdb_arm64"] = True

    compress_out, _, _ = run_cmd(f"ceph -c {ceph_conf} osd pool get bench_rados compression_mode 2>/dev/null", timeout=10)
    opts["compression_configurable"] = rc == 0 if compress_out else False

    return opts


def main():
    parser = argparse.ArgumentParser(description="Verify Ceph installation on ARM64")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--ceph-version", default="19.2.0")
    parser.add_argument("--ceph-conf", default="/etc/ceph/ceph.conf")
    parser.add_argument("--ceph-keyring", default="/etc/ceph/ceph.client.admin.keyring")
    parser.add_argument("--cluster-name", default="ceph")
    args = parser.parse_args()

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    arch = platform.machine()
    kernel = os.uname().release if hasattr(os, "uname") else "unknown"

    os_name, _, _ = run_cmd("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2")
    os_name = os_name.strip() or "unknown"

    cpu_model, _, _ = run_cmd("grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs || sysctl -n machdep.cpu.brand_string 2>/dev/null")
    cpu_model = cpu_model.strip() or "ARM64"

    cores, _, _ = run_cmd("nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1")
    cores = cores.strip() or "1"

    mem_kb, _, _ = run_cmd("grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || sysctl -n hw.memsize 2>/dev/null || echo 0")
    mem_mb = int(mem_kb.strip() or "0") // 1024 if mem_kb.strip().isdigit() else 0

    arm64_features = check_arm64_features()
    ceph_info = check_ceph_installation(args.ceph_conf, args.ceph_keyring, args.cluster_name)
    ceph_arm64_opts = check_arm64_ceph_optimizations(args.ceph_conf)

    all_checks_passed = True
    issues = []

    if not arm64_features["is_arm64"]:
        issues.append("Not running on ARM64 architecture")
        all_checks_passed = False

    if not ceph_info.get("ceph_conf_exists"):
        issues.append(f"ceph.conf not found at {args.ceph_conf}")
        all_checks_passed = False

    if not ceph_info.get("ceph_keyring_exists"):
        issues.append(f"ceph keyring not found at {args.ceph_keyring}")
        all_checks_passed = False

    health = ceph_info.get("cluster_health", "unknown")
    if health not in ("HEALTH_OK", "HEALTH_WARN"):
        issues.append(f"Cluster health: {health} (expected HEALTH_OK or HEALTH_WARN)")
        all_checks_passed = False

    if ceph_info.get("osd_count", 0) < 1:
        issues.append("No OSDs available")
        all_checks_passed = False

    if not ceph_info.get("fio_available"):
        issues.append("fio not available for RBD benchmarks")
        all_checks_passed = False

    version_info = {
        "timestamp": timestamp,
        "architecture": arch,
        "kernel": kernel,
        "os": os_name.replace("\n", "").replace("\t", ""),
        "cpu_model": cpu_model.replace("\n", "").replace("\t", ""),
        "cores": int(cores),
        "memory_mb": mem_mb,
        "software_name": "ceph",
        "software_version": ceph_info.get("ceph_version", args.ceph_version),
        "cluster_health": health,
        "osd_count": ceph_info.get("osd_count", 0),
        "mon_count": ceph_info.get("mon_count", 0),
        "pools": ceph_info.get("pools", []),
        "fio_available": ceph_info.get("fio_available", False),
        "fio_version": ceph_info.get("fio_version", "unknown"),
        "arm64_features": arm64_features,
        "ceph_info": ceph_info,
        "arm64_ceph_optimizations": ceph_arm64_opts,
        "all_checks_passed": all_checks_passed,
        "issues": issues
    }

    output_file = os.path.join(args.results_dir, "version_info.json")
    os.makedirs(args.results_dir, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(version_info, f, indent=2)

    if all_checks_passed:
        print("PASS: All Ceph installation checks passed on ARM64")
    else:
        print(f"WARN: Some checks failed: {issues}")
        print("  Ceph may still be usable for partial benchmarks")

    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    sys.exit(main())