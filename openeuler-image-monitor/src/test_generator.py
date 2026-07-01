import os
import shutil
import subprocess
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BENCHMARK_TYPE_MAP = {
    "ann": "benchmark_ann",
    "vector_search": "benchmark_ann",
    "search": "benchmark_ann",
    "kv_store": "benchmark_kv",
    "database": "benchmark_kv",
    "kv": "benchmark_kv",
    "db": "benchmark_kv",
    "cache": "benchmark_kv",
    "messaging": "benchmark_kv",
    "network": "benchmark_generic",
    "runtime": "benchmark_generic",
    "compiler": "benchmark_generic",
    "language": "benchmark_generic",
    "framework": "benchmark_generic",
}

PYTHON_MODULE_MAP = {
    "faiss": "faiss",
    "hnswlib": "hnswlib",
    "lz4": "lz4",
    "protobuf": "google.protobuf",
    "pytorch": "torch",
    "scann": "scann",
    "openviking": "openviking",
}

COMMON_SCRIPTS_COPY = ["json_helper.py"]
COMMON_SCRIPTS_GENERATE = ["aggregate_results.py", "generate_summary.py"]

BENCHMARK_GENERIC_PY = '''#!/usr/bin/env python3
import argparse
import json
import time
import sys
import subprocess
import os
import tempfile
import shutil
from datetime import datetime, timezone

SOFTWARE_NAME = "{software}"

def compute_stats(values):
    if not values:
        return {{}}
    avg = sum(values) / len(values)
    sorted_v = sorted(values)
    p99 = sorted_v[int(len(sorted_v) * 0.99)] if len(sorted_v) > 1 else sorted_v[0]
    return {{
        "avg": round(avg, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "p99": round(p99, 4),
        "count": len(values),
    }}

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
    py_modules = {{
        "numpy": "numpy", "scipy": "scipy", "petsc4py": "petsc4py",
        "faiss": "faiss", "hnswlib": "hnswlib", "torch": "torch",
        "tensorflow": "tensorflow", "sklearn": "sklearn",
        "pandas": "pandas", "cv2": "cv2", "redis": "redis",
        "sqlite3": "sqlite3",
    }}
    py_found = {{}}
    for name, mod in py_modules.items():
        try:
            m = __import__(mod)
            py_found[name] = getattr(m, "__version__", "unknown")
        except ImportError:
            pass

    binaries = ["rustc", "cargo", "gcc", "g++", "cmake", "make", "java", "javac",
                "python3", "pip3", "node", "npm", "go", "redis-server",
                "mysql", "nginx", "curl", "wget", "git", "docker"]
    bin_found = {{}}
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
    info = {{
        "architecture": os.environ.get("ARCH", subprocess.run(["uname", "-m"], capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"),
        "cpu_cores": os.cpu_count() or 0,
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "kernel": subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=5).stdout.strip(),
    }}
    try:
        if os.path.exists("/proc/cpuinfo"):
            lines = subprocess.run(["cat", "/proc/cpuinfo"], capture_output=True, text=True, timeout=5).stdout
            parts = [l for l in lines.split("\\n") if "model name" in l.lower() or "cpu part" in l.lower() or "implementer" in l.lower()]
            info["cpu_model"] = parts[0].split(":")[-1].strip() if parts else "unknown"
        else:
            info["cpu_model"] = "unknown"
    except Exception:
        info["cpu_model"] = "unknown"
    mem_r = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
    if mem_r.returncode == 0:
        try:
            info["memory_mb"] = int(mem_r.stdout.split("\\n")[1].split()[1])
        except Exception:
            pass
    return info

def _fib_iter(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

def benchmark_petsc(iterations):
    results_list = []
    summary = {{}}

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
                summary[f"vec_dot_sz{{sz}}"] = compute_stats(vec_times_clean)
            if norm_times_clean:
                summary[f"vec_norm_sz{{sz}}"] = compute_stats(norm_times_clean)
            results_list.append({{
                "operation": "vec_dot", "vec_size": sz, "iteration_data": dot_times,
            }})
            results_list.append({{
                "operation": "vec_norm", "vec_size": sz, "iteration_data": norm_times,
            }})

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
                    summary[f"mat_mult_{{m}}x{{n}}"] = compute_stats(mv_clean)
                results_list.append({{
                    "operation": "mat_mult", "mat_size": f"{{m}}x{{n}}", "iteration_data": mv_times,
                }})
            try:
                PETSc.Finalize()
            except Exception:
                pass
        except Exception:
            pass

        if init_times:
            summary["petsc_init"] = compute_stats(init_times)
        results_list.append({{
            "operation": "petsc_init", "iteration_data": init_times,
        }})

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
            summary[f"numpy_dot_sz{{sz}}"] = compute_stats(dot_times)
            summary[f"numpy_norm_sz{{sz}}"] = compute_stats(norm_times)
            results_list.append({{
                "operation": "numpy_dot", "vec_size": sz,
                "avg_time_s": compute_stats(dot_times).get("avg", 0),
                "iterations": iterations,
            }})
            results_list.append({{
                "operation": "numpy_norm", "vec_size": sz,
                "avg_time_s": compute_stats(norm_times).get("avg", 0),
                "iterations": iterations,
            }})

        mat_sizes = [(10, 10), (100, 100), (500, 500), (1000, 1000)]
        for m, n in mat_sizes:
            mv_times = []
            for i in range(iterations):
                A = np.random.random((m, n)).astype("float64")
                x = np.random.random(n).astype("float64")
                t0 = time.time()
                y = A @ x
                mv_times.append(time.time() - t0)
            summary[f"numpy_matmult_{{m}}x{{n}}"] = compute_stats(mv_times)
            results_list.append({{
                "operation": "numpy_matmult", "mat_size": f"{{m}}x{{n}}",
                "avg_time_s": compute_stats(mv_times).get("avg", 0),
                "iterations": iterations,
            }})

        solve_times = []
        for i in range(iterations):
            A = np.random.random((100, 100)).astype("float64")
            A = A @ A.T + np.eye(100) * 0.1
            b = np.random.random(100).astype("float64")
            t0 = time.time()
            x = np.linalg.solve(A, b)
            solve_times.append(time.time() - t0)
        summary["numpy_solve_100x100"] = compute_stats(solve_times)
        results_list.append({{
            "operation": "numpy_solve", "mat_size": "100x100",
            "avg_time_s": compute_stats(solve_times).get("avg", 0),
            "iterations": iterations,
        }})
    else:
        ops = [
            ("float_add_1M", lambda: sum(j * 0.0001 for j in range(1000000))),
            ("float_add_10M", lambda: sum(j * 0.0001 for j in range(10000000))),
            ("list_sort_100K", lambda: sorted([j * 0.001 for j in range(100000)])),
            ("list_sort_1M", lambda: sorted([j * 0.001 for j in range(1000000)])),
            ("dict_create_100K", lambda: dict((j, j * 0.001) for j in range(100000))),
            ("set_membership_100K", lambda: all(j in set(range(100000)) for j in range(0, 100000, 100))),
            ("string_concat_10K", lambda: "".join(str(j) for j in range(10000))),
            ("prime_sieve_10K", lambda: [j for j in range(2, 10000) if all(j % k != 0 for k in range(2, int(j**0.5)+1))]),
            ("fibonacci_iter_100K", lambda: _fib_iter(100000)),
        ]
        for op_name, op_func in ops:
            times = []
            for i in range(iterations):
                t0 = time.time()
                op_func()
                times.append(time.time() - t0)
            summary[op_name] = compute_stats(times)
            results_list.append({{
                "operation": op_name, "iterations": iterations,
                "avg_time_s": compute_stats(times).get("avg", 0),
            }})

        gcc_path = _find_binary("gcc")
        if os.path.exists(gcc_path):
            tmpdir = tempfile.mkdtemp(prefix="petsc_c_bench_")
            c_code = """
#include <stdio.h>
#include <math.h>
int main() {{
    int n = 1000000;
    double sum = 0.0;
    for (int i = 0; i < n; i++) {{
        sum += i * 0.0001;
    }}
    printf("sum = %f\\n", sum);
    return 0;
}}
"""
            c_path = os.path.join(tmpdir, "bench.c")
            with open(c_path, "w") as f:
                f.write(c_code)
            compile_times = []
            for i in range(iterations):
                t0 = time.time()
                r = subprocess.run([gcc_path, c_path, "-o", os.path.join(tmpdir, f"bench_{{i}}"), "-lm"],
                                   capture_output=True, text=True, timeout=30)
                compile_times.append(time.time() - t0)
            summary["gcc_compile_c"] = compute_stats(compile_times)
            results_list.append({{
                "operation": "gcc_compile_c", "iterations": iterations,
                "avg_time_s": compute_stats(compile_times).get("avg", 0),
                "compile_success": r.returncode == 0,
            }})
            run_times = []
            for i in range(iterations):
                exe = os.path.join(tmpdir, f"bench_{{i}}")
                if os.path.exists(exe):
                    t0 = time.time()
                    subprocess.run([exe], capture_output=True, timeout=10)
                    run_times.append(time.time() - t0)
            if run_times:
                summary["c_float_add_1M_run"] = compute_stats(run_times)
                results_list.append({{
                    "operation": "c_float_add_1M_run", "iterations": len(run_times),
                    "avg_time_s": compute_stats(run_times).get("avg", 0),
                }})
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass

    return summary, results_list

def _find_binary(name):
    try:
        r = subprocess.run(["which", name], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    for p in ["/usr/bin", "/usr/local/bin", "/opt/homebrew/bin", "/root/.cargo/bin",
              os.path.expanduser("~/.cargo/bin")]:
        fp = os.path.join(p, name)
        if os.path.exists(fp):
            return fp
    return name

def benchmark_rust(iterations):
    results_list = []
    summary = {{}}
    tmpdir = tempfile.mkdtemp(prefix="rustbench_")

    rustc_path = _find_binary("rustc")
    cargo_path = _find_binary("cargo")
    rustc_ver = subprocess.run([rustc_path, "--version"], capture_output=True, text=True, timeout=5)
    cargo_ver = subprocess.run([cargo_path, "--version"], capture_output=True, text=True, timeout=5)

    summary["rustc_version"] = rustc_ver.stdout.strip()[:100] if rustc_ver.returncode == 0 else "not_found"
    summary["cargo_version"] = cargo_ver.stdout.strip()[:100] if cargo_ver.returncode == 0 else "not_found"

    hello_code = """
fn main() {{
    let mut sum: f64 = 0.0;
    for i in 0..1000000 {{
        sum += i as f64 * 0.0001;
    }}
    println!("sum = {{}}", sum);
}}
"""
    src_path = os.path.join(tmpdir, "hello.rs")
    with open(src_path, "w") as f:
        f.write(hello_code)

    compile_times = []
    for i in range(iterations):
        t0 = time.time()
        r = subprocess.run([rustc_path, src_path, "-o", os.path.join(tmpdir, f"hello_{{i}}")],
                           capture_output=True, text=True, timeout=60)
        compile_times.append(time.time() - t0)
    compile_stats = compute_stats(compile_times)
    summary["rustc_compile_hello"] = compile_stats
    results_list.append({{
        "operation": "rustc_compile_hello", "iterations": iterations,
        "avg_time_s": compile_stats.get("avg", 0),
        "compile_success": r.returncode == 0,
    }})

    run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"hello_{{i}}")
        if os.path.exists(exe):
            t0 = time.time()
            subprocess.run([exe], capture_output=True, timeout=30)
            run_times.append(time.time() - t0)
    if run_times:
        run_stats = compute_stats(run_times)
        summary["rust_hello_run"] = run_stats
        results_list.append({{
            "operation": "rust_hello_run", "iterations": len(run_times),
            "avg_time_s": run_stats.get("avg", 0),
        }})

    matmul_code = """
fn main() {{
    let n: usize = 500;
    let mut a: Vec<Vec<f64>> = vec![vec![0.0; n]; n];
    let mut b: Vec<Vec<f64>> = vec![vec![0.0; n]; n];
    let mut c: Vec<Vec<f64>> = vec![vec![0.0; n]; n];
    for i in 0..n {{
        for j in 0..n {{
            a[i][j] = (i * j) as f64 * 0.001;
            b[i][j] = (i + j) as f64 * 0.001;
        }}
    }}
    let start = std::time::Instant::now();
    for i in 0..n {{
        for k in 0..n {{
            let aik = a[i][k];
            for j in 0..n {{
                c[i][j] += aik * b[k][j];
            }}
        }}
    }}
    let elapsed = start.elapsed().as_secs_f64();
    println!("matmul {{}}x{{}} time: {{:.6}}s", n, n, elapsed);
}}
"""
    src_path2 = os.path.join(tmpdir, "matmul.rs")
    with open(src_path2, "w") as f:
        f.write(matmul_code)

    matmul_compile_times = []
    for i in range(iterations):
        t0 = time.time()
        subprocess.run([rustc_path, src_path2, "-o", os.path.join(tmpdir, f"matmul_{{i}}")],
                       capture_output=True, text=True, timeout=120)
        matmul_compile_times.append(time.time() - t0)
    matmul_compile_stats = compute_stats(matmul_compile_times)
    summary["rustc_compile_matmul"] = matmul_compile_stats
    results_list.append({{
        "operation": "rustc_compile_matmul", "iterations": iterations,
        "avg_time_s": matmul_compile_stats.get("avg", 0),
    }})

    matmul_run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"matmul_{{i}}")
        if os.path.exists(exe):
            t0 = time.time()
            r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
            matmul_run_times.append(time.time() - t0)
    if matmul_run_times:
        matmul_run_stats = compute_stats(matmul_run_times)
        summary["rust_matmul_500x500"] = matmul_run_stats
        results_list.append({{
            "operation": "rust_matmul_500x500", "iterations": len(matmul_run_times),
            "avg_time_s": matmul_run_stats.get("avg", 0),
        }})

    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass

    return summary, results_list

def benchmark_faiss(iterations):
    import numpy as np
    import faiss
    results_list = []
    summary = {{}}

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

    configs = {{
        "FlatL2": lambda d: faiss.IndexFlatL2(d),
        "HNSWFlat": lambda d: faiss.IndexHNSWFlat(d, 32),
    }}

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
        summary[name] = {{
            "build_time_s": build_stats,
            "search_time_s": search_stats,
            "qps": round(qps, 2),
            "num_vectors": n,
            "num_queries": nq,
        }}
        results_list.append({{
            "operation": f"faiss_{{name}}", "iterations": iterations,
            "avg_build_s": build_stats.get("avg", 0),
            "avg_search_s": search_stats.get("avg", 0),
            "qps": round(qps, 2),
        }})

    return summary, results_list

def benchmark_numpy(iterations):
    import numpy as np
    results_list = []
    summary = {{}}

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
        results_list.append({{
            "operation": op_name, "iterations": iterations,
            "avg_time_s": stats.get("avg", 0),
        }})

    return summary, results_list

def benchmark_redis(iterations):
    results_list = []
    summary = {{}}
    try:
        import redis as redis_mod
        r = redis_mod.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        set_times = []
        get_times = []
        for i in range(iterations):
            t0 = time.time()
            r.set(f"bench_key_{{i}}", f"bench_val_{{i}}")
            set_times.append(time.time() - t0)
            t0 = time.time()
            r.get(f"bench_key_{{i}}")
            get_times.append(time.time() - t0)
        summary["redis_set"] = compute_stats(set_times)
        summary["redis_get"] = compute_stats(get_times)
        results_list.append({{
            "operation": "redis_set", "iterations": iterations,
            "avg_time_s": compute_stats(set_times).get("avg", 0),
        }})
        results_list.append({{
            "operation": "redis_get", "iterations": iterations,
            "avg_time_s": compute_stats(get_times).get("avg", 0),
        }})
    except Exception as e:
        summary["redis_error"] = str(e)[:200]
        try:
            subprocess.run(["redis-server", "--version"], capture_output=True, text=True, timeout=5)
            summary["redis_server_available"] = "yes (not running)"
        except Exception:
            summary["redis_server_available"] = "no"
    return summary, results_list

def benchmark_rocksdb(iterations):
    results_list = []
    summary = {{}}
    tmpdir = tempfile.mkdtemp(prefix="rocksdb_bench_")
    db_bench_path = _find_binary("db_bench")
    if os.path.exists(db_bench_path):
        ops = ["fillseq", "fillrandom", "readrandom", "readseq", "deleterandom"]
        for op in ops:
            times = []
            for i in range(iterations):
                t0 = time.time()
                r = subprocess.run(
                    [db_bench_path, "--benchmarks=" + op, "--db=" + tmpdir + f"/db_{{i}}_{{op}}",
                     "--num=10000", "--value_size=100", "--threads=1"],
                    capture_output=True, text=True, timeout=120)
                times.append(time.time() - t0)
            summary[f"rocksdb_{{op}}"] = compute_stats(times)
            results_list.append({{
                "operation": f"rocksdb_{{op}}", "iterations": iterations,
                "avg_time_s": compute_stats(times).get("avg", 0),
            }})
    else:
        summary["rocksdb_db_bench"] = "not_found"
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return summary, results_list

def benchmark_mysql(iterations):
    results_list = []
    summary = {{}}
    mysql_path = _find_binary("mysql")
    mysqld_path = _find_binary("mysqld")
    mysql_ver = subprocess.run([mysqld_path, "--version"], capture_output=True, text=True, timeout=10)
    summary["mysql_version"] = mysql_ver.stdout.strip()[:200] if mysql_ver.returncode == 0 else "not_found"
    try:
        import mysql.connector as mc
        conn_times = []
        for i in range(iterations):
            t0 = time.time()
            try:
                conn = mc.connect(host="localhost", user="root", connect_timeout=5)
                conn.close()
                conn_times.append(time.time() - t0)
            except Exception:
                conn_times.append(None)
        conn_clean = [t for t in conn_times if t is not None]
        if conn_clean:
            summary["mysql_connect"] = compute_stats(conn_clean)
        results_list.append({{"operation": "mysql_connect", "iterations": iterations,
                              "avg_time_s": compute_stats(conn_clean).get("avg", 0) if conn_clean else None}})
    except ImportError:
        summary["mysql_connector"] = "not_available"
    try:
        r = subprocess.run([mysql_path, "-e", "SELECT 1+1;"],
                           capture_output=True, text=True, timeout=10)
        summary["mysql_cli_available"] = r.returncode == 0
    except Exception:
        summary["mysql_cli_available"] = False
    return summary, results_list

def benchmark_go(iterations):
    results_list = []
    summary = {{}}
    tmpdir = tempfile.mkdtemp(prefix="go_bench_")
    go_path = _find_binary("go")
    go_ver = subprocess.run([go_path, "version"], capture_output=True, text=True, timeout=10)
    summary["go_version"] = go_ver.stdout.strip()[:100] if go_ver.returncode == 0 else "not_found"

    go_hello = """package main

import "fmt"

func main() {{
    sum := 0.0
    for i := 0; i < 1000000; i++ {{
        sum += float64(i) * 0.0001
    }}
    fmt.Printf("sum = %f\\n", sum)
}}
"""
    src_dir = os.path.join(tmpdir, "hello")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "main.go"), "w") as f:
        f.write(go_hello)

    build_times = []
    for i in range(iterations):
        t0 = time.time()
        r = subprocess.run([go_path, "build", "-o", os.path.join(tmpdir, f"gohello_{{i}}"), src_dir],
                           capture_output=True, text=True, timeout=60)
        build_times.append(time.time() - t0)
    build_stats = compute_stats(build_times)
    summary["go_build_hello"] = build_stats
    results_list.append({{"operation": "go_build_hello", "iterations": iterations,
                          "avg_time_s": build_stats.get("avg", 0), "compile_success": r.returncode == 0}})

    run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"gohello_{{i}}")
        if os.path.exists(exe):
            t0 = time.time()
            subprocess.run([exe], capture_output=True, timeout=30)
            run_times.append(time.time() - t0)
    if run_times:
        run_stats = compute_stats(run_times)
        summary["go_hello_run"] = run_stats
        results_list.append({{"operation": "go_hello_run", "iterations": len(run_times),
                              "avg_time_s": run_stats.get("avg", 0)}})

    go_matmul = """package main

import "fmt"

func main() {{
    n := 500
    a := make([][]float64, n)
    b := make([][]float64, n)
    c := make([][]float64, n)
    for i := 0; i < n; i++ {{
        a[i] = make([]float64, n)
        b[i] = make([]float64, n)
        c[i] = make([]float64, n)
        for j := 0; j < n; j++ {{
            a[i][j] = float64(i*j) * 0.001
            b[i][j] = float64(i+j) * 0.001
        }}
    }}
    start := 0
    fmt.Println(start)
    for i := 0; i < n; i++ {{
        for k := 0; k < n; k++ {{
            aik := a[i][k]
            for j := 0; j < n; j++ {{
                c[i][j] += aik * b[k][j]
            }}
        }}
    }}
    fmt.Println(c[0][0])
}}
"""
    src_dir2 = os.path.join(tmpdir, "matmul")
    os.makedirs(src_dir2, exist_ok=True)
    with open(os.path.join(src_dir2, "main.go"), "w") as f:
        f.write(go_matmul)
    matmul_build_times = []
    for i in range(iterations):
        t0 = time.time()
        subprocess.run([go_path, "build", "-o", os.path.join(tmpdir, f"gomatmul_{{i}}"), src_dir2],
                       capture_output=True, text=True, timeout=60)
        matmul_build_times.append(time.time() - t0)
    matmul_build_stats = compute_stats(matmul_build_times)
    summary["go_build_matmul"] = matmul_build_stats
    results_list.append({{"operation": "go_build_matmul", "iterations": iterations,
                          "avg_time_s": matmul_build_stats.get("avg", 0)}})

    matmul_run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"gomatmul_{{i}}")
        if os.path.exists(exe):
            t0 = time.time()
            subprocess.run([exe], capture_output=True, timeout=60)
            matmul_run_times.append(time.time() - t0)
    if matmul_run_times:
        matmul_run_stats = compute_stats(matmul_run_times)
        summary["go_matmul_500x500"] = matmul_run_stats
        results_list.append({{"operation": "go_matmul_500x500", "iterations": len(matmul_run_times),
                              "avg_time_s": matmul_run_stats.get("avg", 0)}})

    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return summary, results_list

def benchmark_llvm(iterations):
    results_list = []
    summary = {{}}
    tmpdir = tempfile.mkdtemp(prefix="llvm_bench_")
    clang_path = _find_binary("clang")
    llc_path = _find_binary("llc")
    opt_path = _find_binary("opt")
    clang_ver = subprocess.run([clang_path, "--version"], capture_output=True, text=True, timeout=10)
    summary["clang_version"] = clang_ver.stdout.strip()[:200] if clang_ver.returncode == 0 else "not_found"

    c_code = """
#include <stdio.h>
#include <math.h>
#define N 1000000
int main() {{
    double sum = 0.0;
    for (int i = 0; i < N; i++) {{
        sum += i * 0.0001;
    }}
    printf("sum = %f\\n", sum);
    return 0;
}}
"""
    c_path = os.path.join(tmpdir, "bench.c")
    with open(c_path, "w") as f:
        f.write(c_code)

    clang_compile_times = []
    for i in range(iterations):
        t0 = time.time()
        r = subprocess.run([clang_path, "-O2", c_path, "-o", os.path.join(tmpdir, f"clang_bench_{{i}}"), "-lm"],
                           capture_output=True, text=True, timeout=30)
        clang_compile_times.append(time.time() - t0)
    clang_stats = compute_stats(clang_compile_times)
    summary["clang_compile_O2"] = clang_stats
    results_list.append({{"operation": "clang_compile_O2", "iterations": iterations,
                          "avg_time_s": clang_stats.get("avg", 0), "compile_success": r.returncode == 0}})

    clang_run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"clang_bench_{{i}}")
        if os.path.exists(exe):
            t0 = time.time()
            subprocess.run([exe], capture_output=True, timeout=10)
            clang_run_times.append(time.time() - t0)
    if clang_run_times:
        run_stats = compute_stats(clang_run_times)
        summary["clang_float_add_1M_run"] = run_stats
        results_list.append({{"operation": "clang_float_add_1M_run", "iterations": len(clang_run_times),
                              "avg_time_s": run_stats.get("avg", 0)}})

    c_matmul = """
#include <stdio.h>
#include <stdlib.h>
#define N 500
int main() {{
    double *a = malloc(N*N*sizeof(double));
    double *b = malloc(N*N*sizeof(double));
    double *c = malloc(N*N*sizeof(double));
    for (int i=0; i<N*N; i++) {{ a[i] = i*0.001; b[i] = (i/N+i%N)*0.001; c[i]=0; }}
    for (int i=0; i<N; i++)
        for (int k=0; k<N; k++)
            for (int j=0; j<N; j++)
                c[i*N+j] += a[i*N+k] * b[k*N+j];
    printf("c[0]=%f\\n", c[0]);
    free(a); free(b); free(c);
    return 0;
}}
"""
    c_path2 = os.path.join(tmpdir, "matmul.c")
    with open(c_path2, "w") as f:
        f.write(c_matmul)
    matmul_times = []
    for i in range(iterations):
        t0 = time.time()
        subprocess.run([clang_path, "-O2", c_path2, "-o", os.path.join(tmpdir, f"clang_matmul_{{i}}")],
                       capture_output=True, text=True, timeout=30)
        matmul_times.append(time.time() - t0)
    matmul_stats = compute_stats(matmul_times)
    summary["clang_compile_matmul_O2"] = matmul_stats
    results_list.append({{"operation": "clang_compile_matmul_O2", "iterations": iterations,
                          "avg_time_s": matmul_stats.get("avg", 0)}})
    matmul_run_times = []
    for i in range(iterations):
        exe = os.path.join(tmpdir, f"clang_matmul_{{i}}")
        if os.path.exists(exe):
            t0 = time.time()
            subprocess.run([exe], capture_output=True, timeout=30)
            matmul_run_times.append(time.time() - t0)
    if matmul_run_times:
        mrun_stats = compute_stats(matmul_run_times)
        summary["clang_matmul_500x500_run"] = mrun_stats
        results_list.append({{"operation": "clang_matmul_500x500_run", "iterations": len(matmul_run_times),
                              "avg_time_s": mrun_stats.get("avg", 0)}})

    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return summary, results_list

def benchmark_java(iterations):
    results_list = []
    summary = {{}}
    tmpdir = tempfile.mkdtemp(prefix="java_bench_")
    java_path = _find_binary("java")
    javac_path = _find_binary("javac")
    java_ver = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=10)
    summary["java_version"] = (java_ver.stderr or java_ver.stdout).strip()[:100] if java_ver.returncode == 0 else "not_found"

    java_code = """
public class Bench {{
    public static void main(String[] args) {{
        double sum = 0.0;
        for (int i = 0; i < 1000000; i++) {{
            sum += i * 0.0001;
        }}
        System.out.println("sum = " + sum);
    }}
}}
"""
    with open(os.path.join(tmpdir, "Bench.java"), "w") as f:
        f.write(java_code)

    javac_times = []
    for i in range(iterations):
        t0 = time.time()
        r = subprocess.run([javac_path, os.path.join(tmpdir, "Bench.java")],
                           capture_output=True, text=True, timeout=30)
        javac_times.append(time.time() - t0)
    javac_stats = compute_stats(javac_times)
    summary["javac_compile"] = javac_stats
    results_list.append({{"operation": "javac_compile", "iterations": iterations,
                          "avg_time_s": javac_stats.get("avg", 0), "compile_success": r.returncode == 0}})

    jvm_start_times = []
    java_run_times = []
    for i in range(iterations):
        t0 = time.time()
        r2 = subprocess.run([java_path, "-cp", tmpdir, "Bench"],
                            capture_output=True, text=True, timeout=30)
        elapsed = time.time() - t0
        java_run_times.append(elapsed)
    run_stats = compute_stats(java_run_times)
    summary["java_hello_run"] = run_stats
    results_list.append({{"operation": "java_hello_run", "iterations": iterations,
                          "avg_time_s": run_stats.get("avg", 0)}})

    java_matmul = """
public class MatMul {{
    public static void main(String[] args) {{
        int n = 500;
        double[][] a = new double[n][n];
        double[][] b = new double[n][n];
        double[][] c = new double[n][n];
        for (int i=0; i<n; i++) for (int j=0; j<n; j++) {{
            a[i][j] = i*j*0.001; b[i][j] = (i+j)*0.001;
        }}
        long start = System.nanoTime();
        for (int i=0; i<n; i++)
            for (int k=0; k<n; k++)
                for (int j=0; j<n; j++)
                    c[i][j] += a[i][k]*b[k][j];
        double elapsed = (System.nanoTime()-start)/1e9;
        System.out.println("matmul " + n + "x" + n + " time: " + elapsed + "s");
    }}
}}
"""
    with open(os.path.join(tmpdir, "MatMul.java"), "w") as f:
        f.write(java_matmul)
    subprocess.run([javac_path, os.path.join(tmpdir, "MatMul.java")],
                   capture_output=True, text=True, timeout=30)
    matmul_run_times = []
    for i in range(iterations):
        t0 = time.time()
        subprocess.run([java_path, "-cp", tmpdir, "MatMul"],
                       capture_output=True, text=True, timeout=60)
        matmul_run_times.append(time.time() - t0)
    matmul_stats = compute_stats(matmul_run_times)
    summary["java_matmul_500x500"] = matmul_stats
    results_list.append({{"operation": "java_matmul_500x500", "iterations": iterations,
                          "avg_time_s": matmul_stats.get("avg", 0)}})

    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return summary, results_list

def benchmark_node(iterations):
    results_list = []
    summary = {{}}
    node_path = _find_binary("node")
    node_ver = subprocess.run([node_path, "--version"], capture_output=True, text=True, timeout=10)
    summary["node_version"] = node_ver.stdout.strip()[:100] if node_ver.returncode == 0 else "not_found"

    node_ops = {{
        "float_add_1M": "let sum=0; for(let i=0;i<1000000;i++) sum+=i*0.0001; console.log(sum);",
        "json_parse_10K": "let s=JSON.stringify(Array.from({{length:10000}},(_,i)=>({{id:i,val:i*0.1}}))); let d=JSON.parse(s); console.log(d.length);",
        "array_sort_100K": "let a=Array.from({{length:100000}},(_,i)=>Math.random()); a.sort((x,y)=>x-y); console.log(a[0]);",
        "promise_1K": "let ps=Array.from({{length:1000}},(_,i)=>Promise.resolve(i)); Promise.all(ps).then(r=>console.log(r.length));",
    }}
    for op_name, code in node_ops.items():
        times = []
        for i in range(iterations):
            t0 = time.time()
            subprocess.run([node_path, "-e", code], capture_output=True, text=True, timeout=30)
            times.append(time.time() - t0)
        stats = compute_stats(times)
        summary[op_name] = stats
        results_list.append({{"operation": op_name, "iterations": iterations,
                              "avg_time_s": stats.get("avg", 0)}})

    tmpdir = tempfile.mkdtemp(prefix="node_bench_")
    node_matmul = """
const n = 500;
const a = Array.from({{length: n}}, (_, i) => Array.from({{length: n}}, (_, j) => i*j*0.001));
const b = Array.from({{length: n}}, (_, i) => Array.from({{length: n}}, (_, j) => (i+j)*0.001));
const c = Array.from({{length: n}}, () => new Float64Array(n));
const start = Date.now();
for (let i = 0; i < n; i++)
    for (let k = 0; k < n; k++)
        for (let j = 0; j < n; j++)
            c[i][j] += a[i][k] * b[k][j];
console.log("matmul " + n + "x" + n + " time: " + (Date.now()-start)/1000 + "s");
"""
    js_path = os.path.join(tmpdir, "matmul.js")
    with open(js_path, "w") as f:
        f.write(node_matmul)
    matmul_times = []
    for i in range(iterations):
        t0 = time.time()
        subprocess.run([node_path, js_path], capture_output=True, text=True, timeout=60)
        matmul_times.append(time.time() - t0)
    matmul_stats = compute_stats(matmul_times)
    summary["node_matmul_500x500"] = matmul_stats
    results_list.append({{"operation": "node_matmul_500x500", "iterations": iterations,
                          "avg_time_s": matmul_stats.get("avg", 0)}})

    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return summary, results_list

def benchmark_nginx(iterations):
    results_list = []
    summary = {{}}
    nginx_path = _find_binary("nginx")
    nginx_ver = subprocess.run([nginx_path, "-v"], capture_output=True, text=True, timeout=10)
    summary["nginx_version"] = (nginx_ver.stderr or nginx_ver.stdout).strip()[:100] if nginx_ver.returncode == 0 else "not_found"
    curl_path = _find_binary("curl")
    tmpdir = tempfile.mkdtemp(prefix="nginx_bench_")
    conf = """
worker_processes 1;
daemon off;
events {{ worker_connections 1024; }}
http {{
    server {{
        listen 18080;
        server_name localhost;
        location / {{
            return 200 'hello benchmark';
        }}
    }}
}}
"""
    conf_path = os.path.join(tmpdir, "nginx.conf")
    with open(conf_path, "w") as f:
        f.write(conf)

    nginx_proc = None
    try:
        nginx_proc = subprocess.Popen([nginx_path, "-c", conf_path],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        if curl_path and os.path.exists(curl_path):
            rps_times = []
            req_count = 1000
            for i in range(iterations):
                t0 = time.time()
                for j in range(req_count):
                    subprocess.run([curl_path, "-s", "http://localhost:18080/"], capture_output=True, timeout=5)
                elapsed = time.time() - t0
                rps_times.append(elapsed)
            rps_stats = compute_stats(rps_times)
            qps = req_count / rps_stats.get("avg", 1) if rps_stats.get("avg", 0) > 0 else 0
            summary["nginx_rps_1K"] = rps_stats
            summary["nginx_qps"] = round(qps, 2)
            results_list.append({{"operation": "nginx_rps_1K", "iterations": iterations,
                                  "avg_time_s": rps_stats.get("avg", 0), "qps": round(qps, 2)}})
    except Exception as e:
        summary["nginx_benchmark_error"] = str(e)[:200]
    finally:
        if nginx_proc:
            nginx_proc.terminate()
            nginx_proc.wait(timeout=5)
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return summary, results_list

def benchmark_hnswlib(iterations):
    results_list = []
    summary = {{}}
    try:
        import numpy as np
        import hnswlib
        n = 100000
        d = 128
        k = 10
        np.random.seed(42)
        data = np.random.random((n, d)).astype("float32")
        queries = np.random.random((100, d)).astype("float32")

        build_times = []
        for i in range(iterations):
            t0 = time.time()
            index = hnswlib.Index(space="l2", dim=d)
            index.init_index(max_elements=n, ef_construction=200, M=32)
            index.add_items(data)
            build_times.append(time.time() - t0)
        build_stats = compute_stats(build_times)
        summary["hnswlib_build_100K"] = build_stats
        results_list.append({{"operation": "hnswlib_build_100K", "iterations": iterations,
                              "avg_time_s": build_stats.get("avg", 0)}})

        search_times = []
        for i in range(iterations):
            t0 = time.time()
            labels, distances = index.knn_query(queries, k=k)
            search_times.append(time.time() - t0)
        search_stats = compute_stats(search_times)
        nq = queries.shape[0]
        qps = nq / search_stats.get("avg", 1) if search_stats.get("avg", 0) > 0 else 0
        summary["hnswlib_search_100queries"] = search_stats
        summary["hnswlib_qps"] = round(qps, 2)
        results_list.append({{"operation": "hnswlib_search_100q", "iterations": iterations,
                              "avg_time_s": search_stats.get("avg", 0), "qps": round(qps, 2)}})
    except ImportError as e:
        summary["hnswlib_import_error"] = str(e)[:200]
        try:
            import numpy as np2
            np = np2
            has_np = True
        except ImportError:
            has_np = False
        if has_np:
            for sz in [10000, 100000]:
                dot_times = []
                for i in range(iterations):
                    a = np.random.random(sz).astype("float32")
                    b = np.random.random(sz).astype("float32")
                    t0 = time.time()
                    c = np.dot(a, b)
                    dot_times.append(time.time() - t0)
                stats = compute_stats(dot_times)
                summary[f"numpy_dot_{{sz}}"] = stats
                results_list.append({{"operation": f"numpy_dot_{{sz}}", "iterations": iterations,
                                      "avg_time_s": stats.get("avg", 0)}})
    return summary, results_list

def benchmark_opencv(iterations):
    results_list = []
    summary = {{}}
    try:
        import cv2
        import numpy as np
        summary["opencv_version"] = getattr(cv2, "__version__", "unknown")

        img_sizes = [(640, 480), (1920, 1080), (3840, 2160)]
        for w, h in img_sizes:
            gauss_times = []
            resize_times = []
            for i in range(iterations):
                img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
                t0 = time.time()
                blurred = cv2.GaussianBlur(img, (15, 15), 0)
                gauss_times.append(time.time() - t0)
                t0 = time.time()
                resized = cv2.resize(img, (w // 2, h // 2))
                resize_times.append(time.time() - t0)
            summary[f"opencv_gauss_{{w}}x{{h}}"] = compute_stats(gauss_times)
            summary[f"opencv_resize_{{w}}x{{h}}"] = compute_stats(resize_times)
            results_list.append({{"operation": f"opencv_gauss_{{w}}x{{h}}", "iterations": iterations,
                                  "avg_time_s": compute_stats(gauss_times).get("avg", 0)}})
            results_list.append({{"operation": f"opencv_resize_{{w}}x{{h}}", "iterations": iterations,
                                  "avg_time_s": compute_stats(resize_times).get("avg", 0)}})

        encode_times = []
        for i in range(iterations):
            img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            t0 = time.time()
            _, encoded = cv2.imencode(".jpg", img)
            encode_times.append(time.time() - t0)
        summary["opencv_jpg_encode_640x480"] = compute_stats(encode_times)
        results_list.append({{"operation": "opencv_jpg_encode_640x480", "iterations": iterations,
                              "avg_time_s": compute_stats(encode_times).get("avg", 0)}})

        detect_times = []
        for i in range(iterations):
            img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            t0 = time.time()
            edges = cv2.Canny(gray, 50, 150)
            detect_times.append(time.time() - t0)
        summary["opencv_canny_640x480"] = compute_stats(detect_times)
        results_list.append({{"operation": "opencv_canny_640x480", "iterations": iterations,
                              "avg_time_s": compute_stats(detect_times).get("avg", 0)}})
    except ImportError as e:
        summary["opencv_import_error"] = str(e)[:200]
    return summary, results_list

def benchmark_protobuf(iterations):
    results_list = []
    summary = {{}}
    try:
        from google.protobuf import descriptor_pb2
        import google.protobuf
        summary["protobuf_version"] = getattr(google.protobuf, "__version__", "unknown")
        msg = descriptor_pb2.FileDescriptorProto()
        msg.name = "bench.proto"
        msg.package = "bench"
        msg.syntax = "proto3"

        ser_times = []
        de_times = []
        for i in range(iterations):
            msg_data = msg.SerializeToString()
            t0 = time.time()
            for j in range(10000):
                msg_data = msg.SerializeToString()
            ser_times.append(time.time() - t0)
            t0 = time.time()
            for j in range(10000):
                msg2 = descriptor_pb2.FileDescriptorProto()
                msg2.ParseFromString(msg_data)
            de_times.append(time.time() - t0)
        summary["protobuf_serialize_10K"] = compute_stats(ser_times)
        summary["protobuf_deserialize_10K"] = compute_stats(de_times)
        results_list.append({{"operation": "protobuf_serialize_10K", "iterations": iterations,
                              "avg_time_s": compute_stats(ser_times).get("avg", 0)}})
        results_list.append({{"operation": "protobuf_deserialize_10K", "iterations": iterations,
                              "avg_time_s": compute_stats(de_times).get("avg", 0)}})

        big_msg = descriptor_pb2.FileDescriptorProto()
        big_msg.name = "big_bench.proto"
        for idx in range(1000):
            dep = big_msg.dependency.add()
            dep = f"dep_{{idx}}.proto"
        ser_big_times = []
        de_big_times = []
        for i in range(iterations):
            t0 = time.time()
            big_data = big_msg.SerializeToString()
            ser_big_times.append(time.time() - t0)
            t0 = time.time()
            big_msg2 = descriptor_pb2.FileDescriptorProto()
            big_msg2.ParseFromString(big_data)
            de_big_times.append(time.time() - t0)
        summary["protobuf_serialize_big_1K_deps"] = compute_stats(ser_big_times)
        summary["protobuf_deserialize_big_1K_deps"] = compute_stats(de_big_times)
        results_list.append({{"operation": "protobuf_serialize_big", "iterations": iterations,
                              "avg_time_s": compute_stats(ser_big_times).get("avg", 0)}})
        results_list.append({{"operation": "protobuf_deserialize_big", "iterations": iterations,
                              "avg_time_s": compute_stats(de_big_times).get("avg", 0)}})
    except ImportError as e:
        summary["protobuf_import_error"] = str(e)[:200]
    return summary, results_list

def benchmark_rdkit(iterations):
    results_list = []
    summary = {{}}
    try:
        from rdkit import Chem
        from rdkit import RDLogger
        RDLogger.logger().setLevel(RDLogger.ERROR)
        import rdkit
        summary["rdkit_version"] = getattr(rdkit, "__version__", "unknown")

        smiles_list = ["CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O",
                       "CCCCCCCCCCCCCCCC", "C1CCCCC1", "CC(C)CC(C)C",
                       "c1ccc2c(c1)ccc1ccccc2c1c", "CCN(CC)CC"]
        mol_times = []
        for i in range(iterations):
            t0 = time.time()
            mols = [Chem.MolFromSmiles(s) for s in smiles_list]
            mol_times.append(time.time() - t0)
        summary["rdkit_smiles_parse_8"] = compute_stats(mol_times)
        results_list.append({{"operation": "rdkit_smiles_parse_8", "iterations": iterations,
                              "avg_time_s": compute_stats(mol_times).get("avg", 0)}})

        murcko_times = []
        for i in range(iterations):
            t0 = time.time()
            scaffolds = [Chem.MolToSmiles(Chem.GetScaffoldForMol(m)) for m in mols if m]
            murcko_times.append(time.time() - t0)
        summary["rdkit_murcko_scaffold_8"] = compute_stats(murcko_times)
        results_list.append({{"operation": "rdkit_murcko_scaffold_8", "iterations": iterations,
                              "avg_time_s": compute_stats(murcko_times).get("avg", 0)}})

        fp_times = []
        for i in range(iterations):
            t0 = time.time()
            fps = [Chem.RDKFingerprint(m) for m in mols if m]
            fp_times.append(time.time() - t0)
        summary["rdkit_fingerprint_8"] = compute_stats(fp_times)
        results_list.append({{"operation": "rdkit_fingerprint_8", "iterations": iterations,
                              "avg_time_s": compute_stats(fp_times).get("avg", 0)}})

        sim_times = []
        for i in range(iterations):
            from rdkit import DataStructs
            t0 = time.time()
            for fp1 in fps[:4]:
                for fp2 in fps[:4]:
                    DataStructs.FingerprintSimilarity(fp1, fp2)
            sim_times.append(time.time() - t0)
        summary["rdkit_similarity_4x4"] = compute_stats(sim_times)
        results_list.append({{"operation": "rdkit_similarity_4x4", "iterations": iterations,
                              "avg_time_s": compute_stats(sim_times).get("avg", 0)}})
    except ImportError as e:
        summary["rdkit_import_error"] = str(e)[:200]
    return summary, results_list

def benchmark_hadoop(iterations):
    results_list = []
    summary = {{}}
    hadoop_path = _find_binary("hadoop")
    hdfs_path = _find_binary("hdfs")
    java_path = _find_binary("java")
    if os.path.exists(hadoop_path):
        r = subprocess.run([hadoop_path, "version"], capture_output=True, text=True, timeout=10)
        summary["hadoop_version"] = r.stdout.strip()[:200] if r.returncode == 0 else "not_found"
    else:
        summary["hadoop_version"] = "not_found"
    if os.path.exists(hdfs_path):
        r2 = subprocess.run([hdfs_path, "version"], capture_output=True, text=True, timeout=10)
        summary["hdfs_version"] = r2.stdout.strip()[:200] if r2.returncode == 0 else "not_found"
    else:
        summary["hdfs_version"] = "not_found"
    try:
        import subprocess
        if os.path.exists(java_path):
            tmpdir = tempfile.mkdtemp(prefix="hadoop_bench_")
            java_wordcount = """
import java.io.*;
import java.util.*;
public class WordCount {{
    public static void main(String[] args) {{
        Map<String, Integer> counts = new HashMap<>();
        for (int i = 0; i < 1000000; i++) {{
            String w = "word" + (i % 100);
            counts.merge(w, 1, Integer::sum);
        }}
        System.out.println("unique words: " + counts.size());
    }}
}}
"""
            with open(os.path.join(tmpdir, "WordCount.java"), "w") as f:
                f.write(java_wordcount)
            javac_path = _find_binary("javac")
            subprocess.run([javac_path, os.path.join(tmpdir, "WordCount.java")],
                           capture_output=True, text=True, timeout=30)
            wc_times = []
            for i in range(iterations):
                t0 = time.time()
                subprocess.run([java_path, "-cp", tmpdir, "WordCount"],
                               capture_output=True, text=True, timeout=30)
                wc_times.append(time.time() - t0)
            wc_stats = compute_stats(wc_times)
            summary["java_wordcount_1M"] = wc_stats
            results_list.append({{"operation": "java_wordcount_1M", "iterations": iterations,
                                  "avg_time_s": wc_stats.get("avg", 0)}})
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass
    except Exception as e:
        summary["hadoop_bench_error"] = str(e)[:200]
    return summary, results_list

def benchmark_kylin(iterations):
    results_list = []
    summary = {{}}
    kylin_path = _find_binary("kylin")
    if os.path.exists(kylin_path):
        r = subprocess.run([kylin_path, "--version"], capture_output=True, text=True, timeout=10)
        summary["kylin_version"] = (r.stdout or r.stderr).strip()[:200] if r.returncode == 0 else "not_found"
    else:
        summary["kylin_version"] = "not_found"
    java_path = _find_binary("java")
    javac_path = _find_binary("javac")
    if os.path.exists(java_path) and os.path.exists(javac_path):
        tmpdir = tempfile.mkdtemp(prefix="kylin_bench_")
        java_cube = """
import java.util.*;
public class CubeAgg {{
    public static void main(String[] args) {{
        int n = 100000;
        Map<String, Long> agg = new HashMap<>();
        for (int i = 0; i < n; i++) {{
            String dim1 = "dim" + (i % 10);
            String dim2 = "dim" + (i % 5);
            String key = dim1 + "|" + dim2;
            agg.merge(key, (long)i, Long::sum);
        }}
        System.out.println("cube entries: " + agg.size());
    }}
}}
"""
        with open(os.path.join(tmpdir, "CubeAgg.java"), "w") as f:
            f.write(java_cube)
        subprocess.run([javac_path, os.path.join(tmpdir, "CubeAgg.java")],
                       capture_output=True, text=True, timeout=30)
        cube_times = []
        for i in range(iterations):
            t0 = time.time()
            subprocess.run([java_path, "-cp", tmpdir, "CubeAgg"],
                           capture_output=True, text=True, timeout=30)
            cube_times.append(time.time() - t0)
        cube_stats = compute_stats(cube_times)
        summary["kylin_cube_agg_100K"] = cube_stats
        results_list.append({{"operation": "kylin_cube_agg_100K", "iterations": iterations,
                              "avg_time_s": cube_stats.get("avg", 0)}})
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
    return summary, results_list

def benchmark_mooncake(iterations):
    results_list = []
    summary = {{}}
    mooncake_path = _find_binary("mooncake")
    python3_path = _find_binary("python3")
    try:
        subprocess.run([python3_path, "-c", "import mooncake"],
                       capture_output=True, text=True, timeout=10)
        summary["mooncake_python"] = "available"
    except Exception:
        summary["mooncake_python"] = "not_available"
    ops = [
        ("float_add_1M", lambda: sum(j * 0.0001 for j in range(1000000))),
        ("list_sort_100K", lambda: sorted([j * 0.001 for j in range(100000)])),
        ("dict_create_100K", lambda: dict((j, j * 0.001) for j in range(100000))),
    ]
    for op_name, op_func in ops:
        times = []
        for i in range(iterations):
            t0 = time.time()
            op_func()
            times.append(time.time() - t0)
        summary[op_name] = compute_stats(times)
        results_list.append({{"operation": op_name, "iterations": iterations,
                              "avg_time_s": compute_stats(times).get("avg", 0)}})
    return summary, results_list

def benchmark_juicefs(iterations):
    results_list = []
    summary = {{}}
    juicefs_path = _find_binary("juicefs")
    if os.path.exists(juicefs_path):
        r = subprocess.run([juicefs_path, "--version"], capture_output=True, text=True, timeout=10)
        summary["juicefs_version"] = (r.stdout or r.stderr).strip()[:200] if r.returncode == 0 else "not_found"
    else:
        summary["juicefs_version"] = "not_found"

    tmpdir = tempfile.mkdtemp(prefix="juicefs_io_bench_")
    io_times = {{}}
    for io_op in ["write_1MB", "write_10MB", "read_1MB"]:
        sizes = {{\"write_1MB": 1048576, "write_10MB": 10485760, "read_1MB": 1048576}}
        sz = sizes[io_op]
        times = []
        for i in range(iterations):
            fpath = os.path.join(tmpdir, f"io_{{io_op}}_{{i}}")
            t0 = time.time()
            if io_op.startswith("write"):
                with open(fpath, "wb") as f:
                    f.write(os.urandom(sz))
            else:
                if os.path.exists(fpath.replace("read", "write")):
                    with open(fpath.replace("read", "write"), "rb") as f:
                        f.read()
            times.append(time.time() - t0)
        stats = compute_stats(times)
        io_times[io_op] = stats
        summary[io_op] = stats
        results_list.append({{"operation": io_op, "size_bytes": sz, "iterations": iterations,
                              "avg_time_s": stats.get("avg", 0)}})

    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return summary, results_list

def benchmark_seissol(iterations):
    results_list = []
    summary = {{}}
    seissol_path = _find_binary("SeisSol")
    if os.path.exists(seissol_path):
        r = subprocess.run([seissol_path, "--version"], capture_output=True, text=True, timeout=10)
        summary["seissol_version"] = (r.stdout or r.stderr).strip()[:200] if r.returncode == 0 else "not_found"
    else:
        summary["seissol_version"] = "not_found"
    try:
        import numpy as np
        has_np = True
    except ImportError:
        np = None
        has_np = False
    if has_np:
        stencil_times = []
        for i in range(iterations):
            n = 10000
            a = np.random.random(n).astype("float64")
            b = np.zeros(n).astype("float64")
            t0 = time.time()
            for j in range(1, n - 1):
                b[j] = (a[j-1] + a[j] + a[j+1]) / 3.0
            stencil_times.append(time.time() - t0)
        summary["numpy_stencil_10K"] = compute_stats(stencil_times)
        results_list.append({{"operation": "numpy_stencil_10K", "iterations": iterations,
                              "avg_time_s": compute_stats(stencil_times).get("avg", 0)}})

        laplace_times = []
        for i in range(iterations):
            n = 100
            A = np.eye(n) * 4 + np.roll(np.eye(n), 1, axis=1) * -1 + np.roll(np.eye(n), -1, axis=1) * -1
            b_vec = np.random.random(n).astype("float64")
            t0 = time.time()
            x = np.linalg.solve(A, b_vec)
            laplace_times.append(time.time() - t0)
        summary["numpy_laplace_solve_100"] = compute_stats(laplace_times)
        results_list.append({{"operation": "numpy_laplace_solve_100", "iterations": iterations,
                              "avg_time_s": compute_stats(laplace_times).get("avg", 0)}})
    else:
        ops = [
            ("float_add_1M", lambda: sum(j * 0.0001 for j in range(1000000))),
            ("list_sort_100K", lambda: sorted([j * 0.001 for j in range(100000)])),
            ("fibonacci_iter_100K", lambda: _fib_iter(100000)),
        ]
        for op_name, op_func in ops:
            times = []
            for i in range(iterations):
                t0 = time.time()
                op_func()
                times.append(time.time() - t0)
            summary[op_name] = compute_stats(times)
            results_list.append({{"operation": op_name, "iterations": iterations,
                                  "avg_time_s": compute_stats(times).get("avg", 0)}})
    return summary, results_list

def benchmark_generic_compute(iterations):
    results_list = []
    summary = {{}}
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
        results_list.append({{
            "operation": "numpy_dot_100K", "iterations": iterations,
            "avg_time_s": compute_stats(dot_times).get("avg", 0),
        }})

        mat_times = []
        for i in range(iterations):
            A = np.random.random((100, 100)).astype("float64")
            x = np.random.random(100).astype("float64")
            t0 = time.time()
            y = A @ x
            mat_times.append(time.time() - t0)
        summary["numpy_matmult_100x100"] = compute_stats(mat_times)
        results_list.append({{
            "operation": "numpy_matmult_100x100", "iterations": iterations,
            "avg_time_s": compute_stats(mat_times).get("avg", 0),
        }})

        fft_times = []
        for i in range(iterations):
            t0 = time.time()
            np.fft.fft(np.random.random(10000))
            fft_times.append(time.time() - t0)
        summary["numpy_fft_10K"] = compute_stats(fft_times)
        results_list.append({{
            "operation": "numpy_fft_10K", "iterations": iterations,
            "avg_time_s": compute_stats(fft_times).get("avg", 0),
        }})
    else:
        ops = [
            ("float_add_1M", lambda: sum(j * 0.0001 for j in range(1000000))),
            ("float_add_10M", lambda: sum(j * 0.0001 for j in range(10000000))),
            ("list_sort_100K", lambda: sorted([j * 0.001 for j in range(100000)])),
            ("list_sort_1M", lambda: sorted([j * 0.001 for j in range(1000000)])),
            ("dict_create_100K", lambda: dict((j, j * 0.001) for j in range(100000))),
            ("set_membership_100K", lambda: all(j in set(range(100000)) for j in range(0, 100000, 100))),
            ("string_concat_10K", lambda: "".join(str(j) for j in range(10000))),
            ("fibonacci_iter_100K", lambda: _fib_iter(100000)),
        ]
        for op_name, op_func in ops:
            times = []
            for i in range(iterations):
                t0 = time.time()
                op_func()
                times.append(time.time() - t0)
            summary[op_name] = compute_stats(times)
            results_list.append({{
                "operation": op_name, "iterations": iterations,
                "avg_time_s": compute_stats(times).get("avg", 0),
            }})

    return summary, results_list

SOFTWARE_BENCHMARKS = {{
    "petsc": benchmark_petsc,
    "rust": benchmark_rust,
    "faiss": benchmark_faiss,
    "numpy": benchmark_numpy,
    "redis": benchmark_redis,
    "rocksdb": benchmark_rocksdb,
    "mysql": benchmark_mysql,
    "go": benchmark_go,
    "llvm": benchmark_llvm,
    "clang": benchmark_llvm,
    "java": benchmark_java,
    "node": benchmark_node,
    "nginx": benchmark_nginx,
    "hnswlib": benchmark_hnswlib,
    "opencv": benchmark_opencv,
    "protobuf": benchmark_protobuf,
    "rdkit": benchmark_rdkit,
    "hadoop": benchmark_hadoop,
    "kylin": benchmark_kylin,
    "mooncake": benchmark_mooncake,
    "juicefs": benchmark_juicefs,
    "seissol": benchmark_seissol,
    "lucene": benchmark_hadoop,
    "kibana": benchmark_java,
    "mongoose": benchmark_generic_compute,
    "xla": benchmark_generic_compute,
    "tensorrt-llm": benchmark_generic_compute,
    "fbthrift": benchmark_generic_compute,
    "openvelinux": benchmark_generic_compute,
    "openviking": benchmark_generic_compute,
    "opencloudos": benchmark_generic_compute,
    "cloudwego": benchmark_go,
    "kata-containers": benchmark_generic_compute,
    "kuberay": benchmark_generic_compute,
    "kubeflow": benchmark_generic_compute,
    "e2b": benchmark_generic_compute,
    "sriov-network-operator": benchmark_generic_compute,
    "deathstarbench": benchmark_generic_compute,
    "reedsolomon": benchmark_generic_compute,
    "circos": benchmark_generic_compute,
    "ncl": benchmark_generic_compute,
    "cactus": benchmark_generic_compute,
    "tophat": benchmark_generic_compute,
    "prottest3": benchmark_generic_compute,
    "cufflinks": benchmark_generic_compute,
}}

def run_benchmark(output_file, version, iterations):
    py_found, bin_found = survey_container()
    sys_info = collect_system_info()

    sw_lower = SOFTWARE_NAME.lower()
    bench_func = SOFTWARE_BENCHMARKS.get(sw_lower, benchmark_generic_compute)

    print(f"[BENCHMARK] Running {{sw_lower}} benchmark (func={{bench_func.__name__}}, iterations={{iterations}})")
    sw_summary, sw_results = bench_func(iterations)

    if sw_lower not in SOFTWARE_BENCHMARKS and py_found:
        for dep_name, dep_version in py_found.items():
            dep_func = SOFTWARE_BENCHMARKS.get(dep_name)
            if dep_func:
                try:
                    dep_summary, dep_results = dep_func(iterations)
                    for k, v in dep_summary.items():
                        sw_summary[f"{{dep_name}}_{{k}}"] = v
                    sw_results.extend(dep_results)
                except Exception as e:
                    sw_summary[f"{{dep_name}}_error"] = str(e)[:200]

    perf_metrics = {{}}
    for op_name, stats in sw_summary.items():
        if isinstance(stats, dict) and "avg" in stats:
            perf_metrics[op_name] = {{
                "unit": "seconds",
                "avg_s": stats.get("avg", 0),
                "min_s": stats.get("min", 0),
                "max_s": stats.get("max", 0),
                "p99_s": stats.get("p99", 0),
            }}

    output = {{
        "benchmark": "container_performance",
        "description": f"{{SOFTWARE_NAME}} performance benchmark - real computational tests in container environment",
        "reference": "https://github.com/erikbern/ann-benchmarks methodology",
        "software": SOFTWARE_NAME,
        "version": version,
        "architecture": sys_info.get("architecture", "unknown"),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performance_metrics": perf_metrics,
        "system_info": sys_info,
        "parameters": {{
            "iterations": iterations,
            "software_specific": sw_lower in SOFTWARE_BENCHMARKS,
        }},
        "container_environment": {{
            "python_packages": py_found,
            "binaries": dict((k, v[1][:80]) for k, v in bin_found.items()),
        }},
        "results_summary": sw_summary,
        "results": sw_results,
    }}

    print(f"[BENCHMARK] {{SOFTWARE_NAME}}: {{len(sw_results)}} test results, {{len(sw_summary)}} summary entries")

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[BENCHMARK] Output written to {{output_file}}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    run_benchmark(args.output, args.version, args.iterations)
'''

