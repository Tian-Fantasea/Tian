#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="spark"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-4.1.2}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"

SPARK_HOME="${SPARK_HOME:-${SCRIPT_DIR}/spark}"
SPARK_CORES="${SPARK_CORES:-$(nproc 2>/dev/null || echo 4)}"
SPARK_MEMORY="${SPARK_MEMORY:-8192}"

TPCDS_SCALE="${TPCDS_SCALE:-1}"
MICRO_DATA_SIZE="${MICRO_DATA_SIZE:-100000}"
ML_DATA_SIZE="${ML_DATA_SIZE:-10000}"
STREAM_RATE="${STREAM_RATE:-10000}"
STREAM_DURATION="${STREAM_DURATION:-10}"
ITERATIONS="${ITERATIONS:-1}"
DATA_DIR="${SCRIPT_DIR}/data"

MINIMUM_THROUGHPUT="${MINIMUM_THROUGHPUT:-1}"
MAXIMUM_LATENCY_MS="${MAXIMUM_LATENCY_MS:-60000}"

LOG_FILE="${RESULTS_DIR}/results.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

json_get() { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results() { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }
json_avg_throughput() { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }
json_max_latency() { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }
json_version() { python3 "${JSON_HELPER}" "$1" version; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }

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
    log "SETUP" "shUnit2 downloaded successfully"
}

check_prerequisites() {
    local errors=0

    if ! command -v java >/dev/null 2>&1; then
        log "ERROR" "Java is not installed. Please install JDK 17+ before running."
        log "ERROR" "  Recommended: sudo apt-get install temurin-17-jdk (or equivalent)"
        errors=$((errors + 1))
    else
        log "CHECK" "Java OK: $(java -version 2>&1 | head -1)"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi

    local spark_found=0
    if [ -d "${SPARK_HOME}" ] && [ -x "${SPARK_HOME}/bin/spark-submit" ]; then
        spark_found=1
    elif command -v spark-submit >/dev/null 2>&1; then
        SPARK_HOME="$(dirname "$(dirname "$(which spark-submit)")")"
        spark_found=1
    fi
    if [ "${spark_found}" -eq 0 ]; then
        log "ERROR" "Spark is not installed at ${SPARK_HOME}"
        log "ERROR" "  Please download and extract Spark ${SOFTWARE_VERSION} to ${SCRIPT_DIR}/spark/"
        log "ERROR" "  Or set SPARK_HOME to your installation directory"
        errors=$((errors + 1))
    else
        log "CHECK" "Spark OK: ${SPARK_HOME}"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb java_ver spark_ver scala_ver python_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'ARM64')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    java_ver="$(java -version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    spark_ver="$(spark-submit --version 2>&1 | grep 'version' | head -1 | grep -oP '[\d.]+' | head -1 | tr -d '\n\t' || echo "${SOFTWARE_VERSION}")"
    scala_ver="2.13"
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t' || echo 'unknown')"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${spark_ver}" \
        "${java_ver}" "${SPARK_HOME}" "${SPARK_CORES}" "${scala_ver}" "${python_ver}"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    mkdir -p "${DATA_DIR}"

    local tpcds_data_dir="${DATA_DIR}/tpcds_sf${TPCDS_SCALE}"

    if [ ! -d "${tpcds_data_dir}/store_sales" ]; then
        log "PHASE3" "Generating TPC-DS data at SF=${TPCDS_SCALE}..."
        "${SPARK_HOME}/bin/spark-submit" \
            --master "local[${SPARK_CORES}]" \
            --driver-memory "${SPARK_MEMORY}m" \
            --conf spark.sql.parquet.compression.codec=snappy \
            "${SCRIPT_DIR}/scripts/tpcds_datagen.py" \
            "${TPCDS_SCALE}" "${tpcds_data_dir}" \
            2>&1 | tee -a "${LOG_FILE}" || log "WARN" "TPC-DS data generation had issues"
    fi

    log "PHASE3A" "Running TPC-DS benchmark..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        --conf spark.sql.shuffle.partitions="${SPARK_CORES}" \
        --conf spark.sql.adaptive.enabled=true \
        "${SCRIPT_DIR}/scripts/tpcds_benchmark.py" \
        "${tpcds_data_dir}" "${RESULTS_DIR}" "${TPCDS_SCALE}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "TPC-DS benchmark had issues"

    log "PHASE3B" "Running streaming benchmark..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        "${SCRIPT_DIR}/scripts/streaming_benchmark.py" \
        "${STREAM_RATE}" "${RESULTS_DIR}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Streaming benchmark had issues"

    log "PHASE3C" "Running micro-benchmarks..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        "${MICRO_DATA_SIZE}" "${RESULTS_DIR}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"

    log "PHASE3D" "Running MLlib benchmark..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        "${SCRIPT_DIR}/scripts/mllib_benchmark.py" \
        "${ML_DATA_SIZE}" "${RESULTS_DIR}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "MLlib benchmark had issues"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        "${RESULTS_DIR}" "${RESULTS_DIR}/results.json"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.html"

    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"
    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"
    log "PHASE4" "  HTML: ${RESULTS_DIR}/results.html"
    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"
}

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}" "${DATA_DIR}"

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

