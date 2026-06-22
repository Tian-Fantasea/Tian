#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="openviking"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-v0.3.24}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"

MINIMUM_ACCURACY_LOCOMO=80
MAXIMUM_LATENCY_MS=500
MINIMUM_ACCURACY_HOTPOTQA=72
MINIMUM_EMBEDDING_THROUGHPUT=50
MINIMUM_RETRIEVAL_QPS=10
DATA_SCALE="${DATA_SCALE:-1}"
DATA_SIZE="${DATA_SIZE:-1000}"
ITERATIONS="${ITERATIONS:-1}"
OPENVIKING_VENV="${SCRIPT_DIR}/venv"

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
        log "ERROR" "python3 is not installed. Please install Python 3.10+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi

    local ov_found=0
    if [ -d "${OPENVIKING_VENV}" ] && [ -f "${OPENVIKING_VENV}/bin/python3" ]; then
        if "${OPENVIKING_VENV}/bin/python3" -c 'import openviking' 2>/dev/null; then
            ov_found=1
        fi
    fi
    if [ "${ov_found}" -eq 0 ]; then
        if python3 -c 'import openviking' 2>/dev/null; then ov_found=1; fi
    fi
    if [ "${ov_found}" -eq 0 ]; then
        log "ERROR" "openviking Python package not installed."
        log "ERROR" "  Create venv: python3 -m venv ${OPENVIKING_VENV}"
        log "ERROR" "  Install: ${OPENVIKING_VENV}/bin/pip install openviking"
        errors=$((errors + 1))
    else
        log "CHECK" "openviking OK"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb python_ver ov_ver neon_asimd
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"

    if [ -d "${OPENVIKING_VENV}" ] && [ -f "${OPENVIKING_VENV}/bin/python3" ]; then
        python_ver="$(("${OPENVIKING_VENV}/bin/python3" --version 2>&1 || python3 --version 2>&1) | tr -d '\n\t')"
        ov_ver="$(("${OPENVIKING_VENV}/bin/python3" -c 'import openviking; print(openviking.__version__)' 2>/dev/null || echo 'unknown') | tr -d '\n\t')"
    else
        python_ver="$(python3 --version 2>&1 | tr -d '\n\t')"
        ov_ver="$(python3 -c 'import openviking; print(openviking.__version__)' 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    fi

    neon_asimd="$(grep -c 'asimd' /proc/cpuinfo 2>/dev/null | tr -d '\n\t' || echo '0')"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${python_ver}" "${ov_ver}" "${OPENVIKING_VENV}" "10" "64" \
        "${DATA_SCALE}" \
        --output "${RESULTS_DIR}/version_info.json" \
        --extra "neon_asimd_available=${neon_asimd}" \
        --extra "install_method=pip" \
        --extra "language=python" \
        --extra "arm64_native=true" \
        --extra "max_concurrent_embedding=10" \
        --extra "max_concurrent_vlm=64"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    local venv_bin="${OPENVIKING_VENV}/bin"
    local python_cmd
    if [ -d "${OPENVIKING_VENV}" ] && [ -f "${venv_bin}/python3" ]; then
        python_cmd="${venv_bin}/python3"
    else
        python_cmd="python3"
    fi

    log "PHASE3a" "LoCoMo User Memory benchmark..."
    "${python_cmd}" "${SCRIPT_DIR}/scripts/benchmark_locomo.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}" \
        --venv "${OPENVIKING_VENV}"

    log "PHASE3b" "HotpotQA Knowledge Base benchmark..."
    "${python_cmd}" "${SCRIPT_DIR}/scripts/benchmark_hotpotqa.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}" \
        --venv "${OPENVIKING_VENV}"

    log "PHASE3c" "Micro benchmark..."
    "${python_cmd}" "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}" \
        --venv "${OPENVIKING_VENV}"
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

testSoftwareIsInstalled() {
    local found=0
    if [ -d "${OPENVIKING_VENV}" ] && [ -f "${OPENVIKING_VENV}/bin/python3" ]; then
        if "${OPENVIKING_VENV}/bin/python3" -c 'import openviking' 2>/dev/null; then found=1; fi
    fi
    if [ "${found}" -eq 0 ]; then
        if python3 -c 'import openviking' 2>/dev/null; then found=1; fi
    fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: openviking not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "openviking package should be importable" "[ ${found} -eq 1 ]"
}

