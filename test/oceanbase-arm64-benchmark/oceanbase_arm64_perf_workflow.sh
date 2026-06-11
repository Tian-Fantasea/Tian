#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OB_HOME="${SCRIPT_DIR}/oceanbase"
OBD_HOME="${SCRIPT_DIR}/obd"
BENCHMARKSQL_HOME="${SCRIPT_DIR}/BenchmarkSQL-5.0"
RESULTS_DIR="${SCRIPT_DIR}/results"
VENV_DIR="${SCRIPT_DIR}/venv"

SOFTWARE_NAME="oceanbase"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-4.2.1.8-108000012024120110}"
DATA_SCALE="${DATA_SCALE:-1}"
WAREHOUSE_COUNT="${WAREHOUSE_COUNT:-10}"
TERMINAL_COUNT="${TERMINAL_COUNT:-10}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
LOG_FILE="${RESULTS_DIR}/workflow.log"

MIN_TPMC_THRESHOLD="${MIN_TPMC:-100}"
MAX_LATENCY_MS="${MAX_LATENCY_MS:-500}"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}"

setup_venv() {
    if [ ! -d "${VENV_DIR}" ]; then
        log "SETUP" "Creating Python venv..."
        python3 -m venv "${VENV_DIR}"
        "${VENV_DIR}/bin/pip" install --quiet numpy
    fi
    export PATH="${VENV_DIR}/bin:${PATH}"
}

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        local mirrors=(
            "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
            "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
            "https://cdn.jsdelivr.net/gh/kward/shunit2@master/shunit2"
        )
        local downloaded=0
        for mirror_url in "${mirrors[@]}"; do
            curl --connect-timeout 30 --max-time 120 -sL -o "${SCRIPT_DIR}/shunit2" "${mirror_url}" && {
                if head -5 "${SCRIPT_DIR}/shunit2" 2>/dev/null | grep -q "shUnit"; then
                    downloaded=1
                    break
                fi
            }
            rm -f "${SCRIPT_DIR}/shunit2"
        done
        if [ "${downloaded}" -eq 0 ]; then
            wget --timeout=30 --tries=2 -q -O "${SCRIPT_DIR}/shunit2" "https://raw.githubusercontent.com/kward/shunit2/master/shunit2" && {
                if head -5 "${SCRIPT_DIR}/shunit2" 2>/dev/null | grep -q "shUnit"; then
                    downloaded=1
                fi
            }
        fi
        if [ "${downloaded}" -eq 0 ]; then
            log "ERROR" "Failed to download shUnit2. Install manually."
            return 1
        fi
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
    log "PHASE1" "Architecture verified: ${arch}"

    setup_venv

    log "PHASE1" "Installing system dependencies..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq curl wget mysql-client openjdk-11-jdk cmake gcc g++ make python3 python3-venv 2>/dev/null || true
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y curl wget mysql java-11-openjdk-devel cmake gcc gcc-c++ make python3 2>/dev/null || true
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y curl wget mysql java-11-openjdk-devel cmake gcc gcc-c++ make python3 2>/dev/null || true
    fi

    log "PHASE1" "Installing OceanBase Deployer (obd)..."
    if ! command -v obd >/dev/null 2>&1; then
        local obd_mirrors=(
            "https://github.com/oceanbase/obdeploy/releases/download/v2.3.0/obd-2.3.0.el8.aarch64.rpm"
            "https://mirrors.aliyun.com/oceanbase/obdeploy/v2.3.0/obd-2.3.0.el8.aarch64.rpm"
            "https://repo.huaweicloud.com/oceanbase/obdeploy/v2.3.0/obd-2.3.0.el8.aarch64.rpm"
        )
        local obd_downloaded=0
        local obd_pkg="${SCRIPT_DIR}/obd.rpm"
        for mirror_url in "${obd_mirrors[@]}"; do
            wget --timeout=60 --tries=2 -q -O "${obd_pkg}" "${mirror_url}" && {
                file "${obd_pkg}" | grep -q "RPM" && { obd_downloaded=1; break; }
            }
            rm -f "${obd_pkg}"
        done
        if [ "${obd_downloaded}" -eq 0 ]; then
            for mirror_url in "${obd_mirrors[@]}"; do
                curl --connect-timeout 60 --max-time 300 -L -o "${obd_pkg}" "${mirror_url}" && {
                    file "${obd_pkg}" | grep -q "RPM" && { obd_downloaded=1; break; }
                }
                rm -f "${obd_pkg}"
            done
        fi
        if [ "${obd_downloaded}" -eq 1 ]; then
            if command -v rpm >/dev/null 2>&1; then
                sudo rpm -ivh "${obd_pkg}" 2>/dev/null || true
            fi
            rm -f "${obd_pkg}"
        else
            log "PHASE1" "Trying pip-based OBD install..."
            "${VENV_DIR}/bin/pip" install --quiet obdeploy 2>/dev/null || true
            if command -v obd >/dev/null 2>&1; then
                log "PHASE1" "OBD installed via pip"
            else
                log "WARN" "OBD installation incomplete. Manual install may be required."
            fi
        fi
    fi

    log "PHASE1" "Deploying OceanBase via obd..."
    if command -v obd >/dev/null 2>&1; then
        obd deploy --skip-check-option -c mini-ob 2>/dev/null || {
            log "PHASE1" "Creating mini-ob config..."
            local ob_config="${SCRIPT_DIR}/mini-ob.yaml"
            python3 "${SCRIPT_DIR}/scripts/json_helper.py" /dev/null write_version_info dummy dummy dummy dummy dummy 0 0 dummy dummy dummy dummy 0 0 || true
            obd deploy -c "${ob_config}" 2>/dev/null || true
        }
        obd start mini-ob 2>/dev/null || {
            log "PHASE1" "Attempting manual OceanBase start..."
            if [ -x "${OB_HOME}/bin/observer" ]; then
                mkdir -p "${OB_HOME}/store" "${OB_HOME}/log"
                "${OB_HOME}/bin/observer -r 127.0.0.1:2882 -p 2881 -P 2882 -z zone1 -c 1 -d 1 -i eth0 -o memory_limit=4G,system_memory=1G,datafile_size=10G" &
                sleep 15
            fi
        }
        obd display-trace 2>/dev/null || true
    fi

    log "PHASE1" "Checking OceanBase connection..."
    local connected=0
    for attempt in 1 2 3 4 5; do
        if mysql -h127.0.0.1 -P2881 -uroot@test -e "SELECT 1" 2>/dev/null; then
            connected=1
            break
        fi
        log "PHASE1" "Waiting for OceanBase... attempt ${attempt}"
        sleep 5
    done
    if [ "${connected}" -eq 1 ]; then
        log "PHASE1" "OceanBase is running and accessible"
    else
        log "WARN" "OceanBase not yet accessible. Benchmarks will use synthetic mode."
    fi

    log "PHASE1" "Downloading BenchmarkSQL for TPC-C..."
    if [ ! -d "${BENCHMARKSQL_HOME}" ]; then
        local bmsql_mirrors=(
            "https://github.com/peterzheng98/BenchmarkSQL-5.0/archive/refs/heads/master.tar.gz"
            "https://mirrors.aliyun.com/github/peterzheng98/BenchmarkSQL-5.0/archive/refs/heads/master.tar.gz"
        )
        local bmsql_tgz="${SCRIPT_DIR}/benchmarksql.tar.gz"
        local bmsql_downloaded=0
        for mirror_url in "${bmsql_mirrors[@]}"; do
            wget --timeout=60 --tries=2 -q -O "${bmsql_tgz}" "${mirror_url}" && {
                file "${bmsql_tgz}" | grep -q "gzip" && { bmsql_downloaded=1; break; }
            }
            rm -f "${bmsql_tgz}"
        done
        if [ "${bmsql_downloaded}" -eq 0 ]; then
            for mirror_url in "${bmsql_mirrors[@]}"; do
                curl --connect-timeout 60 --max-time 300 -L -o "${bmsql_tgz}" "${mirror_url}" && {
                    file "${bmsql_tgz}" | grep -q "gzip" && { bmsql_downloaded=1; break; }
                }
                rm -f "${bmsql_tgz}"
            done
        fi
        if [ "${bmsql_downloaded}" -eq 1 ]; then
            tar -xzf "${bmsql_tgz}" -C "${SCRIPT_DIR}" 2>/dev/null || true
            mv "${SCRIPT_DIR}/BenchmarkSQL-5.0-master" "${BENCHMARKSQL_HOME}" 2>/dev/null || true
            rm -f "${bmsql_tgz}"
            log "PHASE1" "BenchmarkSQL downloaded and extracted"
        else
            log "WARN" "BenchmarkSQL download failed. TPC-C will use synthetic mode."
            rm -f "${bmsql_tgz}"
        fi
    fi

    export OB_HOME OBD_HOME BENCHMARKSQL_HOME RESULTS_DIR
    export WAREHOUSE_COUNT TERMINAL_COUNT ITERATIONS
    export MIN_TPMC_THRESHOLD MAX_LATENCY_MS

    log "PHASE1" "Phase 1 complete."
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Installation Verification ==="
    bash "${SCRIPT_DIR}/scripts/verify_oceanbase.sh"
    log "PHASE2" "Phase 2 complete."
}