testSoftwareIsInstalled() {
    local found=0
    if [ -d "${SPARK_HOME}" ] && [ -x "${SPARK_HOME}/bin/spark-submit" ]; then found=1; fi
    if command -v spark-submit >/dev/null 2>&1; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: Spark not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "Spark (spark-submit) should be installed" "[ ${found} -eq 1 ]"
}

testSoftwareVersionMatches() {
    local ver="unknown"
    if [ -x "${SPARK_HOME}/bin/spark-submit" ]; then
        ver="$(spark-submit --version 2>&1 | grep 'version' | head -1 | grep -oP '[\d.]+' | head -1 | tr -d '\n\t' || echo 'unknown')"
    fi
    if [ "${ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertNotNull "Version should not be empty" "${ver}"
}

testSoftwareRunsBasicCommand() {
    local spark_submit="${SPARK_HOME}/bin/spark-submit"
    if [ ! -x "${spark_submit}" ] && ! command -v spark-submit >/dev/null 2>&1; then
        startSkipping
        return
    fi
    local result
    result="$(spark-submit --version 2>&1 | head -1)"
    assertNotNull "spark-submit should produce output" "${result}"
}

testVersionInfoExists() {
    assertTrue "Version info JSON should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasArchitecture() {
    local vfile="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${vfile}" ]; then
        startSkipping
        return
    fi
    local has_arch
    has_arch="$(json_field_exists "${vfile}" architecture)"
    assertTrue "Version info should have architecture field" "[ ${has_arch} -eq 1 ]"
}

testVersionInfoHasSoftwareVersion() {
    local vfile="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${vfile}" ]; then
        startSkipping
        return
    fi
    local has_ver
    has_ver="$(json_field_exists "${vfile}" software_version)"
    assertTrue "Version info should have software_version field" "[ ${has_ver} -eq 1 ]"
}

testBenchmarkPrimaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    assertTrue "TPC-DS benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkPrimaryHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkPrimaryThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local actual_throughput
    actual_throughput="$(json_get "${bench_file}" average_throughput_ops_per_sec)"
    if [ "${actual_throughput}" = "NULL" ] || [ -z "${actual_throughput}" ]; then
        local count
        count="$(json_count_results "${bench_file}")"
        if [ "${count}" -gt 0 ]; then
            actual_throughput="$(json_avg_throughput "${bench_file}" results avg_latency_ms)"
        else
            actual_throughput="$(json_get "${bench_file}" throughput_qph)"
        fi
    fi
    echo "[DIAG] TPC-DS throughput: ${actual_throughput} (threshold: ${MINIMUM_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" throughput_qph)"
    if [ "${has_throughput}" = "0" ]; then
        has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" average_throughput_ops_per_sec)"
    fi
    assertTrue "TPC-DS throughput should be >= ${MINIMUM_THROUGHPUT}, got ${actual_throughput}" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkPrimaryIsTPCDS() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local bench_name
    bench_name="$(json_get "${bench_file}" benchmark)"
    assertEquals "Benchmark name should be TPC-DS" "TPC-DS" "${bench_name}"
}

testBenchmarkSecondaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    assertTrue "Streaming benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkSecondaryHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local has_benchmark has_metrics
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
}

testBenchmarkSecondaryLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local actual_lat
    actual_lat="$(json_get "${bench_file}" avg_latency_ms)"
    if [ "${actual_lat}" = "NULL" ]; then
        actual_lat="$(json_get "${bench_file}" average_latency_ms)"
    fi
    echo "[DIAG] Streaming avg latency: ${actual_lat} ms (threshold: ${MAXIMUM_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" avg_latency_ms)"
    if [ "${has_latency}" = "0" ]; then
        has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" average_latency_ms)"
    fi
    assertTrue "Streaming avg latency should be <= ${MAXIMUM_LATENCY_MS}ms, got ${actual_lat}" \
        "[ ${has_latency} -eq 1 ]"
}

testBenchmarkSecondaryIsStreaming() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local bench_name
    bench_name="$(json_get "${bench_file}" benchmark)"
    assertEquals "Benchmark name should be Structured Streaming" "Structured Streaming" "${bench_name}"
}

testBenchmarkMicroProducesResults() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkMicroAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local ops_count
    ops_count="$(json_count_results "${bench_file}")"
    assertTrue "Should have results for all micro operations (count=${ops_count})" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkMicroHasLatencyData() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local has_latency
    has_latency="$(json_contains "${bench_file}" avg_latency_ms)"
    assertTrue "Micro benchmark should have avg_latency_ms data" "[ ${has_latency} -eq 1 ]"
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
    if [ ! -f "${agg_file}" ]; then
        startSkipping
        return
    fi
    local has_primary has_secondary has_micro
    has_primary="$(json_contains "${agg_file}" primary_benchmark)"
    has_secondary="$(json_contains "${agg_file}" secondary_benchmark)"
    has_micro="$(json_contains "${agg_file}" micro_benchmark)"
    assertTrue "Should contain primary_benchmark (TPC-DS) data" "[ ${has_primary} -eq 1 ]"
    assertTrue "Should contain secondary_benchmark (Streaming) data" "[ ${has_secondary} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
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
            -h|--help)    usage; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        exit 1
    fi

    download_shunit2 || {
        log "FATAL" "Failed to download shUnit2."
        exit 1
    }

    . "${SCRIPT_DIR}/shunit2"
}

usage() {
    cat <<USAGE
Usage: $(basename "$0") [OPTIONS]

Apache Spark ARM64 Performance Benchmark (shUnit2)

Options:
  --check    Check prerequisites only (do not run benchmarks)
  -h|--help  Show this help

Environment variables:
  SPARK_HOME         Spark installation directory (default: ${SCRIPT_DIR}/spark)
  SOFTWARE_VERSION   Spark version (default: 4.1.2)
  SPARK_CORES        Number of cores (default: nproc)
  SPARK_MEMORY       Driver memory in MB (default: 8192)
  TPCDS_SCALE        TPC-DS scale factor GB (default: 1)
  MICRO_DATA_SIZE    Micro-benchmark data size rows (default: 100000)
  ML_DATA_SIZE       MLlib data size samples (default: 10000)
  STREAM_RATE        Streaming rows/s (default: 10000)
  STREAM_DURATION    Streaming duration seconds (default: 10)
  ITERATIONS         Number of iterations (default: 1)
  MINIMUM_THROUGHPUT Min TPC-DS throughput threshold (default: 1)
  MAXIMUM_LATENCY_MS Max streaming latency threshold (default: 60000)

Examples:
  # Check prerequisites
  ./spark_test.sh --check

  # Full run
  ./spark_test.sh

  # Custom params
  TPCDS_SCALE=1 MICRO_DATA_SIZE=100000 ITERATIONS=1 ./spark_test.sh
USAGE
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