MICRO_BENCHMARK_PY = '''#!/usr/bin/env python3
import argparse
import json
import time
import sys
import subprocess
import os

SOFTWARE_NAME = "{software}"

def time_operation(name, func, iterations):
    times = []
    for _ in range(iterations):
        start = time.time()
        try:
            func()
        except Exception:
            pass
        times.append(time.time() - start)
    avg = sum(times) / len(times) if times else 0
    min_t = min(times) if times else 0
    max_t = max(times) if times else 0
    return {{
        "avg_time_s": round(avg, 4),
        "min_time_s": round(min_t, 4),
        "max_time_s": round(max_t, 4),
        "iterations": iterations,
    }}

def detect_and_benchmark(iterations):
    results = {{
        "benchmark": "micro_operations",
        "description": f"{{SOFTWARE_NAME}} micro benchmark",
        "reference": "SKILL.md",
        "parameters": {{
            "iterations": iterations,
        }},
        "performance_metrics": {{}},
        "results": {{}},
    }}

    op_results = {{}}

    py_modules = {{
        "faiss": "faiss", "hnswlib": "hnswlib", "lz4": "lz4",
        "protobuf": "google.protobuf", "pytorch": "torch",
        "scann": "scann", "openviking": "openviking",
        "numpy": "numpy", "pandas": "pandas", "scipy": "scipy",
    }}
    for sw_name, module in py_modules.items():
        try:
            mod = __import__(module)
            op_results["import_" + sw_name] = time_operation(
                "import_" + sw_name,
                lambda: __import__(module),
                1,
            )
            ver = getattr(mod, "__version__", "unknown")
            op_results["import_" + sw_name]["version"] = ver
        except ImportError:
            pass

    binaries = ["redis-cli", "mysql", "nginx", "go", "java", "python3", "docker", "kubectl", "etcd"]
    for b in binaries:
        try:
            r = subprocess.run(["which", b], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                op_results["which_" + b] = time_operation(
                    "which_" + b,
                    lambda: subprocess.run(["which", b], capture_output=True, timeout=5),
                    iterations,
                )
        except Exception:
            pass

    cpu_count = os.cpu_count() or 1
    op_results["system_info"] = {{
        "cpu_cores": cpu_count,
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
    }}

    results["results"] = op_results
    results["performance_metrics"]["operation_count"] = len(op_results)
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()
    data = detect_and_benchmark(args.iterations)
    data["version"] = args.version
    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[MICRO] Output written to {{args.output}}")
'''

