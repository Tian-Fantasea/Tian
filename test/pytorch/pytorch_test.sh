#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="pytorch"
SOFTWARE_VERSION="${PYTORCH_VERSION:-2.7.0}"
SHUNIT_PARENT="${SCRIPT_DIR}/pytorch_test.sh"

DATA_SCALE="${DATA_SCALE:-1M}"
DATA_DIM="${DATA_DIM:-128}"
ITERATIONS="${ITERATIONS:-1}"
PHASES="${PHASES:-1,2,3,4}"

LOG_FILE="${RESULTS_DIR}/results.log"

MINIMUM_THROUGHPUT=10
MAXIMUM_LATENCY_MS=1000

RESULTS_JSON="${RESULTS_DIR}/results.json"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}"

json_get() { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "${@:2}"; }
json_count_results() { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }
json_avg_throughput() { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }
json_max_latency() { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }
json_version() { python3 "${JSON_HELPER}" "$1" version; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }

download_shunit2() {
    if [ -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "shUnit2 already present at ${SCRIPT_DIR}/shunit2"
        return 0
    fi

    log "SETUP" "Downloading shUnit2..."
    local mirrors=(
        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
        "https://raw.gitmirror.com/kward/shunit2/master/shunit2"
    )
    local downloaded=0
    for mirror_url in "${mirrors[@]}"; do
        curl --connect-timeout 30 --max-time 60 -sL -o "${SCRIPT_DIR}/shunit2" "${mirror_url}" && {
            chmod +x "${SCRIPT_DIR}/shunit2"
            grep -q "^SHUNIT_VERSION=" "${SCRIPT_DIR}/shunit2" && { downloaded=1; break; }
        }
        rm -f "${SCRIPT_DIR}/shunit2"
    done
    if [ "${downloaded}" -eq 0 ]; then
        for mirror_url in "${mirrors[@]}"; do
            wget --timeout=30 --tries=2 -q -O "${SCRIPT_DIR}/shunit2" "${mirror_url}" 2>/dev/null && {
                chmod +x "${SCRIPT_DIR}/shunit2"
                grep -q "^SHUNIT_VERSION=" "${SCRIPT_DIR}/shunit2" && { downloaded=1; break; }
            }
            rm -f "${SCRIPT_DIR}/shunit2"
        done
    fi
    if [ "${downloaded}" -eq 0 ]; then
        log "ERROR" "Failed to download shUnit2"
        log "ERROR" "  Manual install: curl -L https://raw.githubusercontent.com/kward/shunit2/master/shunit2 -o ${SCRIPT_DIR}/shunit2 && chmod +x ${SCRIPT_DIR}/shunit2"
        return 1
    fi
    log "SETUP" "shUnit2 downloaded successfully"
}

check_prerequisites() {
    local errors=0

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1 | tr -d '\n\t')"
    fi

    python3 -c "import torch" 2>/dev/null
    if [ $? -ne 0 ]; then
        log "ERROR" "PyTorch is not installed. Please install torch."
        log "ERROR" "  Recommended: pip install torch==${SOFTWARE_VERSION} --index-url https://download.pytorch.org/whl/cpu"
        errors=$((errors + 1))
    else
        local pt_ver
        pt_ver="$(python3 -c 'import torch; print(torch.__version__)' 2>/dev/null | tr -d '\n\t')"
        log "CHECK" "PyTorch OK: ${pt_ver}"
    fi

    python3 -c "import numpy" 2>/dev/null
    if [ $? -ne 0 ]; then
        log "WARN" "NumPy not installed. Some benchmarks may use fallback."
    else
        log "CHECK" "NumPy OK: $(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null | tr -d '\n\t')"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

collect_version_info() {
    local timestamp arch kernel os cpu_model cores mem_mb python_ver pytorch_ver numpy_ver cuda_avail num_threads has_compile simd_str
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    python_ver="$(python3 -c 'import platform; print(platform.python_version())' 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    pytorch_ver="$(python3 -c 'import torch; print(torch.__version__)' 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    numpy_ver="$(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    cuda_avail="$(python3 -c 'import torch; print(1 if torch.cuda.is_available() else 0)' 2>/dev/null | tr -d '\n\t' || echo '0')"
    num_threads="$(python3 -c 'import torch; print(torch.get_num_threads())' 2>/dev/null | tr -d '\n\t' || echo '0')"
    has_compile="$(python3 -c 'import torch; print(1 if hasattr(torch, "compile") else 0)' 2>/dev/null | tr -d '\n\t' || echo '0')"
    simd_str="$(python3 -c 'import torch; flags=torch._C._get_cpu_feature_flags() if hasattr(torch._C, "_get_cpu_feature_flags") else []; print("NEON" if any("NEON" in str(f) for f in flags) else "0")' 2>/dev/null | tr -d '\n\t' || echo '0')"

    python3 "${JSON_HELPER}" "${RESULTS_JSON}" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "pytorch" "${SOFTWARE_VERSION}" \
        "${python_ver}" "${pytorch_ver}" "${numpy_ver}" \
        "${cuda_avail}" "${num_threads}" "${has_compile}" "${simd_str}"
}

run_benchmarks() {
    log "PHASE3" "Running benchmarks..."
    local has_compute=0 has_training=0 has_micro=0
    local IFS=','
    for p in ${PHASES}; do
        case "${p}" in
            3|3a) has_compute=1 ;;
            3b) has_training=1 ;;
            3c) has_micro=1 ;;
        esac
    done

    if [ "${has_compute}" -eq 1 ]; then
        log "PHASE3a" "Running compute benchmark..."
        python3 "${SCRIPT_DIR}/scripts/benchmark_compute.py" \
            --results-dir "${RESULTS_DIR}" \
            --iterations "${ITERATIONS}" \
            --data-dim "${DATA_DIM}" \
            --results-json "${RESULTS_JSON}" \
            --section compute_benchmark
    fi

    if [ "${has_training}" -eq 1 ]; then
        log "PHASE3b" "Running training benchmark..."
        python3 "${SCRIPT_DIR}/scripts/benchmark_training.py" \
            --results-dir "${RESULTS_DIR}" \
            --iterations "${ITERATIONS}" \
            --data-scale "${DATA_SCALE}" \
            --results-json "${RESULTS_JSON}" \
            --section training_benchmark
    fi

    if [ "${has_micro}" -eq 1 ]; then
        log "PHASE3c" "Running micro benchmarks..."
        python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
            --results-dir "${RESULTS_DIR}" \
            --iterations "${ITERATIONS}" \
            --data-dim "${DATA_DIM}" \
            --results-json "${RESULTS_JSON}" \
            --section micro_benchmark
    fi
}

