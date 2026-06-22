#!/usr/bin/env bash

DESKTOP_DIR="$(cd "$(dirname "$0")" && pwd)"

SOFTWARE_REGISTRY=(
    "bolt|BOLT_VERSION|1.4.3"
    "brpc|BRPC_VERSION|1.6.0"
    "ceph|VERSION|19.2.0"
    "cloudwego|KITEX_VERSION|v0.16.2"
    "envoy|SOFTWARE_VERSION|1.38.2"
    "faiss|SOFTWARE_VERSION|1.14.2"
    "flink|VERSION|2.1.0"
    "folly|VERSION|2024.10.14.00"
    "gcc|GCC_VERSION|14"
    "golang|VERSION|1.26.4"
    "hnswlib|HNSWLIB_VERSION|0.8.0"
    "kubernetes|VERSION|1.33.12"
    "lz4|VERSION|1.10.0"
    "mysql|MYSQL_VERSION|8.4.9"
    "oceanbase|SOFTWARE_VERSION|4.2.1.8"
    "openjdk|OPENJDK_VERSION|21"
    "openviking|SOFTWARE_VERSION|v0.3.24"
    "protobuf|VERSION|29.4"
    "python|PYTHON_VERSION|3.13"
    "pytorch|PYTORCH_VERSION|2.7.0"
    "redis|SOFTWARE_VERSION|8.0.2"
    "rocksdb|SOFTWARE_VERSION|9.10.0"
    "scann|SOFTWARE_VERSION|1.4.2"
    "sonic-cpp|SONIC_CPP_VERSION|1.0.2"
    "spark|SOFTWARE_VERSION|4.1.2"
    "zstd|ZSTD_VERSION|1.5.7"
)

CLOUDWEGO_EXTRA="HERTZ_VERSION|v0.10.4"

ALL_NAMES=()
for entry in "${SOFTWARE_REGISTRY[@]}"; do
    name="${entry%%|*}"
    ALL_NAMES+=("$name")
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

ARM64 Batch Install Script — install/benchmark all software under /desktop

Options:
  --all                   Install all 26 software (default)
  --only <list>           Install only specified software (comma-separated)
  --exclude <list>        Exclude specified software from full install
  --version <key=val>     Override version: e.g. --version redis=7.2.4
                          Supports multiple: --version redis=7.2.4 --version golang=1.24.3
  --dry-run               Show what would be installed without running
  --verbose               Print detailed output from each test.sh
  --continue              Continue on error (skip failed, install next)
  --parallel              Run installs in parallel (use with --jobs)
  --jobs <N>              Max parallel jobs (default: 4)
  --list                  List all available software and default versions
  --check                 Check ARM64 architecture and dependencies only
  --help                  Show this help message

Examples:
  batch_install.sh                              # Install all 26 software
  batch_install.sh --only redis,rocksdb         # Install only redis and rocksdb
  batch_install.sh --exclude gcc,python         # Install all except gcc and python
  batch_install.sh --only redis --version redis=7.2.4  # Install redis v7.2.4
  batch_install.sh --only flink,spark --version flink=1.20.0 --version spark=3.5.0
  batch_install.sh --dry-run --only golang      # Preview golang install plan
  batch_install.sh --list                       # Show all software with versions
USAGE
}

list_software() {
    printf "\n%-4s %-15s %-20s %-15s %s\n" "#" "Software" "Version Env Var" "Default" "Install Method"
    printf "%-4s %-15s %-20s %-15s %s\n" "---" "---------------" "--------------------" "---------------" "----------------"
    local idx=1
    for entry in "${SOFTWARE_REGISTRY[@]}"; do
        IFS='|' read -r name var default <<< "$entry"
        local method="test.sh"
        printf "%-4s %-15s %-20s %-15s %s\n" "$idx" "$name" "$var" "$default" "$method"
        idx=$((idx + 1))
    done
    printf "\nNote: cloudwego also uses HERTZ_VERSION=%s (for Hertz framework)\n" "v0.10.4"
    printf "Total: %d software packages\n\n" "${#ALL_NAMES[@]}"
}