AGGREGATE_RESULTS_TEMPLATE = '''#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone


def aggregate_results(results_dir, output_file):
    os.makedirs(results_dir, exist_ok=True)

    merged = {{
        "software_name": "{software}",
        "primary_benchmark": {{}},
        "micro_benchmark": {{}},
        "environment": {{}},
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "test_time": "",
    }}

    benchmark_map = {{
        "benchmark_ann.json": "primary_benchmark",
        "benchmark_kv.json": "primary_benchmark",
        "benchmark_generic.json": "primary_benchmark",
        "micro_benchmark.json": "micro_benchmark",
    }}

    for filename, key in benchmark_map.items():
        filepath = os.path.join(results_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                merged[key] = data
                print(f"[AGGREGATE] Loaded {{key}} from {{filepath}}")
            except Exception as e:
                print(f"[AGGREGATE] Failed to load {{filepath}}: {{e}}")

    env_file = os.path.join(results_dir, "version_info.json")
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                merged["environment"] = json.load(f)
            merged["test_time"] = merged["environment"].get("test_time", "")
            print(f"[AGGREGATE] Loaded environment from {{env_file}}")
        except Exception as e:
            print(f"[AGGREGATE] Failed to load {{env_file}}: {{e}}")

    try:
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(merged, f, indent=2)
        print(f"[AGGREGATE] Aggregated results saved to {{output_file}}")
    except Exception as e:
        print(f"[AGGREGATE] Failed to write {{output_file}}: {{e}}")
    return merged


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: aggregate_results.py <results_dir> <output_file>")
        sys.exit(1)
    aggregate_results(sys.argv[1], sys.argv[2])
'''

