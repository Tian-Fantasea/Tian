#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="ceph"
SOFTWARE_VERSION="${VERSION:-19.2.0}"
SHUNIT_PARENT="${SCRIPT_DIR}/ceph_test.sh"

CEPH_CONF_PATH="${CEPH_CONF_PATH:-/etc/ceph/ceph.conf}"
CEPH_KEYRING_PATH="${CEPH_KEYRING_PATH:-/etc/ceph/ceph.client.admin.keyring}"
CEPHFS_MOUNT="${CEPHFS_MOUNT:-/mnt/cephfs}"

LOG_FILE="${RESULTS_DIR}/results.log"
ITERATIONS="${ITERATIONS:-1}"
PHASES="${PHASES:-1,2,3,4}"
OBJECT_SIZES="${OBJECT_SIZES:-4K,16K,64K,256K,1M,4M}"
CONCURRENCY_LEVELS="${CONCURRENCY_LEVELS:-1,4,16,32}"
BENCH_DURATION="${BENCH_DURATION:-10}"
DATA_SIZE="${DATA_SIZE:-100}"

MINIMUM_THROUGHPUT=1000
MINIMUM_IOPS=500
MAXIMUM_LATENCY_MS=50

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

    if ! command -v ceph >/dev/null 2>&1; then
        log "ERROR" "ceph is not installed. Please install Ceph before running this benchmark."
        log "ERROR" "  Recommended: sudo apt-get install ceph ceph-mds ceph-common (or equivalent for your distro)"
        errors=$((errors + 1))
    else
        local ceph_ver
        ceph_ver="$(ceph --version 2>&1 | head -1 | tr -d '\n\t')"
        log "CHECK" "Ceph OK: ${ceph_ver}"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1 | tr -d '\n\t')"
    fi

    if ! command -v fio >/dev/null 2>&1; then
        log "WARN" "fio not installed. RBD/CephFS benchmarks will use fallback mode."
        log "WARN" "  Install: sudo apt-get install fio (or equivalent)"
    else
        log "CHECK" "fio OK: $(fio --version 2>&1 | head -1 | tr -d '\n\t')"
    fi

    if [ ! -f "${CEPH_CONF_PATH}" ]; then
        log "ERROR" "ceph.conf not found at ${CEPH_CONF_PATH}"
        log "ERROR" "  Set CEPH_CONF_PATH to your ceph.conf location"
        errors=$((errors + 1))
    else
        log "CHECK" "ceph.conf OK: ${CEPH_CONF_PATH}"
    fi

    if [ ! -f "${CEPH_KEYRING_PATH}" ]; then
        log "ERROR" "ceph keyring not found at ${CEPH_KEYRING_PATH}"
        log "ERROR" "  Set CEPH_KEYRING_PATH to your keyring location"
        errors=$((errors + 1))
    else
        log "CHECK" "ceph keyring OK: ${CEPH_KEYRING_PATH}"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

collect_version_info() {
    local timestamp arch kernel os cpu_model cores mem_mb ceph_ver cluster_health osd_count mon_count
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    ceph_ver="$(ceph --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"

    local status_json
    status_json="$(ceph -c "${CEPH_CONF_PATH}" status --format json 2>/dev/null || echo '{}')"
    cluster_health="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('health',{}).get('status','unknown'))" <<< "${status_json}" 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    osd_count="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('osdmap',{}).get('osds',[])))" <<< "${status_json}" 2>/dev/null | tr -d '\n\t' || echo '0')"
    mon_count="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('monmap',{}).get('mons',[])))" <<< "${status_json}" 2>/dev/null | tr -d '\n\t' || echo '0')"

    local neon_available="0"
    local crc32c_available="0"
    if [ "${arch}" = "aarch64" ] || [ "${arch}" = "arm64" ]; then
        local cpuinfo
        cpuinfo="$(cat /proc/cpuinfo 2>/dev/null | head -20)"
        if echo "${cpuinfo}" | grep -qi "neon\|asimd"; then neon_available="1"; fi
        if echo "${cpuinfo}" | grep -qi "crc32\|crc"; then crc32c_available="1"; fi
    fi

    python3 "${JSON_HELPER}" "${RESULTS_JSON}" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "ceph" "${SOFTWARE_VERSION}" \
        "${ceph_ver}" "${CEPH_CONF_PATH}" "1" "0" \
        "${cluster_health}" "${osd_count}" "${mon_count}" \
        "${neon_available}" "${crc32c_available}"
}

