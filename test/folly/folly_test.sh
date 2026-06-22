#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="folly"
SOFTWARE_VERSION="${VERSION:-2024.10.14.00}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"

MINIMUM_CONTAINER_OPS=50000
MINIMUM_THROUGHPUT=100000
MAXIMUM_AVG_LATENCY_MS=1.0
MAXIMUM_P99_LATENCY_MS=10.0
MINIMUM_CODEC_OPS=5000
MINIMUM_SCALING_OPS=100000

BUILD_DIR="${RESULTS_DIR}/build"

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

build_benchmarks() {
    log "BUILD" "Building Folly C++ benchmark binaries..."
    mkdir -p "${BUILD_DIR}"

    cmake -S "${SCRIPT_DIR}/scripts" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release || {
        log "ERROR" "CMake configuration failed. Ensure folly is installed with CMake config."
        log "ERROR" "  Install: apt install libfolly-dev (or build from source with cmake install)"
        return 1
    }

    cmake --build "${BUILD_DIR}" -j 4 || {
        log "ERROR" "Build failed. Check compiler and folly library compatibility."
        return 1
    }

    for bin in benchmark_containers benchmark_concurrency benchmark_codec benchmark_scaling; do
        if [ ! -x "${BUILD_DIR}/${bin}" ]; then
            log "ERROR" "Binary ${bin} not found after build"
            return 1
        fi
        log "BUILD" "Binary ${bin} OK"
    done

    log "BUILD" "All benchmark binaries built successfully"
}

