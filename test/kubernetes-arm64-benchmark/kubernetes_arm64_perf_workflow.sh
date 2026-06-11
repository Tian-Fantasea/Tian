#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="kubernetes"
SOFTWARE_VERSION="${VERSION:-1.33.12}"
DATA_SCALE="${DATA_SCALE:-1}"
DATA_SIZE="${DATA_SIZE:-100}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
LOG_FILE="${RESULTS_DIR}/workflow.log"
KIND_CLUSTER_NAME="arm64-perf-test"
KUBECONFIG_PATH="${RESULTS_DIR}/kubeconfig"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}"

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        local mirrors=(
            "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"
            "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"
            "https://mirrors.tuna.tsinghua.edu.cn/github-raw/kward/shunit2/master/shunit2"
        )
        local downloaded=0
        for mirror_url in "${mirrors[@]}"; do
            curl --connect-timeout 30 --max-time 60 -sL "${mirror_url}" -o "${SCRIPT_DIR}/shunit2" 2>/dev/null && {
                [ -s "${SCRIPT_DIR}/shunit2" ] && { downloaded=1; break; }
            }
            rm -f "${SCRIPT_DIR}/shunit2"
        done
        if [ "${downloaded}" -eq 0 ]; then
            for mirror_url in "${mirrors[@]}"; do
                wget --timeout=30 --tries=2 -q -O "${SCRIPT_DIR}/shunit2" "${mirror_url}" 2>/dev/null && {
                    [ -s "${SCRIPT_DIR}/shunit2" ] && { downloaded=1; break; }
                }
                rm -f "${SCRIPT_DIR}/shunit2"
            done
        fi
        if [ "${downloaded}" -eq 0 ]; then
            log "ERROR" "Failed to download shUnit2. Please download manually from https://github.com/kward/shunit2"
            return 1
        fi
        chmod +x "${SCRIPT_DIR}/shunit2"
    fi
}

download_kubectl() {
    local kubectl_path="${SCRIPT_DIR}/kubectl"
    if [ ! -x "${kubectl_path}" ]; then
        log "INSTALL" "Downloading kubectl v${SOFTWARE_VERSION} for ARM64..."
        local mirrors=(
            "https://dl.k8s.io/release/v${SOFTWARE_VERSION}/bin/linux/arm64/kubectl"
            "https://mirrors.aliyun.com/kubernetes-release/release/v${SOFTWARE_VERSION}/bin/linux/arm64/kubectl"
            "https://mirrors.tuna.tsinghua.edu.cn/kubernetes-release/release/v${SOFTWARE_VERSION}/bin/linux/arm64/kubectl"
        )
        local downloaded=0
        for mirror_url in "${mirrors[@]}"; do
            wget --timeout=60 --tries=2 -q -O "${kubectl_path}" "${mirror_url}" 2>/dev/null && {
                [ -s "${kubectl_path}" ] && { downloaded=1; break; }
            }
            rm -f "${kubectl_path}"
        done
        if [ "${downloaded}" -eq 0 ]; then
            for mirror_url in "${mirrors[@]}"; do
                curl --connect-timeout 60 --max-time 300 -L -o "${kubectl_path}" "${mirror_url}" 2>/dev/null && {
                    [ -s "${kubectl_path}" ] && { downloaded=1; break; }
                }
                rm -f "${kubectl_path}"
            done
        fi
        if [ "${downloaded}" -eq 0 ]; then
            log "ERROR" "Failed to download kubectl. Please download manually from https://dl.k8s.io"
            return 1
        fi
        chmod +x "${kubectl_path}"
    fi
    export PATH="${SCRIPT_DIR}:${PATH}"
}

download_kind() {
    local kind_path="${SCRIPT_DIR}/kind"
    if [ ! -x "${kind_path}" ]; then
        log "INSTALL" "Downloading kind for ARM64..."
        local kind_version="0.27.0"
        local mirrors=(
            "https://kind.sigs.k8s.io/dl/v${kind_version}/kind-linux-arm64"
            "https://github.com/kubernetes-sigs/kind/releases/download/v${kind_version}/kind-linux-arm64"
            "https://mirrors.aliyun.com/github-release/kubernetes-sigs/kind/v${kind_version}/kind-linux-arm64"
        )
        local downloaded=0
        for mirror_url in "${mirrors[@]}"; do
            wget --timeout=60 --tries=2 -q -O "${kind_path}" "${mirror_url}" 2>/dev/null && {
                [ -s "${kind_path}" ] && { downloaded=1; break; }
            }
            rm -f "${kind_path}"
        done
        if [ "${downloaded}" -eq 0 ]; then
            for mirror_url in "${mirrors[@]}"; do
                curl --connect-timeout 60 --max-time 300 -L -o "${kind_path}" "${mirror_url}" 2>/dev/null && {
                    [ -s "${kind_path}" ] && { downloaded=1; break; }
                }
                rm -f "${kind_path}"
            done
        fi
        if [ "${downloaded}" -eq 0 ]; then
            log "ERROR" "Failed to download kind. Please download manually from https://kind.sigs.k8s.io"
            return 1
        fi
        chmod +x "${kind_path}"
    fi
    export PATH="${SCRIPT_DIR}:${PATH}"
}

