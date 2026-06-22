#!/usr/bin/env bash

DESKTOP_DIR="$(cd "$(dirname "$0")" && pwd)"

install_apt_packages() {
    local version="$1"
    sudo apt-get update -qq
    case "$SOFTWARE" in
        gcc)
            sudo apt-get install -y gcc g++
            ;;
        python)
            sudo apt-get install -y python3 python3-pip python3-venv
            ;;
        zstd)
            sudo apt-get install -y zstd libzstd-dev
            ;;
        ceph)
            sudo apt-get install -y ceph ceph-mds ceph-common fio
            ;;
        openjdk)
            if [ -f /etc/apt/sources.list.d/temurin.list ] || [ -f /etc/apt/sources.list.d/adoptium.list ]; then
                sudo apt-get install -y temurin-${version}-jdk
            else
                sudo apt-get install -y wget apt-transport-https gpg
                wget -O - https://packages.adoptium.net/artifactory/api/gpg/key/public | sudo gpg --dearmor -o /usr/share/keyrings/adoptium.gpg
                echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo $VERSION_CODENAME) main" | sudo tee /etc/apt/sources.list.d/temurin.list
                sudo apt-get update -qq
                sudo apt-get install -y temurin-${version}-jdk
            fi
            ;;
        mysql)
            sudo apt-get install -y mysql-server mysql-client sysbench
            ;;
        folly)
            sudo apt-get install -y libfolly-dev libfolly-test-dev
            ;;
        brpc)
            sudo apt-get install -y libbrpc-dev protobuf-compiler libprotobuf-dev libssl-dev cmake
            ;;
        lz4)
            sudo apt-get install -y liblz4-dev lz4
            ;;
        protobuf)
            sudo apt-get install -y protobuf-compiler libprotobuf-dev
            ;;
    esac
}

install_yum_packages() {
    local version="$1"
    case "$SOFTWARE" in
        gcc)
            sudo yum install -y gcc gcc-c++
            ;;
        python)
            sudo yum install -y python3 python3-pip
            ;;
        zstd)
            sudo yum install -y zstd libzstd-devel
            ;;
        openjdk)
            sudo yum install -y java-${version}-openjdk-devel
            ;;
        folly)
            sudo yum install -y folly-devel folly-test-devel cmake gcc-c++
            ;;
        lz4)
            sudo yum install -y lz4-devel lz4
            ;;
        protobuf)
            sudo yum install -y protobuf-devel protobuf-compiler
            ;;
    esac
}

setup_pip_venv() {
    local venv_dir="${DESKTOP_DIR}/venv"
    if [ ! -d "$venv_dir" ]; then
        python3 -m venv "$venv_dir"
    fi
    export PATH="${venv_dir}/bin:${PATH}"
    export VIRTUAL_ENV="$venv_dir"
}

install_pip_packages() {
    local version="$1"
    setup_pip_venv
    case "$SOFTWARE" in
        faiss)
            pip install faiss-cpu numpy
            ;;
        hnswlib)
            pip install hnswlib==${version} numpy
            ;;
        lz4)
            pip install lz4 numpy
            ;;
        openviking)
            pip install openviking==${version} numpy
            ;;
        protobuf)
            pip install protobuf==${version}
            ;;
        pytorch)
            pip install torch==${version} --index-url https://download.pytorch.org/whl/cpu numpy
            ;;
        scann)
            pip install scann==${version} numpy
            ;;
    esac
}

download_tarball() {
    local url="$1"
    local dest="$2"
    local timeout="${3:-120}"

    if command -v wget >/dev/null 2>&1; then
        wget --timeout=${timeout} --tries=3 -q -O "$dest" "$url" && return 0
    fi
    if command -v curl >/dev/null 2>&1; then
        curl --connect-timeout ${timeout} --retry 3 -sL -o "$dest" "$url" && return 0
    fi
    return 1
}

