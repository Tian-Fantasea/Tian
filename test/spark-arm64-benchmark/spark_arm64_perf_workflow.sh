#!/bin/bash
#
# ============================================================================
# Apache Spark ARM64 Performance Benchmark Workflow
# ============================================================================
# Repository: https://github.com/apache/spark
# Reference benchmarks:
#   - TPC-DS (industry standard for Spark SQL, used by Databricks/Amazon/etc.)
#   - HiBench (Intel's big data benchmark suite)
#   - Spark micro-benchmarks (sort, shuffle, aggregation, etc.)
#   - MLlib benchmarks (classification, regression, clustering)
#
# Architecture: aarch64 / arm64
# OS: Ubuntu 22.04+ (adjust for other distros)
# ============================================================================
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
RESULT_DIR="${SCRIPT_DIR}/results"
DATA_DIR="${SCRIPT_DIR}/data"
TPCDS_KIT_DIR="${DATA_DIR}/tpcds-kit_2.13"
SPARK_INSTALL_DIR="${SCRIPT_DIR}/spark"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

SPARK_VERSION="4.1.2"
HADOOP_VERSION="3"
JAVA_VERSION="17"
SCALA_VERSION="2.13"

SPARK_CORES="$(nproc)"
SPARK_MEMORY="$(awk '/MemTotal/ {printf "%.0f", $2/1024*0.8}' /proc/meminfo 2>/dev/null || echo 8192)"

mkdir -p "${LOG_DIR}" "${RESULT_DIR}" "${DATA_DIR}"

log() { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
warn() { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
err() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

# ============================================================================
# Phase 1: Environment Preparation & Spark Installation on ARM64
# ============================================================================
phase1_install() {
    log "============================================"
    log "Phase 1: Environment Preparation & Spark Installation"
    log "============================================"

    # --- 1.1 Verify ARM64 architecture ---
    log "Verifying ARM64 architecture..."
    local arch="$(uname -m)"
    if [[ "${arch}" != "aarch64" && "${arch}" != "arm64" ]]; then
        err "This workflow is designed for ARM64. Current architecture: ${arch}"
        exit 1
    fi
    log "Architecture confirmed: ${arch}"

    # --- 1.2 Install system dependencies ---
    log "Installing system dependencies..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update
        sudo apt-get install -y \
            build-essential gcc g++ make cmake \
            python3 python3-pip python3-dev \
            git wget curl unzip \
            libopenblas-dev liblapack-dev
    elif command -v yum &>/dev/null; then
        sudo yum groupinstall -y "Development Tools"
        sudo yum install -y python3 python3-pip git wget curl unzip \
            openblas-devel lapack-devel
    elif command -v dnf &>/dev/null; then
        sudo dnf groupinstall -y "Development Tools"
        sudo dnf install -y python3 python3-pip git wget curl unzip \
            openblas-devel lapack-devel
    else
        warn "Unsupported package manager. Please install dependencies manually."
    fi

    # --- 1.3 Install Java (ARM64 compatible JDK) ---
    log "Installing Eclipse Temurin JDK ${JAVA_VERSION} for ARM64..."
    if ! java -version 2>&1 | grep -q "${JAVA_VERSION}"; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y apt-transport-https
            wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public | \
                sudo tee /etc/apt/trusted.gpg.d/adoptium.asc
            echo "deb https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo "$VERSION_CODENAME") main" | \
                sudo tee /etc/apt/sources.list.d/adoptium.list
            sudo apt-get update
            sudo apt-get install -y temurin-${JAVA_VERSION}-jdk
        elif command -v yum &>/dev/null || command -v dnf &>/dev/null; then
            local pm="$(command -v dnf &>/dev/null && echo dnf || echo yum)"
            sudo ${pm} install -y temurin-${JAVA_VERSION}-jdk
        fi
    fi

    export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(which java)")")")"
    log "JAVA_HOME: ${JAVA_HOME}"
    java -version 2>&1 | tee "${LOG_DIR}/java_version_${TIMESTAMP}.log"

    # --- 1.4 Install Python packages ---
    log "Installing Python dependencies..."
    python3 -m venv "${SCRIPT_DIR}/venv"
    "${SCRIPT_DIR}/venv/bin/pip" install --upgrade pip setuptools
    "${SCRIPT_DIR}/venv/bin/pip" install numpy pandas scipy matplotlib pyarrow

    # --- 1.5 Download and install Apache Spark ---
    log "Downloading Apache Spark ${SPARK_VERSION} for ARM64..."
    local spark_url="https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz"
    local spark_tmp="/tmp/spark-${SPARK_VERSION}.tgz"

    if [[ ! -d "${SPARK_INSTALL_DIR}" ]]; then
        wget -q -O "${spark_tmp}" "${spark_url}"
        tar -xzf "${spark_tmp}" -C "${SCRIPT_DIR}"
        mv "${SCRIPT_DIR}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP}" "${SPARK_INSTALL_DIR}"
        rm -f "${spark_tmp}"
    fi
    log "Spark extracted to: ${SPARK_INSTALL_DIR}"

    export SPARK_HOME="${SPARK_INSTALL_DIR}"
    export PATH="${SPARK_HOME}/bin:${SPARK_HOME}/sbin:${PATH}"

    # --- 1.6 Configure Spark for ARM64 ---
    log "Configuring Spark for ARM64 local mode..."
    cat > "${SPARK_HOME}/conf/spark-env.sh" <<SPARK_ENV
export JAVA_HOME=${JAVA_HOME}
export SPARK_MASTER_HOST=localhost
export SPARK_MASTER_PORT=7077
export SPARK_WORKER_CORES=${SPARK_CORES}
export SPARK_WORKER_MEMORY=${SPARK_MEMORY}m
export SPARK_WORKER_PORT=8888
export SPARK_WORKER_WEBUI_PORT=8081
SPARK_ENV

    cp "${SPARK_HOME}/conf/spark-defaults.conf.template" "${SPARK_HOME}/conf/spark-defaults.conf"
    cat >> "${SPARK_HOME}/conf/spark-defaults.conf" <<SPARK_CONF
spark.master                    local[${SPARK_CORES}]
spark.driver.memory             ${SPARK_MEMORY}m
spark.executor.memory           ${SPARK_MEMORY}m
spark.executor.cores            ${SPARK_CORES}
spark.serializer                org.apache.spark.serializer.KryoSerializer
spark.sql.shuffle.partitions    ${SPARK_CORES}
spark.sql.adaptive.enabled      true
spark.sql.adaptive.shuffle.partition.enabled true
spark.sql.adaptive.skewJoin.enabled  true
spark.driver.extraJavaOptions   -XX:+UseG1GC -XX:MaxGCPauseMillis=200
spark.executor.extraJavaOptions -XX:+UseG1GC -XX:MaxGCPauseMillis=200
SPARK_CONF

    log "Spark configuration completed."
}

# ============================================================================
# Phase 2: Verify Installation
# ============================================================================
phase2_verify() {
    log "============================================"
    log "Phase 2: Verify Spark Installation & Collect Version Info"
    log "============================================"

    local verify_log="${LOG_DIR}/verify_${TIMESTAMP}.log"

    # --- 2.1 Verify spark-shell / pyspark ---
    log "Testing spark-shell (Scala)..."
    timeout 60 "${SPARK_HOME}/bin/spark-shell" --master "local[2]" -i \
        "${SCRIPT_DIR}/scripts/verify_scala.scala" 2>&1 | tee -a "${verify_log}"

    log "Testing pyspark (Python)..."
    timeout 60 "${SPARK_HOME}/bin/pyspark" --master "local[2]" \
        "${SCRIPT_DIR}/scripts/verify_python.py" 2>&1 | tee -a "${verify_log}"

    # --- 2.2 Collect version information ---
    log "Collecting version information..."
    cat > "${RESULT_DIR}/environment_info_${TIMESTAMP}.json" <<ENV_JSON
{
  "timestamp": "${TIMESTAMP}",
  "architecture": "$(uname -m)",
  "kernel": "$(uname -r)",
  "os": "$(cat /etc/os-release 2>/dev/null | head -1 || echo unknown)",
  "cpu_cores": "$(nproc)",
  "cpu_model": "$(cat /proc/cpuinfo 2>/dev/null | grep 'model name' | head -1 | cut -d: -f2 | xargs || echo unknown)",
  "memory_mb": "$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo unknown)",
  "spark_version": "${SPARK_VERSION}",
  "java_version": "$(java -version 2>&1 | head -1)",
  "java_home": "${JAVA_HOME}",
  "scala_version": "${SCALA_VERSION}",
  "python_version": "$(python3 --version 2>&1)",
  "spark_home": "${SPARK_HOME}",
  "spark_cores_config": "${SPARK_CORES}",
  "spark_memory_config": "${SPARK_MEMORY}m"
}
ENV_JSON

    log "Environment info saved to: ${RESULT_DIR}/environment_info_${TIMESTAMP}.json"
    cat "${RESULT_DIR}/environment_info_${TIMESTAMP}.json"

    # --- 2.3 Run SparkPi sanity check ---
    log "Running SparkPi sanity check..."
    timeout 120 "${SPARK_HOME}/bin/spark-submit" \
        --class org.apache.spark.examples.SparkPi \
        --master "local[${SPARK_CORES}]" \
        "${SPARK_HOME}/examples/jars/spark-examples_*.jar" 100 \
        2>&1 | tee "${LOG_DIR}/sparkpi_${TIMESTAMP}.log"

    log "Phase 2 verification completed."
}

# ============================================================================
# Phase 3: Performance Benchmark Execution
# ============================================================================
#
# Benchmark Suite Overview:
#   A) TPC-DS Benchmark    - Industry standard SQL/DataFrame workload (102 queries)
#   B) Micro-Benchmarks    - Core engine operations (sort, shuffle, join, aggregate)
#   C) MLlib Benchmarks    - Machine learning algorithms performance
#   D) Streaming Benchmark - Structured Streaming throughput
#
# Performance Metrics:
#   - Execution time (ms) per query / operation
#   - Throughput (queries/hour for TPC-DS)
#   - CPU utilization (%)
#   - Memory usage (peak RSS)
#   - GC time (ms)
#   - Shuffle read/write bytes
#   - Disk I/O bytes
#
# Datasets:
#   - TPC-DS: scale factors 1GB (SF1), 10GB (SF10), 100GB (SF100)
#   - Micro-benchmarks: configurable data sizes (1M, 10M, 100M rows)
#   - MLlib: built-in sample datasets + generated data
#
# ============================================================================

phase3_tpcds() {
    log "============================================"
    log "Phase 3A: TPC-DS Benchmark"
    log "============================================"
    log "Benchmark: TPC-DS (Transaction Processing Performance Council - Decision Support)"
    log "Description: Industry standard benchmark for evaluating Spark SQL performance."
    log "             Used by Databricks, Amazon, Microsoft, and others for Spark benchmarking."
    log "             Contains 102 analytical queries simulating a retail data warehouse."
    log "Metrics:    Query execution time, throughput (queries/hour), resource utilization"
    log "Dataset:    TPC-DS data at scale factor ${TPCDS_SCALE}GB"
    log "Reference:  https://www.tpc.org/tpcds/, https://github.com/apache/spark/tree/master/sql/core/src/test/resources/tpcds"
    log "============================================"

    local tpcds_scale="${TPCDS_SCALE:-1}"

    # --- 3A.1 Setup TPC-DS data generation kit ---
    if [[ ! -d "${TPCDS_KIT_DIR}" ]]; then
        log "Cloning TPC-DS data generation kit..."
        git clone https://github.com/apache/spark.git /tmp/spark-src-tpcds --depth 1 --sparse
        cd /tmp/spark-src-tpcds && git sparse-checkout set sql/core/src/test/resources/tpcds

        # Alternative: use standalone TPC-DS kit
        log "Downloading standalone TPC-DS kit..."
        git clone https://github.com/databricks/spark-sql-perf.git "${DATA_DIR}/spark-sql-perf" --depth 1 || true
    fi

    # --- 3A.2 Generate TPC-DS data ---
    log "Generating TPC-DS data at SF=${tpcds_scale}..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        --conf spark.sql.parquet.compression.codec=snappy \
        "${SCRIPT_DIR}/scripts/tpcds_datagen.py" \
        "${tpcds_scale}" "${DATA_DIR}/tpcds_sf${tpcds_scale}" \
        2>&1 | tee "${LOG_DIR}/tpcds_datagen_sf${tpcds_scale}_${TIMESTAMP}.log"

    # --- 3A.3 Run TPC-DS queries ---
    log "Running TPC-DS queries (SF=${tpcds_scale})..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        --conf spark.sql.shuffle.partitions=${SPARK_CORES} \
        --conf spark.sql.adaptive.enabled=true \
        "${SCRIPT_DIR}/scripts/tpcds_benchmark.py" \
        "${DATA_DIR}/tpcds_sf${tpcds_scale}" "${RESULT_DIR}" "${tpcds_scale}" \
        2>&1 | tee "${LOG_DIR}/tpcds_benchmark_sf${tpcds_scale}_${TIMESTAMP}.log"

    log "TPC-DS benchmark completed."
}

phase3_micro() {
    log "============================================"
    log "Phase 3B: Micro-Benchmarks"
    log "============================================"
    log "Benchmark: Spark Core Micro-Benchmarks"
    log "Description: Tests core engine operations to measure individual component performance."
    log "             Inspired by HiBench (Intel) micro-benchmark suite."
    log "Metrics:    Execution time (ms), throughput (records/s), shuffle data volume"
    log "Datasets:   Generated data of ${MICRO_DATA_SIZE} rows"
    log "Tests:      Sort, Shuffle, Aggregate, Join, WordCount, Scan, GroupBy"
    log "============================================"

    local data_size="${MICRO_DATA_SIZE:-10000000}"

    log "Running micro-benchmarks with ${data_size} rows..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        "${SCRIPT_DIR}/scripts/micro_benchmark.py" \
        "${data_size}" "${RESULT_DIR}" \
        2>&1 | tee "${LOG_DIR}/micro_benchmark_${TIMESTAMP}.log"

    log "Micro-benchmarks completed."
}

phase3_mllib() {
    log "============================================"
    log "Phase 3C: MLlib Benchmarks"
    log "============================================"
    log "Benchmark: Spark MLlib Machine Learning Benchmarks"
    log "Description: Evaluates performance of ML algorithms commonly used in production."
    log "             Covers classification, regression, clustering, and collaborative filtering."
    log "Metrics:    Training time (s), inference time (ms), model accuracy"
    log "Datasets:   Generated synthetic datasets (configurable size)"
    log "Tests:      LogisticRegression, RandomForest, KMeans, LinearRegression, ALS"
    log "============================================"

    local ml_data_size="${ML_DATA_SIZE:-1000000}"

    log "Running MLlib benchmarks with ${ml_data_size} samples..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        "${SCRIPT_DIR}/scripts/mllib_benchmark.py" \
        "${ml_data_size}" "${RESULT_DIR}" \
        2>&1 | tee "${LOG_DIR}/mllib_benchmark_${TIMESTAMP}.log"

    log "MLlib benchmarks completed."
}

phase3_streaming() {
    log "============================================"
    log "Phase 3D: Structured Streaming Benchmark"
    log "============================================"
    log "Benchmark: Structured Streaming Throughput Benchmark"
    log "Description: Measures streaming data processing throughput and latency."
    log "             Tests rate source -> processing -> console/memory sink pipeline."
    log "Metrics:    Throughput (records/s), processing latency (ms), end-to-end latency (ms)"
    log "Datasets:   Spark built-in rate source (configurable rows-per-second)"
    log "============================================"

    local stream_rate="${STREAM_RATE:-10000}"

    log "Running streaming benchmark at ${stream_rate} rows/s..."
    "${SPARK_HOME}/bin/spark-submit" \
        --master "local[${SPARK_CORES}]" \
        --driver-memory "${SPARK_MEMORY}m" \
        "${SCRIPT_DIR}/scripts/streaming_benchmark.py" \
        "${stream_rate}" "${RESULT_DIR}" \
        2>&1 | tee "${LOG_DIR}/streaming_benchmark_${TIMESTAMP}.log"

    log "Streaming benchmark completed."
}

# ============================================================================
# Phase 4: Results Collection & Presentation
# ============================================================================
phase4_results() {
    log "============================================"
    log "Phase 4: Results Collection & Presentation"
    log "============================================"

    local final_result="${RESULT_DIR}/final_report_${TIMESTAMP}"
    local json_result="${final_result}.json"
    local html_result="${final_result}.html"
    local summary_result="${final_result}_summary.txt"

    # --- 4.1 Aggregate all results into single JSON ---
    log "Aggregating results..."
    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \
        "${RESULT_DIR}" "${TIMESTAMP}" "${json_result}"

    # --- 4.2 Generate summary text ---
    log "Generating summary..."
    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \
        "${json_result}" "${summary_result}"

    cat "${summary_result}"

    # --- 4.3 Generate HTML report with charts ---
    log "Generating HTML report with visualization..."
    python3 "${SCRIPT_DIR}/scripts/generate_html_report.py" \
        "${json_result}" "${html_result}"

    log "Results saved:"
    log "  JSON:   ${json_result}"
    log "  Summary: ${summary_result}"
    log "  HTML:   ${html_result}"
    log ""
    log "Open the HTML report in a browser to view interactive charts:"
    log "  file://${html_result}"
    log "============================================"
    log "ALL BENCHMARKS COMPLETED SUCCESSFULLY"
    log "============================================"
}

# ============================================================================
# Main Entry Point
# ============================================================================
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║   Apache Spark ARM64 Performance Benchmark Workflow        ║"
    echo "║   Spark Version: ${SPARK_VERSION}                            ║"
    echo "║   Architecture:  ARM64 (aarch64)                           ║"
    echo "║   Repository:    https://github.com/apache/spark           ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    local phases="${SPARK_BENCH_PHASES:-1,2,3,4}"
    local run_tpcds=0
    local run_micro=0
    local run_mllib=0
    local run_streaming=0

    IFS=',' read -ra PHASE_ARRAY <<< "${phases}"
    for p in "${PHASE_ARRAY[@]}"; do
        case "${p}" in
            1) phase1_install ;;
            2) phase2_verify ;;
            3)
                run_tpcds=1; run_micro=1; run_mllib=1; run_streaming=1
                ;;
            3a) run_tpcds=1 ;;
            3b) run_micro=1 ;;
            3c) run_mllib=1 ;;
            3d) run_streaming=1 ;;
            4) phase4_results ;;
            *)
                err "Unknown phase: ${p}"
                usage
                ;;
        esac
    done

    if [[ ${run_tpcds} -eq 1 ]]; then phase3_tpcds; fi
    if [[ ${run_micro} -eq 1 ]];  then phase3_micro; fi
    if [[ ${run_mllib} -eq 1 ]];  then phase3_mllib; fi
    if [[ ${run_streaming} -eq 1 ]]; then phase3_streaming; fi
}

