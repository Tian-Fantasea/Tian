#!/usr/bin/env bash

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SOFT_DIR="${BASE_DIR}/softwares"
mkdir -p "$SOFT_DIR"

dl() {
    local url="$1" dest="$2" t="${3:-120}"
    command -v wget >/dev/null 2>&1 && wget --timeout=$t --tries=3 -q -O "$dest" "$url" && return 0
    command -v curl >/dev/null 2>&1 && curl --connect-timeout $t --retry 3 -sL -o "$dest" "$url" && return 0
    return 1
}

link_bin() {
    local sw="$1"; shift
    mkdir -p "${SOFT_DIR}/${sw}/bin"
    for b in "$@"; do
        local p="$(command -v "$b" 2>/dev/null)"
        [ -n "$p" ] && ln -sf "$p" "${SOFT_DIR}/${sw}/bin/$b"
    done
}

apt_install() {
    local v="$1"
    sudo apt-get update -qq
    case "$SW" in
        gcc)       sudo apt-get install -y gcc g++;           link_bin gcc gcc g++ ;;
        python)    sudo apt-get install -y python3 python3-pip python3-venv; link_bin python python3 pip3 ;;
        zstd)      sudo apt-get install -y zstd;              link_bin zstd zstd ;;
        ceph)      sudo apt-get install -y ceph ceph-mds ceph-common fio; link_bin ceph ceph fio ;;
        lz4)       sudo apt-get install -y lz4;               link_bin lz4 lz4 ;;
        protobuf)  sudo apt-get install -y protobuf-compiler; link_bin protobuf protoc ;;
        mysql)     sudo apt-get install -y mysql-server mysql-client sysbench; link_bin mysql mysql mysqld sysbench ;;
        brpc)      sudo apt-get install -y libbrpc-dev protobuf-compiler libprotobuf-dev libssl-dev cmake ;;
        folly)     sudo apt-get install -y libfolly-dev ;;
        openjdk)
            if [ -f /etc/apt/sources.list.d/temurin.list ] || [ -f /etc/apt/sources.list.d/adoptium.list ]; then
                sudo apt-get install -y temurin-${v}-jdk
            else
                sudo apt-get install -y wget apt-transport-https gpg
                wget -O - https://packages.adoptium.net/artifactory/api/gpg/key/public | sudo gpg --dearmor -o /usr/share/keyrings/adoptium.gpg
                echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo $VERSION_CODENAME) main" | sudo tee /etc/apt/sources.list.d/temurin.list
                sudo apt-get update -qq; sudo apt-get install -y temurin-${v}-jdk
            fi; link_bin openjdk java javac ;;
    esac
}

yum_install() {
    local v="$1"
    case "$SW" in
        gcc)       sudo yum install -y gcc gcc-c++;           link_bin gcc gcc g++ ;;
        python)    sudo yum install -y python3 python3-pip;   link_bin python python3 ;;
        zstd)      sudo yum install -y zstd;                  link_bin zstd zstd ;;
        lz4)       sudo yum install -y lz4;                   link_bin lz4 lz4 ;;
        protobuf)  sudo yum install -y protobuf-compiler;     link_bin protobuf protoc ;;
        openjdk)   sudo yum install -y java-${v}-openjdk-devel; link_bin openjdk java javac ;;
        folly)     sudo yum install -y folly-devel cmake gcc-c++ ;;
        brpc)      sudo yum install -y brpc-devel protobuf-compiler cmake gcc-c++ ;;
    esac
}

pip_install() {
    local v="$1"
    [ ! -d "${SOFT_DIR}/venv" ] && python3 -m venv "${SOFT_DIR}/venv"
    export PATH="${SOFT_DIR}/venv/bin:${PATH}"
    case "$SW" in
        faiss)     pip install faiss-cpu numpy ;;
        hnswlib)   pip install hnswlib==${v} numpy ;;
        openviking) pip install openviking==${v} ;;
        pytorch)   pip install torch==${v} --index-url https://download.pytorch.org/whl/cpu numpy ;;
        scann)     pip install scann==${v} numpy ;;
    esac
}

