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
# 第二个表格
SPREADSHEET_ID_2 = "1qYcIQI9L-HuhogMTZ9GKMeJh_9lpZl72OVs3PK-0VQo"
SHEET_GID_2 = 1474875087
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


def fetch_open_issues(token: str = "") -> list[dict]:
    """Fetch all OPEN issues (excluding PRs) from triton-ascend."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    issues: list[dict] = []
    page = 1
    while True:
        url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/issues"
        params = {
            "state": "open",
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


def fetch_issue(number: int, token: str = "") -> dict | None:
    """Fetch a single issue by number."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/issues/{number}"
    resp = _gh_request(url, headers)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def fetch_first_response(number: int, creator_login: str, token: str = "") -> str:
    """Fetch the first non-creator comment's creation time. Returns ISO datetime or empty."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/issues/{number}/comments"
    params = {"per_page": 100, "sort": "created", "direction": "asc"}
    resp = _gh_request(url, headers, params)
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    data = resp.json()
    for comment in data:
        if comment.get("user", {}).get("login", "") != creator_login:
            return comment.get("created_at", "")
    return ""


def calculate_duration(created_at_str: str, response_at_str: str) -> str:
    """Calculate duration in days (2 decimal places) between two ISO datetimes."""
    if not created_at_str or not response_at_str:
        return ""
    try:
        created = datetime.datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        response = datetime.datetime.fromisoformat(response_at_str.replace("Z", "+00:00"))
        diff = response - created
        total_seconds = diff.total_seconds()
        if total_seconds < 0:
            return ""
        days = total_seconds / 86400
        return f"{days:.2f}天"
    except Exception:
        return ""


def fetch_latest_reply(number: int, token: str = "") -> str:
    """Fetch the latest comment content for an issue. Returns comment body or empty."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/issues/{number}/comments"
    params = {"per_page": 1, "sort": "created", "direction": "desc"}
    resp = _gh_request(url, headers, params)
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    data = resp.json()
    if data:
        body = data[0].get("body", "")
        if len(body) > 500:
            body = body[:500] + "..."
        return body
    return ""


# ==================== Format issue data ====================

def format_issue(issue, latest_reply="", first_response=""):
    """Format GitHub issue data for Apps Script."""
    labels = [l["name"] for l in issue["labels"]]
    status_label, type_label = categorize_labels(labels)
    state = issue["state"]
    closed_at = issue.get("closed_at")
    creator = ""
    if issue.get("user"):
        creator = issue["user"].get("login", "")
    created_at = issue.get("created_at", "")
    first_response_time = format_datetime(first_response) if first_response else ""
    first_response_duration = calculate_duration(created_at, first_response) if first_response else ""
    return {
        "number": issue["number"],
        "title": issue["title"],
        "url": issue["html_url"],
        "state": state,
        "is_closed": "是" if state == "closed" else "否",
        "close_time": format_datetime(closed_at) if closed_at else "",
        "created_time": format_datetime(issue.get("created_at", "")),
        "status_label": status_label,
        "type_label": type_label,
        "comments": issue["comments"],
        "updated_at": issue["updated_at"],
        "created_at": issue.get("created_at", ""),
        "creator": creator,
        "latest_reply": latest_reply,
        "last_updated": format_datetime(issue.get("updated_at", "")),
        "first_response_time": first_response_time,
        "first_response_duration": first_response_duration,
    }


# ==================== Apps Script Web App ====================

def send_to_apps_script(url: str, payload: dict) -> dict:
    """Send data to Apps Script Web App via HTTP POST."""
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


# ==================== Sync one sheet ====================

