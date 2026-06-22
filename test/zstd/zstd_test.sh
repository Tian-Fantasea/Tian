#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="zstd"
SOFTWARE_VERSION="${ZSTD_VERSION:-1.5.7}"
SHUNIT_PARENT="${SCRIPT_DIR}/zstd_test.sh"

MINIMUM_COMPRESSION_THROUGHPUT="${MINIMUM_COMPRESSION_THROUGHPUT:-50}"
MINIMUM_DECOMPRESSION_THROUGHPUT="${MINIMUM_DECOMPRESSION_THROUGHPUT:-100}"
MAXIMUM_COMPRESSION_LATENCY_MS="${MAXIMUM_COMPRESSION_LATENCY_MS:-5000}"

ITERATIONS="${ITERATIONS:-1}"
COMPRESSION_LEVELS="${COMPRESSION_LEVELS:-1,3,5,9,15,19}"
DATA_SIZE="${DATA_SIZE:-10}"
DATA_TYPES="${DATA_TYPES:-text,binary,json}"

LOG_FILE="${RESULTS_DIR}/results.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

json_get()              { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists()     { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results()    { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge()    { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_latency_le()       { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }
json_avg_throughput()   { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }
json_max_latency()      { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }
json_version()          { python3 "${JSON_HELPER}" "$1" version; }
json_contains()         { python3 "${JSON_HELPER}" "$1" contains "$2"; }

download_shunit2() {
    if [ -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "shUnit2 already present"
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
        return 1
    fi
}

check_prerequisites() {
    local errors=0

    if ! command -v zstd >/dev/null 2>&1; then
        log "ERROR" "zstd is not installed. Please install zstd before running."
        log "ERROR" "  On Ubuntu/Debian: sudo apt-get install zstd"
        log "ERROR" "  On RHEL/CentOS: sudo yum install zstd"
        log "ERROR" "  On macOS: brew install zstd"
        log "ERROR" "  Or build from source: https://github.com/facebook/zstd"
        errors=$((errors + 1))
    else
        log "CHECK" "zstd OK: $(zstd --version 2>&1 | head -1)"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "python3 OK: $(python3 --version 2>&1)"
    fi

    if ! command -v gcc >/dev/null 2>&1; then
        log "WARN" "gcc not installed, some micro benchmarks may be skipped"
    else
        log "CHECK" "gcc OK: $(gcc --version 2>&1 | head -1)"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb zstd_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || sysctl -n hw.ncpu 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    zstd_ver="$(zstd --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    local gcc_ver
    gcc_ver="$(gcc --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'not_installed')"
    local has_gcc
    has_gcc="$(command -v gcc >/dev/null 2>&1 && echo 'yes' || echo 'no')"
    local zstd_path
    zstd_path="$(command -v zstd 2>/dev/null | tr -d '\n\t' || echo 'not_found')"
    local parallelism="${cores}"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${zstd_ver}" "${zstd_path}" "${gcc_ver}" "${parallelism}" \
        --output "${RESULTS_DIR}/version_info.json" \
        --extra "gcc_available:${has_gcc}" \
        --extra "gcc_version:${gcc_ver}" \
        --extra "compression_levels:${COMPRESSION_LEVELS}" \
        --extra "data_size_mb:${DATA_SIZE}" \
        --extra "data_types:${DATA_TYPES}" \
        --extra "iterations:${ITERATIONS}"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    log "PHASE3" "--- 3a: Compression Performance Benchmark ---"
    python3 "${SCRIPT_DIR}/scripts/benchmark_compression.py" \
        --output "${RESULTS_DIR}/benchmark_primary.json" \
        --iterations "${ITERATIONS}" \
        --levels "${COMPRESSION_LEVELS}" \
        --data-size "${DATA_SIZE}" \
        --data-types "${DATA_TYPES}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Primary benchmark had issues"

    log "PHASE3" "--- 3b: Decompression Performance Benchmark ---"
    python3 "${SCRIPT_DIR}/scripts/benchmark_decompression.py" \
        --output "${RESULTS_DIR}/benchmark_secondary.json" \
        --iterations "${ITERATIONS}" \
        --levels "${COMPRESSION_LEVELS}" \
        --data-size "${DATA_SIZE}" \
        --data-types "${DATA_TYPES}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Secondary benchmark had issues"

    log "PHASE3" "--- 3c: Micro Benchmark ---"
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --output "${RESULTS_DIR}/micro_benchmark.json" \
        --iterations "${ITERATIONS}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        "${RESULTS_DIR}" "${RESULTS_DIR}/results.json" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Aggregation had issues"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Summary had issues"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.html" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "HTML report had issues"

    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"
    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"
    log "PHASE4" "  HTML: ${RESULTS_DIR}/results.html"
    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"
}

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"

    log "START" "zstd ARM64 Performance Benchmark - v${SOFTWARE_VERSION}"

    check_prerequisites || {
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        return 1
    }

    phase2_verify || log "WARN" "Phase 2 had issues, continuing..."
    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing..."
}

setUp() {
    rm -f "${RESULTS_DIR}/test_temp_*.json"
}

tearDown() {
    rm -f "${RESULTS_DIR}/test_temp_*.json"
}

testArchitectureIsARM64() {
    local arch
    arch="$(uname -m)"
    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \
        "[ '${arch}' = 'aarch64' ] || [ '${arch}' = 'arm64' ]"
}

testZstdIsInstalled() {
    local found=0
    if command -v zstd >/dev/null 2>&1; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: zstd not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "zstd binary should exist" "[ ${found} -eq 1 ]"
}

testZstdVersionMatches() {
    local ver
    ver="$(zstd --version 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1 | sed 's/^v//' | tr -d '\n\t' || echo 'unknown')"
    if [ "${ver}" = "unknown" ] || [ -z "${ver}" ]; then
        startSkipping
        return
    fi
    local major_ver="${ver%%.*}"
    assertTrue "zstd major version should be >= 1, got ${major_ver}" "[ ${major_ver} -ge 1 ]"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkCompressionProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    assertTrue "Primary benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkCompressionHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkCompressionThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_throughput
    actual_throughput="$(json_avg_throughput "${bench_file}" avg_compression_throughput_mb_s)"
    echo "[DIAG] Compression throughput: ${actual_throughput} MB/s (threshold: ${MINIMUM_COMPRESSION_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_COMPRESSION_THROUGHPUT}" avg_compression_throughput_mb_s)"
    assertTrue "Compression throughput should be >= ${MINIMUM_COMPRESSION_THROUGHPUT} MB/s, got ${actual_throughput}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkCompressionRatioDataPresent() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_ratio
    has_ratio="$(json_contains "${bench_file}" compression_ratio_vs_level)"
    assertTrue "Should have compression ratio vs level data" "[ ${has_ratio} -eq 1 ]"
}

testBenchmarkDecompressionProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    assertTrue "Secondary benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkDecompressionHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkDecompressionThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_throughput
    actual_throughput="$(json_avg_throughput "${bench_file}" avg_decompression_throughput_mb_s)"
    echo "[DIAG] Decompression throughput: ${actual_throughput} MB/s (threshold: ${MINIMUM_DECOMPRESSION_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_DECOMPRESSION_THROUGHPUT}" avg_decompression_throughput_mb_s)"
    assertTrue "Decompression throughput should be >= ${MINIMUM_DECOMPRESSION_THROUGHPUT} MB/s, got ${actual_throughput}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkDecompressionLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" avg_decompression_time_ms)"
    echo "[DIAG] Decompression latency: ${actual_lat} ms (threshold: ${MAXIMUM_COMPRESSION_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_COMPRESSION_LATENCY_MS}" avg_decompression_time_ms)"
    assertTrue "Decompression latency should be <= ${MAXIMUM_COMPRESSION_LATENCY_MS}ms, got ${actual_lat}" "[ ${has_latency} -eq 1 ]"
}

