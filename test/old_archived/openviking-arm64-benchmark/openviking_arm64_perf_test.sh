#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="openviking"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-v0.3.24}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

MINIMUM_ACCURACY_LOCOMO=80
MAXIMUM_LATENCY_MS=500
MINIMUM_ACCURACY_HOTPOTQA=72
MINIMUM_EMBEDDING_THROUGHPUT=50
MINIMUM_RETRIEVAL_QPS=10

json_get() { python3 "${JSON_HELPER}" "$1" get "$2"; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "$3" "$4"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "$2" "$3" "$4"; }
json_count_results() { python3 "${JSON_HELPER}" "$1" count_results; }
json_version() { python3 "${JSON_HELPER}" "$1" version; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }

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
    assertTrue "openviking Python package should be importable" \
        "python3 -c 'import openviking' 2>/dev/null"
}

testSoftwareVersionMatches() {
    local ver
    ver="$(python3 -c 'import openviking; print(openviking.__version__)' 2>/dev/null | tr -d '\n\t')"
    assertNotNull "Version should not be empty" "${ver}"
}

testPythonVersionSufficient() {
    local py_ver
    py_ver="$(python3 -c 'import sys; v=sys.version_info; print(f"{v.major}.{v.minor}")' 2>/dev/null | tr -d '\n\t')"
    assertNotNull "Python version should be available" "${py_ver}"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" \
        "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkPrimaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    assertTrue "LoCoMo benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkPrimaryHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    assertTrue "Should have benchmark field" \
        "[ $(json_field_exists "${bench_file}" benchmark) -eq 1 ]"
    assertTrue "Should have performance_metrics field" \
        "[ $(json_field_exists "${bench_file}" performance_metrics) -eq 1 ]"
    assertTrue "Should have results field" \
        "[ $(json_field_exists "${bench_file}" results) -eq 1 ]"
}

testBenchmarkPrimaryAccuracyAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local accuracy
    accuracy="$(json_get "${bench_file}" results 0 accuracy_pct)"
    if [ -z "${accuracy}" ] || [ "${accuracy}" = "None" ]; then
        startSkipping
        return
    fi
    assertTrue "LoCoMo accuracy (${accuracy}%) should be >= ${MINIMUM_ACCURACY_LOCOMO}%" \
        "[ ${accuracy} -ge ${MINIMUM_ACCURACY_LOCOMO} ]"
}

testBenchmarkPrimaryLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local latency_ms
    latency_ms="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" avg_query_time_ms results)"
    assertTrue "LoCoMo avg latency should be <= ${MAXIMUM_LATENCY_MS}ms" \
        "[ ${latency_ms} -eq 1 ]"
}

testBenchmarkSecondaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_hotpotqa.json"
    assertTrue "HotpotQA benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkSecondaryHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_hotpotqa.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    assertTrue "Should have benchmark field" \
        "[ $(json_field_exists "${bench_file}" benchmark) -eq 1 ]"
    assertTrue "Should have results field" \
        "[ $(json_field_exists "${bench_file}" results) -eq 1 ]"
}

testBenchmarkSecondaryAccuracyAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_hotpotqa.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local accuracy
    accuracy="$(json_get "${bench_file}" results 0 accuracy_pct)"
    if [ -z "${accuracy}" ] || [ "${accuracy}" = "None" ]; then
        startSkipping
        return
    fi
    assertTrue "HotpotQA accuracy (${accuracy}%) should be >= ${MINIMUM_ACCURACY_HOTPOTQA}%" \
        "[ ${accuracy} -ge ${MINIMUM_ACCURACY_HOTPOTQA} ]"
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
    assertTrue "Should have results for all micro operations" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkMicroEmbeddingThroughput() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local throughput
    throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_EMBEDDING_THROUGHPUT}" embeddings_per_sec results)"
    assertTrue "Embedding throughput should be >= ${MINIMUM_EMBEDDING_THROUGHPUT}/sec" \
        "[ ${throughput} -eq 1 ]"
}

testBenchmarkStressProducesResults() {
    local bench_file="${RESULTS_DIR}/stress_benchmark.json"
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
    if [ ! -f "${agg_file}" ]; then
        startSkipping
        return
    fi
    assertTrue "Should contain locomo benchmark data" \
        "[ $(json_contains "${agg_file}" locomo) -eq 1 ]"
    assertTrue "Should contain hotpotqa benchmark data" \
        "[ $(json_contains "${agg_file}" hotpotqa) -eq 1 ]"
    assertTrue "Should contain micro benchmark data" \
        "[ $(json_contains "${agg_file}" micro) -eq 1 ]"
}

. "${SCRIPT_DIR}/shunit2"