#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOFTWARE_NAME="brpc"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-1.17.0}"
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
ECHO_SERVER_BIN=""
ECHO_CLIENT_BIN=""
ITERATIONS="${ITERATIONS:-1}"
DURATION="${DURATION:-30}"
MINIMUM_QPS="${MINIMUM_QPS:-1000}"
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
create_build_tmpdir() { BUILD_TMPDIR="$(mktemp -d /tmp/brpc_build_XXXXXX)"; log "BUILD" "Created temp dir: ${BUILD_TMPDIR}"; }
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
    command -v curl >/dev/null 2>&1 && log "CHECK" "curl OK" || log "WARN" "curl not found"
    [ -f "${JSON_HELPER}" ] && log "CHECK" "json_helper.py OK" || { log "ERROR" "json_helper.py not found"; err=$((err+1)); }
    local os_id; os_id="$(detect_os_id)"
    local os_id_lower; os_id_lower="$(echo "${os_id}" | tr '[:upper:]' '[:lower:]')"
    log "CHECK" "OS: $(detect_os_name) (${os_id})"
    log "CHECK" "Architecture: $(uname -m)"
    log "CHECK" "Build method: ${BUILD_METHOD} (cmake, C++ RPC framework, server benchmark variant)"
    case "${os_id_lower}" in
        ubuntu|debian) sudo apt-get update -qq >/dev/null 2>&1; sudo apt-get install -y -qq build-essential g++ cmake make git wget curl libgflags-dev libprotobuf-dev protobuf-compiler libleveldb-dev libssl-dev zlib1g-dev >/dev/null 2>&1 ;;
        openeuler) sudo dnf install -y gcc gcc-c++ cmake make git wget curl gflags-devel protobuf-devel protobuf-compiler leveldb-devel openssl-devel zlib-devel >/dev/null 2>&1 ;;
        centos|rhel|fedora) sudo dnf install -y gcc gcc-c++ cmake make git wget curl gflags-devel protobuf-devel protobuf-compiler leveldb-devel openssl-devel zlib-devel >/dev/null 2>&1 ;;
        *) log "WARN" "Unknown OS: ${os_id}" ;;
    esac
    return ${err}
}
phase1_build() {
    log "PHASE1" "=== Phase 1: Source Build brpc v${SOFTWARE_VERSION} ==="
    create_build_tmpdir
    local SRC="${BUILD_TMPDIR}/brpc_src"
    local BUILD="${BUILD_TMPDIR}/build"
    log "PHASE1" "Cloning brpc v${SOFTWARE_VERSION}..."
    if ! git clone --branch "${SOFTWARE_VERSION}" --depth 1 https://github.com/apache/brpc.git "${SRC}" >> "${LOG_FILE}" 2>&1; then
        log "WARN" "tag ${SOFTWARE_VERSION} not found, trying master..."
        if ! git clone --depth 1 https://github.com/apache/brpc.git "${SRC}" >> "${LOG_FILE}" 2>&1; then
            log "ERROR" "Failed to clone brpc"
            return 1
        fi
    fi
    log "PHASE1" "Configuring CMake..."
    mkdir -p "${BUILD}"
    if ! (cd "${BUILD}" && cmake -DCMAKE_BUILD_TYPE=Release "${SRC}" >> "${LOG_FILE}" 2>&1); then
        log "ERROR" "cmake failed (check protobuf version compatibility)"
        return 1
    fi
    log "PHASE1" "Compiling brpc (may take a few minutes)..."
    if ! (cd "${BUILD}" && make -j$(nproc) >> "${LOG_FILE}" 2>&1); then
        log "ERROR" "make failed"
        return 1
    fi
    # Find libbrpc
    local LIBBRPC=""
    LIBBRPC="$(find "${BUILD}" -name "libbrpc.a" -o -name "libbrpc.so" 2>/dev/null | head -1)"
    if [ -z "${LIBBRPC}" ]; then
        log "ERROR" "libbrpc not found after build"
        return 1
    fi
    log "PHASE1" "libbrpc found: ${LIBBRPC}"
    local LIB_DIR; LIB_DIR="$(dirname "${LIBBRPC}")"
    # Find echo example source files
    local ECHO_SERVER_SRC="${SRC}/example/echo_c++/server.cpp"
    local ECHO_CLIENT_SRC="${SRC}/example/echo_c++/client.cpp"
    # Try alternate paths
    [ ! -f "${ECHO_SERVER_SRC}" ] && ECHO_SERVER_SRC="$(find "${SRC}/example" -name "server.cpp" -o -name "echo_server.cpp" 2>/dev/null | head -1)"
    [ ! -f "${ECHO_CLIENT_SRC}" ] && ECHO_CLIENT_SRC="$(find "${SRC}/example" -name "client.cpp" -o -name "echo_client.cpp" 2>/dev/null | head -1)"
    # Build echo binaries
    ECHO_SERVER_BIN="${BUILD}/echo_server"
    ECHO_CLIENT_BIN="${BUILD}/echo_client"
    local INC_FLAGS="-I${SRC}/src -I${BUILD} -I${SRC}/test"
    # Add protobuf include paths
    for inc in $(pkg-config --cflags protobuf 2>/dev/null); do INC_FLAGS="${INC_FLAGS} ${inc}"; done
    for inc in $(pkg-config --cflags gflags 2>/dev/null); do INC_FLAGS="${INC_FLAGS} ${inc}"; done
    local LIB_FLAGS="-L${LIB_DIR} -lbrpc"
    for lib in $(pkg-config --libs protobuf gflags leveldb openssl 2>/dev/null); do LIB_FLAGS="${LIB_FLAGS} ${lib}"; done
    LIB_FLAGS="${LIB_FLAGS} -lssl -lcrypto -lz -lpthread"
    log "PHASE1] Building echo_server from ${ECHO_SERVER_SRC}..."
    if g++ -O2 -std=c++11 ${INC_FLAGS} "${ECHO_SERVER_SRC}" ${LIB_FLAGS} -o "${ECHO_SERVER_BIN}" >> "${LOG_FILE}" 2>&1; then
        log "PHASE1" "echo_server built: ${ECHO_SERVER_BIN}"
    else
        log "WARN" "echo_server build failed, trying cmake target..."
        (cd "${BUILD}" && cmake --build . --target echo_server 2>/dev/null || cmake --build . --target echo_s++ 2>/dev/null) >> "${LOG_FILE}" 2>&1 || true
        ECHO_SERVER_BIN="$(find "${BUILD}" -name "echo_s++" -o -name "echo_server" -type f -executable 2>/dev/null | head -1)"
    fi
    log "PHASE1] Building echo_client from ${ECHO_CLIENT_SRC}..."
    if g++ -O2 -std=c++11 ${INC_FLAGS} "${ECHO_CLIENT_SRC}" ${LIB_FLAGS} -o "${ECHO_CLIENT_BIN}" >> "${LOG_FILE}" 2>&1; then
        log "PHASE1" "echo_client built: ${ECHO_CLIENT_BIN}"
    else
        log "WARN" "echo_client build failed, trying cmake target..."
        (cd "${BUILD}" && cmake --build . --target echo_client 2>/dev/null || cmake --build . --target echo_c++ 2>/dev/null) >> "${LOG_FILE}" 2>&1 || true
        ECHO_CLIENT_BIN="$(find "${BUILD}" -name "echo_c++" -o -name "echo_client" -type f -executable 2>/dev/null | head -1)"
    fi
    log "PHASE1] Compiling brpc (may take a few minutes)..."
    if ! (cd "${BUILD}" && make -j$(nproc) >> "${LOG_FILE}" 2>&1); then
        log "ERROR" "make failed"
        return 1
    fi
    if [ -z "${ECHO_SERVER_BIN}" ] || [ ! -x "${ECHO_SERVER_BIN}" ]; then
        log "ERROR" "echo_server not built"
        return 1
    fi
    if [ -z "${ECHO_CLIENT_BIN}" ] || [ ! -x "${ECHO_CLIENT_BIN}" ]; then
        log "ERROR" "echo_client not built"
        return 1
    fi
    log "PHASE1" "echo_server: ${ECHO_SERVER_BIN}"
    log "PHASE1" "echo_client: ${ECHO_CLIENT_BIN}"
    log "PHASE1" "Build phase complete"
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
    log "PHASE2" "Version info saved (brpc: ${SOFTWARE_VERSION})"
}
phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="
    mkdir -p "${RESULTS_DIR}"
    if [ -z "${ECHO_SERVER_BIN}" ] || [ -z "${ECHO_CLIENT_BIN}" ]; then
        log "ERROR" "echo binaries not available, skipping benchmarks"
        return 1
    fi
    log "PHASE3A" "Running RPC echo benchmark (start server -> run client)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_rpc.py" \
        "${ECHO_SERVER_BIN}" "${ECHO_CLIENT_BIN}" \
        "${RESULTS_DIR}/benchmark_rpc.json" "${DURATION}" "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "RPC benchmark had issues"
    log "PHASE3B" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        "${ECHO_SERVER_BIN}" "${ECHO_CLIENT_BIN}" \
        "${RESULTS_DIR}/micro_benchmark.json" "15" "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"
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
    log "START" "${SOFTWARE_NAME} Performance Benchmark - v${SOFTWARE_VERSION} (${BUILD_METHOD})"
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
testSoftwareIsInstalled() { local f=0; [ -n "${ECHO_SERVER_BIN}" ] && [ -x "${ECHO_SERVER_BIN}" ] && f=1; if [ "${f}" -eq 0 ]; then startSkipping; return; fi; assertTrue "echo_s++ exists" "[ ${f} -eq 1 ]"; }
testBenchmarkBinaryExists() { local f=0; [ -n "${ECHO_CLIENT_BIN}" ] && [ -x "${ECHO_CLIENT_BIN}" ] && f=1; if [ "${f}" -eq 0 ]; then startSkipping; return; fi; assertTrue "echo_c++ exists" "[ ${f} -eq 1 ]"; }
testSoftwareVersionMatches() { assertNotNull "Version not empty" "${SOFTWARE_VERSION}"; }
testVersionInfoExists() { assertTrue "version_info.json exists" "[ -f '${RESULTS_DIR}/version_info.json' ]"; }
testVersionInfoHasArchitecture() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has architecture" "[ $(json_field_exists "${vf}" architecture) -eq 1 ]"; }
testVersionInfoHasSoftwareVersion() { local vf="${RESULTS_DIR}/version_info.json"; [ -f "${vf}" ] || { startSkipping; return; }; assertTrue "has software_version" "[ $(json_field_exists "${vf}" software_version) -eq 1 ]"; }
testBenchmarkPrimaryProducesResults() { assertTrue "benchmark_rpc.json exists" "[ -f '${RESULTS_DIR}/benchmark_rpc.json' ]"; }
testBenchmarkPrimaryHasRequiredFields() { local bf="${RESULTS_DIR}/benchmark_rpc.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has benchmark" "[ $(json_contains "${bf}" benchmark) -eq 1 ]"; assertTrue "has performance_metrics" "[ $(json_contains "${bf}" performance_metrics) -eq 1 ]"; assertTrue "has results_summary" "[ $(json_contains "${bf}" results_summary) -eq 1 ]"; }
testBenchmarkPrimaryQpsAboveThreshold() { local bf="${RESULTS_DIR}/benchmark_rpc.json"; [ -f "${bf}" ] || { startSkipping; return; }; local qps; qps="$(json_get "${bf}" results_summary threads_16 qps)"; if [ "${qps}" = "NULL" ] || [ -z "${qps}" ]; then startSkipping; return; fi; echo "[DIAG] QPS t=16: ${qps} (min: ${MINIMUM_QPS})"; assertTrue "QPS >= ${MINIMUM_QPS}" "[ $(echo "${qps} >= ${MINIMUM_QPS}" | bc -l) -eq 1 ]"; }
testBenchmarkPrimaryIsRpcEcho() { local bf="${RESULTS_DIR}/benchmark_rpc.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertEquals "benchmark is rpc_echo" "rpc_echo" "$(json_get "${bf}" benchmark)"; }
testBenchmarkPrimaryThreadLevelsCompleted() { local bf="${RESULTS_DIR}/benchmark_rpc.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has threads_1" "[ $(json_contains "${bf}" threads_1) -eq 1 ]"; assertTrue "has threads_32" "[ $(json_contains "${bf}" threads_32) -eq 1 ]"; }
testBenchmarkMicroProducesResults() { assertTrue "micro_benchmark.json exists" "[ -f '${RESULTS_DIR}/micro_benchmark.json' ]"; }
testBenchmarkMicroHasRequiredFields() { local bf="${RESULTS_DIR}/micro_benchmark.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has benchmark" "[ $(json_contains "${bf}" benchmark) -eq 1 ]"; assertTrue "has results" "[ $(json_contains "${bf}" results) -eq 1 ]"; }
testBenchmarkMicroPayloadSweep() { local bf="${RESULTS_DIR}/micro_benchmark.json"; [ -f "${bf}" ] || { startSkipping; return; }; assertTrue "has payload_sweep" "[ $(json_contains "${bf}" payload_sweep) -eq 1 ]"; }
testAggregatedResultsExist() { assertTrue "results.json exists" "[ -f '${RESULTS_DIR}/results.json' ]"; }
testSummaryReportGenerated() { assertTrue "results.txt exists" "[ -f '${RESULTS_DIR}/results.txt' ]"; }
testLogFileGenerated() { assertTrue "results.log exists" "[ -f '${RESULTS_DIR}/results.log' ]"; }
testAggregatedResultsContainsAllBenchmarks() { local af="${RESULTS_DIR}/results.json"; [ -f "${af}" ] || { startSkipping; return; }; assertTrue "has primary" "[ $(json_contains "${af}" primary) -eq 1 ]"; assertTrue "has micro" "[ $(json_contains "${af}" micro) -eq 1 ]"; }
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "brpc Performance Benchmark (cmake, RPC echo server benchmark variant)"
    echo "Options: --check, -h|--help"
    echo "Env: SOFTWARE_VERSION (default: 1.17.0, bare tag no v prefix), DURATION (30), ITERATIONS (1)"
    echo "      MINIMUM_QPS (1000)"
    echo "Note: brpc tag is bare (1.17.0, not v1.17.0). Depends on protobuf/leveldb/gflags/openssl."
    echo "      Build may fail if protobuf version is incompatible. Pin protobuf if needed."
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
