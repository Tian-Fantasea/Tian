#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="flink"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-2.2.1}"
FLINK_SCALE="${FLINK_SCALE:-1}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
FLINK_HOME="${SCRIPT_DIR}/flink"
JAVA_HOME="${JAVA_HOME:-}"
LOG_FILE="${RESULTS_DIR}/workflow.log"
FLINK_DOWNLOAD_URL="https://archive.apache.org/dist/flink/flink-${SOFTWARE_VERSION}/flink-${SOFTWARE_VERSION}-bin-scala_2.12.tgz"
NPROC="$(nproc 2>/dev/null || echo 4)"
TOTAL_MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 8388608)"
FLINK_TM_MEM="$(echo "${TOTAL_MEM_KB} / 1024 * 70 / 100" | bc 2>/dev/null || echo 6144)"

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
    log "PHASE1" "Starting environment preparation & installation"

    local arch
    arch="$(uname -m)"
    log "PHASE1" "Architecture: ${arch}"
    if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
        log "ERROR" "This benchmark requires ARM64. Current: ${arch}"
        return 1
    fi

    log "PHASE1" "Installing system dependencies..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq
        apt-get install -y -qq curl wget python3 python3-venv python3-pip bc
    elif command -v yum >/dev/null 2>&1; then
        yum install -y -q curl wget python3 python3-pip bc
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y -q curl wget python3 python3-pip bc
    fi

    log "PHASE1" "Installing Eclipse Temurin JDK 21 for ARM64..."
    if [ -z "${JAVA_HOME}" ] || [ ! -x "${JAVA_HOME}/bin/java" ]; then
        if command -v apt-get >/dev/null 2>&1; then
            apt-get install -y -qq wget apt-transport-https gpg
local temurin_list="/etc/apt/sources.list.d/temurin.list"
        local adoptium_list="/etc/apt/sources.list.d/adoptium.list"
        if [ ! -f "${temurin_list}" ] && [ ! -f "${adoptium_list}" ]; then
            wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor -o /usr/share/keyrings/adoptium.gpg
            echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo "${VERSION_CODENAME}") main" > "${temurin_list}"
        fi
        apt-get update -qq 2>/dev/null
        apt-get install -y -qq temurin-21-jdk
            JAVA_HOME="/usr/lib/jvm/temurin-21-jdk-arm64"
        elif command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
            rpm --import https://packages.adoptium.net/artifactory/api/gpg/key/public
            cat > /etc/yum.repos.d/temurin.repo << 'REPOEOF'