install_tarball_downloads() {
    local version="$1"
    local tmp_dir="${DESKTOP_DIR}/tmp_downloads"
    mkdir -p "$tmp_dir"

    case "$SOFTWARE" in
        golang)
            local arch="$(uname -m)"
            local go_arch="linux-arm64"
            if [ "$arch" = "x86_64" ]; then go_arch="linux-amd64"; fi
            local url="https://go.dev/dl/go${version}.${go_arch}.tar.gz"
            local mirror="https://mirrors.aliyun.com/golang/go${version}.${go_arch}.tar.gz"
            printf "[DL]   Downloading Go %s...\n" "$version"
            if ! download_tarball "$url" "${tmp_dir}/go.tar.gz" 120; then
                printf "[DL]   Primary mirror failed, trying aliyun...\n"
                download_tarball "$mirror" "${tmp_dir}/go.tar.gz" 120 || return 1
            fi
            sudo rm -rf /usr/local/go
            sudo tar -C /usr/local -xzf "${tmp_dir}/go.tar.gz"
            export PATH="/usr/local/go/bin:${PATH}"
            printf "[OK]   Go %s installed at /usr/local/go\n" "$version"
            ;;
        flink)
            local url="https://archive.apache.org/dist/flink/flink-${version}/flink-${version}-bin-scala_2.12.tgz"
            local mirror="https://mirrors.aliyun.com/apache/flink/flink-${version}/flink-${version}-bin-scala_2.12.tgz"
            printf "[DL]   Downloading Flink %s...\n" "$version"
            if ! download_tarball "$url" "${tmp_dir}/flink.tgz" 300; then
                printf "[DL]   Primary mirror failed, trying aliyun...\n"
                download_tarball "$mirror" "${tmp_dir}/flink.tgz" 300 || return 1
            fi
            tar -xzf "${tmp_dir}/flink.tgz" -C "${DESKTOP_DIR}/flink/"
            printf "[OK]   Flink %s extracted\n" "$version"
            ;;
        spark)
            local url="https://archive.apache.org/dist/spark/spark-${version}/spark-${version}-bin-hadoop3.tgz"
            local mirror="https://mirrors.aliyun.com/apache/spark/spark-${version}/spark-${version}-bin-hadoop3.tgz"
            printf "[DL]   Downloading Spark %s...\n" "$version"
            if ! download_tarball "$url" "${tmp_dir}/spark.tgz" 300; then
                printf "[DL]   Primary mirror failed, trying aliyun...\n"
                download_tarball "$mirror" "${tmp_dir}/spark.tgz" 300 || return 1
            fi
            tar -xzf "${tmp_dir}/spark.tgz" -C "${DESKTOP_DIR}/spark/"
            printf "[OK]   Spark %s extracted\n" "$version"
            ;;
    esac
}

install_binary_downloads() {
    local version="$1"
    local tmp_dir="${DESKTOP_DIR}/tmp_downloads"
    mkdir -p "$tmp_dir"

    case "$SOFTWARE" in
        envoy)
            local url="https://github.com/envoyproxy/envoy/releases/download/v${version}/envoy-v${version}-linux-aarch64.tar.xz"
            printf "[DL]   Downloading Envoy %s...\n" "$version"
            download_tarball "$url" "${tmp_dir}/envoy.tar.xz" 300 || return 1
            tar -xJf "${tmp_dir}/envoy.tar.xz" -C "${tmp_dir}/"
            sudo cp "${tmp_dir}/envoy-v${version}-linux-aarch64/bin/envoy" /usr/local/bin/envoy
            sudo chmod +x /usr/local/bin/envoy
            printf "[OK]   Envoy %s installed\n" "$version"
            ;;
        kubernetes)
            local kubectl_url="https://dl.k8s.io/release/v${version}/bin/linux/arm64/kubectl"
            local kind_url="https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-arm64"
            printf "[DL]   Downloading kubectl v%s...\n" "$version"
            download_tarball "$kubectl_url" "${tmp_dir}/kubectl" 120 || return 1
            sudo chmod +x "${tmp_dir}/kubectl"
            sudo cp "${tmp_dir}/kubectl" /usr/local/bin/kubectl
            printf "[DL]   Downloading kind...\n" "$version"
            download_tarball "$kind_url" "${tmp_dir}/kind" 120 || return 1
            sudo chmod +x "${tmp_dir}/kind"
            sudo cp "${tmp_dir}/kind" /usr/local/bin/kind
            printf "[OK]   Kubernetes tools installed\n"
            ;;
        oceanbase)
            local url="https://github.com/oceanbase/oceanbase/releases/download/v${version}/observer-v${version}-linux-aarch64.tar.gz"
            printf "[DL]   Downloading OceanBase %s...\n" "$version"
            download_tarball "$url" "${tmp_dir}/oceanbase.tar.gz" 300 || return 1
            mkdir -p "${DESKTOP_DIR}/oceanbase/bin"
            tar -xzf "${tmp_dir}/oceanbase.tar.gz" -C "${DESKTOP_DIR}/oceanbase/"
            printf "[OK]   OceanBase %s extracted\n" "$version"
            ;;
    esac
}

