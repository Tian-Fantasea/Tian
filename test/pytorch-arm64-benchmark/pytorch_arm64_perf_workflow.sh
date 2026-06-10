#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
PYTORCH_VERSION="${PYTORCH_VERSION:-2.7.0}"
DATA_SCALE="${DATA_SCALE:-1M}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -p, --phases PHASES       Comma-separated phases (1,2,3,4 or sub-phases like 3a,3b,3c)"
    echo "  -s, --software-version    PyTorch version to test (default: 2.7.0)"
    echo "  -v, --data-scale          Dataset scale: 1M, 10M samples (default: 1M)"
    echo "  -d, --data-size           Data dimension for micro benchmarks (default: 128)"
    echo "  -i, --iterations          Number of iterations per test (default: 3)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Full workflow"
    echo "  $0 -p 3a                              # Run operator benchmark only"
    echo "  $0 -p 3a,3b,3c -i 5                   # Run all benchmarks, 5 iterations"
    echo "  $0 -s 2.6.0 -v 1M                     # Test PyTorch 2.6.0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--phases)    PHASES="$2"; shift 2 ;;
        -s|--software-version) PYTORCH_VERSION="$2"; shift 2 ;;
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

    echo "[SETUP] 1.4 Installing PyTorch v${PYTORCH_VERSION} (CPU-only for ARM64)..."
    python3 -m pip install torch==${PYTORCH_VERSION} torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu --quiet || {
        echo "[SETUP] CPU wheel install failed, trying default pip index..."
        python3 -m pip install torch==${PYTORCH_VERSION} torchvision torchaudio --quiet || {
            echo "[SETUP] Default install also failed. Trying version with +cpu suffix..."
            python3 -m pip install torch==${PYTORCH_VERSION}+cpu torchvision torchaudio \
                --extra-index-url https://download.pytorch.org/whl/cpu --quiet || {
                echo "[SETUP] All install methods failed. Please install PyTorch manually."
                exit 1
            }
        }
    }

    echo "[SETUP] 1.5 Installing benchmark dependencies..."
    python3 -m pip install torchbenchmark --quiet 2>/dev/null || true
    python3 -m pip install timm --quiet 2>/dev/null || true
    echo "[SETUP] Phase 1 complete"
}

phase2_verify() {
    echo "[VERIFY] Phase 2: Verify Installation & Collect Version Info"
    echo "[VERIFY] 2.1 Running verification script..."
    python3 "${SCRIPT_DIR}/scripts/verify_python.py" \
        --results-dir "${RESULTS_DIR}" \
        --pytorch-version "${PYTORCH_VERSION}"

    echo "[VERIFY] 2.2 Running sanity check: tensor operations..."
    python3 -c "
import torch
print(f'[VERIFY] PyTorch version: {torch.__version__}')
print(f'[VERIFY] ARM64 build: {torch.version.debug if hasattr(torch.version, \"debug\") else \"N/A\"}')
x = torch.randn(100, 100)
y = torch.mm(x, x)
print(f'[VERIFY] Matrix multiply (100x100) result shape: {y.shape}')
z = torch.mean(y)
print(f'[VERIFY] Mean of result: {z.item():.6f}')
print(f'[VERIFY] Sanity check passed')
"

    echo "[VERIFY] Phase 2 complete"
}

phase3a_compute() {
    echo "[BENCH-COMPUTE] Phase 3a: Operator-Level Compute Benchmark"
    python3 "${SCRIPT_DIR}/scripts/benchmark_compute.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-dim "${DATA_DIM}"
}

phase3b_training() {
    echo "[BENCH-TRAINING] Phase 3b: Training Throughput Benchmark"
    python3 "${SCRIPT_DIR}/scripts/benchmark_training.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-scale "${DATA_SCALE}"
}

phase3c_micro() {
    echo "[BENCH-MICRO] Phase 3c: Micro Benchmarks (Memory & Compile)"
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-dim "${DATA_DIM}"
}

phase3_run() {
    echo "[BENCH] Phase 3: Running Performance Benchmarks"
    if should_run "3a"; then phase3a_compute; fi
    if should_run "3b"; then phase3b_training; fi
    if should_run "3c"; then phase3c_micro; fi
    if should_run "3"; then
        phase3a_compute
        phase3b_training
        phase3c_micro
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
echo " PyTorch ARM64 Performance Benchmark Workflow"
echo " Version: ${PYTORCH_VERSION} | Scale: ${DATA_SCALE} | Dim: ${DATA_DIM}"
echo " Architecture: $(uname -m) | Iterations: ${ITERATIONS}"
echo "============================================================"

IFS=',' read -ra PHASE_LIST <<< "$PHASES"
for p in "${PHASE_LIST[@]}"; do
    case "$p" in
        1) phase1_install ;;
        2) phase2_verify ;;
        3a) phase3a_compute ;;
        3b) phase3b_training ;;
        3c) phase3c_micro ;;
        3) phase3_run ;;
        4) phase4_results ;;
        *) echo "[WARN] Unknown phase: $p"; ;;
    esac
done

echo "============================================================"
echo " Benchmark workflow complete!"
echo " Results directory: ${RESULTS_DIR}"
echo "============================================================"