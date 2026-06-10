#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="openviking"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-v0.3.24}"
DATA_SCALE="${DATA_SCALE:-1}"
DATA_SIZE="${DATA_SIZE:-1000}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
OPENVIKING_HOME="${SCRIPT_DIR}/openviking_install"
OPENVIKING_VENV="${SCRIPT_DIR}/venv"
LOG_FILE="${RESULTS_DIR}/workflow.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}"

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        curl -sL https://raw.githubusercontent.com/kward/shunit2/master/shunit2 \
            -o "${SCRIPT_DIR}/shunit2"
        chmod +x "${SCRIPT_DIR}/shunit2"
    fi
}

setup_venv() {
    if [ ! -d "${OPENVIKING_VENV}" ]; then
        log "SETUP" "Creating Python virtual environment..."
        python3 -m venv "${OPENVIKING_VENV}"
        "${OPENVIKING_VENV}/bin/pip" install --upgrade pip
        "${OPENVIKING_VENV}/bin/pip" install numpy pandas scipy matplotlib pyarrow requests
    fi
    export PATH="${OPENVIKING_VENV}/bin:${PATH}"
}

phase1_install() {
    log "PHASE1" "=== Phase 1: Environment Preparation & Installation ==="

    local arch
    arch="$(uname -m)"
    if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
        log "ERROR" "This benchmark requires ARM64. Current: ${arch}"
        return 1
    fi
    log "PHASE1" "ARM64 architecture verified: ${arch}"

    local os_id
    os_id="$(cat /etc/os-release 2>/dev/null | grep '^ID=' | cut -d'=' -f2 | tr -d '\"' || echo 'unknown')"
    log "PHASE1" "OS: ${os_id}"

    if [ "${os_id}" = "ubuntu" ] || [ "${os_id}" = "debian" ]; then
        log "PHASE1" "Installing system dependencies via apt..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq build-essential gcc g++ cmake curl wget git \
            python3 python3-dev python3-venv libssl-dev pkg-config
    elif [ "${os_id}" = "centos" ] || [ "${os_id}" = "rhel" ] || [ "${os_id}" = "fedora" ]; then
        log "PHASE1" "Installing system dependencies via yum/dnf..."
        sudo dnf install -y gcc gcc-c++ cmake curl wget git python3 python3-devel openssl-devel pkgconfig
    elif [ "$(uname -s)" = "Darwin" ]; then
        log "PHASE1" "macOS detected - checking Homebrew dependencies..."
        if command -v brew >/dev/null 2>&1; then
            brew install cmake python3 || true
        fi
    fi

    log "PHASE1" "Checking Python version..."
    local py_ver
    py_ver="$(python3 --version 2>&1 | tr -d '\n\t')"
    log "PHASE1" "Python: ${py_ver}"

    local py_major
    py_major="$(python3 -c 'import sys; print(sys.version_info.major)' 2>/dev/null)"
    local py_minor
    py_minor="$(python3 -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)"
    if [ "${py_major}" -lt 3 ] || [ "${py_minor}" -lt 10 ]; then
        log "ERROR" "Python 3.10+ required. Current: ${py_ver}"
        return 1
    fi

    setup_venv

    log "PHASE1" "Installing OpenViking via pip..."
    "${OPENVIKING_VENV}/bin/pip" install openviking --upgrade --force-reinstall

    local version_str="${SOFTWARE_VERSION}"
    if [ "${version_str}" != "latest" ]; then
        "${OPENVIKING_VENV}/bin/pip" install "openviking==${SOFTWARE_VERSION#v}" --force-reinstall || {
            log "WARN" "Specific version install failed, using latest available"
        }
    fi

    log "PHASE1" "Checking Rust/Cargo for CLI components..."
    if ! command -v cargo >/dev/null 2>&1; then
        log "PHASE1" "Installing Rust toolchain..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        source "${HOME}/.cargo/env"
    fi
    local cargo_ver
    cargo_ver="$(cargo --version 2>&1 | tr -d '\n\t')"
    log "PHASE1" "Cargo: ${cargo_ver}"

    log "PHASE1" "OpenViking installation directory: ${OPENVIKING_HOME}"
    mkdir -p "${OPENVIKING_HOME}"

    log "PHASE1" "Phase 1 completed successfully."
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Verify Installation ==="

    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/verify_python.py" \
        "${RESULTS_DIR}" "${SOFTWARE_VERSION}" "${OPENVIKING_VENV}"

    log "PHASE2" "Phase 2 completed."
}

