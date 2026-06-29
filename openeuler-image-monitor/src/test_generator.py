import os
import shutil
import subprocess
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BENCHMARK_TYPE_MAP = {
    "ann": "benchmark_ann",
    "vector_search": "benchmark_ann",
    "search": "benchmark_ann",
    "kv_store": "benchmark_kv",
    "database": "benchmark_kv",
    "kv": "benchmark_kv",
    "db": "benchmark_kv",
    "cache": "benchmark_kv",
    "messaging": "benchmark_kv",
    "network": "benchmark_generic",
    "runtime": "benchmark_generic",
    "compiler": "benchmark_generic",
    "language": "benchmark_generic",
    "framework": "benchmark_generic",
}

BUILD_METHOD_MAP = {
    "faiss": "source_build",
    "hnswlib": "pip",
    "rocksdb": "source_build",
    "redis": "source_build",
    "lz4": "pip",
    "zstd": "pip",
    "protobuf": "pip",
    "pytorch": "pip",
    "scann": "pip",
    "openviking": "pip",
}

PYTHON_MODULE_MAP = {
    "faiss": "faiss",
    "hnswlib": "hnswlib",
    "lz4": "lz4",
    "protobuf": "google.protobuf",
    "pytorch": "torch",
    "scann": "scann",
    "openviking": "openviking",
}

GIT_REPO_MAP = {
    "faiss": "https://github.com/facebookresearch/faiss.git",
    "hnswlib": "https://github.com/nmslib/hnswlib.git",
    "rocksdb": "https://github.com/facebook/rocksdb.git",
    "redis": "https://github.com/redis/redis.git",
    "lz4": "https://github.com/lz4/lz4.git",
    "zstd": "https://github.com/facebook/zstd.git",
    "protobuf": "https://github.com/protocolbuffers/protobuf.git",
}

COMMON_SCRIPTS = ["json_helper.py", "aggregate_results.py", "generate_summary.py"]

BENCHMARK_ANN_SKELETON = '''#!/usr/bin/env python3
import argparse
import json
import time
import numpy as np

def run_benchmark(output_file, num_vectors, dimension, k, ef_values, iterations, version):
    results = {{
        "benchmark": "ann_search",
        "description": "{software} ANN search benchmark",
        "reference": "SKILL.md",
        "version": version,
        "parameters": {{
            "num_vectors": num_vectors,
            "dimension": dimension,
            "k": k,
            "ef_search_values": ef_values,
            "iterations": iterations,
        }},
        "performance_metrics": {{}},
        "results_summary": {{}},
    }}

    np.random.seed(42)
    data = np.random.randn(num_vectors, dimension).astype(np.float32)
    queries = np.random.randn(100, dimension).astype(np.float32)

    print("[BENCHMARK_ANN] TODO: implement {software} index build + search + recall")
    print("[BENCHMARK_ANN] Placeholder - write actual benchmark logic here")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[BENCHMARK_ANN] Output written to {{output_file}}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--num-vectors", type=int, default=100000)
    parser.add_argument("--dimension", type=int, default=128)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--ef-values", nargs="+", type=int, default=[10, 50, 100, 200, 500])
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--version", default="unknown")
    args = parser.parse_args()
    run_benchmark(args.output, args.num_vectors, args.dimension, args.k,
                  args.ef_values, args.iterations, args.version)
'''

BENCHMARK_KV_SKELETON = '''#!/usr/bin/env python3
import argparse
import json
import time

def run_benchmark(output_file, num_ops, value_size, iterations, version):
    results = {{
        "benchmark": "kv_store",
        "description": "{software} KV store benchmark",
        "reference": "SKILL.md",
        "version": version,
        "parameters": {{
            "num_ops": num_ops,
            "value_size_bytes": value_size,
            "iterations": iterations,
        }},
        "performance_metrics": {{}},
        "results_summary": {{
            "write_only": {{
                "write_ops_per_sec": 0,
                "write_speed_mbs": 0,
                "write_latency_us": 0,
            }},
            "read_80_write_20": {{
                "read_ops_per_sec": 0,
                "read_speed_mbs": 0,
                "read_latency_us": 0,
                "write_ops_per_sec": 0,
            }},
        }},
    }}

    print("[BENCHMARK_KV] TODO: implement {software} KV benchmark")
    print("[BENCHMARK_KV] Placeholder - write actual benchmark logic here")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[BENCHMARK_KV] Output written to {{output_file}}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark_bin", nargs="?", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--num-ops", type=int, default=10000)
    parser.add_argument("--value-size", type=int, default=256)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--version", default="unknown")
    args = parser.parse_args()
    run_benchmark(args.output, args.num_ops, args.value_size, args.iterations, args.version)
'''

BENCHMARK_GENERIC_SKELETON = '''#!/usr/bin/env python3
import argparse
import json
import time

def run_benchmark(output_file, version, params):
    results = {{
        "benchmark": "{software}_performance",
        "description": "{software} performance benchmark",
        "reference": "SKILL.md",
        "version": version,
        "parameters": params,
        "performance_metrics": {{}},
        "results_summary": {{}},
    }}

    print("[BENCHMARK] TODO: implement {software} benchmark")
    print("[BENCHMARK] Placeholder - write actual benchmark logic here")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[BENCHMARK] Output written to {{output_file}}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--params", default="")
    args = parser.parse_args()
    params = dict(p.split("=") for p in args.params.split(",") if "=" in p) if args.params else {{}}
    run_benchmark(args.output, args.version, params)
'''

