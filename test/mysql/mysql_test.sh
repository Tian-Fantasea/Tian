#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"
RESULTS_JSON="${RESULTS_DIR}/results.json"
MYSQL_VERSION="${MYSQL_VERSION:-8.4.9}"
TABLE_SIZE="${TABLE_SIZE:-100000}"
SYSBENCH_THREADS="${SYSBENCH_THREADS:-16}"
ITERATIONS="${ITERATIONS:-1}"
MYSQL_PORT="${MYSQL_PORT:-3307}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-bench123}"
SHUNIT_PARENT="${SCRIPT_DIR}/mysql_test.sh"

MIN_TPS_THRESHOLD=100
MAX_LATENCY_P95_MS=50

download_shunit2() {
    if [ -f "${SCRIPT_DIR}/shunit2" ]; then
        return 0
    fi
    local mirrors=(
        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
        "https://raw.githubusercontent.com/kward/shunit2/refs/heads/master/shunit2"
    )
    for mirror_url in "${mirrors[@]}"; do
        curl --connect-timeout 30 --max-time 60 -sL "${mirror_url}" -o "${SCRIPT_DIR}/shunit2" 2>/dev/null && {
            if [ -s "${SCRIPT_DIR}/shunit2" ]; then
                chmod +x "${SCRIPT_DIR}/shunit2"
                echo "[SETUP] shUnit2 downloaded from ${mirror_url}"
                return 0
            fi
        }
        rm -f "${SCRIPT_DIR}/shunit2"
    done
    for mirror_url in "${mirrors[@]}"; do
        wget --timeout=30 --tries=2 -q -O "${SCRIPT_DIR}/shunit2" "${mirror_url}" 2>/dev/null && {
            if [ -s "${SCRIPT_DIR}/shunit2" ]; then
                chmod +x "${SCRIPT_DIR}/shunit2"
                echo "[SETUP] shUnit2 downloaded from ${mirror_url}"
                return 0
            fi
        }
        rm -f "${SCRIPT_DIR}/shunit2"
    done
    echo "[ERROR] Failed to download shUnit2 from all mirrors"
    return 1
}

json_get() { python3 "${JSON_HELPER}" "$1" get "$2" "$3"; }
json_field_exists() { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }
json_contains() { python3 "${JSON_HELPER}" "$1" contains "$2"; }

oneTimeSetUp() {
    mkdir -p "${RESULTS_DIR}"
    download_shunit2 || true
}

check_prerequisites() {
    if ! command -v mysql &>/dev/null; then
        echo "[SKIP] mysql not installed"
        startSkipping
        return
    fi
    if ! command -v mysqld &>/dev/null; then
        echo "[SKIP] mysqld not installed"
        startSkipping
        return
    fi
    if ! command -v sysbench &>/dev/null; then
        echo "[SKIP] sysbench not installed"
        startSkipping
        return
    fi
}

collect_version_info() {
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ | tr -d '\n\t')"
    local arch
    arch="$(uname -m | tr -d '\n\t')"
    local kernel
    kernel="$(uname -r | tr -d '\n\t')"
    local os
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    local cpu_model
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || grep 'Model Name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo 'unknown')"
    local cores
    cores="$(nproc 2>/dev/null || echo 0)"
    local mem_mb
    mem_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"
    local mysql_ver
    mysql_ver="$(mysql -V 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    local sysbench_ver
    sysbench_ver="$(sysbench --version 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    local compile_machine
    compile_machine="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'version_compile_machine';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"
    local innodb_buffer
    innodb_buffer="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"
    local max_conn
    max_conn="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'max_connections';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"
    local flush_log
    flush_log="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"
    local sync_binlog
    sync_binlog="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'sync_binlog';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"
    local thread_cache
    thread_cache="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'thread_cache_size';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"
    local table_open_cache
    table_open_cache="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'table_open_cache';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"
    local sort_buffer
    sort_buffer="$(mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -P "${MYSQL_PORT}" -e "SHOW VARIABLES LIKE 'sort_buffer_size';" 2>/dev/null | tail -1 | awk '{print $2}' | tr -d '\n\t' || echo 'unknown')"

    python3 "${JSON_HELPER}" "${RESULTS_JSON}" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${mysql_ver}" "${sysbench_ver}" \
        "${compile_machine}" "${innodb_buffer}" "${max_conn}" \
        "${flush_log}" "${sync_binlog}" "${thread_cache}" \
        "${table_open_cache}" "${sort_buffer}"
}

run_benchmarks() {
    echo "[BENCH] Running OLTP benchmark (Phase 3a)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_oltp.py" \
        --results-json "${RESULTS_JSON}" \
        --section oltp_benchmark \
        --table-size "${TABLE_SIZE}" \
        --threads "${SYSBENCH_THREADS}" \
        --iterations "${ITERATIONS}" \
        --mysql-port "${MYSQL_PORT}" \
        --mysql-user "${MYSQL_USER}" \
        --mysql-password "${MYSQL_PASSWORD}"

    echo "[BENCH] Running OLAP benchmark (Phase 3b)..."
    python3 "${SCRIPT_DIR}/scripts/benchmark_olap.py" \
        --results-json "${RESULTS_JSON}" \
        --section olap_benchmark \
        --table-size "${TABLE_SIZE}" \
        --iterations "${ITERATIONS}" \
        --mysql-port "${MYSQL_PORT}" \
        --mysql-user "${MYSQL_USER}" \
        --mysql-password "${MYSQL_PASSWORD}"

    echo "[BENCH] Running micro benchmark (Phase 3c)..."
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-json "${RESULTS_JSON}" \
        --section micro_benchmark \
        --iterations "${ITERATIONS}" \
        --mysql-port "${MYSQL_PORT}" \
        --mysql-user "${MYSQL_USER}" \
        --mysql-password "${MYSQL_PASSWORD}"
}