run_benchmarks() {
    log "PHASE3" "Running benchmarks..."
    local has_rados=0 has_rbd=0 has_cephfs=0 has_micro=0
    local IFS=','
    for p in ${PHASES}; do
        case "${p}" in
            3|3a) has_rados=1 ;;
            3b) has_rbd=1 ;;
            3c) has_cephfs=1 ;;
            3d) has_micro=1 ;;
        esac
    done

    if [ "${has_rados}" -eq 1 ]; then
        log "PHASE3a" "Running RADOS benchmark..."
        python3 "${SCRIPTS_DIR}/benchmark_rados.py" \
            --results-dir "${RESULTS_DIR}" \
            --ceph-conf "${CEPH_CONF_PATH}" \
            --ceph-keyring "${CEPH_KEYRING_PATH}" \
            --pool bench_rados \
            --object-sizes "${OBJECT_SIZES}" \
            --concurrency "${CONCURRENCY_LEVELS}" \
            --duration "${BENCH_DURATION}" \
            --iterations "${ITERATIONS}" \
            --results-json "${RESULTS_JSON}" \
            --section rados_benchmark
    fi

    if [ "${has_rbd}" -eq 1 ]; then
        log "PHASE3b" "Running RBD benchmark..."
        python3 "${SCRIPTS_DIR}/benchmark_rbd.py" \
            --results-dir "${RESULTS_DIR}" \
            --ceph-conf "${CEPH_CONF_PATH}" \
            --ceph-keyring "${CEPH_KEYRING_PATH}" \
            --pool bench_rbd \
            --iterations "${ITERATIONS}" \
            --results-json "${RESULTS_JSON}" \
            --section rbd_benchmark
    fi

    if [ "${has_cephfs}" -eq 1 ]; then
        log "PHASE3c" "Running CephFS benchmark..."
        python3 "${SCRIPTS_DIR}/benchmark_cephfs.py" \
            --results-dir "${RESULTS_DIR}" \
            --mount-point "${CEPHFS_MOUNT}" \
            --iterations "${ITERATIONS}" \
            --data-size "${DATA_SIZE}" \
            --results-json "${RESULTS_JSON}" \
            --section cephfs_benchmark
    fi

    if [ "${has_micro}" -eq 1 ]; then
        log "PHASE3d" "Running micro benchmarks..."
        python3 "${SCRIPTS_DIR}/micro_benchmark.py" \
            --results-dir "${RESULTS_DIR}" \
            --ceph-conf "${CEPH_CONF_PATH}" \
            --ceph-keyring "${CEPH_KEYRING_PATH}" \
            --iterations "${ITERATIONS}" \
            --duration "${BENCH_DURATION}" \
            --results-json "${RESULTS_JSON}" \
            --section micro_benchmark
    fi
}

generate_reports() {
    log "PHASE4" "Generating summary and HTML report"
    python3 "${SCRIPTS_DIR}/generate_summary.py" \
        --input "${RESULTS_JSON}" \
        --output "${RESULTS_DIR}/results.txt"
    python3 "${SCRIPTS_DIR}/generate_html_report.py" \
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

testCephIsInstalled() {
    local found=0
    if command -v ceph >/dev/null 2>&1; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: ceph not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "ceph binary should exist" "[ ${found} -eq 1 ]"
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

testBenchmarkRadosInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_rados
    has_rados="$(json_field_exists "${RESULTS_JSON}" rados_benchmark)"
    assertTrue "results.json should contain rados_benchmark data" "[ ${has_rados} -eq 1 ]"
}

testBenchmarkRadosHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_bench has_metrics has_results
    has_bench="$(json_field_exists "${RESULTS_JSON}" rados_benchmark benchmark)"
    has_metrics="$(json_field_exists "${RESULTS_JSON}" rados_benchmark performance_metrics)"
    has_results="$(json_field_exists "${RESULTS_JSON}" rados_benchmark results)"
    assertTrue "rados_benchmark should have benchmark field" "[ ${has_bench} -eq 1 ]"
    assertTrue "rados_benchmark should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "rados_benchmark should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkRbdInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_rbd
    has_rbd="$(json_field_exists "${RESULTS_JSON}" rbd_benchmark)"
    assertTrue "results.json should contain rbd_benchmark data" "[ ${has_rbd} -eq 1 ]"
}

testBenchmarkCephfsInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_cephfs
    has_cephfs="$(json_field_exists "${RESULTS_JSON}" cephfs_benchmark)"
    assertTrue "results.json should contain cephfs_benchmark data" "[ ${has_cephfs} -eq 1 ]"
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
    local has_rados has_rbd has_cephfs has_micro
    has_rados="$(json_contains "${RESULTS_JSON}" rados_benchmark)"
    has_rbd="$(json_contains "${RESULTS_JSON}" rbd_benchmark)"
    has_cephfs="$(json_contains "${RESULTS_JSON}" cephfs_benchmark)"
    has_micro="$(json_contains "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "Should contain rados_benchmark data" "[ ${has_rados} -eq 1 ]"
    assertTrue "Should contain rbd_benchmark data" "[ ${has_rbd} -eq 1 ]"
    assertTrue "Should contain cephfs_benchmark data" "[ ${has_cephfs} -eq 1 ]"
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
Usage: ceph_test.sh [OPTIONS]

Ceph ARM64 Performance Benchmark (shUnit2)

Prerequisites (must be pre-installed):
  - Ceph cluster (running with ceph.conf and keyring)
  - Python 3.8+
  - fio (optional, for RBD/CephFS benchmarks)
  - scripts/json_helper.py

Note: shUnit2 will be auto-downloaded if not present.

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version   Ceph version (default: ${SOFTWARE_VERSION})
  --ceph-conf              Path to ceph.conf (default: ${CEPH_CONF_PATH})
  --ceph-keyring           Path to ceph keyring (default: ${CEPH_KEYRING_PATH})
  --cephfs-mount           CephFS mount point (default: ${CEPHFS_MOUNT})
  -i, --iterations         Iterations per test (default: ${ITERATIONS})
  --duration               Benchmark duration in seconds (default: ${BENCH_DURATION})
  --object-sizes           Comma-separated object sizes (default: ${OBJECT_SIZES})
  --concurrency            Comma-separated concurrency levels (default: ${CONCURRENCY_LEVELS})
  --data-size              Metadata ops count (default: ${DATA_SIZE})
  --check                  Check prerequisites only (no benchmark)
  -h, --help               Usage help

Examples:
  ./ceph_test.sh                     # Full run + shUnit2 validation
  ./ceph_test.sh --check             # Check prerequisites only
  ./ceph_test.sh -p 3a,3b            # Only RADOS and RBD benchmarks
  ./ceph_test.sh --ceph-conf /etc/ceph/my.conf  # Custom config path
  ./ceph_test.sh -i 3 --duration 30  # 3 iterations, 30s duration
EOF
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)          PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            --ceph-conf)          CEPH_CONF_PATH="$2"; shift 2 ;;
            --ceph-keyring)       CEPH_KEYRING_PATH="$2"; shift 2 ;;
            --cephfs-mount)       CEPHFS_MOUNT="$2"; shift 2 ;;
            -i|--iterations)      ITERATIONS="$2"; shift 2 ;;
            --duration)           BENCH_DURATION="$2"; shift 2 ;;
            --object-sizes)       OBJECT_SIZES="$2"; shift 2 ;;
            --concurrency)        CONCURRENCY_LEVELS="$2"; shift 2 ;;
            --data-size)          DATA_SIZE="$2"; shift 2 ;;
            --check)              check_only=1; shift ;;
            -h|--help)            usage; exit 0 ;;
            *)                    log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    log "START" "Ceph ARM64 Benchmark v${SOFTWARE_VERSION}"

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