tarball_install() {
    local v="$1" t="${SOFT_DIR}/.tmp"; mkdir -p "$t"
    case "$SW" in
        golang)
            local a="$(uname -m)" g="linux-arm64"; [ "$a" = "x86_64" ] && g="linux-amd64"
            printf "[DL] Go %s\n" "$v"
            dl "https://go.dev/dl/go${v}.${g}.tar.gz" "${t}/go.tgz" || dl "https://mirrors.aliyun.com/golang/go${v}.${g}.tar.gz" "${t}/go.tgz" || return 1
            mkdir -p "${SOFT_DIR}/golang"; tar -C "${SOFT_DIR}/golang" --strip-components=1 -xzf "${t}/go.tgz"
            ;;
        flink)
            printf "[DL] Flink %s\n" "$v"
            dl "https://archive.apache.org/dist/flink/flink-${v}/flink-${v}-bin-scala_2.12.tgz" "${t}/flink.tgz" 300 || dl "https://mirrors.aliyun.com/apache/flink/flink-${v}/flink-${v}-bin-scala_2.12.tgz" "${t}/flink.tgz" 300 || return 1
            tar -xzf "${t}/flink.tgz" -C "${SOFT_DIR}/"
            ;;
        spark)
            printf "[DL] Spark %s\n" "$v"
            dl "https://archive.apache.org/dist/spark/spark-${v}/spark-${v}-bin-hadoop3.tgz" "${t}/spark.tgz" 300 || dl "https://mirrors.aliyun.com/apache/spark/spark-${v}/spark-${v}-bin-hadoop3.tgz" "${t}/spark.tgz" 300 || return 1
            tar -xzf "${t}/spark.tgz" -C "${SOFT_DIR}/"
            ;;
    esac
}

binary_install() {
    local v="$1" t="${SOFT_DIR}/.tmp"; mkdir -p "$t"
    case "$SW" in
        envoy)
            printf "[DL] Envoy %s\n" "$v"
            dl "https://github.com/envoyproxy/envoy/releases/download/v${v}/envoy-v${v}-linux-aarch64.tar.xz" "${t}/envoy.tar.xz" 300 || return 1
            tar -xJf "${t}/envoy.tar.xz" -C "${t}/"
            mkdir -p "${SOFT_DIR}/envoy"
            cp "${t}/envoy-v${v}-linux-aarch64/bin/envoy" "${SOFT_DIR}/envoy/envoy"; chmod +x "${SOFT_DIR}/envoy/envoy"
            ;;
        kubernetes)
            printf "[DL] kubectl v%s + kind\n" "$v"
            mkdir -p "${SOFT_DIR}/kubernetes"
            dl "https://dl.k8s.io/release/v${v}/bin/linux/arm64/kubectl" "${SOFT_DIR}/kubernetes/kubectl" || return 1; chmod +x "${SOFT_DIR}/kubernetes/kubectl"
            dl "https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-arm64" "${SOFT_DIR}/kubernetes/kind" || return 1; chmod +x "${SOFT_DIR}/kubernetes/kind"
            ;;
        oceanbase)
            printf "[DL] OceanBase %s\n" "$v"
            dl "https://github.com/oceanbase/oceanbase/releases/download/v${v}/observer-v${v}-linux-aarch64.tar.gz" "${t}/ob.tgz" 300 || return 1
            mkdir -p "${SOFT_DIR}/oceanbase"; tar -xzf "${t}/ob.tgz" -C "${SOFT_DIR}/oceanbase/"
            ;;
    esac
}