MICRO_BENCHMARK_SKELETON = '''#!/usr/bin/env python3
import argparse
import json
import time

def run_micro_benchmark(output_file, version, iterations):
    results = {{
        "benchmark": "micro_operations",
        "description": "{software} micro operations benchmark",
        "reference": "SKILL.md",
        "version": version,
        "parameters": {{
            "iterations": iterations,
        }},
        "performance_metrics": {{}},
        "results": {{
            "operation_1": {{
                "avg_time_s": 0,
                "ops_per_sec": 0,
            }},
            "operation_2": {{
                "avg_time_s": 0,
                "ops_per_sec": 0,
            }},
        }},
    }}

    print("[MICRO_BENCHMARK] TODO: implement {software} micro benchmark")
    print("[MICRO_BENCHMARK] Placeholder - write actual benchmark logic here")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[MICRO_BENCHMARK] Output written to {{output_file}}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()
    run_micro_benchmark(args.output, args.version, args.iterations)
'''

AGGREGATE_RESULTS_SKELETON = '''#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone


def aggregate_results(results_dir, output_file):
    merged = {{
        "software_name": "{software}",
        "primary_benchmark": {{}},
        "micro_benchmark": {{}},
        "environment": {{}},
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "test_time": "",
    }}

    benchmark_map = {{
        "benchmark_ann.json": "primary_benchmark",
        "benchmark_kv.json": "primary_benchmark",
        "benchmark_generic.json": "primary_benchmark",
        "micro_benchmark.json": "micro_benchmark",
    }}

    for filename, key in benchmark_map.items():
        filepath = os.path.join(results_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                merged[key] = data
                print(f"[AGGREGATE] Loaded {{key}} from {{filepath}}")
            except Exception as e:
                print(f"[AGGREGATE] Failed to load {{filepath}}: {{e}}")

    env_file = os.path.join(results_dir, "version_info.json")
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                merged["environment"] = json.load(f)
            merged["test_time"] = merged["environment"].get("test_time", "")
            print(f"[AGGREGATE] Loaded environment from {{env_file}}")
        except Exception as e:
            print(f"[AGGREGATE] Failed to load {{env_file}}: {{e}}")

    with open(output_file, "w") as f:
        json.dump(merged, f, indent=2)
    print(f"[AGGREGATE] Aggregated results saved to {{output_file}}")
    return merged


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: aggregate_results.py <results_dir> <output_file>")
        sys.exit(1)
    aggregate_results(sys.argv[1], sys.argv[2])
'''

GENERATE_SUMMARY_SKELETON = '''#!/usr/bin/env python3
import sys
import json
from datetime import datetime, timezone


def generate_summary(input_json, output_file):
    with open(input_json) as f:
        data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("  {software} Source Build & Performance Benchmark Report")
    lines.append("=" * 70)
    lines.append(f"  Generated: {{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}}")
    lines.append(f"  Test Time: {{data.get('test_time', data.get('timestamp', 'N/A'))}}")
    lines.append("")

    env = data.get("environment", {})
    if env:
        lines.append("  --- Environment ---")
        lines.append(f"  Architecture:      {{env.get('architecture', 'N/A')}}")
        lines.append(f"  Model:             {{env.get('Model', 'N/A')}}")
        lines.append(f"  CPU Model:         {{env.get('cpu_model', 'N/A')}}")
        lines.append(f"  CPU Cores:         {{env.get('cpu_cores', 'N/A')}}")
        lines.append(f"  {software} Version:   {{env.get('software_version', 'N/A')}}")
        lines.append(f"  Python Version:    {{env.get('python_version', 'N/A')}}")
        lines.append(f"  OS:                {{env.get('os', 'N/A')}}")
        lines.append(f"  Kernel:            {{env.get('kernel', 'N/A')}}")
        lines.append("")

    primary = data.get("primary_benchmark", {})
    if primary:
        params = primary.get("parameters", {})
        lines.append("  --- Primary Benchmark ---")
        lines.append(f"  Description:       {{primary.get('description', 'N/A')}}")
        lines.append(f"  Parameters:        {{params}}")
        lines.append("")
        results_summary = primary.get("results_summary", {})
        for name, res in results_summary.items():
            if isinstance(res, dict):
                lines.append(f"  {{name}}:")
                for k, v in res.items():
                    lines.append(f"    {{k}}: {{v}}")
                lines.append("")

    micro = data.get("micro_benchmark", {})
    if micro:
        mparams = micro.get("parameters", {})
        lines.append("  --- Micro Benchmarks ---")
        lines.append(f"  Description:       {{micro.get('description', 'N/A')}}")
        lines.append(f"  Parameters:        {{mparams}}")
        lines.append("")
        results = micro.get("results", {})
        if isinstance(results, dict):
            for name, res in results.items():
                if isinstance(res, dict):
                    lines.append(f"  {{name}}:")
                    for k, v in res.items():
                        lines.append(f"    {{k}}: {{v}}")
                lines.append("")

    lines.append("=" * 70)
    lines.append("  Report generated by {software} Source Build & Performance Benchmark Workflow")
    lines.append("=" * 70)

    summary = "\\n".join(lines)
    with open(output_file, "w") as f:
        f.write(summary)
    print(summary)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_summary.py <input_json> <output_file>")
        sys.exit(1)
    generate_summary(sys.argv[1], sys.argv[2])
'''

