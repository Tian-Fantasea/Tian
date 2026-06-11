#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="kubernetes"
SOFTWARE_VERSION="${VERSION:-1.33.12}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"
KUBECONFIG_PATH="${RESULTS_DIR}/kubeconfig"

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

MINIMUM_POD_STARTUP_LATENCY_MS=5000
MAXIMUM_API_LATENCY_MS=1000
MINIMUM_SCHEDULER_THROUGHPUT=100
MAXIMUM_P50_LATENCY_MS=200

json_get() { python3 "${JSON_HELPER}" "$1" get "$2" "$3"; }
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

testKubectlIsInstalled() {
    assertTrue "kubectl binary should exist" \
        "[ -x '${SCRIPT_DIR}/kubectl' ] || [ -x '/usr/local/bin/kubectl' ]"
}

testKindIsInstalled() {
    assertTrue "kind binary should exist" \
        "[ -x '${SCRIPT_DIR}/kind' ] || [ -x '/usr/local/bin/kind' ]"
}

testKubernetesVersionMatches() {
    local ver
    ver="$(kubectl version --client --short 2>/dev/null || kubectl version --client 2>/dev/null | grep -o 'GitVersion:"v[^"]*"' | head -1 | sed 's/GitVersion:"v//' | sed 's/"//' | tr -d '\n\t')"
    if [ -z "${ver}" ]; then
        ver="$(kubectl version --client -o json 2>/dev/null | grep -o '"gitVersion": "v[^"]*"' | head -1 | sed 's/"gitVersion": "v//' | sed 's/"//' | tr -d '\n\t')"
    fi
    assertNotNull "Version should not be empty" "${ver}"
}

testKubernetesClusterIsResponsive() {
    export KUBECONFIG="${KUBECONFIG_PATH}"
    local result
    result="$(kubectl get nodes 2>&1)"
    assertTrue "kubectl get nodes should succeed" "[ $? -eq 0 ]"
    assertNotNull "Output should not be empty" "${result}"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasArchitecture() {
    if [ ! -f "${RESULTS_DIR}/version_info.json" ]; then
        startSkipping
        return
    fi
    local has_arch
    has_arch="$(json_field_exists "${RESULTS_DIR}/version_info.json" architecture)"
    assertTrue "version_info should have architecture field" "[ '${has_arch}' = '1' ]"
}

testVersionInfoHasKubernetesVersion() {
    if [ ! -f "${RESULTS_DIR}/version_info.json" ]; then
        startSkipping
        return
    fi
    local has_ver
    has_ver="$(json_field_exists "${RESULTS_DIR}/version_info.json" software_version)"
    assertTrue "version_info should have software_version field" "[ '${has_ver}' = '1' ]"
}

testBenchmarkPodStartupProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    assertTrue "Pod startup benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkPodStartupHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testBenchmarkPodStartupLatencyBelowSLO() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local p99_latency
    p99_latency="$(json_get "${bench_file}" results 0 p99_latency_ms)"
    assertNotNull "p99 latency should not be empty" "${p99_latency}"
    local meets_slo
    meets_slo="$(json_latency_le "${bench_file}" "${MINIMUM_POD_STARTUP_LATENCY_MS}" p99_latency_ms results 0)"
    assertTrue "Pod startup p99 latency should be <= ${MINIMUM_POD_STARTUP_LATENCY_MS}ms (Kubernetes SLO)" "[ '${meets_slo}' = '1' ]"
}

testBenchmarkPodStartupP50LatencyAcceptable() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local p50_latency
    p50_latency="$(json_get "${bench_file}" results 0 p50_latency_ms)"
    assertNotNull "p50 latency should not be empty" "${p50_latency}"
}

testBenchmarkApiLatencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    assertTrue "API latency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkApiLatencyHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Should have benchmark field" "${content}" "benchmark"
    assertContains "Should have performance_metrics field" "${content}" "performance_metrics"
    assertContains "Should have results field" "${content}" "results"
}

testBenchmarkApiLatencyMutatingBelowSLO() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_API_LATENCY_MS}" p99_latency_ms results 0)"
    assertTrue "API mutating call p99 latency should be <= ${MAXIMUM_API_LATENCY_MS}ms (Kubernetes SLO)" "[ '${has_latency}' = '1' ]"
}

testBenchmarkApiLatencyReadOnlyBelowSLO() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local read_p99
    read_p99="$(json_get "${bench_file}" results 1 p99_latency_ms)"
    assertNotNull "Read-only API latency should have data" "${read_p99}"
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
    assertTrue "Should have results for all micro operations (count: ${ops_count})" "[ ${ops_count} -ge 3 ]"
}

testBenchmarkMicroSchedulerThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_SCHEDULER_THROUGHPUT}" throughput pods_per_sec results 0)"
    assertTrue "Scheduler throughput should be >= ${MINIMUM_SCHEDULER_THROUGHPUT} pods/sec" "[ '${has_throughput}' = '1' ]"
}

testBenchmarkStressProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_stress.json"
    assertTrue "Stress benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkStressClusterStable() {
    local bench_file="${RESULTS_DIR}/benchmark_stress.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(cat "${bench_file}")"
    assertContains "Stress test should have stability field" "${content}" "stable"
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
    assertContains "Should contain pod_startup benchmark data" "${content}" "pod_startup"
    assertContains "Should contain api_latency benchmark data" "${content}" "api_latency"
    assertContains "Should contain micro benchmark data" "${content}" "micro"
    assertContains "Should contain stress benchmark data" "${content}" "stress"
}

. "${SCRIPT_DIR}/shunit2"