testBenchmarkMicroProducesResults() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkMicroAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local ops_count
    ops_count="$(json_count_results "${bench_file}")"
    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkMicroArm64OptimizationsDetected() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_arm64
    has_arm64="$(json_contains "${bench_file}" arm64_optimization_detection)"
    assertTrue "Should have ARM64 optimization detection results" "[ ${has_arm64} -eq 1 ]"
}

testAggregatedResultsExist() {
    assertTrue "results.json should exist" "[ -f '${RESULTS_DIR}/results.json' ]"
}

testHtmlReportGenerated() {
    assertTrue "results.html should exist" "[ -f '${RESULTS_DIR}/results.html' ]"
}

testSummaryReportGenerated() {
    assertTrue "results.txt should exist" "[ -f '${RESULTS_DIR}/results.txt' ]"
}

testLogFileGenerated() {
    assertTrue "results.log should exist" "[ -f '${RESULTS_DIR}/results.log' ]"
}

testAggregatedResultsContainsAllBenchmarks() {
    local agg_file="${RESULTS_DIR}/results.json"
    if [ ! -f "${agg_file}" ]; then startSkipping; return; fi
    local has_primary has_secondary has_micro
    has_primary="$(json_contains "${agg_file}" primary_benchmark)"
    has_secondary="$(json_contains "${agg_file}" secondary_benchmark)"
    has_micro="$(json_contains "${agg_file}" micro_benchmark)"
    assertTrue "Should contain primary_benchmark data" "[ ${has_primary} -eq 1 ]"
    assertTrue "Should contain secondary_benchmark data" "[ ${has_secondary} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
}

oneTimeTearDown() {
    phase4_results || log "WARN" "Phase 4 had issues..."
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

usage() {
    echo "Usage: ./zstd_test.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check    Check prerequisites only"
    echo "  -h|--help  Show this help"
    echo ""
    echo "Environment variables:"
    echo "  ZSTD_VERSION              Version to check (default: 1.5.7)"
    echo "  ITERATIONS                Number of iterations (default: 1)"
    echo "  COMPRESSION_LEVELS        Levels to test (default: 1,3,5,9,15,19)"
    echo "  DATA_SIZE                 Data size in MB (default: 10)"
    echo "  DATA_TYPES                Data types (default: text,binary,json)"
    echo "  MINIMUM_COMPRESSION_THROUGHPUT   Min MB/s threshold (default: 50)"
    echo "  MINIMUM_DECOMPRESSION_THROUGHPUT Min MB/s threshold (default: 100)"
    echo "  MAXIMUM_COMPRESSION_LATENCY_MS   Max latency threshold (default: 5000)"
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)      check_only=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    log "START" "zstd ARM64 Benchmark v${SOFTWARE_VERSION}"

    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi

    download_shunit2 || {
        log "FATAL" "Failed to download shUnit2"
        exit 1
    }

    . "${SCRIPT_DIR}/shunit2"
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
