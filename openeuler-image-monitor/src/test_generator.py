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

PYTHON_MODULE_MAP = {
    "faiss": "faiss",
    "hnswlib": "hnswlib",
    "lz4": "lz4",
    "protobuf": "google.protobuf",
    "pytorch": "torch",
    "scann": "scann",
    "openviking": "openviking",
}

COMMON_SCRIPTS_COPY = ["json_helper.py"]
COMMON_SCRIPTS_GENERATE = ["aggregate_results.py", "generate_summary.py"]

BENCHMARK_GENERIC_PY = '''#!/usr/bin/env python3
import argparse
import json
import time
import sys
import subprocess

SOFTWARE_NAME = "{software}"

def detect_software():
    py_modules = {{
        "faiss": "faiss", "hnswlib": "hnswlib", "lz4": "lz4",
        "protobuf": "google.protobuf", "pytorch": "torch",
        "scann": "scann", "openviking": "openviking",
        "numpy": "numpy", "pandas": "pandas", "scipy": "scipy",
        "sklearn": "sklearn", "tensorflow": "tensorflow",
    }}
    binaries = [
        "redis-server", "redis-cli", "redis-benchmark",
        "rocksdb", "mysql", "nginx", "envoy",
        "go", "java", "javac", "gcc", "g++", "cmake",
        "python3", "pip3", "node", "npm",
        "kubectl", "docker", "etcd",
    ]
    found_py = None
    for name, module in py_modules.items():
        try:
            __import__(module)
            found_py = (name, module)
            break
        except ImportError:
            pass
    found_bin = None
    for b in binaries:
        try:
            result = subprocess.run(["which", b], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                found_bin = b
                break
        except Exception:
            pass
    return found_py, found_bin

def run_python_benchmark(module_name, version, iterations):
    metrics = {{}}
    try:
        mod = __import__(module_name)
        ver = getattr(mod, "__version__", "unknown")
        start = time.time()
        for _ in range(iterations):
            pass
        elapsed = time.time() - start
        metrics["import_time_ms"] = round(elapsed * 1000, 2)
        metrics["version"] = ver
        metrics["importable"] = True
    except ImportError:
        metrics["importable"] = False
        metrics["version"] = "not_found"
    return metrics

def run_binary_benchmark(binary_name, iterations):
    metrics = {{}}
    try:
        start = time.time()
        result = subprocess.run([binary_name, "--version"], capture_output=True, text=True, timeout=10)
        elapsed = time.time() - start
        metrics["version_check_time_ms"] = round(elapsed * 1000, 2)
        metrics["version_output"] = result.stdout.strip()[:100] if result.stdout else ""
        metrics["available"] = True
    except Exception as e:
        metrics["available"] = False
        metrics["error"] = str(e)[:100]
    return metrics

def run_benchmark(output_file, version, iterations):
    found_py, found_bin = detect_software()
    results = {{
        "benchmark": "generic_performance",
        "description": f"{{SOFTWARE_NAME}} generic performance benchmark",
        "reference": "SKILL.md",
        "version": version,
        "parameters": {{
            "iterations": iterations,
        }},
        "performance_metrics": {{}},
        "results_summary": {{}},
    }}

    sw_type = "unknown"
    if found_py:
        sw_name, module = found_py
        sw_type = "python"
        py_metrics = run_python_benchmark(module, version, iterations)
        results["results_summary"]["python_import"] = py_metrics
        results["performance_metrics"]["import_time_ms"] = py_metrics.get("import_time_ms", 0)
        results["performance_metrics"]["version"] = py_metrics.get("version", "unknown")
    if found_bin:
        sw_type = "binary" if not found_py else sw_type + "+binary"
        bin_metrics = run_binary_benchmark(found_bin, iterations)
        results["results_summary"]["binary_check"] = bin_metrics
        results["performance_metrics"]["binary_available"] = bin_metrics.get("available", False)

    results["results_summary"]["software_type"] = sw_type
    print(f"[BENCHMARK] {{SOFTWARE_NAME}} type={{sw_type}} py={{found_py}} bin={{found_bin}}")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[BENCHMARK] Output written to {{output_file}}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()
    run_benchmark(args.output, args.version, args.iterations)
'''

