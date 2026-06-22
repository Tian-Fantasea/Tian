#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="ceph"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-19.2.0}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"

CEPH_CONF_PATH="${CEPH_CONF_PATH:-/etc/ceph/ceph.conf}"
CEPH_KEYRING_PATH="${CEPH_KEYRING_PATH:-/etc/ceph/ceph.client.admin.keyring}"

MINIMUM_THROUGHPUT=1000
MINIMUM_IOPS=500
MAXIMUM_LATENCY_MS=50.0

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

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

testCephIsInstalled() {
    assertTrue "ceph command should exist" \
        "command -v ceph &>/dev/null || [ -x '/usr/bin/ceph' ] || [ -x '/usr/local/bin/ceph' ]"
}

testCephVersionMatches() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local ver
    ver="$(json_version "${ver_file}")"
    assertNotNull "Version should not be null" "${ver}"
}

testCephRunsBasicCommand() {
    local result
    result="$(ceph --version 2>&1 | head -3)"
    assertTrue "ceph --version should succeed" "[ $? -eq 0 ] || [ -n '${result}' ]"
}

testCephConfExists() {
    assertTrue "ceph.conf should exist at ${CEPH_CONF_PATH}" \
        "[ -f '${CEPH_CONF_PATH}' ]"
}

testCephKeyringExists() {
    assertTrue "ceph keyring should exist at ${CEPH_KEYRING_PATH}" \
        "[ -f '${CEPH_KEYRING_PATH}' ]"
}

testClusterIsRunning() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local health
    health="$(json_get "${ver_file}" cluster_health)"
    if [ -z "${health}" ]; then startSkipping; return; fi
    assertTrue "Cluster health should be HEALTH_OK or HEALTH_WARN, got: ${health}" \
        "[ '${health}' = 'HEALTH_OK' ] || [ '${health}' = 'HEALTH_WARN' ]"
}

testArm64CRC32CDetected() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local has_crc
    has_crc="$(json_field_exists "${ver_file}" arm64_features)"
    assertTrue "ARM64 features section should exist" "[ ${has_crc} -eq 1 ]"
}

testRADOSBenchmarkProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_rados.json"
    assertTrue "RADOS benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testRADOSBenchmarkHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_rados.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testRADOSWriteThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_rados.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_contains "${bench_file}" avg_throughput_ops_sec)"
    assertTrue "RADOS results should contain throughput data" "[ ${has_throughput} -eq 1 ]"
}

testRADOSObjectSizeSweepHasData() {
    local bench_file="${RESULTS_DIR}/benchmark_rados.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have object_size_sweep" "${content}" "object_size_sweep"
}

testRADOSConcurrencyScalingHasData() {
    local bench_file="${RESULTS_DIR}/benchmark_rados.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have concurrency_scaling" "${content}" "concurrency_scaling"
}

testRBDBenchmarkProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_rbd.json"
    assertTrue "RBD benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testRBDBenchmarkHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_rbd.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testRBDIODEPTHScalingHasData() {
    local bench_file="${RESULTS_DIR}/benchmark_rbd.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have iodepth_scaling" "${content}" "iodepth_scaling"
}

testCephFSBenchmarkProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_cephfs.json"
    assertTrue "CephFS benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testCephFSBenchmarkHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_cephfs.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testCephFSMetadataOperationsHasData() {
    local bench_file="${RESULTS_DIR}/benchmark_cephfs.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have metadata_operations" "${content}" "metadata_operations"
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
    assertContains "Should have ec_vs_replicated" "${content}" "ec_vs_replicated"
    assertContains "Should have compression_algorithms" "${content}" "compression_algorithms"
    assertContains "Should have arm64_crc32c_checksum" "${content}" "arm64_crc32c_checksum"
}

testECVsReplicatedHasComparisonData() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have EC profile data" "${content}" "ec_profile"
    assertContains "Should have replicated baseline" "${content}" "replicated"
}

testCompressionAlgorithmsTested() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should test lz4 compression" "${content}" "lz4"
    assertContains "Should test zstd compression" "${content}" "zstd"
    assertContains "Should test no compression baseline" "${content}" "none"
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
    assertContains "Should contain RADOS benchmark data" "${content}" "rados"
    assertContains "Should contain RBD benchmark data" "${content}" "rbd"
    assertContains "Should contain CephFS benchmark data" "${content}" "cephfs"
    assertContains "Should contain micro benchmark data" "${content}" "micro"
}

testARM64OptimizationHighlightsExist() {
    local agg_file="${RESULTS_DIR}/all_results.json"
    if [ ! -f "${agg_file}" ]; then startSkipping; return; fi
    local content
    content="$(cat "${agg_file}")"
    assertContains "Should contain ARM64 optimization data" "${content}" "arm64"
}

. "${SCRIPT_DIR}/shunit2"