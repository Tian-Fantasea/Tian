#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="rocksdb"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-9.10.0}"
DATA_SCALE="${DATA_SCALE:-1}"
DATA_SIZE="${DATA_SIZE:-1000000}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
NUM_KEYS="${NUM_KEYS:-1000000}"
VALUE_SIZE="${VALUE_SIZE:-256}"
THREADS="${THREADS:-16}"
DB_BENCH_PATH="${DB_BENCH_PATH:-${SCRIPT_DIR}/rocksdb_src/db_bench}"
VENV_DIR="${SCRIPT_DIR}/venv"
LOG_FILE="${RESULTS_DIR}/workflow.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}" "${SCRIPT_DIR}/scripts"

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        curl -sL https://raw.githubusercontent.com/kward/shunit2/master/shunit2 \
            -o "${SCRIPT_DIR}/shunit2"
        chmod +x "${SCRIPT_DIR}/shunit2"
    fi
}

phase1_install() {
    log "PHASE1" "=== Phase 1: Environment Preparation & Installation ==="

    local arch
    arch="$(uname -m)"
    if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
        log "ERROR" "This benchmark requires ARM64. Current: ${arch}"
        return 1
    fi
    log "PHASE1" "ARM64 architecture confirmed: ${arch}"

    if [ "$(uname -s)" = "Darwin" ]; then
        log "PHASE1" "macOS detected, using Homebrew for dependencies..."
        brew install cmake gflags snappy lz4 zlib zstd jemalloc gcc || true
    else
        log "PHASE1" "Linux detected, installing system dependencies..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get update -qq
            sudo apt-get install -y -qq build-essential cmake libgflags-dev \
                libsnappy-dev liblz4-dev zlib1g-dev libzstd-dev libjemalloc-dev \
                libbz2-dev liburing-dev git curl wget python3 python3-venv
        elif command -v yum &>/dev/null; then
            sudo yum install -y gcc gcc-c++ cmake gflags-devel snappy-devel \
                lz4-devel zlib-devel libzstd-devel jemalloc-devel bzip2-devel \
                liburing-devel git curl wget python3
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y gcc gcc-c++ cmake gflags-devel snappy-devel \
                lz4-devel zlib-devel libzstd-devel jemalloc-devel bzip2-devel \
                liburing-devel git curl wget python3
        fi
    fi

    log "PHASE1" "Setting up Python venv..."
    python3 -m venv "${VENV_DIR}"
    "${VENV_DIR}/bin/pip" install --quiet numpy
    export PATH="${VENV_DIR}/bin:${PATH}"

    log "PHASE1" "Cloning RocksDB repository..."
    local rocksdb_src="${SCRIPT_DIR}/rocksdb_src"
    if [ ! -d "${rocksdb_src}" ]; then
        local mirrors=(
            "https://github.com/facebook/rocksdb.git"
            "https://hub.fastgit.xyz/facebook/rocksdb.git"
            "https://gitclone.com/github.com/facebook/rocksdb.git"
        )
        local cloned=0
        for mirror_url in "${mirrors[@]}"; do
            git clone --depth=1 --branch="v${SOFTWARE_VERSION}" "${mirror_url}" "${rocksdb_src}" 2>/dev/null && {
                cloned=1
                break
            }
            rm -rf "${rocksdb_src}"
        done
        if [ "${cloned}" -eq 0 ]; then
            log "ERROR" "Failed to clone RocksDB. Trying without branch tag..."
            git clone --depth=1 "https://github.com/facebook/rocksdb.git" "${rocksdb_src}" || {
                log "ERROR" "All clone attempts failed. Please clone manually."
                return 1
            }
        fi
    fi

    log "PHASE1" "Building RocksDB and db_bench (Release mode with ARM64 optimizations)..."
    cd "${rocksdb_src}"

    if [ "$(uname -s)" = "Darwin" ]; then
        make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu) db_bench \
            OPT="-O2 -march=armv8-a+crc+crypto" \
            PORTABLE=1 \
            USE_JEMALLOC=1
    else
        make -j$(nproc) db_bench \
            OPT="-O2 -march=armv8-a+crc+crypto" \
            PORTABLE=1 \
            USE_JEMALLOC=1
    fi

    DB_BENCH_PATH="${rocksdb_src}/db_bench"
    if [ ! -f "${DB_BENCH_PATH}" ]; then
        log "ERROR" "db_bench build failed!"
        return 1
    fi

    log "PHASE1" "Building RocksDB static library..."
    if [ "$(uname -s)" = "Darwin" ]; then
        make -j$(sysctl -n hw.ncpu) static_lib OPT="-O2" PORTABLE=1 USE_JEMALLOC=1
    else
        make -j$(nproc) static_lib OPT="-O2" PORTABLE=1 USE_JEMALLOC=1
    fi

    log "PHASE1" "Verifying ARM64 CRC32C support..."
    if grep -q "crc32c_arm64" "${rocksdb_src}/util/crc32c_arm64.cc" 2>/dev/null; then
        log "PHASE1" "ARM64 CRC32C implementation found"
    fi

    log "PHASE1" "Checking NEON/SIMD availability..."
    local neon_check
    if [ "$(uname -s)" = "Darwin" ]; then
        neon_check="$(sysctl -a 2>/dev/null | grep -c hw.optional.neon || echo 1)"
    else
        neon_check="$(grep -c 'neon' /proc/cpuinfo 2>/dev/null || echo 0)"
        if [ "${neon_check}" -eq 0 ]; then
            neon_check="$(cat /proc/cpuinfo | grep -c 'asimd' 2>/dev/null || echo 0)"
        fi
    fi
    log "PHASE1" "NEON/ASIMD support indicators: ${neon_check}"

    log "PHASE1" "Phase 1 complete. db_bench at: ${DB_BENCH_PATH}"
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Installation Verification ==="

    python3 "${SCRIPT_DIR}/scripts/verify_rocksdb.py" \
        --results-dir "${RESULTS_DIR}" \
        --db-bench "${DB_BENCH_PATH}" \
        --rocksdb-version "${SOFTWARE_VERSION}" \
        --rocksdb-src "${SCRIPT_DIR}/rocksdb_src"

    log "PHASE2" "Phase 2 complete."
}