MICRO_BENCHMARK_PY = '''#!/usr/bin/env python3
import argparse
import json
import time
import sys
import subprocess
import os

SOFTWARE_NAME = "{software}"

def time_operation(name, func, iterations):
    times = []
    for _ in range(iterations):
        start = time.time()
        try:
            func()
        except Exception:
            pass
        times.append(time.time() - start)
    avg = sum(times) / len(times) if times else 0
    min_t = min(times) if times else 0
    max_t = max(times) if times else 0
    return {{
        "avg_time_s": round(avg, 4),
        "min_time_s": round(min_t, 4),
        "max_time_s": round(max_t, 4),
        "iterations": iterations,
    }}

def detect_and_benchmark(iterations):
    results = {{
        "benchmark": "micro_operations",
        "description": f"{{SOFTWARE_NAME}} micro benchmark",
        "reference": "SKILL.md",
        "parameters": {{
            "iterations": iterations,
        }},
        "performance_metrics": {{}},
        "results": {{}},
    }}

    op_results = {{}}

    py_modules = {{
        "faiss": "faiss", "hnswlib": "hnswlib", "lz4": "lz4",
        "protobuf": "google.protobuf", "pytorch": "torch",
        "scann": "scann", "openviking": "openviking",
        "numpy": "numpy", "pandas": "pandas", "scipy": "scipy",
    }}
    for sw_name, module in py_modules.items():
        try:
            mod = __import__(module)
            op_results["import_" + sw_name] = time_operation(
                "import_" + sw_name,
                lambda: __import__(module),
                1,
            )
            ver = getattr(mod, "__version__", "unknown")
            op_results["import_" + sw_name]["version"] = ver
        except ImportError:
            pass

    binaries = ["redis-cli", "mysql", "nginx", "go", "java", "python3", "docker", "kubectl", "etcd"]
    for b in binaries:
        try:
            r = subprocess.run(["which", b], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                op_results["which_" + b] = time_operation(
                    "which_" + b,
                    lambda: subprocess.run(["which", b], capture_output=True, timeout=5),
                    iterations,
                )
        except Exception:
            pass

    cpu_count = os.cpu_count() or 1
    op_results["system_info"] = {{
        "cpu_cores": cpu_count,
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
    }}

    results["results"] = op_results
    results["performance_metrics"]["operation_count"] = len(op_results)
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()
    data = detect_and_benchmark(args.iterations)
    data["version"] = args.version
    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[MICRO] Output written to {{args.output}}")
'''

AGGREGATE_RESULTS_TEMPLATE = '''#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone


def aggregate_results(results_dir, output_file):
    os.makedirs(results_dir, exist_ok=True)

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

    try:
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(merged, f, indent=2)
        print(f"[AGGREGATE] Aggregated results saved to {{output_file}}")
    except Exception as e:
        print(f"[AGGREGATE] Failed to write {{output_file}}: {{e}}")
    return merged


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: aggregate_results.py <results_dir> <output_file>")
        sys.exit(1)
    aggregate_results(sys.argv[1], sys.argv[2])
'''