usage() {
    cat <<USAGE
Usage: $(basename "$0") [OPTIONS]

Apache Spark ARM64 Performance Benchmark Workflow

Options:
  -p, --phases PHASES    Comma-separated phases to run (default: 1,2,3,4)
                          Phase 1:  Install Spark & dependencies
                          Phase 2:  Verify installation & collect version info
                          Phase 3:  Run all benchmarks (3a=TPC-DS, 3b=Micro, 3c=MLlib, 3d=Streaming)
                          Phase 4:  Collect & present results

  -s, --spark-version VER   Spark version (default: ${SPARK_VERSION})
  -v, --tpcds-scale SF      TPC-DS scale factor in GB (default: 1)
  -d, --data-size SIZE      Micro-benchmark data size in rows (default: 10000000)
  -m, --ml-data-size SIZE   MLlib data size in samples (default: 1000000)
  -r, --stream-rate RATE    Streaming rows per second (default: 10000)
  -h, --help                Show this help

Examples:
  # Full workflow (install, verify, benchmark, report)
  $(basename "$0")

  # Run only benchmarks (assuming Spark already installed)
  $(basename "$0") -p 3

  # Run only TPC-DS at SF=10
  $(basename "$0") -p 3a -v 10

  # Run micro-benchmarks with 100M rows
  $(basename "$0") -p 3b -d 100000000

  # Skip install, run benchmarks and report
  $(basename "$0") -p 3,4
USAGE
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--phases)     SPARK_BENCH_PHASES="$2"; shift 2 ;;
        -s|--spark-version) SPARK_VERSION="$2"; shift 2 ;;
        -v|--tpcds-scale) TPCDS_SCALE="$2"; shift 2 ;;
        -d|--data-size) MICRO_DATA_SIZE="$2"; shift 2 ;;
        -m|--ml-data-size) ML_DATA_SIZE="$2"; shift 2 ;;
        -r|--stream-rate) STREAM_RATE="$2"; shift 2 ;;
        -h|--help)       usage ;;
        *)               err "Unknown option: $1"; usage ;;
    esac
done

main