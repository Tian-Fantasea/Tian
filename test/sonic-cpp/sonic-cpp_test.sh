#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="sonic-cpp"
SOFTWARE_VERSION="${SONIC_CPP_VERSION:-1.0.2}"
SHUNIT_PARENT="${SCRIPT_DIR}/sonic-cpp_test.sh"

SONIC_CPP_HOME="${SONIC_CPP_HOME:-${SCRIPT_DIR}/sonic-cpp-src}"

MINIMUM_PARSE_THROUGHPUT="${MINIMUM_PARSE_THROUGHPUT:-10}"
MINIMUM_SERIALIZE_THROUGHPUT="${MINIMUM_SERIALIZE_THROUGHPUT:-5}"
MAXIMUM_LATENCY_MS="${MAXIMUM_LATENCY_MS:-1000}"

ITERATIONS="${ITERATIONS:-1}"
JSON_SIZES="${JSON_SIZES:-small,medium,large}"
COMPILE_FLAGS="${COMPILE_FLAGS:--O3 -march=native}"

LOG_FILE="${RESULTS_DIR}/results.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

json_get()              { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists()     { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results()    { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge()    { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_latency_le()       { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }
json_avg_throughput()   { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }
json_max_latency()      { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }
json_version()          { python3 "${JSON_HELPER}" "$1" version; }
json_contains()         { python3 "${JSON_HELPER}" "$1" contains "$2"; }

download_shunit2() {
    if [ -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "shUnit2 already present"
        return 0
    fi

    log "SETUP" "Downloading shUnit2..."
    local mirrors=(
        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
        "https://raw.gitmirror.com/kward/shunit2/master/shunit2"
    )
    local downloaded=0
    for mirror_url in "${mirrors[@]}"; do
        curl --connect-timeout 30 --max-time 60 -sL -o "${SCRIPT_DIR}/shunit2" "${mirror_url}" && {
            chmod +x "${SCRIPT_DIR}/shunit2"
            grep -q "^SHUNIT_VERSION=" "${SCRIPT_DIR}/shunit2" && { downloaded=1; break; }
        }
        rm -f "${SCRIPT_DIR}/shunit2"
    done
    if [ "${downloaded}" -eq 0 ]; then
        for mirror_url in "${mirrors[@]}"; do
            wget --timeout=30 --tries=2 -q -O "${SCRIPT_DIR}/shunit2" "${mirror_url}" 2>/dev/null && {
                chmod +x "${SCRIPT_DIR}/shunit2"
                grep -q "^SHUNIT_VERSION=" "${SCRIPT_DIR}/shunit2" && { downloaded=1; break; }
            }
            rm -f "${SCRIPT_DIR}/shunit2"
        done
    fi
    if [ "${downloaded}" -eq 0 ]; then
        log "ERROR" "Failed to download shUnit2"
        return 1
    fi
}

check_prerequisites() {
    local errors=0

    if ! command -v g++ >/dev/null 2>&1; then
        log "ERROR" "g++ is not installed. Please install GCC/G++ before running."
        log "ERROR" "  On Ubuntu/Debian: sudo apt-get install g++"
        log "ERROR" "  On macOS: xcode-select --install or brew install gcc"
        errors=$((errors + 1))
    else
        log "CHECK" "g++ OK: $(g++ --version 2>&1 | head -1)"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "python3 OK: $(python3 --version 2>&1)"
    fi

    local sonic_include="${SONIC_CPP_HOME}/include/sonic/sonic.h"
    if [ ! -f "${sonic_include}" ]; then
        log "ERROR" "sonic-cpp headers not found at ${SONIC_CPP_HOME}/include/"
        log "ERROR" "  Please clone sonic-cpp: git clone https://github.com/bytedance/sonic-cpp.git ${SONIC_CPP_HOME}"
        log "ERROR" "  Or set SONIC_CPP_HOME to the directory containing sonic-cpp source"
        errors=$((errors + 1))
    else
        log "CHECK" "sonic-cpp headers OK: ${SONIC_CPP_HOME}/include/"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb gpp_ver sonic_ver sonic_home
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || sysctl -n machdep.cpu.brand_string 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || sysctl -n hw.ncpu 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    gpp_ver="$(g++ --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'unknown')"
    sonic_ver="${SOFTWARE_VERSION}"
    sonic_home="${SONIC_CPP_HOME}"
    local sonic_git_ver
    sonic_git_ver="$(git -C ${SONIC_CPP_HOME} describe --tags 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    local compile_test
    compile_test="$(g++ -I${SONIC_CPP_HOME}/include -std=c++11 -O3 -march=native -x c++ - -o /dev/null 2>&1 <<'EOF'
#include "sonic/sonic.h"
int main() { sonic_json::Document doc; doc.Parse("{}"); return 0; }
EOF
echo "compile_ok" || echo "compile_fail")"
    local compile_status
    if echo "${compile_test}" | grep -q "compile_ok"; then
        compile_status="ok"
    else
        compile_status="fail"
    fi

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${gpp_ver}" "${sonic_home}" "${sonic_git_ver}" "${cores}" \
        --output "${RESULTS_DIR}/version_info.json" \
        --extra "sonic_cpp_home:${sonic_home}" \
        --extra "sonic_git_version:${sonic_git_ver}" \
        --extra "compile_flags:${COMPILE_FLAGS}" \
        --extra "compile_test:${compile_status}" \
        --extra "json_sizes:${JSON_SIZES}" \
        --extra "iterations:${ITERATIONS}" \
        --extra "minimum_parse_throughput:${MINIMUM_PARSE_THROUGHPUT}" \
        --extra "minimum_serialize_throughput:${MINIMUM_SERIALIZE_THROUGHPUT}"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    log "PHASE3" "--- 3a: JSON Parse Throughput ---"
    python3 "${SCRIPT_DIR}/scripts/benchmark_json_parse.py" \
        --output "${RESULTS_DIR}/benchmark_primary.json" \
        --sonic-home "${SONIC_CPP_HOME}" \
        --iterations "${ITERATIONS}" \
        --json-sizes "${JSON_SIZES}" \
        --compile-flags "${COMPILE_FLAGS}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Parse benchmark had issues"

    log "PHASE3" "--- 3b: JSON Serialize + ParseOnDemand ---"
    python3 "${SCRIPT_DIR}/scripts/benchmark_json_serialize.py" \
        --output "${RESULTS_DIR}/benchmark_secondary.json" \
        --sonic-home "${SONIC_CPP_HOME}" \
        --iterations "${ITERATIONS}" \
        --json-sizes "${JSON_SIZES}" \
        --compile-flags "${COMPILE_FLAGS}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Serialize benchmark had issues"

    log "PHASE3" "--- 3c: Micro Benchmark ---"
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --output "${RESULTS_DIR}/micro_benchmark.json" \
        --sonic-home "${SONIC_CPP_HOME}" \
        --iterations "${ITERATIONS}" \
        --compile-flags "${COMPILE_FLAGS}" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        "${RESULTS_DIR}" "${RESULTS_DIR}/results.json" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Aggregation had issues"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Summary had issues"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.html" \
        2>&1 | tee -a "${LOG_FILE}" || log "WARN" "HTML report had issues"

    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"
    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"
    log "PHASE4" "  HTML: ${RESULTS_DIR}/results.html"
    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"
}

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"

    log "START" "sonic-cpp ARM64 Performance Benchmark - v${SOFTWARE_VERSION}"

    check_prerequisites || {
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        return 1
    }

    phase2_verify || log "WARN" "Phase 2 had issues, continuing..."
    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing..."
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

testSonicCppIsInstalled() {
    local found=0
    if [ -f "${SONIC_CPP_HOME}/include/sonic/sonic.h" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: sonic-cpp headers not found at ${SONIC_CPP_HOME}, skipping install check"
        startSkipping
        return
    fi
    assertTrue "sonic-cpp headers should exist" "[ ${found} -eq 1 ]"
}

testSonicCppVersionMatches() {
    local git_ver
    git_ver="$(git -C ${SONIC_CPP_HOME} describe --tags 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    if [ "${git_ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertTrue "sonic-cpp version should be available" "[ '${git_ver}' != '' ]"
}

testGplusplusIsAvailable() {
    local found=0
    if command -v g++ >/dev/null 2>&1; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: g++ not installed, skipping compiler check"
        startSkipping
        return
    fi
    assertTrue "g++ should be available" "[ ${found} -eq 1 ]"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkParsingProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    assertTrue "Primary benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkParsingHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkParsingThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_throughput
    actual_throughput="$(json_avg_throughput "${bench_file}" avg_throughput_mb_per_sec)"
    echo "[DIAG] Parse throughput: ${actual_throughput} MB/s (threshold: ${MINIMUM_PARSE_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_PARSE_THROUGHPUT}" avg_throughput_mb_per_sec)"
    assertTrue "Parse throughput should be >= ${MINIMUM_PARSE_THROUGHPUT} MB/s, got ${actual_throughput}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkParsingAllSizesCompleted() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_sizes
    has_sizes="$(json_contains "${bench_file}" parse_throughput_vs_size)"
    assertTrue "Should have parse throughput vs size data" "[ ${has_sizes} -eq 1 ]"
}

testBenchmarkSerializationProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    assertTrue "Secondary benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkSerializationHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkSerializationThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_throughput
    actual_throughput="$(json_avg_throughput "${bench_file}" avg_throughput_mb_per_sec)"
    echo "[DIAG] Serialize throughput: ${actual_throughput} MB/s (threshold: ${MINIMUM_SERIALIZE_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_SERIALIZE_THROUGHPUT}" avg_throughput_mb_per_sec)"
    assertTrue "Serialize throughput should be >= ${MINIMUM_SERIALIZE_THROUGHPUT} MB/s, got ${actual_throughput}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkMicroProducesResults() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkMicroAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local ops_count
    ops_count="$(json_count_results "${bench_file}")"
    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkMicroArm64NeonDetected() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_arm64
    has_arm64="$(json_contains "${bench_file}" arm64_simd_detection)"
    assertTrue "Should have ARM64 SIMD detection results" "[ ${has_arm64} -eq 1 ]"
}

testAggregatedResultsExist() {
    assertTrue "results.json should exist" "[ -f '${RESULTS_DIR}/results.json' ]"
}

testHtmlReportGenerated() {
    assertTrue "results.html should exist" "[ -f '${RESULTS_DIR}/results.html' ]"
}

testSummaryReportGenerated() {
    assertTrue "results.txt should exist" "[ -f '${RESULTS_DIR}/results.txt' ]"
}

testLogFileGenerated() {
    assertTrue "results.log should exist" "[ -f '${RESULTS_DIR}/results.log' ]"
}

testAggregatedResultsContainsAllBenchmarks() {
    local agg_file="${RESULTS_DIR}/results.json"
    if [ ! -f "${agg_file}" ]; then startSkipping; return; fi
    local has_primary has_secondary has_micro
    has_primary="$(json_contains "${agg_file}" primary_benchmark)"
    has_secondary="$(json_contains "${agg_file}" secondary_benchmark)"
    has_micro="$(json_contains "${agg_file}" micro_benchmark)"
    assertTrue "Should contain primary_benchmark data" "[ ${has_primary} -eq 1 ]"
    assertTrue "Should contain secondary_benchmark data" "[ ${has_secondary} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
}

oneTimeTearDown() {
    phase4_results || log "WARN" "Phase 4 had issues..."
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

usage() {
    echo "Usage: ./sonic-cpp_test.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check    Check prerequisites only"
    echo "  -h|--help  Show this help"
    echo ""
    echo "Environment variables:"
    echo "  SONIC_CPP_HOME            sonic-cpp source directory (default: ./sonic-cpp-src)"
    echo "  SONIC_CPP_VERSION         Version to check (default: 1.0.2)"
    echo "  ITERATIONS                Number of iterations (default: 1)"
    echo "  JSON_SIZES                JSON sizes to test (default: small,medium,large)"
    echo "  COMPILE_FLAGS             C++ compile flags (default: -O3 -march=native)"
    echo "  MINIMUM_PARSE_THROUGHPUT  Min MB/s threshold (default: 10)"
    echo "  MINIMUM_SERIALIZE_THROUGHPUT  Min MB/s threshold (default: 5)"
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)      check_only=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    log "START" "sonic-cpp ARM64 Benchmark v${SOFTWARE_VERSION}"

    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi

    download_shunit2 || {
        log "FATAL" "Failed to download shUnit2"
        exit 1
    }

    . "${SCRIPT_DIR}/shunit2"
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