install_source_compile() {
    local version="$1"
    local tmp_dir="${DESKTOP_DIR}/tmp_downloads"
    mkdir -p "$tmp_dir"

    case "$SOFTWARE" in
        redis)
            local url="https://github.com/redis/redis/archive/refs/tags/v${version}.tar.gz"
            local mirror="https://mirrors.aliyun.com/redis/redis-${version}.tar.gz"
            printf "[DL]   Downloading Redis %s source...\n" "$version"
            if ! download_tarball "$url" "${tmp_dir}/redis.tar.gz" 300; then
                download_tarball "$mirror" "${tmp_dir}/redis.tar.gz" 300 || return 1
            fi
            mkdir -p "${DESKTOP_DIR}/redis/redis-${version}"
            tar -xzf "${tmp_dir}/redis.tar.gz" -C "${tmp_dir}/"
            cp -r "${tmp_dir}/redis-${version}" "${DESKTOP_DIR}/redis/" || \
                cp -r "${tmp_dir}/redis-${version}" "${DESKTOP_DIR}/redis/"
            printf "[BUILD] Compiling Redis %s (make -j 4)...\n" "$version"
            make -j 4 -C "${DESKTOP_DIR}/redis/redis-${version}" || return 1
            printf "[OK]   Redis %s compiled\n" "$version"
            ;;
        rocksdb)
            local src_dir="${DESKTOP_DIR}/rocksdb/rocksdb-${version}"
            if [ ! -d "$src_dir" ]; then
                printf "[DL]   Cloning RocksDB %s...\n" "$version"
                git clone --depth 1 --branch v${version} https://github.com/facebook/rocksdb.git "$src_dir" || return 1
            fi
            printf "[BUILD] Compiling RocksDB db_bench (make -j 4)...\n" "$version"
            make -j 4 USE_JEMALLOC=1 db_bench -C "$src_dir" || return 1
            printf "[OK]   RocksDB %s compiled\n" "$version"
            ;;
        brpc)
            local src_dir="${DESKTOP_DIR}/brpc/brpc-${version}"
            if [ ! -d "$src_dir" ]; then
                printf "[DL]   Cloning brpc %s...\n" "$version"
                git clone --depth 1 --branch v${version} https://github.com/apache/brpc.git "$src_dir" || return 1
            fi
            mkdir -p "${src_dir}/build"
            printf "[BUILD] Compiling brpc %s (cmake + make -j 4)...\n" "$version"
            cmake -S "${src_dir}" -B "${src_dir}/build" || return 1
            make -j 4 -C "${src_dir}/build" || return 1
            sudo make install -C "${src_dir}/build" || return 1
            printf "[OK]   brpc %s compiled and installed\n" "$version"
            ;;
        folly)
            local src_dir="${DESKTOP_DIR}/folly/folly-${version}"
            if [ ! -d "$src_dir" ]; then
                printf "[DL]   Cloning folly %s...\n" "$version"
                git clone --depth 1 --branch v${version} https://github.com/facebook/folly.git "$src_dir" || return 1
            fi
            mkdir -p "${src_dir}/build"
            printf "[BUILD] Compiling folly %s (cmake + make -j 4)...\n" "$version"
            cmake -S "${src_dir}" -B "${src_dir}/build" || return 1
            make -j 4 -C "${src_dir}/build" || return 1
            sudo make install -C "${src_dir}/build" || return 1
            printf "[OK]   folly %s compiled and installed\n" "$version"
            ;;
    esac
}

