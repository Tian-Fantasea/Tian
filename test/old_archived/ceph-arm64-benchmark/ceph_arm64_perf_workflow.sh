#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
SOFTWARE_NAME="ceph"
SOFTWARE_VERSION="${SOFTWARE_VERSION:-19.2.0}"
CEPH_CLUSTER_NAME="${CEPH_CLUSTER_NAME:-ceph}"
CEPH_CONF_PATH="${CEPH_CONF_PATH:-/etc/ceph/ceph.conf}"
CEPH_KEYRING_PATH="${CEPH_KEYRING_PATH:-/etc/ceph/ceph.client.admin.keyring}"
NUM_OSDS="${NUM_OSDS:-3}"
OSD_SIZE_GB="${OSD_SIZE_GB:-10}"
OBJECT_SIZES="${OBJECT_SIZES:-4K,16K,64K,256K,1M,4M,16M,64M}"
CONCURRENCY_LEVELS="${CONCURRENCY_LEVELS:-1,4,16,32,64,128}"
BENCH_DURATION="${BENCH_DURATION:-30}"
ITERATIONS="${ITERATIONS:-3}"
PHASES="${PHASES:-1,2,3,4}"
DATA_SCALE="${DATA_SCALE:-1}"
DATA_SIZE="${DATA_SIZE:-1000}"
LOG_FILE="${RESULTS_DIR}/workflow.log"

log() { local tag="$1"; shift; printf '[%s] %s\n' "$tag" "$*" | tee -a "${LOG_FILE}"; }

mkdir -p "${RESULTS_DIR}" "${SCRIPT_DIR}/scripts"

download_shunit2() {
    if [ ! -f "${SCRIPT_DIR}/shunit2" ]; then
        log "SETUP" "Downloading shUnit2..."
        curl -sL https://raw.githubusercontent.com/kward/shunit2/master/shunit2 \
            -o "${SCRIPT_DIR}/shunit2"
        chmod +x "${SCRIPT_DIR}/shunit2"
    fi
}

