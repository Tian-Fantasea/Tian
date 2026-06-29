#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOFTWARE_NAME="rocksdb"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-11.1.2}"
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
BENCHMARK_BIN=""
ROCKSDB_INSTALL_DIR=""

NUM_OPS="${NUM_OPS:-10000}"
VALUE_SIZE="${VALUE_SIZE:-256}"
ITERATIONS="${ITERATIONS:-1}"

MIN_WRITE_OPS="${MIN_WRITE_OPS:-5000}"
MIN_READ_OPS="${MIN_READ_OPS:-10000}"
MIN_WRITE_SPEED="${MIN_WRITE_SPEED:-1}"
MIN_READ_SPEED="${MIN_READ_SPEED:-2}"
MAX_PUT_LATENCY_US="${MAX_PUT_LATENCY_US:-200}"
MAX_GET_LATENCY_US="${MAX_GET_LATENCY_US:-100}"

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

detect_os_id() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "${ID}"
    else
        echo "unknown"
    fi
}

detect_os_name() {
    echo "${TARGET_OS}"
}

create_build_tmpdir() {
    BUILD_TMPDIR="$(mktemp -d /tmp/rocksdb_build_XXXXXX)"
    log "BUILD" "Created temp build directory: ${BUILD_TMPDIR}"
}

cleanup_build_tmpdir() {
    if [ -n "${BUILD_TMPDIR}" ] && [ -d "${BUILD_TMPDIR}" ]; then
        log "BUILD" "Cleaning up temp build directory: ${BUILD_TMPDIR}"
        rm -rf "${BUILD_TMPDIR}"
        BUILD_TMPDIR=""
    fi
}

download_shunit2() {
    local shunit2_tmpdir
    shunit2_tmpdir="$(mktemp -d /tmp/shunit2_XXXXXX)"
    SHUNIT2_PATH="${shunit2_tmpdir}/shunit2"
    log "SETUP" "Downloading shUnit2 to ${shunit2_tmpdir}..."
    local mirrors=(
        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
        "https://raw.gitmirror.com/kward/shunit2/master/shunit2"
    )
    local downloaded=0
    for mirror_url in "${mirrors[@]}"; do
        curl --connect-timeout 30 --max-time 60 -sL -o "${SHUNIT2_PATH}" "${mirror_url}" && {
            chmod +x "${SHUNIT2_PATH}"
            grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { downloaded=1; break; }
        }
        rm -f "${SHUNIT2_PATH}"
    done
    if [ "${downloaded}" -eq 0 ]; then
        for mirror_url in "${mirrors[@]}"; do
            wget --timeout=30 --tries=2 -q -O "${SHUNIT2_PATH}" "${mirror_url}" 2>/dev/null && {
                chmod +x "${SHUNIT2_PATH}"
                grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { downloaded=1; break; }
            }
            rm -f "${SHUNIT2_PATH}"
        done
    fi
    if [ "${downloaded}" -eq 0 ]; then
        log "ERROR" "Failed to download shUnit2"
        rm -rf "${shunit2_tmpdir}"
        return 1
    fi
    log "SETUP" "shUnit2 downloaded successfully"
}

check_prerequisites() {
    local errors=0

    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR" "python3 is not installed. Please install Python 3.8+."
        errors=$((errors + 1))
    else
        log "CHECK" "Python3 OK: $(python3 --version 2>&1)"
    fi

    if ! command -v g++ >/dev/null 2>&1; then
        log "WARN" "g++ not found - will install in build phase"
    else
        log "CHECK" "G++ OK: $(g++ --version 2>&1 | head -1)"
    fi

    if ! command -v cmake >/dev/null 2>&1; then
        log "WARN" "cmake not found - will install in build phase"
    else
        log "CHECK" "CMake OK: $(cmake --version 2>&1 | head -1)"
    fi

    if ! command -v git >/dev/null 2>&1; then
        log "WARN" "git not found - will install in build phase"
    else
        log "CHECK" "Git OK: $(git --version 2>&1)"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    else
        log "CHECK" "json_helper.py OK"
    fi

    local os_id os_name
    os_id="$(detect_os_id)"
    os_name="$(detect_os_name)"
    log "CHECK" "OS: ${os_name} (${os_id})"
    log "CHECK" "Architecture: $(uname -m)"
    log "CHECK" "Build method: ${BUILD_METHOD}"

    return ${errors}
}