run_benchmark_primary() {
    log "PHASE3a" "=== Phase 3a: LoCoMo User Memory Benchmark ==="
    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/benchmark_locomo.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}" \
        --venv "${OPENVIKING_VENV}"
    log "PHASE3a" "LoCoMo benchmark completed."
}

run_benchmark_secondary() {
    log "PHASE3b" "=== Phase 3b: HotpotQA Knowledge Base Benchmark ==="
    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/benchmark_hotpotqa.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}" \
        --venv "${OPENVIKING_VENV}"
    log "PHASE3b" "HotpotQA benchmark completed."
}

run_benchmark_micro() {
    log "PHASE3c" "=== Phase 3c: Micro Benchmarks ==="
    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}" \
        --venv "${OPENVIKING_VENV}"
    log "PHASE3c" "Micro benchmarks completed."
}

run_benchmark_stress() {
    log "PHASE3d" "=== Phase 3d: Stress Test ==="
    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}" \
        --venv "${OPENVIKING_VENV}" \
        --stress-mode
    log "PHASE3d" "Stress test completed."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            3a) run_benchmark_primary ;;
            3b) run_benchmark_secondary ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_stress ;;
            3)  run_benchmark_primary
                run_benchmark_secondary
                run_benchmark_micro
                run_benchmark_stress ;;
            *) ;;
        esac
    done
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Results Collection & Presentation ==="

    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        "${RESULTS_DIR}"

    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/generate_summary.py" \
        "${RESULTS_DIR}"

    "${OPENVIKING_VENV}/bin/python3" "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        "${RESULTS_DIR}" "${SOFTWARE_VERSION}"

    log "PHASE4" "Phase 4 completed."
    log "PHASE4" "Results at: ${RESULTS_DIR}/"
    log "PHASE4" "  all_results.json"
    log "PHASE4" "  benchmark_summary.txt"
    log "PHASE4" "  benchmark_report.html"
}

run_phases() {
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            1)  phase1_install ;;
            2)  phase2_verify ;;
            3)  phase3_run_benchmarks ;;
            3a) run_benchmark_primary ;;
            3b) run_benchmark_secondary ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_stress ;;
            4)  phase4_results ;;
            *)  log "WARN" "Unknown phase: ${p}" ;;
        esac
    done
}

run_tests() {
    download_shunit2
    log "TEST" "Running shUnit2 test suite..."
    "${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"
}

usage() {
    cat <<EOF
Usage: openviking_arm64_perf_workflow.sh [OPTIONS]

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version   Version to test (default: v0.3.24)
  -v, --data-scale         Dataset scale factor (default: 1)
  -d, --data-size          Data size in rows/samples for micro benchmarks (default: 1000)
  -i, --iterations         Number of iterations per test (default: 3)
  -t, --test-only          Run only shUnit2 validation tests
  -h, --help               Usage help
EOF
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)          PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -v|--data-scale)      DATA_SCALE="$2"; shift 2 ;;
            -d|--data-size)       DATA_SIZE="$2"; shift 2 ;;
            -i|--iterations)      ITERATIONS="$2"; shift 2 ;;
            -t|--test-only)       test_only=1; shift ;;
            -h|--help)            usage; exit 0 ;;
            *)                    log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    if [ "${test_only}" -eq 1 ]; then
        run_tests
    else
        run_phases
        run_tests
    fi
}

main "$@"