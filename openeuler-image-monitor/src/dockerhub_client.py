import re
import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

OS_VERSION_TAG_MAP = {
    "24.03-lts-sp3": "oe2403sp3",
    "24.03-lts-sp1": "oe2403sp1",
    "24.03-lts-sp2": "oe2403sp2",
    "24.03-lts": "oe2403lts",
    "22.03-lts-sp3": "oe2203sp3",
    "22.03-lts-sp1": "oe2203sp1",
    "22.03-lts-sp2": "oe2203sp2",
    "22.03-lts": "oe2203lts",
    "20.03-lts-sp3": "oe2003sp3",
    "20.03-lts-sp1": "oe2003sp1",
    "20.03-lts": "oe2003lts",
}


def os_version_to_tag_suffix(os_version: str) -> str:
    if os_version in OS_VERSION_TAG_MAP:
        return OS_VERSION_TAG_MAP[os_version]
    cleaned = re.sub(r"[.\-]", "", os_version)
    return f"oe{cleaned}"


class DockerHubClient:
    def __init__(self, base_url: str, namespace: str):
        self.base_url = base_url.rstrip("/")
        self.namespace = namespace
        self.session = requests.Session()

    def check_repository_exists(self, software_name: str) -> Optional[Dict]:
        url = f"{self.base_url}/repositories/{self.namespace}/{software_name}/"
        logger.info(f"Checking DockerHub repo: {self.namespace}/{software_name}")
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                logger.info(f"DockerHub repo not found: {self.namespace}/{software_name}")
                return None
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"DockerHub repo check error: {e}")
        return None

    def get_tags(self, software_name: str, page_size: int = 50) -> List[Dict]:
        url = f"{self.base_url}/repositories/{self.namespace}/{software_name}/tags/"
        params = {"page_size": page_size}
        logger.info(f"Fetching tags for {self.namespace}/{software_name}")
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 404:
                logger.info(f"No tags found (repo doesn't exist): {self.namespace}/{software_name}")
                return []
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except requests.RequestException as e:
            logger.error(f"DockerHub tags fetch error: {e}")
            return []

    def check_image_pushed(self, software_name: str, version: str, os_version: str) -> Dict:
        repo_info = self.check_repository_exists(software_name)
        if not repo_info:
            return {
                "pushed": False,
                "reason": "repo_not_found",
                "software": software_name,
                "version": version,
                "os_version": os_version,
            }

        tags = self.get_tags(software_name)
        if not tags:
            return {
                "pushed": False,
                "reason": "no_tags",
                "software": software_name,
                "version": version,
                "os_version": os_version,
            }

        if os_version:
            expected_tag = f"{version}-{os_version_to_tag_suffix(os_version)}"
            tag_names = [t["name"] for t in tags]
            if expected_tag in tag_names:
                return {
                    "pushed": True,
                    "tag": expected_tag,
                    "software": software_name,
                    "version": version,
                    "os_version": os_version,
                }
            if "latest" in tag_names:
                return {
                    "pushed": True,
                    "tag": "latest",
                    "software": software_name,
                    "version": version,
                    "os_version": os_version,
                    "note": "only_latest_found",
                }

            normalized_names = [n.lower().replace("-", "").replace("+", "") for n in tag_names]
            normalized_expected = expected_tag.lower().replace("-", "").replace("+", "")
            for orig, norm in zip(tag_names, normalized_names):
                if norm == normalized_expected:
                    return {
                        "pushed": True,
                        "tag": orig,
                        "software": software_name,
                        "version": version,
                        "os_version": os_version,
                    }
            return {
                "pushed": False,
                "reason": "tag_not_found",
                "expected_tag": expected_tag,
                "available_tags": tag_names,
                "software": software_name,
                "version": version,
                "os_version": os_version,
            }

        return {
            "pushed": True,
            "tag": tags[0]["name"],
            "software": software_name,
            "version": version,
            "os_version": os_version,
            "note": "no_os_version_specified",
        }
