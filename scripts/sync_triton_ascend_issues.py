#!/usr/bin/env python3
"""
Sync triton-ascend GitHub issues to Google Sheets via Apps Script Web App.

This script:
  1. Fetches all issues (open + closed, excluding PRs) from triton-lang/triton-ascend
  2. Categorizes GitHub labels into status / type groups
  3. Sends issue data via HTTP POST to a Google Apps Script Web App
  4. The Apps Script handles sheet comparison, cell-level updates, and new row insertion

Environment variables:
    APPS_SCRIPT_URL     URL of the deployed Apps Script Web App (required)
    GITHUB_TOKEN        GitHub token for API rate limits (optional)
    SPREADSHEET_ID      Google Sheet ID (default: the tracking sheet)
    SHEET_GID           Worksheet GID (default: 144346032)
"""

import datetime
import json
import os
import re
import sys
import time

import requests

# ==================== Configuration ====================

DEFAULT_SPREADSHEET_ID = "1i_Wlw1-XNeMdE-ELv9s_hgWjWztYUy6hYgckIh4Ov4k"
DEFAULT_SHEET_GID = 144346032
GITHUB_REPO = "triton-lang/triton-ascend"
GITHUB_API_BASE = "https://api.github.com"

STATUS_LABELS = frozenset({
    "triage review", "triaged", "wait-feedback", "resolved",
    "stale", "duplicated", "invalid", "wontfix",
})
TYPE_LABELS = frozenset({
    "feature request", "RFC", "question", "documentation",
    "installation", "performance", "bug", "ssbuffer",
})


# ==================== Utility ====================

def categorize_labels(labels: list[str]) -> tuple[str, str]:
    """Split GitHub labels into status and type categories."""
    status = [l for l in labels if l in STATUS_LABELS]
    type_ = [l for l in labels if l in TYPE_LABELS]
    return ",".join(status), ",".join(type_)


def format_datetime(date_str: str) -> str:
    """Format ISO 8601 to 'YYYY-MM-DD HH:MM:SS'."""
    if not date_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str


# ==================== GitHub API ====================

def _gh_request(url: str, headers: dict, params: dict | None = None) -> requests.Response:
    """Make GitHub API request with retry on rate limit."""
    for _ in range(3):
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset:
                wait = max(int(reset) - int(time.time()) + 2, 1)
                print(f"  Rate limited. Waiting {wait}s...")
                time.sleep(min(wait, 60))
                continue
        return resp
    return resp


def fetch_all_issues(token: str = "") -> list[dict]:
    """Fetch all issues (open + closed, excluding PRs) from triton-ascend."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    issues: list[dict] = []
    page = 1
    while True:
        url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/issues"
        params = {
            "state": "all",
            "per_page": 100,
            "page": page,
            "sort": "created",
            "direction": "desc",
        }
        resp = _gh_request(url, headers, params)
        resp.raise_for_status()
        page_data = resp.json()

        issues.extend(i for i in page_data if "pull_request" not in i)

        if len(page_data) < 100:
            break
        page += 1

    return issues


# ==================== Apps Script Web App ====================

def send_to_apps_script(url: str, payload: dict) -> dict:
    """Send data to Apps Script Web App via HTTP POST."""
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


# ==================== Main ====================

def main():
    apps_script_url = os.environ.get("APPS_SCRIPT_URL")
    if not apps_script_url:
        print("ERROR: APPS_SCRIPT_URL environment variable not set")
        sys.exit(1)

    github_token = os.environ.get("GITHUB_TOKEN", "")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID)
    sheet_gid = int(os.environ.get("SHEET_GID", str(DEFAULT_SHEET_GID)))

    # --- Fetch all issues from GitHub ---
    print("Fetching all issues from GitHub...")
    all_issues = fetch_all_issues(github_token)
    print(f"Found {len(all_issues)} issues (excluding PRs)")

    # --- Build payload for Apps Script ---
    formatted = []
    for issue in all_issues:
        labels = [l["name"] for l in issue["labels"]]
        status_label, type_label = categorize_labels(labels)
        state = issue["state"]
        closed_at = issue.get("closed_at")

        formatted.append({
            "number": issue["number"],
            "title": issue["title"],
            "url": issue["html_url"],
            "state": state,
            "is_closed": "是" if state == "closed" else "否",
            "close_time": format_datetime(closed_at) if closed_at else "",
            "status_label": status_label,
            "type_label": type_label,
            "comments": issue["comments"],
            "updated_at": issue["updated_at"],
            "created_at": issue.get("created_at", ""),
        })

    payload = {
        "mode": "sync",
        "spreadsheet_id": spreadsheet_id,
        "sheet_gid": sheet_gid,
        "issues": formatted,
    }

    # --- Send to Apps Script ---
    print(f"Sending {len(formatted)} issues to Apps Script...")
    result = send_to_apps_script(apps_script_url, payload)

    # --- Print summary ---
    print(f"\n{'=' * 50}")
    print(f"Sync Summary ({datetime.date.today()})")
    print(f"{'=' * 50}")
    print(f"  Issues fetched:  {len(formatted)}")
    print(f"  Updated:         {result.get('updates', '?')}")
    print(f"  Inserted:        {result.get('inserts', '?')}")
    print(f"  Unchanged:       {result.get('unchanged', '?')}")
    print(f"  Total in sheet:  {result.get('total_in_sheet', '?')}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