[temurin]
name=Adoptium Temurin
baseurl=https://packages.adoptium.net/artifactory/rpm/$(. /etc/os-release && echo "${VERSION_ID}")/${arch}/
enabled=1
gpgcheck=1
REPOEOF
            yum install -y -q temurin-21-jdk || dnf install -y -q temurin-21-jdk
            JAVA_HOME="/usr/lib/jvm/temurin-21-jdk-arm64"
        fi
    fi
    export JAVA_HOME
    export PATH="${JAVA_HOME}/bin:${PATH}"
    log "PHASE1" "Java version: $(java -version 2>&1 | head -1)"

    log "PHASE1" "Installing Python dependencies via venv..."
    if [ ! -f "${SCRIPT_DIR}/venv/bin/pip" ]; then
        rm -rf "${SCRIPT_DIR}/venv"
        python3 -m venv "${SCRIPT_DIR}/venv"
        "${SCRIPT_DIR}/venv/bin/pip" install --quiet --upgrade pip
    fi
    "${SCRIPT_DIR}/venv/bin/pip" install --quiet numpy pandas scipy matplotlib pyarrow
    export PATH="${SCRIPT_DIR}/venv/bin:${PATH}"

    log "PHASE1" "Downloading Apache Flink ${SOFTWARE_VERSION} for ARM64..."
    if [ ! -d "${FLINK_HOME}" ] || [ ! -f "${FLINK_HOME}/bin/start-cluster.sh" ]; then
        rm -rf "${FLINK_HOME}"
        local tgz="/tmp/flink-${SOFTWARE_VERSION}.tgz"
        local flink_filename="flink-${SOFTWARE_VERSION}-bin-scala_2.12.tgz"
        local mirrors=(
            "https://archive.apache.org/dist/flink/flink-${SOFTWARE_VERSION}/${flink_filename}"
            "https://mirrors.aliyun.com/apache/flink/flink-${SOFTWARE_VERSION}/${flink_filename}"
            "https://mirrors.tuna.tsinghua.edu.cn/apache/flink/flink-${SOFTWARE_VERSION}/${flink_filename}"
            "https://mirrors.huaweicloud.com/apache/flink/flink-${SOFTWARE_VERSION}/${flink_filename}"
            "https://repo.huaweicloud.com/apache/flink/flink-${SOFTWARE_VERSION}/${flink_filename}"
        )
        local downloaded=0
        rm -f "${tgz}"
        for mirror_url in "${mirrors[@]}"; do
            log "PHASE1" "Trying: ${mirror_url}"
            wget --timeout=60 --tries=2 -q -O "${tgz}" "${mirror_url}" 2>/dev/null && {
                file "${tgz}" | grep -q "gzip" && {
                    downloaded=1
                    log "PHASE1" "Download succeeded from: ${mirror_url}"
                    break
                }
            }
            rm -f "${tgz}"
        done
        if [ "${downloaded}" -eq 0 ]; then
            for mirror_url in "${mirrors[@]}"; do
                log "PHASE1" "Retrying with curl: ${mirror_url}"
                curl --connect-timeout 60 --max-time 600 -L -o "${tgz}" "${mirror_url}" 2>/dev/null && {
                    file "${tgz}" | grep -q "gzip" && {
                        downloaded=1
                        log "PHASE1" "Download succeeded (curl) from: ${mirror_url}"
                        break
                    }
                }
                rm -f "${tgz}"
            done
        fi
        if [ "${downloaded}" -eq 0 ]; then
            log "ERROR" "All mirrors failed. Please download manually:"
            log "ERROR" "  wget -O /tmp/${flink_filename} <any_mirror_url>"
            log "ERROR" "  Then re-run this script."
            return 1
        fi
        log "PHASE1" "Extracting Flink..."
        tar -xzf "${tgz}" -C "${SCRIPT_DIR}"
        local extracted_dir
        extracted_dir="$(find "${SCRIPT_DIR}" -maxdepth 1 -name 'flink-*' -type d | head -1)"
        if [ -z "${extracted_dir}" ]; then
            log "ERROR" "Flink extraction failed - no flink directory found"
            return 1
        fi
        if [ "${extracted_dir}" != "${FLINK_HOME}" ]; then
            mv "${extracted_dir}" "${FLINK_HOME}"
        fi
        if [ ! -f "${FLINK_HOME}/bin/start-cluster.sh" ]; then
            log "ERROR" "Flink installation incomplete: start-cluster.sh not found"
            return 1
        fi
        rm -f "${tgz}"
    else
        log "PHASE1" "Flink already installed at ${FLINK_HOME}"
    fi

    log "PHASE1" "Configuring Flink for ARM64..."
    local task_slots="${NPROC}"
    local jm_mem="$(echo "${TOTAL_MEM_KB} / 1024 * 20 / 100" | bc 2>/dev/null || echo 2048)"
    local tm_mem="${FLINK_TM_MEM}"

    printf '%s\n' \
        "jobmanager.memory.process.size: ${jm_mem}m" \
        "taskmanager.memory.process.size: ${tm_mem}m" \
        "taskmanager.numberOfTaskSlots: ${task_slots}" \
        "parallelism.default: ${task_slots}" \
        "rest.port: 8081" \
        "rest.address: 0.0.0.0" \
        "web.submit-enabled: true" \
        "web.cancel-enabled: true" \
        >> "${FLINK_HOME}/conf/flink-conf.yaml"

    log "PHASE1" "Flink configured: JM=${jm_mem}m, TM=${tm_mem}m, slots=${task_slots}, parallelism=${task_slots}"
    log "PHASE1" "Phase 1 complete"
}

