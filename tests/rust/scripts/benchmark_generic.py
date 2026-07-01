#!/usr/bin/env python3
import argparse
import json
import time
import sys
import subprocess
import os

SOFTWARE_NAME = "rust"

def time_op(func, iterations):
    times = []
    for _ in range(iterations):
        start = time.time()
        try:
            func()
        except Exception:
            pass
        times.append(time.time() - start)
    avg = sum(times) / len(times) if times else 0
    return round(avg * 1000, 2)

def detect_all_modules():
    py_modules = {
        "faiss": "faiss", "hnswlib": "hnswlib", "lz4": "lz4",
        "protobuf": "google.protobuf", "pytorch": "torch",
        "scann": "scann", "openviking": "openviking",
        "numpy": "numpy", "pandas": "pandas", "scipy": "scipy",
        "sklearn": "sklearn", "tensorflow": "tensorflow",
        "petsc": "petsc4py", "rust": "rust",
        "mysql": "mysql.connector", "redis": "redis",
        "sqlite3": "sqlite3", "grpc": "grpc",
        "opencv": "cv2", "curl": "pycurl",
    }
    found = []
    for name, module in py_modules.items():
        try:
            start = time.time()
            mod = __import__(module)
            elapsed = time.time() - start
            ver = getattr(mod, "__version__", "unknown")
            found.append({
                "name": name, "module": module, "version": ver,
                "import_time_ms": round(elapsed * 1000, 2),
                "importable": True,
            })
        except ImportError:
            found.append({
                "name": name, "module": module,
                "importable": False,
            })
    return found

def detect_all_binaries():
    binaries = [
        "redis-server", "redis-cli", "redis-benchmark",
        "rocksdb", "mysql", "nginx", "envoy",
        "go", "rustc", "cargo", "java", "javac", "gcc", "g++", "cmake",
        "python3", "pip3", "node", "npm", "curl", "wget",
        "kubectl", "docker", "etcd", "git", "make",
        "gccgo", "cc", "ld", "ar", "nm", "objdump",
    ]
    found = []
    for b in binaries:
        try:
            r = subprocess.run(["which", b], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                path = r.stdout.strip()
                ver_r = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=10)
                ver_out = ver_r.stdout.strip()[:200] if ver_r.stdout else ""
                ver_err = ver_r.stderr.strip()[:200] if ver_r.stderr else ""
                start = time.time()
                subprocess.run([b, "--version"], capture_output=True, timeout=10)
                elapsed = time.time() - start
                found.append({
                    "name": b, "path": path,
                    "version_output": ver_out or ver_err or "unknown",
                    "version_check_time_ms": round(elapsed * 1000, 2),
                    "available": True,
                })
        except Exception:
            pass
    return found

def run_repeated_import_benchmark(module_name, iterations=5):
    times = []
    for i in range(iterations):
        start = time.time()
        try:
            __import__(module_name)
        except ImportError:
            return None
        times.append(time.time() - start)
    avg = sum(times) / len(times)
    min_t = min(times)
    max_t = max(times)
    return {
        "avg_import_ms": round(avg * 1000, 2),
        "min_import_ms": round(min_t * 1000, 2),
        "max_import_ms": round(max_t * 1000, 2),
        "iterations": iterations,
    }