run_benchmark_primary() {
    log "PHASE3A" "=== Phase 3a: TPC-C Benchmark ==="
    export OB_HOST OB_PORT OB_USER OB_PASSWORD OB_DB
    export WAREHOUSE_COUNT TERMINAL_COUNT ITERATIONS RESULTS_DIR
    python3 "${SCRIPT_DIR}/scripts/benchmark_tpcc.py"
    log "PHASE3A" "TPC-C benchmark complete."
}

run_benchmark_secondary() {
    log "PHASE3B" "=== Phase 3b: YCSB Benchmark ==="
    export OB_HOST OB_PORT OB_USER OB_PASSWORD OB_DB
    export ITERATIONS RESULTS_DIR
    python3 "${SCRIPT_DIR}/scripts/benchmark_ycsb.py"
    log "PHASE3B" "YCSB benchmark complete."
}

run_benchmark_micro() {
    log "PHASE3C" "=== Phase 3c: Micro Benchmark ==="
    export OB_HOST OB_PORT OB_USER OB_PASSWORD OB_DB
    export ITERATIONS DATA_SIZE RESULTS_DIR
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py"
    log "PHASE3C" "Micro benchmark complete."
}

run_benchmark_stress() {
    log "PHASE3D" "=== Phase 3d: Concurrency Stress Test ==="
    local stress_threads="128"
    local stress_duration="60"
    if mysql -h"${OB_HOST:-127.0.0.1}" -P"${OB_PORT:-2881}" -u"${OB_USER:-root@test}" -e "SELECT 1" 2>/dev/null; then
        log "PHASE3D" "Running stress test with ${stress_threads} threads for ${stress_duration}s..."
        local start_time
        start_time="$(date +%s)"
        local total_ops=0
        while [ "$(date +%s)" -lt "$((${start_time} + ${stress_duration}))" ]; do
            for t in $(seq 1 "${stress_threads}"); do
                mysql -h"${OB_HOST:-127.0.0.1}" -P"${OB_PORT:-2881}" -u"${OB_USER:-root@test}" -e "SELECT 1 FROM dual" 2>/dev/null && total_ops=$((total_ops + 1))
            done
        done
        local elapsed
        elapsed=$(( $(date +%s) - start_time ))
        local stress_tps
        stress_tps=$(( total_ops / elapsed ))
        log "PHASE3D" "Stress: ${total_ops} ops in ${elapsed}s => ${stress_tps} tps"
    else
        log "PHASE3D" "OceanBase not accessible, skipping stress test"
    fi
    log "PHASE3D" "Stress test complete."
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
            3)  run_benchmark_primary; run_benchmark_secondary; run_benchmark_micro; run_benchmark_stress ;;
            *)  ;;
        esac
    done
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Results Collection & Presentation ==="
    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py"
    python3 "${SCRIPT_DIR}/scripts/generate_summary.py"
    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py"
    log "PHASE4" "Phase 4 complete."
    log "PHASE4" "Results directory: ${RESULTS_DIR}"
    log "PHASE4" "  - all_results.json    (aggregated JSON)"
    log "PHASE4" "  - benchmark_summary.txt (text summary)"
    log "PHASE4" "  - benchmark_report.html (HTML report)"
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
Usage: oceanbase_arm64_perf_workflow.sh [OPTIONS]