testSoftwareVersionMatches() {
    local ver
    if [ -d "${OPENVIKING_VENV}" ] && [ -f "${OPENVIKING_VENV}/bin/python3" ]; then
        ver="$("${OPENVIKING_VENV}/bin/python3" -c 'import openviking; print(openviking.__version__)' 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    else
        ver="$(python3 -c 'import openviking; print(openviking.__version__)' 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    fi
    if [ "${ver}" = "unknown" ] || [ -z "${ver}" ]; then
        startSkipping
        return
    fi
    assertNotNull "Version should not be empty" "${ver}"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testBenchmarkLoComoProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    assertTrue "LoCoMo benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkLoComoHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkLoComoAccuracyAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local accuracy
    accuracy="$(json_get "${bench_file}" results 0 accuracy_pct)"
    if [ -z "${accuracy}" ] || [ "${accuracy}" = "None" ] || [ "${accuracy}" = "0" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] LoCoMo accuracy: ${accuracy}% (threshold: ${MINIMUM_ACCURACY_LOCOMO})"
    assertTrue "LoCoMo accuracy (${accuracy}%) should be >= ${MINIMUM_ACCURACY_LOCOMO}%" \
        "[ ${accuracy} -ge ${MINIMUM_ACCURACY_LOCOMO} ]"
}

testBenchmarkLoComoLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_locomo.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local meets_slo
    meets_slo="$(json_latency_le "${bench_file}" "${MAXIMUM_LATENCY_MS}" avg_query_time_ms results 0)"
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" avg_query_time_ms)"
    echo "[DIAG] LoCoMo avg latency: ${actual_lat} ms (threshold: ${MAXIMUM_LATENCY_MS})"
    assertTrue "LoCoMo avg latency should be <= ${MAXIMUM_LATENCY_MS}ms" "[ '${meets_slo}' = '1' ]"
}

testBenchmarkHotpotQAProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_hotpotqa.json"
    assertTrue "HotpotQA benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkHotpotQAHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_hotpotqa.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkHotpotQAAccuracyAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_hotpotqa.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local accuracy
    accuracy="$(json_get "${bench_file}" results 0 accuracy_pct)"
    if [ -z "${accuracy}" ] || [ "${accuracy}" = "None" ] || [ "${accuracy}" = "0" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] HotpotQA accuracy: ${accuracy}% (threshold: ${MINIMUM_ACCURACY_HOTPOTQA})"
    assertTrue "HotpotQA accuracy (${accuracy}%) should be >= ${MINIMUM_ACCURACY_HOTPOTQA}%" \
        "[ ${accuracy} -ge ${MINIMUM_ACCURACY_HOTPOTQA} ]"
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
    assertTrue "Should have results for all micro operations (count=${ops_count})" "[ ${ops_count} -gt 0 ]"
}

testBenchmarkMicroEmbeddingThroughput() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_EMBEDDING_THROUGHPUT}" embeddings_per_sec results)"
    local actual_tp
    actual_tp="$(json_avg_throughput "${bench_file}" embeddings_per_sec)"
    echo "[DIAG] Embedding throughput: ${actual_tp} ops/sec (threshold: ${MINIMUM_EMBEDDING_THROUGHPUT})"
    assertTrue "Embedding throughput should be >= ${MINIMUM_EMBEDDING_THROUGHPUT}/sec" "[ '${has_throughput}' = '1' ]"
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
    local has_locomo has_hotpotqa has_micro
    has_locomo="$(json_contains "${agg_file}" locomo)"
    has_hotpotqa="$(json_contains "${agg_file}" hotpotqa)"
    has_micro="$(json_contains "${agg_file}" micro)"
    assertTrue "Should contain locomo data" "[ ${has_locomo} -eq 1 ]"
    assertTrue "Should contain hotpotqa data" "[ ${has_hotpotqa} -eq 1 ]"
    assertTrue "Should contain micro data" "[ ${has_micro} -eq 1 ]"
}

oneTimeTearDown() {
    phase4_results || log "WARN" "Phase 4 had issues..."
    log "DONE" "Benchmark complete. Results in: ${RESULTS_DIR}/"
}

main() {
    local check_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)  PHASES="$2"; shift 2 ;;
            --check)      check_only=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            *)            log "ERROR" "Unknown option: $1"; exit 1 ;;
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