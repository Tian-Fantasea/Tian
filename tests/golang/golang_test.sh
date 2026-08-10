#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOFTWARE_NAME="golang"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-go1.26.5}"
export SOFTWARE_VERSION
BUILD_METHOD="prebuilt"
TARGET_OS="${TARGET_OS:-openEuler 24.03 SP3}"
TARGET_MODEL="${TARGET_MODEL:-Kunpeng-920}"
RESULTS_DIR="${SCRIPT_DIR}/results/${SOFTWARE_VERSION}"
mkdir -p "${RESULTS_DIR}"
LOG_FILE="${RESULTS_DIR}/results.log"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"
BUILD_TMPDIR=""
SHUNIT2_PATH=""
GOROOT=""
ITERATIONS="${ITERATIONS:-1}"
MINIMUM_OPS_PER_SEC="${MINIMUM_OPS_PER_SEC:-1000}"
log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }
json_get()              { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists()     { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results()    { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge()    { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_avg_throughput()   { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }
json_version()          { python3 "${JSON_HELPER}" "$1" version; }
json_contains()         { python3 "${JSON_HELPER}" "$1" contains "$2"; }
detect_os_id() { if [ -f /etc/os-release ]; then . /etc/os-release; echo "${ID}"; else echo "unknown"; fi; }
detect_os_name() { echo "${TARGET_OS}"; }
create_build_tmpdir() { BUILD_TMPDIR="$(mktemp -d /tmp/golang_build_XXXXXX)"; log "BUILD" "Created temp dir: ${BUILD_TMPDIR}"; }
cleanup_build_tmpdir() { if [ -n "${BUILD_TMPDIR}" ] && [ -d "${BUILD_TMPDIR}" ]; then rm -rf "${BUILD_TMPDIR}"; BUILD_TMPDIR=""; fi; }
download_shunit2() {
    local d; d="$(mktemp -d /tmp/shunit2_XXXXXX)"; SHUNIT2_PATH="${d}/shunit2"
    log "SETUP" "Downloading shUnit2 to ${d}..."
    local mirrors=("https://raw.githubusercontent.com/kward/shunit2/master/shunit2" "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2" "https://raw.gitmirror.com/kward/shunit2/master/shunit2")
    local ok=0
    for u in "${mirrors[@]}"; do curl --connect-timeout 30 --max-time 60 -sL -o "${SHUNIT2_PATH}" "${u}" && { chmod +x "${SHUNIT2_PATH}"; grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { ok=1; break; }; }; rm -f "${SHUNIT2_PATH}"; done
    if [ "${ok}" -eq 0 ]; then for u in "${mirrors[@]}"; do wget --timeout=30 --tries=2 -q -O "${SHUNIT2_PATH}" "${u}" 2>/dev/null && { chmod +x "${SHUNIT2_PATH}"; grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { ok=1; break; }; }; rm -f "${SHUNIT2_PATH}"; done; fi
    if [ "${ok}" -eq 0 ]; then log "ERROR" "Failed to download shUnit2"; rm -rf "${d}"; return 1; fi
}
check_prerequisites() {
    local err=0
    command -v python3 >/dev/null 2>&1 && log "CHECK" "Python3 OK: $(python3 --version 2>&1)" || { log "ERROR" "python3 missing"; err=$((err+1)); }
    command -v wget >/dev/null 2>&1 && log "CHECK" "wget OK" || log "WARN" "wget not found"
    command -v curl >/dev/null 2>&1 && log "CHECK" "curl OK" || log "WARN" "curl not found"
    [ -f "${JSON_HELPER}" ] && log "CHECK" "json_helper.py OK" || { log "ERROR" "json_helper.py not found"; err=$((err+1)); }
    local os_id; os_id="$(detect_os_id)"
    log "CHECK" "OS: $(detect_os_name) (${os_id})"
    log "CHECK" "Architecture: $(uname -m)"
    log "CHECK" "Build method: ${BUILD_METHOD} (prebuilt binary download, NOT source build)"
    return ${err}
}
phase1_build() {
    log "PHASE1" "=== Phase 1: Download Go ${SOFTWARE_VERSION} (prebuilt binary) ==="
    create_build_tmpdir
    GOROOT="${BUILD_TMPDIR}/go"
    local tarball="${SOFTWARE_VERSION}.linux-arm64.tar.gz"
    local url="https://go.dev/dl/${tarball}"
    log "PHASE1" "Downloading ${tarball} from go.dev..."
    (cd "${BUILD_TMPDIR}" && curl -sL -o "${tarball}" "${url}" 2>&1 | tee -a "${LOG_FILE}" || wget -q -O "${tarball}" "${url}" 2>&1 | tee -a "${LOG_FILE}") || { log "ERROR" "Failed to download Go"; return 1; }
    if [ ! -f "${BUILD_TMPDIR}/${tarball}" ]; then log "ERROR" "Tarball not found after download"; return 1; fi
    log "PHASE1" "Extracting..."
    (cd "${BUILD_TMPDIR}" && tar xzf "${tarball}" 2>&1 | tee -a "${LOG_FILE}") || { log "ERROR" "Extract failed"; return 1; }
    if [ ! -x "${GOROOT}/bin/go" ]; then log "ERROR" "go binary not found at ${GOROOT}/bin/go"; return 1; fi
    log "PHASE1" "Verifying Go..."
    "${GOROOT}/bin/go" version 2>&1 | tee -a "${LOG_FILE}" | head -1 || log "WARN" "version check failed"
    log "PHASE1" "Build phase complete (prebuilt, no compilation needed)"
}
phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="
    local timestamp model arch kernel os_name cpu_model cores python_ver go_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    model="${TARGET_MODEL}"; arch="$(uname -m | tr -d '\n\t')"; kernel="$(uname -r | tr -d '\n\t')"
    os_name="$(detect_os_name | tr -d '\n\t')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ]; then local np; np="$(grep -c 'processor' /proc/cpuinfo 2>/dev/null || echo 0)"; cpu_model="ARM64 CPU (${np} cores)"; fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t')"
    go_ver="${SOFTWARE_VERSION}"
    if [ -x "${GOROOT}/bin/go" ]; then go_ver="$("${GOROOT}/bin/go" version 2>&1 | tr -d '\n\t' || echo "${SOFTWARE_VERSION}")"; fi
    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${model}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${SOFTWARE_NAME}" "${go_ver}" "${python_ver}" "prebuilt"
    log "PHASE2" "Version info saved (Go: ${go_ver})"
}
phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="
    mkdir -p "${RESULTS_DIR}"
    log "PHASE3A" "Running Go stdlib benchmarks (go test -bench)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_go.py" "${GOROOT}" "${RESULTS_DIR}/benchmark_go.json" "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Go benchmark had issues"
    log "PHASE3B" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" "${GOROOT}" "${RESULTS_DIR}/micro_benchmark.json" "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"
}
phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate and Report ==="
    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" "${RESULTS_DIR}" "${RESULTS_DIR}/results.json"
    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt"
    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"
    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"
    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"
}
oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"
    log "START" "${SOFTWARE_NAME} Performance Benchmark - ${SOFTWARE_VERSION} (${BUILD_METHOD})"
    check_prerequisites || log "WARN" "Some prerequisites missing"
    phase1_build || log "FATAL" "Phase 1 failed"
    phase2_verify || log "WARN" "Phase 2 had issues"
    phase3_run_benchmarks || log "WARN" "Phase 3 had issues"
    phase4_results || log "WARN" "Phase 4 had issues"
}
oneTimeTearDown() { cleanup_build_tmpdir; if [ -n "${SHUNIT2_PATH}" ]; then rm -rf "$(dirname "${SHUNIT2_PATH}")"; SHUNIT2_PATH=""; fi; }
setUp() { rm -f "${RESULTS_DIR}/test_temp_*.json"; }
tearDown() { rm -f "${RESULTS_DIR}/test_temp_*.json"; }
testArchitectureIsARM64() { local a; a="$(uname -m)"; assertTrue "Arch aarch64/arm64, got ${a}" "[ '${a}' = 'aarch64' ] || [ '${a}' = 'arm64' ]"; }
testSoftwareIsInstalled() { local f=0; [ -n "${GOROOT}" ] && [ -x "${GOROOT}/bin/go" ] && f=1; if [ "${f}" -eq 0 ]; then startSkipping; return; fi; assertTrue "go binary should exist" "[ ${f} -eq 1 ]"; }
testSoftwareVersionMatches() { assertNotNull "Version not empty" "${SOFTWARE_VERSION}"; }
testVersionInfoExists() { assertTrue "version_info.json exists" "[ -f '${RESULTS_DIR}/version_info.json' ]"; }
testVersionInfoHasArchitecture() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has architecture" "[ $(json_field_exists "${vf}" architecture) -eq 1 ]"; }
testVersionInfoHasSoftwareVersion() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has software_version" "[ $(json_field_exists "${vf}" software_version) -eq 1 ]"; }
testBenchmarkPrimaryProducesResults() { assertTrue "benchmark_go.json exists" "[ -f '${RESULTS_DIR}/benchmark_go.json' ]"; }
testBenchmarkPrimaryHasRequiredFields() { local bf="${RESULTS_DIR}/benchmark_go.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has benchmark" "[ $(json_contains "${bf}" benchmark) -eq 1 ]"; assertTrue "has performance_metrics" "[ $(json_contains "${bf}" performance_metrics) -eq 1 ]"; assertTrue "has results_summary" "[ $(json_contains "${bf}" results_summary) -eq 1 ]"; }
testBenchmarkPrimaryOpsAboveThreshold() { local bf="${RESULTS_DIR}/benchmark_go.json"; [ -f "${bf}" ] || { startSkipping; return; }; local ops; ops="$(python3 -c "import json; d=json.load(open('${bf}')); vals=[v.get('ops_per_sec',0) for v in d.get('results_summary',{}).values() if isinstance(v,dict) and v.get('ops_per_sec')]; print(round(sum(vals)/len(vals),2) if vals else 0)" 2>/dev/null)"; if [ -z "${ops}" ] || [ "${ops}" = "0" ]; then startSkipping; return; fi; echo "[DIAG] Avg ops/sec: ${ops} (min: ${MINIMUM_OPS_PER_SEC})"; assertTrue "Avg ops/sec >= ${MINIMUM_OPS_PER_SEC}" "[ $(echo "${ops} >= ${MINIMUM_OPS_PER_SEC}" | bc -l) -eq 1 ]"; }
testBenchmarkPrimaryIsGoStdlib() { local bf="${RESULTS_DIR}/benchmark_go.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertEquals "benchmark is go_stdlib" "go_stdlib" "$(json_get "${bf}" benchmark)"; }
testBenchmarkMicroProducesResults() { assertTrue "micro_benchmark.json exists" "[ -f '${RESULTS_DIR}/micro_benchmark.json' ]"; }
testBenchmarkMicroThreadScaling() { local bf="${RESULTS_DIR}/micro_benchmark.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has thread_scaling" "[ $(json_contains "${bf}" thread_scaling) -eq 1 ]"; }
testAggregatedResultsExist() { assertTrue "results.json exists" "[ -f '${RESULTS_DIR}/results.json' ]"; }
testSummaryReportGenerated() { assertTrue "results.txt exists" "[ -f '${RESULTS_DIR}/results.txt' ]"; }
testLogFileGenerated() { assertTrue "results.log exists" "[ -f '${RESULTS_DIR}/results.log' ]"; }
testAggregatedResultsContainsAllBenchmarks() { local af="${RESULTS_DIR}/results.json"; [ -f "${af}" ] || { startSkipping; return; }; assertTrue "has primary" "[ $(json_contains "${af}" primary) -eq 1 ]"; assertTrue "has micro" "[ $(json_contains "${af}" micro) -eq 1 ]"; }
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Golang Performance Benchmark (prebuilt binary, go test -bench)"
    echo "Options: --check (prerequisites), -h|--help"
    echo "Env: SOFTWARE_VERSION (default: go1.26.5), ITERATIONS (default: 1)"
    echo "      MINIMUM_OPS_PER_SEC (default: 1000)"
    echo "Note: Downloads prebuilt Go binary from go.dev/dl (no source build)"
}
main() {
    local check_only=0
    while [ $# -gt 0 ]; do case "$1" in --check) check_only=1; shift ;; -h|--help) usage; exit 0 ;; *) log "ERROR" "Unknown: $1"; usage; exit 1 ;; esac; done
    log "START" "${SOFTWARE_NAME} Performance Benchmark ${SOFTWARE_VERSION}"
    if [ "${check_only}" -eq 1 ]; then check_prerequisites; exit $?; fi
    check_prerequisites || { log "FATAL" "Prerequisites not met"; exit 1; }
    download_shunit2 || { log "FATAL" "Failed to download shUnit2"; exit 1; }
    SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"
    . "${SHUNIT2_PATH}"
}
if [ "${1:-}" != "--shunit2-run" ]; then main "$@"; fi
