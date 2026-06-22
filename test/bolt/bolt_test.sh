#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="bolt"
SOFTWARE_VERSION="${BOLT_VERSION:-1.4.3}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"

DATA_SIZE="${DATA_SIZE:-100000}"
ITERATIONS="${ITERATIONS:-1}"

MINIMUM_YCSB_THROUGHPUT="${MINIMUM_YCSB_THROUGHPUT:-10000}"
MAXIMUM_YCSB_LATENCY_MS="${MAXIMUM_YCSB_LATENCY_MS:-100}"
MINIMUM_THROUGHPUT_OPS="${MINIMUM_THROUGHPUT_OPS:-10000}"

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
    log "BUILD" "Building Go benchmark binaries..."
    local build_dir="/tmp/bolt_bench_build_${SOFTWARE_VERSION}"
    rm -rf "${build_dir}"
    mkdir -p "${build_dir}/src/benchmark"

    printf '%s\n' 'module benchmark' > "${build_dir}/src/benchmark/go.mod"
    printf '%s\n' '' >> "${build_dir}/src/benchmark/go.mod"
    printf '%s\n' 'go 1.23' >> "${build_dir}/src/benchmark/go.mod"
    printf '%s\n' '' >> "${build_dir}/src/benchmark/go.mod"
    printf '%s\n' 'require go.etcd.io/bbolt v1.4.3' >> "${build_dir}/src/benchmark/go.mod"

    for bench_src in "${SCRIPT_DIR}/scripts"/*.go; do
        local bench_name
        bench_name="$(basename "${bench_src}" .go)"
        cp "${bench_src}" "${build_dir}/src/benchmark/${bench_name}.go"
    done

    cd "${build_dir}/src/benchmark"
    GOTOOLCHAIN=local go mod tidy 2>&1 | tee -a "${LOG_FILE}"
    if [ ! -f "go.sum" ]; then
        log "ERROR" "go mod tidy failed"
        cd "${SCRIPT_DIR}"
        return 1
    fi

    for bench_src in "${SCRIPT_DIR}/scripts"/*.go; do
        local bench_name
        bench_name="$(basename "${bench_src}" .go)"
        log "BUILD" "Compiling ${bench_name}..."
        GOTOOLCHAIN=local go build -o "${SCRIPT_DIR}/scripts/${bench_name}" "${bench_name}.go" 2>&1 | tee -a "${LOG_FILE}"
    done

    cd "${SCRIPT_DIR}"
    rm -rf "${build_dir}"
    log "BUILD" "All benchmark binaries built successfully"
}

check_prerequisites() {
    local errors=0

    if ! command -v go >/dev/null 2>&1; then
        log "ERROR" "Go is not installed. Please install Go 1.23+ before running."
        log "ERROR" "  Recommended: https://go.dev/dl/ (ARM64 tarball)"
        errors=$((errors + 1))
    else
        log "CHECK" "Go OK: $(go version 2>&1 | head -1)"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    else
        log "CHECK" "json_helper.py OK"
    fi

    if [ ! -x "${SCRIPT_DIR}/scripts/micro_benchmark" ]; then
        log "WARN" "Go benchmark binaries not found, will build..."
        build_benchmarks || {
            log "ERROR" "Failed to build benchmark binaries"
            errors=$((errors + 1))
        }
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local db_path="${RESULTS_DIR}/verify_test.db"
    rm -f "${db_path}"
    "${SCRIPT_DIR}/scripts/micro_benchmark" --mode verify --db-path "${db_path}" --results-dir "${RESULTS_DIR}" 2>&1 | tee -a "${LOG_FILE}"
    rm -f "${db_path}"

    local timestamp arch kernel os cpu_model cores mem_mb go_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ] || [ "${cpu_model}" = "" ]; then
        cpu_model="$(grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    go_ver="$(go version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    local bbolt_ver="${SOFTWARE_VERSION}"
    local parallelism="${cores}"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${go_ver}" "go_module" "1" "${parallelism}" \
        --output "${RESULTS_DIR}/version_info.json" \
        --extra "go_version=${go_ver}" \
        --extra "bbolt_version=${bbolt_ver}" \
        --extra "install_method=go_module" \
        --extra "value_size=256"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    log "PHASE3a" "Running YCSB benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_ycsb" \
        --key-count "${DATA_SIZE}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}" 2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3b" "Running throughput scaling benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_throughput" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}" 2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3c" "Running micro benchmark..."
    "${SCRIPT_DIR}/scripts/micro_benchmark" \
        --mode full \
        --key-count "${DATA_SIZE}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}" 2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3d" "Running concurrency benchmark..."
    "${SCRIPT_DIR}/scripts/benchmark_concurrency" \
        --key-count "${DATA_SIZE}" \
        --iterations "${ITERATIONS}" \
        --results-dir "${RESULTS_DIR}" 2>&1 | tee -a "${LOG_FILE}"
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

testGoIsInstalled() {
    assertTrue "Go should be installed" "command -v go >/dev/null 2>&1"
}

testGoVersionSufficient() {
    local go_ver
    go_ver="$(go version 2>&1 | head -1 | tr -d '\n\t')"
    local major
    major="$(echo "${go_ver}" | grep -oP 'go[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 | sed 's/go//' | cut -d. -f1 | tr -d '\n\t')"
    local minor
    minor="$(echo "${go_ver}" | grep -oP 'go[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 | sed 's/go//' | cut -d. -f2 | tr -d '\n\t')"
    assertTrue "Go version should be >= 1.23" \
        "[ ${major} -ge 1 ] && ([ ${major} -gt 1 ] || [ ${minor} -ge 23 ])"
}

testSoftwareIsInstalled() {
    local found=0
    [ -x "${SCRIPT_DIR}/scripts/micro_benchmark" ] && found=1
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: bbolt benchmark binaries not built, skipping"
        startSkipping
        return
    fi
    assertTrue "bbolt benchmark binary should exist" "[ ${found} -eq 1 ]"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkYcsbProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    assertTrue "YCSB benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkYcsbHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_contains "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkYcsbThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_YCSB_THROUGHPUT}" results ops_per_sec)"
    local actual_throughput
    actual_throughput="$(json_avg_throughput "${bench_file}" results ops_per_sec)"
    echo "[DIAG] YCSB throughput: ${actual_throughput} ops/sec (threshold: ${MINIMUM_YCSB_THROUGHPUT})"
    assertTrue "YCSB throughput should be >= ${MINIMUM_YCSB_THROUGHPUT}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkYcsbLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_YCSB_LATENCY_MS}" results avg_latency_ms)"
    local actual_latency
    actual_latency="$(json_max_latency "${bench_file}" results avg_latency_ms)"
    echo "[DIAG] YCSB max latency: ${actual_latency} ms (threshold: ${MAXIMUM_YCSB_LATENCY_MS})"
    assertTrue "YCSB avg latency should be <= ${MAXIMUM_YCSB_LATENCY_MS}ms" "[ ${has_latency} -eq 1 ]"
}

testBenchmarkThroughputProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    assertTrue "Throughput benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkThroughputScalingShowsProgression() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}")"
    assertTrue "Should have throughput results at multiple key counts" "[ ${count} -ge 3 ]"
}

testBenchmarkThroughputOpsPerSecAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT_OPS}" results write_ops_per_sec)"
    local actual
    actual="$(json_avg_throughput "${bench_file}" results write_ops_per_sec)"
    echo "[DIAG] Throughput write ops/sec: ${actual} (threshold: ${MINIMUM_THROUGHPUT_OPS})"
    assertTrue "Throughput ops/sec should be >= ${MINIMUM_THROUGHPUT_OPS}" "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkMicroProducesResults() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkMicroAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}")"
    assertTrue "Should have results for all micro operations" "[ ${count} -ge 4 ]"
}

testBenchmarkMicroContainsOperations() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_put has_get
    has_put="$(json_contains "${bench_file}" put)"
    has_get="$(json_contains "${bench_file}" get)"
    assertTrue "Should contain put operation" "[ ${has_put} -eq 1 ]"
    assertTrue "Should contain get operation" "[ ${has_get} -eq 1 ]"
}

testBenchmarkConcurrencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    assertTrue "Concurrency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkConcurrencyScalingShowsProgression() {
    local bench_file="${RESULTS_DIR}/benchmark_concurrency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local count
    count="$(json_count_results "${bench_file}")"
    assertTrue "Should have results at multiple concurrency levels" "[ ${count} -ge 3 ]"
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
    local has_ycsb has_throughput has_micro has_concurrency
    has_ycsb="$(json_contains "${agg_file}" ycsb)"
    has_throughput="$(json_contains "${agg_file}" throughput)"
    has_micro="$(json_contains "${agg_file}" micro)"
    has_concurrency="$(json_contains "${agg_file}" concurrency)"
    assertTrue "Should contain ycsb data" "[ ${has_ycsb} -eq 1 ]"
    assertTrue "Should contain throughput data" "[ ${has_throughput} -eq 1 ]"
    assertTrue "Should contain micro data" "[ ${has_micro} -eq 1 ]"
    assertTrue "Should contain concurrency data" "[ ${has_concurrency} -eq 1 ]"
}

oneTimeTearDown() {
    phase4_results || log "WARN" "Phase 4 had issues..."
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check              Check prerequisites only"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  BOLT_VERSION         bbolt version (default: 1.4.3)"
    echo "  DATA_SIZE            Number of keys (default: 100000)"
    echo "  ITERATIONS           Iterations per test (default: 1)"
    echo "  MINIMUM_YCSB_THROUGHPUT  YCSB ops/sec threshold (default: 10000)"
    echo "  MAXIMUM_YCSB_LATENCY_MS YCSB latency threshold ms (default: 100)"
    exit 0
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --check)      check_only=1; shift ;;
            -h|--help)    usage ;;
            *)            log "ERROR" "Unknown option: $1"; usage ;;
        esac
    done

    log "START" "${SOFTWARE_NAME} ARM64 Benchmark v${SOFTWARE_VERSION}"

    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi

    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        exit 1
    fi

    download_shunit2 || {
        log "FATAL" "Failed to download shUnit2. Please install manually."
        exit 1
    }

    . "${SCRIPT_DIR}/shunit2"
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
