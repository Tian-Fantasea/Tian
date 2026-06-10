#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="flink"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-2.2.1}"
FLINK_HOME="${SCRIPT_DIR}/flink"
SHUNIT_PARENT="${SCRIPT_DIR}/flink_arm64_perf_test.sh"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

MIN_THROUGHPUT_RECORDS=10
MAX_LATENCY_MS=5000

json_get() {
    python3 "${JSON_HELPER}" "$1" get "$2"
}

json_field_exists() {
    python3 "${JSON_HELPER}" "$1" field_exists "$2"
}

json_count_results() {
    python3 "${JSON_HELPER}" "$1" count_results
}

json_throughput_ge() {
    python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "$3" "$4"
}

json_latency_le() {
    python3 "${JSON_HELPER}" "$1" latency_le "$2" "$3" "$4"
}

json_version() {
    python3 "${JSON_HELPER}" "$1" version
}

json_contains() {
    python3 "${JSON_HELPER}" "$1" contains "$2"
}

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
    arch="$(uname -m)"
    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \
        "[ '${arch}' = 'aarch64' ] || [ '${arch}' = 'arm64' ]"
}

testFlinkIsInstalled() {
    assertTrue "Flink home directory should exist" \
        "[ -d '${FLINK_HOME}' ]"
}

testFlinkBinaryExists() {
    assertTrue "Flink CLI binary should exist" \
        "[ -x '${FLINK_HOME}/bin/flink' ]"
}

testJavaIsInstalled() {
    local java_ver
    java_ver="$(java -version 2>&1 | head -1)"
    assertNotNull "Java version should not be empty" "${java_ver}"
}

testFlinkVersionMatches() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then
        startSkipping
        return
    fi
    local ver
    ver="$(json_version "${ver_file}")"
    assertEquals "Flink version should match" "${SOFTWARE_VERSION}" "${ver}"
}

testFlinkStartsCluster() {
    "${FLINK_HOME}/bin/start-cluster.sh"
    sleep 10
    local pid_count
    pid_count="$(ps aux | grep -c '[f]link' || echo 0)"
    assertTrue "Flink processes should be running (count: ${pid_count})" \
        "[ ${pid_count} -ge 2 ]"
    "${FLINK_HOME}/bin/stop-cluster.sh"
    sleep 5
}

testFlinkWordCountSucceeds() {
    "${FLINK_HOME}/bin/start-cluster.sh"
    sleep 10
    "${FLINK_HOME}/bin/flink" run "${FLINK_HOME}/examples/streaming/WordCount.jar" >/dev/null 2>&1
    local rc=$?
    assertTrue "WordCount job should succeed (exit code: ${rc})" "[ ${rc} -eq 0 ]"
    "${FLINK_HOME}/bin/stop-cluster.sh"
    sleep 5
}

testVersionInfoJSONExists() {
    assertTrue "version_info.json should exist" \
        "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasRequiredFields() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${ver_file}")"
    assertContains "Should have architecture field" "${content}" "architecture"
    assertContains "Should have software field" "${content}" "software"
    assertContains "Should have cpu_cores field" "${content}" "cpu_cores"
    assertContains "Should have memory_mb field" "${content}" "memory_mb"
}

testBenchmarkTpcdsProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_tpcds.json"
    assertTrue "TPC-DS benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkTpcdsHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_tpcds.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have reference field" "${content}" "reference"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testBenchmarkTpcdsThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_tpcds.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MIN_THROUGHPUT_RECORDS}" avg_records_per_sec records_per_sec throughput)"
    assertTrue "TPC-DS throughput should be >= ${MIN_THROUGHPUT_RECORDS} records/sec" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkStreamingProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_streaming.json"
    assertTrue "Streaming benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkStreamingLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_streaming.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local latency_ok
    latency_ok="$(json_latency_le "${bench_file}" "${MAX_LATENCY_MS}" avg_latency_ms latency_ms)"
    assertTrue "Streaming avg latency should be <= ${MAX_LATENCY_MS}ms" \
        "[ ${latency_ok} -eq 1 ]"
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
    assertTrue "Should have results for all micro operations (count: ${ops_count})" \
        "[ ${ops_count} -gt 0 ]"
}

testBenchmarkStateProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_state.json"
    assertTrue "State backend benchmark JSON should exist" "[ -f '${bench_file}' ]"
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
    if [ ! -f "${agg_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${agg_file}")"
    assertContains "Should contain tpcds data" "${content}" "tpcds"
    assertContains "Should contain streaming data" "${content}" "streaming"
    assertContains "Should contain micro data" "${content}" "micro"
    assertContains "Should contain state data" "${content}" "state"
}

. "${SCRIPT_DIR}/shunit2"