generate_reports() {
    log "PHASE4" "Generating summary and HTML report"
    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --input "${RESULTS_JSON}" \
        --output "${RESULTS_DIR}/results.txt"
    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --input "${RESULTS_JSON}" \
        --output "${RESULTS_DIR}/results.html"
    log "PHASE4" "Reports generated: results.txt, results.html"
}

oneTimeSetUp() {
    log "LIFECYCLE" "oneTimeSetUp: Check prerequisites + Collect version info + Run benchmarks"

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        return 1
    fi

    collect_version_info
    run_benchmarks
}

setUp() {
    rm -f "${RESULTS_DIR}/test_temp_*.json"
}

tearDown() {
    rm -f "${RESULTS_DIR}/test_temp_*.json"
}

oneTimeTearDown() {
    log "LIFECYCLE" "oneTimeTearDown: Generate reports"
    generate_reports
}

testArchitectureIsARM64() {
    local arch
    arch="$(uname -m)"
    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \
        "[ '${arch}' = 'aarch64' ] || [ '${arch}' = 'arm64' ]"
}

testPytorchIsInstalled() {
    local found=0
    python3 -c "import torch" 2>/dev/null && found=1
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: PyTorch not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "PyTorch should be importable" "[ ${found} -eq 1 ]"
}

testResultsJsonExists() {
    assertTrue "results.json should exist" "[ -f '${RESULTS_JSON}' ]"
}

testResultsJsonHasVersionInfo() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_vi
    has_vi="$(json_field_exists "${RESULTS_JSON}" version_info)"
    assertTrue "results.json should have version_info section" "[ ${has_vi} -eq 1 ]"
}

testResultsJsonHasArchitecture() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_arch
    has_arch="$(json_field_exists "${RESULTS_JSON}" version_info architecture)"
    assertTrue "results.json version_info should have architecture" "[ ${has_arch} -eq 1 ]"
}

