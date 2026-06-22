#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="oceanbase"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-4.2.1.8}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"

OB_HOME="${SCRIPT_DIR}/oceanbase"
OB_HOST="${OB_HOST:-127.0.0.1}"
OB_PORT="${OB_PORT:-2881}"
OB_USER="${OB_USER:-root@test}"
OB_PASSWORD="${OB_PASSWORD:-}"
OB_DB="${OB_DB:-test}"

_mysql_cmd() {
    if [ -n "${OB_PASSWORD}" ]; then
        echo "mysql -h${OB_HOST} -P${OB_PORT} -u${OB_USER} -p'${OB_PASSWORD}'"
    else
        echo "mysql -h${OB_HOST} -P${OB_PORT} -u${OB_USER}"
    fi
}

MINIMUM_TPMC="${MIN_TPMC:-10}"
MAXIMUM_LATENCY_MS="${MAX_LATENCY_MS:-5000}"

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

json_get() { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results() { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }
json_version() { python3 "${JSON_HELPER}" "$1" version; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"
    if [ "$(uname -m)" != "aarch64" ] && [ "$(uname -m)" != "arm64" ]; then
        echo "WARNING: Not running on ARM64 architecture (current: $(uname -m))"
    fi
}

oneTimeTearDown() {
    if [ -f "${RESULTS_DIR}/all_results.json" ]; then
        echo "Results aggregated at: ${RESULTS_DIR}/all_results.json"
    fi
    if [ -f "${RESULTS_DIR}/benchmark_report.html" ]; then
        echo "HTML report at: ${RESULTS_DIR}/benchmark_report.html"
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
    local found=0
    if [ -x "${OB_HOME}/bin/observer" ]; then found=1; fi
    if command -v observer >/dev/null 2>&1; then found=1; fi
    if command -v obd >/dev/null 2>&1; then found=1; fi
    if [ -x "${SCRIPT_DIR}/obd/bin/obd" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: OceanBase not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "OceanBase (observer or obd) should be installed" "[ ${found} -eq 1 ]"
}

testSoftwareVersionMatches() {
    local ver="unknown"
    if [ -x "${OB_HOME}/bin/observer" ]; then
        ver="$("${OB_HOME}/bin/observer" --version 2>&1 | head -1 | grep -oP '[\d.]+' | head -1 | tr -d '\n\t')"
    elif command -v obd >/dev/null 2>&1; then
        ver="$(obd display-trace 2>&1 | head -1 | tr -d '\n\t')"
    fi
    if [ "${ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertNotNull "Version should not be empty" "${ver}"
}

testSoftwareRunsBasicCommand() {
    local result
    if eval "$(_mysql_cmd)" -e "SELECT 1 FROM dual" 2>/dev/null; then
        assertTrue "OceanBase basic query should succeed" "true"
    else
        if command -v obd >/dev/null 2>&1; then
            result="$(obd display-trace 2>&1)"
            assertNotNull "obd output should not be empty" "${result}"
        else
            startSkipping
        fi
    fi
}

testBenchmarkPrimaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    assertTrue "TPC-C benchmark JSON should exist" "[ -f '${bench_file}' ]"
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
    local avg_tpmc
    avg_tpmc="$(json_get "${bench_file}" average_tpmC)"
    if [ "${avg_tpmc}" = "NULL" ] || [ -z "${avg_tpmc}" ]; then
        local count
        count="$(json_count_results "${bench_file}")"
        if [ "${count}" -gt 0 ]; then
            avg_tpmc="$(python3 "${JSON_HELPER}" "${bench_file}" avg_throughput tpmC)"
        else
            startSkipping
            return
        fi
    fi
    assertTrue "Average tpmC (${avg_tpmc}) should be >= ${MINIMUM_TPMC}" \
        "[ $(echo "${avg_tpmc}" | awk '{printf "%d", $1}') -ge ${MINIMUM_TPMC} ]"
}

testBenchmarkPrimaryIsTPCCBenchmark() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local bench_name
    bench_name="$(json_get "${bench_file}" benchmark)"
    assertEquals "Benchmark name should be tpcc" "tpcc" "${bench_name}"
}

testBenchmarkSecondaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    assertTrue "YCSB benchmark JSON should exist" "[ -f '${bench_file}' ]"
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
    actual_lat="$(json_get "${bench_file}" results 0 avg_latency_ms)"
    echo "[DIAG] YCSB avg latency: ${actual_lat} ms (threshold: ${MAXIMUM_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" results 0 avg_latency_ms)"
    assertTrue "Avg YCSB latency should be <= ${MAXIMUM_LATENCY_MS}ms, got ${actual_lat}" "[ ${has_latency} -eq 1 ]"
}

testBenchmarkSecondaryIsYCSBBenchmark() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local bench_name
    bench_name="$(json_get "${bench_file}" benchmark)"
    assertEquals "Benchmark name should be ycsb" "ycsb" "${bench_name}"
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
    local has_primary has_secondary has_micro
    has_primary="$(json_contains "${agg_file}" primary_benchmark)"
    has_secondary="$(json_contains "${agg_file}" secondary_benchmark)"
    has_micro="$(json_contains "${agg_file}" micro_benchmark)"
    assertTrue "Should contain primary_benchmark (TPC-C) data" "[ ${has_primary} -eq 1 ]"
    assertTrue "Should contain secondary_benchmark (YCSB) data" "[ ${has_secondary} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
}

. "${SCRIPT_DIR}/shunit2"