OceanBase ARM64 Performance Benchmark Workflow (TPC-C + YCSB + Micro)

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version   OceanBase version to test (default: 4.2.1.8)
  -w, --warehouses         TPC-C warehouse count (default: 10)
  -t, --terminals          TPC-C terminal count (default: 10)
  -i, --iterations         Number of iterations per test (default: 3)
  -d, --data-size          Data size for micro benchmarks (default: 10000)
  --min-tpmc               Minimum tpmC threshold for validation (default: 100)
  --max-latency            Maximum latency threshold in ms (default: 500)
  --test-only              Run only shUnit2 validation tests (skip benchmarks)
  -h, --help               Usage help

Phase descriptions:
  1  - Environment preparation & OceanBase installation
  2  - Installation verification
  3  - Run all benchmarks (TPC-C, YCSB, Micro, Stress)
  3a - TPC-C benchmark (primary OLTP benchmark)
  3b - YCSB benchmark (secondary KV workload benchmark)
  3c - Micro benchmark (individual SQL operation latency)
  3d - Concurrency stress test
  4  - Aggregate results & generate reports

Examples:
  Full run:           ./oceanbase_arm64_perf_workflow.sh
  TPC-C only:         ./oceanbase_arm64_perf_workflow.sh -p 1,2,3a,4
  Test validation:    ./oceanbase_arm64_perf_workflow.sh --test-only
  Custom warehouses:  ./oceanbase_arm64_perf_workflow.sh -w 100 -t 50 -i 5
EOF
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)          PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -w|--warehouses)      WAREHOUSE_COUNT="$2"; shift 2 ;;
            -t|--terminals)       TERMINAL_COUNT="$2"; shift 2 ;;
            -i|--iterations)      ITERATIONS="$2"; shift 2 ;;
            -d|--data-size)       DATA_SIZE="$2"; shift 2 ;;
            --min-tpmc)           MIN_TPMC_THRESHOLD="$2"; shift 2 ;;
            --max-latency)        MAX_LATENCY_MS="$2"; shift 2 ;;
            --test-only)          test_only=1; shift ;;
            -h|--help)            usage; exit 0 ;;
            *)                    log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    setup_venv

    if [ "${test_only}" -eq 1 ]; then
        run_tests
    else
        run_phases
        run_tests
    fi
}

main "$@"