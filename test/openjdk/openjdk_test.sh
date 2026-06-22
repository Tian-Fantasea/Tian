#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"
RESULTS_JSON="${RESULTS_DIR}/results.json"
OPENJDK_VERSION="${OPENJDK_VERSION:-21}"
ITERATIONS="${ITERATIONS:-1}"
SHUNIT_PARENT="${SCRIPT_DIR}/openjdk_test.sh"

MIN_THROUGHPUT_OPS=1000
MAX_LATENCY_MS=100

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
    if ! command -v java &>/dev/null; then
        echo "[SKIP] java not installed"
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

    local openjdk_ver
    openjdk_ver="$(java -version 2>&1 | head -1 | sed 's/.*"\([^"]*\)".*/\1/' | tr -d '\n\t')"
    local jvm_name
    jvm_name="$(java -version 2>&1 | grep -i 'Server VM\|Client VM' | sed 's/^[[:space:]]*//' | tr -d '\n\t' || echo 'unknown')"
    local jvm_vendor
    jvm_vendor="$(java -version 2>&1 | grep -i 'Runtime Environment' | sed 's/OpenJDK Runtime Environment (\(build[^)]*\))/\1/' | cut -d+ -f1 | tr -d '\n\t' || echo 'unknown')"
    local gc_default
    gc_default="G1 GC"
    local java_ver_num
    java_ver_num="$(echo "${openjdk_ver}" | cut -d. -f1)"
    if [ "${java_ver_num}" = "1" ]; then
        gc_default="Parallel GC"
    elif [ "${java_ver_num}" -ge 12 ] 2>/dev/null; then
        gc_default="G1 GC"
    fi
    local jit_compiler
    jit_compiler="HotSpot JIT"

    python3 "${JSON_HELPER}" "${RESULTS_JSON}" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${openjdk_ver}" "${jvm_name}" \
        "${jvm_vendor}" "${gc_default}" "${jit_compiler}"
}

run_benchmarks() {
    echo "[BENCH] Running Renaissance benchmark (Phase 3a - primary)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_renaissance.py" \
        --results-json "${RESULTS_JSON}" \
        --section renaissance_benchmark \
        --iterations "${ITERATIONS}"

    echo "[BENCH] Running DaCapo benchmark (Phase 3b - secondary)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_dacapo.py" \
        --results-json "${RESULTS_JSON}" \
        --section dacapo_benchmark \
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

testJavaIsInstalled() {
    check_prerequisites
    assertTrue "java should be installed" "command -v java"
}

testJavacIsInstalled() {
    if ! command -v javac &>/dev/null; then
        echo "[WARN] javac not installed (JRE-only system)"
        startSkipping
        return
    fi
    assertTrue "javac should be installed" "command -v javac"
}

testOpenjdkIsInstalled() {
    check_prerequisites
    local vendor_info
    vendor_info="$(java -version 2>&1)"
    assertContains "java should be OpenJDK" "${vendor_info}" "OpenJDK"
}

testJvmIsHotspot() {
    check_prerequisites
    local jvm_info
    jvm_info="$(java -version 2>&1)"
    assertContains "JVM should be HotSpot" "${jvm_info}" "HotSpot"
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

testResultsJsonHasJvmName() {
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
    local jvm_name
    jvm_name="$(json_get "${RESULTS_JSON}" version_info jvm_name)"
    assertNotNull "jvm_name should be set" "${jvm_name}"
}

testResultsJsonHasGcDefault() {
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
    local gc
    gc="$(json_get "${RESULTS_JSON}" version_info gc_default)"
    assertNotNull "gc_default should be set" "${gc}"
}

testBenchmarkRenaissanceInResultsJson() {
    run_benchmarks
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" renaissance_benchmark)"
    assertTrue "results.json should have renaissance_benchmark section" "[ '${has}' = '1' ]"
}

testBenchmarkRenaissanceHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" renaissance_benchmark)"
    if [ "${has}" != "1" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" benchmark)"
    assertTrue "renaissance_benchmark should contain 'benchmark' field" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" results)"
    assertTrue "renaissance_benchmark should contain 'results' field" "[ '${content}' = '1' ]"
}

testBenchmarkDacapoInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" dacapo_benchmark)"
    assertTrue "results.json should have dacapo_benchmark section" "[ '${has}' = '1' ]"
}

testBenchmarkDacapoHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" dacapo_benchmark)"
    if [ "${has}" != "1" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" benchmark)"
    assertTrue "dacapo_benchmark should contain 'benchmark' field" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" results)"
    assertTrue "dacapo_benchmark should contain 'results' field" "[ '${content}' = '1' ]"
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
    content="$(json_contains "${RESULTS_JSON}" renaissance)"
    assertTrue "Should contain renaissance benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" dacapo)"
    assertTrue "Should contain dacapo benchmark" "[ '${content}' = '1' ]"
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
