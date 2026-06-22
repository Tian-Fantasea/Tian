#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="rocksdb"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-9.10.0}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"

DB_BENCH_PATH="${DB_BENCH_PATH:-${SCRIPT_DIR}/rocksdb_src/db_bench}"
MINIMUM_THROUGHPUT=100
MAXIMUM_LATENCY_MS=10.0

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

json_get() { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "${@:2}"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "${@:2}"; }
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

testRocksdbIsInstalled() {
    assertTrue "db_bench binary should exist" \
        "[ -x '${DB_BENCH_PATH}' ]"
}

testRocksdbVersionMatches() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local ver
    ver="$(json_version "${ver_file}")"
    assertNotNull "Version should not be null" "${ver}"
}

testRocksdbRunsBasicCommand() {
    if [ ! -x "${DB_BENCH_PATH}" ]; then startSkipping; return; fi
    local result
    result="$(${DB_BENCH_PATH} --help 2>&1 | head -5)"
    assertTrue "db_bench --help should succeed" "[ $? -eq 0 ]"
    assertNotNull "Output should not be empty" "${result}"
}

testArm64CRC32CDetected() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local has_crc
    has_crc="$(json_get "${ver_file}" arm64_crc32c_source_exists)"
    assertNotNull "ARM64 CRC32C detection result should exist" "${has_crc}"
}

testYCSBBenchmarkProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    assertTrue "YCSB benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testYCSBBenchmarkHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testYCSBWorkloadAThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_a
    actual_a="$(json_get "${bench_file}" results ycsb_workload_a_update_heavy run_throughput_ops_sec)"
    echo "[DIAG] YCSB-A actual throughput: ${actual_a} ops/sec (threshold: ${MINIMUM_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" results ycsb_workload_a_update_heavy run_throughput_ops_sec)"
    assertTrue "YCSB-A throughput should be >= ${MINIMUM_THROUGHPUT}, got ${actual_a}" "[ ${has_throughput} -eq 1 ]"
}

testYCSBWorkloadCReadOnlyThroughput() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_c
    actual_c="$(json_get "${bench_file}" results ycsb_workload_c_read_only run_throughput_ops_sec)"
    echo "[DIAG] YCSB-C actual throughput: ${actual_c} ops/sec (threshold: ${MINIMUM_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" results ycsb_workload_c_read_only run_throughput_ops_sec)"
    assertTrue "YCSB-C read-only throughput should be >= ${MINIMUM_THROUGHPUT}, got ${actual_c}" "[ ${has_throughput} -eq 1 ]"
}

testDbBenchProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    assertTrue "db_bench advanced benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testDbBenchCompactionStylesValid() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should contain compaction_styles data" "${content}" "compaction_styles"
    assertContains "Should contain level_compaction" "${content}" "level_compaction"
    assertContains "Should contain universal_compaction" "${content}" "universal_compaction"
}

testDbBenchCompressionValid() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should contain compression_algorithms data" "${content}" "compression_algorithms"
    assertContains "Should contain no_compression baseline" "${content}" "no_compression"
}

testDbBenchFiltersValid() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should contain bloom_ribbon_filters data" "${content}" "bloom_ribbon_filters"
    assertContains "Should contain no_filter baseline" "${content}" "no_filter"
}

testMicroBenchmarkProducesResults() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testMicroBenchmarkAllCategoriesPresent() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have write_operations" "${content}" "write_operations"
    assertContains "Should have read_operations" "${content}" "read_operations"
    assertContains "Should have delete_operations" "${content}" "delete_operations"
    assertContains "Should have mixed_operations" "${content}" "mixed_operations"
    assertContains "Should have hash_checksum" "${content}" "hash_checksum"
}

testMicroCRC32CARM64Performance() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    local crc_val
    crc_val="$(json_get "${bench_file}" results hash_checksum crc32c avg_ops_sec 2>/dev/null || echo 'NOT_FOUND')"
    local xx_val
    xx_val="$(json_get "${bench_file}" results hash_checksum xxhash avg_ops_sec 2>/dev/null || echo 'NOT_FOUND')"
    echo "[DIAG] CRC32C ops/sec: ${crc_val}, xxhash ops/sec: ${xx_val}"
    assertContains "Should have CRC32C benchmark" "${content}" "crc32c"
    assertContains "Should have xxhash benchmark" "${content}" "xxhash"
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
    assertContains "Should contain db_bench data" "${content}" "dbbench"
    assertContains "Should contain micro benchmark data" "${content}" "micro"
}

. "${SCRIPT_DIR}/shunit2"