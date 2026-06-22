#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="faiss"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-1.14.2}"
DATA_SCALE="${DATA_SCALE:-1M}"
DATA_DIM="${DATA_DIM:-128}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
LOG_FILE="${RESULTS_DIR}/workflow.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}"

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        curl -sL https://raw.githubusercontent.com/kward/shunit2/master/shunit2 \
            -o "${SCRIPT_DIR}/shunit2"
        chmod +x "${SCRIPT_DIR}/shunit2"
    fi
}

phase1_install() {
    log "PHASE1" "Phase 1: Environment Preparation & Installation"
    log "PHASE1" "1.1 Verifying ARM64 architecture..."
    local arch
    arch="$(uname -m)"
    if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
        log "ERROR" "This benchmark requires ARM64. Current: ${arch}"
        return 1
    fi
    log "PHASE1" "Architecture confirmed: ${arch}"

    log "PHASE1" "1.2 Installing system dependencies..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq cmake g++ python3 python3-venv python3-dev \
            libopenblas-dev liblapack-dev wget curl bc
    elif command -v yum &>/dev/null; then
        sudo yum install -y cmake gcc-c++ python3 python3-pip python3-devel \
            openblas-devel lapack-devel wget curl bc
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y cmake gcc-c++ python3 python3-pip python3-devel \
            openblas-devel lapack-devel wget curl bc
    fi
    log "PHASE1" "System dependencies installed"

    log "PHASE1" "1.3 Installing Python dependencies via venv..."
    if [ ! -f "${SCRIPT_DIR}/venv/bin/pip" ]; then
        rm -rf "${SCRIPT_DIR}/venv"
        python3 -m venv "${SCRIPT_DIR}/venv"
        "${SCRIPT_DIR}/venv/bin/pip" install --quiet --upgrade pip
    fi
    "${SCRIPT_DIR}/venv/bin/pip" install --quiet numpy
    export PATH="${SCRIPT_DIR}/venv/bin:${PATH}"
    log "PHASE1" "Python dependencies installed"

    log "PHASE1" "1.4 Installing Faiss v${SOFTWARE_VERSION}..."
    "${SCRIPT_DIR}/venv/bin/pip" install faiss-cpu==${SOFTWARE_VERSION} --quiet || {
        log "PHASE1" "pip install failed, attempting conda install..."
        if command -v conda &>/dev/null; then
            conda install -c pytorch faiss-cpu=${SOFTWARE_VERSION} -y
        else
            log "PHASE1" "conda not available, building from source..."
            local FAISS_SRC="/tmp/faiss-${SOFTWARE_VERSION}"
            if [ ! -d "${FAISS_SRC}" ]; then
                git clone --depth 1 --branch v${SOFTWARE_VERSION} \
                    https://github.com/facebookresearch/faiss.git "${FAISS_SRC}" || {
                    git clone --depth 1 https://github.com/facebookresearch/faiss.git "${FAISS_SRC}"
                }
            fi
            mkdir -p "${FAISS_SRC}/build" && cd "${FAISS_SRC}/build"
            cmake .. \
                -DFAISS_ENABLE_GPU=OFF \
                -DCMAKE_C_FLAGS="-march=armv8-a" \
                -DCMAKE_CXX_FLAGS="-march=armv8-a" \
                -DBUILD_TESTING=OFF \
                -DFAISS_OPT_LEVEL=generic
            make -j 4 faiss
            sudo make install
            cd "${SCRIPT_DIR}"
        fi
    }

    log "PHASE1" "1.5 Validating Faiss installation..."
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/verify_python.py" \
        --results-dir "${RESULTS_DIR}" \
        --faiss-version "${SOFTWARE_VERSION}" \
        --sanity-check
    log "PHASE1" "Phase 1 complete"
}

phase2_verify() {
    log "PHASE2" "Phase 2: Verify Installation & Collect Version Info"
    log "PHASE2" "2.1 Running verification script..."
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/verify_python.py" \
        --results-dir "${RESULTS_DIR}" \
        --faiss-version "${SOFTWARE_VERSION}"

    log "PHASE2" "2.2 Collecting version info via json_helper..."
    local arch kernel os_name cpu_model cores mem_mb python_ver faiss_ver numpy_ver blas
    arch="$(uname -m | tr -d '\n\t')"
    kernel="$(uname -r | tr -d '\n\t')"
    os_name="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo 'Unknown')"
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t')"
    if [ -z "${cpu_model}" ]; then
        local num_proc
        num_proc="$(grep -c 'processor' /proc/cpuinfo 2>/dev/null || echo 0)"
        cpu_model="ARM64 CPU (${num_proc} cores)"
    fi
    cores="$(grep -c 'processor' /proc/cpuinfo 2>/dev/null || echo 0)"
    mem_mb="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)"
    python_ver="$(python3 --version 2>&1 | tr -d '\n\t')"
    faiss_ver="$(python3 -c "import faiss; print(faiss.__version__)" 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    numpy_ver="$(python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null | tr -d '\n\t' || echo 'unknown')"
    blas="$(python3 -c "import numpy; numpy.show_config()" 2>/dev/null | grep -c 'openblas' | tr -d '\n\t' || echo '0')"
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%S | tr -d '\n\t')"

    python3 "${SCRIPT_DIR}/scripts/json_helper.py" \
        "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_VERSION}" "Python" \
        "${python_ver}" "${faiss_ver}" "${numpy_ver}" "${blas}" "${cores}"

    log "PHASE2" "Phase 2 complete"
}

