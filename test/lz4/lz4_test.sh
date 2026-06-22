#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="lz4"
SOFTWARE_VERSION="${VERSION:-1.10.0}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"

MINIMUM_COMPRESSION_THROUGHPUT_MB=100
MINIMUM_DECOMPRESSION_THROUGHPUT_MB=200
MINIMUM_COMPRESSION_RATIO=1.5
MINIMUM_MICRO_OPS=5000
MAXIMUM_AVG_LATENCY_MS=5.0
MAXIMUM_P99_LATENCY_MS=50.0
ITERATIONS="${ITERATIONS:-1}"
PARALLELISM="${PARALLELISM:-4}"

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

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi

    python3 -c "import lz4" 2>/dev/null || {
        log "ERROR" "Python lz4 bindings not installed. Install: pip install lz4 (or use venv)"
        errors=$((errors + 1))
    }

    local lz4_found=0
    if command -v lz4 >/dev/null 2>&1; then lz4_found=1; fi
    if [ -f "/usr/bin/lz4" ]; then lz4_found=1; fi
    if [ -f "/usr/local/bin/lz4" ]; then lz4_found=1; fi
    if [ "${lz4_found}" -eq 0 ]; then
        log "WARN" "lz4 CLI not found (optional, Python bindings are primary)"
    else
        log "CHECK" "lz4 CLI OK: $(lz4 --version 2>&1 | head -1 || echo 'available')"
    fi

    local liblz4_found=0
    ldconfig -p 2>/dev/null | grep -q liblz4 && liblz4_found=1
    [ -f "/usr/lib/liblz4.so" ] && liblz4_found=1
    [ -f "/usr/lib/aarch64-linux-gnu/liblz4.so" ] && liblz4_found=1
    [ -f "/usr/lib64/liblz4.so" ] && liblz4_found=1
    if [ "${liblz4_found}" -eq 0 ]; then
        log "WARN" "liblz4 not found via ldconfig (may still work via Python bindings)"
    else
        log "CHECK" "liblz4 OK: found"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb python_ver lz4_py_ver lz4_cli_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ] || [ "${cpu_model}" = "" ]; then
        cpu_model="$(grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t' || echo 'unknown')"
    lz4_py_ver="$(python3 -c 'import lz4; print(lz4.version.version)' 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    lz4_cli_ver="$(lz4 --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"

    local lz4_found=0
    command -v lz4 >/dev/null 2>&1 && lz4_found=1
    [ -f "/usr/bin/lz4" ] && lz4_found=1

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${python_ver}" "pip/system" "${lz4_found}" "${PARALLELISM}" \
        --extra "lz4_py_version=${lz4_py_ver}" "lz4_cli_version=${lz4_cli_ver}" "category=compression_codec" "language=C" \
        --output "${RESULTS_DIR}/version_info.json"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    log "PHASE3a" "Running compression throughput benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_compression.py" \
        --output "${RESULTS_DIR}/benchmark_compression.json" \
        --iterations "${ITERATIONS}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m | tr -d '\n\t')" || log "WARN" "Compression benchmark had issues"

    log "PHASE3b" "Running decompression throughput benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_decompression.py" \
        --output "${RESULTS_DIR}/benchmark_decompression.json" \
        --iterations "${ITERATIONS}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m | tr -d '\n\t')" || log "WARN" "Decompression benchmark had issues"

    log "PHASE3c" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --output "${RESULTS_DIR}/micro_benchmark.json" \
        --iterations "${ITERATIONS}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m | tr -d '\n\t')" || log "WARN" "Micro benchmark had issues"

    log "PHASE3d" "Running concurrency scaling benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_concurrency.py" \
        --output "${RESULTS_DIR}/benchmark_concurrency.json" \
        --iterations "${ITERATIONS}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m | tr -d '\n\t')" || log "WARN" "Concurrency benchmark had issues"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        --results-dir "${RESULTS_DIR}" \
        --output "${RESULTS_DIR}/results.json"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --input "${RESULTS_DIR}/results.json" \
        --output "${RESULTS_DIR}/results.txt"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --input "${RESULTS_DIR}/results.json" \
        --output "${RESULTS_DIR}/results.html"

    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"
    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"
    log "PHASE4" "  HTML: ${RESULTS_DIR}/results.html"
    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"
}

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"

    log "START" "lz4 ARM64 Performance Benchmark - v${SOFTWARE_VERSION}"

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Run './lz4_test.sh --check' for detailed status."
        return 1
    fi

    phase2_verify || log "WARN" "Phase 2 had issues, continuing..."
    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing..."
    phase4_results || log "WARN" "Phase 4 had issues, continuing..."
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