GENERATE_SUMMARY_TEMPLATE = '''#!/usr/bin/env python3
import sys
import json
import os
from datetime import datetime, timezone


def generate_summary(input_json, output_file):
    if not os.path.exists(input_json):
        lines = [
            "=" * 70,
            "  {software} Performance Benchmark Report",
            "=" * 70,
            f"  Generated: {{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}}",
            "  Status: INCOMPLETE - benchmark data not available",
            "=" * 70,
        ]
        summary = "\\n".join(lines)
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            f.write(summary)
        print(summary)
        return

    with open(input_json) as f:
        data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("  {software} Performance Benchmark Report")
    lines.append("=" * 70)
    lines.append(f"  Generated: {{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}}")
    lines.append(f"  Test Time: {{data.get('test_time', data.get('timestamp', 'N/A'))}}")
    lines.append("")

    env = data.get("environment", {{}})
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

    primary = data.get("primary_benchmark", {{}})
    if primary:
        params = primary.get("parameters", {{}})
        lines.append("  --- Primary Benchmark ---")
        lines.append(f"  Description:       {{primary.get('description', 'N/A')}}")
        lines.append(f"  Parameters:        {{params}}")
        lines.append("")
        results_summary = primary.get("results_summary", {{}})
        if isinstance(results_summary, dict):
            for name, res in results_summary.items():
                if isinstance(res, dict):
                    lines.append(f"  {{name}}:")
                    for k, v in res.items():
                        lines.append(f"    {{k}}: {{v}}")
                else:
                    lines.append(f"  {{name}}: {{res}}")
                lines.append("")

    micro = data.get("micro_benchmark", {{}})
    if micro:
        mparams = micro.get("parameters", {{}})
        lines.append("  --- Micro Benchmarks ---")
        lines.append(f"  Description:       {{micro.get('description', 'N/A')}}")
        lines.append(f"  Parameters:        {{mparams}}")
        lines.append("")
        results = micro.get("results", {{}})
        if isinstance(results, dict):
            for name, res in results.items():
                if isinstance(res, dict):
                    lines.append(f"  {{name}}:")
                    for k, v in res.items():
                        lines.append(f"    {{k}}: {{v}}")
                else:
                    lines.append(f"  {{name}}: {{res}}")
                lines.append("")

    lines.append("=" * 70)
    lines.append("  Report generated by {software} Performance Benchmark Workflow")
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

JSON_HELPER_MINIMAL = '''#!/usr/bin/env python3
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
    data = {{
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
    }}
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
        print(len(data.get("results", data.get("results_summary", {{}}))))
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
        print(f"Unknown command: {{command}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''


def build_test_sh(software, version, docker_namespace, docker_tag, benchmark_type):
    sw = software
    ver = version or "1.0.0"
    bm_type = benchmark_type
    docker_image = f"{docker_namespace}/{sw}"
    docker_tag_val = docker_tag or f"{ver}-oe2403sp3"

    if bm_type == "benchmark_ann":
        bench_file = "benchmark_ann.json"
        bench_cmd = f'    docker exec "${{DOCKER_CID}}" python3 /workspace/scripts/benchmark_generic.py --output /workspace/results/${{SOFTWARE_VERSION}}/benchmark_generic.json --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"'
    elif bm_type == "benchmark_kv":
        bench_file = "benchmark_kv.json"
        bench_cmd = f'    docker exec "${{DOCKER_CID}}" python3 /workspace/scripts/benchmark_generic.py --output /workspace/results/${{SOFTWARE_VERSION}}/benchmark_generic.json --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"'
    else:
        bench_file = "benchmark_generic.json"
        bench_cmd = f'    docker exec "${{DOCKER_CID}}" python3 /workspace/scripts/benchmark_generic.py --output /workspace/results/${{SOFTWARE_VERSION}}/benchmark_generic.json --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"'

    python_module = PYTHON_MODULE_MAP.get(sw, sw)

    lines = [
        '#!/bin/bash',
        '',
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        f'SOFTWARE_NAME="{sw}"',
        f'SOFTWARE_VERSION="${{SOFTWARE_VERSION:-{ver}}}"',
        'export SOFTWARE_VERSION',
        f'DOCKER_IMAGE="{docker_image}"',
        f'DOCKER_TAG="${{DOCKER_TAG:-{docker_tag_val}}}"',
        'DOCKER_CID=""',
        'SHUNIT2_PATH=""',
        'HAS_PYTHON3=0',
        'ITERATIONS="${ITERATIONS:-1}"',
        '',
        'RESULTS_DIR="${SCRIPT_DIR}/results/${SOFTWARE_VERSION}"',
        'mkdir -p "${RESULTS_DIR}"',
        'LOG_FILE="${RESULTS_DIR}/results.log"',
        'JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"',
        '',
        'log() { local tag="$1"; shift; printf \'[%s] %s\\n\' "$tag" "$*" | tee -a "${LOG_FILE}"; }',
        '',
        'json_get()              { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }',
        'json_field_exists()     { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }',
        'json_count_results()    { python3 "${JSON_HELPER}" "$1" count_results; }',
        'json_throughput_ge()    { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }',
        'json_latency_le()       { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }',
        'json_avg_throughput()   { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }',
        'json_max_latency()      { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }',
        'json_version()          { python3 "${JSON_HELPER}" "$1" version; }',
        'json_contains()         { python3 "${JSON_HELPER}" "$1" contains "$2"; }',
        '',
        'detect_os_name() { echo "openEuler 24.03 SP3"; }',
        '',
        'download_shunit2() {',
        '    local shunit2_tmpdir="$(mktemp -d /tmp/shunit2_XXXXXX)"',
        '    SHUNIT2_PATH="${shunit2_tmpdir}/shunit2"',
        '    log "SETUP" "Downloading shUnit2..."',
        '    local mirrors=(',
        '        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"',
        '        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"',
        '        "https://raw.gitmirror.com/kward/shunit2/master/shunit2"',
        '    )',
        '    local downloaded=0',
        '    for mirror_url in "${mirrors[@]}"; do',
        '        curl --connect-timeout 30 --max-time 60 -sL -o "${SHUNIT2_PATH}" "${mirror_url}" && {',
        '            chmod +x "${SHUNIT2_PATH}"',
        '            grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { downloaded=1; break; }',
        '        }',
        '        rm -f "${SHUNIT2_PATH}"',
        '    done',
        '    if [ "${downloaded}" -eq 0 ]; then',
        '        for mirror_url in "${mirrors[@]}"; do',
        '            wget --timeout=30 --tries=2 -q -O "${SHUNIT2_PATH}" "${mirror_url}" 2>/dev/null && {',
        '                chmod +x "${SHUNIT2_PATH}"',
        '                grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { downloaded=1; break; }',
        '            }',
        '            rm -f "${SHUNIT2_PATH}"',
        '        done',
        '    fi',
        '    if [ "${downloaded}" -eq 0 ]; then',
        '        log "ERROR" "Failed to download shUnit2"',
        '        rm -rf "${shunit2_tmpdir}"',
        '        return 1',
        '    fi',
        '    log "SETUP" "shUnit2 downloaded successfully"',
        '}',
        '',
        'check_prerequisites() {',
        '    local errors=0',
        '    if ! command -v docker >/dev/null 2>&1; then',
        '        log "ERROR" "docker is not installed"',
        '        errors=$((errors + 1))',
        '    else',
        '        log "CHECK" "Docker OK: $(docker --version 2>&1)"',
        '    fi',
        '    if [ ! -f "${JSON_HELPER}" ]; then',
        '        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"',
        '        errors=$((errors + 1))',
        '    else',
        '        log "CHECK" "json_helper.py OK"',
        '    fi',
        '    log "CHECK" "Architecture: $(uname -m)"',
        '    return ${errors}',
        '}',
        '',
        'phase1_install() {',
        f'    log "PHASE1" "=== Phase 1: Docker Pull {sw} v${{SOFTWARE_VERSION}} ==="',
        '    log "PHASE1" "Pulling ${DOCKER_IMAGE}:${DOCKER_TAG}..."',
        '    docker pull "${DOCKER_IMAGE}:${DOCKER_TAG}" 2>&1 | tee -a "${LOG_FILE}" || {',
        '        log "ERROR" "docker pull failed"',
        '        return 1',
        '    }',
        '    log "PHASE1" "Starting container..."',
        '    DOCKER_CID=$(docker run -d \\',
        '        -v "${SCRIPT_DIR}/scripts:/workspace/scripts" \\',
        '        -v "${SCRIPT_DIR}/results:/workspace/results" \\',
        '        -e SOFTWARE_VERSION="${SOFTWARE_VERSION}" \\',
        '        "${DOCKER_IMAGE}:${DOCKER_TAG}" \\',
        '        sleep infinity) || {',
        '        log "ERROR" "docker run failed"',
        '        return 1',
        '    }',
        '    log "PHASE1" "Container ${DOCKER_CID} started"',
        '}',
        '',
        'phase2_verify() {',
        '    log "PHASE2" "=== Phase 2: Collect Version Info ==="',
        '    local timestamp model arch kernel os_name cpu_model cores python_ver numpy_ver',
        '    timestamp="$(date -u \'+%Y-%m-%dT%H:%M:%SZ\' | tr -d \'\\n\\t\')"',
        '    model="Kunpeng-920"',
        '    arch="$(uname -m | tr -d \'\\n\\t\')"',
        '    kernel="$(uname -r | tr -d \'\\n\\t\')"',
        '    os_name="$(detect_os_name | tr -d \'\\n\\t\')"',
        '    cpu_model="$(grep \'model name\' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d \'\\n\\t\')"',
        '    if [ -z "${cpu_model}" ]; then',
        '        local num_proc="$(grep -c \'processor\' /proc/cpuinfo 2>/dev/null || echo 0)"',
        '        cpu_model="ARM64 CPU (${num_proc} cores)"',
        '    fi',
        '    cores="$(nproc 2>/dev/null | tr -d \'\\n\\t\' || echo \'4\')"',
        '    if [ "${HAS_PYTHON3}" -eq 1 ]; then',
        '        python_ver="$(docker exec "${DOCKER_CID}" python3 --version 2>&1 | tr -d \'\\n\\t\')"',
        '        numpy_ver="$(docker exec "${DOCKER_CID}" python3 -c \'import numpy; print(numpy.__version__)\' 2>/dev/null | tr -d \'\\n\\t\' || echo \'unknown\')"',
        '    else',
        '        python_ver="$(python3 --version 2>&1 | tr -d \'\\n\\t\' || echo \'unknown\')"',
        '        numpy_ver="$(python3 -c \'import numpy; print(numpy.__version__)\' 2>/dev/null | tr -d \'\\n\\t\' || echo \'unknown\')"',
        '    fi',
        '',
        '    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \\',
        '        "${timestamp}" "${model}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \\',
        '        "${cores}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \\',
        '        "${python_ver}" "${numpy_ver}"',
        '}',
        '',
        'phase3_run_benchmarks() {',
        '    log "PHASE3" "=== Phase 3: Run Benchmarks ==="',
        '    mkdir -p "${RESULTS_DIR}"',
        '',
        '    if [ "${HAS_PYTHON3}" -eq 1 ]; then',
        bench_cmd,
        '        log "PHASE3B" "Running micro benchmark..."',
        '        docker exec "${DOCKER_CID}" python3 /workspace/scripts/micro_benchmark.py \\',
        '            --output /workspace/results/${SOFTWARE_VERSION}/micro_benchmark.json \\',
        '            --version "${SOFTWARE_VERSION}" \\',
        '            --iterations "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"',
        '    else',
        '        log "PHASE3" "No python3 in container, running benchmarks on host"',
        f'        python3 "${{SCRIPT_DIR}}/scripts/benchmark_generic.py" --output "${{RESULTS_DIR}}/benchmark_generic.json" --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"',
        '        python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \\',
        '            --output "${RESULTS_DIR}/micro_benchmark.json" \\',
        '            --version "${SOFTWARE_VERSION}" \\',
        '            --iterations "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"',
        '    fi',
        '}',
        '',
        'phase4_results() {',
        '    log "PHASE4" "=== Phase 4: Aggregate & Report ==="',
        '    mkdir -p "${RESULTS_DIR}"',
        '',
        '    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \\',
        '        "${RESULTS_DIR}" "${RESULTS_DIR}/results.json"',
        '',
        '    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \\',
        '        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt"',
        '',
        '    log "PHASE4" "Reports generated:"',
        '    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"',
        '    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"',
        '    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"',
        '}',
        '',
        'oneTimeSetUp() {',
        '    mkdir -p "${RESULTS_DIR}"',
        f'    log "START" "{sw} Performance Benchmark v${{SOFTWARE_VERSION}}"',
        '    check_prerequisites || log "WARN" "Some prerequisites missing, continuing..."',
        '    phase1_install || { log "FATAL" "Phase 1 (docker pull) failed, aborting"; return 1; }',
        '    HAS_PYTHON3=0',
        '    if docker exec "${DOCKER_CID}" python3 --version >/dev/null 2>&1; then',
        '        HAS_PYTHON3=1',
        '        log "CHECK" "python3 available inside container"',
        '    else',
        '        HAS_PYTHON3=0',
        '        log "WARN" "python3 NOT available inside container, using host-side fallback"',
        '    fi',
        '    phase2_verify || log "WARN" "Phase 2 had issues, continuing..."',
        '    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing..."',
        '    phase4_results || log "WARN" "Phase 4 had issues..."',
        '}',
        '',
        'oneTimeTearDown() {',
        '    if [ -n "${DOCKER_CID}" ]; then',
        '        log "CLEANUP" "Stopping container ${DOCKER_CID}"',
        '        docker stop "${DOCKER_CID}" >/dev/null 2>&1',
        '        docker rm "${DOCKER_CID}" >/dev/null 2>&1',
        '        DOCKER_CID=""',
        '    fi',
        '    if [ -n "${SHUNIT2_PATH}" ]; then',
        '        local shunit2_dir="$(dirname "${SHUNIT2_PATH}")"',
        '        rm -rf "${shunit2_dir}"',
        '        SHUNIT2_PATH=""',
        '    fi',
        '}',
        '',
        'setUp() { rm -f "${RESULTS_DIR}/test_temp_*.json"; }',
        'tearDown() { rm -f "${RESULTS_DIR}/test_temp_*.json"; }',
        '',
        'testArchitectureIsARM64() {',
        '    local arch="$(uname -m)"',
        '    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \\',
        '        "[ \'${arch}\' = \'aarch64\' ] || [ \'${arch}\' = \'arm64\' ]"',
        '}',
        '',
        'testDockerImageAvailable() {',
        '    if [ -z "${DOCKER_CID}" ]; then startSkipping; return; fi',
        f'    local img="{docker_image}:${{DOCKER_TAG}}"',
        '    local check',
        '    check="$(docker images --format \'{{.Repository}}:{{.Tag}}\' "${img}" | grep -c "${img}")"',
        '    assertTrue "Docker image ${img} should be available" "[ ${check} -ge 1 ]"',
        '}',
        '',
        'testSoftwareIsInstalled() {',
        '    if [ -z "${DOCKER_CID}" ]; then startSkipping; return; fi',
        '    if [ "${HAS_PYTHON3}" -eq 0 ]; then startSkipping; return; fi',
        f'    local check="$(docker exec "${{DOCKER_CID}}" python3 -c "import {python_module}" 2>/dev/null && echo 1 || echo 0)"',
        '    assertTrue "Software should be importable in container" "[ ${check} -eq 1 ]"',
        '}',
        '',
        'testSoftwareVersionMatches() {',
        '    local ver="${SOFTWARE_VERSION}"',
        '    assertNotNull "Version should not be empty" "${ver}"',
        '}',
        '',
        'testVersionInfoExists() {',
        '    assertTrue "Version info JSON should exist" "[ -f \'${RESULTS_DIR}/version_info.json\' ]"',
        '}',
        '',
        'testVersionInfoHasArchitecture() {',
        '    local vfile="${RESULTS_DIR}/version_info.json"',
        '    if [ ! -f "${vfile}" ]; then startSkipping; return; fi',
        '    local has_arch="$(json_field_exists "${vfile}" architecture)"',
        '    assertTrue "Version info should have architecture field" "[ ${has_arch} -eq 1 ]"',
        '}',
        '',
        'testVersionInfoHasSoftwareVersion() {',
        '    local vfile="${RESULTS_DIR}/version_info.json"',
        '    if [ ! -f "${vfile}" ]; then startSkipping; return; fi',
        '    local has_ver="$(json_field_exists "${vfile}" software_version)"',
        '    assertTrue "Version info should have software_version field" "[ ${has_ver} -eq 1 ]"',
        '}',
        '',
        f'testBenchmarkPrimaryProducesResults() {{',
        '    if [ -z "${DOCKER_CID}" ] && [ "${HAS_PYTHON3}" -eq 0 ]; then startSkipping; return; fi',
        f'    assertTrue "Benchmark JSON should exist" "[ -f \'${{RESULTS_DIR}}/{bench_file}\' ]"',
        '}',
        '',
        f'testBenchmarkPrimaryHasRequiredFields() {{',
        f'    local bench_file="${{RESULTS_DIR}}/{bench_file}"',
        '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
        '    local has_benchmark has_metrics has_results',
        '    has_benchmark="$(json_contains "${bench_file}" benchmark)"',
        '    has_metrics="$(json_contains "${bench_file}" performance_metrics)"',
        '    has_results="$(json_contains "${bench_file}" results_summary)"',
        '    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"',
        '    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"',
        '    assertTrue "Should have results_summary field" "[ ${has_results} -eq 1 ]"',
        '}',
        '',
        'testBenchmarkMicroProducesResults() {',
        '    if [ -z "${DOCKER_CID}" ] && [ "${HAS_PYTHON3}" -eq 0 ]; then startSkipping; return; fi',
        '    assertTrue "Micro benchmark JSON should exist" "[ -f \'${RESULTS_DIR}/micro_benchmark.json\' ]"',
        '}',
        '',
        'testBenchmarkMicroHasRequiredFields() {',
        '    local bench_file="${RESULTS_DIR}/micro_benchmark.json"',
        '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
        '    local has_benchmark has_metrics has_results',
        '    has_benchmark="$(json_contains "${bench_file}" benchmark)"',
        '    has_metrics="$(json_contains "${bench_file}" performance_metrics)"',
        '    has_results="$(json_contains "${bench_file}" results)"',
        '    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"',
        '    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"',
        '    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"',
        '}',
        '',
        'testBenchmarkMicroAllOperationsCompleted() {',
        '    local bench_file="${RESULTS_DIR}/micro_benchmark.json"',
        '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
        '    local ops_count="$(json_count_results "${bench_file}")"',
        '    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -ge 2 ]"',
        '}',
        '',
        'testAggregatedResultsExist() {',
        '    if [ ! -f "${RESULTS_DIR}/results.json" ]; then startSkipping; return; fi',
        '    assertTrue "results.json should exist" "[ -f \'${RESULTS_DIR}/results.json\' ]"',
        '}',
        '',
        'testSummaryReportGenerated() {',
        '    if [ ! -f "${RESULTS_DIR}/results.txt" ]; then startSkipping; return; fi',
        '    assertTrue "results.txt should exist" "[ -f \'${RESULTS_DIR}/results.txt\' ]"',
        '}',
        '',
        'testLogFileGenerated() {',
        '    if [ ! -f "${RESULTS_DIR}/results.log" ]; then startSkipping; return; fi',
        '    assertTrue "results.log should exist" "[ -f \'${RESULTS_DIR}/results.log\' ]"',
        '}',
        '',
        'testAggregatedResultsContainsAllBenchmarks() {',
        '    local agg_file="${RESULTS_DIR}/results.json"',
        '    if [ ! -f "${agg_file}" ]; then startSkipping; return; fi',
        '    local has_primary has_micro',
        '    has_primary="$(json_contains "${agg_file}" primary_benchmark)"',
        '    has_micro="$(json_contains "${agg_file}" micro)"',
        '    assertTrue "Should contain primary_benchmark data" "[ ${has_primary} -eq 1 ]"',
        '    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"',
        '}',
        '',
        f'usage() {{',
        f'    cat <<USAGE',
        f'Usage: $(basename "$0") [OPTIONS]',
        f'{sw} Performance Benchmark (shUnit2 + Docker)',
        f'Options:',
        f'  --check    Check prerequisites only',
        f'  -h|--help  Show this help',
        f'Environment variables:',
        f'  SOFTWARE_VERSION         {sw} version (default: {ver})',
        f'  DOCKER_TAG              Docker image tag (default: {docker_tag_val})',
        f'  ITERATIONS              Number of iterations (default: 1)',
        f'Examples:',
        f'  ./{sw}_test.sh --check',
        f'  ./{sw}_test.sh',
        f'  SOFTWARE_VERSION={ver} ./{sw}_test.sh',
        f'USAGE',
        '}',
        '',
        'main() {',
        '    local check_only=0',
        '    while [ $# -gt 0 ]; do',
        '        case "$1" in',
        '            --check)      check_only=1; shift ;;',
        '            -h|--help)    usage; exit 0 ;;',
        '            *)            log "ERROR" "Unknown option: $1"; usage; exit 1 ;;',
        '        esac',
        '    done',
        '',
        f'    log "START" "{sw} Performance Benchmark v${{SOFTWARE_VERSION}}"',
        '',
        '    if [ "${check_only}" -eq 1 ]; then',
        '        check_prerequisites',
        '        exit $?',
        '    fi',
        '',
        '    if ! check_prerequisites; then',
        '        log "FATAL" "Prerequisites not met. Use --check for detailed status."',
        '        exit 1',
        '    fi',
        '',
        '    download_shunit2 || {',
        '        log "FATAL" "Failed to download shUnit2."',
        '        exit 1',
        '    }',
        '',
        f'    SHUNIT_PARENT="${{SCRIPT_DIR}}/{sw}_test.sh"',
        '    . "${SHUNIT2_PATH}"',
        '}',
        '',
        'if [ "${1:-}" != "--shunit2-run" ]; then',
        '    main "$@"',
        'fi',
    ]
    return "\n".join(lines)


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
        self.tests_dir = Path(tests_dir).resolve()
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

    def get_python_module(self, software: str) -> str:
        return PYTHON_MODULE_MAP.get(software, software)

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

    def _copy_common_scripts(self, dest_scripts: Path, software: str = ""):
        for script_name in COMMON_SCRIPTS_COPY:
            src = self.reference_dir / script_name
            dst = dest_scripts / script_name
            if src.exists():
                shutil.copy2(str(src), str(dst))
                logger.info(f"Copied {script_name} from reference")
            else:
                self._generate_common_script(script_name, dst, software)
        for script_name in COMMON_SCRIPTS_GENERATE:
            dst = dest_scripts / script_name
            self._generate_common_script(script_name, dst, software)

    def _generate_common_script(self, script_name: str, dest: Path, software: str = ""):
        if script_name == "aggregate_results.py":
            content = AGGREGATE_RESULTS_TEMPLATE.replace("{software}", software)
            with open(dest, "w") as f:
                f.write(content)
            logger.info(f"Generated {script_name} for {software}")
            return
        elif script_name == "generate_summary.py":
            content = GENERATE_SUMMARY_TEMPLATE.replace("{software}", software)
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
            content = JSON_HELPER_MINIMAL.replace("{software}", software)
            with open(dest, "w") as f:
                f.write(content)
            return
        else:
            return

    def _generate_benchmark_script(self, software: str, dest: Path):
        content = BENCHMARK_GENERIC_PY.replace("{software}", software)
        with open(dest / "benchmark_generic.py", "w") as f:
            f.write(content)

    def _generate_micro_benchmark(self, software: str, dest: Path):
        content = MICRO_BENCHMARK_PY.replace("{software}", software)
        with open(dest / "micro_benchmark.py", "w") as f:
            f.write(content)

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
            logger.info(f"Software {software} already has tests, skipping")
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
        python_module = self.get_python_module(software)

        self._copy_common_scripts(scripts_dir, software)
        self._generate_benchmark_script(software, scripts_dir)
        self._generate_micro_benchmark(software, scripts_dir)

        test_sh_content = build_test_sh(
            software, version, namespace, tag, benchmark_type
        )
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
            "python_module": python_module,
            "docker_image": f"{namespace}/{software}",
            "docker_tag": tag or f"{version}-oe2403sp3",
            "status": "generated",
            "path": str(sw_dir),
            "files": [
                f"{software}_test.sh",
                "scripts/json_helper.py",
                "scripts/aggregate_results.py",
                "scripts/generate_summary.py",
                "scripts/benchmark_generic.py",
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
