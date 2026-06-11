#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="redis"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-8.0.2}"
REDIS_HOME="${SCRIPT_DIR}/redis-${SOFTWARE_VERSION}"
REDIS_PORT="${REDIS_PORT:-6380}"
SHUNIT_PARENT="${SCRIPT_DIR}/redis_arm64_perf_test.sh"

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

MINIMUM_THROUGHPUT_GET=5000
MINIMUM_THROUGHPUT_SET=3000
MAXIMUM_LATENCY_P99_MS=50.0
MINIMUM_YCSB_THROUGHPUT=1000

json_get() { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results() { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "${@:2}"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "${@:2}"; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }
json_version() { python3 "${JSON_HELPER}" "$1" version; }

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"
    if [ "$(uname -m)" != "aarch64" ] && [ "$(uname -m)" != "arm64" ]; then
        echo "WARNING: Not running on ARM64 architecture"
    fi
}

oneTimeTearDown() {
    if [ -f "${RESULTS_DIR}/all_results.json" ]; then
        echo "Results aggregated at: ${RESULTS_DIR}/all_results.json"
    fi
    if [ -f "${RESULTS_DIR}/benchmark_report.html" ]; then
        echo "HTML report at: ${RESULTS_DIR}/benchmark_report.html"
    fi
    echo "shUnit2 test suite completed."
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

testRedisBinaryExists() {
    assertTrue "redis-server binary should exist" \
        "[ -x '${REDIS_HOME}/src/redis-server' ]"
}

testRedisCliBinaryExists() {
    assertTrue "redis-cli binary should exist" \
        "[ -x '${REDIS_HOME}/src/redis-cli' ]"
}

testRedisBenchmarkBinaryExists() {
    assertTrue "redis-benchmark binary should exist" \
        "[ -x '${REDIS_HOME}/src/redis-benchmark' ]"
}

testRedisVersionMatches() {
    local ver_output
    ver_output="$("${REDIS_HOME}/src/redis-server" --version 2>&1 | grep -oP 'v=[\d.]+' | cut -d= -f2 | tr -d '\n\t')"
    assertNotNull "Version should not be empty" "${ver_output}"
}

testRedisServerResponsive() {
    if ! "${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>/dev/null | grep -q "PONG"; then
        echo "[DIAG] Redis server not running on port ${REDIS_PORT}, skipping PING test"
        startSkipping
        return
    fi
    local result
    result="$("${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>&1)"
    assertContains "Redis should respond to PING" "${result}" "PONG"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" \
        "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasArchitecture() {
    local bench_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_arch
    has_arch="$(json_field_exists "${bench_file}" architecture)"
    assertTrue "Version info should have architecture field" "[ ${has_arch} -eq 1 ]"
}

testBenchmarkYCSBProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    assertTrue "YCSB benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkYCSBHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testBenchmarkYCSBThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_ycsb
    actual_ycsb="$(json_get "${bench_file}" summary avg_throughput_ops_per_sec)"
    echo "[DIAG] YCSB overall throughput: ${actual_ycsb} ops/sec (threshold: ${MINIMUM_YCSB_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_YCSB_THROUGHPUT}" summary avg_throughput_ops_per_sec)"
    assertTrue "YCSB throughput should be >= ${MINIMUM_YCSB_THROUGHPUT} ops/sec, got ${actual_ycsb}" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkYCSBReadLatencyAcceptable() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_get "${bench_file}" results 0 p99_read_latency_ms)"
    echo "[DIAG] YCSB read p99 latency: ${actual_lat} ms (threshold: ${MAXIMUM_LATENCY_P99_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_P99_MS}" results 0 p99_read_latency_ms)"
    assertTrue "YCSB read p99 latency should be <= ${MAXIMUM_LATENCY_P99_MS} ms, got ${actual_lat}" \
        "[ ${has_latency} -eq 1 ]"
}

testBenchmarkThroughputProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    assertTrue "Throughput benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkThroughputHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testBenchmarkThroughputGETAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_get
    actual_get="$(json_get "${bench_file}" throughput_get)"
    echo "[DIAG] GET throughput: ${actual_get} ops/sec (threshold: ${MINIMUM_THROUGHPUT_GET})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT_GET}" throughput_get)"
    assertTrue "GET throughput should be >= ${MINIMUM_THROUGHPUT_GET} ops/sec, got ${actual_get}" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkThroughputSETAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_set
    actual_set="$(json_get "${bench_file}" throughput_set)"
    echo "[DIAG] SET throughput: ${actual_set} ops/sec (threshold: ${MINIMUM_THROUGHPUT_SET})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT_SET}" throughput_set)"
    assertTrue "SET throughput should be >= ${MINIMUM_THROUGHPUT_SET} ops/sec, got ${actual_set}" \
        "[ ${has_throughput} -eq 1 ]"
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
    assertTrue "Should have results for all micro operations" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkMicroLatencyP99BelowThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_P99_MS}" GET p99_latency_ms)"
    assertTrue "GET p99 latency should be <= ${MAXIMUM_LATENCY_P99_MS} ms" \
        "[ ${has_latency} -eq 1 ]"
}

testBenchmarkStressProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_stress.json"
    assertTrue "Stress benchmark JSON should exist" "[ -f '${bench_file}' ]"
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
    local content
    content="$(cat "${agg_file}")"
    assertContains "Should contain YCSB benchmark data" "${content}" "ycsb"
    assertContains "Should contain throughput benchmark data" "${content}" "throughput"
    assertContains "Should contain micro benchmark data" "${content}" "micro"
}

. "${SCRIPT_DIR}/shunit2"