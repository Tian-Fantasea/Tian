#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="rocksdb"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-9.10.0}"
ROCKSDB_SRC="${ROCKSDB_SRC:-${SCRIPT_DIR}/rocksdb_src}"
DB_BENCH_PATH="${DB_BENCH_PATH:-${ROCKSDB_SRC}/db_bench}"
SHUNIT_PARENT="${SCRIPT_DIR}/rocksdb_test.sh"

MINIMUM_THROUGHPUT=100
MAXIMUM_LATENCY_MS=10.0

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

    if [ ! -x "${DB_BENCH_PATH}" ]; then
        log "ERROR" "db_bench not found at ${DB_BENCH_PATH}"
        log "ERROR" "  Please compile RocksDB ${SOFTWARE_VERSION} and ensure db_bench is at ${ROCKSDB_SRC}/db_bench"
        log "ERROR" "  Or set DB_BENCH_PATH to your db_bench binary"
        errors=$((errors + 1))
    else
        log "CHECK" "db_bench OK: ${DB_BENCH_PATH}"
    fi

    if [ ! -f "${JSON_HELPER}" ]; then
        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"
        errors=$((errors + 1))
    fi

    return ${errors}
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Collect Version Info ==="

    local timestamp arch kernel os cpu_model cores mem_mb rocksdb_ver crc_exists neon_exists
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    cores="$(nproc 2>/dev/null | tr -d '\n\t' || echo '4')"
    mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' | tr -d '\n\t' || echo '0')"
    rocksdb_ver="${SOFTWARE_VERSION}"

    crc_exists="0"
    if [ -f "${ROCKSDB_SRC}/util/crc32c_arm64.cc" ]; then
        crc_exists="1"
    fi

    neon_exists="0"
    if grep -q 'asimd' /proc/cpuinfo 2>/dev/null; then
        neon_exists="1"
    elif [ "$(uname -s)" = "Darwin" ]; then
        neon_exists="1"
    fi

    local static_lib="0"
    if [ -f "${ROCKSDB_SRC}/librocksdb.a" ]; then
        static_lib="1"
    fi

    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${rocksdb_ver}" "${DB_BENCH_PATH}" \
        "${static_lib}" "${crc_exists}" "${neon_exists}"

    log "PHASE2" "Version info saved."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    local num_keys="${NUM_KEYS:-1000000}"
    local value_size="${VALUE_SIZE:-256}"
    local threads="${THREADS:-16}"
    local iterations="${ITERATIONS:-1}"

    log "PHASE3a" "Running YCSB benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_ycsb.py" \
        --results-dir "${RESULTS_DIR}" \
        --db-bench "${DB_BENCH_PATH}" \
        --num-keys "${num_keys}" \
        --value-size "${value_size}" \
        --threads "${threads}" \
        --iterations "${iterations}" \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3b" "Running db_bench compaction/filter benchmark..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_dbbench.py" \
        --results-dir "${RESULTS_DIR}" \
        --db-bench "${DB_BENCH_PATH}" \
        --num-keys "${num_keys}" \
        --value-size "${value_size}" \
        --threads "${threads}" \
        --iterations "${iterations}" \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3c" "Running micro benchmark..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --db-bench "${DB_BENCH_PATH}" \
        --num-keys "${num_keys}" \
        --value-size "${value_size}" \
        --iterations "${iterations}" \
        2>&1 | tee -a "${LOG_FILE}"

    log "PHASE3" "Phase 3 complete."
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

    log "START" "RocksDB ARM64 Performance Benchmark - v${SOFTWARE_VERSION}"

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

testRocksdbIsInstalled() {
    local found=0
    if [ -x "${DB_BENCH_PATH}" ]; then found=1; fi
    if [ "${found}" -eq 0 ]; then
        echo "WARNING: db_bench not installed, skipping"
        startSkipping
        return
    fi
    assertTrue "db_bench binary should exist" "[ ${found} -eq 1 ]"
}

testRocksdbVersionMatches() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local ver
    ver="$(json_version "${ver_file}")"
    assertTrue "Version should not be empty" "[ -n '${ver}' ]"
}