setup_python_venv() {
    if [ ! -d "${SCRIPT_DIR}/venv" ]; then
        log "SETUP" "Creating Python venv..."
        python3 -m venv "${SCRIPT_DIR}/venv"
        "${SCRIPT_DIR}/venv/bin/pip" install --quiet numpy pandas
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
    log "PHASE1" "ARM64 architecture confirmed: ${arch}"

    log "PHASE1" "Installing system dependencies..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq \
            cmake ninja-build python3-dev python3-pip \
            libboost-all-dev libfmt-dev libaio-dev libblkid-dev \
            libcurl4-openssl-dev libuuid1-dev libudev-dev \
            leveldb-dev liboath-dev libibverbs-dev librdmacm-dev \
            libncurses-dev libedit-dev libldap2-dev libsasl2-dev \
            librabbitmq-dev librdkafka-dev libnl-3-dev libnl-route-3-dev \
            libxml2-dev libyajl-dev libsqlite3-dev libssh2-dev \
            fio uuid-runtime xfsprogs lvm2 \
            g++ gcc make autoconf automake libtool \
            2>/dev/null || true
    elif command -v yum &>/dev/null; then
        sudo yum install -y \
            cmake ninja-build python3-devel python3-pip \
            boost-devel fmt-devel libaio-devel libblkid-devel \
            libcurl-devel libuuid-devel libudev-devel \
            leveldb-devel liboath-devel libibverbs-devel librdmacm-devel \
            ncurses-devel libedit-devel openldap-devel cyrus-sasl-devel \
            librabbitmq-devel librdkafka-devel libnl3-devel libnl3-route-devel \
            libxml2-devel yajl-devel sqlite-devel libssh2-devel \
            fio uuidgen xfsprogs lvm2 \
            gcc gcc-c++ make autoconf automake libtool \
            2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y \
            cmake ninja-build python3-devel python3-pip \
            boost-devel fmt-devel libaio-devel libblkid-devel \
            libcurl-devel libuuid-devel libudev-devel \
            leveldb-devel liboath-devel libibverbs-devel librdmacm-devel \
            ncurses-devel libedit-devel openldap-devel cyrus-sasl-devel \
            librabbitmq-devel librdkafka-devel libnl3-devel libnl3-route-devel \
            libxml2-devel yajl-devel sqlite-devel libssh2-devel \
            fio uuidgen xfsprogs lvm2 \
            gcc gcc-c++ make autoconf automake libtool \
            2>/dev/null || true
    fi

    setup_python_venv

    log "PHASE1" "Installing Ceph..."
    local ceph_src="${SCRIPT_DIR}/ceph_src"
    local ceph_install="${SCRIPT_DIR}/ceph_install"

    if [ ! -d "${ceph_src}" ]; then
        log "PHASE1" "Cloning Ceph repository (v${SOFTWARE_VERSION})..."
        local mirrors=(
            "https://github.com/ceph/ceph.git"
            "https://gitee.com/mirrors/ceph.git"
            "https://gitlab.com/ceph/ceph.git"
        )
        local cloned=0
        for mirror_url in "${mirrors[@]}"; do
            git clone --depth 1 --branch "v${SOFTWARE_VERSION}" \
                --timeout=120 "${mirror_url}" "${ceph_src}" 2>/dev/null && {
                cloned=1; break
            }
            rm -rf "${ceph_src}"
        done
        if [ "${cloned}" -eq 0 ]; then
            log "PHASE1" "Git clone failed, trying package manager install..."
            if command -v apt-get &>/dev/null; then
                sudo apt-get install -y -qq ceph ceph-mds ceph-common 2>/dev/null || true
            elif command -v yum &>/dev/null; then
                sudo yum install -y ceph ceph-mds ceph-common 2>/dev/null || true
            elif command -v dnf &>/dev/null; then
                sudo dnf install -y ceph ceph-mds ceph-common 2>/dev/null || true
            fi
            if command -v ceph &>/dev/null; then
                log "PHASE1" "Ceph installed via package manager"
            else
                log "ERROR" "Ceph installation failed. Please install manually."
                return 1
            fi
        else
            log "PHASE1" "Building Ceph from source with ARM64 optimizations..."
            mkdir -p "${ceph_src}/build"
            cd "${ceph_src}/build"
            cmake .. \
                -DCMAKE_BUILD_TYPE=Release \
                -DWITH_TESTS=OFF \
                -DWITH_MGR=ON \
                -DWITH_RBD=ON \
                -DWITH_CEPHFS=ON \
                -DWITH_RDMA=OFF \
                -DWITH_SYSTEM_BOOST=ON \
                -DWITH_SYSTEM_FMT=ON \
                -DCMAKE_C_FLAGS="-O2 -march=armv8-a+crc+crypto" \
                -DCMAKE_CXX_FLAGS="-O2 -march=armv8-a+crc+crypto" \
                -GNinja \
                2>/dev/null || cmake .. \
                -DCMAKE_BUILD_TYPE=Release \
                -DWITH_TESTS=OFF \
                -DWITH_MGR=ON \
                -DWITH_RBD=ON \
                -DWITH_CEPHFS=ON \
                -DCMAKE_C_FLAGS="-O2 -march=armv8-a+crc+crypto" \
                -DCMAKE_CXX_FLAGS="-O2 -march=armv8-a+crc+crypto" \
                2>/dev/null || {
                log "ERROR" "CMake configure failed"
                return 1
            }
            ninja -j$(nproc) 2>/dev/null || make -j$(nproc) 2>/dev/null || {
                log "WARN" "Build may have partial failures, continuing..."
            }
            sudo make install 2>/dev/null || true
            cd "${SCRIPT_DIR}"
        fi
    else
        log "PHASE1" "Ceph source already exists at ${ceph_src}"
    fi

    log "PHASE1" "Deploying minimal Ceph cluster for benchmarking..."

    local fsid
    fsid="$(uuidgen | tr -d '\n\t')"
    log "PHASE1" "Cluster FSID: ${fsid}"

    sudo mkdir -p /etc/ceph /var/lib/ceph/mon/ceph-a /var/lib/ceph/mgr/ceph-a

    if [ ! -f "${CEPH_CONF_PATH}" ]; then
        log "PHASE1" "Generating ceph.conf..."
        local local_host
        local_host="$(hostname | tr -d '\n\t')"
        local local_ip
        local_ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '127.0.0.1' | head -1 | tr -d '\n\t')"
        if [ -z "${local_ip}" ]; then
            local_ip="$(hostname -I 2>/dev/null | head -1 | tr -d ' \n\t')"
        fi
        if [ -z "${local_ip}" ]; then
            local_ip="127.0.0.1"
        fi
        python3 "${SCRIPT_DIR}/scripts/json_helper.py" \
            "${CEPH_CONF_PATH}" write_ceph_conf_file \
            "${fsid}" "a" "${local_host}" "${local_ip}"
    fi

    if [ ! -f "${CEPH_KEYRING_PATH}" ]; then
        log "PHASE1" "Generating admin keyring..."
        sudo mkdir -p "$(dirname "${CEPH_KEYRING_PATH}")"
        local admin_key
        admin_key="$(ceph-authtool --gen-key /dev/stdout 2>/dev/null | head -1 | tr -d '\n\t' || echo 'AQAAarchAA==')"
        sudo ceph-authtool --create-keyring "${CEPH_KEYRING_PATH}" \
            --name client.admin --add-key "${admin_key}" 2>/dev/null
        if [ ! -f "${CEPH_KEYRING_PATH}" ]; then
            log "WARN" "ceph-authtool failed, creating keyring manually"
            echo "[client.admin]" | sudo tee "${CEPH_KEYRING_PATH}" >/dev/null
            echo "key = ${admin_key}" | sudo tee -a "${CEPH_KEYRING_PATH}" >/dev/null
            echo "caps mds = \"allow *\"" | sudo tee -a "${CEPH_KEYRING_PATH}" >/dev/null
            echo "caps mon = \"allow *\"" | sudo tee -a "${CEPH_KEYRING_PATH}" >/dev/null
            echo "caps osd = \"allow *\"" | sudo tee -a "${CEPH_KEYRING_PATH}" >/dev/null
        fi
        sudo chmod 644 "${CEPH_KEYRING_PATH}" 2>/dev/null || true
    fi

    log "PHASE1" "Setting up loopback OSD devices..."
    for i in $(seq 1 "${NUM_OSDS}"); do
        local loop_dev="/dev/loop${i}"
        local osd_file="/var/lib/ceph/osd/ceph-${i}/osd_data"
        if [ ! -b "${loop_dev}" ]; then
            sudo mkdir -p "/var/lib/ceph/osd/ceph-${i}"
            sudo truncate -s "${OSD_SIZE_GB}G" "${osd_file}" 2>/dev/null || true
            sudo losetup "${loop_dev}" "${osd_file}" 2>/dev/null || true
            sudo mkfs.xfs -f "${loop_dev}" 2>/dev/null || true
            sudo mount "${loop_dev}" "/var/lib/ceph/osd/ceph-${i}" 2>/dev/null || true
        fi
    done

    log "PHASE1" "Starting Ceph Monitor..."
    if ! pgrep -x ceph-mon &>/dev/null; then
        sudo ceph-mon --cluster "${CEPH_CLUSTER_NAME}" -i a \
            --mon-data /var/lib/ceph/mon/ceph-a 2>/dev/null &
        sleep 5
    fi

    log "PHASE1" "Starting Ceph Manager..."
    if ! pgrep -x ceph-mgr &>/dev/null; then
        sudo ceph-mgr --cluster "${CEPH_CLUSTER_NAME}" -i a 2>/dev/null &
        sleep 3
    fi

    log "PHASE1" "Initializing OSDs..."
    for i in $(seq 1 "${NUM_OSDS}"); do
        local osd_uuid
        osd_uuid="$(uuidgen | tr -d '\n\t')"
        sudo ceph-osd --cluster "${CEPH_CLUSTER_NAME}" -i "${i}" \
            --mkfs --osd-uuid "${osd_uuid}" 2>/dev/null || true
        sudo ceph-osd --cluster "${CEPH_CLUSTER_NAME}" -i "${i}" 2>/dev/null &
    done
    sleep 10

    log "PHASE1" "Waiting for cluster HEALTH_OK..."
    local health_wait=0
    while [ "${health_wait}" -lt 120 ]; do
        local health
        health="$(ceph status --format json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["health"]["status"])' 2>/dev/null || echo 'UNKNOWN')"
        if [ "${health}" = "HEALTH_OK" ] || [ "${health}" = "HEALTH_WARN" ]; then
            log "PHASE1" "Cluster health: ${health}"
            break
        fi
        health_wait=$((health_wait + 5))
        sleep 5
    done

    log "PHASE1" "Creating benchmark pools..."
    ceph osd pool create bench_rados 128 128 replicated 2>/dev/null || true
    ceph osd pool create bench_rbd 128 128 replicated 2>/dev/null || true
    ceph osd pool create bench_cephfs_meta 64 64 replicated 2>/dev/null || true
    ceph osd pool create bench_cephfs_data 128 128 replicated 2>/dev/null || true

    log "PHASE1" "Enabling CephFS..."
    ceph fs new bench_cephfs bench_cephfs_meta bench_cephfs_data 2>/dev/null || true
    if ! pgrep -x ceph-mds &>/dev/null; then
        sudo ceph-mds --cluster "${CEPH_CLUSTER_NAME}" -i a 2>/dev/null &
        sleep 5
    fi

    local cephfs_mnt="/mnt/cephfs"
    local local_ip_for_mount="${local_ip}"
    if [ -z "${local_ip_for_mount}" ]; then
        local_ip_for_mount="$(hostname -I 2>/dev/null | tr ' ' '\n' | head -1 | tr -d '\n\t')"
    fi
    if [ ! -d "${cephfs_mnt}" ]; then
        sudo mkdir -p "${cephfs_mnt}"
        sleep 5
        sudo mount -t ceph "${local_ip_for_mount}:6789:/bench_cephfs" "${cephfs_mnt}" \
            -o name=admin,secretfile="${CEPH_KEYRING_PATH}" 2>/dev/null || true
    fi

    log "PHASE1" "Creating RBD image for block benchmarks..."
    rbd create bench_image --size 10G --pool bench_rbd 2>/dev/null || true

    log "PHASE1" "Phase 1 complete. Cluster ready for benchmarking."
}

