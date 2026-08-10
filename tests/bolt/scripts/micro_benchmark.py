#!/usr/bin/env python3
"""Bolt micro: build characteristics + library analysis on ARM64."""
import sys
import os
import json
import glob
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_bolt import find_library, find_benchmark_binaries, run_binary_and_parse


def bench_library_analysis(build_dir):
    """Analyze the built library: size, symbols, sections."""
    results = {}
    lib_path = find_library(build_dir)
    if not lib_path:
        return {"error": "library not found"}

    results["lib_path"] = lib_path
    results["lib_size_bytes"] = os.path.getsize(lib_path)

    # Count symbols
    try:
        nm_result = subprocess.run(
            ["nm", lib_path], capture_output=True, text=True, timeout=30,
        )
        if nm_result.returncode == 0:
            lines = nm_result.stdout.strip().split("\n")
            results["symbol_count"] = len(lines)
            # Count defined (T) vs undefined (U) symbols
            t_count = sum(1 for l in lines if " T " in l or " t " in l)
            u_count = sum(1 for l in lines if " U " in l)
            results["defined_symbols"] = t_count
            results["undefined_symbols"] = u_count
    except Exception:
        pass

    # Readelf sections
    try:
        readelf_result = subprocess.run(
            ["readelf", "-S", lib_path], capture_output=True, text=True, timeout=30,
        )
        if readelf_result.returncode == 0:
            section_lines = [l for l in readelf_result.stdout.split("\n") if ".text" in l or ".data" in l or ".rodata" in l]
            results["section_count"] = len(readelf_result.stdout.strip().split("\n"))
    except Exception:
        pass

    return results


def bench_binary_scan(build_dir):
    """Scan for all executable binaries in build dir."""
    binaries = find_benchmark_binaries(build_dir)
    results = {"total_binaries": len(binaries)}
    if binaries:
        results["binary_names"] = [os.path.basename(b) for b in binaries[:20]]
        # Try running each and count pass/fail
        passed = 0
        failed = 0
        for binary in binaries[:10]:
            parsed = run_binary_and_parse(binary, timeout=60)
            if parsed.get("passed"):
                passed += 1
            else:
                failed += 1
        results["binaries_tested"] = min(len(binaries), 10)
        results["binaries_passed"] = passed
        results["binaries_failed"] = failed
    return results


def main():
    if len(sys.argv) < 4:
        print("Usage: micro_benchmark.py <src_dir> <build_dir> <output_file>")
        sys.exit(1)
    src_dir = sys.argv[1]
    build_dir = sys.argv[2]
    output_file = sys.argv[3]
    version_str = os.environ.get("SOFTWARE_VERSION", "main")

    if not os.path.isdir(build_dir):
        print(f"[MICRO] Build dir not found: {build_dir}")
        sys.exit(1)

    print("[MICRO] Running library_analysis...")
    lib_results = bench_library_analysis(build_dir)
    print(f"[MICRO] Library: {lib_results.get('lib_size_bytes', 'N/A')} bytes, {lib_results.get('symbol_count', 'N/A')} symbols")

    print("[MICRO] Running binary_scan...")
    bin_results = bench_binary_scan(build_dir)
    print(f"[MICRO] Binaries: {bin_results.get('total_binaries', 0)} found, {bin_results.get('binaries_passed', 0)} passed")

    out = {
        "benchmark": "micro_operations",
        "description": "Bolt micro: library analysis + binary scan on ARM64",
        "reference": "https://github.com/bytedance/bolt",
        "software": "bolt",
        "version": version_str,
        "architecture": "arm64",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": {
            "lib_size_bytes": {"unit": "bytes", "description": "Library binary size"},
            "symbol_count": {"unit": "count", "description": "Total symbols in library"},
            "binaries_passed": {"unit": "count", "description": "Test binaries that passed"},
        },
        "parameters": {},
        "results": {
            "library_analysis": lib_results,
            "binary_scan": bin_results,
        },
    }
    with open(output_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[MICRO] Output written to {output_file}")


if __name__ == "__main__":
    main()
