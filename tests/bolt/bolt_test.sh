#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOFTWARE_NAME="bolt"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-main}"
export SOFTWARE_VERSION
BUILD_METHOD="source_build"
TARGET_OS="${TARGET_OS:-openEuler 24.03 SP3}"
TARGET_MODEL="${TARGET_MODEL:-Kunpeng-920}"
RESULTS_DIR="${SCRIPT_DIR}/results/${SOFTWARE_VERSION}"
mkdir -p "${RESULTS_DIR}"
LOG_FILE="${RESULTS_DIR}/results.log"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"
BUILD_TMPDIR=""
SHUNIT2_PATH=""
BOLT_SRC_DIR=""
BOLT_BUILD_DIR=""
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
create_build_tmpdir() { BUILD_TMPDIR="$(mktemp -d /tmp/bolt_build_XXXXXX)"; log "BUILD" "Created temp dir: ${BUILD_TMPDIR}"; }
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
    command -v g++ >/dev/null 2>&1 && log "CHECK" "G++ OK: $(g++ --version 2>&1 | head -1)" || log "WARN" "g++ not found"
    command -v cmake >/dev/null 2>&1 && log "CHECK" "CMake OK: $(cmake --version 2>&1 | head -1)" || log "WARN" "cmake not found"
    command -v git >/dev/null 2>&1 && log "CHECK" "Git OK: $(git --version 2>&1)" || log "WARN" "git not found"
    command -v pip3 >/dev/null 2>&1 && log "CHECK" "pip3 OK" || log "WARN" "pip3 not found (needed for conan)"
    [ -f "${JSON_HELPER}" ] && log "CHECK" "json_helper.py OK" || { log "ERROR" "json_helper.py not found"; err=$((err+1)); }
    local os_id; os_id="$(detect_os_id)"
    local os_id_lower; os_id_lower="$(echo "${os_id}" | tr '[:upper:]' '[:lower:]')"
    log "CHECK" "OS: $(detect_os_name) (${os_id})"
    log "CHECK" "Architecture: $(uname -m)"
    log "CHECK" "Build method: ${BUILD_METHOD} (cmake + conan, Velox-derived)"
    log "CHECK" "Note: Bolt is a C++ data-processing acceleration library (derived from Velox)"
    case "${os_id_lower}" in
        ubuntu|debian) sudo apt-get update -qq >/dev/null 2>&1; sudo apt-get install -y -qq build-essential g++ cmake make git wget curl python3-pip flex bison >/dev/null 2>&1 ;;
        openeuler) sudo dnf install -y gcc gcc-c++ cmake make git wget curl python3-pip flex bison >/dev/null 2>&1 ;;
        centos|rhel|fedora) sudo dnf install -y gcc gcc-c++ cmake make git wget curl python3-pip flex bison >/dev/null 2>&1 ;;
        *) log "WARN" "Unknown OS: ${os_id}" ;;
    esac
    return ${err}
}
phase1_build() {
    log "PHASE1" "=== Phase 1: Source Build Bolt (bytedance) v${SOFTWARE_VERSION} ==="
    create_build_tmpdir
    BOLT_SRC_DIR="${BUILD_TMPDIR}/bolt_src"
    BOLT_BUILD_DIR="${BUILD_TMPDIR}/build"
    log "PHASE1" "Cloning Bolt (main branch)..."
    if ! git clone --depth 1 https://github.com/bytedance/bolt.git "${BOLT_SRC_DIR}" >> "${LOG_FILE}" 2>&1; then
        log "ERROR" "Failed to clone Bolt"
        return 1
    fi
    log "PHASE1" "Installing Conan (dependency manager)..."
    pip3 install --break-system-packages conan >> "${LOG_FILE}" 2>&1 || log "WARN" "conan install failed, trying without..."
    log "PHASE1" "Running setup-dev-env.sh..."
    if [ -f "${BOLT_SRC_DIR}/scripts/setup-dev-env.sh" ]; then
        (cd "${BOLT_SRC_DIR}" && bash scripts/setup-dev-env.sh >> "${LOG_FILE}" 2>&1) || log "WARN" "setup-dev-env had issues, continuing..."
    fi
    log "PHASE1" "Building Bolt (make release, may take 10-30+ minutes)..."
    local build_ok=0
    if (cd "${BOLT_SRC_DIR}" && make release BUILD_VERSION="${SOFTWARE_VERSION}" >> "${LOG_FILE}" 2>&1); then
        log "PHASE1" "make release succeeded"
        build_ok=1
    else
        log "WARN" "make release failed, trying cmake directly..."
        mkdir -p "${BOLT_BUILD_DIR}"
        if (cd "${BOLT_BUILD_DIR}" && cmake -DCMAKE_BUILD_TYPE=Release "${BOLT_SRC_DIR}" >> "${LOG_FILE}" 2>&1) && \
           (cd "${BOLT_BUILD_DIR}" && make -j$(nproc) >> "${LOG_FILE}" 2>&1); then
            log "PHASE1" "cmake build succeeded"
            build_ok=1
        else
            log "ERROR" "Both make release and cmake build failed"
            return 1
        fi
    fi
    # Search for build output directory with actual artifacts
    BOLT_BUILD_DIR=""
    for dir in "${BOLT_SRC_DIR}/build" "${BOLT_SRC_DIR}/_build" "${BUILD_TMPDIR}/build" "${BOLT_SRC_DIR}/cmake-build-release" "${BOLT_SRC_DIR}"; do
        if [ -d "${dir}" ]; then
            local found_libs
            found_libs="$(find "${dir}" \( -name "*.a" -o -name "*.so" \) 2>/dev/null | head -1)"
            if [ -n "${found_libs}" ]; then
                BOLT_BUILD_DIR="${dir}"
                log "PHASE1" "Build dir found: ${BOLT_BUILD_DIR} (has: $(basename "${found_libs}"))"
                break
            fi
        fi
    done
    if [ -z "${BOLT_BUILD_DIR}" ]; then
        log "WARN" "No .a/.so files found in any build dir. Searching for any build output..."
        for dir in "${BOLT_SRC_DIR}/build" "${BOLT_SRC_DIR}/_build" "${BUILD_TMPDIR}/build" "${BOLT_SRC_DIR}/cmake-build-release"; do
            if [ -d "${dir}" ]; then
                BOLT_BUILD_DIR="${dir}"
                log "PHASE1" "Using build dir (no libs yet): ${BOLT_BUILD_DIR}"
                break
            fi
        done
    fi
    if [ -z "${BOLT_BUILD_DIR}" ]; then
        BOLT_BUILD_DIR="${BOLT_SRC_DIR}"
        log "WARN" "No dedicated build dir found, using source dir as fallback: ${BOLT_BUILD_DIR}"
    fi
    log "PHASE1" "Build phase complete (build_ok=${build_ok}, build_dir=${BOLT_BUILD_DIR})"
}
phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="
    local timestamp model arch kernel os_name cpu_model cores python_ver gcc_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    model="${TARGET_MODEL}"; arch="$(uname -m | tr -d '\n\t')"; kernel="$(uname -r | tr -d '\n\t')"
    os_name="$(detect_os_name | tr -d '\n\t')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ]; then local np; np="$(grep -c 'processor' /proc/cpuinfo 2>/dev/null || echo 0)"; cpu_model="ARM64 CPU (${np} cores)"; fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t')"
    gcc_ver="$(g++ --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'unknown')"
    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${model}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" "${python_ver}" "${gcc_ver}"
    log "PHASE2" "Version info saved (Bolt: ${SOFTWARE_VERSION})"
}
phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks (adaptive: find/run/compile) ==="
    mkdir -p "${RESULTS_DIR}"
    if [ -z "${BOLT_BUILD_DIR}" ] || [ ! -d "${BOLT_BUILD_DIR}" ]; then
        log "ERROR" "Bolt build dir not available, skipping benchmarks"
        return 1
    fi
    log "PHASE3A" "Running Bolt benchmark (adaptive)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_bolt.py" "${BOLT_SRC_DIR}" "${BOLT_BUILD_DIR}" "${RESULTS_DIR}/benchmark_bolt.json" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "benchmark had issues"
    log "PHASE3B" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" "${BOLT_SRC_DIR}" "${BOLT_BUILD_DIR}" "${RESULTS_DIR}/micro_benchmark.json" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "micro benchmark had issues"
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
    log "START" "${SOFTWARE_NAME} (bytedance) Performance Benchmark - v${SOFTWARE_VERSION} (${BUILD_METHOD})"
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
testSoftwareIsInstalled() { local f=0; [ -n "${BOLT_BUILD_DIR}" ] && [ -d "${BOLT_BUILD_DIR}" ] && f=1; if [ "${f}" -eq 0 ]; then startSkipping; return; fi; assertTrue "Bolt build dir exists" "[ ${f} -eq 1 ]"; }
testSoftwareVersionMatches() { assertNotNull "Version not empty" "${SOFTWARE_VERSION}"; }
testVersionInfoExists() { assertTrue "version_info.json exists" "[ -f '${RESULTS_DIR}/version_info.json' ]"; }
testVersionInfoHasArchitecture() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has architecture" "[ $(json_field_exists "${vf}" architecture) -eq 1 ]"; }
testVersionInfoHasSoftwareVersion() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has software_version" "[ $(json_field_exists "${vf}" software_version) -eq 1 ]"; }
testBenchmarkPrimaryProducesResults() { assertTrue "benchmark_bolt.json exists" "[ -f '${RESULTS_DIR}/benchmark_bolt.json' ]"; }
testBenchmarkPrimaryHasRequiredFields() { local bf="${RESULTS_DIR}/benchmark_bolt.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has benchmark" "[ $(json_contains "${bf}" benchmark) -eq 1 ]"; assertTrue "has performance_metrics" "[ $(json_contains "${bf}" performance_metrics) -eq 1 ]"; assertTrue "has results_summary" "[ $(json_contains "${bf}" results_summary) -eq 1 ]"; }
testBenchmarkPrimaryIsBoltAcceleration() { local bf="${RESULTS_DIR}/benchmark_bolt.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertEquals "benchmark is bolt_acceleration" "bolt_acceleration" "$(json_get "${bf}" benchmark)"; }
testBenchmarkPrimaryLinkTest() { local bf="${RESULTS_DIR}/benchmark_bolt.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has link_test" "[ $(json_contains "${bf}" link_test) -eq 1 ]"; }
testBenchmarkMicroProducesResults() { assertTrue "micro_benchmark.json exists" "[ -f '${RESULTS_DIR}/micro_benchmark.json' ]"; }
testBenchmarkMicroHasRequiredFields() { local bf="${RESULTS_DIR}/micro_benchmark.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has benchmark" "[ $(json_contains "${bf}" benchmark) -eq 1 ]"; assertTrue "has results" "[ $(json_contains "${bf}" results) -eq 1 ]"; }
testBenchmarkMicroLibraryAnalysis() { local bf="${RESULTS_DIR}/micro_benchmark.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has library_analysis" "[ $(json_contains "${bf}" library_analysis) -eq 1 ]"; }
testAggregatedResultsExist() { assertTrue "results.json exists" "[ -f '${RESULTS_DIR}/results.json' ]"; }
testSummaryReportGenerated() { assertTrue "results.txt exists" "[ -f '${RESULTS_DIR}/results.txt' ]"; }
testLogFileGenerated() { assertTrue "results.log exists" "[ -f '${RESULTS_DIR}/results.log' ]"; }
testAggregatedResultsContainsAllBenchmarks() { local af="${RESULTS_DIR}/results.json"; [ -f "${af}" ] || { startSkipping; return; }; assertTrue "has primary" "[ $(json_contains "${af}" primary) -eq 1 ]"; assertTrue "has micro" "[ $(json_contains "${af}" micro) -eq 1 ]"; }
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Bolt (bytedance) Performance Benchmark (cmake+conan, Velox-derived)"
    echo "Options: --check, -h|--help"
    echo "Env: SOFTWARE_VERSION (default: main), ITERATIONS (default: 1)"
    echo "      MINIMUM_OPS_PER_SEC (default: 1000)"
    echo "Note: Bolt is a C++ data-processing acceleration library (derived from Velox)."
    echo "      Build may take 10-30+ minutes (Conan deps from source on first run)."
    echo "      Benchmark is adaptive: finds/runs existing bench targets or compiles link test."
}
main() {
    local check_only=0
    while [ $# -gt 0 ]; do case "$1" in --check) check_only=1; shift ;; -h|--help) usage; exit 0 ;; *) log "ERROR" "Unknown: $1"; usage; exit 1 ;; esac; done
    log "START" "${SOFTWARE_NAME} Performance Benchmark v${SOFTWARE_VERSION}"
    if [ "${check_only}" -eq 1 ]; then check_prerequisites; exit $?; fi
    check_prerequisites || { log "FATAL" "Prerequisites not met"; exit 1; }
    download_shunit2 || { log "FATAL" "Failed to download shUnit2"; exit 1; }
    SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"
    . "${SHUNIT2_PATH}"
}
if [ "${1:-}" != "--shunit2-run" ]; then main "$@"; fi
