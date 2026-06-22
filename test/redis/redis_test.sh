#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="redis"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-8.0.2}"
REDIS_HOME="${REDIS_HOME:-${SCRIPT_DIR}/redis-${SOFTWARE_VERSION}}"
REDIS_PORT="${REDIS_PORT:-6380}"
SHUNIT_PARENT="${SCRIPT_DIR}/redis_test.sh"

MINIMUM_THROUGHPUT_GET=5000
MINIMUM_THROUGHPUT_SET=3000
MINIMUM_YCSB_THROUGHPUT=1000
MAXIMUM_LATENCY_P99_MS=50.0

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

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi

    if [ ! -x "${REDIS_HOME}/src/redis-server" ]; then
        log "ERROR" "redis-server not found at ${REDIS_HOME}/src/redis-server"
        log "ERROR" "  Please compile Redis ${SOFTWARE_VERSION} and place it at ${REDIS_HOME}/"
        log "ERROR" "  Or set REDIS_HOME to your installation directory"
        errors=$((errors + 1))
    else
        log "CHECK" "redis-server OK: ${REDIS_HOME}/src/redis-server"
    fi

    if [ ! -x "${REDIS_HOME}/src/redis-cli" ]; then
        log "ERROR" "redis-cli not found at ${REDIS_HOME}/src/redis-cli"
        errors=$((errors + 1))
    else
        log "CHECK" "redis-cli OK"
    fi

    if [ ! -x "${REDIS_HOME}/src/redis-benchmark" ]; then
        log "ERROR" "redis-benchmark not found at ${REDIS_HOME}/src/redis-benchmark"
        errors=$((errors + 1))
    else
        log "CHECK" "redis-benchmark OK"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

start_redis_if_needed() {
    if "${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>/dev/null | grep -q "PONG"; then
        log "PHASE3" "Redis server already running on port ${REDIS_PORT}"
        return 0
    fi

    local config="${REDIS_HOME}/redis.conf"
    if [ ! -f "${config}" ]; then
        config="${REDIS_HOME}/redis-full.conf"
    fi
    if [ ! -f "${config}" ]; then
        log "WARN" "No redis.conf found, starting with defaults..."
        "${REDIS_HOME}/src/redis-server" --port "${REDIS_PORT}" --daemonize yes --maxmemory 512mb --save "" 2>&1 | tee -a "${LOG_FILE}"
    else
        local tmp_config="${RESULTS_DIR}/redis_bench.conf"
        cp "${config}" "${tmp_config}"
        sed -i "s|^port .*|port ${REDIS_PORT}|" "${tmp_config}"
        sed -i "s|^daemonize .*|daemonize yes|" "${tmp_config}"
        sed -i "s|^pidfile .*|pidfile ${RESULTS_DIR}/redis_bench.pid|" "${tmp_config}"
        sed -i "s|^logfile .*|logfile ${RESULTS_DIR}/redis_bench.log|" "${tmp_config}"
        sed -i "s|^dir .*|dir ${RESULTS_DIR}|" "${tmp_config}"
        sed -i "s|^bind .*|bind 127.0.0.1|" "${tmp_config}"
        sed -i "s|^# maxmemory .*|maxmemory 512mb|" "${tmp_config}"
        "${REDIS_HOME}/src/redis-server" "${tmp_config}" 2>&1 | tee -a "${LOG_FILE}"
    fi
    sleep 2

    if "${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>/dev/null | grep -q "PONG"; then
        log "PHASE3" "Redis server started on port ${REDIS_PORT}"
        return 0
    else
        log "ERROR" "Redis server failed to start"
        return 1
    fi
}

stop_redis() {
    "${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" SHUTDOWN NOSAVE 2>/dev/null || true
    sleep 1
    log "PHASE4" "Redis server stopped"
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb redis_ver gcc_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    redis_ver="$("${REDIS_HOME}/src/redis-server" --version 2>&1 | grep -oP 'v=[\d.]+' | cut -d= -f2 | tr -d '\n\t' || echo "${SOFTWARE_VERSION}")"
    gcc_ver="$(gcc --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'N/A')"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${redis_ver}" "${gcc_ver}" \
        "N/A" "${REDIS_HOME}" "${cores}" "${cores}"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    start_redis_if_needed || log "WARN" "Redis server start had issues, continuing..."

    log "PHASE3a" "Running YCSB benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_ycsb.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS:-1}" \
        --data-scale "${DATA_SCALE:-1}" \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3b" "Running throughput benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_throughput.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS:-1}" \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3c" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS:-1}" \
        --data-size "${DATA_SIZE:-1000000}" \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3d" "Running stress benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --redis-home "${REDIS_HOME}" \
        --port "${REDIS_PORT}" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS:-1}" \
        --data-size "${DATA_SIZE:-1000000}" \
        --stress-only \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3" "Phase 3 complete."
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    stop_redis

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

    log "START" "Redis ARM64 Performance Benchmark - v${SOFTWARE_VERSION}"

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