testRocksdbRunsBasicCommand() {
    if [ ! -x "${DB_BENCH_PATH}" ]; then startSkipping; return; fi
    local result
    result="$(${DB_BENCH_PATH} --help 2>&1 | head -5)"
    assertNotNull "db_bench --help output should not be empty" "${result}"
}

testArm64CRC32CDetected() {
    local ver_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${ver_file}" ]; then startSkipping; return; fi
    local has_crc
    has_crc="$(json_get "${ver_file}" arm64_crc32c_detected)"
    assertNotNull "ARM64 CRC32C detection result should exist" "${has_crc}"
}

testVersionInfoJsonExists() {
    assertTrue "version_info.json should exist" "[ -f '${RESULTS_DIR}/version_info.json' ]"
}

testVersionInfoHasRequiredFields() {
    local bench_file="${RESULTS_DIR}/version_info.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_arch has_ver has_crc
    has_arch="$(json_field_exists "${bench_file}" architecture)"
    has_ver="$(json_field_exists "${bench_file}" rocksdb_version)"
    has_crc="$(json_field_exists "${bench_file}" arm64_crc32c_detected)"
    assertTrue "Should have architecture field" "[ ${has_arch} -eq 1 ]"
    assertTrue "Should have rocksdb_version field" "[ ${has_ver} -eq 1 ]"
    assertTrue "Should have arm64_crc32c_detected field" "[ ${has_crc} -eq 1 ]"
}

testYCSBBenchmarkProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    assertTrue "YCSB benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testYCSBBenchmarkHasRequiredFields() {
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

testYCSBWorkloadAThroughputAboveThreshold() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_a
    actual_a="$(json_get "${bench_file}" results ycsb_workload_a_update_heavy run_throughput_ops_sec)"
    echo "[DIAG] YCSB-A actual throughput: ${actual_a} ops/sec (threshold: ${MINIMUM_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" results ycsb_workload_a_update_heavy run_throughput_ops_sec)"
    assertTrue "YCSB-A throughput should be >= ${MINIMUM_THROUGHPUT}, got ${actual_a}" "[ ${has_throughput} -eq 1 ]"
}

testYCSBWorkloadCReadOnlyThroughput() {
    local bench_file="${RESULTS_DIR}/benchmark_ycsb.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local actual_c
    actual_c="$(json_get "${bench_file}" results ycsb_workload_c_read_only run_throughput_ops_sec)"
    echo "[DIAG] YCSB-C actual throughput: ${actual_c} ops/sec (threshold: ${MINIMUM_THROUGHPUT})"
    local has_throughput
    has_throughput="$(json_throughput_ge "${bench_file}" "${MINIMUM_THROUGHPUT}" results ycsb_workload_c_read_only run_throughput_ops_sec)"
    assertTrue "YCSB-C read-only throughput should be >= ${MINIMUM_THROUGHPUT}, got ${actual_c}" "[ ${has_throughput} -eq 1 ]"
}

testDbBenchProducesResults() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    assertTrue "db_bench advanced benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testDbBenchCompactionStylesValid() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_comp has_level has_universal
    has_comp="$(json_contains "${bench_file}" compaction_styles)"
    has_level="$(json_contains "${bench_file}" level_compaction)"
    has_universal="$(json_contains "${bench_file}" universal_compaction)"
    assertTrue "Should contain compaction_styles" "[ ${has_comp} -eq 1 ]"
    assertTrue "Should contain level_compaction" "[ ${has_level} -eq 1 ]"
    assertTrue "Should contain universal_compaction" "[ ${has_universal} -eq 1 ]"
}

testDbBenchCompressionValid() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_compress has_nocomp
    has_compress="$(json_contains "${bench_file}" compression_algorithms)"
    has_nocomp="$(json_contains "${bench_file}" no_compression)"
    assertTrue "Should contain compression_algorithms" "[ ${has_compress} -eq 1 ]"
    assertTrue "Should contain no_compression baseline" "[ ${has_nocomp} -eq 1 ]"
}