def sync_sheet(apps_script_url, spreadsheet_id, sheet_gid, formatted, github_token, sheet_label=""):
    """Sync issues to one Google Sheet (delete_auto + sync + possibly_closed)."""
    prefix = f"[{sheet_label}] " if sheet_label else ""

    # Step 1: Delete auto-added rows
    print(f"\n{prefix}Step 1: Deleting auto-added rows...")
    try:
        delete_result = send_to_apps_script(apps_script_url, {
            "mode": "delete_auto",
            "spreadsheet_id": spreadsheet_id,
            "sheet_gid": sheet_gid,
        })
        print(f"  {prefix}Deleted: {delete_result.get('deleted', '?')} rows, remaining: {delete_result.get('remaining', '?')}")
    except Exception as e:
        print(f"  {prefix}Delete warning: {e}")

    # Step 2: Sync open issues
    print(f"{prefix}Step 2: Sending {len(formatted)} open issues...")
    result = send_to_apps_script(apps_script_url, {
        "mode": "sync",
        "spreadsheet_id": spreadsheet_id,
        "sheet_gid": sheet_gid,
        "issues": formatted,
    })
    print(f"  {prefix}Sync: updates={result.get('updates', 0)}, inserts={result.get('inserts', 0)}, unchanged={result.get('unchanged', 0)}")

    # Step 3: Check possibly closed issues
    possibly_closed = result.get("possibly_closed", [])
    if possibly_closed:
        print(f"{prefix}Step 3: Checking {len(possibly_closed)} possibly closed issues...")
        closed_formatted = []
        for num in possibly_closed:
            issue = fetch_issue(num, github_token)
            if issue:
                reply = ""
                first_resp = ""
                creator_login = issue.get("user", {}).get("login", "")
                if issue.get("comments", 0) > 0:
                    reply = fetch_latest_reply(issue["number"], github_token)
                    first_resp = fetch_first_response(issue["number"], creator_login, github_token)
                closed_formatted.append(format_issue(issue, reply, first_resp))

        if closed_formatted:
            closed_result = send_to_apps_script(apps_script_url, {
                "mode": "sync",
                "spreadsheet_id": spreadsheet_id,
                "sheet_gid": sheet_gid,
                "issues": closed_formatted,
            })
            print(f"  {prefix}Closed: updates={closed_result.get('updates', 0)}, unchanged={closed_result.get('unchanged', 0)}")
            result["updates"] = result.get("updates", 0) + closed_result.get("updates", 0)
            result["inserts"] = result.get("inserts", 0) + closed_result.get("inserts", 0)
    else:
        print(f"{prefix}Step 3: No possibly closed issues.")

    # Summary
    print(f"\n{prefix}Summary: updated={result.get('updates', 0)}, inserted={result.get('inserts', 0)}, unchanged={result.get('unchanged', 0)}, total_in_sheet={result.get('total_in_sheet', '?')}")
    return result


# ==================== Main ====================

def main():
    apps_script_url = os.environ.get("APPS_SCRIPT_URL")
    if not apps_script_url:
        print("ERROR: APPS_SCRIPT_URL environment variable not set")
        sys.exit(1)

    github_token = os.environ.get("GITHUB_TOKEN", "")

    # Sheet configs (调试期间只同步 Sheet1)
    sheets = [
        ("Sheet1", DEFAULT_SPREADSHEET_ID, DEFAULT_SHEET_GID),
        # ("Sheet2", SPREADSHEET_ID_2, SHEET_GID_2),  # 调试完成后再放开
    ]

    # --- Fetch OPEN issues from GitHub (once for all sheets) ---
    print("Fetching open issues from GitHub...")
    open_issues = fetch_open_issues(github_token)
    print(f"Found {len(open_issues)} open issues (excluding PRs)")

    # --- Build formatted issue data (once for all sheets) ---
    print("Fetching latest replies and first responses...")
    formatted = []
    for issue in open_issues:
        reply = ""
        first_resp = ""
        creator_login = issue.get("user", {}).get("login", "")
        if issue.get("comments", 0) > 0:
            reply = fetch_latest_reply(issue["number"], github_token)
            first_resp = fetch_first_response(issue["number"], creator_login, github_token)
        formatted.append(format_issue(issue, reply, first_resp))

    # --- Sync each sheet ---
    for label, sid, gid in sheets:
        print(f"\n{'=' * 50}")
        print(f"Syncing {label}")
        print(f"{'=' * 50}")
        sync_sheet(apps_script_url, sid, gid, formatted, github_token, label)

    print(f"\n{'=' * 50}")
    print(f"All sheets synced. ({datetime.date.today()})")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()


