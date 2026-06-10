#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="bolt"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-1.4.3}"
SHUNIT_PARENT="${SCRIPT_DIR}/bolt_arm64_perf_test.sh"

MINIMUM_THROUGHPUT=10000
MAXIMUM_LATENCY_MS=100

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

json_get() { python3 "${JSON_HELPER}" "$1" get "$2" "$3"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "$3" "$4"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "$2" "$3" "$4"; }
json_count_results() { python3 "${JSON_HELPER}" "$1" count_results; }
json_version() { python3 "${JSON_HELPER}" "$1" version; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"
}

oneTimeTearDown() {
    if [ -f "${RESULTS_DIR}/all_results.json" ]; then
        echo "Results aggregated at: ${RESULTS_DIR}/all_results.json"
    fi
}

setUp() {
    rm -f "${RESULTS_DIR}/test_temp_*.json"
}

tearDown() {
    rm -f "${RESULTS_DIR}/test_temp_*.json"
}

testArchitectureIsARM64() {
    local arch
    arch="$(uname -m | tr -d '\n\t')"
    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \
        "[ '${arch}' = 'aarch64' ] || [ '${arch}' = 'arm64' ]"
}

testGoIsInstalled() {
    assertTrue "Go should be installed" "command -v go"
}

testGoVersionIsNewEnough() {
    local go_ver
    go_ver="$(go version 2>&1 | head -1 | tr -d '\n\t')"
    local major
    major="$(echo "${go_ver}" | grep -oP 'go[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 | sed 's/go//' | cut -d. -f1 | tr -d '\n\t')"
    local minor
    minor="$(echo "${go_ver}" | grep -oP 'go[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 | sed 's/go//' | cut -d. -f2 | tr -d '\n\t')"
    assertTrue "Go version should be >= 1.22" \
        "[ ${major} -ge 1 ] && ([ ${major} -gt 1 ] || [ ${minor} -ge 22 ])"
}

testBboltBinaryExists() {
    assertTrue "micro_benchmark binary should exist" \
        "[ -x '${SCRIPT_DIR}/scripts/micro_benchmark' ]"
}

testBenchmarkYcsbBinaryExists() {
    assertTrue "benchmark_ycsb binary should exist" \
        "[ -x '${SCRIPT_DIR}/scripts/benchmark_ycsb' ]"
}

testBenchmarkThroughputBinaryExists() {
    assertTrue "benchmark_throughput binary should exist" \
        "[ -x '${SCRIPT_DIR}/scripts/benchmark_throughput' ]"
}

testBenchmarkConcurrencyBinaryExists() {
    assertTrue "benchmark_concurrency binary should exist" \
        "[ -x '${SCRIPT_DIR}/scripts/benchmark_concurrency' ]"
}

testBboltCreatesDatabase() {
    local db_path="${RESULTS_DIR}/test_temp_verify.db"
    rm -f "${db_path}"
    "${SCRIPT_DIR}/scripts/micro_benchmark" --mode verify --db-path "${db_path}" --results-dir "${RESULTS_DIR}" 2>/dev/null
    assertTrue "bbolt should create database file" "[ -f '${db_path}' ]"
    rm -f "${db_path}"
}

testVersionInfoJSONExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasRequiredFields() {
    local vfile="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${vfile}" ]; then startSkipping; return; fi
    local has_arch
    has_arch="$(json_field_exists "${vfile}" architecture | tr -d '\n\t')"
    assertTrue "Should have architecture field" "[ ${has_arch} -eq 1 ]"
    local has_software
    has_software="$(json_field_exists "${vfile}" software | tr -d '\n\t')"
    assertTrue "Should have software field" "[ ${has_software} -eq 1 ]"
    local has_timestamp
    has_timestamp="$(json_field_exists "${vfile}" timestamp | tr -d '\n\t')"
    assertTrue "Should have timestamp field" "[ ${has_timestamp} -eq 1 ]"
}

testVersionInfoArchitectureIsARM64() {
    local vfile="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${vfile}" ]; then startSkipping; return; fi
    local arch
    arch="$(json_get "${vfile}" architecture | tr -d '\n\t')"
    assertTrue "Version info architecture should be ARM64" \
        "[ '${arch}' = 'aarch64' ] || [ '${arch}' = 'arm64' ]"
}

testVersionInfoVersionMatches() {
    local vfile="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${vfile}" ]; then startSkipping; return; fi
    local ver
    ver="$(json_version "${vfile}" | tr -d '\n\t')"
    assertEquals "Bbolt version should match" "${SOFTWARE_VERSION}" "${ver}"
}

testBenchmarkYcsbProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    assertTrue "YCSB benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkYcsbHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_bench
    has_bench="$(json_contains "${bench_file}" benchmark | tr -d '\n\t')"
    assertTrue "Should contain benchmark field" "[ ${has_bench} -eq 1 ]"
    local has_metrics
    has_metrics="$(json_contains "${bench_file}" performance_metrics | tr -d '\n\t')"
    assertTrue "Should contain performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    local has_results
    has_results="$(json_contains "${bench_file}" results | tr -d '\n\t')"
    assertTrue "Should contain results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkYcsbThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" ops_per_sec throughput | tr -d '\n\t')"
    assertTrue "YCSB throughput should be >= ${MINIMUM_THROUGHPUT} ops/sec" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkYcsbLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local latency_ok
    latency_ok="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" avg_latency_ms latency_ms | tr -d '\n\t')"
    assertTrue "YCSB avg latency should be <= ${MAXIMUM_LATENCY_MS}ms on embedded KV" "[ ${latency_ok} -eq 1 ]"
}

testBenchmarkThroughputProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    assertTrue "Throughput benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkThroughputScalingShowsProgression() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}" | tr -d '\n\t')"
    assertTrue "Should have throughput results at multiple key counts" "[ ${count} -ge 3 ]"
}

testBenchmarkThroughputOpsPerSecAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" ops_per_sec throughput | tr -d '\n\t')"
    assertTrue "Throughput ops/sec should be >= ${MINIMUM_THROUGHPUT}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkMicroProducesResults() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkMicroAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}" | tr -d '\n\t')"
    assertTrue "Should have results for all micro operations" "[ ${count} -ge 4 ]"
}

testBenchmarkMicroContainsOperations() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_put
    has_put="$(json_contains "${bench_file}" put | tr -d '\n\t')"
    assertTrue "Should contain put operation" "[ ${has_put} -eq 1 ]"
    local has_get
    has_get="$(json_contains "${bench_file}" get | tr -d '\n\t')"
    assertTrue "Should contain get operation" "[ ${has_get} -eq 1 ]"
    local has_delete
    has_delete="$(json_contains "${bench_file}" delete | tr -d '\n\t')"
    assertTrue "Should contain delete operation" "[ ${has_delete} -eq 1 ]"
}

testBenchmarkMicroLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local latency_ok
    latency_ok="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" avg_latency_ms latency_ms | tr -d '\n\t')"
    assertTrue "Micro benchmark avg latency should be <= ${MAXIMUM_LATENCY_MS}ms on embedded KV" "[ ${latency_ok} -eq 1 ]"
}

testBenchmarkConcurrencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    assertTrue "Concurrency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkConcurrencyScalingShowsProgression() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}" | tr -d '\n\t')"
    assertTrue "Should have results at multiple concurrency levels" "[ ${count} -ge 3 ]"
}

testBenchmarkConcurrencyLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local latency_ok
    latency_ok="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" avg_latency_ms latency_ms | tr -d '\n\t')"
    assertTrue "Concurrency avg latency should be <= ${MAXIMUM_LATENCY_MS}ms on embedded KV" "[ ${latency_ok} -eq 1 ]"
}

testAggregatedResultsExist() {
    assertTrue "Aggregated results file should exist" \
        "[ -f '${RESULTS_DIR}/all_results.json' ]"
}

testHtmlReportGenerated() {
    assertTrue "HTML report should exist" \
        "[ -f '${RESULTS_DIR}/benchmark_report.html' ]"
}

testSummaryReportGenerated() {
    assertTrue "Summary report should exist" \
        "[ -f '${RESULTS_DIR}/benchmark_summary.txt' ]"
}

testAggregatedResultsContainsAllBenchmarks() {
    local agg_file="${RESULTS_DIR}/all_results.json"
    if [ ! -f "${agg_file}" ]; then startSkipping; return; fi
    local has_ycsb
    has_ycsb="$(json_contains "${agg_file}" ycsb | tr -d '\n\t')"
    assertTrue "Should contain ycsb data" "[ ${has_ycsb} -eq 1 ]"
    local has_throughput
    has_throughput="$(json_contains "${agg_file}" throughput | tr -d '\n\t')"
    assertTrue "Should contain throughput data" "[ ${has_throughput} -eq 1 ]"
    local has_micro
    has_micro="$(json_contains "${agg_file}" micro | tr -d '\n\t')"
    assertTrue "Should contain micro data" "[ ${has_micro} -eq 1 ]"
    local has_concurrency
    has_concurrency="$(json_contains "${agg_file}" concurrency | tr -d '\n\t')"
    assertTrue "Should contain concurrency data" "[ ${has_concurrency} -eq 1 ]"
}

. "${SCRIPT_DIR}/shunit2"