phase2_verify() {
    log "PHASE2" "=== Phase 2: Verify Installation ==="

    python3 "${SCRIPT_DIR}/scripts/verify_ceph.py" \
        --results-dir "${RESULTS_DIR}" \
        --ceph-version "${SOFTWARE_VERSION}" \
        --ceph-conf "${CEPH_CONF_PATH}" \
        --ceph-keyring "${CEPH_KEYRING_PATH}" \
        --cluster-name "${CEPH_CLUSTER_NAME}"

    log "PHASE2" "Phase 2 complete."
}

phase3_run_benchmarks() {
    log "PHASE3" "=== Phase 3: Run Benchmarks ==="

    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            3a) run_benchmark_rados ;;
            3b) run_benchmark_rbd ;;
            3c) run_benchmark_cephfs ;;
            3d) run_benchmark_micro ;;
            3)  run_benchmark_rados; run_benchmark_rbd; run_benchmark_cephfs; run_benchmark_micro ;;
            *)  ;;
        esac
    done
}

run_benchmark_rados() {
    log "PHASE3a" "=== RADOS Object Storage Benchmarks ==="

    python3 "${SCRIPT_DIR}/scripts/benchmark_rados.py" \
        --results-dir "${RESULTS_DIR}" \
        --ceph-conf "${CEPH_CONF_PATH}" \
        --ceph-keyring "${CEPH_KEYRING_PATH}" \
        --cluster-name "${CEPH_CLUSTER_NAME}" \
        --pool bench_rados \
        --object-sizes "${OBJECT_SIZES}" \
        --concurrency "${CONCURRENCY_LEVELS}" \
        --duration "${BENCH_DURATION}" \
        --iterations "${ITERATIONS}"
}

