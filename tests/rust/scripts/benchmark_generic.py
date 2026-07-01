#!/usr/bin/env python3
import argparse
import json
import time
import sys
import subprocess
import os
import tempfile
import shutil
from datetime import datetime, timezone

SOFTWARE_NAME = "rust"

def compute_stats(values):
    if not values:
        return {}
    avg = sum(values) / len(values)
    sorted_v = sorted(values)
    p99 = sorted_v[int(len(sorted_v) * 0.99)] if len(sorted_v) > 1 else sorted_v[0]
    return {
        "avg": round(avg, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "p99": round(p99, 4),
        "count": len(values),
    }

def time_op(func, iterations):
    times = []
    for _ in range(iterations):
        start = time.time()
        try:
            func()
        except Exception:
            pass
        times.append(time.time() - start)
    return compute_stats(times)

def survey_container():
    py_modules = {
        "numpy": "numpy", "scipy": "scipy", "petsc4py": "petsc4py",
        "faiss": "faiss", "hnswlib": "hnswlib", "torch": "torch",
        "tensorflow": "tensorflow", "sklearn": "sklearn",
        "pandas": "pandas", "cv2": "cv2", "redis": "redis",
        "sqlite3": "sqlite3",
    }
    py_found = {}
    for name, mod in py_modules.items():
        try:
            m = __import__(mod)
            py_found[name] = getattr(m, "__version__", "unknown")
        except ImportError:
            pass

    binaries = ["rustc", "cargo", "gcc", "g++", "cmake", "make", "java", "javac",
                "python3", "pip3", "node", "npm", "go", "redis-server",
                "mysql", "nginx", "curl", "wget", "git", "docker"]
    bin_found = {}
    for b in binaries:
        try:
            r = subprocess.run(["which", b], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                vr = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=10)
                bin_found[b] = (r.stdout.strip(), (vr.stdout or vr.stderr or "").strip()[:200])
        except Exception:
            pass
    return py_found, bin_found

def collect_system_info():
    info = {
        "architecture": os.environ.get("ARCH", subprocess.run(["uname", "-m"], capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"),
        "cpu_cores": os.cpu_count() or 0,
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "kernel": subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=5).stdout.strip(),
    }
    try:
        if os.path.exists("/proc/cpuinfo"):
            lines = subprocess.run(["cat", "/proc/cpuinfo"], capture_output=True, text=True, timeout=5).stdout
            parts = [l for l in lines.split("\n") if "model name" in l.lower() or "cpu part" in l.lower() or "implementer" in l.lower()]
            info["cpu_model"] = parts[0].split(":")[-1].strip() if parts else "unknown"
        else:
            info["cpu_model"] = "unknown"
    except Exception:
        info["cpu_model"] = "unknown"
    mem_r = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
    if mem_r.returncode == 0:
        try:
            info["memory_mb"] = int(mem_r.stdout.split("\n")[1].split()[1])
        except Exception:
            pass
    return info

def benchmark_petsc(iterations):
    results_list = []
    summary = {}

    has_petsc4py = False
    try:
        from petsc4py import PETSc
        has_petsc4py = True
    except ImportError:
        pass

    has_numpy = False
    try:
        import numpy as np
        has_numpy = True
    except ImportError:
        np = None

    if has_petsc4py:
        from petsc4py import PETSc
        init_times = []
        for i in range(iterations):
            start = time.time()
            try:
                PETSc.Initialize()
            except Exception:
                pass
            init_times.append(time.time() - start)

        vec_sizes = [1000, 10000, 100000]
        for sz in vec_sizes:
            vec_times = []
            dot_times = []
            norm_times = []
            for i in range(iterations):
                try:
                    v = PETSc.Vec().create()
                    v.setSizes(sz)
                    v.setFromOptions()
                    v.setUp()
                    if has_numpy:
                        arr = np.random.random(sz).astype("float64")
                        v.setArray(arr)
                    else:
                        v.setRandom()
                    t0 = time.time()
                    dot_val = v.dot(v)
                    dot_times.append(time.time() - t0)
                    t0 = time.time()
                    nrm = v.norm()
                    norm_times.append(time.time() - t0)
                    v.destroy()
                except Exception as e:
                    dot_times.append(None)
                    norm_times.append(None)
            vec_times_clean = [t for t in dot_times if t is not None]
            norm_times_clean = [t for t in norm_times if t is not None]
            if vec_times_clean:
                summary[f"vec_dot_sz{sz}"] = compute_stats(vec_times_clean)
            if norm_times_clean:
                summary[f"vec_norm_sz{sz}"] = compute_stats(norm_times_clean)
            results_list.append({
                "operation": "vec_dot", "vec_size": sz, "iteration_data": dot_times,
            })
            results_list.append({
                "operation": "vec_norm", "vec_size": sz, "iteration_data": norm_times,
            })

        try:
            mat_sizes = [(10, 10), (100, 100), (500, 500)]
            for m, n in mat_sizes:
                mv_times = []
                for i in range(iterations):
                    try:
                        A = PETSc.Mat().create()
                        A.setSizes((m, n))
                        A.setFromOptions()
                        A.setUp()
                        if has_numpy:
                            for row in range(m):
                                cols = list(range(n))
                                vals = np.random.random(n).astype("float64")
                                A.setValues(row, cols, vals)
                            A.assemble()
                        x = PETSc.Vec().create()
                        x.setSizes(n)
                        x.setFromOptions()
                        x.setUp()
                        y = PETSc.Vec().create()
                        y.setSizes(m)
                        y.setFromOptions()
                        y.setUp()
                        if has_numpy:
                            x.setArray(np.random.random(n).astype("float64"))
                        else:
                            x.setRandom()
                        t0 = time.time()
                        A.mult(x, y)
                        mv_times.append(time.time() - t0)
                        A.destroy(); x.destroy(); y.destroy()
                    except Exception:
                        mv_times.append(None)
                mv_clean = [t for t in mv_times if t is not None]
                if mv_clean:
                    summary[f"mat_mult_{m}x{n}"] = compute_stats(mv_clean)
                results_list.append({
                    "operation": "mat_mult", "mat_size": f"{m}x{n}", "iteration_data": mv_times,
                })
            try:
                PETSc.Finalize()
            except Exception:
                pass
        except Exception:
            pass

        if init_times:
            summary["petsc_init"] = compute_stats(init_times)
        results_list.append({
            "operation": "petsc_init", "iteration_data": init_times,
        })

    elif has_numpy:
        vec_sizes = [1000, 10000, 100000, 1000000]
        for sz in vec_sizes:
            dot_times = []
            norm_times = []
            for i in range(iterations):
                a = np.random.random(sz).astype("float64")
                b = np.random.random(sz).astype("float64")
                t0 = time.time()
                c = np.dot(a, b)
                dot_times.append(time.time() - t0)
                t0 = time.time()
                nrm = np.linalg.norm(a)
                norm_times.append(time.time() - t0)
            summary[f"numpy_dot_sz{sz}"] = compute_stats(dot_times)
            summary[f"numpy_norm_sz{sz}"] = compute_stats(norm_times)
            results_list.append({
                "operation": "numpy_dot", "vec_size": sz,
                "avg_time_s": compute_stats(dot_times).get("avg", 0),
                "iterations": iterations,
            })
            results_list.append({
                "operation": "numpy_norm", "vec_size": sz,
                "avg_time_s": compute_stats(norm_times).get("avg", 0),
                "iterations": iterations,
            })

        mat_sizes = [(10, 10), (100, 100), (500, 500), (1000, 1000)]
        for m, n in mat_sizes:
            mv_times = []
            for i in range(iterations):
                A = np.random.random((m, n)).astype("float64")
                x = np.random.random(n).astype("float64")
                t0 = time.time()
                y = A @ x
                mv_times.append(time.time() - t0)
            summary[f"numpy_matmult_{m}x{n}"] = compute_stats(mv_times)
            results_list.append({
                "operation": "numpy_matmult", "mat_size": f"{m}x{n}",
                "avg_time_s": compute_stats(mv_times).get("avg", 0),
                "iterations": iterations,
            })

        solve_times = []
        for i in range(iterations):
            A = np.random.random((100, 100)).astype("float64")
            A = A @ A.T + np.eye(100) * 0.1
            b = np.random.random(100).astype("float64")
            t0 = time.time()
            x = np.linalg.solve(A, b)
            solve_times.append(time.time() - t0)
        summary["numpy_solve_100x100"] = compute_stats(solve_times)
        results_list.append({
            "operation": "numpy_solve", "mat_size": "100x100",
            "avg_time_s": compute_stats(solve_times).get("avg", 0),
            "iterations": iterations,
        })
    else:
        cpu_times = []
        for i in range(iterations):
            n = 1000000
            total = 0.0
            t0 = time.time()
            for j in range(n):
                total += j * 0.0001
            cpu_times.append(time.time() - t0)
        summary["cpu_float_add_1M"] = compute_stats(cpu_times)
        results_list.append({
            "operation": "cpu_float_add", "count": 1000000,
            "avg_time_s": compute_stats(cpu_times).get("avg", 0),
            "iterations": iterations,
        })

    return summary, results_list

def benchmark_rust(iterations):
    results_list = []
    summary = {}
    tmpdir = tempfile.mkdtemp(prefix="rustbench_")

    rustc_ver = subprocess.run(["rustc", "--version"], capture_output=True, text=True, timeout=5)
    cargo_ver = subprocess.run(["cargo", "--version"], capture_output=True, text=True, timeout=5)

    summary["rustc_version"] = rustc_ver.stdout.strip()[:100] if rustc_ver.returncode == 0 else "not_found"
    summary["cargo_version"] = cargo_ver.stdout.strip()[:100] if cargo_ver.returncode == 0 else "not_found"

    hello_code = """
fn main() {
    let mut sum: f64 = 0.0;
    for i in 0..1000000 {
        sum += i as f64 * 0.0001;
    }
    println!("sum = {}", sum);
}
"""
    src_path = os.path.join(tmpdir, "hello.rs")
    with open(src_path, "w") as f:
        f.write(hello_code)

    compile_times = []
    for i in range(iterations):
        t0 = time.time()
        r = subprocess.run(["rustc", src_path, "-o", os.path.join(tmpdir, f"hello_{i}")],
                           capture_output=True, text=True, timeout=60)
        compile_times.append(time.time() - t0)
    compile_stats = compute_stats(compile_times)
    summary["rustc_compile_hello"] = compile_stats
    results_list.append({
        "operation": "rustc_compile_hello", "iterations": iterations,
        "avg_time_s": compile_stats.get("avg", 0),
        "compile_success": r.returncode == 0,
    })

    run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"hello_{i}")
        if os.path.exists(exe):
            t0 = time.time()
            subprocess.run([exe], capture_output=True, timeout=30)
            run_times.append(time.time() - t0)
    if run_times:
        run_stats = compute_stats(run_times)
        summary["rust_hello_run"] = run_stats
        results_list.append({
            "operation": "rust_hello_run", "iterations": len(run_times),
            "avg_time_s": run_stats.get("avg", 0),
        })

    matmul_code = """
fn main() {
    let n: usize = 500;
    let mut a: Vec<Vec<f64>> = vec![vec![0.0; n]; n];
    let mut b: Vec<Vec<f64>> = vec![vec![0.0; n]; n];
    let mut c: Vec<Vec<f64>> = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in 0..n {
            a[i][j] = (i * j) as f64 * 0.001;
            b[i][j] = (i + j) as f64 * 0.001;
        }
    }
    let start = std::time::Instant::now();
    for i in 0..n {
        for k in 0..n {
            let aik = a[i][k];
            for j in 0..n {
                c[i][j] += aik * b[k][j];
            }
        }
    }
    let elapsed = start.elapsed().as_secs_f64();
    println!("matmul {}x{} time: {:.6}s", n, n, elapsed);
}
"""
    src_path2 = os.path.join(tmpdir, "matmul.rs")
    with open(src_path2, "w") as f:
        f.write(matmul_code)

    matmul_compile_times = []
    for i in range(iterations):
        t0 = time.time()
        subprocess.run(["rustc", src_path2, "-o", os.path.join(tmpdir, f"matmul_{i}")],
                       capture_output=True, text=True, timeout=120)
        matmul_compile_times.append(time.time() - t0)
    matmul_compile_stats = compute_stats(matmul_compile_times)
    summary["rustc_compile_matmul"] = matmul_compile_stats
    results_list.append({
        "operation": "rustc_compile_matmul", "iterations": iterations,
        "avg_time_s": matmul_compile_stats.get("avg", 0),
    })

    matmul_run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"matmul_{i}")
        if os.path.exists(exe):
            t0 = time.time()
            r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
            matmul_run_times.append(time.time() - t0)
    if matmul_run_times:
        matmul_run_stats = compute_stats(matmul_run_times)
        summary["rust_matmul_500x500"] = matmul_run_stats
        results_list.append({
            "operation": "rust_matmul_500x500", "iterations": len(matmul_run_times),
            "avg_time_s": matmul_run_stats.get("avg", 0),
        })

    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass

    return summary, results_list