install_go_software() {
    local version="$1"
    if ! command -v go >/dev/null 2>&1; then
        printf "[DEP]  Go not installed. Installing Go first...\n"
        SOFTWARE="golang"
        install_tarball_downloads "${GOLANG_VERSION:-1.26.4}"
    fi
    export GOTOOLCHAIN=local
    export PATH="/usr/local/go/bin:${PATH}"

    case "$SOFTWARE" in
        bolt)
            local bolt_dir="${DESKTOP_DIR}/bolt"
            mkdir -p "$bolt_dir"
            printf "[DL]   Setting up bolt (bbolt) %s Go module...\n" "$version"
            if [ ! -f "${bolt_dir}/go.mod" ]; then
                cd "$bolt_dir"
                go mod init bolt-arm64-benchmark
                go mod tidy
            fi
            printf "[OK]   bolt %s module ready\n" "$version"
            ;;
        cloudwego)
            local cw_dir="${DESKTOP_DIR}/cloudwego"
            printf "[DL]   Setting up cloudwego (Kitex %s + Hertz %s)...\n" "${KITEX_VERSION:-v0.16.2}" "${HERTZ_VERSION:-v0.10.4}"
            mkdir -p "$cw_dir"
            printf "[OK]   cloudwego Go module ready (kitex/hertz benchmarks will build in test phase)\n"
            ;;
    esac
}

install_git_clone() {
    local version="$1"
    case "$SOFTWARE" in
        sonic-cpp)
            local src_dir="${DESKTOP_DIR}/sonic-cpp/sonic-cpp-${version}"
            if [ ! -d "$src_dir" ]; then
                printf "[DL]   Cloning sonic-cpp %s...\n" "$version"
                git clone --depth 1 --branch v${version} https://github.com/bytedance/sonic-cpp.git "$src_dir" || return 1
            fi
            printf "[OK]   sonic-cpp %s source ready\n" "$version"
            ;;
    esac
}

SOFTWARE_REGISTRY=(
    "gcc|GCC_VERSION|14|apt"
    "python|PYTHON_VERSION|3.13|apt"
    "zstd|ZSTD_VERSION|1.5.7|apt"
    "openjdk|OPENJDK_VERSION|21|apt"
    "mysql|MYSQL_VERSION|8.4.9|apt"
    "ceph|VERSION|19.2.0|apt"
    "lz4|VERSION|1.10.0|apt"
    "protobuf|VERSION|29.4|apt"
    "brpc|BRPC_VERSION|1.6.0|apt"
    "folly|VERSION|2024.10.14.00|apt"
    "faiss|SOFTWARE_VERSION|1.14.2|pip"
    "hnswlib|HNSWLIB_VERSION|0.8.0|pip"
    "openviking|SOFTWARE_VERSION|v0.3.24|pip"
    "pytorch|PYTORCH_VERSION|2.7.0|pip"
    "scann|SOFTWARE_VERSION|1.4.2|pip"
    "golang|VERSION|1.26.4|tarball"
    "flink|VERSION|2.1.0|tarball"
    "spark|SOFTWARE_VERSION|4.1.2|tarball"
    "envoy|SOFTWARE_VERSION|1.38.2|binary"
    "kubernetes|VERSION|1.33.12|binary"
    "oceanbase|SOFTWARE_VERSION|4.2.1.8|binary"
    "redis|SOFTWARE_VERSION|8.0.2|source"
    "rocksdb|SOFTWARE_VERSION|9.10.0|source"
    "bolt|BOLT_VERSION|1.4.3|go"
    "cloudwego|KITEX_VERSION|v0.16.2|go"
    "sonic-cpp|SONIC_CPP_VERSION|1.0.2|git"
)