testDbBenchFiltersValid() {
    local bench_file="${RESULTS_DIR}/benchmark_dbbench.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_filters has_nofilt
    has_filters="$(json_contains "${bench_file}" bloom_ribbon_filters)"
    has_nofilt="$(json_contains "${bench_file}" no_filter)"
    assertTrue "Should contain bloom_ribbon_filters" "[ ${has_filters} -eq 1 ]"
    assertTrue "Should contain no_filter baseline" "[ ${has_nofilt} -eq 1 ]"
}

testMicroBenchmarkProducesResults() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    assertTrue "Micro benchmark JSON should exist" "[ -f '${bench_file}' ]"
}

testMicroBenchmarkAllCategoriesPresent() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_write has_read has_delete has_mixed has_checksum
    has_write="$(json_contains "${bench_file}" write_operations)"
    has_read="$(json_contains "${bench_file}" read_operations)"
    has_delete="$(json_contains "${bench_file}" delete_operations)"
    has_mixed="$(json_contains "${bench_file}" mixed_operations)"
    has_checksum="$(json_contains "${bench_file}" hash_checksum)"
    assertTrue "Should have write_operations" "[ ${has_write} -eq 1 ]"
    assertTrue "Should have read_operations" "[ ${has_read} -eq 1 ]"
    assertTrue "Should have delete_operations" "[ ${has_delete} -eq 1 ]"
    assertTrue "Should have mixed_operations" "[ ${has_mixed} -eq 1 ]"
    assertTrue "Should have hash_checksum" "[ ${has_checksum} -eq 1 ]"
}

testMicroCRC32CARM64Performance() {
    local bench_file="${RESULTS_DIR}/micro_benchmark.json"
    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi
    local has_crc has_xx
    has_crc="$(json_contains "${bench_file}" crc32c)"
    has_xx="$(json_contains "${bench_file}" xxhash)"
    echo "[DIAG] CRC32C found: ${has_crc}, xxhash found: ${has_xx}"
    assertTrue "Should have CRC32C benchmark" "[ ${has_crc} -eq 1 ]"
    assertTrue "Should have xxhash benchmark" "[ ${has_xx} -eq 1 ]"
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
    local has_ycsb has_dbbench has_micro
    has_ycsb="$(json_contains "${agg_file}" ycsb)"
    has_dbbench="$(json_contains "${agg_file}" dbbench)"
    has_micro="$(json_contains "${agg_file}" micro)"
    assertTrue "Should contain ycsb benchmark data" "[ ${has_ycsb} -eq 1 ]"
    assertTrue "Should contain db_bench data" "[ ${has_dbbench} -eq 1 ]"
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

    log "START" "RocksDB ARM64 Benchmark v${SOFTWARE_VERSION}"

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
    printf 'Usage: rocksdb_test.sh [OPTIONS]\n\n'
    printf 'RocksDB ARM64 Performance Benchmark v%s\n\n' "${SOFTWARE_VERSION}"
    printf 'Options:\n'
    printf '  --check     Check prerequisites only\n'
    printf '  -h, --help  Show usage\n\n'
    printf 'Environment variables:\n'
    printf '  ROCKSDB_SRC      RocksDB source directory (default: %s)\n' "${ROCKSDB_SRC}"
    printf '  DB_BENCH_PATH    db_bench binary path (default: %s)\n' "${DB_BENCH_PATH}"
    printf '  NUM_KEYS         Number of keys for benchmarks (default: 1000000)\n'
    printf '  VALUE_SIZE       Value size in bytes (default: 256)\n'
    printf '  THREADS          Number of threads (default: 16)\n'
    printf '  ITERATIONS       Number of iterations (default: 1)\n\n'
    printf 'Examples:\n'
    printf '  ./rocksdb_test.sh                    # Full benchmark + shUnit2 validation\n'
    printf '  ./rocksdb_test.sh --check            # Check prerequisites only\n'
    printf '  ITERATIONS=3 ./rocksdb_test.sh       # 3 iterations per benchmark\n'
}

if [ "${1:-}" != "--shunit2-run" ]; then
    main "$@"
fi