phase1_build() {
    log "PHASE1" "=== Phase 1: Source Build RocksDB v${SOFTWARE_VERSION} ==="

    create_build_tmpdir

    local ROCKSDB_SRC_DIR="${BUILD_TMPDIR}/rocksdb_src"
    local ROCKSDB_BUILD_DIR="${BUILD_TMPDIR}/build"
    ROCKSDB_INSTALL_DIR="${BUILD_TMPDIR}/install"

    local os_id
    os_id="$(detect_os_id)"
    log "PHASE1" "Building RocksDB from source on ${os_id}..."

    case "${os_id}" in
        ubuntu|debian)
            log "PHASE1" "Installing build dependencies (Ubuntu/Debian)..."
            sudo apt-get update -qq 2>&1 | tee -a "${LOG_FILE}"
            sudo apt-get install -y -qq build-essential g++ cmake make \
                libsnappy-dev liblz4-dev libzstd-dev zlib1g-dev \
                git wget curl 2>&1 | tee -a "${LOG_FILE}"
            ;;
        openeuler)
            log "PHASE1" "Installing build dependencies (openEuler 24.03 SP3)..."
            sudo dnf install -y gcc gcc-c++ cmake make \
                snappy-devel lz4-devel libzstd-devel zlib-devel \
                git wget curl 2>&1 | tee -a "${LOG_FILE}"
            ;;
        centos|rhel|fedora)
            log "PHASE1" "Installing build dependencies (RHEL-family)..."
            sudo dnf install -y gcc gcc-c++ cmake make \
                snappy-devel lz4-devel libzstd-devel zlib-devel \
                git wget curl 2>&1 | tee -a "${LOG_FILE}"
            ;;
        *)
            log "WARN" "Unknown OS: ${os_id}, attempting generic build..."
            ;;
    esac

    log "PHASE1" "Cloning RocksDB v${SOFTWARE_VERSION}..."
    git clone --branch v${SOFTWARE_VERSION} --depth 1 \
        https://github.com/facebook/rocksdb.git \
        "${ROCKSDB_SRC_DIR}" 2>&1 | tee -a "${LOG_FILE}" || {
        log "ERROR" "Failed to clone RocksDB"
        return 1
    }

    log "PHASE1" "Configuring CMake..."
    mkdir -p "${ROCKSDB_BUILD_DIR}"
    (cd "${ROCKSDB_BUILD_DIR}" && cmake \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="${ROCKSDB_INSTALL_DIR}" \
        -DWITH_TESTS=OFF \
        -DWITH_BENCHMARK_TOOLS=OFF \
        -DWITH_SNAPPY=ON \
        -DWITH_LZ4=ON \
        -DWITH_ZSTD=ON \
        -DWITH_ZLIB=ON \
        -DROCKSDB_BUILD_SHARED=OFF \
        "${ROCKSDB_SRC_DIR}" 2>&1 | tee -a "${LOG_FILE}") || {
        log "WARN" "CMake with compression libs failed, retrying without..."
        rm -rf "${ROCKSDB_BUILD_DIR}"
        mkdir -p "${ROCKSDB_BUILD_DIR}"
        (cd "${ROCKSDB_BUILD_DIR}" && cmake \
            -DCMAKE_BUILD_TYPE=Release \
            -DCMAKE_INSTALL_PREFIX="${ROCKSDB_INSTALL_DIR}" \
            -DWITH_TESTS=OFF \
            -DWITH_BENCHMARK_TOOLS=OFF \
            -DWITH_SNAPPY=OFF \
            -DWITH_LZ4=OFF \
            -DWITH_ZSTD=OFF \
            -DWITH_ZLIB=OFF \
            -DROCKSDB_BUILD_SHARED=OFF \
            "${ROCKSDB_SRC_DIR}" 2>&1 | tee -a "${LOG_FILE}") || {
            log "ERROR" "CMake configuration failed"
            return 1
        }
    }

    log "PHASE1" "Compiling RocksDB (this may take several minutes)..."
    (cd "${ROCKSDB_BUILD_DIR}" && make -j$(nproc) 2>&1 | tee -a "${LOG_FILE}") || {
        log "ERROR" "RocksDB compilation failed"
        return 1
    }

    log "PHASE1" "Installing RocksDB..."
    (cd "${ROCKSDB_BUILD_DIR}" && make install 2>&1 | tee -a "${LOG_FILE}") || {
        log "WARN" "make install failed"
    }

    local rocksdb_lib_dir="${ROCKSDB_INSTALL_DIR}/lib"
    if [ ! -d "${rocksdb_lib_dir}" ]; then rocksdb_lib_dir="${ROCKSDB_INSTALL_DIR}/lib64"; fi
    if [ ! -f "${rocksdb_lib_dir}/librocksdb.a" ]; then
        log "PHASE1" "Static lib not found in install dir, checking /usr/local..."
        for d in /usr/local/lib /usr/local/lib64 /usr/lib /usr/lib64; do
            if [ -f "${d}/librocksdb.a" ]; then
                ROCKSDB_INSTALL_DIR="/usr/local"
                log "PHASE1" "Using system-installed RocksDB"
                break
            fi
        done
    fi

    log "PHASE1" "Compiling benchmark program..."
    local BENCHMARK_SRC="${SCRIPT_DIR}/scripts/rocksdb_benchmark.cc"
    BENCHMARK_BIN="${BUILD_TMPDIR}/rocksdb_benchmark"

    local ROCKSDB_INC="${ROCKSDB_INSTALL_DIR}/include"
    local ROCKSDB_LIB="${ROCKSDB_INSTALL_DIR}/lib"
    if [ ! -d "${ROCKSDB_LIB}" ]; then ROCKSDB_LIB="${ROCKSDB_INSTALL_DIR}/lib64"; fi

    local ROCKSDB_STATIC_LIB=""
    for d in "${ROCKSDB_LIB}" /usr/local/lib /usr/local/lib64 /usr/lib /usr/lib64; do
        if [ -f "${d}/librocksdb.a" ]; then
            ROCKSDB_STATIC_LIB="${d}/librocksdb.a"
            break
        fi
    done

    local EXTRA_LIBS=""
    for d in "${ROCKSDB_LIB}" /usr/local/lib /usr/local/lib64 /usr/lib /usr/lib64; do
        if [ -f "${d}/libsnappy.a" ] || [ -f "${d}/libsnappy.so" ]; then EXTRA_LIBS="${EXTRA_LIBS} -lsnappy"; break; fi
    done
    for d in "${ROCKSDB_LIB}" /usr/local/lib /usr/local/lib64 /usr/lib /usr/lib64; do
        if [ -f "${d}/liblz4.a" ] || [ -f "${d}/liblz4.so" ]; then EXTRA_LIBS="${EXTRA_LIBS} -llz4"; break; fi
    done
    for d in "${ROCKSDB_LIB}" /usr/local/lib /usr/local/lib64 /usr/lib /usr/lib64; do
        if [ -f "${d}/libzstd.a" ] || [ -f "${d}/libzstd.so" ]; then EXTRA_LIBS="${EXTRA_LIBS} -lzstd"; break; fi
    done
    for d in "${ROCKSDB_LIB}" /usr/local/lib /usr/local/lib64 /usr/lib /usr/lib64; do
        if [ -f "${d}/libz.a" ] || [ -f "${d}/libz.so" ]; then EXTRA_LIBS="${EXTRA_LIBS} -lz"; break; fi
    done

    if [ -n "${ROCKSDB_STATIC_LIB}" ]; then
        log "PHASE1" "Linking with static librocksdb: ${ROCKSDB_STATIC_LIB} ${EXTRA_LIBS}"
        g++ -O2 -std=c++17 \
            -I"${ROCKSDB_INC}" \
            "${BENCHMARK_SRC}" \
            "${ROCKSDB_STATIC_LIB}" \
            ${EXTRA_LIBS} \
            -o "${BENCHMARK_BIN}" 2>&1 | tee -a "${LOG_FILE}" || {
            log "ERROR" "Benchmark compilation failed"
            return 1
        }
    else
        log "PHASE1" "Linking with shared librocksdb from ${ROCKSDB_LIB}"
        g++ -O2 -std=c++17 \
            -I"${ROCKSDB_INC}" \
            "${BENCHMARK_SRC}" \
            -L"${ROCKSDB_LIB}" -lrocksdb \
            ${EXTRA_LIBS} \
            -Wl,-rpath,"${ROCKSDB_LIB}" \
            -o "${BENCHMARK_BIN}" 2>&1 | tee -a "${LOG_FILE}" || {
            log "ERROR" "Benchmark compilation (shared) failed"
            return 1
        }
    fi

    log "PHASE1" "Verifying benchmark binary..."
    if [ -x "${BENCHMARK_BIN}" ]; then
        "${BENCHMARK_BIN}" kv 1 "${BUILD_TMPDIR}/test_verify.json" 100 64 2>&1 | tee -a "${LOG_FILE}" || {
            log "WARN" "Benchmark verification run failed"
        }
        if [ -f "${BUILD_TMPDIR}/test_verify.json" ]; then
            log "PHASE1" "Benchmark binary verified successfully"
            rm -f "${BUILD_TMPDIR}/test_verify.json"
        else
            log "WARN" "Benchmark verification output not found, but continuing..."
        fi
    else
        log "ERROR" "Benchmark binary not executable"
        return 1
    fi

    log "PHASE1" "RocksDB source build and benchmark compilation complete"
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="
    local timestamp model arch kernel os_name cpu_model cores python_ver gcc_ver
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    model="${TARGET_MODEL}"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os_name="$(detect_os_name | tr -d '\n\t')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ]; then
        local num_proc
        num_proc="$(grep -c 'processor' /proc/cpuinfo 2>/dev/null || echo 0)"
        cpu_model="ARM64 CPU (${num_proc} cores)"
    fi
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t')"
    gcc_ver="$(g++ --version 2>/dev/null | head -1 | sed 's/.* //' | tr -d '\n\t' || echo 'unknown')"

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${model}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \
        "${python_ver}" "${gcc_ver}"
    log "PHASE2" "Version info saved (OS: ${os_name}, GCC: ${gcc_ver})"
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="
    mkdir -p "${RESULTS_DIR}"

    log "PHASE3A" "Running KV store benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_kv.py" \
        "${BENCHMARK_BIN}" \
        "${RESULTS_DIR}/benchmark_kv.json" \
        "${NUM_OPS}" \
        "${VALUE_SIZE}" \
        "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "KV benchmark had issues"

    log "PHASE3B" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        "${BENCHMARK_BIN}" \
        "${RESULTS_DIR}/micro_benchmark.json" \
        "${NUM_OPS}" \
        "${VALUE_SIZE}" \
        "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate & Report ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        "${RESULTS_DIR}" "${RESULTS_DIR}/results.json"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt"

    log "PHASE4" "Reports generated:"
    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"
    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"
    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"
}

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"
    log "START" "${SOFTWARE_NAME} Source Build & Performance Benchmark - v${SOFTWARE_VERSION}"
    local os_id os_name
    os_id="$(detect_os_id)"
    os_name="$(detect_os_name)"
    log "START" "OS: ${os_name} (${os_id}), Build: ${BUILD_METHOD}"

    check_prerequisites || log "WARN" "Some prerequisites missing, continuing..."
    phase1_build || log "FATAL" "Phase 1 (source build) failed"
    phase2_verify || log "WARN" "Phase 2 had issues, continuing..."
    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing..."
    phase4_results || log "WARN" "Phase 4 had issues..."
}

