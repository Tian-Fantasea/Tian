#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="redis"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-8.0.2}"
DATA_SCALE="${DATA_SCALE:-1}"
ITERATIONS="${ITERATIONS:-3}"
DATA_SIZE="${DATA_SIZE:-1000000}"
PHASES="${PHASES:-1,2,3,4}"
REDIS_PORT="${REDIS_PORT:-6380}"
REDIS_PID=""
REDIS_HOME="${SCRIPT_DIR}/redis-${SOFTWARE_VERSION}"
LOG_FILE="${RESULTS_DIR}/workflow.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}" "${SCRIPT_DIR}/scripts"

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        local mirrors=(
            "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
            "https://mirrors.aliyun.com/githubraw/kward/shunit2/master/shunit2"
            "https://cdn.jsdelivr.net/gh/kward/shunit2@master/shunit2"
        )
        local downloaded=0
        for mirror_url in "${mirrors[@]}"; do
            curl --connect-timeout 30 --max-time 120 -sL "${mirror_url}" -o "${SCRIPT_DIR}/shunit2" 2>/dev/null && {
                file "${SCRIPT_DIR}/shunit2" | grep -qi "shell script\|text" && { downloaded=1; break; }
            }
            rm -f "${SCRIPT_DIR}/shunit2"
        done
        if [ "${downloaded}" -eq 0 ]; then
            for mirror_url in "${mirrors[@]}"; do
                wget --timeout=30 --tries=2 -q -O "${SCRIPT_DIR}/shunit2" "${mirror_url}" 2>/dev/null && {
                    file "${SCRIPT_DIR}/shunit2" | grep -qi "shell script\|text" && { downloaded=1; break; }
                }
                rm -f "${SCRIPT_DIR}/shunit2"
            done
        fi
        if [ "${downloaded}" -eq 0 ]; then
            log "ERROR" "Failed to download shUnit2. Please download manually."
            return 1
        fi
        chmod +x "${SCRIPT_DIR}/shunit2"
        log "SETUP" "shUnit2 downloaded successfully."
    fi
}

download_redis() {
    local tgz="${SCRIPT_DIR}/redis-${SOFTWARE_VERSION}.tar.gz"
    local mirrors=(
        "https://github.com/redis/redis/archive/refs/tags/${SOFTWARE_VERSION}.tar.gz"
        "https://mirrors.aliyun.com/github.com/redis/redis/archive/refs/tags/${SOFTWARE_VERSION}.tar.gz"
        "https://ghproxy.com/https://github.com/redis/redis/archive/refs/tags/${SOFTWARE_VERSION}.tar.gz"
        "https://mirror.ghproxy.com/https://github.com/redis/redis/archive/refs/tags/${SOFTWARE_VERSION}.tar.gz"
    )
    local downloaded=0
    for mirror_url in "${mirrors[@]}"; do
        wget --timeout=60 --tries=2 -q -O "${tgz}" "${mirror_url}" 2>/dev/null && {
            file "${tgz}" | grep -q "gzip" && { downloaded=1; break; }
        }
        rm -f "${tgz}"
    done
    if [ "${downloaded}" -eq 0 ]; then
        for mirror_url in "${mirrors[@]}"; do
            curl --connect-timeout 60 --max-time 600 -L -o "${tgz}" "${mirror_url}" 2>/dev/null && {
                file "${tgz}" | grep -q "gzip" && { downloaded=1; break; }
            }
            rm -f "${tgz}"
        done
    fi
    if [ "${downloaded}" -eq 0 ]; then
        log "ERROR" "All mirrors failed for Redis ${SOFTWARE_VERSION}. Please download manually."
        return 1
    fi
    tar xzf "${tgz}" -C "${SCRIPT_DIR}"
    rm -f "${tgz}"
    log "PHASE1" "Redis ${SOFTWARE_VERSION} source downloaded."
}