source_install() {
    local v="$1" t="${SOFT_DIR}/.tmp"; mkdir -p "$t"
    case "$SW" in
        redis)
            printf "[DL+BUILD] Redis %s\n" "$v"
            dl "https://github.com/redis/redis/archive/refs/tags/v${v}.tar.gz" "${t}/redis.tgz" || return 1
            tar -xzf "${t}/redis.tgz" -C "${t}/"
            make -j 4 -C "${t}/redis-${v}"
            mkdir -p "${SOFT_DIR}/redis/bin"
            cp "${t}/redis-${v}/src/redis-server" "${t}/redis-${v}/src/redis-cli" "${t}/redis-${v}/src/redis-benchmark" "${SOFT_DIR}/redis/bin/"
            ;;
        rocksdb)
            printf "[DL+BUILD] RocksDB %s\n" "$v"
            git clone --depth 1 --branch v${v} https://github.com/facebook/rocksdb.git "${t}/rocksdb" || return 1
            make -j 4 USE_JEMALLOC=1 db_bench -C "${t}/rocksdb"
            mkdir -p "${SOFT_DIR}/rocksdb"
            cp "${t}/rocksdb/db_bench" "${SOFT_DIR}/rocksdb/"
            ;;
        brpc)
            printf "[DL+BUILD] brpc %s\n" "$v"
            git clone --depth 1 --branch v${v} https://github.com/apache/brpc.git "${t}/brpc" || return 1
            mkdir -p "${t}/brpc/build"; cmake -S "${t}/brpc" -B "${t}/brpc/build" && make -j 4 -C "${t}/brpc/build"
            mkdir -p "${SOFT_DIR}/brpc/bin"
            cp "${t}/brpc/build/brpc_*" "${SOFT_DIR}/brpc/bin/" 2>/dev/null; cp "${t}/brpc/build/examples/*" "${SOFT_DIR}/brpc/bin/" 2>/dev/null
            ;;
        folly)
            printf "[DL+BUILD] folly %s\n" "$v"
            git clone --depth 1 --branch v${v} https://github.com/facebook/folly.git "${t}/folly" || return 1
            mkdir -p "${t}/folly/build"; cmake -S "${t}/folly" -B "${t}/folly/build" && make -j 4 -C "${t}/folly/build"
            sudo make install -C "${t}/folly/build"
            ;;
    esac
}

go_install() {
    local v="$1"
    [ ! -f "${SOFT_DIR}/golang/bin/go" ] && { SW=golang; tarball_install "${GOLANG_VERSION:-1.26.4}"; }
    export GOTOOLCHAIN=local PATH="${SOFT_DIR}/golang/bin:${PATH}"
    case "$SW" in
        bolt)      mkdir -p "${SOFT_DIR}/bolt"; cd "${SOFT_DIR}/bolt"; [ ! -f go.mod ] && go mod init bolt-benchmark ;;
        cloudwego) mkdir -p "${SOFT_DIR}/cloudwego" ;;
    esac
}

git_install() {
    local v="$1"
    case "$SW" in
        sonic-cpp) printf "[DL] sonic-cpp %s\n" "$v"; mkdir -p "${SOFT_DIR}/sonic-cpp"; git clone --depth 1 --branch v${v} https://github.com/bytedance/sonic-cpp.git "${SOFT_DIR}/sonic-cpp" ;;
    esac
}

