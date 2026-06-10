#!/usr/bin/env python3
import sys
import os
import subprocess
import json


def main():
    results_dir = sys.argv[1]
    software_version = sys.argv[2]
    venv_path = sys.argv[3]

    timestamp = subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"]).decode().strip()
    arch = subprocess.check_output(["uname", "-m"]).decode().strip()
    kernel = subprocess.check_output(["uname", "-r"]).decode().strip()
    os_name = ""
    try:
        os_name = subprocess.check_output(
            ["bash", "-c", "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2"]
        ).decode().strip()
    except subprocess.CalledProcessError:
        os_name = subprocess.check_output(["uname", "-s"]).decode().strip()
    cpu_model = ""
    try:
        cpu_model = subprocess.check_output(
            ["bash", "-c", "grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs"]
        ).decode().strip()
    except subprocess.CalledProcessError:
        cpu_model = "N/A"
    cores = subprocess.check_output(["nproc"]).decode().strip() if os.path.exists("/proc/cpuinfo") else "4"
    mem_mb = "0"
    try:
        mem_kb = subprocess.check_output(["bash", "-c", "awk '/MemTotal/ {print $2}' /proc/meminfo"]).decode().strip()
        mem_mb = str(int(mem_kb) // 1024)
    except (subprocess.CalledProcessError, ValueError):
        mem_mb = "0"

    python_ver = subprocess.check_output([os.path.join(venv_path, "bin", "python3"), "--version"]).decode().strip()
    ov_ver = ""
    try:
        ov_ver = subprocess.check_output(
            [os.path.join(venv_path, "bin", "python3"), "-c", "import openviking; print(openviking.__version__)"]
        ).decode().strip()
    except subprocess.CalledProcessError:
        ov_ver = "unknown"

    json_helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_helper.py")
    subprocess.run([
        os.path.join(venv_path, "bin", "python3"), json_helper,
        os.path.join(results_dir, "version_info.json"), "write_version_info",
        timestamp, arch, kernel, os_name, cpu_model,
        cores, mem_mb, software_version, "N/A",
        python_ver, venv_path, "10", "64"
    ], check=True)

    print(f"[VERIFY] OpenViking version: {ov_ver}")
    print(f"[VERIFY] Python: {python_ver}")
    print(f"[VERIFY] Architecture: {arch}")
    print(f"[VERIFY] Version info written to {results_dir}/version_info.json")

    try:
        subprocess.check_output(
            [os.path.join(venv_path, "bin", "python3"), "-c",
             "from openviking import server; print('OpenViking server module OK')"],
            timeout=10
        )
        print("[VERIFY] OpenViking server module importable")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"[VERIFY] WARNING: OpenViking server module import issue: {e}")


if __name__ == "__main__":
    main()