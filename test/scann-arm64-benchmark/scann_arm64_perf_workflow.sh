#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SCANN_VERSION="${SCANN_VERSION:-1.4.2}"
DATA_SCALE="${DATA_SCALE:-1M}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -p, --phases PHASES       Comma-separated phases (1,2,3,4 or sub-phases like 3a,3b)"
    echo "  -s, --software-version    ScaNN version to test (default: 1.4.2)"
    echo "  -v, --data-scale          Dataset scale: 1M, 10M (default: 1M)"
    echo "  -d, --data-size           Data dimension: 32, 64, 96, 128, 256 (default: 128)"
    echo "  -i, --iterations          Number of iterations per test (default: 3)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Full workflow"
    echo "  $0 -p 3a                              # Run ANN benchmark only"
    echo "  $0 -p 3a,3b -i 5 -v 1M               # Run ANN + micro benchmarks, 5 iterations"
    echo "  $0 -s 1.3.5 -d 96                     # Test ScaNN 1.3.5 with 96-dim vectors"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--phases)    PHASES="$2"; shift 2 ;;
        -s|--software-version) SCANN_VERSION="$2"; shift 2 ;;
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
        sudo apt-get install -y -qq python3 python3-pip python3-dev wget curl
        LIBSTDCXX_VER=$(dpkg-query -Wf '${Version}' libstdc++6 2>/dev/null || echo "unknown")
        echo "[SETUP] libstdc++ version: $LIBSTDCXX_VER (ScaNN requires >= 3.4.23)"
    elif command -v yum &>/dev/null; then
        sudo yum install -y python3 python3-pip python3-devel wget curl
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip python3-devel wget curl
    fi
    echo "[SETUP] System dependencies installed"

    echo "[SETUP] 1.3 Installing Python dependencies..."
    python3 -m pip install --upgrade pip --quiet
    python3 -m pip install numpy --quiet
    echo "[SETUP] Python dependencies installed"

    echo "[SETUP] 1.4 Installing ScaNN v${SCANN_VERSION}..."
    python3 -m pip install scann==${SCANN_VERSION} --quiet || {
        echo "[SETUP] pip install failed, trying google-scann package name..."
        python3 -m pip install google-scann==${SCANN_VERSION} --quiet || {
            echo "[SETUP] Both package names failed, building from source..."
            echo "[SETUP] Source build requires Bazel 7.x, Clang 19, and GCC 9+"
            SCANN_SRC="/tmp/scann-${SCANN_VERSION}"
            if [[ ! -d "${SCANN_SRC}" ]]; then
                git clone --depth 1 --branch v${SCANN_VERSION} \
                    https://github.com/google-research/google-research.git "${SCANN_SRC}/google-research" || {
                    git clone --depth 1 https://github.com/google-research/google-research.git "${SCANN_SRC}/google-research"
                }
            fi
            cd "${SCANN_SRC}/google-research/scann"
            python3 configure.py
            CC=clang-19 bazel build -c opt --features=thin_lto \
                --copt=-march=armv8-a+simd --cxxopt="-std=c++17" \
                --copt=-fsized-deallocation --copt=-w :build_pip_pkg
            ./bazel-bin/build_pip_pkg
            python3 -m pip install scann*.whl --quiet
            cd "${SCRIPT_DIR}"
        }
    }

    echo "[SETUP] 1.5 Validating ScaNN installation..."
    python3 -c "import scann; print(f'ScaNN imported successfully')"
    echo "[SETUP] Phase 1 complete"
}

phase2_verify() {
    echo "[VERIFY] Phase 2: Verify Installation & Collect Version Info"
    echo "[VERIFY] 2.1 Running verification script..."
    python3 "${SCRIPT_DIR}/scripts/verify_python.py" \
        --results-dir "${RESULTS_DIR}" \
        --scann-version "${SCANN_VERSION}"

    echo "[VERIFY] 2.2 Running sanity check: ScaNN search on 1000 vectors..."
    python3 -c "
import scann
import numpy as np
dim = 128
nb = 1000
np.random.seed(42)
data = np.random.random((nb, dim)).astype('float32')
searcher = scann.scann_ops_pybind.builder(data, 10, 'squared_l2').score_brute_force().build()
neighbors, distances = searcher.search(data[:5], final_num_neighbors=5)
print(f'[VERIFY] Sanity check passed: top-5 neighbors for query 0 = {neighbors[0]}')
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
    echo "[BENCH-MICRO] Phase 3b: Micro Benchmarks (Index operations & ScaNN parameter sweep)"
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
echo " ScaNN ARM64 Performance Benchmark Workflow"
echo " Version: ${SCANN_VERSION} | Scale: ${DATA_SCALE} | Dim: ${DATA_DIM}"
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