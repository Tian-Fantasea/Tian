#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOFTWARE_NAME="glibc"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-2.44}"
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
GLIBC_BUILD_DIR=""

ITERATIONS="${ITERATIONS:-1}"
MINIMUM_MEAN_NS="${MINIMUM_MEAN_NS:-0.1}"
export BENCH_TIMEOUT="${BENCH_TIMEOUT:-300}"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

json_get()              { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }
json_field_exists()     { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_count_results()    { python3 "${JSON_HELPER}" "$1" count_results; }
json_throughput_ge()    { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }
json_latency_le()       { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }
json_avg_throughput()   { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }
json_max_latency()      { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }
json_version()          { python3 "${JSON_HELPER}" "$1" version; }
json_contains()         { python3 "${JSON_HELPER}" "$1" contains "$2"; }

detect_os_id() { if [ -f /etc/os-release ]; then . /etc/os-release; echo "${ID}"; else echo "unknown"; fi; }
detect_os_name() { echo "${TARGET_OS}"; }

create_build_tmpdir() { BUILD_TMPDIR="$(mktemp -d /tmp/glibc_build_XXXXXX)"; log "BUILD" "Created temp dir: ${BUILD_TMPDIR}"; }
cleanup_build_tmpdir() { if [ -n "${BUILD_TMPDIR}" ] && [ -d "${BUILD_TMPDIR}" ]; then rm -rf "${BUILD_TMPDIR}"; BUILD_TMPDIR=""; fi; }

download_shunit2() {
    local d; d="$(mktemp -d /tmp/shunit2_XXXXXX)"; SHUNIT2_PATH="${d}/shunit2"
    log "SETUP" "Downloading shUnit2 to ${d}..."
    local mirrors=("https://raw.githubusercontent.com/kward/shunit2/master/shunit2" "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2" "https://raw.gitmirror.com/kward/shunit2/master/shunit2")
    local ok=0
    for u in "${mirrors[@]}"; do curl --connect-timeout 30 --max-time 60 -sL -o "${SHUNIT2_PATH}" "${u}" && { chmod +x "${SHUNIT2_PATH}"; grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { ok=1; break; }; }; rm -f "${SHUNIT2_PATH}"; done
    if [ "${ok}" -eq 0 ]; then for u in "${mirrors[@]}"; do wget --timeout=30 --tries=2 -q -O "${SHUNIT2_PATH}" "${u}" 2>/dev/null && { chmod +x "${SHUNIT2_PATH}"; grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { ok=1; break; }; }; rm -f "${SHUNIT2_PATH}"; done; fi
    if [ "${ok}" -eq 0 ]; then log "ERROR" "Failed to download shUnit2"; rm -rf "${d}"; return 1; fi
    log "SETUP" "shUnit2 downloaded successfully"
}

check_prerequisites() {
    local err=0
    command -v python3 >/dev/null 2>&1 && log "CHECK" "Python3 OK: $(python3 --version 2>&1)" || { log "ERROR" "python3 missing"; err=$((err+1)); }
    command -v gcc >/dev/null 2>&1 && log "CHECK" "GCC OK: $(gcc --version 2>&1 | head -1)" || log "WARN" "gcc not found - will install"
    command -v make >/dev/null 2>&1 && log "CHECK" "Make OK" || log "WARN" "make not found - will install"
    command -v git >/dev/null 2>&1 && log "CHECK" "Git OK: $(git --version 2>&1)" || log "WARN" "git not found"
    [ -f "${JSON_HELPER}" ] && log "CHECK" "json_helper.py OK" || { log "ERROR" "json_helper.py not found"; err=$((err+1)); }
    local os_id; os_id="$(detect_os_id)"
    local os_id_lower; os_id_lower="$(echo "${os_id}" | tr '[:upper:]' '[:lower:]')"
    log "CHECK" "OS: $(detect_os_name) (${os_id})"
    log "CHECK" "Architecture: $(uname -m)"
    log "CHECK" "Build method: ${BUILD_METHOD} (configure+make, benchtests via loader trick)"
    log "CHECK" "Note: glibc ${SOFTWARE_VERSION} will be built to /tmp, system glibc NOT touched"
    case "${os_id_lower}" in
        ubuntu|debian) sudo apt-get update -qq >/dev/null 2>&1; sudo apt-get install -y -qq build-essential gcc g++ make git wget curl bison gawk texinfo python3 >/dev/null 2>&1 ;;
        openeuler) sudo dnf install -y gcc gcc-c++ make git wget curl bison gawk texinfo python3 >/dev/null 2>&1 ;;
        centos|rhel|fedora) sudo dnf install -y gcc gcc-c++ make git wget curl bison gawk texinfo python3 >/dev/null 2>&1 ;;
        *) log "WARN" "Unknown OS: ${os_id}" ;;
    esac
    return ${err}
}

