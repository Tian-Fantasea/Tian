#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="bolt"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-1.4.3}"
DATA_SCALE="${DATA_SCALE:-1}"
DATA_SIZE="${DATA_SIZE:-100000}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
GO_VERSION="${GO_VERSION:-1.23.7}"
BOLT_HOME="${SCRIPT_DIR}/bolt_home"
LOG_FILE="${RESULTS_DIR}/workflow.log"
NPROC="$(nproc 2>/dev/null || echo 4)"
TOTAL_MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 8388608)"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        curl -sL https://raw.githubusercontent.com/kward/shunit2/master/shunit2 \
            -o "${SCRIPT_DIR}/shunit2"
        chmod +x "${SCRIPT_DIR}/shunit2"
    fi
}

phase1_install() {
    local arch
    arch="$(uname -m)"
    log "PHASE1" "Architecture: ${arch}"
    if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
        log "ERROR" "This benchmark requires ARM64. Current: ${arch}"
        return 1
    fi

    log "PHASE1" "Installing system dependencies..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq 2>/dev/null
        apt-get install -y -qq curl wget python3 python3-venv bc git gcc 2>/dev/null
    elif command -v yum >/dev/null 2>&1; then
        yum install -y -q curl wget python3 python3-pip bc git gcc 2>/dev/null
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y -q curl wget python3 python3-pip bc git gcc 2>/dev/null
    fi

    log "PHASE1" "Installing Go ${GO_VERSION} for ARM64..."
    local need_install=0
    if command -v go >/dev/null 2>&1; then
        local current_ver
        current_ver="$(go version | grep -oP 'go\K[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)"
        local required_minor
        required_minor="$(echo "${GO_VERSION}" | cut -d. -f2)"
        local current_minor
        current_minor="$(echo "${current_ver}" | cut -d. -f2)"
        if [ "${current_minor}" -lt "${required_minor}" ]; then
            log "PHASE1" "Go ${current_ver} installed but ${GO_VERSION} required, upgrading..."
            need_install=1
        else
            log "PHASE1" "Go ${current_ver} already installed, sufficient"
        fi
    else
        need_install=1
    fi
    if [ "${need_install}" -eq 1 ]; then
        local go_tgz="/tmp/go${GO_VERSION}.linux-arm64.tar.gz"
        local go_mirrors=(
            "https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz"
            "https://mirrors.aliyun.com/golang/go${GO_VERSION}.linux-arm64.tar.gz"
            "https://dl.google.com/go/go${GO_VERSION}.linux-arm64.tar.gz"
        )
        local downloaded=0
        rm -f "${go_tgz}"
        for mirror_url in "${go_mirrors[@]}"; do
            log "PHASE1" "Trying: ${mirror_url}"
            wget --timeout=60 --tries=2 -q -O "${go_tgz}" "${mirror_url}" 2>/dev/null && {
                file "${go_tgz}" | grep -q "gzip" && {
                    downloaded=1
                    log "PHASE1" "Download succeeded from: ${mirror_url}"
                    break
                }
            }
            rm -f "${go_tgz}"
        done
        if [ "${downloaded}" -eq 0 ]; then
            for mirror_url in "${go_mirrors[@]}"; do
                log "PHASE1" "Retrying with curl: ${mirror_url}"
                curl --connect-timeout 60 --max-time 600 -L -o "${go_tgz}" "${mirror_url}" 2>/dev/null && {
                    file "${go_tgz}" | grep -q "gzip" && {
                        downloaded=1
                        log "PHASE1" "Download succeeded (curl) from: ${mirror_url}"
                        break
                    }
                }
                rm -f "${go_tgz}"
            done
        fi
        if [ "${downloaded}" -eq 0 ]; then
            log "ERROR" "Go download failed. Install manually: https://go.dev/dl/"
            return 1
        fi
        tar -C /usr/local -xzf "${go_tgz}"
        rm -f "${go_tgz}"
        export PATH="/usr/local/go/bin:${PATH}"
        echo 'export PATH=/usr/local/go/bin:$PATH' >> /etc/profile.d/go.sh
    fi
    export PATH="/usr/local/go/bin:${PATH}"
    log "PHASE1" "Go version: $(go version | head -1)"

    log "PHASE1" "Installing Python dependencies via venv..."
    if [ ! -f "${SCRIPT_DIR}/venv/bin/pip" ]; then
        rm -rf "${SCRIPT_DIR}/venv"
        python3 -m venv "${SCRIPT_DIR}/venv"
        "${SCRIPT_DIR}/venv/bin/pip" install --quiet --upgrade pip
    fi
    "${SCRIPT_DIR}/venv/bin/pip" install --quiet numpy pandas scipy matplotlib
    export PATH="${SCRIPT_DIR}/venv/bin:${PATH}"

    log "PHASE1" "Setting up bbolt and compiling benchmark programs..."
    mkdir -p "${BOLT_HOME}"
    export GOPATH="${BOLT_HOME}/go"
    export GOBIN="${GOPATH}/bin"
    cd "${BOLT_HOME}"
    mkdir -p src/benchmark
    cat > src/benchmark/go.mod << 'GOMOD'
module benchmark

go 1.23

require go.etcd.io/bbolt v1.4.3
GOMOD

    for bench_src in "${SCRIPT_DIR}/scripts"/*.go; do
        local bench_name
        bench_name="$(basename "${bench_src}" .go)"
        cp "${bench_src}" "${BOLT_HOME}/src/benchmark/${bench_name}.go"
    done

    log "PHASE1" "Downloading bbolt module..."
    cd "${BOLT_HOME}/src/benchmark"
    GOTOOLCHAIN=local go mod tidy
    if [ ! -f "go.sum" ]; then
        log "ERROR" "go.sum not generated, go mod tidy failed"
        return 1
    fi

    for bench_src in "${SCRIPT_DIR}/scripts"/*.go; do
        local bench_name
        bench_name="$(basename "${bench_src}" .go)"
        log "PHASE1" "Compiling ${bench_name}..."
        cd "${BOLT_HOME}/src/benchmark"
        GOTOOLCHAIN=local go build -o "${SCRIPT_DIR}/scripts/${bench_name}" "${bench_name}.go"
    done
    cd "${SCRIPT_DIR}"

    log "PHASE1" "Phase 1 complete"
}

phase2_verify() {
    log "PHASE2" "Verifying installation & collecting version info"

    local db_path="${RESULTS_DIR}/verify_test.db"
    rm -f "${db_path}"

    "${SCRIPT_DIR}/scripts/micro_benchmark" --mode verify --db-path "${db_path}" --results-dir "${RESULTS_DIR}"

    if [ ! -f "${db_path}" ]; then
        log "ERROR" "bbolt database creation failed"
        return 1
    fi
    rm -f "${db_path}"

    log "PHASE2" "Collecting version info..."
    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local arch
    arch="$(uname -m)"
    local kernel
    kernel="$(uname -r | tr -d '\n\t')"
    local os
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || uname -s | tr -d '\n\t')"
    local cpu_model
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'ARM64 CPU')"
    local cores="${NPROC}"
    local mem_mb
    mem_mb="$(echo "${TOTAL_MEM_KB} / 1024" | bc 2>/dev/null || echo 8192)"
    local go_ver
    go_ver="$(go version 2>&1 | head -1 | tr -d '\n\t')"
    local bolt_ver="${SOFTWARE_VERSION}"

    mkdir -p "${RESULTS_DIR}"
    python3 "${SCRIPT_DIR}/scripts/json_helper.py" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" "${cores}" "${mem_mb}" \
        "${SOFTWARE_VERSION}" "go" "${go_ver}" "${BOLT_HOME}" "${cores}" "${cores}"

    log "PHASE2" "Version info saved to ${RESULTS_DIR}/version_info.json"
    log "PHASE2" "Phase 2 complete"
}

run_benchmark_ycsb() {
    log "PHASE3a" "Running YCSB-like workload benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_ycsb" \
        --key-count "${DATA_SIZE}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

run_benchmark_throughput() {
    log "PHASE3b" "Running throughput scaling benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_throughput" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

run_benchmark_micro() {
    log "PHASE3c" "Running micro benchmarks..."
    "${SCRIPT_DIR}/scripts/micro_benchmark" \
        --mode full \
        --key-count "${DATA_SIZE}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

run_benchmark_concurrency() {
    log "PHASE3d" "Running concurrency scaling benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_concurrency" \
        --key-count "${DATA_SIZE}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

phase3_run_benchmarks() {
    log "PHASE3" "Running performance benchmarks"
    run_benchmark_ycsb
    run_benchmark_throughput
    run_benchmark_micro
    run_benchmark_concurrency
    log "PHASE3" "All benchmarks complete"
}

phase4_results() {
    log "PHASE4" "Collecting & presenting results"

    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/aggregate_results.py" --results-dir "${RESULTS_DIR}"
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/generate_summary.py" --results-dir "${RESULTS_DIR}"
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/generate_html_report.py" --results-dir "${RESULTS_DIR}"

    log "PHASE4" "Results saved:"
    log "PHASE4" "  JSON:   ${RESULTS_DIR}/all_results.json"
    log "PHASE4" "  Summary: ${RESULTS_DIR}/benchmark_summary.txt"
    log "PHASE4" "  HTML:   ${RESULTS_DIR}/benchmark_report.html"
    log "PHASE4" "Phase 4 complete"
}

run_tests() {
    download_shunit2
    log "TEST" "Running shUnit2 test suite..."
    "${SCRIPT_DIR}/bolt_arm64_perf_test.sh"
}

usage() {
    cat <<EOF
Usage: bolt_arm64_perf_workflow.sh [OPTIONS]

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version   bbolt version (default: 1.4.3)
  -v, --data-scale         Dataset scale factor (default: 1)
  -d, --data-size          Number of keys for benchmarks (default: 100000)
  -i, --iterations         Iterations per test (default: 3)
  -g, --go-version         Go version to install (default: 1.22.7)
  -t, --test-only          Run only shUnit2 validation tests
  -h, --help               Usage help
EOF
}

run_phases() {
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            1)  phase1_install ;;
            2)  phase2_verify ;;
            3)  phase3_run_benchmarks ;;
            3a) run_benchmark_ycsb ;;
            3b) run_benchmark_throughput ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_concurrency ;;
            4)  phase4_results ;;
            *)  log "WARN" "Unknown phase: ${p}" ;;
        esac
    done
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)        PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -v|--data-scale)    DATA_SCALE="$2"; shift 2 ;;
            -d|--data-size)     DATA_SIZE="$2"; shift 2 ;;
            -i|--iterations)    ITERATIONS="$2"; shift 2 ;;
            -g|--go-version)    GO_VERSION="$2"; shift 2 ;;
            -t|--test-only)     test_only=1; shift ;;
            -h|--help)          usage; exit 0 ;;
            *)                  log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    mkdir -p "${RESULTS_DIR}"
    : > "${LOG_FILE}"

    if [ "${test_only}" -eq 1 ]; then
        run_tests
    else
        run_phases
        run_tests
    fi
}

main "$@"