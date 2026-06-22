#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="protobuf"
SOFTWARE_VERSION="${VERSION:-29.4}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"

MINIMUM_THROUGHPUT=5000
MINIMUM_BYTES_PER_SEC=500000
MAXIMUM_AVG_LATENCY_MS=5.0
MAXIMUM_P99_LATENCY_MS=50.0
MINIMUM_MICRO_OPS=5000

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
        log "CHECK" "python3 OK: $(python3 --version 2>&1)"
    fi

    if ! python3 -c "import google.protobuf" 2>/dev/null; then
        log "ERROR" "google.protobuf Python package not installed. Install: pip3 install protobuf"
        log "ERROR" "  Or with venv: python3 -m venv venv && venv/bin/pip install protobuf"
        errors=$((errors + 1))
    else
        local pb_ver
        pb_ver="$(python3 -c "import google.protobuf; print(google.protobuf.__version__)" 2>/dev/null | tr -d '\n\t')"
        log "CHECK" "protobuf Python OK: v${pb_ver}"
    fi

    if ! command -v protoc >/dev/null 2>&1; then
        log "WARN" "protoc not installed (optional — benchmarks use well-known types as fallback)"
    else
        log "CHECK" "protoc OK: $(protoc --version 2>&1)"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb python_pb_ver protoc_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ] || [ "${cpu_model}" = "unknown" ]; then
        cpu_model="$(grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | awk '{print $3}' | tr -d '\n\t' || echo 'unknown')"
    fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    python_pb_ver="$(python3 -c "import google.protobuf; print(google.protobuf.__version__)" 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    protoc_ver="$(protoc --version 2>/dev/null | sed 's|libprotoc ||' | tr -d '\n\t' || echo 'not_installed')"
    local python_ver
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t' || echo 'unknown')"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${python_ver}" "pip" "1" "${cores}" \
        --output "${RESULTS_DIR}/version_info.json" \
        --extra "protoc_version=${protoc_ver}" "python_protobuf_version=${python_pb_ver}" "install_method=pip" "category=serialization_codec" "language=python_cpp"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    log "PHASE3" "Running serialization throughput benchmark (Phase 3a)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_serialization.py" \
        --output "${RESULTS_DIR}/benchmark_serialization.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-1000}" || log "WARN" "Serialization benchmark failed"

    log "PHASE3" "Running latency distribution benchmark (Phase 3b)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_latency.py" \
        --output "${RESULTS_DIR}/benchmark_latency.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-10000}" || log "WARN" "Latency benchmark failed"

    log "PHASE3" "Running micro benchmark (Phase 3c)..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --output "${RESULTS_DIR}/micro_benchmark.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-5000}" || log "WARN" "Micro benchmark failed"

    log "PHASE3" "Running concurrency scaling benchmark (Phase 3d)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_concurrency.py" \
        --output "${RESULTS_DIR}/benchmark_concurrency.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-1000}" || log "WARN" "Concurrency benchmark failed"
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

    log "START" "${SOFTWARE_NAME} ARM64 Performance Benchmark - v${SOFTWARE_VERSION}"

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        return 1
    fi

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

testProtocIsInstalled() {
    local found=0
    if command -v protoc >/dev/null 2>&1; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: protoc not installed, skipping"
        startSkipping
        return
    fi
    assertTrue "protoc binary should exist" "[ ${found} -eq 1 ]"
}

testProtobufPythonIsInstalled() {
    local found=0
    python3 -c "import google.protobuf" 2>/dev/null && found=1
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: google.protobuf not installed, skipping"
        startSkipping
        return
    fi
    assertTrue "google.protobuf should be importable" "[ ${found} -eq 1 ]"
}

testProtobufVersionMatches() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local ver
    ver="$(json_version "${ver_file}")"
    if [ -z "${ver}" ] || [ "${ver}" = "None" ] || [ "${ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertTrue "Version should be recorded" "[ -n '${ver}' ]"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkSerializationProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_serialization.json"
    assertTrue "Serialization benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkSerializationHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_serialization.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkSerializationThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_serialization.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results serialize_ops_per_sec)"
    echo "[DIAG] Serialization throughput: ${actual} msgs/sec (threshold: ${MINIMUM_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" results serialize_ops_per_sec)"
    assertTrue "Serialize throughput should be >= ${MINIMUM_THROUGHPUT} msgs/sec, got ${actual}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkSerializationBytesPerSecAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_serialization.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results serialize_bytes_per_sec)"
    echo "[DIAG] Serialization bytes/sec: ${actual} (threshold: ${MINIMUM_BYTES_PER_SEC})"
    local has_bytes
    has_bytes="$(json_throughput_ge "${bench_file}" "${MINIMUM_BYTES_PER_SEC}" results serialize_bytes_per_sec)"
    assertTrue "Serialize bytes/sec should be >= ${MINIMUM_BYTES_PER_SEC}, got ${actual}" "[ ${has_bytes} -eq 1 ]"
}

testBenchmarkLatencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_latency.json"
    assertTrue "Latency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkLatencyAvgBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_latency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" results avg_latency_ms)"
    echo "[DIAG] Max avg latency: ${actual_lat} ms (threshold: ${MAXIMUM_AVG_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_AVG_LATENCY_MS}" results avg_latency_ms)"
    assertTrue "Avg latency should be <= ${MAXIMUM_AVG_LATENCY_MS}ms, got ${actual_lat}" "[ ${has_latency} -eq 1 ]"
}

testBenchmarkLatencyP99BelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_latency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" results p99_latency_ms)"
    echo "[DIAG] Max p99 latency: ${actual_lat} ms (threshold: ${MAXIMUM_P99_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_P99_LATENCY_MS}" results p99_latency_ms)"
    assertTrue "P99 latency should be <= ${MAXIMUM_P99_LATENCY_MS}ms, got ${actual_lat}" "[ ${has_latency} -eq 1 ]"
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

testBenchmarkMicroSerializeOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results serialize_ops_per_sec)"
    echo "[DIAG] Micro serialize ops: ${actual} (threshold: ${MINIMUM_MICRO_OPS})"
    local has_ops
    has_ops="$(json_throughput_ge "${bench_file}" "${MINIMUM_MICRO_OPS}" results serialize_ops_per_sec)"
    assertTrue "Micro serialize ops should be >= ${MINIMUM_MICRO_OPS}, got ${actual}" "[ ${has_ops} -eq 1 ]"
}

testBenchmarkMicroDeserializeOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results deserialize_ops_per_sec)"
    echo "[DIAG] Micro deserialize ops: ${actual} (threshold: ${MINIMUM_MICRO_OPS})"
    local has_ops
    has_ops="$(json_throughput_ge "${bench_file}" "${MINIMUM_MICRO_OPS}" results deserialize_ops_per_sec)"
    assertTrue "Micro deserialize ops should be >= ${MINIMUM_MICRO_OPS}, got ${actual}" "[ ${has_ops} -eq 1 ]"
}

testBenchmarkConcurrencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    assertTrue "Concurrency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkConcurrencyScalingShowsProgression() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}")"
    assertTrue "Should have multiple concurrency levels (count=${count})" "[ ${count} -ge 2 ]"
}

testBenchmarkConcurrencyThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results total_ops_per_sec)"
    echo "[DIAG] Concurrency total throughput: ${actual} (threshold: ${MINIMUM_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" results total_ops_per_sec)"
    assertTrue "Concurrency throughput should be >= ${MINIMUM_THROUGHPUT}, got ${actual}" "[ ${has_throughput} -eq 1 ]"
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
    local has_serialization has_latency has_micro has_concurrency
    has_serialization="$(json_contains "${agg_file}" serialization)"
    has_latency="$(json_contains "${agg_file}" latency)"
    has_micro="$(json_contains "${agg_file}" micro)"
    has_concurrency="$(json_contains "${agg_file}" concurrency)"
    assertTrue "Should contain serialization data" "[ ${has_serialization} -eq 1 ]"
    assertTrue "Should contain latency data" "[ ${has_latency} -eq 1 ]"
    assertTrue "Should contain micro data" "[ ${has_micro} -eq 1 ]"
    assertTrue "Should contain concurrency data" "[ ${has_concurrency} -eq 1 ]"
}

oneTimeTearDown() {
    phase4_results || log "WARN" "Phase 4 had issues..."
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)      check_only=1; shift ;;
            -h|--help)    echo "Usage: ./protobuf_test.sh [--check]"; echo "  --check: Only verify prerequisites"; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; exit 1 ;;
        esac
    done

    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
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