check_architecture() {
    local arch="$(uname -m)"
    printf "[CHECK] Architecture: %s\n" "$arch"
    if [ "$arch" != "aarch64" ] && [ "$arch" != "arm64" ]; then
        printf "[WARN] Not running on ARM64/aarch64! Current: %s\n" "$arch"
        printf "[WARN] Some benchmarks may not work correctly.\n"
        return 1
    fi
    printf "[CHECK] ARM64 architecture confirmed.\n"

    local missing=0
    for cmd in bash python3 curl wget; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            printf "[MISS] %s not found\n" "$cmd"
            missing=$((missing + 1))
        else
            printf "[OK]   %s found\n" "$cmd"
        fi
    done
    if [ "$missing" -gt 0 ]; then
        printf "[WARN] %d dependencies missing. Install them first.\n" "$missing"
        return 1
    fi
    return 0
}

resolve_version_var() {
    local target_name="$1"
    for entry in "${SOFTWARE_REGISTRY[@]}"; do
        IFS='|' read -r name var default <<< "$entry"
        if [ "$name" = "$target_name" ]; then
            printf "%s" "$var"
            return 0
        fi
    done
    printf "SOFTWARE_VERSION"
}

resolve_default_version() {
    local target_name="$1"
    for entry in "${SOFTWARE_REGISTRY[@]}"; do
        IFS='|' read -r name var default <<< "$entry"
        if [ "$name" = "$target_name" ]; then
            printf "%s" "$default"
            return 0
        fi
    done
    printf "unknown"
}

find_test_script() {
    local name="$1"
    local dir="${DESKTOP_DIR}/${name}"
    if [ -f "${dir}/${name}_test.sh" ]; then
        printf "%s" "${dir}/${name}_test.sh"
        return 0
    fi
    if [ "$name" = "oceanbase" ]; then
        if [ -f "${dir}/oceanbase_arm64_perf_test.sh" ]; then
            printf "%s" "${dir}/oceanbase_arm64_perf_test.sh"
            return 0
        fi
    fi
    if [ -f "${dir}/test.sh" ]; then
        printf "%s" "${dir}/test.sh"
        return 0
    fi
    return 1
}

apply_version_overrides() {
    local target_name="$1"
    local resolved_var="$(resolve_version_var "$target_name")"
    local resolved_default="$(resolve_default_version "$target_name")"

    for ov in "${VERSION_OVERRIDES[@]}"; do
        local ov_name="${ov%%=*}"
        local ov_ver="${ov#*=}"
        if [ "$ov_name" = "$target_name" ]; then
            export "$resolved_var"="$ov_ver"
            if [ "$target_name" = "cloudwego" ]; then
                export HERTZ_VERSION="$ov_ver"
            fi
            return 0
        fi
    done

    export "$resolved_var"="$resolved_default"
    if [ "$target_name" = "cloudwego" ]; then
        IFS='|' read -r hz_var hz_default <<< "$CLOUDWEGO_EXTRA"
        export HERTZ_VERSION="$hz_default"
    fi
    return 0
}

run_single() {
    local name="$1"
    local test_script="$(find_test_script "$name")"
    local software_dir="${DESKTOP_DIR}/${name}"

    if [ -z "$test_script" ]; then
        printf "[FAIL] %s — test script not found\n" "$name"
        return 1
    fi

    apply_version_overrides "$name"

    local var_name="$(resolve_version_var "$name")"
    local ver_val="${!var_name}"
    printf "[RUN]  %s (version: %s, var: %s)\n" "$name" "$ver_val" "$var_name"

    if [ "$DRY_RUN" -eq 1 ]; then
        printf "[DRY]  Would run: %s\n" "$test_script"
        printf "[DRY]  Env: %s=%s\n" "$var_name" "$ver_val"
        return 0
    fi

    local start_ts="$(date +%s)"
    local log_file="${software_dir}/results/install.log"
    mkdir -p "${software_dir}/results"

    local rc=0
    local saved_dir="$(pwd)"
    cd "$software_dir"
    if [ "$VERBOSE" -eq 1 ]; then
        bash "$test_script" 2>&1 | tee "$log_file" || rc=$?
    else
        bash "$test_script" > "$log_file" 2>&1 || rc=$?
    fi
    cd "$saved_dir"

    local end_ts="$(date +%s)"
    local duration=$((end_ts - start_ts))
    local duration_min=$((duration / 60))
    local duration_sec=$((duration % 60))

    if [ "$rc" -eq 0 ]; then
        printf "[OK]   %s — completed in %dm%ds\n" "$name" "$duration_min" "$duration_sec"
    else
        printf "[FAIL] %s — exit code %d, duration %dm%ds\n" "$name" "$rc" "$duration_min" "$duration_sec"
        printf "[LOG]  %s\n" "$log_file"
    fi

    return $rc
}

