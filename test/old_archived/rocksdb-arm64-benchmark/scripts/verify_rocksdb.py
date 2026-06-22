#!/usr/bin/env python3
import subprocess
import json
import os
import sys
import argparse
import platform
import datetime
import re


def run_cmd(cmd, timeout=60):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def verify_installation(db_bench_path, rocksdb_version, rocksdb_src, results_dir):
    print("[VERIFY] Starting RocksDB installation verification...")

    info = {}
    info["timestamp"] = datetime.datetime.now().isoformat()
    info["architecture"] = platform.machine()
    info["os"] = platform.system()
    info["kernel"] = platform.release()
    info["platform_detail"] = platform.platform()

    if platform.system() == "Darwin":
        cpu_model_out, _, _ = run_cmd("sysctl -n machdep.cpu.brand_string")
        cpu_cores_out, _, _ = run_cmd("sysctl -n hw.ncpu")
        mem_out, _, _ = run_cmd("sysctl -n hw.memsize")
        mem_mb = int(mem_out) // (1024 * 1024) if mem_out else 0
    else:
        cpu_model_out, _, _ = run_cmd("grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2 | xargs")
        if not cpu_model_out:
            cpu_model_out, _, _ = run_cmd("grep 'Hardware' /proc/cpuinfo | head -1 | cut -d: -f2 | xargs")
        cpu_cores_out, _, _ = run_cmd("nproc")
        mem_kb_out, _, _ = run_cmd("grep MemTotal /proc/meminfo | awk '{print $2}'")
        mem_mb = int(mem_kb_out) // 1024 if mem_kb_out else 0

    info["cpu_model"] = cpu_model_out.replace("\n", "").replace("\t", "")
    info["cpu_cores"] = int(cpu_cores_out) if cpu_cores_out else 0
    info["total_memory_mb"] = mem_mb
    info["total_memory_gb"] = round(mem_mb / 1024, 2) if mem_mb else 0

    print(f"[VERIFY] Architecture: {info['architecture']}")
    print(f"[VERIFY] CPU: {info['cpu_model']} ({info['cpu_cores']} cores)")
    print(f"[VERIFY] Memory: {info['total_memory_gb']} GB")

    db_bench_exists = os.path.isfile(db_bench_path) and os.access(db_bench_path, os.X_OK)
    info["db_bench_installed"] = db_bench_exists
    info["db_bench_path"] = db_bench_path
    print(f"[VERIFY] db_bench: {db_bench_exists} at {db_bench_path}")

    if db_bench_exists:
        help_out, help_err, help_rc = run_cmd(f"{db_bench_path} --help", timeout=30)
        info["db_bench_help_available"] = help_rc == 0

        version_from_help = ""
        for line in help_out.split("\n"):
            if "rocksdb" in line.lower() or "version" in line.lower():
                version_from_help = line.strip()
        info["rocksdb_version_from_help"] = version_from_help

        short_test_out, short_test_err, short_test_rc = run_cmd(
            f"{db_bench_path} --benchmarks=fillseq --num=100 --value_size=64 --threads=1 "
            f"--db=/tmp/rocksdb_verify_test --wal_dir=/tmp/rocksdb_verify_test_wal",
            timeout=60
        )
        info["db_bench_basic_run_success"] = short_test_rc == 0 or "fillseq" in short_test_out

        if short_test_out:
            for line in short_test_out.split("\n"):
                if "fillseq" in line and "micros/op" in line or "ops/sec" in line:
                    info["basic_fillseq_output"] = line.strip()
                    break

        import shutil
        shutil.rmtree("/tmp/rocksdb_verify_test", ignore_errors=True)
        shutil.rmtree("/tmp/rocksdb_verify_test_wal", ignore_errors=True)
    else:
        info["db_bench_basic_run_success"] = False

    info["rocksdb_version"] = rocksdb_version
    info["expected_version"] = rocksdb_version

    if os.path.isdir(rocksdb_src):
        cmake_cache = os.path.join(rocksdb_src, "CMakeCache.txt")
        if os.path.isfile(cmake_cache):
            cache_content, _, _ = run_cmd(f"grep -E 'CMAKE_SYSTEM_PROCESSOR|HAS_ARMV8_CRC|WITH_SNAPPY|WITH_LZ4|WITH_ZSTD|WITH_ZLIB|WITH_JEMALLOC|WITH_GFLAGS' {cmake_cache}")
            cmake_info = {}
            for line in cache_content.split("\n"):
                if "=" in line:
                    key, val = line.split("=", 1)
                    cmake_info[key.strip()] = val.strip()
            info["cmake_config"] = cmake_info
            info["arm64_crc_detected"] = cmake_info.get("HAS_ARMV8_CRC", "not found")

        makefile_rocksdb = os.path.join(rocksdb_src, "Makefile")
        if os.path.isfile(makefile_rocksdb):
            version_out, _, _ = run_cmd(f"grep -E '^ROCKSDB_MAJOR|^ROCKSDB_MINOR|^ROCKSDB_PATCH' {makefile_rocksdb}")
            version_parts = {}
            for line in version_out.split("\n"):
                if "=" in line:
                    key, val = line.split("=", 1)
                    version_parts[key.strip()] = val.strip()
            if version_parts:
                major = version_parts.get("ROCKSDB_MAJOR", "0")
                minor = version_parts.get("ROCKSDB_MINOR", "0")
                patch = version_parts.get("ROCKSDB_PATCH", "0")
                info["rocksdb_build_version"] = f"{major}.{minor}.{patch}"

        crc_arm64_path = os.path.join(rocksdb_src, "util", "crc32c_arm64.cc")
        info["arm64_crc32c_source_exists"] = os.path.isfile(crc_arm64_path)

        static_lib_path = os.path.join(rocksdb_src, "librocksdb.a")
        info["static_lib_exists"] = os.path.isfile(static_lib_path)
        if info["static_lib_exists"]:
            lib_size = os.path.getsize(static_lib_path)
            info["static_lib_size_mb"] = round(lib_size / (1024 * 1024), 2)

    info["compression_available"] = {}
    for comp in ["snappy", "lz4", "zstd", "zlib", "bzip2"]:
        comp_check, _, _ = run_cmd(f"pkg-config --exists lib{comp} && echo yes || echo no")
        if platform.system() == "Darwin":
            comp_check, _, _ = run_cmd(f"brew list {comp} 2>/dev/null && echo yes || echo no")
        info["compression_available"][comp] = comp_check == "yes"

    if platform.system() != "Darwin":
        neon_out, _, _ = run_cmd("grep -c 'asimd' /proc/cpuinfo 2>/dev/null || echo 0")
        info["neon_asimd_count"] = int(neon_out) if neon_out else 0
        crc_out, _, _ = run_cmd("grep -c 'crc32' /proc/cpuinfo 2>/dev/null || echo 0")
        info["arm64_crc_count"] = int(crc_out) if crc_out else 0
    else:
        info["neon_asimd_count"] = 1
        info["arm64_crc_count"] = 1

    info["jemalloc_available"] = False
    je_check, _, _ = run_cmd("ldconfig -p 2>/dev/null | grep -c jemalloc || echo 0")
    if platform.system() == "Darwin":
        je_check, _, _ = run_cmd("brew list jemalloc 2>/dev/null && echo 1 || echo 0")
    if je_check and int(je_check) > 0:
        info["jemalloc_available"] = True

    info["io_uring_available"] = False
    if platform.system() == "Linux":
        io_uring_check, _, _ = run_cmd("grep -c 'io_uring' /proc/kallsyms 2>/dev/null || echo 0")
        if io_uring_check and int(io_uring_check) > 0:
            info["io_uring_available"] = True

    output_path = os.path.join(results_dir, "version_info.json")
    with open(output_path, "w") as f:
        json.dump(info, f, indent=2)

    print(f"[VERIFY] Version info saved to: {output_path}")

    checks_passed = 0
    checks_total = 5
    if info["architecture"] in ("aarch64", "arm64"):
        checks_passed += 1
        print("[VERIFY] PASS: ARM64 architecture confirmed")
    else:
        print("[VERIFY] WARN: Not on ARM64 architecture")
    if info["db_bench_installed"]:
        checks_passed += 1
        print("[VERIFY] PASS: db_bench binary exists and is executable")
    else:
        print("[VERIFY] FAIL: db_bench binary not found")
    if info.get("db_bench_basic_run_success"):
        checks_passed += 1
        print("[VERIFY] PASS: db_bench basic fillseq runs successfully")
    else:
        print("[VERIFY] FAIL: db_bench basic run failed")
    if info.get("arm64_crc32c_source_exists"):
        checks_passed += 1
        print("[VERIFY] PASS: ARM64 CRC32C source code exists")
    else:
        print("[VERIFY] WARN: ARM64 CRC32C source not found")
    if info.get("static_lib_exists"):
        checks_passed += 1
        print("[VERIFY] PASS: RocksDB static library built")
    else:
        print("[VERIFY] WARN: RocksDB static library not found")

    print(f"[VERIFY] Verification result: {checks_passed}/{checks_total} checks passed")
    return checks_passed >= 3


def main():
    parser = argparse.ArgumentParser(description="Verify RocksDB installation")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--db-bench", required=True)
    parser.add_argument("--rocksdb-version", required=True)
    parser.add_argument("--rocksdb-src", required=True)
    args = parser.parse_args()

    ok = verify_installation(args.db_bench, args.rocksdb_version, args.rocksdb_src, args.results_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()