def benchmark_faiss(iterations):
    import numpy as np
    import faiss
    results_list = []
    summary = {}

    n = 100000
    d = 128
    k = 10
    np.random.seed(42)
    xb = np.random.random((n, d)).astype("float32")
    nq = min(1000, n // 10)
    xq = np.random.random((nq, d)).astype("float32")

    gt_index = faiss.IndexFlatL2(d)
    gt_index.add(xb)
    gt_D, gt_I = gt_index.search(xq, k)

    configs = {
        "FlatL2": lambda d: faiss.IndexFlatL2(d),
        "HNSWFlat": lambda d: faiss.IndexHNSWFlat(d, 32),
    }

    for name, ctor in configs.items():
        search_times = []
        build_times = []
        for i in range(iterations):
            idx = ctor(d)
            t0 = time.time()
            idx.add(xb)
            build_times.append(time.time() - t0)
            t0 = time.time()
            D, I = idx.search(xq, k)
            search_times.append(time.time() - t0)
        build_stats = compute_stats(build_times)
        search_stats = compute_stats(search_times)
        qps = nq / search_stats.get("avg", 1) if search_stats.get("avg", 0) > 0 else 0
        summary[name] = {
            "build_time_s": build_stats,
            "search_time_s": search_stats,
            "qps": round(qps, 2),
            "num_vectors": n,
            "num_queries": nq,
        }
        results_list.append({
            "operation": f"faiss_{name}", "iterations": iterations,
            "avg_build_s": build_stats.get("avg", 0),
            "avg_search_s": search_stats.get("avg", 0),
            "qps": round(qps, 2),
        })

    return summary, results_list

def benchmark_numpy(iterations):
    import numpy as np
    results_list = []
    summary = {}

    ops = [
        ("dot_1M", lambda: np.dot(np.random.random(1000000), np.random.random(1000000))),
        ("matmult_500x500", lambda: np.random.random((500, 500)) @ np.random.random(500)),
        ("matmult_1Kx1K", lambda: np.random.random((1000, 1000)) @ np.random.random(1000)),
        ("solve_500x500", lambda: np.linalg.solve(
            np.random.random((500, 500)) @ np.random.random((500, 500)).T + np.eye(500),
            np.random.random(500))),
        ("fft_1M", lambda: np.fft.fft(np.random.random(1000000))),
        ("sort_1M", lambda: np.sort(np.random.random(1000000))),
    ]
    for op_name, op_func in ops:
        times = []
        for i in range(iterations):
            t0 = time.time()
            op_func()
            times.append(time.time() - t0)
        stats = compute_stats(times)
        summary[op_name] = stats
        results_list.append({
            "operation": op_name, "iterations": iterations,
            "avg_time_s": stats.get("avg", 0),
        })

    return summary, results_list

def benchmark_redis(iterations):
    results_list = []
    summary = {}
    try:
        import redis as redis_mod
        r = redis_mod.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        set_times = []
        get_times = []
        for i in range(iterations):
            t0 = time.time()
            r.set(f"bench_key_{i}", f"bench_val_{i}")
            set_times.append(time.time() - t0)
            t0 = time.time()
            r.get(f"bench_key_{i}")
            get_times.append(time.time() - t0)
        summary["redis_set"] = compute_stats(set_times)
        summary["redis_get"] = compute_stats(get_times)
        results_list.append({
            "operation": "redis_set", "iterations": iterations,
            "avg_time_s": compute_stats(set_times).get("avg", 0),
        })
        results_list.append({
            "operation": "redis_get", "iterations": iterations,
            "avg_time_s": compute_stats(get_times).get("avg", 0),
        })
    except Exception as e:
        summary["redis_error"] = str(e)[:200]
        try:
            subprocess.run(["redis-server", "--version"], capture_output=True, text=True, timeout=5)
            summary["redis_server_available"] = "yes (not running)"
        except Exception:
            summary["redis_server_available"] = "no"
    return summary, results_list

def benchmark_generic_compute(iterations):
    results_list = []
    summary = {}
    try:
        import numpy as np
        has_np = True
    except ImportError:
        np = None
        has_np = False

    if has_np:
        dot_times = []
        for i in range(iterations):
            a = np.random.random(100000).astype("float64")
            b = np.random.random(100000).astype("float64")
            t0 = time.time()
            c = np.dot(a, b)
            dot_times.append(time.time() - t0)
        summary["numpy_dot_100K"] = compute_stats(dot_times)
        results_list.append({
            "operation": "numpy_dot_100K", "iterations": iterations,
            "avg_time_s": compute_stats(dot_times).get("avg", 0),
        })

        mat_times = []
        for i in range(iterations):
            A = np.random.random((100, 100)).astype("float64")
            x = np.random.random(100).astype("float64")
            t0 = time.time()
            y = A @ x
            mat_times.append(time.time() - t0)
        summary["numpy_matmult_100x100"] = compute_stats(mat_times)
        results_list.append({
            "operation": "numpy_matmult_100x100", "iterations": iterations,
            "avg_time_s": compute_stats(mat_times).get("avg", 0),
        })

        fft_times = []
        for i in range(iterations):
            t0 = time.time()
            np.fft.fft(np.random.random(10000))
            fft_times.append(time.time() - t0)
        summary["numpy_fft_10K"] = compute_stats(fft_times)
        results_list.append({
            "operation": "numpy_fft_10K", "iterations": iterations,
            "avg_time_s": compute_stats(fft_times).get("avg", 0),
        })
    else:
        cpu_times = []
        for i in range(iterations):
            n = 1000000
            total = 0.0
            t0 = time.time()
            for j in range(n):
                total += j * 0.0001
            cpu_times.append(time.time() - t0)
        summary["cpu_float_add_1M"] = compute_stats(cpu_times)
        results_list.append({
            "operation": "cpu_float_add_1M", "iterations": iterations,
            "avg_time_s": compute_stats(cpu_times).get("avg", 0),
        })

        sort_times = []
        for i in range(iterations):
            t0 = time.time()
            sorted(range(100000))
            sort_times.append(time.time() - t0)
        summary["python_sort_100K"] = compute_stats(sort_times)
        results_list.append({
            "operation": "python_sort_100K", "iterations": iterations,
            "avg_time_s": compute_stats(sort_times).get("avg", 0),
        })

    return summary, results_list

SOFTWARE_BENCHMARKS = {
    "petsc": benchmark_petsc,
    "rust": benchmark_rust,
    "faiss": benchmark_faiss,
    "numpy": benchmark_numpy,
    "redis": benchmark_redis,
}

def run_benchmark(output_file, version, iterations):
    py_found, bin_found = survey_container()
    sys_info = collect_system_info()

    sw_lower = SOFTWARE_NAME.lower()
    bench_func = SOFTWARE_BENCHMARKS.get(sw_lower, benchmark_generic_compute)

    print(f"[BENCHMARK] Running {sw_lower} benchmark (func={bench_func.__name__}, iterations={iterations})")
    sw_summary, sw_results = bench_func(iterations)

    if sw_lower not in SOFTWARE_BENCHMARKS and py_found:
        for dep_name, dep_version in py_found.items():
            dep_func = SOFTWARE_BENCHMARKS.get(dep_name)
            if dep_func:
                try:
                    dep_summary, dep_results = dep_func(iterations)
                    for k, v in dep_summary.items():
                        sw_summary[f"{dep_name}_{k}"] = v
                    sw_results.extend(dep_results)
                except Exception as e:
                    sw_summary[f"{dep_name}_error"] = str(e)[:200]

    perf_metrics = {}
    for op_name, stats in sw_summary.items():
        if isinstance(stats, dict) and "avg" in stats:
            perf_metrics[op_name] = {
                "unit": "seconds",
                "avg_s": stats.get("avg", 0),
                "min_s": stats.get("min", 0),
                "max_s": stats.get("max", 0),
                "p99_s": stats.get("p99", 0),
            }

    output = {
        "benchmark": "container_performance",
        "description": f"{SOFTWARE_NAME} performance benchmark - real computational tests in container environment",
        "reference": "https://github.com/erikbern/ann-benchmarks methodology",
        "software": SOFTWARE_NAME,
        "version": version,
        "architecture": sys_info.get("architecture", "unknown"),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": perf_metrics,
        "system_info": sys_info,
        "parameters": {
            "iterations": iterations,
            "software_specific": sw_lower in SOFTWARE_BENCHMARKS,
        },
        "container_environment": {
            "python_packages": py_found,
            "binaries": dict((k, v[1][:80]) for k, v in bin_found.items()),
        },
        "results_summary": sw_summary,
        "results": sw_results,
    }

    print(f"[BENCHMARK] {SOFTWARE_NAME}: {len(sw_results)} test results, {len(sw_summary)} summary entries")

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[BENCHMARK] Output written to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    run_benchmark(args.output, args.version, args.iterations)