build_selected_list() {
    if [ "${#SELECTED[@]}" -gt 0 ]; then
        return 0
    fi

    SELECTED=("${ALL_NAMES[@]}")

    if [ "${#EXCLUDED[@]}" -gt 0 ]; then
        local new_selected=()
        for s in "${SELECTED[@]}"; do
            local skip=0
            for e in "${EXCLUDED[@]}"; do
                if [ "$s" = "$e" ]; then
                    skip=1
                    break
                fi
            done
            if [ "$skip" -eq 0 ]; then
                new_selected+=("$s")
            fi
        done
        SELECTED=("${new_selected[@]}")
    fi
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --all)
                SELECTED=("${ALL_NAMES[@]}")
                shift
                ;;
            --only)
                if [ -z "$2" ]; then
                    printf "[ERROR] --only requires a comma-separated list\n"
                    exit 1
                fi
                IFS=',' read -ra SELECTED <<< "$2"
                shift 2
                ;;
            --exclude)
                if [ -z "$2" ]; then
                    printf "[ERROR] --exclude requires a comma-separated list\n"
                    exit 1
                fi
                IFS=',' read -ra EXCLUDED <<< "$2"
                shift 2
                ;;
            --version)
                if [ -z "$2" ]; then
                    printf "[ERROR] --version requires key=value format (e.g. redis=7.2.4)\n"
                    exit 1
                fi
                VERSION_OVERRIDES+=("$2")
                shift 2
                ;;
            --dry-run)
                DRY_RUN=1
                shift
                ;;
            --verbose)
                VERBOSE=1
                shift
                ;;
            --continue)
                CONTINUE_ON_ERROR=1
                shift
                ;;
            --parallel)
                PARALLEL=1
                shift
                ;;
            --jobs)
                if [ -z "$2" ]; then
                    printf "[ERROR] --jobs requires a number\n"
                    exit 1
                fi
                JOBS="$2"
                shift 2
                ;;
            --list)
                list_software
                exit 0
                ;;
            --check)
                check_architecture
                exit $?
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                printf "[ERROR] Unknown option: %s\n" "$1"
                usage
                exit 1
                ;;
        esac
    done
}

validate_selected() {
    for s in "${SELECTED[@]}"; do
        local found=0
        for a in "${ALL_NAMES[@]}"; do
            if [ "$s" = "$a" ]; then
                found=1
                break
            fi
        done
        if [ "$found" -eq 0 ]; then
            printf "[ERROR] Unknown software: '%s'\n" "$s"
            printf "[INFO]  Available: %s\n" "$(IFS=','; echo "${ALL_NAMES[*]}")"
            exit 1
        fi
    done

    for ov in "${VERSION_OVERRIDES[@]}"; do
        local ov_name="${ov%%=*}"
        local found=0
        for a in "${ALL_NAMES[@]}"; do
            if [ "$ov_name" = "$a" ]; then
                found=1
                break
            fi
        done
        if [ "$found" -eq 0 ]; then
            printf "[ERROR] Unknown software in --version: '%s'\n" "$ov_name"
            exit 1
        fi
    done
}