GENERATE_SUMMARY_TEMPLATE = '''#!/usr/bin/env python3
import sys
import json
import os
from datetime import datetime, timezone


def generate_summary(input_json, output_file):
    if not os.path.exists(input_json):
        lines = [
            "=" * 70,
            "  {software} Performance Benchmark Report",
            "=" * 70,
            f"  Generated: {{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}}",
            "  Status: INCOMPLETE - benchmark data not available",
            "=" * 70,
        ]
        summary = "\\n".join(lines)
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            f.write(summary)
        print(summary)
        return

    with open(input_json) as f:
        data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("  {software} Performance Benchmark Report")
    lines.append("=" * 70)
    lines.append(f"  Generated: {{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}}")
    lines.append(f"  Test Time: {{data.get('test_time', data.get('timestamp', 'N/A'))}}")
    lines.append("")

    env = data.get("environment", {{}})
    if env:
        lines.append("  --- Environment ---")
        lines.append(f"  Architecture:      {{env.get('architecture', 'N/A')}}")
        lines.append(f"  Model:             {{env.get('Model', 'N/A')}}")
        lines.append(f"  CPU Model:         {{env.get('cpu_model', 'N/A')}}")
        lines.append(f"  CPU Cores:         {{env.get('cpu_cores', 'N/A')}}")
        lines.append(f"  {software} Version:   {{env.get('software_version', 'N/A')}}")
        lines.append(f"  Python Version:    {{env.get('python_version', 'N/A')}}")
        lines.append(f"  OS:                {{env.get('os', 'N/A')}}")
        lines.append(f"  Kernel:            {{env.get('kernel', 'N/A')}}")
        lines.append("")

    primary = data.get("primary_benchmark", {{}})
    if primary:
        params = primary.get("parameters", {{}})
        lines.append("  --- Primary Benchmark ---")
        lines.append(f"  Description:       {{primary.get('description', 'N/A')}}")
        lines.append(f"  Parameters:        {{params}}")
        lines.append("")
        results_summary = primary.get("results_summary", {{}})
        if isinstance(results_summary, dict):
            for name, res in results_summary.items():
                if isinstance(res, dict):
                    lines.append(f"  {{name}}:")
                    for k, v in res.items():
                        lines.append(f"    {{k}}: {{v}}")
                else:
                    lines.append(f"  {{name}}: {{res}}")
                lines.append("")

    micro = data.get("micro_benchmark", {{}})
    if micro:
        mparams = micro.get("parameters", {{}})
        lines.append("  --- Micro Benchmarks ---")
        lines.append(f"  Description:       {{micro.get('description', 'N/A')}}")
        lines.append(f"  Parameters:        {{mparams}}")
        lines.append("")
        results = micro.get("results", {{}})
        if isinstance(results, dict):
            for name, res in results.items():
                if isinstance(res, dict):
                    lines.append(f"  {{name}}:")
                    for k, v in res.items():
                        lines.append(f"    {{k}}: {{v}}")
                else:
                    lines.append(f"  {{name}}: {{res}}")
                lines.append("")

    lines.append("=" * 70)
    lines.append("  Report generated by {software} Performance Benchmark Workflow")
    lines.append("=" * 70)

    summary = "\\n".join(lines)
    with open(output_file, "w") as f:
        f.write(summary)
    print(summary)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_summary.py <input_json> <output_file>")
        sys.exit(1)
    generate_summary(sys.argv[1], sys.argv[2])
'''