TEST_SH_SKELETON = '''#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
SOFTWARE_NAME="{software}"
SOFTWARE_VERSION="${{SOFTWARE_VERSION:-{version}}}"
export SOFTWARE_VERSION
BUILD_METHOD="${{BUILD_METHOD:-{build_method}}}"
TARGET_OS="${{TARGET_OS:-openEuler 24.03 SP3}}"
TARGET_MODEL="${{TARGET_MODEL:-Kunpeng-920}}"
RESULTS_DIR="${{SCRIPT_DIR}}/results/${{SOFTWARE_VERSION}}"
mkdir -p "${{RESULTS_DIR}}"
LOG_FILE="${{RESULTS_DIR}}/results.log"
JSON_HELPER="${{SCRIPT_DIR}}/scripts/json_helper.py"

BUILD_TMPDIR=""
SHUNIT2_PATH=""
{benchmark_params}
{threshold_params}

log() {{ local tag="$1"; shift; printf '[%s] %s\\n' "$tag" "$*" | tee -a "${{LOG_FILE}}"; }}

json_get()              {{ python3 "${{JSON_HELPER}}" "$1" get "${{@:2}}"; }}
json_field_exists()     {{ python3 "${{JSON_HELPER}}" "$1" field_exists "$2"; }}
json_count_results()    {{ python3 "${{JSON_HELPER}}" "$1" count_results; }}
json_throughput_ge()    {{ python3 "${{JSON_HELPER}}" "$1" throughput_ge "$2" "${{@:3}}"; }}
json_latency_le()       {{ python3 "${{JSON_HELPER}}" "$1" latency_le "$2" "${{@:3}}"; }}
json_avg_throughput()   {{ python3 "${{JSON_HELPER}}" "$1" avg_throughput "${{@:2}}"; }}
json_max_latency()      {{ python3 "${{JSON_HELPER}}" "$1" max_latency "${{@:2}}"; }}
json_version()          {{ python3 "${{JSON_HELPER}}" "$1" version; }}
json_contains()         {{ python3 "${{JSON_HELPER}}" "$1" contains "$2"; }}

detect_os_id() {{
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "${{ID}}"
    else
        echo "unknown"
    fi
}}

detect_os_name() {{ echo "${{TARGET_OS}}"; }}

create_build_tmpdir() {{
    BUILD_TMPDIR="$(mktemp -d /tmp/{software}_build_XXXXXX)"
    log "BUILD" "Created temp build directory: ${{BUILD_TMPDIR}}"
}}

cleanup_build_tmpdir() {{
    if [ -n "${{BUILD_TMPDIR}}" ] && [ -d "${{BUILD_TMPDIR}}" ]; then
        log "BUILD" "Cleaning up temp build directory: ${{BUILD_TMPDIR}}"
        rm -rf "${{BUILD_TMPDIR}}"
        BUILD_TMPDIR=""
    fi
}}

download_shunit2() {{
    local shunit2_tmpdir
    shunit2_tmpdir="$(mktemp -d /tmp/shunit2_XXXXXX)"
    SHUNIT2_PATH="${{shunit2_tmpdir}}/shunit2"
    log "SETUP" "Downloading shUnit2 to ${{shunit2_tmpdir}}..."
    local mirrors=(
        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
        "https://raw.gitmirror.com/kward/shunit2/master/shunit2"
    )
    local downloaded=0
    for mirror_url in "${{mirrors[@]}}"; do
        curl --connect-timeout 30 --max-time 60 -sL -o "${{SHUNIT2_PATH}}" "${{mirror_url}}" && {{
            chmod +x "${{SHUNIT2_PATH}}"
            grep -q "^SHUNIT_VERSION=" "${{SHUNIT2_PATH}}" && {{ downloaded=1; break; }}
        }}
        rm -f "${{SHUNIT2_PATH}}"
    done
    if [ "${{downloaded}}" -eq 0 ]; then
        for mirror_url in "${{mirrors[@]}}"; do
            wget --timeout=30 --tries=2 -q -O "${{SHUNIT2_PATH}}" "${{mirror_url}}" 2>/dev/null && {{
                chmod +x "${{SHUNIT2_PATH}}"
                grep -q "^SHUNIT_VERSION=" "${{SHUNIT2_PATH}}" && {{ downloaded=1; break; }}
            }}
            rm -f "${{SHUNIT2_PATH}}"
        done
    fi
    if [ "${{downloaded}}" -eq 0 ]; then
        log "ERROR" "Failed to download shUnit2"
        rm -rf "${{shunit2_tmpdir}}"
        return 1
    fi
    log "SETUP" "shUnit2 downloaded successfully"
}}

check_prerequisites() {{
    local errors=0
    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed"
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi
    if [ ! -f "${{JSON_HELPER}}" ]; then
        log "ERROR" "json_helper.py not found at ${{JSON_HELPER}}"
        errors=$((errors + 1))
    else
        log "CHECK" "json_helper.py OK"
    fi
    log "CHECK" "OS: $(detect_os_name) ($(detect_os_id))"
    log "CHECK" "Architecture: $(uname -m)"
    log "CHECK" "Build method: ${{BUILD_METHOD}}"
    return ${{errors}}
}}

phase1_install() {{
    log "PHASE1" "=== Phase 1: Install {software} v${{SOFTWARE_VERSION}} (${{BUILD_METHOD}}) ==="

    {install_check}
    case "${{BUILD_METHOD}}" in
        pip)
            pip3 install --break-system-packages {pip_package}==${{SOFTWARE_VERSION}} 2>&1 | tee -a "${{LOG_FILE}}"
            ;;
        source_build)
            create_build_tmpdir
            {source_build_block}
            cleanup_build_tmpdir
            ;;
        *)
            log "ERROR" "Unknown BUILD_METHOD: ${{BUILD_METHOD}}"
            return 1
            ;;
    esac

    {install_verify}
}}

phase2_verify() {{
    log "PHASE2" "=== Phase 2: Collect Version Info ==="
    local timestamp model arch kernel os_name cpu_model cores python_ver numpy_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\\n\\t')"
    model="${{TARGET_MODEL}}"
    arch="$(uname -m | tr -d '\\n\\t')"
    kernel="$(uname -r | tr -d '\\n\\t')"
    os_name="$(detect_os_name | tr -d '\\n\\t')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\\n\\t')"
    if [ -z "${{cpu_model}}" ]; then
        local num_proc="$(grep -c 'processor' /proc/cpuinfo 2>/dev/null || echo 0)"
        cpu_model="ARM64 CPU (${{num_proc}} cores)"
    fi
    cores="$(nproc 2>/dev/null | tr -d '\\n\\t' || echo '4')"
    python_ver="$(python3 --version 2>&1 | tr -d '\\n\\t')"
    numpy_ver="$(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null | tr -d '\\n\\t' || echo 'unknown')"

    python3 "${{JSON_HELPER}}" "${{RESULTS_DIR}}/version_info.json" write_version_info \
        "${{timestamp}}" "${{model}}" "${{arch}}" "${{kernel}}" "${{os_name}}" "${{cpu_model}}" \
        "${{cores}}" "${{SOFTWARE_NAME}}" "${{SOFTWARE_VERSION}}" \
        "${{python_ver}}" "${{numpy_ver}}"
}}

phase3_run_benchmarks() {{
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="
    mkdir -p "${{RESULTS_DIR}}"

    {phase3_benchmark_cmd}

    log "PHASE3B" "Running micro benchmark..."
    python3 "${{SCRIPT_DIR}}/scripts/micro_benchmark.py" \
        --output "${{RESULTS_DIR}}/micro_benchmark.json" \
        --version "${{SOFTWARE_VERSION}}" \
        --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Micro benchmark had issues"
}}

phase4_results() {{
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    python3 "${{SCRIPT_DIR}}/scripts/aggregate_results.py" \
        "${{RESULTS_DIR}}" "${{RESULTS_DIR}}/results.json"

    python3 "${{SCRIPT_DIR}}/scripts/generate_summary.py" \
        "${{RESULTS_DIR}}/results.json" "${{RESULTS_DIR}}/results.txt"

    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${{RESULTS_DIR}}/results.json"
    log "PHASE4" "  TXT:  ${{RESULTS_DIR}}/results.txt"
    log "PHASE4" "  LOG:  ${{RESULTS_DIR}}/results.log"
}}

oneTimeSetUp() {{
    mkdir -p "${{RESULTS_DIR}}"
    log "START" "${{SOFTWARE_NAME}} Source Build & Performance Benchmark - v${{SOFTWARE_VERSION}}"
    log "START" "OS: $(detect_os_name) ($(detect_os_id)), Build: ${{BUILD_METHOD}}"

    check_prerequisites || log "WARN" "Some prerequisites missing, continuing..."
    phase1_install || log "FATAL" "Phase 1 (install) failed"
    phase2_verify || log "WARN" "Phase 2 had issues, continuing..."
    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing..."
    phase4_results || log "WARN" "Phase 4 had issues..."
}}

oneTimeTearDown() {{
    cleanup_build_tmpdir
    if [ -n "${{SHUNIT2_PATH}}" ]; then
        local shunit2_dir="$(dirname "${{SHUNIT2_PATH}}")"
        rm -rf "${{shunit2_dir}}"
        SHUNIT2_PATH=""
    fi
}}

setUp() {{ rm -f "${{RESULTS_DIR}}/test_temp_*.json"; }}
tearDown() {{ rm -f "${{RESULTS_DIR}}/test_temp_*.json"; }}

testArchitectureIsARM64() {{
    local arch="$(uname -m)"
    assertTrue "Architecture should be aarch64 or arm64, got: ${{arch}}" \
        "[ '${{arch}}' = 'aarch64' ] || [ '${{arch}}' = 'arm64' ]"
}}

testSoftwareIsInstalled() {{
    {test_install_check}
}}

testSoftwareVersionMatches() {{
    local ver="${{SOFTWARE_VERSION}}"
    assertNotNull "Version should not be empty" "${{ver}}"
}}

testVersionInfoExists() {{
    assertTrue "Version info JSON should exist" "[ -f '${{RESULTS_DIR}}/version_info.json' ]"
}}

testVersionInfoHasArchitecture() {{
    local vfile="${{RESULTS_DIR}}/version_info.json"
    if [ ! -f "${{vfile}}" ]; then startSkipping; return; fi
    local has_arch="$(json_field_exists "${{vfile}}" architecture)"
    assertTrue "Version info should have architecture field" "[ ${{has_arch}} -eq 1 ]"
}}

testVersionInfoHasSoftwareVersion() {{
    local vfile="${{RESULTS_DIR}}/version_info.json"
    if [ ! -f "${{vfile}}" ]; then startSkipping; return; fi
    local has_ver="$(json_field_exists "${{vfile}}" software_version)"
    assertTrue "Version info should have software_version field" "[ ${{has_ver}} -eq 1 ]"
}}

{test_benchmark_primary}

testBenchmarkMicroProducesResults() {{
    assertTrue "Micro benchmark JSON should exist" "[ -f '${{RESULTS_DIR}}/micro_benchmark.json' ]"
}}

testBenchmarkMicroHasRequiredFields() {{
    local bench_file="${{RESULTS_DIR}}/micro_benchmark.json"
    if [ ! -f "${{bench_file}}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${{bench_file}}" benchmark)"
    has_metrics="$(json_contains "${{bench_file}}" performance_metrics)"
    has_results="$(json_contains "${{bench_file}}" results)"
    assertTrue "Should have benchmark field" "[ ${{has_benchmark}} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${{has_metrics}} -eq 1 ]"
    assertTrue "Should have results field" "[ ${{has_results}} -eq 1 ]"
}}

testBenchmarkMicroAllOperationsCompleted() {{
    local bench_file="${{RESULTS_DIR}}/micro_benchmark.json"
    if [ ! -f "${{bench_file}}" ]; then startSkipping; return; fi
    local ops_count="$(json_count_results "${{bench_file}}")"
    assertTrue "Should have micro benchmark results (count=${{ops_count}})" "[ ${{ops_count}} -ge 2 ]"
}}

testAggregatedResultsExist() {{
    assertTrue "results.json should exist" "[ -f '${{RESULTS_DIR}}/results.json' ]"
}}

testSummaryReportGenerated() {{
    assertTrue "results.txt should exist" "[ -f '${{RESULTS_DIR}}/results.txt' ]"
}}

testLogFileGenerated() {{
    assertTrue "results.log should exist" "[ -f '${{RESULTS_DIR}}/results.log' ]"
}}

testAggregatedResultsContainsAllBenchmarks() {{
    local agg_file="${{RESULTS_DIR}}/results.json"
    if [ ! -f "${{agg_file}}" ]; then startSkipping; return; fi
    local has_primary has_micro
    has_primary="$(json_contains "${{agg_file}}" primary_benchmark)"
    has_micro="$(json_contains "${{agg_file}}" micro)"
    assertTrue "Should contain primary_benchmark data" "[ ${{has_primary}} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${{has_micro}} -eq 1 ]"
}}

usage() {{
    cat <<USAGE
Usage: $(basename "$0") [OPTIONS]
{software} Source Build & Performance Benchmark (shUnit2)
Options:
  --check    Check prerequisites only
  -h|--help  Show this help
Environment variables:
  SOFTWARE_VERSION         {software} version (default: {version})
  BUILD_METHOD            Build method: pip or source_build (default: {build_method})
  TARGET_OS              OS name in results (default: openEuler 24.03 SP3)
  TARGET_MODEL           Hardware model (default: Kunpeng-920)
  ITERATIONS             Number of iterations (default: 1)
{usage_thresholds}
Examples:
  ./{software}_test.sh --check
  ./{software}_test.sh
  SOFTWARE_VERSION={version} BUILD_METHOD={build_method} ./{software}_test.sh
USAGE
}}

main() {{
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)      check_only=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    log "START" "${{SOFTWARE_NAME}} Performance Benchmark v${{SOFTWARE_VERSION}}"

    if [ "${{check_only}}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        exit 1
    fi

    download_shunit2 || {{
        log "FATAL" "Failed to download shUnit2."
        exit 1
    }}

    SHUNIT_PARENT="${{SCRIPT_DIR}}/${{SOFTWARE_NAME}}_test.sh"
    . "${{SHUNIT2_PATH}}"
}}

if [ "${{1:-}}" != "--shunit2-run" ]; then
    main "$@"
fi
'''


