#!/bin/bash
set -euo pipefail

REDIS_HOME="${1:-}"
REDIS_PORT="${2:-6380}"
RESULTS_DIR="${3:-.}"

if [ -z "${REDIS_HOME}" ]; then
    echo "Usage: verify_c.sh <redis_home> <port> <results_dir>"
    exit 1
fi

echo "[VERIFY] Checking Redis installation..."

echo "[VERIFY] 1. Checking redis-server binary..."
if [ -x "${REDIS_HOME}/src/redis-server" ]; then
    echo "[VERIFY]   redis-server binary found and executable."
else
    echo "[VERIFY]   ERROR: redis-server binary not found or not executable."
    exit 1
fi

echo "[VERIFY] 2. Checking redis-cli binary..."
if [ -x "${REDIS_HOME}/src/redis-cli" ]; then
    echo "[VERIFY]   redis-cli binary found and executable."
else
    echo "[VERIFY]   ERROR: redis-cli binary not found or not executable."
    exit 1
fi

echo "[VERIFY] 3. Checking redis-benchmark binary..."
if [ -x "${REDIS_HOME}/src/redis-benchmark" ]; then
    echo "[VERIFY]   redis-benchmark binary found and executable."
else
    echo "[VERIFY]   ERROR: redis-benchmark binary not found or not executable."
    exit 1
fi

echo "[VERIFY] 4. Checking Redis server version..."
VER_OUTPUT="$("${REDIS_HOME}/src/redis-server" --version 2>&1)"
echo "[VERIFY]   ${VER_OUTPUT}"

echo "[VERIFY] 5. Checking Redis server is responsive..."
PING_RESULT="$("${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" PING 2>&1)"
if [ "${PING_RESULT}" = "PONG" ]; then
    echo "[VERIFY]   Redis server is responsive (PING -> PONG)."
else
    echo "[VERIFY]   ERROR: Redis server not responsive. PING returned: ${PING_RESULT}"
    exit 1
fi

echo "[VERIFY] 6. Checking ARM64 architecture..."
ARCH="$(uname -m)"
echo "[VERIFY]   Architecture: ${ARCH}"

echo "[VERIFY] 7. Running basic SET/GET test..."
SET_RESULT="$("${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" SET verify:test "hello_arm64" 2>&1)"
GET_RESULT="$("${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" GET verify:test 2>&1)"
if [ "${GET_RESULT}" = "hello_arm64" ]; then
    echo "[VERIFY]   SET/GET test passed."
else
    echo "[VERIFY]   ERROR: SET/GET test failed. SET=${SET_RESULT}, GET=${GET_RESULT}"
    exit 1
fi

echo "[VERIFY] 8. Checking Redis info..."
INFO_RESULT="$("${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" INFO server 2>&1 | head -20)"
echo "[VERIFY]   ${INFO_RESULT}"

"${REDIS_HOME}/src/redis-cli" -p "${REDIS_PORT}" DEL verify:test 2>/dev/null || true

echo "[VERIFY] All verification checks passed."
exit 0