phase2_verify() {
    log "PHASE2" "Verifying installation & collecting version info"

    log "PHASE2" "Starting Flink cluster..."
    "${FLINK_HOME}/bin/start-cluster.sh"
    sleep 10

    log "PHASE2" "Running WordCount example..."
    "${FLINK_HOME}/bin/flink" run "${FLINK_HOME}/examples/streaming/WordCount.jar"
    sleep 5

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
    local cores
    cores="${NPROC}"
    local mem_mb
    mem_mb="$(echo "${TOTAL_MEM_KB} / 1024" | bc 2>/dev/null || echo 8192)"
    local java_ver
    java_ver="$(java -version 2>&1 | head -1 | tr -d '\n\t')"
    local flink_ver
    flink_ver="$(grep 'flink-version' "${FLINK_HOME}/lib/"*.jar 2>/dev/null | head -1 | tr -d '\n\t' || echo "${SOFTWARE_VERSION}")"

    mkdir -p "${RESULTS_DIR}"
    python3 "${SCRIPT_DIR}/scripts/json_helper.py" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" "${cores}" "${mem_mb}" \
        "${SOFTWARE_VERSION}" "2.12" "${java_ver}" "${FLINK_HOME}" "${cores}" "${cores}"

    log "PHASE2" "Version info saved to ${RESULTS_DIR}/version_info.json"

    "${FLINK_HOME}/bin/stop-cluster.sh"
    sleep 5
    log "PHASE2" "Phase 2 complete"
}

run_benchmark_tpcds() {
    log "PHASE3a" "Running TPC-DS SQL benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_tpcds.py" \
        --flink-home "${FLINK_HOME}" \
        --scale "${FLINK_SCALE}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

run_benchmark_streaming() {
    log "PHASE3b" "Running streaming throughput/latency benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_streaming.py" \
        --flink-home "${FLINK_HOME}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

run_benchmark_micro() {
    log "PHASE3c" "Running micro benchmarks..."
    "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --flink-home "${FLINK_HOME}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

run_benchmark_state() {
    log "PHASE3d" "Running state backend & checkpoint benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_state.py" \
        --flink-home "${FLINK_HOME}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}"
}

phase3_run_benchmarks() {
    log "PHASE3" "Running performance benchmarks"
    local phases="${PHASES}"
    local has_3=false
    for p in $(echo "${phases}" | tr ',' ' '); do
        case "${p}" in
            3)  has_3=true ;;
            3a) run_benchmark_tpcds ;;
            3b) run_benchmark_streaming ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_state ;;
        esac
    done
    if [ "${has_3}" = true ]; then
        run_benchmark_tpcds
        run_benchmark_streaming
        run_benchmark_micro
        run_benchmark_state
    fi
}

phase4_results() {
    log "PHASE4" "Collecting & presenting results"

    "${SCRIPT_DIR}/scripts/aggregate_results.py" --results-dir "${RESULTS_DIR}"
    "${SCRIPT_DIR}/scripts/generate_summary.py" --results-dir "${RESULTS_DIR}"
    "${SCRIPT_DIR}/scripts/generate_html_report.py" --results-dir "${RESULTS_DIR}"

    log "PHASE4" "Results saved:"
    log "PHASE4" "  JSON:   ${RESULTS_DIR}/all_results.json"
    log "PHASE4" "  Summary: ${RESULTS_DIR}/benchmark_summary.txt"
    log "PHASE4" "  HTML:   ${RESULTS_DIR}/benchmark_report.html"
    log "PHASE4" "Phase 4 complete"
}

run_tests() {
    download_shunit2
    log "TEST" "Running shUnit2 test suite..."
    "${SCRIPT_DIR}/flink_arm64_perf_test.sh"
}

usage() {
    cat <<EOF
Usage: flink_arm64_perf_workflow.sh [OPTIONS]

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version   Version to test (default: 2.2.1)
  -v, --data-scale         TPC-DS scale factor (default: 1)
  -i, --iterations         Number of iterations per test (default: 3)
  -t, --test-only          Run only shUnit2 validation tests
  -h, --help               Usage help
EOF
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)        PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -v|--data-scale)    FLINK_SCALE="$2"; shift 2 ;;
            -i|--iterations)    ITERATIONS="$2"; shift 2 ;;
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

run_phases() {
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            1)  phase1_install ;;
            2)  phase2_verify ;;
            3)  phase3_run_benchmarks ;;
            3a) run_benchmark_tpcds ;;
            3b) run_benchmark_streaming ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_state ;;
            4)  phase4_results ;;
            *)  log "WARN" "Unknown phase: ${p}" ;;
        esac
    done
}

main "$@"