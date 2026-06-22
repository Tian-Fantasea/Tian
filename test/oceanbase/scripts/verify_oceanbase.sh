#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OB_HOME="${SCRIPT_DIR}/oceanbase"
OBD_HOME="${SCRIPT_DIR}/obd"
BENCHMARKSQL_HOME="${SCRIPT_DIR}/BenchmarkSQL-5.0"
RESULTS_DIR="${SCRIPT_DIR}/results"
LOG_FILE="${RESULTS_DIR}/verify.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}"

check_ob_binary() {
    if [ -x "${OB_HOME}/bin/observer" ]; then
        log "VERIFY" "observer binary found at ${OB_HOME}/bin/observer"
        return 0
    elif command -v observer >/dev/null 2>&1; then
        log "VERIFY" "observer found in PATH"
        return 0
    else
        log "ERROR" "observer binary not found"
        return 1
    fi
}

check_obd_binary() {
    if [ -x "${OBD_HOME}/bin/obd" ]; then
        log "VERIFY" "obd binary found at ${OBD_HOME}/bin/obd"
        return 0
    elif command -v obd >/dev/null 2>&1; then
        log "VERIFY" "obd found in PATH"
        return 0
    else
        log "ERROR" "obd binary not found"
        return 1
    fi
}

check_java() {
    if command -v java >/dev/null 2>&1; then
        local java_ver
        java_ver="$(java -version 2>&1 | head -1 | tr -d '\n\t')"
        log "VERIFY" "Java found: ${java_ver}"
        return 0
    else
        log "ERROR" "Java not found (required for BenchmarkSQL TPC-C)"
        return 1
    fi
}

check_mysql_client() {
    if command -v mysql >/dev/null 2>&1; then
        log "VERIFY" "mysql client found"
        return 0
    else
        log "WARN" "mysql client not found, some tests may fail"
        return 1
    fi
}

get_ob_version() {
    if [ -x "${OB_HOME}/bin/observer" ]; then
        "${OB_HOME}/bin/observer" --version 2>&1 | head -1 | tr -d '\n\t'
    elif command -v observer >/dev/null 2>&1; then
        observer --version 2>&1 | head -1 | tr -d '\n\t'
    else
        echo "unknown"
    fi
}

get_obd_version() {
    if [ -x "${OBD_HOME}/bin/obd" ]; then
        "${OBD_HOME}/bin/obd" --version 2>&1 | head -1 | tr -d '\n\t'
    elif command -v obd >/dev/null 2>&1; then
        obd display-trace 2>&1 | head -1 | tr -d '\n\t'
    else
        echo "unknown"
    fi
}

get_system_info() {
    local arch kernel os_name cpu_model cores mem_mb
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os_name="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || uname -m)"
    cores="$(nproc 2>/dev/null || echo 1)"
    mem_mb="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)"
    echo "${arch}|${kernel}|${os_name}|${cpu_model}|${cores}|${mem_mb}"
}

write_version_info() {
    local timestamp arch kernel os_name cpu_model cores mem_mb
    local ob_version obd_ver java_ver warehouse terminal
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local sys_info
    sys_info="$(get_system_info)"
    arch="$(echo "${sys_info}" | cut -d'|' -f1)"
    kernel="$(echo "${sys_info}" | cut -d'|' -f2)"
    os_name="$(echo "${sys_info}" | cut -d'|' -f3)"
    cpu_model="$(echo "${sys_info}" | cut -d'|' -f4)"
    cores="$(echo "${sys_info}" | cut -d'|' -f5)"
    mem_mb="$(echo "${sys_info}" | cut -d'|' -f6)"
    ob_version="$(get_ob_version)"
    obd_ver="$(get_obd_version)"
    java_ver="$(java -version 2>&1 | head -1 | tr -d '\n\t')"
    warehouse="${WAREHOUSE_COUNT:-10}"
    terminal="${TERMINAL_COUNT:-10}"

    python3 "${SCRIPT_DIR}/json_helper.py" \
        "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${ob_version}" "${obd_ver}" "${java_ver}" \
        "${OB_HOME}" "${warehouse}" "${terminal}"

    log "VERIFY" "Version info written to ${RESULTS_DIR}/version_info.json"
}

main() {
    log "VERIFY" "Starting OceanBase installation verification..."
    check_ob_binary || log "WARN" "observer binary not found (will use synthetic benchmarks)"
    check_obd_binary || log "WARN" "obd binary not found (will use synthetic benchmarks)"
    check_java || log "WARN" "Java not found (TPC-C BenchmarkSQL may not work)"
    check_mysql_client || log "WARN" "mysql client not found (some tests may fail)"
    write_version_info
    log "VERIFY" "Verification complete."
}

main "$@"