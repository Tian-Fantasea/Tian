import subprocess
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DockerVerifier:
    def __init__(
        self,
        enabled: bool = False,
        ssh_host: str = "",
        ssh_user: str = "",
        ssh_port: int = 22,
        ssh_key_path: str = "",
        docker_pull_timeout: int = 600,
    ):
        self.enabled = enabled
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_port = ssh_port
        self.ssh_key_path = ssh_key_path
        self.docker_pull_timeout = docker_pull_timeout

    def _build_ssh_cmd(self, remote_cmd: str) -> list:
        cmd = [
            "ssh",
            "-p", str(self.ssh_port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
        ]
        if self.ssh_key_path:
            cmd.extend(["-i", self.ssh_key_path])
        cmd.append(f"{self.ssh_user}@{self.ssh_host}")
        cmd.append(remote_cmd)
        return cmd

    def _run_ssh(self, remote_cmd: str, timeout: int = None) -> Dict:
        if timeout is None:
            timeout = self.docker_pull_timeout + 60
        cmd = self._build_ssh_cmd(remote_cmd)
        logger.info(f"Running SSH command: {remote_cmd}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            logger.error(f"SSH command timed out: {remote_cmd}")
            return {"success": False, "stderr": "timeout", "returncode": -1}
        except Exception as e:
            logger.error(f"SSH command failed: {e}")
            return {"success": False, "stderr": str(e), "returncode": -1}

    def verify_pull(self, namespace: str, software: str, tag: str) -> Dict:
        if not self.enabled:
            logger.info("Docker verification disabled, skipping")
            return {
                "verified": False,
                "reason": "verification_disabled",
                "software": software,
                "tag": tag,
            }

        image = f"{namespace}/{software}:{tag}"
        logger.info(f"Verifying docker pull for: {image}")

        pull_result = self._run_ssh(f"docker pull {image}")
        if not pull_result["success"]:
            return {
                "verified": False,
                "reason": "pull_failed",
                "software": software,
                "tag": tag,
                "image": image,
                "error": pull_result.get("stderr", ""),
            }

        inspect_cmd = f"docker inspect --format='{{{{.RepoDigests}}}}' {image}"
        inspect_result = self._run_ssh(inspect_cmd, timeout=30)
        digest = ""
        if inspect_result["success"]:
            digest = inspect_result["stdout"].strip()

        size_cmd = f"docker inspect --format='{{{{.Size}}}}' {image}"
        size_result = self._run_ssh(size_cmd, timeout=30)
        size = ""
        if size_result["success"]:
            size = size_result["stdout"].strip()

        rm_cmd = f"docker rmi {image}"
        self._run_ssh(rm_cmd, timeout=30)

        return {
            "verified": True,
            "software": software,
            "tag": tag,
            "image": image,
            "digest": digest,
            "size": size,
        }

    def verify_local_pull(self, namespace: str, software: str, tag: str) -> Dict:
        image = f"{namespace}/{software}:{tag}"
        logger.info(f"Local docker pull: {image}")
        try:
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=True, text=True, timeout=self.docker_pull_timeout,
            )
            if result.returncode != 0:
                return {
                    "verified": False,
                    "reason": "pull_failed",
                    "image": image,
                    "error": result.stderr,
                }
            inspect = subprocess.run(
                ["docker", "inspect", "--format", "{{.RepoDigests}}", image],
                capture_output=True, text=True, timeout=30,
            )
            digest = inspect.stdout.strip() if inspect.returncode == 0 else ""
            subprocess.run(["docker", "rmi", image], capture_output=True, timeout=30)
            return {"verified": True, "image": image, "digest": digest}
        except subprocess.TimeoutExpired:
            return {"verified": False, "reason": "timeout", "image": image}
        except Exception as e:
            return {"verified": False, "reason": str(e), "image": image}
