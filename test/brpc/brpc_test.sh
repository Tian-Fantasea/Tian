#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"
RESULTS_JSON="${RESULTS_DIR}/results.json"
BRPC_VERSION="${BRPC_VERSION:-1.6.0}"
ITERATIONS="${ITERATIONS:-1}"
SHUNIT_PARENT="${SCRIPT_DIR}/brpc_test.sh"

MIN_QPS_THRESHOLD=5000
MAX_LATENCY_P99_MS=10

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
    if ! command -v gcc &>/dev/null && ! command -v clang &>/dev/null; then
        echo "[SKIP] No C++ compiler available"
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
    local os_name
    if [ -f /etc/os-release ]; then
        os_name="$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2 | tr -d '\n\t')"
    else
        os_name="$(sw_vers -productName 2>/dev/null || echo 'unknown')"
        local os_ver="$(sw_vers -productVersion 2>/dev/null || echo '')"
        os_name="${os_name} ${os_ver}"
        os_name="$(echo "${os_name}" | tr -d '\n\t')"
    fi
    local cpu_model
    if [ -f /proc/cpuinfo ]; then
        cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    else
        cpu_model="$(sysctl -n machdep.cpu.brand_string 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    fi
    local cores
    cores="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo '4')"
    local mem_mb
    if [ -f /proc/meminfo ]; then
        mem_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo '0')"
    else
        local mem_bytes="$(sysctl -n hw.memsize 2>/dev/null || echo '0')"
        mem_mb="$(echo "${mem_bytes}" | awk '{printf "%.0f", $1/1024/1024}')"
    fi

    local brpc_ver="${BRPC_VERSION}"
    if [ -f "${SCRIPT_DIR}/../../brpc/VERSION" ]; then
        brpc_ver="$(cat "${SCRIPT_DIR}/../../brpc/VERSION" | tr -d '\n\t')"
    elif command -v pkg-config &>/dev/null; then
        brpc_ver="$(pkg-config --modversion brpc 2>/dev/null | tr -d '\n\t' || echo "${BRPC_VERSION}")"
    fi

    local gcc_ver
    if command -v gcc &>/dev/null; then
        gcc_ver="$(gcc --version 2>/dev/null | head -1 | tr -d '\n\t')"
    elif command -v clang &>/dev/null; then
        gcc_ver="$(clang --version 2>/dev/null | head -1 | tr -d '\n\t')"
    else
        gcc_ver="unknown"
    fi

    local cmake_ver
    cmake_ver="$(cmake --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'unknown')"

    local protobuf_ver
    protobuf_ver="$(protoc --version 2>/dev/null | tr -d '\n\t' || echo 'unknown')"

    local openssl_support="no"
    if [ -f /usr/include/openssl/ssl.h ] || [ -f /usr/local/include/openssl/ssl.h ] || [ -f /opt/homebrew/include/openssl/ssl.h ]; then
        openssl_support="yes"
    elif command -v openssl &>/dev/null; then
        openssl_support="yes"
    fi

    python3 "${JSON_HELPER}" "${RESULTS_JSON}" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${brpc_ver}" "${gcc_ver}" \
        "${cmake_ver}" "${protobuf_ver}" "${openssl_support}"
}

run_benchmarks() {
    echo "[BENCH] Running RPC benchmark (Phase 3a - primary)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_rpc.py" \
        --results-json "${RESULTS_JSON}" \
        --section rpc_benchmark \
        --iterations "${ITERATIONS}"

    echo "[BENCH] Running protocol benchmark (Phase 3b - secondary)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_protocol.py" \
        --results-json "${RESULTS_JSON}" \
        --section protocol_benchmark \
        --iterations "${ITERATIONS}"

    echo "[BENCH] Running micro benchmark (Phase 3c)..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-json "${RESULTS_JSON}" \
        --section micro_benchmark \
        --iterations "${ITERATIONS}"
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

testGccOrClangIsInstalled() {
    local has_compiler=0
    command -v gcc &>/dev/null && has_compiler=1
    command -v clang &>/dev/null && has_compiler=1
    assertTrue "gcc or clang should be installed" "[ ${has_compiler} -eq 1 ]"
}

testCmakeIsInstalled() {
    if ! command -v cmake &>/dev/null; then
        echo "[WARN] cmake not installed"
        startSkipping
        return
    fi
    assertTrue "cmake should be installed" "command -v cmake"
}

testProtobufIsInstalled() {
    if ! command -v protoc &>/dev/null; then
        echo "[WARN] protoc not installed"
        startSkipping
        return
    fi
    assertTrue "protoc should be installed" "command -v protoc"
}

testBrpcHeadersAvailable() {
    local found=0
    for path in \
        /usr/include/brpc/server.h \
        /usr/local/include/brpc/server.h \
        /opt/homebrew/include/brpc/server.h \
        "${SCRIPT_DIR}/../../brpc/src/brpc/server.h"; do
        if [ -f "${path}" ]; then
            found=1
            break
        fi
    done
    assertTrue "brpc/server.h should exist somewhere" "[ ${found} -eq 1 ]"
}

testBrpcLibraryAvailable() {
    local found=0
    for path in \
        /usr/lib/libbrpc.a \
        /usr/lib/libbrpc.so \
        /usr/local/lib/libbrpc.a \
        /usr/local/lib/libbrpc.so \
        /opt/homebrew/lib/libbrpc.a \
        "${SCRIPT_DIR}/../../brpc/output/lib/libbrpc.a"; do
        if [ -f "${path}" ]; then
            found=1
            break
        fi
    done
    assertTrue "brpc library should exist" "[ ${found} -eq 1 ]"
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
    assertTrue "results.json should have version_info" "[ '${has}' = '1' ]"
}

testResultsJsonHasArchitecture() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local arch
    arch="$(json_get "${RESULTS_JSON}" architecture)"
    assertNotNull "Architecture should be set" "${arch}"
}

testResultsJsonHasSoftwareVersion() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local ver
    ver="$(json_get "${RESULTS_JSON}" version)"
    assertNotNull "Software version should be set" "${ver}"
}

testResultsJsonHasCompilerInfo() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" version_info)"
    if [ "${has}" != "1" ]; then
        startSkipping
        return
    fi
    local gcc_ver
    gcc_ver="$(json_get "${RESULTS_JSON}" version_info gcc_version)"
    assertNotNull "gcc_version should be set" "${gcc_ver}"
}

testBenchmarkRpcInResultsJson() {
    run_benchmarks
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" rpc_benchmark)"
    assertTrue "results.json should have rpc_benchmark" "[ '${has}' = '1' ]"
}

testBenchmarkRpcHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" rpc_benchmark)"
    if [ "${has}" != "1" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" benchmark)"
    assertTrue "rpc_benchmark should contain 'benchmark'" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" results)"
    assertTrue "rpc_benchmark should contain 'results'" "[ '${content}' = '1' ]"
}

testBenchmarkProtocolInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" protocol_benchmark)"
    assertTrue "results.json should have protocol_benchmark" "[ '${has}' = '1' ]"
}

testBenchmarkMicroInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "results.json should have micro_benchmark" "[ '${has}' = '1' ]"
}

testResultsJsonContainsAllBenchmarks() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" rpc)"
    assertTrue "Should contain rpc benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" protocol)"
    assertTrue "Should contain protocol benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" micro)"
    assertTrue "Should contain micro benchmark" "[ '${content}' = '1' ]"
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