testResultsJsonHasSoftwareVersion() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_ver
    has_ver="$(json_field_exists "${RESULTS_JSON}" version_info software_version)"
    assertTrue "results.json version_info should have version" "[ ${has_ver} -eq 1 ]"
}

testBenchmarkComputeInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_compute
    has_compute="$(json_field_exists "${RESULTS_JSON}" compute_benchmark)"
    assertTrue "results.json should contain compute_benchmark data" "[ ${has_compute} -eq 1 ]"
}

testBenchmarkComputeHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_bench has_metrics has_results
    has_bench="$(json_field_exists "${RESULTS_JSON}" compute_benchmark benchmark)"
    has_metrics="$(json_field_exists "${RESULTS_JSON}" compute_benchmark performance_metrics)"
    has_results="$(json_field_exists "${RESULTS_JSON}" compute_benchmark results)"
    assertTrue "compute_benchmark should have benchmark field" "[ ${has_bench} -eq 1 ]"
    assertTrue "compute_benchmark should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "compute_benchmark should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkTrainingInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_training
    has_training="$(json_field_exists "${RESULTS_JSON}" training_benchmark)"
    assertTrue "results.json should contain training_benchmark data" "[ ${has_training} -eq 1 ]"
}

testBenchmarkMicroInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_micro
    has_micro="$(json_field_exists "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "results.json should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
}

testBenchmarkMicroAllOperationsCompleted() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local ops_count
    ops_count="$(json_count_results "${RESULTS_JSON}")"
    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -gt 0 ]"
}

testResultsJsonContainsAllBenchmarks() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_compute has_training has_micro
    has_compute="$(json_contains "${RESULTS_JSON}" compute_benchmark)"
    has_training="$(json_contains "${RESULTS_JSON}" training_benchmark)"
    has_micro="$(json_contains "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "Should contain compute_benchmark data" "[ ${has_compute} -eq 1 ]"
    assertTrue "Should contain training_benchmark data" "[ ${has_training} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
}

testHtmlReportGenerated() {
    assertTrue "results.html should exist" "[ -f '${RESULTS_DIR}/results.html' ]"
}

testSummaryReportGenerated() {
    assertTrue "results.txt should exist" "[ -f '${RESULTS_DIR}/results.txt' ]"
}

testLogFileGenerated() {
    assertTrue "results.log should exist" "[ -f '${LOG_FILE}' ]"
}

usage() {
    cat <<EOF
Usage: pytorch_test.sh [OPTIONS]

PyTorch ARM64 Performance Benchmark (shUnit2)

Prerequisites (must be pre-installed):
  - Python 3.8+
  - PyTorch ${SOFTWARE_VERSION}
  - NumPy (optional)
  - scripts/json_helper.py

Note: shUnit2 will be auto-downloaded if not present.

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c)
  -s, --software-version   PyTorch version (default: ${SOFTWARE_VERSION})
  -v, --data-scale         Dataset scale: 1M, 10M (default: ${DATA_SCALE})
  -d, --data-dim           Data dimension for micro benchmarks (default: ${DATA_DIM})
  -i, --iterations         Iterations per test (default: ${ITERATIONS})
  --check                  Check prerequisites only (no benchmark)
  -h, --help               Usage help

Examples:
  ./pytorch_test.sh                     # Full run + shUnit2 validation
  ./pytorch_test.sh --check             # Check prerequisites only
  ./pytorch_test.sh -p 3a,3b            # Only compute and training benchmarks
  ./pytorch_test.sh -i 5                # 5 iterations
EOF
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)          PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -v|--data-scale)      DATA_SCALE="$2"; shift 2 ;;
            -d|--data-dim)        DATA_DIM="$2"; shift 2 ;;
            -i|--iterations)      ITERATIONS="$2"; shift 2 ;;
            --check)              check_only=1; shift ;;
            -h|--help)            usage; exit 0 ;;
            *)                    log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    log "START" "PyTorch ARM64 Benchmark v${SOFTWARE_VERSION}"

    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        exit 1
    fi

    download_shunit2 || {
        log "FATAL" "Failed to download shUnit2. Please install manually."
        exit 1
    }

    log "TEST" "Running shUnit2 test suite..."
    . "${SCRIPT_DIR}/shunit2"
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
