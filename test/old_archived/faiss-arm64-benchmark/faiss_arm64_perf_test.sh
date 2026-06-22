#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="faiss"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-1.14.2}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

MIN_QPS_FLAT=100
MAX_LATENCY_SINGLE_US=5000
MIN_RECALL_FLAT=0.99

json_get() {
    python3 "${JSON_HELPER}" "$1" get "$2" "$3" "$4"
}

json_field_exists() {
    python3 "${JSON_HELPER}" "$1" field_exists "$2"
}

json_count_results() {
    python3 "${JSON_HELPER}" "$1" count_results
}

json_throughput_ge() {
    python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "$3" "$4" "$5"
}

json_latency_le() {
    python3 "${JSON_HELPER}" "$1" latency_le "$2" "$3" "$4" "$5"
}

json_version() {
    python3 "${JSON_HELPER}" "$1" version
}

json_contains() {
    python3 "${JSON_HELPER}" "$1" contains "$2"
}

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

testFaissPythonModuleInstalled() {
    local result
    result="$(python3 -c "import faiss" 2>&1)"
    assertTrue "Faiss Python module should be importable" "[ $? -eq 0 ]"
}

testFaissVersionMatches() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then
        startSkipping
        return
    fi
    local ver
    ver="$(json_version "${ver_file}")"
    assertEquals "Faiss version should match" "${SOFTWARE_VERSION}" "${ver}"
}

testFaissBasicIndexSearchWorks() {
    local result
    result="$(python3 "${SCRIPT_DIR}/scripts/verify_python.py" \
        --results-dir "${RESULTS_DIR}" \
        --faiss-version "${SOFTWARE_VERSION}" \
        --sanity-check 2>&1)"
    assertTrue "Faiss sanity check (IndexFlatL2 search) should pass" "[ $? -eq 0 ]"
    assertContains "Sanity check output should confirm pass" "${result}" "Sanity check passed"
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

testBenchmarkAnnProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_ann.json"
    assertTrue "ANN benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkAnnHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_ann.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have reference field" "${content}" "reference"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results_summary field" "${content}" "results_summary"
}

testBenchmarkAnnFlatL2QpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ann.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local flat_qps
    flat_qps="$(json_get "${bench_file}" results_summary FlatL2 qps)"
    if [ -z "${flat_qps}" ] || [ "${flat_qps}" = "" ]; then
        startSkipping
        return
    fi
    assertTrue "FlatL2 QPS (${flat_qps}) should be >= ${MIN_QPS_FLAT}" \
        "[ $(echo "${flat_qps} >= ${MIN_QPS_FLAT}" | bc -l) -eq 1 ]"
}

testBenchmarkAnnFlatL2RecallAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ann.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local recall_key="recall_at_10"
    local flat_recall
    flat_recall="$(json_get "${bench_file}" results_summary FlatL2 "${recall_key}")"
    if [ -z "${flat_recall}" ] || [ "${flat_recall}" = "" ]; then
        startSkipping
        return
    fi
    assertTrue "FlatL2 Recall@10 (${flat_recall}) should be >= ${MIN_RECALL_FLAT}" \
        "[ $(echo "${flat_recall} >= ${MIN_RECALL_FLAT}" | bc -l) -eq 1 ]"
}

testBenchmarkAnnAllIndexesCompleted() {
    local bench_file="${RESULTS_DIR}/benchmark_ann.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have FlatL2 results" "${content}" "FlatL2"
    assertContains "Should have IVFFlat results" "${content}" "IVFFlat"
    assertContains "Should have HNSWFlat results" "${content}" "HNSWFlat"
}

testBenchmarkMicroProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_micro.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkMicroHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_micro.json"
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

testBenchmarkMicroAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/benchmark_micro.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have kmeans_clustering results" "${content}" "kmeans_clustering"
    assertContains "Should have add_vectors_flat results" "${content}" "add_vectors_flat"
    assertContains "Should have search_single_flat results" "${content}" "search_single_flat"
    assertContains "Should have search_batch_flat results" "${content}" "search_batch_flat"
    assertContains "Should have range_search_flat results" "${content}" "range_search_flat"
    assertContains "Should have pq_encoding results" "${content}" "pq_encoding"
}

testBenchmarkMicroSearchLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_micro.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local latency
    latency="$(json_get "${bench_file}" results search_single_flat avg_latency_us)"
    if [ -z "${latency}" ] || [ "${latency}" = "" ]; then
        startSkipping
        return
    fi
    assertTrue "Single search latency (${latency}us) should be <= ${MAX_LATENCY_SINGLE_US}us" \
        "[ $(echo "${latency} <= ${MAX_LATENCY_SINGLE_US}" | bc -l) -eq 1 ]"
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
    assertContains "Should contain version_info data" "${content}" "version_info"
    assertContains "Should contain ann benchmark data" "${content}" "ann"
    assertContains "Should contain micro benchmark data" "${content}" "micro"
}

. "${SCRIPT_DIR}/shunit2"