run_benchmark_rbd() {
    log "PHASE3b" "=== RBD Block Storage Benchmarks ==="

    python3 "${SCRIPT_DIR}/scripts/benchmark_rbd.py" \
        --results-dir "${RESULTS_DIR}" \
        --ceph-conf "${CEPH_CONF_PATH}" \
        --ceph-keyring "${CEPH_KEYRING_PATH}" \
        --pool bench_rbd \
        --image bench_image \
        --iterations "${ITERATIONS}"
}

run_benchmark_cephfs() {
    log "PHASE3c" "=== CephFS File Storage Benchmarks ==="

    local cephfs_mnt="${CEPHFS_MOUNT:-/mnt/cephfs}"

    python3 "${SCRIPT_DIR}/scripts/benchmark_cephfs.py" \
        --results-dir "${RESULTS_DIR}" \
        --mount-point "${cephfs_mnt}" \
        --iterations "${ITERATIONS}" \
        --data-size "${DATA_SIZE}"
}

run_benchmark_micro() {
    log "PHASE3d" "=== Micro Benchmarks - OSD/EC/Compression ==="

    python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        --results-dir "${RESULTS_DIR}" \
        --ceph-conf "${CEPH_CONF_PATH}" \
        --ceph-keyring "${CEPH_KEYRING_PATH}" \
        --cluster-name "${CEPH_CLUSTER_NAME}" \
        --iterations "${ITERATIONS}" \
        --duration "${BENCH_DURATION}"
}

