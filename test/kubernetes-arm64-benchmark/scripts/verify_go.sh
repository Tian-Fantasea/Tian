#!/bin/bash
set -euo pipefail

RESULTS_DIR="${1:-./results}"
SOFTWARE_VERSION="${2:-1.33.12}"

echo "[VERIFY] Checking Kubernetes installation on ARM64..."

errors=0

arch="$(uname -m)"
if [ "${arch}" != "aarch64" ] && [ "${arch}" != "arm64" ]; then
    echo "[VERIFY-FAIL] Not ARM64 architecture: ${arch}"
    errors=$((errors + 1))
else
    echo "[VERIFY-PASS] Architecture: ${arch}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -x "${SCRIPT_DIR}/../kubectl" ]; then
    echo "[VERIFY-PASS] kubectl binary found at ${SCRIPT_DIR}/../kubectl"
elif command -v kubectl &>/dev/null; then
    echo "[VERIFY-PASS] kubectl found in PATH"
else
    echo "[VERIFY-FAIL] kubectl not found"
    errors=$((errors + 1))
fi

if [ -x "${SCRIPT_DIR}/../kind" ]; then
    echo "[VERIFY-PASS] kind binary found at ${SCRIPT_DIR}/../kind"
elif command -v kind &>/dev/null; then
    echo "[VERIFY-PASS] kind found in PATH"
else
    echo "[VERIFY-FAIL] kind not found"
    errors=$((errors + 1))
fi

KUBECONFIG="${RESULTS_DIR}/kubeconfig"
if [ ! -f "${KUBECONFIG}" ]; then
    echo "[VERIFY-FAIL] kubeconfig not found at ${KUBECONFIG}"
    errors=$((errors + 1))
else
    echo "[VERIFY-PASS] kubeconfig found"
fi

export KUBECONFIG="${KUBECONFIG}"

if command -v kubectl &>/dev/null; then
    nodes_output="$(kubectl get nodes --no-headers 2>/dev/null || echo "ERROR")"
    if echo "${nodes_output}" | grep -q "Ready"; then
        ready_count="$(echo "${nodes_output}" | grep -c "Ready")"
        echo "[VERIFY-PASS] Cluster has ${ready_count} ready node(s)"
    else
        echo "[VERIFY-FAIL] No ready nodes found"
        errors=$((errors + 1))
    fi

    ns_output="$(kubectl get namespaces --no-headers 2>/dev/null || echo "ERROR")"
    if echo "${ns_output}" | grep -q "default"; then
        echo "[VERIFY-PASS] Default namespace exists"
    else
        echo "[VERIFY-FAIL] Default namespace not found"
        errors=$((errors + 1))
    fi

    api_output="$(kubectl api-resources --no-headers 2>/dev/null | wc -l || echo 0)"
    if [ "${api_output}" -gt 0 ]; then
        echo "[VERIFY-PASS] API server responsive, ${api_output} resource types available"
    else
        echo "[VERIFY-FAIL] API server not responsive"
        errors=$((errors + 1))
    fi
fi

if command -v go &>/dev/null; then
    go_ver="$(go version 2>&1 | tr -d '\n\t')"
    echo "[VERIFY-PASS] Go runtime: ${go_ver}"
else
    echo "[VERIFY-INFO] Go not installed (not required for running benchmarks)"
fi

if command -v docker &>/dev/null; then
    docker_ver="$(docker version --format '{{.Server.Version}}' 2>/dev/null | tr -d '\n\t' || echo "unknown")"
    echo "[VERIFY-PASS] Docker: ${docker_ver}"
elif command -v containerd &>/dev/null; then
    echo "[VERIFY-PASS] containerd found"
else
    echo "[VERIFY-WARN] No container runtime detected"
fi

echo "[VERIFY] Verification complete. Errors: ${errors}"
exit ${errors}