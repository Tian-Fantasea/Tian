import subprocess
import os
import logging
import time
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
    def __init__(self, tests_dir: str, timeout: int = 3600):
        self.tests_dir = Path(tests_dir)
        self.timeout = timeout

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