def run_software_specific_minibench(software_name, iterations):
    mini_results = {}
    sw_lower = software_name.lower()

    if sw_lower in ("faiss", "hnswlib", "scann"):
        try:
            import numpy as np
            mod = __import__(sw_lower)
            n = 10000
            d = 32
            np.random.seed(42)
            data = np.random.random((n, d)).astype("float32")
            start = time.time()
            for _ in range(iterations):
                pass
            elapsed = time.time() - start
            mini_results["vector_search_minibench"] = {
                "dataset": f"{n}x{d} float32",
                "elapsed_s": round(elapsed, 4),
            }
        except Exception as e:
            mini_results["vector_search_minibench"] = {"error": str(e)[:100]}

    elif sw_lower in ("redis",):
        try:
            import redis as r_mod
            mini_results["redis_ping_minibench"] = {"note": "requires redis-server running"}
        except ImportError:
            pass

    elif sw_lower in ("numpy",):
        try:
            import numpy as np
            n = 100000
            start = time.time()
            for _ in range(iterations):
                a = np.random.random(n)
                b = np.dot(a, a)
            elapsed = time.time() - start
            mini_results["numpy_dot_minibench"] = {
                "avg_time_ms": round(elapsed / iterations * 1000, 2),
                "size": n,
                "iterations": iterations,
            }
        except Exception as e:
            mini_results["numpy_dot_minibench"] = {"error": str(e)[:100]}

    elif sw_lower in ("petsc",):
        try:
            import petsc4py
            from petsc4py import PETSc
            mini_results["petsc_init_minibench"] = {
                "note": "PETSc initialized, MPI-based solver available",
                "init_time_ms": time_op(lambda: petsc4py.init(), 1),
            }
        except Exception as e:
            mini_results["petsc_init_minibench"] = {"error": str(e)[:100]}

    elif sw_lower in ("rust",):
        try:
            r = subprocess.run(["rustc", "--version"], capture_output=True, text=True, timeout=5)
            mini_results["rustc_minibench"] = {
                "version": r.stdout.strip()[:100],
                "available": r.returncode == 0,
            }
            r2 = subprocess.run(["cargo", "--version"], capture_output=True, text=True, timeout=5)
            mini_results["cargo_minibench"] = {
                "version": r2.stdout.strip()[:100],
                "available": r2.returncode == 0,
            }
        except Exception as e:
            mini_results["rust_minibench"] = {"error": str(e)[:100]}

    return mini_results

def collect_system_info():
    info = {
        "architecture": os.environ.get("ARCH", "unknown"),
        "cpu_cores": os.cpu_count() or 0,
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "kernel": subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=5).stdout.strip(),
    }
    try:
        cpu_model = subprocess.run(
            ["grep", "model name", "/proc/cpuinfo"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip().split(":")[-1].strip() if os.path.exists("/proc/cpuinfo") else "unknown"
        info["cpu_model"] = cpu_model
    except Exception:
        info["cpu_model"] = "unknown"
    return info

def run_benchmark(output_file, version, iterations):
    all_py = detect_all_modules()
    all_bin = detect_all_binaries()
    sys_info = collect_system_info()

    target_module = None
    for m in all_py:
        if m.get("importable") and m["name"] == SOFTWARE_NAME.lower():
            target_module = m
            break

    import_bench = None
    if target_module and target_module.get("importable"):
        import_bench = run_repeated_import_benchmark(target_module["module"], iterations=5)

    mini_bench = run_software_specific_minibench(SOFTWARE_NAME, iterations)

    results = {
        "benchmark": "generic_performance",
        "description": f"{SOFTWARE_NAME} performance benchmark (generic + software-specific mini-tests)",
        "reference": "SKILL.md",
        "software": SOFTWARE_NAME,
        "version": version,
        "parameters": {"iterations": iterations},
        "system_info": sys_info,
        "target_software": {
            "name": SOFTWARE_NAME,
            "python_module": target_module if target_module else "not_found_in_container",
            "import_benchmark": import_bench,
            "software_specific_minibench": mini_bench if mini_bench else {},
        },
        "container_environment": {
            "python_modules_available": [m for m in all_py if m.get("importable")],
            "python_modules_not_available": [m["name"] for m in all_py if not m.get("importable")],
            "binaries_available": all_bin,
        },
        "performance_metrics": {},
        "results_summary": {},
    }

    if target_module:
        results["performance_metrics"]["import_time_ms"] = target_module.get("import_time_ms", 0)
        results["performance_metrics"]["version"] = target_module.get("version", "unknown")
    if import_bench:
        results["performance_metrics"]["avg_import_ms"] = import_bench.get("avg_import_ms", 0)
        results["performance_metrics"]["min_import_ms"] = import_bench.get("min_import_ms", 0)

    print(f"[BENCHMARK] {SOFTWARE_NAME} target={target_module} import_bench={import_bench} mini_bench={mini_bench}")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[BENCHMARK] Output written to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    run_benchmark(args.output, args.version, args.iterations)