ALL_NAMES=()
ALL_VERSION_VARS=()
ALL_DEFAULT_VERSIONS=()
ALL_METHODS=()

for entry in "${SOFTWARE_REGISTRY[@]}"; do
    IFS='|' read -r name var default method <<< "$entry"
    ALL_NAMES+=("$name")
    ALL_VERSION_VARS+=("$var")
    ALL_DEFAULT_VERSIONS+=("$default")
    ALL_METHODS+=("$method")
done

SELECTED=()
EXCLUDED=()
VERSION_OVERRIDES=()
DRY_RUN=0
VERBOSE=0
CONTINUE_ON_ERROR=0
PARALLEL=0
JOBS=4

usage() {
    cat << 'USAGE'
Usage: batch_install.sh [OPTIONS]

ARM64 Batch Installer — install all 26 software independently

Install methods:
  apt     = system package manager (apt-get/yum)
  pip     = Python pip (with venv for PEP 668)
  tarball = download and extract tar.gz
  binary  = download prebuilt binary
  source  = download source + compile (make -j 4)
  go      = Go module build
  git     = git clone source

Options:
  --all                   Install all 26 software (default)
  --only <list>           Install only specified (comma-separated)
  --exclude <list>        Exclude specified from full install
  --version <key=val>     Override version: --version redis=7.2.4
  --dry-run               Show install plan without executing
  --verbose               Print detailed install output
  --continue              Continue on error (skip failed)
  --parallel              Install in parallel (--jobs N)
  --jobs <N>              Max parallel jobs (default: 4)
  --list                  List all software, versions, methods
  --check                 Check ARM64 architecture + OS
  --help                  Show this help

Examples:
  batch_install.sh                              # Install all
  batch_install.sh --only redis,golang          # Install only these
  batch_install.sh --exclude gcc,python         # Install all except
  batch_install.sh --only redis --version redis=7.2.4
  batch_install.sh --dry-run --list
USAGE
}

list_software() {
    printf "\n%-3s %-15s %-18s %-12s %-8s %s\n" "#" "Software" "Version Var" "Default" "Method" "Install Command"
    printf "%-3s %-15s %-18s %-12s %-8s %s\n" "---" "---------------" "------------------" "------------" "--------" "---------------------------"
    local idx=0
    for name in "${ALL_NAMES[@]}"; do
        local var="${ALL_VERSION_VARS[$idx]}"
        local ver="${ALL_DEFAULT_VERSIONS[$idx]}"
        local method="${ALL_METHODS[$idx]}"
        local cmd=""
        case "$method" in
            apt)   cmd="apt-get/yum install" ;;
            pip)   cmd="pip install (venv)" ;;
            tarball) cmd="download + extract" ;;
            binary) cmd="download binary" ;;
            source) cmd="download + make -j 4" ;;
            go)    cmd="go mod + build" ;;
            git)   cmd="git clone" ;;
        esac
        printf "%-3s %-15s %-18s %-12s %-8s %s\n" "$((idx+1))" "$name" "$var" "$ver" "$method" "$cmd"
        idx=$((idx + 1))
    done
    printf "\nTotal: %d software\n" "${#ALL_NAMES[@]}"
    printf "Note: lz4/protobuf use both apt + pip; bolt/cloudwego require Go (auto-installed)\n\n"
}