setup_python_venv() {
    if [ ! -d "${SCRIPT_DIR}/venv" ]; then
        log "INSTALL" "Setting up Python venv..."
        python3 -m venv "${SCRIPT_DIR}/venv"
        "${SCRIPT_DIR}/venv/bin/pip" install --quiet numpy
    fi
    export PATH="${SCRIPT_DIR}/venv/bin:${PATH}"
}

phase1_install() {
    log "PHASE1" "=== Phase 1: Environment Preparation & Installation ==="

    local arch
    arch="$(uname -m)"
    if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
        log "ERROR" "This benchmark requires ARM64. Current: ${arch}"
        return 1
    fi
    log "PHASE1" "Architecture verified: ${arch}"

    if command -v apt-get &>/dev/null; then
        log "PHASE1" "Installing system dependencies (apt-get)..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq docker.io containerd wget curl python3 python3-venv gcc make &>/dev/null || true
    elif command -v yum &>/dev/null; then
        log "PHASE1" "Installing system dependencies (yum)..."
        sudo yum install -y docker containerd wget curl python3 python3-venv gcc make &>/dev/null || true
    elif command -v dnf &>/dev/null; then
        log "PHASE1" "Installing system dependencies (dnf)..."
        sudo dnf install -y docker containerd wget curl python3 python3-venv gcc make &>/dev/null || true
    fi

    if ! command -v docker &>/dev/null && ! command -v containerd &>/dev/null; then
        log "ERROR" "Docker or containerd is required for kind. Please install one."
        return 1
    fi

    if ! systemctl is-active docker &>/dev/null 2>&1; then
        sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true
    fi

    download_kubectl
    download_kind
    setup_python_venv

    log "PHASE1" "Creating kind cluster '${KIND_CLUSTER_NAME}' with Kubernetes v${SOFTWARE_VERSION}..."
    if kind get clusters 2>/dev/null | grep -q "${KIND_CLUSTER_NAME}"; then
        log "PHASE1" "Kind cluster '${KIND_CLUSTER_NAME}' already exists, deleting..."
        kind delete cluster --name "${KIND_CLUSTER_NAME}" 2>/dev/null || true
    fi

    kind create cluster --name "${KIND_CLUSTER_NAME}" --image "kindest/node:v${SOFTWARE_VERSION}" --wait 300s --kubeconfig "${KUBECONFIG_PATH}" 2>&1 | tee -a "${LOG_FILE}"

    export KUBECONFIG="${KUBECONFIG_PATH}"

    log "PHASE1" "Waiting for cluster to be ready..."
    local ready=0
    for i in $(seq 1 30); do
        if kubectl get nodes 2>/dev/null | grep -q "Ready"; then
            ready=1
            break
        fi
        sleep 5
    done
    if [ "${ready}" -eq 0 ]; then
        log "ERROR" "Cluster failed to become ready within 150 seconds"
        return 1
    fi

    log "PHASE1" "Phase 1 complete. Kubernetes cluster running on ARM64."
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Installation Verification ==="

    export KUBECONFIG="${KUBECONFIG_PATH}"

    log "PHASE2" "Verifying kubectl connectivity..."
    kubectl cluster-info 2>&1 | tee -a "${LOG_FILE}"

    local nodes_ready
    nodes_ready="$(kubectl get nodes --no-headers 2>/dev/null | grep -c "Ready" || echo 0)"
    log "PHASE2" "Ready nodes: ${nodes_ready}"

    local kubectl_ver
    kubectl_ver="$(kubectl version --client --short 2>/dev/null || kubectl version --client 2>/dev/null | grep -o 'GitVersion:"[^"]*"' | head -1 | cut -d'"' -f2 | tr -d '\n\t')"

    local kube_server_ver
    kube_server_ver="$(kubectl version 2>/dev/null | grep -o 'serverVersion.*GitVersion:"[^"]*"' | grep -o 'GitVersion:"[^"]*"' | cut -d'"' -f2 | tr -d '\n\t' || echo "unknown")"

    local arch
    arch="$(uname -m | tr -d '\n\t')"
    local kernel
    kernel="$(uname -r | tr -d '\n\t')"
    local os
    os="$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 | tr -d '\n\t' || echo "unknown")"
    local cpu_model
    cpu_model="$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || grep 'CPU part' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d '\n\t' || echo "unknown")"
    local cores
    cores="$(nproc 2>/dev/null || echo 1)"
    local mem_mb
    mem_mb="$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"

    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' | tr -d '\n\t')"

    python3 "${SCRIPT_DIR}/scripts/json_helper.py" \
        "${RESULTS_DIR}/version_info.json" write_version_info \
        "${timestamp}" "${arch}" "${kernel}" "${os}" "${cpu_model}" \
        "${cores}" "${mem_mb}" "${SOFTWARE_VERSION}" "${kube_server_ver}" \
        "${kubectl_ver}" "${KIND_CLUSTER_NAME}" "${nodes_ready}" "${DATA_SCALE}"

    log "PHASE2" "Running verification script..."
    bash "${SCRIPT_DIR}/scripts/verify_go.sh" "${RESULTS_DIR}" "${SOFTWARE_VERSION}"

    log "PHASE2" "Phase 2 complete."
}

run_benchmark_pod_startup() {
    log "BENCH-3a" "=== Phase 3a: Pod Startup Latency Benchmark ==="
    export KUBECONFIG="${KUBECONFIG_PATH}"
    python3 "${SCRIPT_DIR}/scripts/benchmark_pod_startup.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}" \
        --kubeconfig "${KUBECONFIG_PATH}"
}

run_benchmark_api_latency() {
    log "BENCH-3b" "=== Phase 3b: API Responsiveness Benchmark ==="
    export KUBECONFIG="${KUBECONFIG_PATH}"
    python3 "${SCRIPT_DIR}/scripts/benchmark_api_latency.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --kubeconfig "${KUBECONFIG_PATH}"
}

run_benchmark_micro() {
    log "BENCH-3c" "=== Phase 3c: Micro Benchmarks ==="
    export KUBECONFIG="${KUBECONFIG_PATH}"
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --kubeconfig "${KUBECONFIG_PATH}"
}

run_benchmark_stress() {
    log "BENCH-3d" "=== Phase 3d: Stress Test ==="
    export KUBECONFIG="${KUBECONFIG_PATH}"
    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --iterations "${ITERATIONS}" \
        --kubeconfig "${KUBECONFIG_PATH}" \
        --stress-only
}

phase3_run_benchmarks() {
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            3a) run_benchmark_pod_startup ;;
            3b) run_benchmark_api_latency ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_stress ;;
            3)  run_benchmark_pod_startup
                run_benchmark_api_latency
                run_benchmark_micro
                run_benchmark_stress ;;
        esac
    done
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Results Collection & Presentation ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        --results-dir "${RESULTS_DIR}"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --results-dir "${RESULTS_DIR}"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --results-dir "${RESULTS_DIR}"

    log "PHASE4" "Phase 4 complete. Results available at:"
    log "PHASE4" "  JSON:    ${RESULTS_DIR}/all_results.json"
    log "PHASE4" "  Summary: ${RESULTS_DIR}/benchmark_summary.txt"
    log "PHASE4" "  HTML:    ${RESULTS_DIR}/benchmark_report.html"
}

