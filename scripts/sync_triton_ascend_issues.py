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

    # --- Step 1: Delete auto-added rows (keep original data only) ---
    print("Step 1: Deleting auto-added rows...")
    delete_payload = {
        "mode": "delete_auto",
        "spreadsheet_id": spreadsheet_id,
        "sheet_gid": sheet_gid,
    }
    try:
        delete_result = send_to_apps_script(apps_script_url, delete_payload)
        print(f"  Deleted: {delete_result.get('deleted', '?')} auto rows, remaining: {delete_result.get('remaining', '?')}")
    except Exception as e:
        print(f"  Delete warning: {e}")

    # --- Step 2: Fetch OPEN issues from GitHub ---
    print("\nStep 2: Fetching open issues from GitHub...")
    open_issues = fetch_open_issues(github_token)
    print(f"Found {len(open_issues)} open issues (excluding PRs)")

    # --- Build payload ---
    def format_issue(issue, latest_reply=""):
        labels = [l["name"] for l in issue["labels"]]
        status_label, type_label = categorize_labels(labels)
        state = issue["state"]
        closed_at = issue.get("closed_at")
        creator = ""
        if issue.get("user"):
            creator = issue["user"].get("login", "")
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
        }

    # Fetch latest reply for issues with comments > 0
    print("Fetching latest replies...")
    formatted = []
    for issue in open_issues:
        reply = ""
        if issue.get("comments", 0) > 0:
            reply = fetch_latest_reply(issue["number"], github_token)
        formatted.append(format_issue(issue, reply))

    payload = {
        "mode": "sync",
        "spreadsheet_id": spreadsheet_id,
        "sheet_gid": sheet_gid,
        "issues": formatted,
    }

    # --- Step 3: Send open issues to Apps Script ---
    print(f"\nStep 3: Sending {len(formatted)} open issues to Apps Script...")
    result = send_to_apps_script(apps_script_url, payload)
    print(f"  Step3 response: {json.dumps(result, ensure_ascii=False)}")

    # --- Step 4: Check tracked issues that might be closed ---
    possibly_closed = result.get("possibly_closed", [])
    if possibly_closed:
        print(f"\nStep 4: Checking {len(possibly_closed)} tracked issues that may be closed...")
        print(f"  Possibly closed numbers: {possibly_closed[:20]}{'...' if len(possibly_closed)>20 else ''}")
        closed_formatted = []
        for num in possibly_closed:
            issue = fetch_issue(num, github_token)
            if issue:
                reply = ""
                if issue.get("comments", 0) > 0:
                    reply = fetch_latest_reply(issue["number"], github_token)
                closed_formatted.append(format_issue(issue, reply))

        if closed_formatted:
            # Debug: read one closed issue's row data BEFORE update
            if closed_formatted:
                debug_payload = {
                    "mode": "read_row",
                    "spreadsheet_id": spreadsheet_id,
                    "sheet_gid": sheet_gid,
                    "issue_number": closed_formatted[0]["number"],
                }
                try:
                    debug_result = send_to_apps_script(apps_script_url, debug_payload)
                    print(f"  [DEBUG] Issue #{closed_formatted[0]['number']} BEFORE update:")
                    print(f"    {json.dumps(debug_result, ensure_ascii=False)[:500]}")
                except Exception as e:
                    print(f"  [DEBUG] read_row error: {e}")

            closed_payload = {
                "mode": "sync",
                "spreadsheet_id": spreadsheet_id,
                "sheet_gid": sheet_gid,
                "issues": closed_formatted,
            }
            closed_result = send_to_apps_script(apps_script_url, closed_payload)
            print(f"  Step4 response: {json.dumps(closed_result, ensure_ascii=False)}")
            result["updates"] = result.get("updates", 0) + closed_result.get("updates", 0)
            result["inserts"] = result.get("inserts", 0) + closed_result.get("inserts", 0)

            # Debug: read same issue's row data AFTER update
            try:
                debug_result2 = send_to_apps_script(apps_script_url, debug_payload)
                print(f"  [DEBUG] Issue #{closed_formatted[0]['number']} AFTER update:")
                print(f"    {json.dumps(debug_result2, ensure_ascii=False)[:500]}")
            except Exception as e:
                print(f"  [DEBUG] read_row error: {e}")
    else:
        print("\nStep 4: No tracked issues missing from open list.")

    # --- Print summary ---
    print(f"\n{'=' * 50}")
    print(f"Sync Summary ({datetime.date.today()})")
    print(f"{'=' * 50}")
    print(f"  Open issues fetched: {len(formatted)}")
    print(f"  Possibly closed:     {len(possibly_closed)}")
    print(f"  Updated:            {result.get('updates', '?')}")
    print(f"  Inserted:            {result.get('inserts', '?')}")
    print(f"  Unchanged:          {result.get('unchanged', '?')}")
    print(f"  Total in sheet:     {result.get('total_in_sheet', '?')}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()