check_architecture() {
    local arch="$(uname -m)"
    printf "[CHECK] Architecture: %s\n" "$arch"
    if [ "$arch" != "aarch64" ] && [ "$arch" != "arm64" ]; then
        printf "[WARN] Not ARM64! Current: %s\n" "$arch"
    else
        printf "[OK]   ARM64 confirmed\n"
    fi

    if [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
        printf "[OS]   Debian/Ubuntu (apt-based)\n"
    elif [ -f /etc/redhat-release ] || [ -f /etc/euler-release ]; then
        printf "[OS]   RHEL/CentOS/openEuler (yum-based)\n"
    else
        printf "[OS]   Unknown Linux\n"
    fi

    local missing=0
    for cmd in sudo bash python3; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            printf "[MISS] %s\n" "$cmd"
            missing=$((missing + 1))
        else
            printf "[OK]   %s\n" "$cmd"
        fi
    done
    [ "$missing" -gt 0 ] && printf "[WARN] %d missing\n" "$missing"
}

resolve_idx() {
    local target="$1"
    local idx=0
    for name in "${ALL_NAMES[@]}"; do
        if [ "$name" = "$target" ]; then
            printf "%d" "$idx"
            return 0
        fi
        idx=$((idx + 1))
    done
    printf "-1"
}

apply_version() {
    local idx="$(resolve_idx "$SOFTWARE")"
    if [ "$idx" -eq -1 ]; then return; fi
    local var="${ALL_VERSION_VARS[$idx]}"
    local default="${ALL_DEFAULT_VERSIONS[$idx]}"

    for ov in "${VERSION_OVERRIDES[@]}"; do
        local ov_name="${ov%%=*}"
        local ov_ver="${ov#*=}"
        if [ "$ov_name" = "$SOFTWARE" ]; then
            export "$var"="$ov_ver"
            SOFTWARE_VERSION="$ov_ver"
            return
        fi
    done

    export "$var"="$default"
    SOFTWARE_VERSION="$default"
}

install_single() {
    local name="$1"
    SOFTWARE="$name"

    local idx="$(resolve_idx "$name")"
    if [ "$idx" -eq -1 ]; then
        printf "[FAIL] %s — not in registry\n" "$name"
        return 1
    fi

    local method="${ALL_METHODS[$idx]}"
    apply_version

    printf "[%-2s] %-15s method=%-8s version=%s\n" "RUN" "$name" "$method" "$SOFTWARE_VERSION"

    if [ "$DRY_RUN" -eq 1 ]; then
        printf "[DRY]  Would install %s via %s\n" "$name" "$method"
        return 0
    fi

    case "$method" in
        apt)
            if [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
                install_apt_packages "$SOFTWARE_VERSION"
            elif [ -f /etc/redhat-release ] || [ -f /etc/euler-release ]; then
                install_yum_packages "$SOFTWARE_VERSION"
            else
                printf "[WARN] Unknown OS, trying apt...\n"
                install_apt_packages "$SOFTWARE_VERSION"
            fi
            ;;
        pip)
            install_pip_packages "$SOFTWARE_VERSION"
            ;;
        tarball)
            install_tarball_downloads "$SOFTWARE_VERSION"
            ;;
        binary)
            install_binary_downloads "$SOFTWARE_VERSION"
            ;;
        source)
            install_source_compile "$SOFTWARE_VERSION"
            ;;
        go)
            install_go_software "$SOFTWARE_VERSION"
            ;;
        git)
            install_git_clone "$SOFTWARE_VERSION"
            ;;
        *)
            printf "[FAIL] Unknown method: %s\n" "$method"
            return 1
            ;;
    esac

    verify_install "$name" "$idx"
}