class TestGenerator:
    def __init__(
        self,
        tests_dir: str,
        reference_dir: str = "",
        docker_pull_enabled: bool = False,
        ssh_host: str = "",
        ssh_user: str = "",
        ssh_port: int = 22,
        ssh_key_path: str = "",
        docker_pull_timeout: int = 600,
    ):
        self.tests_dir = Path(tests_dir)
        self.reference_dir = Path(reference_dir) if reference_dir else self._find_reference()
        self.docker_pull_enabled = docker_pull_enabled
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_port = ssh_port
        self.ssh_key_path = ssh_key_path
        self.docker_pull_timeout = docker_pull_timeout

    def _find_reference(self) -> Path:
        for sw in ["faiss", "rocksdb", "redis", "hnswlib"]:
            ref = self.tests_dir / sw / "scripts"
            if ref.exists():
                return ref
        return self.tests_dir / "faiss" / "scripts"

    def get_benchmark_type(self, category: str) -> str:
        cat_lower = category.lower() if category else ""
        for key, bm_type in BENCHMARK_TYPE_MAP.items():
            if key in cat_lower or cat_lower in key:
                return bm_type
        return "benchmark_generic"

    def get_build_method(self, software: str) -> str:
        return BUILD_METHOD_MAP.get(software, "source_build")

    def get_python_module(self, software: str) -> str:
        return PYTHON_MODULE_MAP.get(software, software)

    def get_git_repo(self, software: str) -> str:
        return GIT_REPO_MAP.get(software, f"https://github.com/{software}/{software}.git")

    def has_existing_tests(self, software: str) -> bool:
        sw_dir = self.tests_dir / software
        if sw_dir.exists():
            test_sh = sw_dir / f"{software}_test.sh"
            if test_sh.exists():
                return True
        return False

    def check_local_docker_image(self, namespace: str, software: str, tag: str) -> bool:
        image = f"{namespace}/{software}:{tag}"
        try:
            result = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", image],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and image in result.stdout.strip():
                logger.info(f"Local docker image found: {image}")
                return True
        except Exception as e:
            logger.debug(f"Local docker check failed: {e}")
        return False

    def check_remote_docker_image(self, namespace: str, software: str, tag: str) -> bool:
        if not self.ssh_host:
            return False
        image = f"{namespace}/{software}:{tag}"
        ssh_cmd = [
            "ssh", "-p", str(self.ssh_port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
        ]
        if self.ssh_key_path:
            ssh_cmd.extend(["-i", self.ssh_key_path])
        ssh_cmd.append(f"{self.ssh_user}@{self.ssh_host}")
        ssh_cmd.append(f"docker images --format '{{.Repository}}:{{.Tag}}' {image}")
        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and image in result.stdout.strip():
                logger.info(f"Remote docker image found: {image}")
                return True
        except Exception as e:
            logger.debug(f"Remote docker check failed: {e}")
        return False

    def pull_docker_image(self, namespace: str, software: str, tag: str) -> Dict:
        image = f"{namespace}/{software}:{tag}"
        if self.ssh_host:
            ssh_cmd = [
                "ssh", "-p", str(self.ssh_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
            ]
            if self.ssh_key_path:
                ssh_cmd.extend(["-i", self.ssh_key_path])
            ssh_cmd.append(f"{self.ssh_user}@{self.ssh_host}")
            ssh_cmd.append(f"docker pull {image}")
            try:
                result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=self.docker_pull_timeout)
                if result.returncode == 0:
                    logger.info(f"Remote docker pull succeeded: {image}")
                    return {"success": True, "image": image, "method": "ssh"}
                logger.error(f"Remote docker pull failed: {result.stderr}")
                return {"success": False, "image": image, "error": result.stderr}
            except subprocess.TimeoutExpired:
                return {"success": False, "image": image, "error": "timeout"}
            except Exception as e:
                return {"success": False, "image": image, "error": str(e)}

        try:
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=True, text=True, timeout=self.docker_pull_timeout,
            )
            if result.returncode == 0:
                logger.info(f"Local docker pull succeeded: {image}")
                return {"success": True, "image": image, "method": "local"}
            logger.error(f"Local docker pull failed: {result.stderr}")
            return {"success": False, "image": image, "error": result.stderr}
        except subprocess.TimeoutExpired:
            return {"success": False, "image": image, "error": "timeout"}
        except Exception as e:
            return {"success": False, "image": image, "error": str(e)}

    COMMON_SCRIPTS_COPY = ["json_helper.py"]
    COMMON_SCRIPTS_GENERATE = ["aggregate_results.py", "generate_summary.py"]

    def _copy_common_scripts(self, dest_scripts: Path, software: str = ""):
        for script_name in self.COMMON_SCRIPTS_COPY:
            src = self.reference_dir / script_name
            dst = dest_scripts / script_name
            if src.exists():
                shutil.copy2(str(src), str(dst))
                logger.info(f"Copied {script_name} from reference")
            else:
                self._generate_common_script(script_name, dst, software)
        for script_name in self.COMMON_SCRIPTS_GENERATE:
            dst = dest_scripts / script_name
            self._generate_common_script(script_name, dst, software)

    def _generate_common_script(self, script_name: str, dest: Path, software: str = ""):
        if script_name == "aggregate_results.py":
            content = AGGREGATE_RESULTS_SKELETON.replace("{software}", software)
            with open(dest, "w") as f:
                f.write(content)
            logger.info(f"Generated {script_name} for {software}")
            return
        elif script_name == "generate_summary.py":
            content = GENERATE_SUMMARY_SKELETON.replace("{software}", software)
            with open(dest, "w") as f:
                f.write(content)
            logger.info(f"Generated {script_name} for {software}")
            return
        elif script_name == "json_helper.py":
            if self.reference_dir.exists():
                src = self.reference_dir / "json_helper.py"
                if src.exists():
                    shutil.copy2(str(src), str(dest))
                    return
            logger.warning("No json_helper.py reference found, using minimal version")
            minimal = '''#!/usr/bin/env python3
import json
import sys


def load_json(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def get_nested(data, keys):
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)]
        else:
            return None
    return data


def cmd_write_version_info(filepath, timestamp, model, arch, kernel, os_name, cpu_model,
                           cores, sw_name, sw_version, python_ver, numpy_ver):
    data = {
        "test_time": str(timestamp),
        "Model": str(model),
        "architecture": str(arch),
        "kernel": str(kernel),
        "os": str(os_name),
        "cpu_model": str(cpu_model),
        "cpu_cores": int(cores),
        "software_name": str(sw_name),
        "software_version": str(sw_version),
        "python_version": str(python_ver),
        "numpy_version": str(numpy_ver),
    }
    save_json(filepath, data)


def main():
    filepath = sys.argv[1]
    command = sys.argv[2]
    args = sys.argv[3:]
    if command == "write_version_info":
        cmd_write_version_info(filepath, *args)
    elif command == "get":
        data = load_json(filepath)
        result = get_nested(data, args)
        print(result if result is not None else "NULL")
    elif command == "field_exists":
        data = load_json(filepath)
        print(1 if args[0] in data else 0)
    elif command == "count_results":
        data = load_json(filepath)
        print(len(data.get("results", data.get("results_summary", {}))))
    elif command == "version":
        data = load_json(filepath)
        print(data.get("software_version", "unknown"))
    elif command == "contains":
        with open(filepath) as f:
            print(1 if args[0] in f.read() else 0)
    elif command == "throughput_ge":
        print(0)
    elif command == "latency_le":
        print(0)
    elif command == "avg_throughput":
        print(0)
    elif command == "max_latency":
        print(0)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
            with open(dest, "w") as f:
                f.write(minimal)
            return
        else:
            return

    def _generate_benchmark_script(self, benchmark_type: str, software: str, dest: Path):
        if benchmark_type == "benchmark_ann":
            content = BENCHMARK_ANN_SKELETON.format(software=software)
            filename = "benchmark_ann.py"
        elif benchmark_type == "benchmark_kv":
            content = BENCHMARK_KV_SKELETON.format(software=software)
            filename = "benchmark_kv.py"
        else:
            content = BENCHMARK_GENERIC_SKELETON.format(software=software)
            filename = "benchmark_generic.py"

        with open(dest / filename, "w") as f:
            f.write(content)
        return filename

    def _generate_micro_benchmark(self, software: str, dest: Path):
        content = MICRO_BENCHMARK_SKELETON.format(software=software)
        with open(dest / "micro_benchmark.py", "w") as f:
            f.write(content)

    def _build_test_sh(self, software: str, version: str, build_method: str,
                       benchmark_type: str, category: str) -> str:
        sw = software
        ver = version or "1.0.0"
        bm = build_method
        bm_type = benchmark_type

        python_module = self.get_python_module(sw)
        pip_package = sw
        git_repo = self.get_git_repo(sw)

        if bm_type == "benchmark_ann":
            benchmark_params = "\n".join([
                'DATA_SCALE="${DATA_SCALE:-1M}"',
                'DATA_DIM="${DATA_DIM:-128}"',
                'ITERATIONS="${ITERATIONS:-1}"',
                'K_VALUE="${K_VALUE:-10}"',
                'MINIMUM_QPS="${MINIMUM_QPS:-100}"',
                'MINIMUM_RECALL="${MINIMUM_RECALL:-0.90}"',
                'MAXIMUM_LATENCY_US="${MAXIMUM_LATENCY_US:-5000}"',
                'MINIMUM_ADD_RATE="${MINIMUM_ADD_RATE:-50000}"',
            ])
            phase3_cmd = "\n".join([
                '    log "PHASE3A" "Running ANN search benchmark..."',
                '    python3 "${SCRIPT_DIR}/scripts/benchmark_ann.py" \\',
                '        --output "${RESULTS_DIR}/benchmark_ann.json" \\',
                '        --num-vectors "${DATA_SCALE}" \\',
                '        --dimension "${DATA_DIM}" \\',
                '        --k "${K_VALUE}" \\',
                '        --version "${SOFTWARE_VERSION}" \\',
                '        --iterations "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "ANN benchmark had issues"',
            ])
            test_primary = "\n".join([
                'testBenchmarkPrimaryProducesResults() {',
                '    assertTrue "ANN benchmark JSON should exist" "[ -f \'${RESULTS_DIR}/benchmark_ann.json\' ]"',
                '}',
                '',
                'testBenchmarkPrimaryHasRequiredFields() {',
                '    local bench_file="${RESULTS_DIR}/benchmark_ann.json"',
                '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
                '    local has_benchmark has_metrics has_results',
                '    has_benchmark="$(json_contains "${bench_file}" benchmark)"',
                '    has_metrics="$(json_contains "${bench_file}" performance_metrics)"',
                '    has_results="$(json_contains "${bench_file}" results_summary)"',
                '    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"',
                '    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"',
                '    assertTrue "Should have results_summary field" "[ ${has_results} -eq 1 ]"',
                '}',
            ])
            usage_thresholds = "\n".join([
                '  DATA_SCALE              Dataset size (default: 1M)',
                '  DATA_DIM               Vector dimension (default: 128)',
                '  K_VALUE                Number of nearest neighbors (default: 10)',
                '  MINIMUM_QPS            Minimum QPS threshold (default: 100)',
                '  MINIMUM_RECALL         Minimum recall threshold (default: 0.90)',
            ])
        elif bm_type == "benchmark_kv":
            benchmark_params = "\n".join([
                'NUM_OPS="${NUM_OPS:-10000}"',
                'VALUE_SIZE="${VALUE_SIZE:-256}"',
                'ITERATIONS="${ITERATIONS:-1}"',
                'MIN_WRITE_OPS="${MIN_WRITE_OPS:-5000}"',
                'MIN_READ_OPS="${MIN_READ_OPS:-10000}"',
                'MIN_WRITE_SPEED="${MIN_WRITE_SPEED:-1}"',
                'MIN_READ_SPEED="${MIN_READ_SPEED:-2}"',
                'MAX_PUT_LATENCY_US="${MAX_PUT_LATENCY_US:-200}"',
                'MAX_GET_LATENCY_US="${MAX_GET_LATENCY_US:-100}"',
            ])
            phase3_cmd = "\n".join([
                '    log "PHASE3A" "Running KV store benchmark..."',
                '    python3 "${SCRIPT_DIR}/scripts/benchmark_kv.py" \\',
                '        --output "${RESULTS_DIR}/benchmark_kv.json" \\',
                '        --num-ops "${NUM_OPS}" \\',
                '        --value-size "${VALUE_SIZE}" \\',
                '        --version "${SOFTWARE_VERSION}" \\',
                '        --iterations "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "KV benchmark had issues"',
            ])
            test_primary = "\n".join([
                'testBenchmarkPrimaryProducesResults() {',
                '    assertTrue "KV benchmark JSON should exist" "[ -f \'${RESULTS_DIR}/benchmark_kv.json\' ]"',
                '}',
                '',
                'testBenchmarkPrimaryHasRequiredFields() {',
                '    local bench_file="${RESULTS_DIR}/benchmark_kv.json"',
                '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
                '    local has_benchmark has_metrics has_results',
                '    has_benchmark="$(json_contains "${bench_file}" benchmark)"',
                '    has_metrics="$(json_contains "${bench_file}" performance_metrics)"',
                '    has_results="$(json_contains "${bench_file}" results_summary)"',
                '    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"',
                '    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"',
                '    assertTrue "Should have results_summary field" "[ ${has_results} -eq 1 ]"',
                '}',
            ])
            usage_thresholds = "\n".join([
                '  NUM_OPS                 Number of operations (default: 10000)',
                '  VALUE_SIZE              Value size in bytes (default: 256)',
                '  MIN_WRITE_OPS           Minimum write ops/s threshold (default: 5000)',
                '  MIN_READ_OPS            Minimum read ops/s threshold (default: 10000)',
            ])
        else:
            benchmark_params = 'ITERATIONS="${ITERATIONS:-1}"'
            phase3_cmd = "\n".join([
                '    log "PHASE3A" "Running performance benchmark..."',
                '    python3 "${SCRIPT_DIR}/scripts/benchmark_generic.py" \\',
                '        --output "${RESULTS_DIR}/benchmark_generic.json" \\',
                '        --version "${SOFTWARE_VERSION}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Benchmark had issues"',
            ])
            test_primary = "\n".join([
                'testBenchmarkPrimaryProducesResults() {',
                '    assertTrue "Benchmark JSON should exist" "[ -f \'${RESULTS_DIR}/benchmark_generic.json\' ]"',
                '}',
            ])
            usage_thresholds = '  ITERATIONS             Number of iterations (default: 1)'

        if bm == "pip":
            install_check = "\n".join([
                '    python3 -c "import {python_module}" 2>/dev/null && {{',
                '        log "PHASE1" "{sw} already importable, skipping install"',
                '        return 0',
                '    }}',
            ]).format(python_module=python_module, sw=sw)
            source_build_block = ""
            install_verify = '    python3 -c "import {python_module}" 2>/dev/null || {{ log "ERROR" "import {python_module} failed"; return 1; }}'.format(python_module=python_module)
            test_install = "\n".join([
                '    python3 -c "import {python_module}" 2>/dev/null || {{ startSkipping; return; }}',
                '    assertTrue "{sw} should be importable" "[ 1 -eq 1 ]"',
            ]).format(python_module=python_module, sw=sw)
        elif bm == "source_build":
            install_check = "\n".join([
                '    local found=0',
                '    # TODO: check if {sw} is already installed',
                '    if [ "${{found}}" -eq 1 ]; then',
                '        log "PHASE1" "{sw} already installed, skipping build"',
                '        return 0',
                '    fi',
            ]).format(sw=sw)
            source_build_block = "\n".join([
                '    # TODO: implement source build for {sw}',
                '    # git clone --branch v${{SOFTWARE_VERSION}} --depth 1 {git_repo} "${{BUILD_TMPDIR}}/{sw}"',
                '    # cmake/make/install steps here',
                '    log "WARN" "Source build for {sw} is a placeholder - implement actual build steps"',
            ]).format(sw=sw, git_repo=git_repo)
            install_verify = "\n".join([
                '    # TODO: verify {sw} is installed after source_build',
                '    log "PHASE1" "Verifying {sw} installation..."',
            ]).format(sw=sw)
            test_install = "\n".join([
                '    # TODO: check {sw} installation',
                '    log "CHECK" "Checking {sw} installation..."',
            ]).format(sw=sw)
        else:
            install_check = ""
            source_build_block = ""
            install_verify = ""
            test_install = '    log "CHECK" "Checking {sw} installation..."'.format(sw=sw)

        content = TEST_SH_SKELETON.format(
            software=sw,
            version=ver,
            build_method=bm,
            benchmark_params=benchmark_params,
            threshold_params="",
            install_check=install_check,
            pip_package=pip_package,
            source_build_block=source_build_block,
            install_verify=install_verify,
            phase3_benchmark_cmd=phase3_cmd,
            test_install_check=test_install,
            test_benchmark_primary=test_primary,
            usage_thresholds=usage_thresholds,
        )
        return content

    def generate_test_scaffolding(
        self,
        software: str,
        version: str,
        category: str,
        namespace: str = "openeuler",
        tag: str = "",
    ) -> Dict:
        sw_dir = self.tests_dir / software
        scripts_dir = sw_dir / "scripts"

        if self.has_existing_tests(software):
            logger.info(f"Software {software} already has tests, skipping scaffolding generation")
            return {
                "software": software,
                "status": "existing",
                "message": "Test directory already exists",
                "path": str(sw_dir),
            }

        logger.info(f"Generating test scaffolding for {software} v{version}")

        sw_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir.mkdir(parents=True, exist_ok=True)

        benchmark_type = self.get_benchmark_type(category)
        build_method = self.get_build_method(software)

        self._copy_common_scripts(scripts_dir, software)
        self._generate_benchmark_script(benchmark_type, software, scripts_dir)
        self._generate_micro_benchmark(software, scripts_dir)

        test_sh_content = self._build_test_sh(software, version, build_method, benchmark_type, category)
        test_sh_path = sw_dir / f"{software}_test.sh"
        with open(test_sh_path, "w") as f:
            f.write(test_sh_content)
        os.chmod(str(test_sh_path), 0o755)

        results_dir = sw_dir / "results" / (version or "1.0.0")
        results_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Test scaffolding generated at {sw_dir}")
        return {
            "software": software,
            "version": version,
            "category": category,
            "benchmark_type": benchmark_type,
            "build_method": build_method,
            "status": "generated",
            "path": str(sw_dir),
            "files": [
                f"{software}_test.sh",
                "scripts/json_helper.py",
                "scripts/aggregate_results.py",
                "scripts/generate_summary.py",
                f"scripts/{benchmark_type}.py",
                "scripts/micro_benchmark.py",
            ],
        }

    def generate_for_pushed_images(
        self,
        pushed_results: List[Dict],
        namespace: str = "openeuler",
        docker_pull: bool = False,
    ) -> List[Dict]:
        generated = []
        for r in pushed_results:
            software = r.get("software", "")
            version = r.get("version", "")
            category = r.get("category", "")
            tag = r.get("dockerhub_tag", "latest")

            if not software:
                continue

            if self.has_existing_tests(software):
                logger.info(f"{software}: existing tests, skipping")
                generated.append({
                    "software": software,
                    "status": "existing",
                    "message": "Test directory already exists",
                })
                continue

            docker_status = "not_checked"
            if docker_pull:
                if self.check_local_docker_image(namespace, software, tag):
                    docker_status = "local_found"
                elif self.check_remote_docker_image(namespace, software, tag):
                    docker_status = "remote_found"
                else:
                    pull_result = self.pull_docker_image(namespace, software, tag)
                    if pull_result.get("success"):
                        docker_status = "pulled"
                    else:
                        docker_status = f"pull_failed: {pull_result.get('error', 'unknown')}"

            result = self.generate_test_scaffolding(
                software, version, category, namespace, tag,
            )
            result["docker_status"] = docker_status
            generated.append(result)

        return generated