run_benchmark_primary() {
    log "PHASE3A" "=== Phase 3a: YCSB Benchmark ==="
    python3 "${SCRIPT_DIR}/scripts/benchmark_ycsb.py" \
        --results-dir "${RESULTS_DIR}" \
        --db-bench "${DB_BENCH_PATH}" \
        --num-keys "${NUM_KEYS}" \
        --value-size "${VALUE_SIZE}" \
        --threads "${THREADS}" \
        --iterations "${ITERATIONS}"
}

run_benchmark_secondary() {
    log "PHASE3B" "=== Phase 3b: db_bench Compaction & Filter Benchmark ==="
    python3 "${SCRIPT_DIR}/scripts/benchmark_dbbench.py" \
        --results-dir "${RESULTS_DIR}" \
        --db-bench "${DB_BENCH_PATH}" \
        --num-keys "${NUM_KEYS}" \
        --value-size "${VALUE_SIZE}" \
        --threads "${THREADS}" \
        --iterations "${ITERATIONS}"
}

run_benchmark_micro() {
    log "PHASE3C" "=== Phase 3c: Micro Benchmarks ==="
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --db-bench "${DB_BENCH_PATH}" \
        --num-keys "${NUM_KEYS}" \
        --value-size "${VALUE_SIZE}" \
        --iterations "${ITERATIONS}"
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Running Benchmarks ==="
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            3a) run_benchmark_primary ;;
            3b) run_benchmark_secondary ;;
            3c) run_benchmark_micro ;;
            3)  run_benchmark_primary; run_benchmark_secondary; run_benchmark_micro ;;
        esac
    done
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Results Collection & Presentation ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" --results-dir "${RESULTS_DIR}"
    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" --results-dir "${RESULTS_DIR}"
    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" --results-dir "${RESULTS_DIR}"

    log "PHASE4" "Phase 4 complete. Results in: ${RESULTS_DIR}"
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
            4)  phase4_results ;;
            *)  log "WARN" "Unknown phase: ${p}" ;;
        esac
    done
}

run_tests() {
    download_shunit2
    log "TEST" "Running shUnit2 test suite..."
    export DB_BENCH_PATH RESULTS_DIR SOFTWARE_VERSION
    "${SCRIPT_DIR}/rocksdb_arm64_perf_test.sh"
}

usage() {
    cat <<EOF
Usage: rocksdb_arm64_perf_workflow.sh [OPTIONS]

Options:
  -p, --phases PHASES        Comma-separated phases (1,2,3,4 or 3a,3b,3c)
  -s, --software-version VER Version to test (default: 9.10.0)
  -n, --num-keys N           Number of keys for benchmarks (default: 1000000)
  -V, --value-size SIZE      Value size in bytes (default: 256)
  -t, --threads T            Number of threads (default: 16)
  -i, --iterations I         Number of iterations per test (default: 3)
  -T, --test-only            Run only shUnit2 validation tests
  -h, --help                 Usage help
EOF
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)          PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -n|--num-keys)        NUM_KEYS="$2"; shift 2 ;;
            -V|--value-size)      VALUE_SIZE="$2"; shift 2 ;;
            -t|--threads)         THREADS="$2"; shift 2 ;;
            -i|--iterations)      ITERATIONS="$2"; shift 2 ;;
            -T|--test-only)       test_only=1; shift ;;
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