phase3a_ann() {
    log "ANN" "Phase 3a: ANN Benchmark (ann-benchmarks methodology)"
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/benchmark_ann.py" \
        --results-dir "${RESULTS_DIR}" \
        --data-scale "${DATA_SCALE}" \
        --data-dim "${DATA_DIM}" \
        --iterations "${ITERATIONS}"
}

phase3b_micro() {
    log "MICRO" "Phase 3b: Micro Benchmarks (Index operations)"
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --data-scale "${DATA_SCALE}" \
        --data-dim "${DATA_DIM}" \
        --iterations "${ITERATIONS}"
}

phase3_run_benchmarks() {
    log "BENCH" "Phase 3: Running Performance Benchmarks"
    local IFS=','
    for p in ${PHASES}; do
        case "${p}" in
            3a) phase3a_ann ;;
            3b) phase3b_micro ;;
            3)  phase3a_ann; phase3b_micro ;;
            *)  ;;
        esac
    done
}

phase4_results() {
    log "RESULTS" "Phase 4: Results Collection & Presentation"
    log "RESULTS" "4.1 Aggregating all JSON results..."
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        --results-dir "${RESULTS_DIR}"

    log "RESULTS" "4.2 Generating text summary..."
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --results-dir "${RESULTS_DIR}"

    log "RESULTS" "4.3 Generating HTML report..."
    "${SCRIPT_DIR}/venv/bin/python3" "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --results-dir "${RESULTS_DIR}"

    log "RESULTS" "Phase 4 complete"
}

run_phases() {
    local IFS=','
    for p in ${PHASES}; do
        case "${p}" in
            1)  phase1_install ;;
            2)  phase2_verify ;;
            3a) phase3a_ann ;;
            3b) phase3b_micro ;;
            3)  phase3_run_benchmarks ;;
            4)  phase4_results ;;
            *)  log "WARN" "Unknown phase: ${p}" ;;
        esac
    done
}

run_tests() {
    download_shunit2
    log "TEST" "Running shUnit2 test suite..."
    "${SCRIPT_DIR}/${SOFTWARE_NAME}_arm64_perf_test.sh"
}

usage() {
    printf '%s\n' "Usage: ${SOFTWARE_NAME}_arm64_perf_workflow.sh [OPTIONS]"
    printf '%s\n' ""
    printf '%s\n' "Options:"
    printf '%s\n' "  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b)"
    printf '%s\n' "  -s, --software-version   Faiss version to test (default: ${SOFTWARE_VERSION})"
    printf '%s\n' "  -v, --data-scale         Dataset scale: 1M, 10M, 100M (default: ${DATA_SCALE})"
    printf '%s\n' "  -d, --data-size          Data dimension: 32,64,96,128,256 (default: ${DATA_DIM})"
    printf '%s\n' "  -i, --iterations         Number of iterations per test (default: ${ITERATIONS})"
    printf '%s\n' "  -t, --test-only          Run only shUnit2 validation tests"
    printf '%s\n' "  -h, --help               Show this help message"
    printf '%s\n' ""
    printf '%s\n' "Examples:"
    printf '%s\n' "  $0                          # Full workflow"
    printf '%s\n' "  $0 -p 3a                    # Run ANN benchmark only"
    printf '%s\n' "  $0 -p 3a,3b -i 5 -v 10M    # ANN + micro, 5 iterations, 10M vectors"
    printf '%s\n' "  $0 -t                       # Run shUnit2 test validation only"
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)      PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -v|--data-scale)  DATA_SCALE="$2"; shift 2 ;;
            -d|--data-size)   DATA_DIM="$2"; shift 2 ;;
            -i|--iterations)  ITERATIONS="$2"; shift 2 ;;
            -t|--test-only)   test_only=1; shift ;;
            -h|--help)        usage; exit 0 ;;
            *)                log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    printf '%s\n' "============================================================"
    printf '%s\n' " Faiss ARM64 Performance Benchmark Workflow"
    printf '%s\n' " Version: ${SOFTWARE_VERSION} | Scale: ${DATA_SCALE} | Dim: ${DATA_DIM}"
    printf '%s\n' " Architecture: $(uname -m) | Iterations: ${ITERATIONS}"
    printf '%s\n' "============================================================"

    if [ "${test_only}" -eq 1 ]; then
        run_tests
    else
        run_phases
        run_tests
    fi
}

main "$@"