oneTimeTearDown() {
    cleanup_build_tmpdir
    if [ -n "${SHUNIT2_PATH}" ]; then
        local shunit2_dir="$(dirname "${SHUNIT2_PATH}")"
        rm -rf "${shunit2_dir}"
        SHUNIT2_PATH=""
    fi
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
    for d in /usr/local/lib /usr/local/lib64 /usr/lib /usr/lib64; do
        if [ -f "${d}/librocksdb.so" ] || [ -f "${d}/librocksdb.a" ]; then found=1; break; fi
    done
    if [ -n "${ROCKSDB_INSTALL_DIR}" ]; then
        local rdb_lib="${ROCKSDB_INSTALL_DIR}/lib"
        if [ ! -d "${rdb_lib}" ]; then rdb_lib="${ROCKSDB_INSTALL_DIR}/lib64"; fi
        if [ -f "${rdb_lib}/librocksdb.so" ] || [ -f "${rdb_lib}/librocksdb.a" ]; then found=1; fi
    fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: RocksDB library not found, skipping install check"
        startSkipping
        return
    fi
    assertTrue "RocksDB library should exist" "[ ${found} -eq 1 ]"
}

testSoftwareVersionMatches() {
    local ver="${SOFTWARE_VERSION}"
    assertNotNull "Version should not be empty" "${ver}"
}

