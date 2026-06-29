import re
import requests
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class GitCodeClient:
    def __init__(self, base_url: str, repo_owner: str, repo_name: str, access_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.access_token = access_token
        self.session = requests.Session()
        if access_token:
            self.session.params["access_token"] = access_token

    def get_merged_prs(self, page: int = 1, per_page: int = 20) -> List[Dict]:
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls"
        params = {"state": "merged", "page": page, "per_page": per_page}
        logger.info(f"Fetching merged PRs: page={page}, per_page={per_page}")
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_merged_prs_since(self, since_iso: str, max_pages: int = 10) -> List[Dict]:
        all_prs = []
        seen_old = False
        for page in range(1, max_pages + 1):
            prs = self.get_merged_prs(page=page, per_page=20)
            if not prs:
                break
            for pr in prs:
                merged_at = pr.get("merged_at", "")
                if merged_at and merged_at >= since_iso:
                    all_prs.append(pr)
                elif merged_at and merged_at < since_iso:
                    seen_old = True
            if seen_old:
                break
        return all_prs

    def get_pr_detail(self, pr_number: int) -> Dict:
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}"
        logger.info(f"Fetching PR detail: #{pr_number}")
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_pr_files(self, pr_number: int) -> List[Dict]:
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}/files"
        logger.info(f"Fetching PR files: #{pr_number}")
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def extract_software_info_from_files(self, pr_number: int) -> List[Dict]:
        files = self.get_pr_files(pr_number)
        results = []

        for f in files:
            filepath = f.get("filename", "")
            if not filepath.endswith("Dockerfile"):
                continue

            info = _parse_dockerfile_path(filepath, pr_number)
            if info:
                results.append(info)

        if not results:
            logger.info(f"No Dockerfile paths found in PR #{pr_number}")
            test_info = _extract_from_test_paths(files, pr_number)
            if test_info:
                results.extend(test_info)

        if not results:
            logger.info(f"PR #{pr_number}: trying body/table parsing")
            pr_detail = self.get_pr_detail(pr_number)
            title = pr_detail.get("title", "")
            body = pr_detail.get("body", "")
            results = _extract_from_title_and_body(title, body, pr_number)

        return results


def _parse_dockerfile_path(filepath: str, pr_number: int) -> Optional[Dict]:
    parts = filepath.split("/")
    if len(parts) < 5 or parts[-1] != "Dockerfile":
        return None

    category = parts[0]
    os_version = parts[-2]
    version = parts[-3]
    software = parts[-4]
    subdir = "/".join(parts[1:-4]) if len(parts) > 5 else ""

    return {
        "software": software,
        "version": version,
        "os_version": os_version,
        "category": category,
        "filepath": filepath,
        "pr_number": pr_number,
        "source": "filepath",
        "subdir": subdir,
    }


def _extract_from_test_paths(files: List[Dict], pr_number: int) -> List[Dict]:
    results = []
    pattern = re.compile(r"^tests/(?P<software>[^/]+)/")
    seen = set()
    for f in files:
        filepath = f.get("filename", "")
        m = pattern.match(filepath)
        if m:
            software = m.group("software")
            if software not in seen:
                seen.add(software)
                version_match = re.search(r"tests/{software}/(?:scripts|results)/(?P<version>[^/]+)/".format(software=software), filepath)
                version = version_match.group("version") if version_match else ""
                results.append({
                    "software": software,
                    "version": version,
                    "os_version": "",
                    "category": "tests",
                    "filepath": filepath,
                    "pr_number": pr_number,
                    "source": "test_path",
                })
    return results


def _extract_from_title_and_body(title: str, body: str, pr_number: int) -> List[Dict]:
    title_patterns = [
        re.compile(r"【自动升级】(?P<software>\S+)\s*容器镜像升级至\s*(?P<version>[^\s版本.]+)", re.IGNORECASE),
        re.compile(r"(?:fix|feat)\s*[:：]\s*(?:【自动升级】)?(?P<software>\S+)\s*(?:容器镜像升级至|performance test scripts and results|)(?P<version>[^\s(,/]+)", re.IGNORECASE),
        re.compile(r"(?P<software>\S+)\s+容器镜像升级至\s+(?P<version>[^\s版本.]+)", re.IGNORECASE),
    ]

    software = ""
    version = ""
    os_version = ""
    source = "title"

    for pat in title_patterns:
        m = pat.search(title)
        if m:
            sw = m.group("software").strip()
            skip_words = {"fix", "feat", "add", "update", "升级", "自动升级", "【自动升级】", "【自动升级】"}
            if sw.lower() in skip_words:
                continue
            software = sw
            version = m.group("version").strip()
            break

    body_os = _extract_os_from_body(body)
    if body_os and not os_version:
        os_version = body_os

    if software and version:
        return [{
            "software": software,
            "version": version,
            "os_version": os_version,
            "category": "",
            "filepath": "",
            "pr_number": pr_number,
            "source": source,
        }]

    body_table = _extract_from_body_table(body, pr_number)
    if body_table:
        return body_table

    return [{
        "software": software or "",
        "version": version or "",
        "os_version": os_version,
        "category": "",
        "filepath": "",
        "pr_number": pr_number,
        "source": "title_fallback",
        "raw_title": title,
    }]


def _extract_os_from_body(body: str) -> str:
    if not body:
        return ""
    patterns = [
        re.compile(r"\|\s*openEuler version\s*\|\s*(\S+)\s*\|"),
        re.compile(r"(\d+\.\d+-lts(?:-sp\d+)?)"),
    ]
    for pat in patterns:
        m = pat.search(body)
        if m:
            return m.group(1).strip()
    return ""


def _extract_from_body_table(body: str, pr_number: int) -> List[Dict]:
    if not body:
        return []
    app_ver_match = re.search(r"\|\s*Application version\s*\|\s*(\S+)\s*\|", body)
    os_ver_match = re.search(r"\|\s*openEuler version\s*\|\s*(\S+)\s*\|", body)
    if app_ver_match:
        return [{
            "software": "",
            "version": app_ver_match.group(1).strip(),
            "os_version": os_ver_match.group(1).strip() if os_ver_match else "",
            "category": "",
            "filepath": "",
            "pr_number": pr_number,
            "source": "body_table",
        }]
    return []