REG=(
    "gcc|GCC_VERSION|14|apt"           "python|PYTHON_VERSION|3.13|apt"
    "zstd|ZSTD_VERSION|1.5.7|apt"      "openjdk|OPENJDK_VERSION|21|apt"
    "mysql|MYSQL_VERSION|8.4.9|apt"    "ceph|VERSION|19.2.0|apt"
    "lz4|VERSION|1.10.0|apt"           "protobuf|VERSION|29.4|apt"
    "brpc|BRPC_VERSION|1.6.0|apt"      "folly|VERSION|2024.10.14.00|apt"
    "faiss|SOFTWARE_VERSION|1.14.2|pip" "hnswlib|HNSWLIB_VERSION|0.8.0|pip"
    "openviking|SOFTWARE_VERSION|v0.3.24|pip" "pytorch|PYTORCH_VERSION|2.7.0|pip"
    "scann|SOFTWARE_VERSION|1.4.2|pip" "golang|VERSION|1.26.4|tarball"
    "flink|VERSION|2.1.0|tarball"      "spark|SOFTWARE_VERSION|4.1.2|tarball"
    "envoy|SOFTWARE_VERSION|1.38.2|binary" "kubernetes|VERSION|1.33.12|binary"
    "oceanbase|SOFTWARE_VERSION|4.2.1.8|binary" "redis|SOFTWARE_VERSION|8.0.2|source"
    "rocksdb|SOFTWARE_VERSION|9.10.0|source" "brpc|BRPC_VERSION|1.6.0|source"
    "folly|VERSION|2024.10.14.00|source" "bolt|BOLT_VERSION|1.4.3|go"
    "cloudwego|KITEX_VERSION|v0.16.2|go" "sonic-cpp|SONIC_CPP_VERSION|1.0.2|git"
)

NM=() VR=() DF=() MT=()
for e in "${REG[@]}"; do IFS='|' read -r n v d m <<< "$e"; NM+=("$n"); VR+=("$v"); DF+=("$d"); MT+=("$m"); done

SEL=() EXC=() VOV=() DRY=0 CONT=0 PAR=0 JBS=4

i_of() { local t="$1" i=0; for n in "${NM[@]}"; do [ "$n" = "$t" ] && echo $i && return; i=$((i+1)); done; echo -1; }

set_v() {
    local i="$(i_of "$SW")"; [ "$i" = "-1" ] && return
    for ov in "${VOV[@]}"; do local on="${ov%%=*}" ovv="${ov#*=}"
        [ "$on" = "$SW" ] && export "${VR[$i]}"="$ovv" && SV="$ovv" && return; done
    export "${VR[$i]}"="${DF[$i]}"; SV="${DF[$i]}"
}

do_one() {
    local name="$1"; SW="$name"
    local i="$(i_of "$name")"; [ "$i" = "-1" ] && echo "[FAIL] $name" && return 1
    local m="${MT[$i]}"; set_v
    printf "[RUN] %-15s %-8s %-14s -> softwares/%s/\n" "$name" "$m" "$SV" "$name"
    [ "$DRY" -eq 1 ] && return 0
    case "$m" in
        apt)     [ -f /etc/debian_version ] || [ -f /etc/lsb-release ] && apt_install "$SV" || yum_install "$SV" ;;
        pip)     pip_install "$SV" ;;
        tarball) tarball_install "$SV" ;;
        binary)  binary_install "$SV" ;;
        source)  source_install "$SV" ;;
        go)      go_install "$SV" ;;
        git)     git_install "$SV" ;;
        *)       echo "[FAIL] bad method $m"; return 1 ;;
    esac
}

rm_tmp() { rm -rf "${SOFT_DIR}/.tmp"; }

list() {
    printf "\n%-3s %-15s %-12s %-8s %-25s\n" "#" "Software" "Default" "Method" "In softwares/"
    printf "%-3s %-15s %-12s %-8s %-25s\n" "---" "---------------" "--------" "------" "-------------------------"
    local i=0; for n in "${NM[@]}"; do printf "%-3s %-15s %-12s %-8s %s/\n" "$((i+1))" "$n" "${DF[$i]}" "${MT[$i]}" "$n"; i=$((i+1)); done
    printf "\n%d software | Install to: %s\n\n" "${#NM[@]}" "$SOFT_DIR"
}