testBenchmarkBinaryExists() {
    local found=0
    if [ -n "${BENCHMARK_BIN}" ] && [ -x "${BENCHMARK_BIN}" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        startSkipping
        return
    fi
    assertTrue "Benchmark binary should be executable" "[ ${found} -eq 1 ]"
}

testVersionInfoExists() {
    assertTrue "Version info JSON should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasArchitecture() {
    local vfile="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${vfile}" ]; then startSkipping; return; fi
    local has_arch
    has_arch="$(json_field_exists "${vfile}" architecture)"
    assertTrue "Version info should have architecture field" "[ ${has_arch} -eq 1 ]"
}

testVersionInfoHasSoftwareVersion() {
    local vfile="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${vfile}" ]; then startSkipping; return; fi
    local has_ver
    has_ver="$(json_field_exists "${vfile}" software_version)"
    assertTrue "Version info should have software_version field" "[ ${has_ver} -eq 1 ]"
}

testBenchmarkPrimaryProducesResults() {
    assertTrue "KV benchmark JSON should exist" "[ -f '${RESULTS_DIR}/benchmark_kv.json' ]"
}

testBenchmarkPrimaryHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/benchmark_kv.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_contains "${bench_file}" results_summary)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results_summary field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkPrimaryWriteOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_kv.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local write_ops
    write_ops="$(json_get "${bench_file}" results_summary write_only write_ops_per_sec)"
    if [ "${write_ops}" = "NULL" ] || [ -z "${write_ops}" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] Write-only ops/s: ${write_ops} (threshold: ${MIN_WRITE_OPS})"
    assertTrue "Write-only ops/s (${write_ops}) should be >= ${MIN_WRITE_OPS}" \
        "[ $(echo "${write_ops} >= ${MIN_WRITE_OPS}" | bc -l) -eq 1 ]"
}

testBenchmarkPrimaryReadOpsAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_kv.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local read_ops
    read_ops="$(json_get "${bench_file}" results_summary read_80_write_20 read_ops_per_sec)"
    if [ "${read_ops}" = "NULL" ] || [ -z "${read_ops}" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] Read-80 ops/s: ${read_ops} (threshold: ${MIN_READ_OPS})"
    assertTrue "Read-80-W20 ops/s (${read_ops}) should be >= ${MIN_READ_OPS}" \
        "[ $(echo "${read_ops} >= ${MIN_READ_OPS}" | bc -l) -eq 1 ]"
}

testBenchmarkPrimaryIsKV() {
    local bench_file="${RESULTS_DIR}/benchmark_kv.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local bench_name
    bench_name="$(json_get "${bench_file}" benchmark)"
    assertEquals "Benchmark name should be kv_store" "kv_store" "${bench_name}"
}

testBenchmarkPrimaryWriteSpeedAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_kv.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local write_mbs
    write_mbs="$(json_get "${bench_file}" results_summary write_only write_speed_mbs)"
    if [ "${write_mbs}" = "NULL" ] || [ -z "${write_mbs}" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] Write-only MB/s: ${write_mbs} (threshold: ${MIN_WRITE_SPEED})"
    assertTrue "Write MB/s (${write_mbs}) should be >= ${MIN_WRITE_SPEED}" \
        "[ $(echo "${write_mbs} >= ${MIN_WRITE_SPEED}" | bc -l) -eq 1 ]"
}

testBenchmarkPrimaryReadSpeedAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_kv.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local read_mbs
    read_mbs="$(json_get "${bench_file}" results_summary read_80_write_20 read_speed_mbs)"
    if [ "${read_mbs}" = "NULL" ] || [ -z "${read_mbs}" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] Read-80 MB/s: ${read_mbs} (threshold: ${MIN_READ_SPEED})"
    assertTrue "Read MB/s (${read_mbs}) should be >= ${MIN_READ_SPEED}" \
        "[ $(echo "${read_mbs} >= ${MIN_READ_SPEED}" | bc -l) -eq 1 ]"
}

