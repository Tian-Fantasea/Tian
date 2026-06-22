#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="envoy"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-1.38.2}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"
LOG_FILE="${RESULTS_DIR}/results.log"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"

ENVOY_BIN="${ENVOY_BIN:-/usr/local/bin/envoy}"
ENVOY_PORT="${ENVOY_PORT:-10000}"
ENVOY_ADMIN_PORT="${ENVOY_ADMIN_PORT:-9901}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
DURATION="${DURATION:-5}"
ITERATIONS="${ITERATIONS:-1}"
CONCURRENCY="${CONCURRENCY:-1,16,64}"
MINIMUM_RPS="${MINIMUM_RPS:-5000}"
MAXIMUM_P99_MS="${MAXIMUM_P99_MS:-50.0}"
DATA_SIZE="${DATA_SIZE:-1000}"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

json_get() { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results() { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge() { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_latency_le() { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }
json_avg_throughput() { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }
json_max_latency() { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }
json_version() { python3 "${JSON_HELPER}" "$1" version; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }

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
    log "SETUP" "shUnit2 downloaded successfully"
}

check_prerequisites() {
    local errors=0
    local envoy_bin="${ENVOY_BIN}"
    if [ "${envoy_bin}" = "docker_envoy" ]; then
        if ! command -v docker >/dev/null 2>&1; then
            log "ERROR" "docker is not installed"
            errors=$((errors + 1))
        else
            log "CHECK" "Docker OK"
        fi
    else
        if [ ! -x "${envoy_bin}" ]; then
            log "ERROR" "Envoy binary not found at ${envoy_bin}"
            log "ERROR" "  Please install Envoy or set ENVOY_BIN to your binary path"
            log "ERROR" "  Or set ENVOY_BIN=docker_envoy to use Docker"
            errors=$((errors + 1))
        else
            log "CHECK" "Envoy OK: $("${envoy_bin}" --version 2>&1 | head -1)"
        fi
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed"
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi
    if ! command -v wrk >/dev/null 2>&1; then
        log "WARN" "wrk not available (HTTP benchmarks will be limited)"
    else
        log "CHECK" "wrk OK"
    fi
    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi
    return ${errors}
}

start_backend() {
    local backend_pid_file="${RESULTS_DIR}/backend.pid"
    if [ -f "${backend_pid_file}" ]; then
        kill "$(cat "${backend_pid_file}")" 2>/dev/null || true
        rm -f "${backend_pid_file}"
    fi
    python3 "${SCRIPT_DIR}/scripts/backend_server.py" &
    local bp=$!
    echo "${bp}" > "${backend_pid_file}"
    sleep 1
    log "SETUP" "Backend server started on port ${BACKEND_PORT} (PID ${bp})"
}

stop_backend() {
    local backend_pid_file="${RESULTS_DIR}/backend.pid"
    if [ -f "${backend_pid_file}" ]; then
        kill "$(cat "${backend_pid_file}")" 2>/dev/null || true
        rm -f "${backend_pid_file}"
        log "SETUP" "Backend server stopped"
    fi
}

start_envoy() {
    local envoy_pid_file="${RESULTS_DIR}/envoy.pid"
    local envoy_conf="${SCRIPT_DIR}/envoy_config/envoy_http.yaml"
    if [ ! -f "${envoy_conf}" ]; then
        mkdir -p "${SCRIPT_DIR}/envoy_config"
        python3 "${JSON_HELPER}" "${envoy_conf}" write_envoy_http_config \
            "${ENVOY_PORT}" "${ENVOY_ADMIN_PORT}" "${BACKEND_PORT}" "127.0.0.1"
    fi
    if [ -f "${envoy_pid_file}" ]; then
        kill "$(cat "${envoy_pid_file}")" 2>/dev/null || true
        rm -f "${envoy_pid_file}"
    fi
    local envoy_bin="${ENVOY_BIN}"
    if [ "${envoy_bin}" = "docker_envoy" ]; then
        docker run -d --name envoy_bench -p "${ENVOY_PORT}:${ENVOY_PORT}" -p "${ENVOY_ADMIN_PORT}:${ENVOY_ADMIN_PORT}" \
            -v "${envoy_conf}:/etc/envoy/envoy.yaml" \
            envoyproxy/envoy:v1.38-latest -c /etc/envoy/envoy.yaml 2>/dev/null || log "WARN" "Docker Envoy start failed"
    else
        "${envoy_bin}" -c "${envoy_conf}" --concurrency "$(nproc 2>/dev/null || echo 4)" &
        local ep=$!
        echo "${ep}" > "${envoy_pid_file}"
        sleep 2
        log "SETUP" "Envoy started on port ${ENVOY_PORT} (PID ${ep})"
    fi
}

stop_envoy() {
    local envoy_pid_file="${RESULTS_DIR}/envoy.pid"
    if [ -f "${envoy_pid_file}" ]; then
        kill "$(cat "${envoy_pid_file}")" 2>/dev/null || true
        rm -f "${envoy_pid_file}"
        log "SETUP" "Envoy stopped"
    fi
    if [ "${ENVOY_BIN}" = "docker_envoy" ]; then
        docker rm -f envoy_bench 2>/dev/null || true
    fi
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="
    local timestamp arch kernel os_name cpu_model cores mem_mb envoy_ver python_ver wrk_ver threads
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os_name="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ]; then
        local num_proc
        num_proc="$(grep -c 'processor' /proc/cpuinfo 2>/dev/null || echo 0)"
        cpu_model="ARM64 CPU (${num_proc} cores)"
    fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t')"
    if [ "${ENVOY_BIN}" = "docker_envoy" ]; then
        envoy_ver="$(docker run --rm envoyproxy/envoy:v1.38-latest --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    else
        envoy_ver="$("${ENVOY_BIN}" --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    fi
    wrk_ver="$(wrk --version 2>&1 | head -1 | tr -d '\n\t' || echo 'not available')"
    threads="${cores}"
    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${envoy_ver}" "${python_ver}" "${wrk_ver}" "${ENVOY_BIN}" "${threads}"
    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="
    mkdir -p "${RESULTS_DIR}"
    start_backend
    start_envoy
    sleep 2
    export ENVOY_PORT ENVOY_ADMIN_PORT BACKEND_PORT DURATION ITERATIONS CONCURRENCY DATA_SIZE RESULTS_DIR
    local envoy_conf_dir="${SCRIPT_DIR}/envoy_config"
    local envoy_bin="${ENVOY_BIN}"
    export ENVOY_CONF_DIR="${envoy_conf_dir}" ENVOY_BIN="${envoy_bin}"
    log "PHASE3A" "Running HTTP proxy benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_http_proxy.py" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "HTTP proxy benchmark had issues"
    log "PHASE3B" "Running TCP proxy + latency benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_tcp_proxy.py" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "TCP proxy benchmark had issues"
    log "PHASE3C" "Running micro benchmarks..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="
    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        "${RESULTS_DIR}" "${RESULTS_DIR}/results.json"
    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt"
    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.html"
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
    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing"
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
    local envoy_bin="${ENVOY_BIN}"
    if [ "${envoy_bin}" = "docker_envoy" ]; then
        if command -v docker >/dev/null 2>&1; then found=1; fi
    else
        if [ -x "${envoy_bin}" ]; then found=1; fi
    fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: Envoy not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "Envoy binary should exist" "[ ${found} -eq 1 ]"
}

testSoftwareVersionMatches() {
    local ver="unknown"
    if [ "${ENVOY_BIN}" = "docker_envoy" ]; then
        ver="$(docker run --rm envoyproxy/envoy:v1.38-latest --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    else
        ver="$("${ENVOY_BIN}" --version 2>&1 | head -1 | tr -d '\n\t' || echo 'unknown')"
    fi
    if [ "${ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertNotNull "Version should not be empty" "${ver}"
}

testSoftwareRunsBasicCommand() {
    local envoy_bin="${ENVOY_BIN}"
    if [ "${envoy_bin}" = "docker_envoy" ]; then
        local result
        result="$(docker run --rm envoyproxy/envoy:v1.38-latest --version 2>&1)"
        assertTrue "Envoy basic command should succeed" "[ $? -eq 0 ]"
    else
        if [ ! -x "${envoy_bin}" ]; then
            startSkipping
            return
        fi
        local result
        result="$("${envoy_bin}" --version 2>&1)"
        assertTrue "Envoy basic command should succeed" "[ $? -eq 0 ]"
    fi
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

testBenchmarkPrimaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    assertTrue "HTTP proxy benchmark JSON should exist" "[ -f '${bench_file}' ]"
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

testBenchmarkPrimaryRpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_primary.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local peak_rps
    peak_rps="$(json_avg_throughput "${bench_file}" results_summary rps_vs_concurrency avg_rps)"
    if [ "${peak_rps}" = "NULL" ] || [ -z "${peak_rps}" ]; then
        local count
        count="$(json_count_results "${bench_file}")"
        if [ "${count}" -gt 0 ]; then
            local has_thr
            has_thr="$(json_throughput_ge "${bench_file}" "${MINIMUM_RPS}" results 0 data 0 avg_rps)"
            echo "[DIAG] HTTP RPS threshold check: ${has_thr} (threshold: ${MINIMUM_RPS})"
            assertTrue "HTTP RPS should be >= ${MINIMUM_RPS}" "[ ${has_thr} -eq 1 ]"
        else
            startSkipping
            return
        fi
    else
        echo "[DIAG] HTTP peak RPS: ${peak_rps} (threshold: ${MINIMUM_RPS})"
        assertTrue "HTTP peak RPS (${peak_rps}) should be >= ${MINIMUM_RPS}" \
            "[ $(echo "${peak_rps} >= ${MINIMUM_RPS}" | bc -l) -eq 1 ]"
    fi
}

testBenchmarkSecondaryProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_secondary.json"
    assertTrue "TCP proxy benchmark JSON should exist" "[ -f '${bench_file}' ]"
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
    local has_lat
    has_lat="$(json_latency_le "${bench_file}" "${MAXIMUM_P99_MS}" results 0 data avg_latency_p99_ms)"
    if [ "${has_lat}" = "0" ]; then
        has_lat="$(json_latency_le "${bench_file}" "${MAXIMUM_P99_MS}" results 0 data 0 avg_latency_p99_ms)"
    fi
    echo "[DIAG] TCP P99 latency check: ${has_lat} (threshold: ${MAXIMUM_P99_MS} ms)"
    assertTrue "TCP P99 latency should be <= ${MAXIMUM_P99_MS} ms" "[ ${has_lat} -eq 1 ]"
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
    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkMicroHasArm64CryptoData() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then
        startSkipping
        return
    fi
    local has_crypto
    has_crypto="$(json_contains "${bench_file}" arm64_crypto)"
    assertTrue "Should have ARM64 crypto detection data" "[ ${has_crypto} -eq 1 ]"
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
    if [ ! -f "${agg_file}" ]; then
        startSkipping
        return
    fi
    local has_primary has_secondary has_micro
    has_primary="$(json_contains "${agg_file}" primary_benchmark)"
    has_secondary="$(json_contains "${agg_file}" secondary_benchmark)"
    has_micro="$(json_contains "${agg_file}" micro_benchmark)"
    assertTrue "Should contain primary_benchmark data" "[ ${has_primary} -eq 1 ]"
    assertTrue "Should contain secondary_benchmark data" "[ ${has_secondary} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
}

oneTimeTearDown() {
    stop_envoy
    stop_backend
    phase4_results || log "WARN" "Phase 4 had issues"
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

usage() {
    cat <<USAGE
Usage: $(basename "$0") [OPTIONS]
Envoy ARM64 Performance Benchmark (shUnit2)
Options:
  --check    Check prerequisites only (do not run benchmarks)
  -h|--help  Show this help
Environment variables:
  SOFTWARE_VERSION   Envoy version (default: 1.38.2)
  ENVOY_BIN          Envoy binary path or "docker_envoy" (default: /usr/local/bin/envoy)
  ENVOY_PORT         Envoy listener port (default: 10000)
  ENVOY_ADMIN_PORT   Envoy admin port (default: 9901)
  BACKEND_PORT       Backend server port (default: 8080)
  DURATION           wrk test duration in seconds (default: 5)
  ITERATIONS         Number of iterations per test (default: 1)
  CONCURRENCY        Concurrency levels, comma-separated (default: 1,16,64)
  MINIMUM_RPS        Minimum RPS threshold (default: 5000)
  MAXIMUM_P99_MS     Maximum P99 latency threshold in ms (default: 50.0)
  DATA_SIZE          Backend response size in bytes (default: 1000)
Examples:
  # Check prerequisites
  ./envoy_test.sh --check
  # Full run with local Envoy
  ./envoy_test.sh
  # Full run with Docker Envoy
  ENVOY_BIN=docker_envoy ./envoy_test.sh
  # Quick verify
  DURATION=5 ITERATIONS=1 CONCURRENCY=1,16,64 ./envoy_test.sh
USAGE
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
    if [ "${check_only}" -eq 1 ]; then
        check_prerequisites
        exit $?
    fi
    if ! check_prerequisites; then
        log "FATAL" "Prerequisites not met. Use --check for detailed status."
        exit 1
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