parse() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --all)     SEL=("${NM[@]}"); shift ;;
            --only)    IFS=',' read -ra SEL <<< "$2"; shift 2 ;;
            --exclude) IFS=',' read -ra EXC <<< "$2"; shift 2 ;;
            --version) VOV+=("$2"); shift 2 ;;
            --dry-run) DRY=1; shift ;;
            --continue) CONT=1; shift ;;
            --parallel) PAR=1; shift ;;
            --jobs)    JBS="$2"; shift 2 ;;
            --list)    list; exit 0 ;;
            --check)   echo "Arch: $(uname -m)"; for c in sudo bash python3 git cmake make; do command -v "$c" >/dev/null && echo "[OK] $c" || echo "[MISS] $c"; done; exit 0 ;;
            --help|-h) echo 'Usage: batch_install.sh [--all|--only X,Y|--exclude X|--version K=V|--dry-run|--continue|--list|--check]'; exit 0 ;;
            *) echo "[ERROR] $1"; exit 1 ;;
        esac
    done
}

valid() { for s in "${SEL[@]}"; do local f=0; for a in "${NM[@]}"; do [ "$s" = "$a" ] && f=1 && break; done; [ "$f" -eq 0 ] && echo "[ERROR] Unknown: $s" && exit 1; done; }

mk_sel() {
    [ "${#SEL[@]}" -gt 0 ] && return
    SEL=("${NM[@]}")
    [ "${#EXC[@]}" -eq 0 ] && return
    local nw=(); for s in "${SEL[@]}"; do local sk=0; for e in "${EXC[@]}"; do [ "$s" = "$e" ] && sk=1 && break; done; [ "$sk" -eq 0 ] && nw+=("$s"); done; SEL=("${nw[@]}")
}

run_seq() {
    local ok=0 fl=0 fls=()
    printf "\n======== ARM64 Install %d software -> %s ========\n\n" "${#SEL[@]}" "$SOFT_DIR"
    for name in "${SEL[@]}"; do
        do_one "$name" && ok=$((ok+1)) || { fl=$((fl+1)); fls+=("$name"); [ "$CONT" -eq 0 ] && echo "[ABORT] --continue to skip" && break; }
    done
    rm_tmp
    printf "\n======== Done: %d ok %d fail ========\n" "$ok" "$fl"
    [ "${#fls[@]}" -gt 0 ] && printf "Failed: %s\n" "$(IFS=','; echo "${fls[*]}")"
    printf "All at: %s\n========\n\n" "$SOFT_DIR"
    [ "$fl" -gt 0 ] && return 1
}

run_par() {
    printf "\n======== ARM64 Install %d software (par %d jobs) -> %s ========\n\n" "${#SEL[@]}" "$JBS" "$SOFT_DIR"
    local pids=() ns=() r=0
    for name in "${SEL[@]}"; do SW="$name"; set_v; ( do_one "$name" ) &
        pids+=($!); ns+=("$name"); r=$((r+1))
        [ "$r" -ge "$JBS" ] && { for j in "${!pids[@]}"; do wait "${pids[$j]}" 2>/dev/null; [ $? -eq 0 ] && echo "[OK] ${ns[$j]}" || echo "[FAIL] ${ns[$j]}"; done; pids=() ns=() r=0; }
    done
    for j in "${!pids[@]}"; do wait "${pids[$j]}" 2>/dev/null; [ $? -eq 0 ] && echo "[OK] ${ns[$j]}" || echo "[FAIL] ${ns[$j]}"; done
    rm_tmp
    printf "\n======== Done | All at: %s ========\n\n" "$SOFT_DIR"
}

main() {
    parse "$@"; mk_sel; valid
    echo "[INFO] Install to: $SOFT_DIR | Selected: ${#SEL[@]}"
    [ "$DRY" -eq 1 ] && { for name in "${SEL[@]}"; do local i="$(i_of "$name")"; printf "[DRY] %-15s %-8s %s -> softwares/%s/\n" "$name" "${MT[$i]}" "${DF[$i]}" "$name"; done; echo; echo "All into $SOFT_DIR"; exit 0; }
    mkdir -p "$SOFT_DIR"
    [ "$PAR" -eq 1 ] && run_par || run_seq
}

main "$@"