testBenchmarkMicroProducesResults() {
    assertTrue "Micro benchmark JSON should exist" "[ -f '${RESULTS_DIR}/micro_benchmark.json' ]"
}

testBenchmarkMicroHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_benchmark has_metrics has_results
    has_benchmark="$(json_contains "${bench_file}" benchmark)"
    has_metrics="$(json_contains "${bench_file}" performance_metrics)"
    has_results="$(json_contains "${bench_file}" results)"
    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"
    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"
    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"
}

testBenchmarkMicroAllOperationsCompleted() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local ops_count
    ops_count="$(json_count_results "${bench_file}")"
    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -ge 2 ]"
}

testBenchmarkMicroGetLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local get_latency
    get_latency="$(json_get "${bench_file}" results single_operations single_get latency_us)"
    if [ "${get_latency}" = "NULL" ] || [ -z "${get_latency}" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] Single Get latency: ${get_latency} us (threshold: ${MAX_GET_LATENCY_US})"
    assertTrue "Single Get latency (${get_latency}us) should be <= ${MAX_GET_LATENCY_US}us" \
        "[ $(echo "${get_latency} <= ${MAX_GET_LATENCY_US}" | bc -l) -eq 1 ]"
}

testBenchmarkMicroPutLatencyBelowThreshold() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local put_latency
    put_latency="$(json_get "${bench_file}" results single_operations single_put latency_us)"
    if [ "${put_latency}" = "NULL" ] || [ -z "${put_latency}" ]; then
        startSkipping
        return
    fi
    echo "[DIAG] Single Put latency: ${put_latency} us (threshold: ${MAX_PUT_LATENCY_US})"
    assertTrue "Single Put latency (${put_latency}us) should be <= ${MAX_PUT_LATENCY_US}us" \
        "[ $(echo "${put_latency} <= ${MAX_PUT_LATENCY_US}" | bc -l) -eq 1 ]"
}

testBenchmarkMicroMultithreadScaling() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_mt
    has_mt="$(json_contains "${bench_file}" multithread_scaling)"
    assertTrue "Should have multithread scaling results" "[ ${has_mt} -eq 1 ]"
}

testAggregatedResultsExist() {
    assertTrue "results.json should exist" "[ -f '${RESULTS_DIR}/results.json' ]"
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
    local has_primary has_micro
    has_primary="$(json_contains "${agg_file}" primary_benchmark)"
    has_micro="$(json_contains "${agg_file}" micro)"
    assertTrue "Should contain primary_benchmark (KV) data" "[ ${has_primary} -eq 1 ]"
    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"
}

usage() {
    cat <<USAGE
Usage: $(basename "$0") [OPTIONS]
RocksDB Source Build & Performance Benchmark (shUnit2)
Options:
  --check    Check prerequisites only (do not run benchmarks)
  -h|--help  Show this help
Environment variables:
  SOFTWARE_VERSION         RocksDB version (default: 11.1.2)
  TARGET_OS               OS name in results (default: openEuler 24.03 SP3)
  TARGET_MODEL            Hardware model (default: Kunpeng-920)
  NUM_OPS                 Number of operations (default: 10000)
  VALUE_SIZE              Value size in bytes (default: 256)
  ITERATIONS              Number of iterations (default: 1)
  MIN_WRITE_OPS           Minimum write ops/s threshold (default: 5000)
  MIN_READ_OPS            Minimum read ops/s threshold (default: 10000)
  MIN_WRITE_SPEED         Minimum write MB/s threshold (default: 1)
  MIN_READ_SPEED          Minimum read MB/s threshold (default: 2)
  MAX_PUT_LATENCY_US      Maximum Put latency us (default: 200)
  MAX_GET_LATENCY_US      Maximum Get latency us (default: 100)
Examples:
  ./rocksdb_test.sh --check
  ./rocksdb_test.sh
  NUM_OPS=50000 VALUE_SIZE=1024 ./rocksdb_test.sh
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

    log "START" "${SOFTWARE_NAME} Source Build & Performance Benchmark v${SOFTWARE_VERSION}"

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

    SHUNIT_PARENT="${SCRIPT_DIR}/${SOFTWARE_NAME}_test.sh"
    . "${SHUNIT2_PATH}"
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