check_prerequisites() {
    local errors=0

    local cpp_compiler=""
    if command -v g++ >/dev/null 2>&1; then cpp_compiler="g++"; fi
    if command -v clang++ >/dev/null 2>&1; then cpp_compiler="clang++"; fi
    if [ -z "${cpp_compiler}" ]; then
        log "ERROR" "C++ compiler not found. Install g++ or clang++ with C++17 support."
        errors=$((errors + 1))
    else
        log "CHECK" "C++ compiler OK: ${cpp_compiler} $(${cpp_compiler} --version 2>&1 | head -1)"
    fi

    if ! command -v cmake >/dev/null 2>&1; then
        log "ERROR" "cmake not found. Install cmake 3.10+."
        errors=$((errors + 1))
    else
        log "CHECK" "cmake OK: $(cmake --version 2>&1 | head -1)"
    fi

    local folly_found=0
    if [ -f "/usr/include/folly/FBString.h" ]; then folly_found=1; fi
    if [ -f "/usr/local/include/folly/FBString.h" ]; then folly_found=1; fi
    if [ -f "${FOLLY_HOME:-}/include/folly/FBString.h" ]; then folly_found=1; fi
    if [ "${folly_found}" -eq 0 ]; then
        log "ERROR" "folly headers not found. Install: apt install libfolly-dev"
        log "ERROR" "  Or build from source: https://github.com/facebook/folly/blob/main/folly/docs/QuickStart.md"
        errors=$((errors + 1))
    else
        log "CHECK" "folly headers OK"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "python3 OK: $(python3 --version 2>&1)"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb cpp_ver cmake_ver folly_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ] || [ "${cpu_model}" = "unknown" ]; then
        cpu_model="$(grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | awk '{print $3}' | tr -d '\n\t' || echo 'unknown')"
    fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"

    local cpp_compiler=""
    command -v g++ >/dev/null 2>&1 && cpp_compiler="g++"
    command -v clang++ >/dev/null 2>&1 && cpp_compiler="clang++"
    cpp_ver="$(command ${cpp_compiler} --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    cmake_ver="$(cmake --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    folly_ver="$(pkg-config --modversion folly 2>/dev/null | tr -d '\n\t' || echo "${SOFTWARE_VERSION}")"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${cpp_ver}" "cmake" "1" "${cores}" \
        --output "${RESULTS_DIR}/version_info.json" \
        --extra "folly_version=${folly_ver}" "compiler_version=${cpp_ver}" "cmake_version=${cmake_ver}" "install_method=package_manager" "category=cpp_foundation_library" "language=cpp"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    log "PHASE3" "Running container throughput benchmark (Phase 3a)..."
    "${BUILD_DIR}/benchmark_containers" \
        --output "${RESULTS_DIR}/benchmark_containers.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-100000}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m)" || log "WARN" "Containers benchmark failed"

    log "PHASE3" "Running concurrency latency benchmark (Phase 3b)..."
    "${BUILD_DIR}/benchmark_concurrency" \
        --output "${RESULTS_DIR}/benchmark_concurrency.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-100000}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m)" || log "WARN" "Concurrency benchmark failed"

    log "PHASE3" "Running codec micro benchmark (Phase 3c)..."
    "${BUILD_DIR}/benchmark_codec" \
        --output "${RESULTS_DIR}/benchmark_codec.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-10000}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m)" || log "WARN" "Codec benchmark failed"

    log "PHASE3" "Running concurrency scaling benchmark (Phase 3d)..."
    "${BUILD_DIR}/benchmark_scaling" \
        --output "${RESULTS_DIR}/benchmark_scaling.json" \
        --iterations "${ITERATIONS:-1}" \
        --ops-per-iter "${OPS_PER_ITER:-10000}" \
        --version "${SOFTWARE_VERSION}" \
        --architecture "$(uname -m)" || log "WARN" "Scaling benchmark failed"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        --results-dir "${RESULTS_DIR}" \
        --output "${RESULTS_DIR}/results.json"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --input "${RESULTS_DIR}/results.json" \
        --output "${RESULTS_DIR}/results.txt"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --input "${RESULTS_DIR}/results.json" \
        --output "${RESULTS_DIR}/results.html"

    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"
    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"
    log "PHASE4" "  HTML: ${RESULTS_DIR}/results.html"
    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"
}

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"

    log "START" "${SOFTWARE_NAME} ARM64 Performance Benchmark - v${SOFTWARE_VERSION}"

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        return 1
    fi

    build_benchmarks || {
        log "FATAL" "Failed to build benchmark binaries. Check folly installation."
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

testCppCompilerIsInstalled() {
    local found=0
    command -v g++ >/dev/null 2>&1 && found=1
    command -v clang++ >/dev/null 2>&1 && found=1
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: C++ compiler not installed, skipping"
        startSkipping
        return
    fi
    assertTrue "C++ compiler should exist" "[ ${found} -eq 1 ]"
}

testFollyIsInstalled() {
    local found=0
    [ -f "/usr/include/folly/FBString.h" ] && found=1
    [ -f "/usr/local/include/folly/FBString.h" ] && found=1
    [ -f "${FOLLY_HOME:-}/include/folly/FBString.h" ] && found=1
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: folly headers not found, skipping"
        startSkipping
        return
    fi
    assertTrue "folly headers should exist" "[ ${found} -eq 1 ]"
}

testFollyVersionMatches() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local ver
    ver="$(json_version "${ver_file}")"
    if [ -z "${ver}" ] || [ "${ver}" = "None" ] || [ "${ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertTrue "Version should be recorded" "[ -n '${ver}' ]"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkContainersProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_containers.json"
    assertTrue "Containers benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkContainersHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_containers.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkContainersThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_containers.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results ops_per_sec)"
    echo "[DIAG] Containers avg throughput: ${actual} ops/sec (threshold: ${MINIMUM_CONTAINER_OPS})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_CONTAINER_OPS}" results ops_per_sec)"
    assertTrue "Container throughput should be >= ${MINIMUM_CONTAINER_OPS} ops/sec, got ${actual}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkContainersF14FastMapOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_containers.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results f14_ops_per_sec)"
    echo "[DIAG] F14FastMap avg ops: ${actual} (threshold: ${MINIMUM_CONTAINER_OPS})"
    local has_ops
    has_ops="$(json_throughput_ge "${bench_file}" "${MINIMUM_CONTAINER_OPS}" results f14_ops_per_sec)"
    assertTrue "F14FastMap ops should be >= ${MINIMUM_CONTAINER_OPS}, got ${actual}" "[ ${has_ops} -eq 1 ]"
}

testBenchmarkConcurrencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    assertTrue "Concurrency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkConcurrencyAvgLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" results avg_latency_ms)"
    echo "[DIAG] Max avg concurrency latency: ${actual_lat} ms (threshold: ${MAXIMUM_AVG_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_AVG_LATENCY_MS}" results avg_latency_ms)"
    assertTrue "Avg concurrency latency should be <= ${MAXIMUM_AVG_LATENCY_MS}ms, got ${actual_lat}" "[ ${has_latency} -eq 1 ]"
}

testBenchmarkConcurrencyP99LatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" results p99_latency_ms)"
    echo "[DIAG] Max p99 concurrency latency: ${actual_lat} ms (threshold: ${MAXIMUM_P99_LATENCY_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_P99_LATENCY_MS}" results p99_latency_ms)"
    assertTrue "P99 concurrency latency should be <= ${MAXIMUM_P99_LATENCY_MS}ms, got ${actual_lat}" "[ ${has_latency} -eq 1 ]"
}

testBenchmarkCodecProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_codec.json"
    assertTrue "Codec benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkCodecAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/benchmark_codec.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local ops_count
    ops_count="$(json_count_results "${bench_file}")"
    assertTrue "Should have codec benchmark results (count=${ops_count})" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkCodecJsonParseOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_codec.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results json_parse_ops_per_sec)"
    echo "[DIAG] JSON parse ops: ${actual} (threshold: ${MINIMUM_CODEC_OPS})"
    local has_ops
    has_ops="$(json_throughput_ge "${bench_file}" "${MINIMUM_CODEC_OPS}" results json_parse_ops_per_sec)"
    assertTrue "JSON parse ops should be >= ${MINIMUM_CODEC_OPS}, got ${actual}" "[ ${has_ops} -eq 1 ]"
}

testBenchmarkCodecIOBufOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_codec.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results iobuf_ops_per_sec)"
    echo "[DIAG] IOBuf ops: ${actual} (threshold: ${MINIMUM_CODEC_OPS})"
    local has_ops
    has_ops="$(json_throughput_ge "${bench_file}" "${MINIMUM_CODEC_OPS}" results iobuf_ops_per_sec)"
    assertTrue "IOBuf ops should be >= ${MINIMUM_CODEC_OPS}, got ${actual}" "[ ${has_ops} -eq 1 ]"
}

testBenchmarkScalingProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_scaling.json"
    assertTrue "Scaling benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkScalingShowsProgression() {
    local bench_file="${RESULTS_DIR}/benchmark_scaling.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}")"
    assertTrue "Should have multiple scaling levels (count=${count})" "[ ${count} -ge 2 ]"
}

testBenchmarkScalingThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_scaling.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual
    actual="$(json_avg_throughput "${bench_file}" results total_ops_per_sec)"
    echo "[DIAG] Scaling avg throughput: ${actual} (threshold: ${MINIMUM_SCALING_OPS})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_SCALING_OPS}" results total_ops_per_sec)"
    assertTrue "Scaling throughput should be >= ${MINIMUM_SCALING_OPS}, got ${actual}" "[ ${has_throughput} -eq 1 ]"
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
    local has_containers has_concurrency has_codec has_scaling
    has_containers="$(json_contains "${agg_file}" containers)"
    has_concurrency="$(json_contains "${agg_file}" concurrency)"
    has_codec="$(json_contains "${agg_file}" codec)"
    has_scaling="$(json_contains "${agg_file}" scaling)"
    assertTrue "Should contain containers data" "[ ${has_containers} -eq 1 ]"
    assertTrue "Should contain concurrency data" "[ ${has_concurrency} -eq 1 ]"
    assertTrue "Should contain codec data" "[ ${has_codec} -eq 1 ]"
    assertTrue "Should contain scaling data" "[ ${has_scaling} -eq 1 ]"
}

oneTimeTearDown() {
    phase4_results || log "WARN" "Phase 4 had issues..."
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)      check_only=1; shift ;;
            -h|--help)    echo "Usage: ./folly_test.sh [--check]"; echo "  --check: Only verify prerequisites"; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; exit 1 ;;
        esac
    done

    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi

    download_shunit2 || {
        log "FATAL" "Failed to download shUnit2."
        exit 1
    }

    . "${SCRIPT_DIR}/shunit2"
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