oneTimeTearDown() {
    if [ -f "${RESULTS_JSON}" ]; then
        echo "[REPORT] Generating text summary..."
        python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
            --input "${RESULTS_JSON}" \
            --output "${RESULTS_DIR}/results.txt"

        echo "[REPORT] Generating HTML report..."
        python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
            --input "${RESULTS_JSON}" \
            --output "${RESULTS_DIR}/results.html"
    fi
}

setUp() { :; }
tearDown() { :; }

testArchitectureIsARM64() {
    check_prerequisites
    local arch
    arch="$(uname -m)"
    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \
        "[ '${arch}' = 'aarch64' ] || [ '${arch}' = 'arm64' ]"
}

testMysqlIsInstalled() {
    check_prerequisites
    assertTrue "mysql binary should exist" \
        "[ -x '$(command -v mysql 2>/dev/null)' ] || [ -f '/usr/bin/mysql' ] || [ -f '/usr/local/bin/mysql' ]"
}

testMysqldIsInstalled() {
    check_prerequisites
    assertTrue "mysqld binary should exist" \
        "[ -x '$(command -v mysqld 2>/dev/null)' ] || [ -f '/usr/sbin/mysqld' ] || [ -f '/usr/local/bin/mysqld' ]"
}

testSysbenchIsInstalled() {
    check_prerequisites
    assertTrue "sysbench binary should exist" \
        "[ -x '$(command -v sysbench 2>/dev/null)' ]"
}

testCompileMachineIsARM64() {
    check_prerequisites
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local compile_machine
    compile_machine="$(json_get "${RESULTS_JSON}" version_info compile_machine)"
    if [ "${compile_machine}" = "None" ] || [ "${compile_machine}" = "N/A" ] || [ -z "${compile_machine}" ]; then
        startSkipping
        return
    fi
    assertTrue "MySQL compile machine should be aarch64 or arm64, got: ${compile_machine}" \
        "[ '${compile_machine}' = 'aarch64' ] || [ '${compile_machine}' = 'arm64' ]"
}

testInnoDBBufferPoolConfigured() {
    check_prerequisites
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local buffer
    buffer="$(json_get "${RESULTS_JSON}" version_info innodb_buffer_pool_size)"
    if [ "${buffer}" = "None" ] || [ "${buffer}" = "N/A" ] || [ -z "${buffer}" ]; then
        startSkipping
        return
    fi
    assertNotNull "InnoDB buffer pool should be set" "${buffer}"
}

testResultsJsonExists() {
    collect_version_info
    assertTrue "results.json should exist" "[ -f '${RESULTS_JSON}' ]"
}

testResultsJsonHasVersionInfo() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" version_info)"
    assertTrue "results.json should have version_info section" "[ '${has}' = '1' ]"
}

testResultsJsonHasArchitecture() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local arch
    arch="$(json_get "${RESULTS_JSON}" architecture)"
    assertNotNull "Architecture should be set in results.json" "${arch}"
}

testResultsJsonHasSoftwareVersion() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local ver
    ver="$(json_get "${RESULTS_JSON}" version)"
    assertNotNull "Software version should be set in results.json" "${ver}"
}

testBenchmarkOltInResultsJson() {
    run_benchmarks
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" oltp_benchmark)"
    assertTrue "results.json should have oltp_benchmark section" "[ '${has}' = '1' ]"
}

testBenchmarkOltpHasRequiredFields() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" benchmark)"
    assertTrue "oltp_benchmark should contain 'benchmark' field" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" results)"
    assertTrue "oltp_benchmark should contain 'results' field" "[ '${content}' = '1' ]"
}

testBenchmarkOlapInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" olap_benchmark)"
    assertTrue "results.json should have olap_benchmark section" "[ '${has}' = '1' ]"
}

testBenchmarkMicroInResultsJson() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local has
    has="$(json_field_exists "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "results.json should have micro_benchmark section" "[ '${has}' = '1' ]"
}

testResultsJsonContainsAllBenchmarks() {
    if [ ! -f "${RESULTS_JSON}" ]; then
        startSkipping
        return
    fi
    local content
    content="$(json_contains "${RESULTS_JSON}" oltp_benchmark)"
    assertTrue "Should contain oltp_benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" olap_benchmark)"
    assertTrue "Should contain olap_benchmark" "[ '${content}' = '1' ]"
    content="$(json_contains "${RESULTS_JSON}" micro_benchmark)"
    assertTrue "Should contain micro_benchmark" "[ '${content}' = '1' ]"
}

testHtmlReportGenerated() {
    assertTrue "HTML report should exist" "[ -f '${RESULTS_DIR}/results.html' ]"
}

testSummaryReportGenerated() {
    assertTrue "Summary report should exist" "[ -f '${RESULTS_DIR}/results.txt' ]"
}

testLogFileGenerated() {
    assertTrue "Log file should exist" "[ -f '${RESULTS_DIR}/results.log' ]"
}

. "${SCRIPT_DIR}/shunit2"