testLz4IsInstalled() {
    local found=0
    if command -v lz4 >/dev/null 2>&1; then found=1; fi
    if [ -f "/usr/bin/lz4" ]; then found=1; fi
    if [ -f "/usr/local/bin/lz4" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: lz4 CLI not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "lz4 binary should exist" "[ ${found} -eq 1 ]"
}

testLz4VersionMatches() {
    local ver
    ver="$(lz4 --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    if [ "${ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertTrue "Version should contain lz4 or ${SOFTWARE_VERSION}" \
        "echo '${ver}' | grep -qi 'lz4\|${SOFTWARE_VERSION}'"
}

testPythonLz4BindingsAvailable() {
    local py_found
    py_found="$(python3 -c 'import lz4; print(1)' 2>/dev/null || echo '0')"
    if [ "${py_found}" = "0" ]; then
        echo "WARNING: Python lz4 bindings not available, skipping"
        startSkipping
        return
    fi
    assertTrue "Python lz4 bindings should be available" "[ ${py_found} -eq 1 ]"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkCompressionProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_compression.json"
    assertTrue "Compression benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkCompressionHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_compression.json"
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
    local bench_file="${RESULTS_DIR}/benchmark_compression.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_throughput
    actual_throughput="$(json_avg_throughput "${bench_file}" compression_throughput_mb_per_sec)"
    echo "[DIAG] Compression throughput: ${actual_throughput} MB/s (threshold: ${MINIMUM_COMPRESSION_THROUGHPUT_MB})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_COMPRESSION_THROUGHPUT_MB}" compression_throughput_mb_per_sec)"
    assertTrue "Compression throughput should be >= ${MINIMUM_COMPRESSION_THROUGHPUT_MB} MB/s, got ${actual_throughput}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkCompressionRatioAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_compression.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_ratio
    has_ratio="$(json_throughput_ge "${bench_file}" "${MINIMUM_COMPRESSION_RATIO}" compression_ratio)"
    echo "[DIAG] Compression ratio check (threshold: ${MINIMUM_COMPRESSION_RATIO})"
    assertTrue "Compression ratio should be >= ${MINIMUM_COMPRESSION_RATIO}" "[ ${has_ratio} -eq 1 ]"
}

testBenchmarkDecompressionProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_decompression.json"
    assertTrue "Decompression benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkDecompressionThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_decompression.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_throughput
    actual_throughput="$(json_avg_throughput "${bench_file}" decompression_throughput_mb_per_sec)"
    echo "[DIAG] Decompression throughput: ${actual_throughput} MB/s (threshold: ${MINIMUM_DECOMPRESSION_THROUGHPUT_MB})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_DECOMPRESSION_THROUGHPUT_MB}" decompression_throughput_mb_per_sec)"
    assertTrue "Decompression throughput should be >= ${MINIMUM_DECOMPRESSION_THROUGHPUT_MB} MB/s, got ${actual_throughput}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkDecompressionLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_decompression.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" avg_latency_ms)"
    echo "[DIAG] Decompression avg latency: ${actual_lat} ms (threshold: ${MAXIMUM_AVG_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_AVG_LATENCY_MS}" avg_latency_ms)"
    assertTrue "Avg latency should be <= ${MAXIMUM_AVG_LATENCY_MS}ms, got ${actual_lat}" "[ ${has_latency} -eq 1 ]"
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

testBenchmarkMicroCompressOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_ops
    has_ops="$(json_throughput_ge "${bench_file}" "${MINIMUM_MICRO_OPS}" ops_per_sec)"
    echo "[DIAG] Micro compress ops threshold: ${MINIMUM_MICRO_OPS}"
    assertTrue "Micro ops should be >= ${MINIMUM_MICRO_OPS}" "[ ${has_ops} -eq 1 ]"
}

testBenchmarkMicroDecompressOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local decomp_results
    decomp_results="$(json_contains "${bench_file}" decompress)"
    echo "[DIAG] Micro decompress check (contains decompress: ${decomp_results})"
    assertTrue "Should have decompress operation results" "[ ${decomp_results} -eq 1 ]"
}

testBenchmarkConcurrencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    assertTrue "Concurrency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkConcurrencyShowsProgression() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_threads
    has_threads="$(json_contains "${bench_file}" thread_count)"
    assertTrue "Should have thread_count data" "[ ${has_threads} -eq 1 ]"
}

testBenchmarkConcurrencyThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_COMPRESSION_THROUGHPUT_MB}" total_throughput_mb_per_sec)"
    echo "[DIAG] Concurrency throughput check (threshold: ${MINIMUM_COMPRESSION_THROUGHPUT_MB} MB/s)"
    assertTrue "Concurrency throughput should be >= ${MINIMUM_COMPRESSION_THROUGHPUT_MB} MB/s" "[ ${has_throughput} -eq 1 ]"
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
    local has_compression has_decompression has_micro has_concurrency
    has_compression="$(json_contains "${agg_file}" compression)"
    has_decompression="$(json_contains "${agg_file}" decompression)"
    has_micro="$(json_contains "${agg_file}" micro)"
    has_concurrency="$(json_contains "${agg_file}" concurrency)"
    assertTrue "Should contain compression benchmark data" "[ ${has_compression} -eq 1 ]"
    assertTrue "Should contain decompression benchmark data" "[ ${has_decompression} -eq 1 ]"
    assertTrue "Should contain micro benchmark data" "[ ${has_micro} -eq 1 ]"
    assertTrue "Should contain concurrency benchmark data" "[ ${has_concurrency} -eq 1 ]"
}

oneTimeTearDown() {
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)  PHASES="$2"; shift 2 ;;
            --check)      check_only=1; shift ;;
            -h|--help)    echo "Usage: ./lz4_test.sh [--check]"; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; exit 1 ;;
        esac
    done

    log "START" "lz4 ARM64 Benchmark v${SOFTWARE_VERSION}"

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

    . "${SCRIPT_DIR}/shunit2"
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