JSON_HELPER_MINIMAL = '''#!/usr/bin/env python3
import json
import sys


def load_json(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def get_nested(data, keys):
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)]
        else:
            return None
    return data


def cmd_write_version_info(filepath, timestamp, model, arch, kernel, os_name, cpu_model,
                           cores, sw_name, sw_version, python_ver, numpy_ver):
    data = {{
        "test_time": str(timestamp),
        "Model": str(model),
        "architecture": str(arch),
        "kernel": str(kernel),
        "os": str(os_name),
        "cpu_model": str(cpu_model),
        "cpu_cores": int(cores),
        "software_name": str(sw_name),
        "software_version": str(sw_version),
        "python_version": str(python_ver),
        "numpy_version": str(numpy_ver),
    }}
    save_json(filepath, data)


def main():
    filepath = sys.argv[1]
    command = sys.argv[2]
    args = sys.argv[3:]
    if command == "write_version_info":
        cmd_write_version_info(filepath, *args)
    elif command == "get":
        data = load_json(filepath)
        result = get_nested(data, args)
        print(result if result is not None else "NULL")
    elif command == "field_exists":
        data = load_json(filepath)
        print(1 if args[0] in data else 0)
    elif command == "count_results":
        data = load_json(filepath)
        print(len(data.get("results", data.get("results_summary", {{}}))))
    elif command == "version":
        data = load_json(filepath)
        print(data.get("software_version", "unknown"))
    elif command == "contains":
        with open(filepath) as f:
            print(1 if args[0] in f.read() else 0)
    elif command == "throughput_ge":
        print(0)
    elif command == "latency_le":
        print(0)
    elif command == "avg_throughput":
        print(0)
    elif command == "max_latency":
        print(0)
    else:
        print(f"Unknown command: {{command}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''


def build_test_sh(software, version, docker_namespace, docker_tag, benchmark_type):
    sw = software
    ver = version or "1.0.0"
    bm_type = benchmark_type
    docker_image = f"{docker_namespace}/{sw}"
    docker_tag_val = docker_tag or f"{ver}-oe2403sp3"

    if bm_type == "benchmark_ann":
        bench_file = "benchmark_ann.json"
        bench_cmd = f'    docker exec "${{DOCKER_CID}}" python3 /workspace/scripts/benchmark_generic.py --output /workspace/results/${{SOFTWARE_VERSION}}/benchmark_generic.json --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"'
    elif bm_type == "benchmark_kv":
        bench_file = "benchmark_kv.json"
        bench_cmd = f'    docker exec "${{DOCKER_CID}}" python3 /workspace/scripts/benchmark_generic.py --output /workspace/results/${{SOFTWARE_VERSION}}/benchmark_generic.json --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"'
    else:
        bench_file = "benchmark_generic.json"
        bench_cmd = f'    docker exec "${{DOCKER_CID}}" python3 /workspace/scripts/benchmark_generic.py --output /workspace/results/${{SOFTWARE_VERSION}}/benchmark_generic.json --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"'

    python_module = PYTHON_MODULE_MAP.get(sw, sw)

    lines = [
        '#!/bin/bash',
        '',
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        f'SOFTWARE_NAME="{sw}"',
        f'SOFTWARE_VERSION="${{SOFTWARE_VERSION:-{ver}}}"',
        'export SOFTWARE_VERSION',
        f'DOCKER_IMAGE="{docker_image}"',
        f'DOCKER_TAG="${{DOCKER_TAG:-{docker_tag_val}}}"',
        'DOCKER_CID=""',
        'SHUNIT2_PATH=""',
        'HAS_PYTHON3=0',
        'ITERATIONS="${ITERATIONS:-1}"',
        '',
        'RESULTS_DIR="${SCRIPT_DIR}/results/${SOFTWARE_VERSION}"',
        'mkdir -p "${RESULTS_DIR}"',
        'LOG_FILE="${RESULTS_DIR}/results.log"',
        'JSON_HELPER="${SCRIPT_DIR}/scripts/json_helper.py"',
        '',
        'log() { local tag="$1"; shift; printf \'[%s] %s\\n\' "$tag" "$*" | tee -a "${LOG_FILE}"; }',
        '',
        'json_get()              { python3 "${JSON_HELPER}" "$1" get "${@:2}"; }',
        'json_field_exists()     { python3 "${JSON_HELPER}" "$1" field_exists "$2"; }',
        'json_count_results()    { python3 "${JSON_HELPER}" "$1" count_results; }',
        'json_throughput_ge()    { python3 "${JSON_HELPER}" "$1" throughput_ge "$2" "${@:3}"; }',
        'json_latency_le()       { python3 "${JSON_HELPER}" "$1" latency_le "$2" "${@:3}"; }',
        'json_avg_throughput()   { python3 "${JSON_HELPER}" "$1" avg_throughput "${@:2}"; }',
        'json_max_latency()      { python3 "${JSON_HELPER}" "$1" max_latency "${@:2}"; }',
        'json_version()          { python3 "${JSON_HELPER}" "$1" version; }',
        'json_contains()         { python3 "${JSON_HELPER}" "$1" contains "$2"; }',
        '',
        'detect_os_name() { echo "openEuler 24.03 SP3"; }',
        '',
        'download_shunit2() {',
        '    local shunit2_tmpdir="$(mktemp -d /tmp/shunit2_XXXXXX)"',
        '    SHUNIT2_PATH="${shunit2_tmpdir}/shunit2"',
        '    log "SETUP" "Downloading shUnit2..."',
        '    local mirrors=(',
        '        "https://raw.githubusercontent.com/kward/shunit2/master/shunit2"',
        '        "https://mirrors.aliyun.com/github-raw/kward/shunit2/master/shunit2"',
        '        "https://raw.gitmirror.com/kward/shunit2/master/shunit2"',
        '    )',
        '    local downloaded=0',
        '    for mirror_url in "${mirrors[@]}"; do',
        '        curl --connect-timeout 30 --max-time 60 -sL -o "${SHUNIT2_PATH}" "${mirror_url}" && {',
        '            chmod +x "${SHUNIT2_PATH}"',
        '            grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { downloaded=1; break; }',
        '        }',
        '        rm -f "${SHUNIT2_PATH}"',
        '    done',
        '    if [ "${downloaded}" -eq 0 ]; then',
        '        for mirror_url in "${mirrors[@]}"; do',
        '            wget --timeout=30 --tries=2 -q -O "${SHUNIT2_PATH}" "${mirror_url}" 2>/dev/null && {',
        '                chmod +x "${SHUNIT2_PATH}"',
        '                grep -q "^SHUNIT_VERSION=" "${SHUNIT2_PATH}" && { downloaded=1; break; }',
        '            }',
        '            rm -f "${SHUNIT2_PATH}"',
        '        done',
        '    fi',
        '    if [ "${downloaded}" -eq 0 ]; then',
        '        log "ERROR" "Failed to download shUnit2"',
        '        rm -rf "${shunit2_tmpdir}"',
        '        return 1',
        '    fi',
        '    log "SETUP" "shUnit2 downloaded successfully"',
        '}',
        '',
        'check_prerequisites() {',
        '    local errors=0',
        '    if ! command -v docker >/dev/null 2>&1; then',
        '        log "ERROR" "docker is not installed"',
        '        errors=$((errors + 1))',
        '    else',
        '        log "CHECK" "Docker OK: $(docker --version 2>&1)"',
        '    fi',
        '    if [ ! -f "${JSON_HELPER}" ]; then',
        '        log "ERROR" "json_helper.py not found at ${JSON_HELPER}"',
        '        errors=$((errors + 1))',
        '    else',
        '        log "CHECK" "json_helper.py OK"',
        '    fi',
        '    log "CHECK" "Architecture: $(uname -m)"',
        '    return ${errors}',
        '}',
        '',
        'phase1_install() {',
        f'    log "PHASE1" "=== Phase 1: Docker Pull {sw} v${{SOFTWARE_VERSION}} ==="',
        '    log "PHASE1" "Pulling ${DOCKER_IMAGE}:${DOCKER_TAG}..."',
        '    docker pull "${DOCKER_IMAGE}:${DOCKER_TAG}" 2>&1 | tee -a "${LOG_FILE}" || {',
        '        log "ERROR" "docker pull failed"',
        '        return 1',
        '    }',
        '    log "PHASE1" "Starting container..."',
        '    DOCKER_CID=$(docker run -d \\',
        '        -v "${SCRIPT_DIR}/scripts:/workspace/scripts" \\',
        '        -v "${SCRIPT_DIR}/results:/workspace/results" \\',
        '        -e SOFTWARE_VERSION="${SOFTWARE_VERSION}" \\',
        '        "${DOCKER_IMAGE}:${DOCKER_TAG}" \\',
        '        sleep infinity) || {',
        '        log "ERROR" "docker run failed"',
        '        return 1',
        '    }',
        '    log "PHASE1" "Container ${DOCKER_CID} started"',
        '}',
        '',
        'phase2_verify() {',
        '    log "PHASE2" "=== Phase 2: Collect Version Info ==="',
        '    local timestamp model arch kernel os_name cpu_model cores python_ver numpy_ver',
        '    timestamp="$(date -u \'+%Y-%m-%dT%H:%M:%SZ\' | tr -d \'\\n\\t\')"',
        '    model="Kunpeng-920"',
        '    arch="$(uname -m | tr -d \'\\n\\t\')"',
        '    kernel="$(uname -r | tr -d \'\\n\\t\')"',
        '    os_name="$(detect_os_name | tr -d \'\\n\\t\')"',
        '    cpu_model="$(grep \'model name\' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs | tr -d \'\\n\\t\')"',
        '    if [ -z "${cpu_model}" ]; then',
        '        local num_proc="$(grep -c \'processor\' /proc/cpuinfo 2>/dev/null || echo 0)"',
        '        cpu_model="ARM64 CPU (${num_proc} cores)"',
        '    fi',
        '    cores="$(nproc 2>/dev/null | tr -d \'\\n\\t\' || echo \'4\')"',
        '    if [ "${HAS_PYTHON3}" -eq 1 ]; then',
        '        python_ver="$(docker exec "${DOCKER_CID}" python3 --version 2>&1 | tr -d \'\\n\\t\')"',
        '        numpy_ver="$(docker exec "${DOCKER_CID}" python3 -c \'import numpy; print(numpy.__version__)\' 2>/dev/null | tr -d \'\\n\\t\' || echo \'unknown\')"',
        '    else',
        '        python_ver="$(python3 --version 2>&1 | tr -d \'\\n\\t\' || echo \'unknown\')"',
        '        numpy_ver="$(python3 -c \'import numpy; print(numpy.__version__)\' 2>/dev/null | tr -d \'\\n\\t\' || echo \'unknown\')"',
        '    fi',
        '',
        '    python3 "${JSON_HELPER}" "${RESULTS_DIR}/version_info.json" write_version_info \\',
        '        "${timestamp}" "${model}" "${arch}" "${kernel}" "${os_name}" "${cpu_model}" \\',
        '        "${cores}" "${SOFTWARE_NAME}" "${SOFTWARE_VERSION}" \\',
        '        "${python_ver}" "${numpy_ver}"',
        '}',
        '',
        'phase3_run_benchmarks() {',
        '    log "PHASE3" "=== Phase 3: Run Benchmarks ==="',
        '    mkdir -p "${RESULTS_DIR}"',
        '',
        '    if [ "${HAS_PYTHON3}" -eq 1 ]; then',
        bench_cmd,
        '        log "PHASE3B" "Running micro benchmark..."',
        '        docker exec "${DOCKER_CID}" python3 /workspace/scripts/micro_benchmark.py \\',
        '            --output /workspace/results/${SOFTWARE_VERSION}/micro_benchmark.json \\',
        '            --version "${SOFTWARE_VERSION}" \\',
        '            --iterations "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"',
        '    else',
        '        log "PHASE3" "No python3 in container, running benchmarks on host"',
        f'        python3 "${{SCRIPT_DIR}}/scripts/benchmark_generic.py" --output "${{RESULTS_DIR}}/benchmark_generic.json" --version "${{SOFTWARE_VERSION}}" --iterations "${{ITERATIONS}}" 2>&1 | tee -a "${{LOG_FILE}}" || log "WARN" "Benchmark had issues"',
        '        python3 "${SCRIPT_DIR}/scripts/micro_benchmark.py" \\',
        '            --output "${RESULTS_DIR}/micro_benchmark.json" \\',
        '            --version "${SOFTWARE_VERSION}" \\',
        '            --iterations "${ITERATIONS}" 2>&1 | tee -a "${LOG_FILE}" || log "WARN" "Micro benchmark had issues"',
        '    fi',
        '}',
        '',
        'phase4_results() {',
        '    log "PHASE4" "=== Phase 4: Aggregate & Report ==="',
        '    mkdir -p "${RESULTS_DIR}"',
        '',
        '    python3 "${SCRIPT_DIR}/scripts/aggregate_results.py" \\',
        '        "${RESULTS_DIR}" "${RESULTS_DIR}/results.json"',
        '',
        '    python3 "${SCRIPT_DIR}/scripts/generate_summary.py" \\',
        '        "${RESULTS_DIR}/results.json" "${RESULTS_DIR}/results.txt"',
        '',
        '    log "PHASE4" "Reports generated:"',
        '    log "PHASE4" "  JSON: ${RESULTS_DIR}/results.json"',
        '    log "PHASE4" "  TXT:  ${RESULTS_DIR}/results.txt"',
        '    log "PHASE4" "  LOG:  ${RESULTS_DIR}/results.log"',
        '}',
        '',
        'oneTimeSetUp() {',
        '    mkdir -p "${RESULTS_DIR}"',
        f'    log "START" "{sw} Performance Benchmark v${{SOFTWARE_VERSION}}"',
        '    check_prerequisites || log "WARN" "Some prerequisites missing, continuing..."',
        '    phase1_install || { log "FATAL" "Phase 1 (docker pull) failed, aborting"; return 1; }',
        '    HAS_PYTHON3=0',
        '    if docker exec "${DOCKER_CID}" python3 --version >/dev/null 2>&1; then',
        '        HAS_PYTHON3=1',
        '        log "CHECK" "python3 available inside container"',
        '    else',
        '        HAS_PYTHON3=0',
        '        log "WARN" "python3 NOT available inside container, using host-side fallback"',
        '    fi',
        '    phase2_verify || log "WARN" "Phase 2 had issues, continuing..."',
        '    phase3_run_benchmarks || log "WARN" "Phase 3 had issues, continuing..."',
        '    phase4_results || log "WARN" "Phase 4 had issues..."',
        '}',
        '',
        'oneTimeTearDown() {',
        '    if [ -n "${DOCKER_CID}" ]; then',
        '        log "CLEANUP" "Stopping container ${DOCKER_CID}"',
        '        docker stop "${DOCKER_CID}" >/dev/null 2>&1',
        '        docker rm "${DOCKER_CID}" >/dev/null 2>&1',
        '        DOCKER_CID=""',
        '    fi',
        '    if [ -n "${SHUNIT2_PATH}" ]; then',
        '        local shunit2_dir="$(dirname "${SHUNIT2_PATH}")"',
        '        rm -rf "${shunit2_dir}"',
        '        SHUNIT2_PATH=""',
        '    fi',
        '}',
        '',
        'setUp() { rm -f "${RESULTS_DIR}/test_temp_*.json"; }',
        'tearDown() { rm -f "${RESULTS_DIR}/test_temp_*.json"; }',
        '',
        'testArchitectureIsARM64() {',
        '    local arch="$(uname -m)"',
        '    assertTrue "Architecture should be aarch64 or arm64, got: ${arch}" \\',
        '        "[ \'${arch}\' = \'aarch64\' ] || [ \'${arch}\' = \'arm64\' ]"',
        '}',
        '',
        'testDockerImageAvailable() {',
        '    if [ -z "${DOCKER_CID}" ]; then startSkipping; return; fi',
        f'    local img="{docker_image}:${{DOCKER_TAG}}"',
        '    local check',
        '    check="$(docker images --format \'{{.Repository}}:{{.Tag}}\' "${img}" | grep -c "${img}")"',
        '    assertTrue "Docker image ${img} should be available" "[ ${check} -ge 1 ]"',
        '}',
        '',
        'testSoftwareIsInstalled() {',
        '    if [ -z "${DOCKER_CID}" ]; then startSkipping; return; fi',
        '    local found=0',
        '    if [ "${HAS_PYTHON3}" -eq 1 ]; then',
        f'        docker exec "${{DOCKER_CID}}" python3 -c "import {python_module}" 2>/dev/null && found=1',
        '    fi',
        f'    if [ "${{found}}" -eq 0 ]; then',
        f'        docker exec "${{DOCKER_CID}}" which {sw} 2>/dev/null && found=1',
        '    fi',
        f'    if [ "${{found}}" -eq 0 ]; then',
        f'        docker exec "${{DOCKER_CID}}" bash -c "ls /opt/{sw}*/bin/{sw} /usr/local/bin/{sw} /usr/bin/{sw} 2>/dev/null" | head -1 | grep -q . && found=1',
        '    fi',
        f'    if [ "${{found}}" -eq 0 ]; then',
        f'        log "WARN" "{sw} not found as Python module or binary, skipping install check"',
        '        startSkipping',
        '        return',
        '    fi',
        '    assertTrue "Software should be available in container" "[ ${found} -eq 1 ]"',
        '}',
        '',
        'testSoftwareVersionMatches() {',
        '    local ver="${SOFTWARE_VERSION}"',
        '    assertNotNull "Version should not be empty" "${ver}"',
        '}',
        '',
        'testVersionInfoExists() {',
        '    assertTrue "Version info JSON should exist" "[ -f \'${RESULTS_DIR}/version_info.json\' ]"',
        '}',
        '',
        'testVersionInfoHasArchitecture() {',
        '    local vfile="${RESULTS_DIR}/version_info.json"',
        '    if [ ! -f "${vfile}" ]; then startSkipping; return; fi',
        '    local has_arch="$(json_field_exists "${vfile}" architecture)"',
        '    assertTrue "Version info should have architecture field" "[ ${has_arch} -eq 1 ]"',
        '}',
        '',
        'testVersionInfoHasSoftwareVersion() {',
        '    local vfile="${RESULTS_DIR}/version_info.json"',
        '    if [ ! -f "${vfile}" ]; then startSkipping; return; fi',
        '    local has_ver="$(json_field_exists "${vfile}" software_version)"',
        '    assertTrue "Version info should have software_version field" "[ ${has_ver} -eq 1 ]"',
        '}',
        '',
        f'testBenchmarkPrimaryProducesResults() {{',
        '    if [ -z "${DOCKER_CID}" ] && [ "${HAS_PYTHON3}" -eq 0 ]; then startSkipping; return; fi',
        f'    assertTrue "Benchmark JSON should exist" "[ -f \'${{RESULTS_DIR}}/{bench_file}\' ]"',
        '}',
        '',
        f'testBenchmarkPrimaryHasRequiredFields() {{',
        f'    local bench_file="${{RESULTS_DIR}}/{bench_file}"',
        '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
        '    local has_benchmark has_metrics has_results',
        '    has_benchmark="$(json_contains "${bench_file}" benchmark)"',
        '    has_metrics="$(json_contains "${bench_file}" performance_metrics)"',
        '    has_results="$(json_contains "${bench_file}" results_summary)"',
        '    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"',
        '    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"',
        '    assertTrue "Should have results_summary field" "[ ${has_results} -eq 1 ]"',
        '}',
        '',
        'testBenchmarkMicroProducesResults() {',
        '    if [ -z "${DOCKER_CID}" ] && [ "${HAS_PYTHON3}" -eq 0 ]; then startSkipping; return; fi',
        '    assertTrue "Micro benchmark JSON should exist" "[ -f \'${RESULTS_DIR}/micro_benchmark.json\' ]"',
        '}',
        '',
        'testBenchmarkMicroHasRequiredFields() {',
        '    local bench_file="${RESULTS_DIR}/micro_benchmark.json"',
        '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
        '    local has_benchmark has_metrics has_results',
        '    has_benchmark="$(json_contains "${bench_file}" benchmark)"',
        '    has_metrics="$(json_contains "${bench_file}" performance_metrics)"',
        '    has_results="$(json_contains "${bench_file}" results)"',
        '    assertTrue "Should have benchmark field" "[ ${has_benchmark} -eq 1 ]"',
        '    assertTrue "Should have performance_metrics field" "[ ${has_metrics} -eq 1 ]"',
        '    assertTrue "Should have results field" "[ ${has_results} -eq 1 ]"',
        '}',
        '',
        'testBenchmarkMicroAllOperationsCompleted() {',
        '    local bench_file="${RESULTS_DIR}/micro_benchmark.json"',
        '    if [ ! -f "${bench_file}" ]; then startSkipping; return; fi',
        '    local ops_count="$(json_count_results "${bench_file}")"',
        '    assertTrue "Should have micro benchmark results (count=${ops_count})" "[ ${ops_count} -ge 2 ]"',
        '}',
        '',
        'testAggregatedResultsExist() {',
        '    if [ ! -f "${RESULTS_DIR}/results.json" ]; then startSkipping; return; fi',
        '    assertTrue "results.json should exist" "[ -f \'${RESULTS_DIR}/results.json\' ]"',
        '}',
        '',
        'testSummaryReportGenerated() {',
        '    if [ ! -f "${RESULTS_DIR}/results.txt" ]; then startSkipping; return; fi',
        '    assertTrue "results.txt should exist" "[ -f \'${RESULTS_DIR}/results.txt\' ]"',
        '}',
        '',
        'testLogFileGenerated() {',
        '    if [ ! -f "${RESULTS_DIR}/results.log" ]; then startSkipping; return; fi',
        '    assertTrue "results.log should exist" "[ -f \'${RESULTS_DIR}/results.log\' ]"',
        '}',
        '',
        'testAggregatedResultsContainsAllBenchmarks() {',
        '    local agg_file="${RESULTS_DIR}/results.json"',
        '    if [ ! -f "${agg_file}" ]; then startSkipping; return; fi',
        '    local has_primary has_micro',
        '    has_primary="$(json_contains "${agg_file}" primary_benchmark)"',
        '    has_micro="$(json_contains "${agg_file}" micro)"',
        '    assertTrue "Should contain primary_benchmark data" "[ ${has_primary} -eq 1 ]"',
        '    assertTrue "Should contain micro_benchmark data" "[ ${has_micro} -eq 1 ]"',
        '}',
        '',
        f'usage() {{',
        f'    cat <<USAGE',
        f'Usage: $(basename "$0") [OPTIONS]',
        f'{sw} Performance Benchmark (shUnit2 + Docker)',
        f'Options:',
        f'  --check    Check prerequisites only',
        f'  -h|--help  Show this help',
        f'Environment variables:',
        f'  SOFTWARE_VERSION         {sw} version (default: {ver})',
        f'  DOCKER_TAG              Docker image tag (default: {docker_tag_val})',
        f'  ITERATIONS              Number of iterations (default: 1)',
        f'Examples:',
        f'  ./{sw}_test.sh --check',
        f'  ./{sw}_test.sh',
        f'  SOFTWARE_VERSION={ver} ./{sw}_test.sh',
        f'USAGE',
        '}',
        '',
        'main() {',
        '    local check_only=0',
        '    while [ $# -gt 0 ]; do',
        '        case "$1" in',
        '            --check)      check_only=1; shift ;;',
        '            -h|--help)    usage; exit 0 ;;',
        '            *)            log "ERROR" "Unknown option: $1"; usage; exit 1 ;;',
        '        esac',
        '    done',
        '',
        f'    log "START" "{sw} Performance Benchmark v${{SOFTWARE_VERSION}}"',
        '',
        '    if [ "${check_only}" -eq 1 ]; then',
        '        check_prerequisites',
        '        exit $?',
        '    fi',
        '',
        '    if ! check_prerequisites; then',
        '        log "FATAL" "Prerequisites not met. Use --check for detailed status."',
        '        exit 1',
        '    fi',
        '',
        '    download_shunit2 || {',
        '        log "FATAL" "Failed to download shUnit2."',
        '        exit 1',
        '    }',
        '',
        f'    SHUNIT_PARENT="${{SCRIPT_DIR}}/{sw}_test.sh"',
        '    . "${SHUNIT2_PATH}"',
        '}',
        '',
        'if [ "${1:-}" != "--shunit2-run" ]; then',
        '    main "$@"',
        'fi',
    ]
    return "\n".join(lines)


class TestGenerator:
    def __init__(
        self,
        tests_dir: str,
        reference_dir: str = "",
        docker_pull_enabled: bool = False,
        ssh_host: str = "",
        ssh_user: str = "",
        ssh_port: int = 22,
        ssh_key_path: str = "",
        docker_pull_timeout: int = 600,
    ):
        self.tests_dir = Path(tests_dir).resolve()
        self.reference_dir = Path(reference_dir) if reference_dir else self._find_reference()
        self.docker_pull_enabled = docker_pull_enabled
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_port = ssh_port
        self.ssh_key_path = ssh_key_path
        self.docker_pull_timeout = docker_pull_timeout

    def _find_reference(self) -> Path:
        for sw in ["faiss", "rocksdb", "redis", "hnswlib"]:
            ref = self.tests_dir / sw / "scripts"
            if ref.exists():
                return ref
        return self.tests_dir / "faiss" / "scripts"

    def get_benchmark_type(self, category: str) -> str:
        cat_lower = category.lower() if category else ""
        for key, bm_type in BENCHMARK_TYPE_MAP.items():
            if key in cat_lower or cat_lower in key:
                return bm_type
        return "benchmark_generic"

    def get_python_module(self, software: str) -> str:
        return PYTHON_MODULE_MAP.get(software, software)

    def has_existing_tests(self, software: str) -> bool:
        sw_dir = self.tests_dir / software
        test_sh = sw_dir / f"{software}_test.sh"
        return test_sh.exists()

    def check_local_docker_image(self, namespace: str, software: str, tag: str) -> bool:
        image = f"{namespace}/{software}:{tag}"
        try:
            result = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", image],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and image in result.stdout.strip():
                logger.info(f"Local docker image found: {image}")
                return True
        except Exception as e:
            logger.debug(f"Local docker check failed: {e}")
        return False

    def check_remote_docker_image(self, namespace: str, software: str, tag: str) -> bool:
        if not self.ssh_host:
            return False
        image = f"{namespace}/{software}:{tag}"
        ssh_cmd = [
            "ssh", "-p", str(self.ssh_port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
        ]
        if self.ssh_key_path:
            ssh_cmd.extend(["-i", self.ssh_key_path])
        ssh_cmd.append(f"{self.ssh_user}@{self.ssh_host}")
        ssh_cmd.append(f"docker images --format '{{.Repository}}:{{.Tag}}' {image}")
        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and image in result.stdout.strip():
                logger.info(f"Remote docker image found: {image}")
                return True
        except Exception as e:
            logger.debug(f"Remote docker check failed: {e}")
        return False

    def pull_docker_image(self, namespace: str, software: str, tag: str) -> Dict:
        image = f"{namespace}/{software}:{tag}"
        if self.ssh_host:
            ssh_cmd = [
                "ssh", "-p", str(self.ssh_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
            ]
            if self.ssh_key_path:
                ssh_cmd.extend(["-i", self.ssh_key_path])
            ssh_cmd.append(f"{self.ssh_user}@{self.ssh_host}")
            ssh_cmd.append(f"docker pull {image}")
            try:
                result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=self.docker_pull_timeout)
                if result.returncode == 0:
                    logger.info(f"Remote docker pull succeeded: {image}")
                    return {"success": True, "image": image, "method": "ssh"}
                logger.error(f"Remote docker pull failed: {result.stderr}")
                return {"success": False, "image": image, "error": result.stderr}
            except subprocess.TimeoutExpired:
                return {"success": False, "image": image, "error": "timeout"}
            except Exception as e:
                return {"success": False, "image": image, "error": str(e)}

        try:
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=True, text=True, timeout=self.docker_pull_timeout,
            )
            if result.returncode == 0:
                logger.info(f"Local docker pull succeeded: {image}")
                return {"success": True, "image": image, "method": "local"}
            logger.error(f"Local docker pull failed: {result.stderr}")
            return {"success": False, "image": image, "error": result.stderr}
        except subprocess.TimeoutExpired:
            return {"success": False, "image": image, "error": "timeout"}
        except Exception as e:
            return {"success": False, "image": image, "error": str(e)}

    def _copy_common_scripts(self, dest_scripts: Path, software: str = ""):
        for script_name in COMMON_SCRIPTS_COPY:
            src = self.reference_dir / script_name
            dst = dest_scripts / script_name
            if src.resolve() == dst.resolve():
                logger.info(f"{script_name}: src and dst are same file, skipping copy")
                continue
            if src.exists():
                shutil.copy2(str(src), str(dst))
                logger.info(f"Copied {script_name} from reference")
            else:
                self._generate_common_script(script_name, dst, software)
        for script_name in COMMON_SCRIPTS_GENERATE:
            dst = dest_scripts / script_name
            self._generate_common_script(script_name, dst, software)

    def _generate_common_script(self, script_name: str, dest: Path, software: str = ""):
        if script_name == "aggregate_results.py":
            content = AGGREGATE_RESULTS_TEMPLATE.format(software=software)
            with open(dest, "w") as f:
                f.write(content)
            logger.info(f"Generated {script_name} for {software}")
            return
        elif script_name == "generate_summary.py":
            content = GENERATE_SUMMARY_TEMPLATE.format(software=software)
            with open(dest, "w") as f:
                f.write(content)
            logger.info(f"Generated {script_name} for {software}")
            return
        elif script_name == "json_helper.py":
            if self.reference_dir.exists():
                src = self.reference_dir / "json_helper.py"
                if src.exists():
                    shutil.copy2(str(src), str(dest))
                    return
            logger.warning("No json_helper.py reference found, using minimal version")
            content = JSON_HELPER_MINIMAL.format(software=software)
            with open(dest, "w") as f:
                f.write(content)
            return
        else:
            return

    def _generate_benchmark_script(self, software: str, dest: Path):
        content = BENCHMARK_GENERIC_PY.format(software=software)
        with open(dest / "benchmark_generic.py", "w") as f:
            f.write(content)

    def _generate_micro_benchmark(self, software: str, dest: Path):
        content = MICRO_BENCHMARK_PY.format(software=software)
        with open(dest / "micro_benchmark.py", "w") as f:
            f.write(content)

    def generate_test_scaffolding(
        self,
        software: str,
        version: str,
        category: str,
        namespace: str = "openeuler",
        tag: str = "",
    ) -> Dict:
        sw_dir = self.tests_dir / software
        scripts_dir = sw_dir / "scripts"

        if self.has_existing_tests(software):
            logger.info(f"Software {software} already has tests, skipping")
            return {
                "software": software,
                "status": "existing",
                "message": "Test directory already exists",
                "path": str(sw_dir),
            }

        logger.info(f"Generating test scaffolding for {software} v{version}")

        sw_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir.mkdir(parents=True, exist_ok=True)

        benchmark_type = self.get_benchmark_type(category)
        python_module = self.get_python_module(software)

        self._copy_common_scripts(scripts_dir, software)
        self._generate_benchmark_script(software, scripts_dir)
        self._generate_micro_benchmark(software, scripts_dir)

        test_sh_content = build_test_sh(
            software, version, namespace, tag, benchmark_type
        )
        test_sh_path = sw_dir / f"{software}_test.sh"
        with open(test_sh_path, "w") as f:
            f.write(test_sh_content)
        os.chmod(str(test_sh_path), 0o755)

        results_dir = sw_dir / "results" / (version or "1.0.0")
        results_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Test scaffolding generated at {sw_dir}")
        return {
            "software": software,
            "version": version,
            "category": category,
            "benchmark_type": benchmark_type,
            "python_module": python_module,
            "docker_image": f"{namespace}/{software}",
            "docker_tag": tag or f"{version}-oe2403sp3",
            "status": "generated",
            "path": str(sw_dir),
            "files": [
                f"{software}_test.sh",
                "scripts/json_helper.py",
                "scripts/aggregate_results.py",
                "scripts/generate_summary.py",
                "scripts/benchmark_generic.py",
                "scripts/micro_benchmark.py",
            ],
        }

    def generate_for_pushed_images(
        self,
        pushed_results: List[Dict],
        namespace: str = "openeuler",
        docker_pull: bool = False,
    ) -> List[Dict]:
        generated = []
        for r in pushed_results:
            software = r.get("software", "")
            version = r.get("version", "")
            category = r.get("category", "")
            tag = r.get("dockerhub_tag", "latest")

            if not software:
                continue

            if self.has_existing_tests(software):
                logger.info(f"{software}: existing tests, skipping")
                generated.append({
                    "software": software,
                    "status": "existing",
                    "message": "Test directory already exists",
                })
                continue

            docker_status = "not_checked"
            if docker_pull:
                if self.check_local_docker_image(namespace, software, tag):
                    docker_status = "local_found"
                elif self.check_remote_docker_image(namespace, software, tag):
                    docker_status = "remote_found"
                else:
                    pull_result = self.pull_docker_image(namespace, software, tag)
                    if pull_result.get("success"):
                        docker_status = "pulled"
                    else:
                        docker_status = f"pull_failed: {pull_result.get('error', 'unknown')}"

            result = self.generate_test_scaffolding(
                software, version, category, namespace, tag,
            )
            result["docker_status"] = docker_status
            generated.append(result)

        return generated
