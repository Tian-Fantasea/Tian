#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOFTWARE_NAME="flink"
SOFTWARE_VERSION="${VERSION:-2.1.0}"
RESULTS_DIR="${SCRIPT_DIR}/results"
SCRIPTS_DIR="${SCRIPT_DIR}/scripts"
LOG_FILE="${RESULTS_DIR}/results.log"
DATA_SCALE="${DATA_SCALE:-1}"
ITERATIONS="${ITERATIONS:-1}"
FLINK_HOME="${FLINK_HOME:-${SCRIPT_DIR}/flink-${SOFTWARE_VERSION}}"
PARALLELISM="${PARALLELISM:-4}"
PHASES="${PHASES:-1,2,3a,3b,3c,4}"
SHUNIT_PARENT="${SCRIPT_DIR}/flink_test.sh"

RESULTS_JSON="${RESULTS_DIR}/results.json"

MINIMUM_TPCDS_THROUGHPUT=500
MINIMUM_STREAMING_THROUGHPUT=10000
MAXIMUM_STREAMING_LATENCY=500

JSON_HELPER="${SCRIPTS_DIR}/json_helper.py"

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

    if ! command -v java >/dev/null 2>&1; then
        log "ERROR" "Java is not installed. Please install JDK 17+ before running this benchmark."
        log "ERROR" "  Recommended: sudo apt-get install temurin-17-jdk  (or equivalent for your distro)"
        errors=$((errors + 1))
    else
        local java_ver
        java_ver="$(java -version 2>&1 | head -1 | tr -d '\n\t')"
        log "CHECK" "Java OK: ${java_ver}"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+ before running this benchmark."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1 | tr -d '\n\t')"
    fi

    if [ ! -d "${FLINK_HOME}" ] || [ ! -x "${FLINK_HOME}/bin/flink" ]; then
        log "ERROR" "Flink is not installed at ${FLINK_HOME}"
        log "ERROR" "  Please download Flink ${SOFTWARE_VERSION} and extract to ${SCRIPT_DIR}/"
        log "ERROR" "  Download: https://archive.apache.org/dist/flink/flink-${SOFTWARE_VERSION}/flink-${SOFTWARE_VERSION}-bin-scala_2.12.tgz"
        log "ERROR" "  Or set FLINK_HOME to point to your Flink installation directory"
        errors=$((errors + 1))
    else
        local flink_ver
        flink_ver="$(bash "${FLINK_HOME}/bin/flink" --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
        log "CHECK" "Flink OK: ${flink_ver}"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        log "ERROR" "  This file is required for shUnit2 JSON assertions"
        errors=$((errors + 1))
    fi

    return ${errors}
}

collect_version_info() {
    local timestamp arch kernel os cpu_model cores mem_mb java_ver flink_found
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    java_ver="$(java -version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    if [ -d "${FLINK_HOME}" ] && [ -x "${FLINK_HOME}/bin/flink" ]; then
        flink_found=1
    else
        flink_found=0
    fi

    python3 "${JSON_HELPER}" "${RESULTS_JSON}" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "flink" "${SOFTWARE_VERSION}" \
        "${java_ver}" "${FLINK_HOME}" "${flink_found}" "${PARALLELISM}"
}

run_benchmarks() {
    log "PHASE3" "Running benchmarks..."
    local has_primary=0
    local has_secondary=0
    local has_micro=0
    local IFS=','
    for p in ${PHASES}; do
        case "${p}" in
            3|3a) has_primary=1 ;;
            3b) has_secondary=1 ;;
            3c) has_micro=1 ;;
        esac
    done

    if [ "${has_primary}" -eq 1 ]; then
        log "PHASE3a" "Running TPC-DS benchmark..."
        python3 "${SCRIPTS_DIR}/benchmark_tpcds.py" \
            --flink-home "${FLINK_HOME}" \
            --results-dir "${RESULTS_DIR}" \
            --iterations "${ITERATIONS}" \
            --data-scale "${DATA_SCALE}" \
            --parallelism "${PARALLELISM}" \
            --results-json "${RESULTS_JSON}" \
            --section primary_benchmark
    fi

    if [ "${has_secondary}" -eq 1 ]; then
        log "PHASE3b" "Running streaming benchmark..."
        python3 "${SCRIPTS_DIR}/benchmark_streaming.py" \
            --flink-home "${FLINK_HOME}" \
            --results-dir "${RESULTS_DIR}" \
            --iterations "${ITERATIONS}" \
            --parallelism "${PARALLELISM}" \
            --results-json "${RESULTS_JSON}" \
            --section secondary_benchmark
    fi

    if [ "${has_micro}" -eq 1 ]; then
        log "PHASE3c" "Running micro benchmarks..."
        python3 "${SCRIPTS_DIR}/micro_benchmark.py" \
            --flink-home "${FLINK_HOME}" \
            --results-dir "${RESULTS_DIR}" \
            --iterations "${ITERATIONS}" \
            --parallelism "${PARALLELISM}" \
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
    log "LIFECYCLE" "oneTimeSetUp: Check prerequisites + Write version_info into results.json + Run benchmarks"

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Please install missing dependencies and try again."
        log "FATAL" "Run './flink_test.sh --check' to see detailed prerequisite status."
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

testSoftwareIsInstalled() {
    local found=0
    if [ -d "${FLINK_HOME}" ] && [ -x "${FLINK_HOME}/bin/flink" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: Flink not installed at ${FLINK_HOME}, skipping install check"
        startSkipping
        return
    fi
    assertTrue "Flink binary should exist" "[ ${found} -eq 1 ]"
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
    has_ver="$(json_field_exists "${RESULTS_JSON}" version_info version)"
    assertTrue "results.json version_info should have version" "[ ${has_ver} -eq 1 ]"
}

testBenchmarkPrimaryInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_primary
    has_primary="$(json_field_exists "${RESULTS_JSON}" primary_benchmark)"
    assertTrue "results.json should contain primary_benchmark data" "[ ${has_primary} -eq 1 ]"
}

testBenchmarkPrimaryHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_bench has_metrics has_results
    has_bench="$(json_field_exists "${RESULTS_JSON}" primary_benchmark benchmark)"
    has_metrics="$(json_field_exists "${RESULTS_JSON}" primary_benchmark performance_metrics)"
    has_results="$(json_field_exists "${RESULTS_JSON}" primary_benchmark results)"
    assertTrue "primary_benchmark should have benchmark field" "[ ${has_bench} -eq 1 ]"
    assertTrue "primary_benchmark should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "primary_benchmark should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkPrimaryThroughputAboveThreshold() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local avg_throughput
    avg_throughput="$(json_get "${RESULTS_JSON}" primary_benchmark average_throughput_ops_per_sec)"
    echo "[DIAG] TPC-DS avg throughput: ${avg_throughput} ops/sec (threshold: ${MINIMUM_TPCDS_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${RESULTS_JSON}" "${MINIMUM_TPCDS_THROUGHPUT}" primary_benchmark average_throughput_ops_per_sec)"
    assertTrue "TPC-DS throughput should be >= ${MINIMUM_TPCDS_THROUGHPUT}, got ${avg_throughput}" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkSecondaryInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local has_secondary
    has_secondary="$(json_field_exists "${RESULTS_JSON}" secondary_benchmark)"
    assertTrue "results.json should contain secondary_benchmark data" "[ ${has_secondary} -eq 1 ]"
}

testBenchmarkSecondaryThroughputAboveThreshold() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local avg_throughput
    avg_throughput="$(json_get "${RESULTS_JSON}" secondary_benchmark average_throughput_events_per_sec)"
    echo "[DIAG] Streaming avg throughput: ${avg_throughput} events/sec (threshold: ${MINIMUM_STREAMING_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${RESULTS_JSON}" "${MINIMUM_STREAMING_THROUGHPUT}" secondary_benchmark average_throughput_events_per_sec)"
    assertTrue "Streaming throughput should be >= ${MINIMUM_STREAMING_THROUGHPUT}, got ${avg_throughput}" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkSecondaryLatencyBelowThreshold() {
    if [ ! -f "${RESULTS_JSON}" ]; then startSkipping; return; fi
    local avg_latency
    avg_latency="$(json_get "${RESULTS_JSON}" secondary_benchmark average_latency_ms)"
    echo "[DIAG] Streaming avg latency: ${avg_latency} ms (threshold: ${MAXIMUM_STREAMING_LATENCY})"
    local has_latency
    has_latency="$(json_latency_le "${RESULTS_JSON}" "${MAXIMUM_STREAMING_LATENCY}" secondary_benchmark average_latency_ms)"
    assertTrue "Streaming latency should be <= ${MAXIMUM_STREAMING_LATENCY}ms, got ${avg_latency}" \
        "[ ${has_latency} -eq 1 ]"
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
    local has_primary
    has_primary="$(json_contains "${RESULTS_JSON}" primary_benchmark)"
    local has_secondary
    has_secondary="$(json_contains "${RESULTS_JSON}" secondary_benchmark)"
    local has_micro
    has_micro="$(json_contains "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "Should contain primary_benchmark data" "[ ${has_primary} -eq 1 ]"
    assertTrue "Should contain secondary_benchmark data" "[ ${has_secondary} -eq 1 ]"
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
Usage: flink_test.sh [OPTIONS]

Apache Flink ARM64 Performance Benchmark (shUnit2)

Prerequisites (must be pre-installed):
  - Java JDK 17+
  - Python 3.8+
  - Apache Flink ${SOFTWARE_VERSION} (at ${FLINK_HOME} or set FLINK_HOME)
  - scripts/json_helper.py

Note: shUnit2 will be auto-downloaded if not present.

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c)
  -s, --software-version   Flink version (default: ${SOFTWARE_VERSION})
  --flink-home             Flink installation path (default: ${FLINK_HOME})
  -v, --data-scale         TPC-DS scale factor (default: ${DATA_SCALE})
  -i, --iterations         Iterations per test (default: ${ITERATIONS})
  --parallelism            Flink parallelism (default: ${PARALLELISM})
  --check                  Check prerequisites only (no benchmark)
  -h, --help               Usage help

Examples:
  ./flink_test.sh                     # Full run + shUnit2 validation
  ./flink_test.sh --check             # Check prerequisites only
  ./flink_test.sh -p 3a,3b            # Only TPC-DS and streaming
  ./flink_test.sh --flink-home /opt/flink-2.1.0  # Custom Flink path
  ./flink_test.sh -i 5 -v 10          # 5 iterations, scale 10
EOF
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)      PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; FLINK_HOME="${SCRIPT_DIR}/flink-${SOFTWARE_VERSION}"; shift 2 ;;
            --flink-home)     FLINK_HOME="$2"; shift 2 ;;
            -v|--data-scale)  DATA_SCALE="$2"; shift 2 ;;
            -i|--iterations)  ITERATIONS="$2"; shift 2 ;;
            --parallelism)    PARALLELISM="$2"; shift 2 ;;
            --check)          check_only=1; shift ;;
            -h|--help)        usage; exit 0 ;;
            *)                log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    log "START" "Flink ARM64 Benchmark v${SOFTWARE_VERSION}"

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