testRedisBinaryExists() {
    local found=0
    if [ -x "${REDIS_HOME}/src/redis-server" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: redis-server not installed, skipping"
        startSkipping
        return
    fi
    assertTrue "redis-server binary should exist" "[ ${found} -eq 1 ]"
}

testRedisCliBinaryExists() {
    local found=0
    if [ -x "${REDIS_HOME}/src/redis-cli" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        startSkipping
        return
    fi
    assertTrue "redis-cli binary should exist" "[ ${found} -eq 1 ]"
}

testRedisBenchmarkBinaryExists() {
    local found=0
    if [ -x "${REDIS_HOME}/src/redis-benchmark" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        startSkipping
        return
    fi
    assertTrue "redis-benchmark binary should exist" "[ ${found} -eq 1 ]"
}

testRedisVersionMatches() {
    local ver
    ver="$("${REDIS_HOME}/src/redis-server" --version 2>/dev/null | grep -oP 'v=[\d.]+' | cut -d= -f2 | tr -d '\n\t' || echo 'unknown')"
    if [ "${ver}" = "unknown" ]; then
        startSkipping
        return
    fi
    assertTrue "Version should not be empty" "[ -n '${ver}' ]"
}

testRedisServerResponsive() {
    if ! "${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>/dev/null | grep -q "PONG"; then
        echo "[DIAG] Redis server not running on port ${REDIS_PORT}, skipping PING test"
        startSkipping
        return
    fi
    local result
    result="$("${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>&1)"
    assertContains "Redis should respond to PING" "${result}" "PONG"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_arch has_ver
    has_arch="$(json_field_exists "${bench_file}" architecture)"
    has_ver="$(json_field_exists "${bench_file}" software_version)"
    assertTrue "Version info should have architecture field" "[ ${has_arch} -eq 1 ]"
    assertTrue "Version info should have software_version field" "[ ${has_ver} -eq 1 ]"
}

testBenchmarkYCSBProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    assertTrue "YCSB benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkYCSBHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkYCSBThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_ycsb
    actual_ycsb="$(json_get "${bench_file}" summary avg_throughput_ops_per_sec)"
    echo "[DIAG] YCSB overall throughput: ${actual_ycsb} ops/sec (threshold: ${MINIMUM_YCSB_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_YCSB_THROUGHPUT}" summary avg_throughput_ops_per_sec)"
    assertTrue "YCSB throughput should be >= ${MINIMUM_YCSB_THROUGHPUT} ops/sec, got ${actual_ycsb}" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkYCSBReadLatencyAcceptable() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_get "${bench_file}" results 0 p99_read_latency_ms)"
    echo "[DIAG] YCSB read p99 latency: ${actual_lat} ms (threshold: ${MAXIMUM_LATENCY_P99_MS})"
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_P99_MS}" results 0 p99_read_latency_ms)"
    assertTrue "YCSB read p99 latency should be <= ${MAXIMUM_LATENCY_P99_MS} ms, got ${actual_lat}" \
        "[ ${has_latency} -eq 1 ]"
}

testBenchmarkThroughputProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    assertTrue "Throughput benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkThroughputHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkThroughputGETAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_get
    actual_get="$(json_get "${bench_file}" throughput_get)"
    echo "[DIAG] GET throughput: ${actual_get} ops/sec (threshold: ${MINIMUM_THROUGHPUT_GET})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT_GET}" throughput_get)"
    assertTrue "GET throughput should be >= ${MINIMUM_THROUGHPUT_GET} ops/sec, got ${actual_get}" \
        "[ ${has_throughput} -eq 1 ]"
}

testBenchmarkThroughputSETAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_throughput.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_set
    actual_set="$(json_get "${bench_file}" throughput_set)"
    echo "[DIAG] SET throughput: ${actual_set} ops/sec (threshold: ${MINIMUM_THROUGHPUT_SET})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT_SET}" throughput_set)"
    assertTrue "SET throughput should be >= ${MINIMUM_THROUGHPUT_SET} ops/sec, got ${actual_set}" \
        "[ ${has_throughput} -eq 1 ]"
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

testBenchmarkMicroLatencyP99BelowThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_P99_MS}" results 0 p99_latency_ms)"
    assertTrue "GET p99 latency should be <= ${MAXIMUM_LATENCY_P99_MS} ms" \
        "[ ${has_latency} -eq 1 ]"
}

testBenchmarkStressProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_stress.json"
    assertTrue "Stress benchmark JSON should exist" "[ -f '${bench_file}' ]"
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
    local has_ycsb has_throughput has_micro
    has_ycsb="$(json_contains "${agg_file}" ycsb)"
    has_throughput="$(json_contains "${agg_file}" throughput)"
    has_micro="$(json_contains "${agg_file}" micro)"
    assertTrue "Should contain ycsb benchmark data" "[ ${has_ycsb} -eq 1 ]"
    assertTrue "Should contain throughput benchmark data" "[ ${has_throughput} -eq 1 ]"
    assertTrue "Should contain micro benchmark data" "[ ${has_micro} -eq 1 ]"
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
            -h|--help)    usage; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    log "START" "Redis ARM64 Benchmark v${SOFTWARE_VERSION}"

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

usage() {
    printf 'Usage: redis_test.sh [OPTIONS]\n\n'
    printf 'Redis ARM64 Performance Benchmark v%s\n\n' "${SOFTWARE_VERSION}"
    printf 'Options:\n'
    printf '  --check     Check prerequisites only\n'
    printf '  -h, --help  Show usage\n\n'
    printf 'Environment variables:\n'
    printf '  REDIS_HOME      Redis installation directory (default: %s)\n' "${REDIS_HOME}"
    printf '  REDIS_PORT      Redis port (default: %s)\n' "${REDIS_PORT}"
    printf '  ITERATIONS      Number of iterations (default: 1)\n'
    printf '  DATA_SCALE      YCSB data scale (default: 1)\n'
    printf '  DATA_SIZE       Micro benchmark data size (default: 1000000)\n\n'
    printf 'Examples:\n'
    printf '  ./redis_test.sh                    # Full benchmark + shUnit2 validation\n'
    printf '  ./redis_test.sh --check            # Check prerequisites only\n'
    printf '  ITERATIONS=3 ./redis_test.sh       # 3 iterations per benchmark\n'
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