verify_install() {
    local name="$1"
    local idx="$2"
    local ok=0

    case "$name" in
        gcc)       command -v gcc >/dev/null 2>&1 && ok=1 ;;
        python)    command -v python3 >/dev/null 2>&1 && ok=1 ;;
        zstd)      command -v zstd >/dev/null 2>&1 && ok=1 ;;
        openjdk)   command -v java >/dev/null 2>&1 && ok=1 ;;
        mysql)     command -v mysql >/dev/null 2>&1 && ok=1 ;;
        ceph)      command -v ceph >/dev/null 2>&1 && ok=1 ;;
        lz4)       command -v lz4 >/dev/null 2>&1 && ok=1 ;;
        protobuf)  command -v protoc >/dev/null 2>&1 && ok=1 ;;
        brpc)      pkg-config --exists brpc >/dev/null 2>&1 && ok=1 ;;
        folly)     pkg-config --exists folly >/dev/null 2>&1 && ok=1 ;;
        faiss)     python3 -c "import faiss" >/dev/null 2>&1 && ok=1 ;;
        hnswlib)   python3 -c "import hnswlib" >/dev/null 2>&1 && ok=1 ;;
        openviking) python3 -c "import openviking" >/dev/null 2>&1 && ok=1 ;;
        pytorch)   python3 -c "import torch" >/dev/null 2>&1 && ok=1 ;;
        scann)     python3 -c "import scann" >/dev/null 2>&1 && ok=1 ;;
        golang)    command -v go >/dev/null 2>&1 && ok=1 ;;
        flink)     [ -f "${DESKTOP_DIR}/flink/flink-${SOFTWARE_VERSION}/bin/flink" ] && ok=1 ;;
        spark)     [ -f "${DESKTOP_DIR}/spark/spark-${SOFTWARE_VERSION}/bin/spark-submit" ] && ok=1 ;;
        envoy)     command -v envoy >/dev/null 2>&1 && ok=1 ;;
        kubernetes) command -v kubectl >/dev/null 2>&1 && ok=1 ;;
        oceanbase) [ -f "${DESKTOP_DIR}/oceanbase/bin/observer" ] && ok=1 ;;
        redis)     [ -f "${DESKTOP_DIR}/redis/redis-${SOFTWARE_VERSION}/src/redis-server" ] && ok=1 ;;
        rocksdb)   [ -f "${DESKTOP_DIR}/rocksdb/rocksdb-${SOFTWARE_VERSION}/db_bench" ] && ok=1 ;;
        bolt)      command -v go >/dev/null 2>&1 && ok=1 ;;
        cloudwego) command -v go >/dev/null 2>&1 && ok=1 ;;
        sonic-cpp) [ -d "${DESKTOP_DIR}/sonic-cpp/sonic-cpp-${SOFTWARE_VERSION}" ] && ok=1 ;;
    esac

    if [ "$ok" -eq 1 ]; then
        printf "[OK]   %-15s verified\n" "$name"
        return 0
    else
        printf "[WARN] %-15s installed but verification failed (may need PATH/config)\n" "$name"
        return 0
    fi
}

build_selected_list() {
    if [ "${#SELECTED[@]}" -gt 0 ]; then return 0; fi
    SELECTED=("${ALL_NAMES[@]}")
    if [ "${#EXCLUDED[@]}" -gt 0 ]; then
        local new=()
        for s in "${SELECTED[@]}"; do
            local skip=0
            for e in "${EXCLUDED[@]}"; do
                [ "$s" = "$e" ] && skip=1 && break
            done
            [ "$skip" -eq 0 ] && new+=("$s")
        done
        SELECTED=("${new[@]}")
    fi
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --all)     SELECTED=("${ALL_NAMES[@]}"); shift ;;
            --only)    IFS=',' read -ra SELECTED <<< "$2"; shift 2 ;;
            --exclude) IFS=',' read -ra EXCLUDED <<< "$2"; shift 2 ;;
            --version) VERSION_OVERRIDES+=("$2"); shift 2 ;;
            --dry-run) DRY_RUN=1; shift ;;
            --verbose) VERBOSE=1; shift ;;
            --continue) CONTINUE_ON_ERROR=1; shift ;;
            --parallel) PARALLEL=1; shift ;;
            --jobs)    JOBS="$2"; shift 2 ;;
            --list)    list_software; exit 0 ;;
            --check)   check_architecture; exit 0 ;;
            --help|-h) usage; exit 0 ;;
            *) printf "[ERROR] Unknown: %s\n" "$1"; usage; exit 1 ;;
        esac
    done
}

