#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"
RESULTS_JSON="${RESULTS_DIR}/results.json"
KITEX_VERSION="${KITEX_VERSION:-v0.16.2}"
HERTZ_VERSION="${HERTZ_VERSION:-v0.10.4}"
ITERATIONS="${ITERATIONS:-1}"
DATA_SCALE="${DATA_SCALE:-1}"
BENCH_DIR="${SCRIPT_DIR}/bench"
KITEX_BENCH_DIR="${BENCH_DIR}/kitex-benchmark"
HERTZ_BENCH_DIR="${BENCH_DIR}/hertz-benchmark"
SHUNIT_PARENT="${SCRIPT_DIR}/cloudwego_test.sh"

MINIMUM_KITEX_QPS=50000
MINIMUM_HERTZ_QPS=30000

download_shunit2() {
    if [ -f "${SCRIPT_DIR}/shunit2" ]; then
        return 0
    fi
    local mirrors=(
        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
        "https://raw.githubusercontent.com/kward/shunit2/refs/heads/master/shunit2"
    )
    for mirror_url in "${mirrors[@]}"; do
        curl --connect-timeout 30 --max-time 60 -sL "${mirror_url}" -o "${SCRIPT_DIR}/shunit2" 2>/dev/null && {
            if [ -s "${SCRIPT_DIR}/shunit2" ]; then
                chmod +x "${SCRIPT_DIR}/shunit2"
                echo "[SETUP] shUnit2 downloaded from ${mirror_url}"
                return 0
            fi
        }
        rm -f "${SCRIPT_DIR}/shunit2"
    done
    for mirror_url in "${mirrors[@]}"; do
        wget --timeout=30 --tries=2 -q -O "${SCRIPT_DIR}/shunit2" "${mirror_url}" 2>/dev/null && {
            if [ -s "${SCRIPT_DIR}/shunit2" ]; then
                chmod +x "${SCRIPT_DIR}/shunit2"
                echo "[SETUP] shUnit2 downloaded from ${mirror_url}"
                return 0
            fi
        }
        rm -f "${SCRIPT_DIR}/shunit2"
    done
    echo "[ERROR] Failed to download shUnit2 from all mirrors"
    return 1
}

json_get() { python3 "${JSON_HELPER}" "$1" get "$2" "$3"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"
    download_shunit2 || true
}

check_prerequisites() {
    if ! command -v go &>/dev/null; then
        echo "[SKIP] Go not installed"
        startSkipping
        return
    fi
}

collect_version_info() {
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ | tr -d '\n\t')"
    local arch
    arch="$(uname -m | tr -d '\n\t')"
    local kernel
    kernel="$(uname -r | tr -d '\n\t')"
    local os
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    local cpu_model
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || grep 'Model Name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    local cores
    cores="$(nproc 2>/dev/null || echo 0)"
    local mem_mb
    mem_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"
    local go_ver
    go_ver="$(go version 2>&1 | awk '{print $3}' | sed 's/go//' | tr -d '\n\t' || echo 'unknown')"
    local wrk_ver
    wrk_ver="$(wrk --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'not_installed')"
    local taskset_avail
    taskset_avail="$(command -v taskset &>/dev/null && echo 'yes' || echo 'no')"

    python3 "${JSON_HELPER}" "${RESULTS_JSON}" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${KITEX_VERSION}" "${HERTZ_VERSION}" \
        "${go_ver}" "${wrk_ver}" "${taskset_avail}"
}

run_benchmarks() {
    echo "[BENCH] Running Kitex RPC benchmark (Phase 3a)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_kitex_rpc.py" \
        --results-json "${RESULTS_JSON}" \
        --section kitex_benchmark \
        --kitex-bench-dir "${KITEX_BENCH_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}"

    echo "[BENCH] Running Hertz HTTP benchmark (Phase 3b)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_hertz_http.py" \
        --results-json "${RESULTS_JSON}" \
        --section hertz_benchmark \
        --hertz-bench-dir "${HERTZ_BENCH_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}"

    echo "[BENCH] Running micro benchmark (Phase 3c)..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-json "${RESULTS_JSON}" \
        --section micro_benchmark \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}"

    echo "[BENCH] Running stress benchmark (Phase 3d)..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-json "${RESULTS_JSON}" \
        --section stress_benchmark \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}" \
        --stress-only
}

