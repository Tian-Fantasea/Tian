import subprocess
import os
import logging
import time
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

EXPECTED_RESULT_FILES = [
    "version_info.json",
    "results.json",
    "results.txt",
    "results.log",
]


class TestRunner:
    def __init__(self, tests_dir: str, timeout: int = 3600, docker_check: bool = True):
        self.tests_dir = Path(tests_dir).resolve()
        self.timeout = timeout
        self.docker_check = docker_check

    def _extract_docker_info(self, test_sh_path: Path) -> Dict:
        image = ""
        tag = ""
        content = test_sh_path.read_text()
        m_img = re.search(r'DOCKER_IMAGE="([^"]+)"', content)
        m_tag = re.search(r'DOCKER_TAG="\$\{DOCKER_TAG:-(.+)\}"', content)
        if m_img:
            image = m_img.group(1)
        if m_tag:
            tag = m_tag.group(1)
        return {"image": image, "tag": tag}

    def _check_docker_image_available(self, image: str, tag: str) -> bool:
        if not image or not tag:
            return True
        full_image = f"{image}:{tag}"
        try:
            result = subprocess.run(
                ["docker", "manifest", "inspect", full_image],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                logger.info(f"Docker image {full_image} available on registry")
                return True
            logger.warning(f"Docker image {full_image} NOT available on registry: {result.stderr[:200]}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Docker manifest check timed out for {full_image}")
            return False
        except Exception as e:
            logger.warning(f"Docker manifest check failed for {full_image}: {e}")
            return True

    def has_complete_results(self, software: str, version: str) -> bool:
        version_dir = self.tests_dir / software / "results" / version
        if not version_dir.exists():
            return False
        existing = {f.name for f in version_dir.iterdir() if f.is_file()}
        primary_bench = None
        for f in version_dir.iterdir():
            if f.name.startswith("benchmark_") and f.name.endswith(".json"):
                primary_bench = f.name
                break
        required = set(EXPECTED_RESULT_FILES)
        if primary_bench:
            required.add(primary_bench)
        required.add("micro_benchmark.json")
        return required.issubset(existing)

    def run_test(self, software: str, version: str) -> Dict:
        test_sh = self.tests_dir / software / f"{software}_test.sh"
        if not test_sh.exists():
            logger.error(f"Test script not found: {test_sh}")
            return {
                "software": software,
                "version": version,
                "status": "script_not_found",
                "path": str(test_sh),
            }

        if self.has_complete_results(software, version):
            logger.info(f"{software} v{version} already has complete results, skipping execution")
            return {
                "software": software,
                "version": version,
                "status": "already_completed",
                "message": "All result files present, skipping",
            }

        if self.docker_check:
            docker_info = self._extract_docker_info(test_sh)
            image = docker_info.get("image", "")
            tag = docker_info.get("tag", "")
            if image and tag:
                if not self._check_docker_image_available(image, tag):
                    logger.warning(f"Skipping {software}: Docker image {image}:{tag} not available")
                    return {
                        "software": software,
                        "version": version,
                        "status": "image_not_available",
                        "docker_image": f"{image}:{tag}",
                        "message": f"Docker image {image}:{tag} not available on registry",
                    }

        logger.info(f"Executing {software}_test.sh (version={version}, timeout={self.timeout}s)")

        env = os.environ.copy()
        env["SOFTWARE_VERSION"] = version

        start_time = time.time()
        try:
            result = subprocess.run(
                ["bash", str(test_sh)],
                cwd=str(self.tests_dir / software),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            elapsed = time.time() - start_time

            if result.returncode == 0:
                logger.info(f"{software}_test.sh completed successfully in {elapsed:.1f}s")
            else:
                logger.warning(f"{software}_test.sh exited with code {result.returncode} in {elapsed:.1f}s")
                if result.stderr:
                    logger.warning(f"stderr: {result.stderr[-500:]}")

            completion_status = self._check_results(software, version)

            return {
                "software": software,
                "version": version,
                "status": completion_status,
                "returncode": result.returncode,
                "elapsed_seconds": round(elapsed, 1),
                "stdout_tail": result.stdout[-200:] if result.stdout else "",
                "stderr_tail": result.stderr[-200:] if result.stderr else "",
            }

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            logger.error(f"{software}_test.sh timed out after {elapsed:.1f}s")
            return {
                "software": software,
                "version": version,
                "status": "timeout",
                "elapsed_seconds": round(elapsed, 1),
            }
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"{software}_test.sh failed with exception: {e}")
            return {
                "software": software,
                "version": version,
                "status": "error",
                "error": str(e),
                "elapsed_seconds": round(elapsed, 1),
            }

    def _check_results(self, software: str, version: str) -> str:
        version_dir = self.tests_dir / software / "results" / version
        if not version_dir.exists():
            return "no_results_dir"

        existing = {f.name for f in version_dir.iterdir() if f.is_file()}
        primary_bench = None
        for name in existing:
            if name.startswith("benchmark_") and name.endswith(".json"):
                primary_bench = name
                break

        found = []
        missing = []
        for req in EXPECTED_RESULT_FILES:
            if req in existing:
                found.append(req)
            else:
                missing.append(req)
        if "micro_benchmark.json" in existing:
            found.append("micro_benchmark.json")
        else:
            missing.append("micro_benchmark.json")
        if primary_bench:
            found.append(primary_bench)
        else:
            missing.append("benchmark_*.json")

        if not missing:
            return "completed"
        return f"partial({len(found)}/{len(found) + len(missing)} files, missing: {','.join(missing)})"

    def discover_test_scripts(self) -> List[Dict]:
        discovered = []
        for entry in sorted(self.tests_dir.iterdir()):
            if not entry.is_dir():
                continue
            software = entry.name
            test_sh = entry / f"{software}_test.sh"
            if not test_sh.exists():
                continue
            version = self._detect_version(software)
            discovered.append({"software": software, "version": version})
        return discovered

    def _detect_version(self, software: str) -> str:
        results_base = self.tests_dir / software / "results"
        if results_base.exists():
            version_dirs = sorted(
                [d for d in results_base.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if version_dirs:
                return version_dirs[0].name
        return ""

    def run_all(self, software_list: List[Dict]) -> List[Dict]:
        results = []
        for item in software_list:
            software = item.get("software", "")
            version = item.get("version", "")
            if not software:
                continue
            run_result = self.run_test(software, version)
            results.append(run_result)
        return results
