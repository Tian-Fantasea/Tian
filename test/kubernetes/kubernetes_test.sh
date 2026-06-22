#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="kubernetes"
SOFTWARE_VERSION="${VERSION:-1.33.12}"
SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"

MINIMUM_POD_STARTUP_P99_MS=5000
MAXIMUM_API_MUTATING_P99_MS=1000
MINIMUM_SCHEDULER_THROUGHPUT=100
MAXIMUM_P50_LATENCY_MS=200
DATA_SCALE="${DATA_SCALE:-1}"
DATA_SIZE="${DATA_SIZE:-100}"
ITERATIONS="${ITERATIONS:-1}"
KIND_CLUSTER_NAME="arm64-perf-test"
KUBECONFIG_PATH="${RESULTS_DIR}/kubeconfig"

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

    local kubectl_found=0
    if command -v kubectl >/dev/null 2>&1; then kubectl_found=1; fi
    if [ -x "${SCRIPT_DIR}/kubectl" ]; then kubectl_found=1; fi
    if [ "${kubectl_found}" -eq 0 ]; then
        log "ERROR" "kubectl is not installed. Please install kubectl v${SOFTWARE_VERSION} for ARM64."
        log "ERROR" "  Download: https://dl.k8s.io/release/v${SOFTWARE_VERSION}/bin/linux/arm64/kubectl"
        errors=$((errors + 1))
    else
        log "CHECK" "kubectl OK"
    fi

    local kind_found=0
    if command -v kind >/dev/null 2>&1; then kind_found=1; fi
    if [ -x "${SCRIPT_DIR}/kind" ]; then kind_found=1; fi
    if [ "${kind_found}" -eq 0 ]; then
        log "ERROR" "kind is not installed. Please install kind for ARM64."
        log "ERROR" "  Download: https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-arm64"
        errors=$((errors + 1))
    else
        log "CHECK" "kind OK"
    fi

    if ! command -v docker >/dev/null 2>&1 && ! command -v containerd >/dev/null 2>&1; then
        log "ERROR" "Docker or containerd is required for kind. Please install one."
        errors=$((errors + 1))
    else
        log "CHECK" "Container runtime OK"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb kubectl_ver kube_server_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"

    export KUBECONFIG="${KUBECONFIG_PATH}"
    kubectl_ver="$(kubectl version --client 2>/dev/null | grep -o 'GitVersion:"[^"]*"' | head -1 | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    kube_server_ver="$(kubectl version 2>/dev/null | grep -o 'serverVersion.*GitVersion:"[^"]*"' | grep -o 'GitVersion:"[^"]*"' | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"

    local nodes_ready
    nodes_ready="$(kubectl get nodes --no-headers 2>/dev/null | grep -c 'Ready' | tr -d '\n\t' || echo '0')"

    local neon_asimd
    neon_asimd="$(grep -c 'asimd' /proc/cpuinfo 2>/dev/null | tr -d '\n\t' || echo '0')"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${kubectl_ver}" "${kube_server_ver}" "${KIND_CLUSTER_NAME}" "${nodes_ready}" \
        "${DATA_SCALE}" \
        --output "${RESULTS_DIR}/version_info.json" \
        --extra "neon_asimd_available=${neon_asimd}" \
        --extra "install_method=kind" \
        --extra "language=go" \
        --extra "arm64_native=true" \
        --extra "kubeconfig_path=${KUBECONFIG_PATH}"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    export KUBECONFIG="${KUBECONFIG_PATH}"

    log "PHASE3a" "Pod startup latency benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_pod_startup.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}" \
        --kubeconfig "${KUBECONFIG_PATH}"

    log "PHASE3b" "API responsiveness benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_api_latency.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --kubeconfig "${KUBECONFIG_PATH}"

    log "PHASE3c" "Micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --kubeconfig "${KUBECONFIG_PATH}"
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
    if command -v kubectl >/dev/null 2>&1; then found=1; fi
    if [ -x "${SCRIPT_DIR}/kubectl" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: kubectl not installed, skipping install check"
        startSkipping
        return
    fi
    assertTrue "kubectl binary should exist" "[ ${found} -eq 1 ]"
}

testSoftwareVersionMatches() {
    local ver
    ver="$(kubectl version --client 2>/dev/null | grep -o 'GitVersion:"v[^"]*"' | head -1 | sed 's/GitVersion:"//' | sed 's/"//' | tr -d '\n\t' || echo 'unknown')"
    if [ "${ver}" = "unknown" ] || [ -z "${ver}" ]; then
        startSkipping
        return
    fi
    local ver_num
    ver_num="$(echo "${ver}" | sed 's/^v//' | tr -d '\n\t')"
    assertNotNull "Version should not be empty" "${ver_num}"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testClusterIsResponsive() {
    if [ ! -f "${KUBECONFIG_PATH}" ]; then
        startSkipping
        return
    fi
    export KUBECONFIG="${KUBECONFIG_PATH}"
    local result
    result="$(kubectl get nodes 2>&1)"
    local rc=$?
    if [ ${rc} -ne 0 ]; then
        startSkipping
        return
    fi
    assertTrue "kubectl get nodes should succeed" "[ ${rc} -eq 0 ]"
}

testBenchmarkPodStartupProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    assertTrue "Pod startup benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkPodStartupHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkPodStartupLatencyBelowSLO() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_lat
    actual_lat="$(json_max_latency "${bench_file}" p99_latency_ms)"
    echo "[DIAG] Pod startup p99 latency: ${actual_lat} ms (SLO threshold: ${MINIMUM_POD_STARTUP_P99_MS})"
    local meets_slo
    meets_slo="$(json_latency_le "${bench_file}" "${MINIMUM_POD_STARTUP_P99_MS}" p99_latency_ms results 0)"
    assertTrue "Pod startup p99 latency should be <= ${MINIMUM_POD_STARTUP_P99_MS}ms (Kubernetes SLO)" "[ '${meets_slo}' = '1' ]"
}

testBenchmarkPodStartupP50LatencyAcceptable() {
    local bench_file="${RESULTS_DIR}/benchmark_pod_startup.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local p50_lat
    p50_lat="$(json_get "${bench_file}" results 0 p50_latency_ms)"
    echo "[DIAG] Pod startup p50 latency: ${p50_lat} ms (threshold: ${MAXIMUM_P50_LATENCY_MS})"
    assertNotNull "p50 latency should not be empty" "${p50_lat}"
}

testBenchmarkApiLatencyProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    assertTrue "API latency benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testBenchmarkApiLatencyHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_field_exists "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkApiLatencyMutatingBelowSLO() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_latency
    has_latency="$(json_latency_le "${bench_file}" "${MAXIMUM_API_MUTATING_P99_MS}" p99_latency_ms results 0)"
    local actual_lat
    actual_lat="$(json_get "${bench_file}" results 0 p99_latency_ms)"
    echo "[DIAG] API mutating p99 latency: ${actual_lat} ms (SLO threshold: ${MAXIMUM_API_MUTATING_P99_MS})"
    assertTrue "API mutating call p99 latency should be <= ${MAXIMUM_API_MUTATING_P99_MS}ms (Kubernetes SLO)" "[ '${has_latency}' = '1' ]"
}

testBenchmarkApiLatencyReadOnlyBelowSLO() {
    local bench_file="${RESULTS_DIR}/benchmark_api_latency.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local read_p99
    read_p99="$(json_get "${bench_file}" results 1 p99_latency_ms)"
    echo "[DIAG] API read-only p99 latency: ${read_p99} ms"
    assertNotNull "Read-only API latency should have data" "${read_p99}"
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
    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -ge 3 ]"
}

testBenchmarkMicroSchedulerThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_SCHEDULER_THROUGHPUT}" throughput pods_per_sec results 0)"
    local actual_tp
    actual_tp="$(json_avg_throughput "${bench_file}" throughput_pods_per_sec)"
    echo "[DIAG] Scheduler throughput: ${actual_tp} pods/sec (threshold: ${MINIMUM_SCHEDULER_THROUGHPUT})"
    assertTrue "Scheduler throughput should be >= ${MINIMUM_SCHEDULER_THROUGHPUT} pods/sec" "[ '${has_throughput}' = '1' ]"
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
    local has_pod has_api has_micro
    has_pod="$(json_contains "${agg_file}" pod_startup)"
    has_api="$(json_contains "${agg_file}" api_latency)"
    has_micro="$(json_contains "${agg_file}" micro)"
    assertTrue "Should contain pod_startup data" "[ ${has_pod} -eq 1 ]"
    assertTrue "Should contain api_latency data" "[ ${has_api} -eq 1 ]"
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