oneTimeTearDown() {
    if [ -f "${RESULTS_JSON}" ]; then
        echo "[REPORT] Generating text summary..."
        python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
            --input "${RESULTS_JSON}" \
            --output "${RESULTS_DIR}/results.txt"

        echo "[REPORT] Generating HTML report..."
        python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
            --input "${RESULTS_JSON}" \
            --output "${RESULTS_DIR}/results.html"
    fi
}

setUp() { :; }
tearDown() { :; }

testArchitectureIsARM64() {
    check_prerequisites
    local arch
    arch="$(uname -m)"
    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \
        "[ '${arch}' = 'aarch64' ] || [ '${arch}' = 'arm64' ]"
}

testGoIsInstalled() {
    check_prerequisites
    assertTrue "Go should be installed" \
        "command -v go >/dev/null 2>&1"
}

testGoVersionIsAcceptable() {
    check_prerequisites
    local go_ver
    go_ver="$(go version 2>&1 | awk '{print $3}' | sed 's/go//')"
    assertNotNull "Go version should not be empty" "${go_ver}"
}

testWrkIsInstalled() {
    check_prerequisites
    if ! command -v wrk &>/dev/null; then
        echo "[SKIP] wrk not installed (Hertz benchmarks limited)"
        startSkipping
        return
    fi
    assertTrue "wrk should be available" "command -v wrk >/dev/null 2>&1"
}

testKitexBenchRepoExists() {
    check_prerequisites
    assertTrue "kitex-benchmark repo should exist" \
        "[ -d '${KITEX_BENCH_DIR}' ]"
}

testHertzBenchRepoExists() {
    check_prerequisites
    assertTrue "hertz-benchmark repo should exist" \
        "[ -d '${HERTZ_BENCH_DIR}' ]"
}

testResultsJsonExists() {
    collect_version_info
    assertTrue "results.json should exist" "[ -f '${RESULTS_JSON}' ]"
}

testResultsJsonHasVersionInfo() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" version_info)"
    assertTrue "results.json should have version_info section" "[ '${has}' = '1' ]"
}

testResultsJsonHasArchitecture() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local arch
    arch="$(json_get "${RESULTS_JSON}" architecture)"
    assertNotNull "Architecture should be set in results.json" "${arch}"
}

testResultsJsonHasSoftwareVersion() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local ver
    ver="$(json_get "${RESULTS_JSON}" version)"
    assertNotNull "Software version should be set in results.json" "${ver}"
}

testBenchmarkKitexInResultsJson() {
    run_benchmarks
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" kitex_benchmark)"
    assertTrue "results.json should have kitex_benchmark section" "[ '${has}' = '1' ]"
}

testBenchmarkKitexHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" kitex_benchmark)"
    assertTrue "Should contain kitex_benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" benchmark)"
    assertTrue "Should contain benchmark field" "[ '${content}' = '1' ]"
}

testBenchmarkHertzInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" hertz_benchmark)"
    assertTrue "results.json should have hertz_benchmark section" "[ '${has}' = '1' ]"
}

testBenchmarkMicroInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "results.json should have micro_benchmark section" "[ '${has}' = '1' ]"
}

testResultsJsonContainsAllBenchmarks() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" kitex_benchmark)"
    assertTrue "Should contain kitex_benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" hertz_benchmark)"
    assertTrue "Should contain hertz_benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "Should contain micro_benchmark" "[ '${content}' = '1' ]"
}

testHtmlReportGenerated() {
    assertTrue "HTML report should exist" "[ -f '${RESULTS_DIR}/results.html' ]"
}

testSummaryReportGenerated() {
    assertTrue "Summary report should exist" "[ -f '${RESULTS_DIR}/results.txt' ]"
}

testLogFileGenerated() {
    assertTrue "Log file should exist" "[ -f '${RESULTS_DIR}/results.log' ]"
}

. "${SCRIPT_DIR}/shunit2"