phase4_results() {
    log "PHASE4" "=== Phase 4: Aggregate Results & Generate Reports ==="

    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        --results-dir "${RESULTS_DIR}" \
        --software-name "${SOFTWARE_NAME}" \
        --software-version "${SOFTWARE_VERSION}"

    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        --results-dir "${RESULTS_DIR}" \
        --software-name "${SOFTWARE_NAME}" \
        --software-version "${SOFTWARE_VERSION}"

    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        --results-dir "${RESULTS_DIR}" \
        --software-name "${SOFTWARE_NAME}" \
        --software-version "${SOFTWARE_VERSION}"

    log "PHASE4" "Phase 4 complete."
    log "PHASE4" "Results: ${RESULTS_DIR}/all_results.json"
    log "PHASE4" "Summary: ${RESULTS_DIR}/benchmark_summary.txt"
    log "PHASE4" "Report:  ${RESULTS_DIR}/benchmark_report.html"
}

run_phases() {
    local phases="${PHASES}"
    local IFS=','
    for p in ${phases}; do
        case "${p}" in
            1)  phase1_install ;;
            2)  phase2_verify ;;
            3)  phase3_run_benchmarks ;;
            3a) run_benchmark_rados ;;
            3b) run_benchmark_rbd ;;
            3c) run_benchmark_cephfs ;;
            3d) run_benchmark_micro ;;
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
Usage: ${SOFTWARE_NAME}_arm64_perf_workflow.sh [OPTIONS]

Options:
  -p, --phases PHASES         Comma-separated phases (1,2,3,4 or 3a,3b,3c,3d)
  -s, --software-version      Version to test (default: ${SOFTWARE_VERSION})
  -v, --data-scale            Dataset scale factor (default: ${DATA_SCALE})
  -d, --data-size             Data size for micro benchmarks (default: ${DATA_SIZE})
  -i, --iterations            Number of iterations per test (default: ${ITERATIONS})
  -o, --num-osds              Number of OSDs (default: ${NUM_OSDS})
  -S, --osd-size              OSD size in GB (default: ${OSD_SIZE_GB})
  -D, --bench-duration        Benchmark duration in seconds (default: ${BENCH_DURATION})
  -O, --object-sizes          Comma-separated object sizes (default: ${OBJECT_SIZES})
  -c, --concurrency           Comma-separated concurrency levels (default: ${CONCURRENCY_LEVELS})
  -t, --test-only             Run only shUnit2 validation tests
  -h, --help                  Usage help
EOF
}

main() {
    local test_only=0
    while [ $# -gt 0 ]; do
        case "$1" in
            -p|--phases)         PHASES="$2"; shift 2 ;;
            -s|--software-version) SOFTWARE_VERSION="$2"; shift 2 ;;
            -v|--data-scale)    DATA_SCALE="$2"; shift 2 ;;
            -d|--data-size)     DATA_SIZE="$2"; shift 2 ;;
            -i|--iterations)    ITERATIONS="$2"; shift 2 ;;
            -o|--num-osds)      NUM_OSDS="$2"; shift 2 ;;
            -S|--osd-size)      OSD_SIZE_GB="$2"; shift 2 ;;
            -D|--bench-duration) BENCH_DURATION="$2"; shift 2 ;;
            -O|--object-sizes)  OBJECT_SIZES="$2"; shift 2 ;;
            -c|--concurrency)   CONCURRENCY_LEVELS="$2"; shift 2 ;;
            -t|--test-only)     test_only=1; shift ;;
            -h|--help)          usage; exit 0 ;;
            *)                  log "ERROR" "Unknown option: $1"; usage; exit 1 ;;
        esac
    done

    if [ "${test_only}" -eq 1 ]; then
        run_tests
    else
        run_phases
        run_tests
    fi
}

main "$@"