start_redis_server() {
    local config="${REDIS_HOME}/redis.conf"
    if [ ! -f "${config}" ]; then
        config="${REDIS_HOME}/redis-full.conf"
    fi
    local tmp_config="${RESULTS_DIR}/redis_bench.conf"
    cp "${config}" "${tmp_config}"
    sed -i "s/^port .*/port ${REDIS_PORT}/" "${tmp_config}"
    sed -i "s/^daemonize .*/daemonize yes/" "${tmp_config}"
    sed -i "s/^pidfile .*/pidfile ${RESULTS_DIR}/redis_bench.pid/" "${tmp_config}"
    sed -i "s/^logfile .*/logfile ${RESULTS_DIR}/redis_bench.log/" "${tmp_config}"
    sed -i "s/^dir .*/dir ${RESULTS_DIR}/" "${tmp_config}"
    sed -i "s/^bind .*/bind 127.0.0.1/" "${tmp_config}"
    sed -i "s/^# maxmemory .*/maxmemory 512mb/" "${tmp_config}"
    sed -i "s/^tcp-backlog .*/tcp-backlog 511/" "${tmp_config}"
    "${REDIS_HOME}/src/redis-server" "${tmp_config}" 2>&1
    sleep 2
    local pid_check
    pid_check="$(cat "${RESULTS_DIR}/redis_bench.pid" 2>/dev/null || echo "")"
    if [ -n "${pid_check}" ] && kill -0 "${pid_check}" 2>/dev/null; then
        REDIS_PID="${pid_check}"
        log "PHASE1" "Redis server started on port ${REDIS_PORT}, PID=${REDIS_PID}"
    else
        log "ERROR" "Redis server failed to start."
        return 1
    fi
}

stop_redis_server() {
    if [ -n "${REDIS_PID}" ] && kill -0 "${REDIS_PID}" 2>/dev/null; then
        "${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" SHUTDOWN NOSAVE 2>/dev/null || true
        sleep 1
        kill -9 "${REDIS_PID}" 2>/dev/null || true
        log "PHASE1" "Redis server stopped."
    fi
    REDIS_PID=""
}

phase1_install() {
    log "PHASE1" "Starting Phase 1: Environment Preparation & Installation"

    local arch
    arch="$(uname -m)"
    if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
        log "ERROR" "This benchmark requires ARM64. Current: ${arch}"
        return 1
    fi

    log "PHASE1" "Detected architecture: ${arch}"

    if [ "$(uname -s)" = "Darwin" ]; then
        log "PHASE1" "macOS detected. Checking build dependencies..."
        if ! command -v make &>/dev/null; then
            log "PHASE1" "Installing make via Homebrew..."
            brew install make 2>/dev/null || true
        fi
        if ! command -v cmake &>/dev/null; then
            log "PHASE1" "Installing cmake via Homebrew..."
            brew install cmake 2>/dev/null || true
        fi
    else
        log "PHASE1" "Linux detected. Installing build dependencies..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get update -qq
            sudo apt-get install -y --no-install-recommends gcc g++ libc6-dev libssl-dev make cmake python3 python3-pip python3-venv python3-dev git wget curl 2>/dev/null || true
        elif command -v yum &>/dev/null || command -v dnf &>/dev/null; then
            sudo yum install -y gcc gcc-c++ openssl-devel make cmake python3 python3-devel git wget curl 2>/dev/null || true
        elif command -v apk &>/dev/null; then
            apk add --no-cache build-base openssl openssl-dev cmake python3 python3-dev git wget curl bash 2>/dev/null || true
        fi
    fi

    log "PHASE1" "Setting up Python venv..."
    python3 -m venv "${SCRIPT_DIR}/venv" 2>/dev/null || true
    "${SCRIPT_DIR}/venv/bin/pip" install --upgrade pip 2>/dev/null || true
    "${SCRIPT_DIR}/venv/bin/pip" install numpy 2>/dev/null || true
    export PATH="${SCRIPT_DIR}/venv/bin:${PATH}"

    log "PHASE1" "Downloading Redis ${SOFTWARE_VERSION}..."
    download_redis

    log "PHASE1" "Building Redis ${SOFTWARE_VERSION} on ARM64..."
    make -C "${REDIS_HOME}" -j "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)" 2>&1 | tee -a "${LOG_FILE}"

    if [ ! -x "${REDIS_HOME}/src/redis-server" ]; then
        log "ERROR" "Redis build failed. redis-server binary not found."
        return 1
    fi

    log "PHASE1" "Redis build successful."

    log "PHASE1" "Starting Redis server for benchmarking..."
    start_redis_server

    log "PHASE1" "Phase 1 complete."
}