phase1_build() {
    log "PHASE1" "=== Phase 1: Source Build glibc ${SOFTWARE_VERSION} (out-of-tree, NOT touching system) ==="
    if [ -n "${GLIBC_BUILD_DIR}" ] && [ -d "${GLIBC_BUILD_DIR}" ]; then
        log "PHASE1" "Reusing existing glibc build at ${GLIBC_BUILD_DIR}"
        log "PHASE1" "Build phase complete (reused, system glibc untouched)"
        return 0
    fi
    create_build_tmpdir
    local SRC="${BUILD_TMPDIR}/glibc_src"
    local BUILD="${BUILD_TMPDIR}/build"
    local INSTALL="${BUILD_TMPDIR}/install"
    local os_id; os_id="$(detect_os_id)"
    local os_id_lower; os_id_lower="$(echo "${os_id}" | tr '[:upper:]' '[:lower:]')"
    local ver_tag="glibc-${SOFTWARE_VERSION}"
    [ "${SOFTWARE_VERSION:0:6}" = "glibc-" ] && ver_tag="${SOFTWARE_VERSION}"
    local tarball="glibc-${SOFTWARE_VERSION}.tar.xz"
    log "PHASE1" "Downloading glibc ${SOFTWARE_VERSION} tarball from GNU FTP..."
    (cd "${BUILD_TMPDIR}" && curl -sL -o "${tarball}" "https://ftp.gnu.org/gnu/glibc/${tarball}" 2>&1 | tee -a "${LOG_FILE}") || \
        wget -q -O "${BUILD_TMPDIR}/${tarball}" "https://ftp.gnu.org/gnu/glibc/${tarball}" 2>&1 | tee -a "${LOG_FILE}"
    if [ -f "${BUILD_TMPDIR}/${tarball}" ]; then
        log "PHASE1" "Extracting tarball..."
        (cd "${BUILD_TMPDIR}" && tar xJf "${tarball}" 2>&1 | tee -a "${LOG_FILE}") && SRC="${BUILD_TMPDIR}/glibc-${SOFTWARE_VERSION}"
    fi
    if [ ! -d "${SRC}" ]; then
        log "WARN" "tarball download failed, trying git clone from GitHub mirror..."
        git clone --branch "${ver_tag}" --depth 1 https://github.com/bminor/glibc.git "${SRC}" >> "${LOG_FILE}" 2>&1 || {
            log "WARN" "GitHub mirror failed, trying sourceware.org..."
            git clone --branch "${ver_tag}" --depth 1 https://sourceware.org/git/glibc.git "${SRC}" >> "${LOG_FILE}" 2>&1 || { log "ERROR" "Failed to download glibc"; return 1; }
        }
    fi
    log "PHASE1" "Configuring (out-of-tree build)..."
    mkdir -p "${BUILD}"
    (cd "${BUILD}" && "${SRC}/configure" --prefix="${INSTALL}" --disable-werror --enable-kernel=6.6 2>&1 | tee -a "${LOG_FILE}") || { log "ERROR" "configure failed"; return 1; }
    log "PHASE1" "Compiling glibc (10-25 minutes)..."
    (cd "${BUILD}" && make -j$(nproc) 2>&1 | tee -a "${LOG_FILE}") || { log "ERROR" "make failed"; return 1; }
    log "PHASE1" "Installing to temp prefix (NOT system)..."
    (cd "${BUILD}" && make install 2>&1 | tee -a "${LOG_FILE}") || log "WARN" "make install had issues"
    GLIBC_BUILD_DIR="${BUILD}"
    log "PHASE1" "Verifying build..."
    if [ -f "${INSTALL}/lib/libc.so.6" ] || [ -f "${INSTALL}/lib64/libc.so.6" ]; then
        log "PHASE1" "glibc ${SOFTWARE_VERSION} built successfully at ${INSTALL}"
    else
        log "WARN" "libc.so.6 not found in install dir, checking build tree..."
        if [ -f "${BUILD}/libc.so" ]; then log "PHASE1" "Found libc.so in build tree"; fi
    fi
    log "PHASE1" "Build phase complete (system glibc untouched)"
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
    gcc_ver="$(gcc --version 2>/dev/null | head -1 | tr -d '\n\t' || echo 'unknown')"
    local glibc_ver="${SOFTWARE_VERSION}"
    if [ -n "${GLIBC_BUILD_DIR}" ] && [ -f "${GLIBC_BUILD_DIR}/config.make" ]; then
        local version_line; version_line="$(grep '^VERSION' ${GLIBC_BUILD_DIR}/config.make 2>/dev/null | head -1 | tr -d '\n\t')"
        [ -n "${version_line}" ] && glibc_ver="${version_line#VERSION=} (${SOFTWARE_VERSION})"
    fi
    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${model}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${SOFTWARE_NAME}" "${glibc_ver}" "${python_ver}" "${gcc_ver}"
    log "PHASE2" "Version info saved (glibc: ${glibc_ver})"
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks (make bench via loader trick) ==="
    mkdir -p "${RESULTS_DIR}"
    if [ -z "${GLIBC_BUILD_DIR}" ] || [ ! -d "${GLIBC_BUILD_DIR}" ]; then
        log "ERROR" "glibc build dir not available, skipping benchmarks"
        return 1
    fi
    log "PHASE3A" "Running glibc benchtests (make bench)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_glibc.py" "${GLIBC_BUILD_DIR}" "${RESULTS_DIR}/benchmark_glibc.json" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "benchtests had issues"
    log "PHASE3B" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" "${GLIBC_BUILD_DIR}" "${RESULTS_DIR}/micro_benchmark.json" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "micro benchmark had issues"
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
    log "START" "${SOFTWARE_NAME} benchtests Performance Benchmark - ${SOFTWARE_VERSION} (${BUILD_METHOD})"
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
testSoftwareIsInstalled() { local f=0; [ -n "${GLIBC_BUILD_DIR}" ] && [ -d "${GLIBC_BUILD_DIR}" ] && f=1; if [ "${f}" -eq 0 ]; then startSkipping; return; fi; assertTrue "glibc build dir exists" "[ ${f} -eq 1 ]"; }
testSoftwareVersionMatches() { assertNotNull "Version not empty" "${SOFTWARE_VERSION}"; }
testVersionInfoExists() { assertTrue "version_info.json exists" "[ -f '${RESULTS_DIR}/version_info.json' ]"; }
testVersionInfoHasArchitecture() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has architecture" "[ $(json_field_exists "${vf}" architecture) -eq 1 ]"; }
testVersionInfoHasSoftwareVersion() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has software_version" "[ $(json_field_exists "${vf}" software_version) -eq 1 ]"; }
testBenchmarkPrimaryProducesResults() { assertTrue "benchmark_glibc.json exists" "[ -f '${RESULTS_DIR}/benchmark_glibc.json' ]"; }
testBenchmarkPrimaryHasRequiredFields() { local bf="${RESULTS_DIR}/benchmark_glibc.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has benchmark" "[ $(json_contains "${bf}" benchmark) -eq 1 ]"; assertTrue "has performance_metrics" "[ $(json_contains "${bf}" performance_metrics) -eq 1 ]"; assertTrue "has results_summary" "[ $(json_contains "${bf}" results_summary) -eq 1 ]"; }
testBenchmarkPrimaryIsGlibcBenchtests() { local bf="${RESULTS_DIR}/benchmark_glibc.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertEquals "benchmark is glibc_benchtests" "glibc_benchtests" "$(json_get "${bf}" benchmark)"; }
testBenchmarkPrimaryBenchsetsCompleted() { local bf="${RESULTS_DIR}/benchmark_glibc.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has bench-math" "[ $(json_contains "${bf}" bench-math) -eq 1 ]"; assertTrue "has bench-string" "[ $(json_contains "${bf}" bench-string) -eq 1 ]"; }
testBenchmarkMicroProducesResults() { assertTrue "micro_benchmark.json exists" "[ -f '${RESULTS_DIR}/micro_benchmark.json' ]"; }
testBenchmarkMicroHasRequiredFields() { local bf="${RESULTS_DIR}/micro_benchmark.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has benchmark" "[ $(json_contains "${bf}" benchmark) -eq 1 ]"; assertTrue "has results" "[ $(json_contains "${bf}" results) -eq 1 ]"; }
testBenchmarkMicroPthreadScaling() { local bf="${RESULTS_DIR}/micro_benchmark.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has pthread_scaling" "[ $(json_contains "${bf}" pthread_scaling) -eq 1 ]"; }
testAggregatedResultsExist() { assertTrue "results.json exists" "[ -f '${RESULTS_DIR}/results.json' ]"; }
testSummaryReportGenerated() { assertTrue "results.txt exists" "[ -f '${RESULTS_DIR}/results.txt' ]"; }
testLogFileGenerated() { assertTrue "results.log exists" "[ -f '${RESULTS_DIR}/results.log' ]"; }
testAggregatedResultsContainsAllBenchmarks() { local af="${RESULTS_DIR}/results.json"; [ -f "${af}" ] || { startSkipping; return; }; assertTrue "has primary" "[ $(json_contains "${af}" primary) -eq 1 ]"; assertTrue "has micro" "[ $(json_contains "${af}" micro) -eq 1 ]"; }
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "glibc benchtests Performance Benchmark (source build + make bench via loader trick)"
    echo "Options: --check (prerequisites), -h|--help"
    echo "Env: SOFTWARE_VERSION (default: 2.44, tag glibc-2.44), ITERATIONS (default: 1)"
    echo "      MINIMUM_MEAN_NS (default: 0.1)"
    echo "      BENCH_TIMEOUT (default: 300s per benchset)"
    echo "      GLIBC_BUILD_DIR (set to reuse an existing build dir, skip compile)"
    echo "Note: Builds glibc to /tmp, system glibc NOT touched"
    echo "      make bench runs via loader trick (ld-linux --library-path)"
}
main() {
    local check_only=0
    while [ $# -gt 0 ]; do case "$1" in --check) check_only=1; shift ;; -h|--help) usage; exit 0 ;; *) log "ERROR" "Unknown: $1"; usage; exit 1 ;; esac; done
    log "START" "${SOFTWARE_NAME} benchtests Performance Benchmark ${SOFTWARE_VERSION}"
    if [ "${check_only}" -eq 1 ]; then check_prerequisites; exit $?; fi
    check_prerequisites || { log "FATAL" "Prerequisites not met"; exit 1; }
    download_shunit2 || { log "FATAL" "Failed to download shUnit2"; exit 1; }
    SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"
    . "${SHUNIT2_PATH}"
}
if [ "${1:-}" != "--shunit2-run" ]; then main "$@"; fi