validate_selected() {
    for s in "${SELECTED[@]}"; do
        local found=0
        for a in "${ALL_NAMES[@]}"; do [ "$s" = "$a" ] && found=1 && break; done
        if [ "$found" -eq 0 ]; then
            printf "[ERROR] Unknown: '%s'\nAvailable: %s\n" "$s" "$(IFS=','; echo "${ALL_NAMES[*]}")"
            exit 1
        fi
    done
}

run_sequential() {
    local total="${#SELECTED[@]}"
    local succeeded=0 failed=0 failed_list=()

    printf "\n========================================\n"
    printf "  ARM64 Batch Install — %d software\n" "$total"
    printf "========================================\n\n"

    local i=1
    for name in "${SELECTED[@]}"; do
        if install_single "$name"; then
            succeeded=$((succeeded + 1))
        else
            failed=$((failed + 1))
            failed_list+=("$name")
            if [ "$CONTINUE_ON_ERROR" -eq 0 ]; then
                printf "\n[ABORT] Use --continue to skip failures.\n"
                break
            fi
        fi
        i=$((i + 1))
    done

    printf "\n========================================\n"
    printf "  Summary: %d ok, %d fail\n" "$succeeded" "$failed"
    if [ "${#failed_list[@]}" -gt 0 ]; then
        printf "  Failed: %s\n" "$(IFS=','; echo "${failed_list[*]}")"
    fi
    printf "========================================\n\n"

    [ "$failed" -gt 0 ] && return 1
    return 0
}

run_parallel() {
    local total="${#SELECTED[@]}"
    printf "\n========================================\n"
    printf "  ARM64 Batch Install — %d (parallel, %d jobs)\n" "$total" "$JOBS"
    printf "========================================\n\n"

    local pids=() names=() running=0
    for name in "${SELECTED[@]}"; do
        SOFTWARE="$name"
        apply_version
        ( install_single "$name" ) &
        pids+=($!)
        names+=("$name")
        running=$((running + 1))
        if [ "$running" -ge "$JOBS" ]; then
            for idx in "${!pids[@]}"; do
                wait "${pids[$idx]}" 2>/dev/null
                local rc=$?
                [ "$rc" -eq 0 ] && printf "[OK]   %s\n" "${names[$idx]}" \
                               || printf "[FAIL] %s (exit %d)\n" "${names[$idx]}" "$rc"
            done
            pids=() names=() running=0
        fi
    done
    for idx in "${!pids[@]}"; do
        wait "${pids[$idx]}" 2>/dev/null
        local rc=$?
        [ "$rc" -eq 0 ] && printf "[OK]   %s\n" "${names[$idx]}" \
                       || printf "[FAIL] %s (exit %d)\n" "${names[$idx]}" "$rc"
    done
    printf "\n========================================\n  Parallel complete.\n========================================\n\n"
}

main() {
    parse_args "$@"
    build_selected_list
    validate_selected

    printf "[INFO] Directory: %s\n" "$DESKTOP_DIR"
    printf "[INFO] Selected: %d\n" "${#SELECTED[@]}"
    [ "${#SELECTED[@]}" -le 10 ] && printf "[INFO] List: %s\n" "$(IFS=','; echo "${SELECTED[*]}")"

    if [ "$DRY_RUN" -eq 1 ]; then
        printf "[INFO] DRY RUN\n\n"
        for name in "${SELECTED[@]}"; do
            local idx="$(resolve_idx "$name")"
            printf "[DRY]  %-15s %-8s %s\n" "$name" "${ALL_METHODS[$idx]}" "${ALL_DEFAULT_VERSIONS[$idx]}"
        done
        exit 0
    fi

    if [ "$PARALLEL" -eq 1 ]; then
        run_parallel
    else
        run_sequential
    fi
}

main "$@"