cleanup_cluster() {
    if kind get clusters 2>/dev/null | grep -q "${KIND_CLUSTER_NAME}"; then
        log "CLEANUP" "Deleting kind cluster '${KIND_CLUSTER_NAME}'..."
        kind delete cluster --name "${KIND_CLUSTER_NAME}" 2>/dev/null || true
    fi
}

run_phases() {
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            1)  phase1_install ;;
            2)  phase2_verify ;;
            3)  phase3_run_benchmarks ;;
            3a) run_benchmark_pod_startup ;;
            3b) run_benchmark_api_latency ;;
            3c) run_benchmark_micro ;;
            3d) run_benchmark_stress ;;
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
    cat <<EOF
Usage: kubernetes_arm64_perf_workflow.sh [OPTIONS]

Options:
  -p, --phases PHASES      Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version   Kubernetes version to test (default: 1.33.12)
  -v, --data-scale         Dataset scale factor (default: 1)
  -d, --data-size          Number of pods for micro benchmarks (default: 100)
  -i, --iterations         Number of iterations per test (default: 3)
  -t, --test-only          Run only shUnit2 validation tests
  -c, --cleanup            Delete kind cluster after benchmarks
  -h, --help               Usage help

Examples:
  kubernetes_arm64_perf_workflow.sh                        # Full run
  kubernetes_arm64_perf_workflow.sh -p 3a,3b               # Pod startup + API latency only
  kubernetes_arm64_perf_workflow.sh -t                     # Validation tests only
  kubernetes_arm64_perf_workflow.sh -s 1.36.1 -i 5         # Custom version, 5 iterations
  kubernetes_arm64_perf_workflow.sh -d 500                 # 500 pods for benchmarks
EOF
}

main() {
    local test_only=0
    local do_cleanup=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)      PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -v|--data-scale)  DATA_SCALE="$2"; shift 2 ;;
            -d|--data-size)   DATA_SIZE="$2"; shift 2 ;;
            -i|--iterations)  ITERATIONS="$2"; shift 2 ;;
            -t|--test-only)   test_only=1; shift ;;
            -c|--cleanup)     do_cleanup=1; shift ;;
            -h|--help)        usage; exit 0 ;;
            *)                log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    if [ "${test_only}" -eq 1 ]; then
        run_tests
    else
        run_phases
        run_tests
        if [ "${do_cleanup}" -eq 1 ]; then
            cleanup_cluster
        fi
    fi
}

main "$@"