phase2_verify() {
    log "PHASE2" "Starting Phase 2: Installation Verification"

    "${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>&1 | tee -a "${LOG_FILE}"

    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || python3 -c "import datetime; print(datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))")"
    local arch
    arch="$(uname -m)"
    local kernel
    kernel="$(uname -r | tr -d '\n\t')"
    local os
    os="$(uname -s | tr -d '\n\t')"
    local cpu_model
    if [ "$(uname -s)" = "Darwin" ]; then
        cpu_model="$(sysctl -n machdep.cpu.brand_string 2>/dev/null | tr -d '\n\t' || echo 'Unknown')"
    else
        cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'Unknown')"
    fi
    local cores
    cores="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
    local mem_mb
    if [ "$(uname -s)" = "Darwin" ]; then
        mem_mb="$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0f", $1/1048576}' || echo 0)"
    else
        mem_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"
    fi
    local redis_ver
    redis_ver="$(tr -d '\n\t' <<< "$("${REDIS_HOME}/src/redis-server" --version 2>&1 | grep -oP 'v=[\d.]+' | cut -d= -f2)")"
    local gcc_ver
    gcc_ver="$(gcc --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'N/A')"

    python3 "${SCRIPT_DIR}/scripts/json_helper.py" \
        "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${redis_ver}" "${gcc_ver}" \
        "N/A" "${REDIS_HOME}" "${cores}" "${cores}"

    bash "${SCRIPT_DIR}/scripts/verify_c.sh" "${REDIS_HOME}" "${REDIS_PORT}" "${RESULTS_DIR}" 2>&1 | tee -a "${LOG_FILE}"

    log "PHASE2" "Phase 2 complete."
}

run_benchmark_ycsb() {
    log "PHASE3a" "Running YCSB benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_ycsb.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}" \
        2>&1 | tee -a "${LOG_FILE}"
    log "PHASE3a" "YCSB benchmark complete."
}

run_benchmark_throughput() {
    log "PHASE3b" "Running throughput benchmark at various load levels..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_throughput.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        2>&1 | tee -a "${LOG_FILE}"
    log "PHASE3b" "Throughput benchmark complete."
}

run_benchmark_micro() {
    log "PHASE3c" "Running micro benchmarks (latency distribution + individual commands)..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}" \
        2>&1 | tee -a "${LOG_FILE}"
    log "PHASE3c" "Micro benchmarks complete."
}

run_benchmark_stress() {
    log "PHASE3d" "Running concurrency scaling stress test..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}" \
        --stress-only \
        2>&1 | tee -a "${LOG_FILE}"
    log "PHASE3d" "Stress test complete."
}

phase3_run_benchmarks() {
    log "PHASE3" "Starting Phase 3: Benchmark Execution"
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            3)  run_benchmark_ycsb && run_benchmark_throughput && run_benchmark_micro && run_benchmark_stress ;;
            3a) run_benchmark_ycsb ;;
            3b) run_benchmark_throughput ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_stress ;;
        esac
    done
    log "PHASE3" "Phase 3 complete."
}

phase4_results() {
    log "PHASE4" "Starting Phase 4: Results Collection & Presentation"

    stop_redis_server

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        --results-dir "${RESULTS_DIR}" \
        2>&1 | tee -a "${LOG_FILE}"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --results-dir "${RESULTS_DIR}" \
        2>&1 | tee -a "${LOG_FILE}"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --results-dir "${RESULTS_DIR}" \
        --software-version "${SOFTWARE_VERSION}" \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE4" "Phase 4 complete. Results available at: ${RESULTS_DIR}"
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
            3d) run_benchmark_stress ;;
            4)  phase4_results ;;
            *)  log "WARN" "Unknown phase: ${p}" ;;
        esac
    done
}

run_tests() {
    download_shunit2
    log "TEST" "Running shUnit2 test suite..."
    "${SCRIPT_DIR}/redis_arm64_perf_test.sh"
}

cleanup() {
    stop_redis_server
    log "CLEANUP" "Workflow cleanup done."
}

trap cleanup EXIT

usage() {
    cat <<EOF
Usage: redis_arm64_perf_workflow.sh [OPTIONS]

ARM64 Performance Benchmark Workflow for Redis ${SOFTWARE_VERSION}

Options:
  -p, --phases PHASES          Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version VER   Redis version to test (default: ${SOFTWARE_VERSION})
  -v, --data-scale SCALE       YCSB dataset scale factor (default: ${DATA_SCALE})
  -d, --data-size SIZE         Data size in records for micro benchmarks (default: ${DATA_SIZE})
  -i, --iterations N           Number of iterations per test (default: ${ITERATIONS})
  -t, --test-only              Run only shUnit2 validation tests
  -h, --help                   Usage help

Examples:
  redis_arm64_perf_workflow.sh                      # Full benchmark workflow
  redis_arm64_perf_workflow.sh -p 3a,3b             # Run YCSB + throughput only
  redis_arm64_perf_workflow.sh -t                   # Run shUnit2 validation only
  redis_arm64_perf_workflow.sh -i 5 -d 5000000     # 5 iterations, 5M records
  redis_arm64_perf_workflow.sh -s 7.4.2             # Test specific Redis version
EOF
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)          PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; REDIS_HOME="${SCRIPT_DIR}/redis-${SOFTWARE_VERSION}"; shift 2 ;;
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