run_sequential() {
    local total="${#SELECTED[@]}"
    local succeeded=0
    local failed=0
    local skipped=0
    local failed_list=()

    printf "\n========================================\n"
    printf "  ARM64 Batch Install — %d software\n" "$total"
    printf "========================================\n\n"

    local i=1
    for name in "${SELECTED[@]}"; do
        printf "[%-2d/%-2d] " "$i" "$total"
        if run_single "$name"; then
            succeeded=$((succeeded + 1))
        else
            failed=$((failed + 1))
            failed_list+=("$name")
            if [ "$CONTINUE_ON_ERROR" -eq 0 ]; then
                printf "\n[ABORT] Stopping on first failure. Use --continue to skip.\n"
                break
            fi
        fi
        i=$((i + 1))
    done

    printf "\n========================================\n"
    printf "  Summary\n"
    printf "========================================\n"
    printf "  Total:     %d\n" "$total"
    printf "  Succeeded: %d\n" "$succeeded"
    printf "  Failed:    %d\n" "$failed"
    if [ "${#failed_list[@]}" -gt 0 ]; then
        printf "  Failed list: %s\n" "$(IFS=','; echo "${failed_list[*]}")"
    fi
    printf "========================================\n\n"

    if [ "$failed" -gt 0 ]; then
        return 1
    fi
    return 0
}

run_parallel() {
    local total="${#SELECTED[@]}"
    local running=0
    local pids=()
    local names=()
    local logs=()

    printf "\n========================================\n"
    printf "  ARM64 Batch Install — %d software (parallel, jobs=%d)\n" "$total" "$JOBS"
    printf "========================================\n\n"

    for name in "${SELECTED[@]}"; do
        apply_version_overrides "$name"
        local test_script="$(find_test_script "$name")"
        if [ -z "$test_script" ]; then
            printf "[FAIL] %s — test script not found\n" "$name"
            continue
        fi

        local var_name="$(resolve_version_var "$name")"
        local ver_val="${!var_name}"
        local log_file="${DESKTOP_DIR}/${name}/results/install.log"
        mkdir -p "${DESKTOP_DIR}/${name}/results"

        printf "[RUN]  %s (version: %s)\n" "$name" "$ver_val"

        if [ "$DRY_RUN" -eq 1 ]; then
            printf "[DRY]  Would run: %s\n" "$test_script"
            continue
        fi

        ( cd "${DESKTOP_DIR}/${name}" && bash "$test_script" > "$log_file" 2>&1 ) &
        pids+=($!)
        names+=("$name")
        logs+=("$log_file")
        running=$((running + 1))

        if [ "$running" -ge "$JOBS" ]; then
            for idx in "${!pids[@]}"; do
                wait "${pids[$idx]}" 2>/dev/null
                local rc=$?
                if [ "$rc" -eq 0 ]; then
                    printf "[OK]   %s\n" "${names[$idx]}"
                else
                    printf "[FAIL] %s (exit: %d, log: %s)\n" "${names[$idx]}" "$rc" "${logs[$idx]}"
                fi
            done
            pids=()
            names=()
            logs=()
            running=0
        fi
    done

    for idx in "${!pids[@]}"; do
        wait "${pids[$idx]}" 2>/dev/null
        local rc=$?
        if [ "$rc" -eq 0 ]; then
            printf "[OK]   %s\n" "${names[$idx]}"
        else
            printf "[FAIL] %s (exit: %d, log: %s)\n" "${names[$idx]}" "$rc" "${logs[$idx]}"
        fi
    done

    printf "\n========================================\n"
    printf "  Parallel install complete.\n"
    printf "========================================\n\n"
}

main() {
    parse_args "$@"
    build_selected_list
    validate_selected

    printf "[INFO] Desktop directory: %s\n" "$DESKTOP_DIR"
    printf "[INFO] Selected: %d software\n" "${#SELECTED[@]}"
    if [ "${#SELECTED[@]}" -le 10 ]; then
        printf "[INFO] List: %s\n" "$(IFS=','; echo "${SELECTED[*]}")"
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        printf "[INFO] DRY RUN — no installs will be executed\n\n"
        for name in "${SELECTED[@]}"; do
            apply_version_overrides "$name"
            local var_name="$(resolve_version_var "$name")"
            local ver_val="${!var_name}"
            local test_script="$(find_test_script "$name")"
            printf "[DRY]  %-15s version=%-12s (%s=%s) script=%s\n" "$name" "$ver_val" "$var_name" "$ver_val" "${test_script:-NOT_FOUND}"
        done
        printf "\n[DRY] Total: %d software would be installed.\n" "${#SELECTED[@]}"
        exit 0
    fi

    if [ "$PARALLEL" -eq 1 ]; then
        run_parallel
    else
        run_sequential
    fi
}

main "$@"
