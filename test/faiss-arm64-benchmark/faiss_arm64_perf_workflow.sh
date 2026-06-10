#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
FAISS_VERSION="${FAISS_VERSION:-1.14.2}"
DATA_SCALE="${DATA_SCALE:-1M}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -p, --phases PHASES       Comma-separated phases (1,2,3,4 or sub-phases like 3a,3b)"
    echo "  -s, --software-version    Faiss version to test (default: 1.14.2)"
    echo "  -v, --data-scale          Dataset scale: 1M, 10M, 100M vectors (default: 1M)"
    echo "  -d, --data-size           Data dimension: 32, 64, 96, 128, 256 (default: 128)"
    echo "  -i, --iterations          Number of iterations per test (default: 3)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Full workflow"
    echo "  $0 -p 3a                              # Run ANN benchmark only"
    echo "  $0 -p 3a,3b -i 5 -v 10M              # Run ANN + micro benchmarks, 5 iterations, 10M vectors"
    echo "  $0 -s 1.9.0 -v 1M                     # Test Faiss 1.9.0 with 1M vectors"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--phases)    PHASES="$2"; shift 2 ;;
        -s|--software-version) FAISS_VERSION="$2"; shift 2 ;;
        -v|--data-scale) DATA_SCALE="$2"; shift 2 ;;
        -d|--data-size) DATA_DIM="$2"; shift 2 ;;
        -i|--iterations) ITERATIONS="$2"; shift 2 ;;
        -h|--help)      usage ;;
        *)              echo "Unknown option: $1"; usage ;;
    esac
done

DATA_DIM="${DATA_DIM:-128}"
mkdir -p "${RESULTS_DIR}"

should_run() {
    local phase="$1"
    IFS=',' read -ra PHASE_LIST <<< "$PHASES"
    for p in "${PHASE_LIST[@]}"; do
        if [[ "$p" == "$phase" ]]; then return 0; fi
    done
    return 1
}

phase1_install() {
    echo "[SETUP] Phase 1: Environment Preparation & Installation"
    echo "[SETUP] 1.1 Verifying ARM64 architecture..."
    ARCH=$(uname -m)
    if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
        echo "[ERROR] This benchmark requires ARM64 architecture. Current: $ARCH"
        exit 1
    fi
    echo "[SETUP] Architecture confirmed: $ARCH"

    echo "[SETUP] 1.2 Installing system dependencies..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq cmake g++ python3 python3-pip python3-dev \
            libopenblas-dev liblapack-dev wget curl
    elif command -v yum &>/dev/null; then
        sudo yum install -y cmake gcc-c++ python3 python3-pip python3-devel \
            openblas-devel lapack-devel wget curl
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y cmake gcc-c++ python3 python3-pip python3-devel \
            openblas-devel lapack-devel wget curl
    fi
    echo "[SETUP] System dependencies installed"

    echo "[SETUP] 1.3 Installing Python dependencies..."
    python3 -m pip install --upgrade pip --quiet
    python3 -m pip install numpy --quiet
    echo "[SETUP] Python dependencies installed"

    echo "[SETUP] 1.4 Installing Faiss v${FAISS_VERSION}..."
    python3 -m pip install faiss-cpu==${FAISS_VERSION} --quiet || {
        echo "[SETUP] pip install failed, attempting conda install..."
        if command -v conda &>/dev/null; then
            conda install -c pytorch faiss-cpu=${FAISS_VERSION} -y
        else
            echo "[SETUP] conda not available, building from source..."
            FAISS_SRC="/tmp/faiss-${FAISS_VERSION}"
            if [[ ! -d "${FAISS_SRC}" ]]; then
                git clone --depth 1 --branch v${FAISS_VERSION} \
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
            make -j$(nproc) faiss
            sudo make install
            cd "${SCRIPT_DIR}"
        fi
    }

    echo "[SETUP] 1.5 Validating Faiss installation..."
    python3 -c "import faiss; print(f'Faiss version: {faiss.__version__}')"
    echo "[SETUP] Phase 1 complete"
}

phase2_verify() {
    echo "[VERIFY] Phase 2: Verify Installation & Collect Version Info"
    echo "[VERIFY] 2.1 Running verification script..."
    python3 "${SCRIPT_DIR}/scripts/verify_python.py" \
        --results-dir "${RESULTS_DIR}" \
        --faiss-version "${FAISS_VERSION}"

    echo "[VERIFY] 2.2 Running sanity check: IndexFlatL2 search on 1000 vectors..."
    python3 -c "
import faiss
import numpy as np
d = 128
nb = 1000
np.random.seed(42)
xb = np.random.random((nb, d)).astype('float32')
xq = np.random.random((1, d)).astype('float32')
index = faiss.IndexFlatL2(d)
index.add(xb)
D, I = index.search(xq, 5)
print(f'[VERIFY] Sanity check passed: top-5 IDs={I[0]}, distances={D[0]}')
"

    echo "[VERIFY] Phase 2 complete"
}

phase3a_ann() {
    echo "[BENCH-ANN] Phase 3a: ANN Benchmark (Industry-standard ann-benchmarks methodology)"
    python3 "${SCRIPT_DIR}/scripts/benchmark_ann.py" \
        --results-dir "${RESULTS_DIR}" \
        --data-scale "${DATA_SCALE}" \
        --data-dim "${DATA_DIM}" \
        --iterations "${ITERATIONS}"
}

phase3b_micro() {
    echo "[BENCH-MICRO] Phase 3b: Micro Benchmarks (Index operations)"
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --data-scale "${DATA_SCALE}" \
        --data-dim "${DATA_DIM}" \
        --iterations "${ITERATIONS}"
}

phase3_run() {
    echo "[BENCH] Phase 3: Running Performance Benchmarks"
    if should_run "3a"; then phase3a_ann; fi
    if should_run "3b"; then phase3b_micro; fi
    if should_run "3"; then
        phase3a_ann
        phase3b_micro
    fi
}

phase4_results() {
    echo "[RESULTS] Phase 4: Results Collection & Presentation"
    echo "[RESULTS] 4.1 Aggregating all JSON results..."
    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        --results-dir "${RESULTS_DIR}"

    echo "[RESULTS] 4.2 Generating text summary..."
    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --results-dir "${RESULTS_DIR}"

    echo "[RESULTS] 4.3 Generating HTML report..."
    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --results-dir "${RESULTS_DIR}"

    echo "[RESULTS] Phase 4 complete"
}

echo "============================================================"
echo " Faiss ARM64 Performance Benchmark Workflow"
echo " Version: ${FAISS_VERSION} | Scale: ${DATA_SCALE} | Dim: ${DATA_DIM}"
echo " Architecture: $(uname -m) | Iterations: ${ITERATIONS}"
echo "============================================================"

IFS=',' read -ra PHASE_LIST <<< "$PHASES"
for p in "${PHASE_LIST[@]}"; do
    case "$p" in
        1) phase1_install ;;
        2) phase2_verify ;;
        3a) phase3a_ann ;;
        3b) phase3b_micro ;;
        3) phase3_run ;;
        4) phase4_results ;;
        *) echo "[WARN] Unknown phase: $p"; ;;
    esac
done

echo "============================================================"
echo " Benchmark workflow complete!"
echo " Results directory: ${RESULTS_DIR}"
echo "============================================================"