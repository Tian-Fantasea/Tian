#!/usr/bin/env python3
"""
Sync triton-ascend GitHub issues to Google Sheets tracking table.

This script monitors the triton-lang/triton-ascend repository for issue changes
and synchronizes them to a Google Sheets tracking table.

What it does:
  1. Reads the current tracking table from Google Sheets (row 2 = headers, row 3+ = data)
  2. Fetches all open issues (excluding PRs) from triton-lang/triton-ascend via GitHub API
  3. For tracked issues not in the open list, fetches them individually (may have been closed)
  4. Compares each issue's current GitHub state with the sheet data:
     - State change (open -> closed): updates "是否关闭" and "关闭时间"
     - Label changes: updates "状态标签" and "类型标签"
     - New comments (detected via metadata): appends a note to "进展"
     - Title changes: updates "Issue Title"
  5. Appends new issues (not yet in the sheet) with all auto-fillable columns
  6. Saves metadata JSON for change detection between runs

Environment variables:
    GOOGLE_SERVICE_ACCOUNT_KEY  JSON string of Google Service Account credentials (required)
    GITHUB_TOKEN                GitHub token for API rate limits (optional, falls back to anonymous)
    METADATA_FILE_PATH          Path to metadata file (default: <script_dir>/triton_ascend_issue_metadata.json)
"""

import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

import gspread
import requests

# ==================== Configuration ====================

SPREADSHEET_ID = "1i_Wlw1-XNeMdE-ELv9s_hgWjWztYUy6hYgckIh4Ov4k"
WORKSHEET_GID = 144346032
GITHUB_REPO = "triton-lang/triton-ascend"
GITHUB_API_BASE = "https://api.github.com"
HEADER_ROW = 2       # Row 2 contains column headers (row 1 is instructions)
DATA_START_ROW = 3   # Data starts from row 3

# Label categories matching the sheet's convention
STATUS_LABELS = frozenset({
    "triage review", "triaged", "wait-feedback", "resolved",
    "stale", "duplicated", "invalid", "wontfix",
})
TYPE_LABELS = frozenset({
    "feature request", "RFC", "question", "documentation",
    "installation", "performance", "bug", "ssbuffer",
})


# ==================== Utility functions ====================

def load_metadata(filepath: Path) -> dict:
    """Load metadata from JSON file, or return empty structure."""
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_sync": None, "issues": {}}


def save_metadata(filepath: Path, metadata: dict) -> None:
    """Save metadata to JSON file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def get_column_letter(col_num: int) -> str:
    """Convert 1-based column number to spreadsheet column letter (A, B, ..., Z, AA, ...)."""
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


def extract_issue_number(url: str) -> int | None:
    """Extract issue number from a GitHub issue URL."""
    match = re.search(r"/issues/(\d+)", url or "")
    return int(match.group(1)) if match else None


def categorize_labels(labels: list[str]) -> tuple[str, str]:
    """Split GitHub labels into status and type categories matching the sheet's convention."""
    status = [l for l in labels if l in STATUS_LABELS]
    type_ = [l for l in labels if l in TYPE_LABELS]
    return ",".join(status), ",".join(type_)


def format_datetime(date_str: str) -> str:
    """Format ISO 8601 datetime to 'YYYY-MM-DD HH:MM:SS'."""
    if not date_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str


def get_cell(row_data: list, col_idx: int) -> str:
    """Get cell value from row data, handling index out of range."""
    if col_idx < len(row_data):
        return (row_data[col_idx] or "").strip()
    return ""


# ==================== Google Sheets ====================

def connect_to_sheet(service_account_key: str) -> gspread.Worksheet:
    """Connect to Google Sheets and return the target worksheet."""
    credentials_dict = json.loads(service_account_key)
    gc = gspread.service_account_from_dict(credentials_dict)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    for ws in spreadsheet.worksheets():
        if ws.id == WORKSHEET_GID:
            return ws
    raise ValueError(f"Worksheet with gid {WORKSHEET_GID} not found in spreadsheet {SPREADSHEET_ID}")


def parse_column_mapping(all_values: list[list[str]]) -> dict[str, int]:
    """
    Read the header row (row 2) and build a mapping of column purpose -> 0-based column index.

    Expected headers (matched by keyword):
        "Issue Title"     -> title
        "Issue 链接"      -> url
        "是否关闭"         -> closed
        "关闭时间"         -> close_time
        "状态标签"         -> status_label
        "类型标签"         -> type_label
        "Maintainer"      -> maintainer
        "Issue 责任人"    -> owner
        "进展"            -> progress
    """
    headers = all_values[HEADER_ROW - 1] if len(all_values) >= HEADER_ROW else []
    mapping: dict[str, int] = {}

    for i, h in enumerate(headers):
        h_stripped = (h or "").strip()
        h_lower = h_stripped.lower()
        if not h_lower:
            continue

        if "title" in h_lower or "标题" in h_stripped:
            mapping["title"] = i
        elif "链接" in h_stripped or "url" in h_lower:
            mapping["url"] = i
        elif "是否" in h_stripped and "关闭" in h_stripped:
            mapping["closed"] = i
        elif "关闭" in h_stripped and "时间" in h_stripped:
            mapping["close_time"] = i
        elif "状态" in h_stripped and "标签" in h_stripped:
            mapping["status_label"] = i
        elif "类型" in h_stripped and "标签" in h_stripped:
            mapping["type_label"] = i
        elif "maintainer" in h_lower:
            mapping["maintainer"] = i
        elif "责任" in h_stripped:
            mapping["owner"] = i
        elif "进展" in h_stripped:
            mapping["progress"] = i

    # Cross-check: if URL column not found via header, scan data rows
    if "url" not in mapping:
        for row in all_values[DATA_START_ROW - 1 : DATA_START_ROW + 20]:
            for i, val in enumerate(row):
                if "github.com" in (val or "") and "/issues/" in (val or ""):
                    mapping["url"] = i
                    break
            if "url" in mapping:
                break

    return mapping


# ==================== GitHub API ====================

def _gh_request(url: str, headers: dict, params: dict | None = None) -> requests.Response:
    """Make a GitHub API request with basic retry on rate limit."""
    for attempt in range(3):
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset:
                wait = max(int(reset) - int(time.time()) + 2, 1)
                print(f"  Rate limited. Waiting {wait}s for reset...")
                time.sleep(min(wait, 60))
                continue
        return resp
    return resp


def fetch_all_open_issues(token: str = "") -> list[dict]:
    """Fetch all open issues (excluding PRs) from triton-ascend repo."""
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


# ==================== Main sync logic ====================

def main() -> None:
    service_account_key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if not service_account_key:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_KEY environment variable not set")
        sys.exit(1)

    github_token = os.environ.get("GITHUB_TOKEN", "")

    metadata_path = Path(os.environ.get(
        "METADATA_FILE_PATH",
        str(Path(__file__).parent / "triton_ascend_issue_metadata.json"),
    ))
    metadata = load_metadata(metadata_path)

    # --- Connect to sheet and read data ---
    print("Connecting to Google Sheets...")
    worksheet = connect_to_sheet(service_account_key)
    all_values = worksheet.get_all_values()
    col_map = parse_column_mapping(all_values)
    print(f"Column mapping: {col_map}")

    if "url" not in col_map:
        print("ERROR: Could not find the issue URL column in the sheet")
        sys.exit(1)

    # --- Build existing issues map (issue_number -> {row, data}) ---
    existing_issues: dict[int, dict] = {}
    url_col = col_map["url"]
    for row_idx in range(DATA_START_ROW - 1, len(all_values)):
        row = all_values[row_idx]
        url = get_cell(row, url_col)
        issue_num = extract_issue_number(url)
        if issue_num:
            existing_issues[issue_num] = {
                "row": row_idx + 1,  # gspread uses 1-based rows
                "data": row,
            }
    print(f"Found {len(existing_issues)} tracked issues in sheet")

    # --- Fetch all open issues from GitHub ---
    print("Fetching open issues from GitHub...")
    open_issues = fetch_all_open_issues(github_token)
    open_issue_numbers = {i["number"] for i in open_issues}
    print(f"Found {len(open_issues)} open issues on GitHub")

    # --- For tracked issues not in open list, fetch individually (may be closed) ---
    tracked_not_open = set(existing_issues.keys()) - open_issue_numbers
    closed_issues: dict[int, dict] = {}
    if tracked_not_open:
        print(f"Checking {len(tracked_not_open)} tracked issues that may have been closed...")
    for num in sorted(tracked_not_open):
        issue = fetch_issue(num, github_token)
        if issue:
            if issue["state"] == "closed":
                closed_issues[num] = issue
            else:
                # Still open but wasn't in the paginated list (edge case)
                open_issues.append(issue)
                open_issue_numbers.add(num)

    # Combine all issues to process
    all_current_issues: dict[int, dict] = {i["number"]: i for i in open_issues}
    all_current_issues.update(closed_issues)
    print(f"Total issues to process: {len(all_current_issues)}")

    # --- Process each issue ---
    updates: list[dict] = []       # batch_update entries: {"range": "A3", "values": [["val"]]}
    new_rows: list[list[str]] = []  # rows to append
    stats = {"updated": 0, "new": 0, "unchanged": 0}
    new_metadata_issues: dict[str, dict] = {}
    today = datetime.date.today().strftime("%m-%d")

    for issue_num in sorted(all_current_issues.keys()):
        issue = all_current_issues[issue_num]
        title: str = issue["title"]
        url: str = issue["html_url"]
        state: str = issue["state"]
        closed_at: str | None = issue.get("closed_at")
        labels: list[str] = [l["name"] for l in issue["labels"]]
        comments: int = issue["comments"]
        updated_at: str = issue["updated_at"]

        status_label, type_label = categorize_labels(labels)
        is_closed = "是" if state == "closed" else "否"
        close_time = format_datetime(closed_at) if closed_at else ""

        if issue_num in existing_issues:
            # --- Existing issue: detect and sync changes ---
            row_num = existing_issues[issue_num]["row"]
            row_data = existing_issues[issue_num]["data"]

            cell_updates: dict[int, str] = {}
            changes: list[str] = []

            # Compare sheet data with current GitHub data
            if "title" in col_map:
                old_val = get_cell(row_data, col_map["title"])
                if old_val != title:
                    cell_updates[col_map["title"]] = title
                    changes.append("title changed")

            if "closed" in col_map:
                old_val = get_cell(row_data, col_map["closed"])
                if old_val != is_closed:
                    cell_updates[col_map["closed"]] = is_closed
                    changes.append(f"state->{state}")

            if "close_time" in col_map:
                old_val = get_cell(row_data, col_map["close_time"])
                if close_time and old_val != close_time:
                    cell_updates[col_map["close_time"]] = close_time
                    if not any("state->closed" in c for c in changes):
                        changes.append("close time updated")

            if "status_label" in col_map:
                old_val = get_cell(row_data, col_map["status_label"])
                if old_val != status_label:
                    cell_updates[col_map["status_label"]] = status_label
                    changes.append(f"status->{status_label or '(none)'}")

            if "type_label" in col_map:
                old_val = get_cell(row_data, col_map["type_label"])
                if old_val != type_label:
                    cell_updates[col_map["type_label"]] = type_label
                    changes.append(f"type->{type_label or '(none)'}")

            # Check new comments using stored metadata
            stored = metadata["issues"].get(str(issue_num), {})
            stored_comments = stored.get("comments")
            if stored_comments is not None and comments > stored_comments:
                diff = comments - stored_comments
                changes.append(f"+{diff} comment(s)")

            if cell_updates or changes:
                # Append auto-sync note to progress column
                if "progress" in col_map and changes:
                    old_progress = get_cell(row_data, col_map["progress"])
                    auto_note = f"[auto-sync {today}] {'; '.join(changes)}"
                    new_progress = f"{old_progress}\n{auto_note}" if old_progress else auto_note
                    cell_updates[col_map["progress"]] = new_progress

                # Convert to batch_update format
                for col_idx, value in cell_updates.items():
                    col_letter = get_column_letter(col_idx + 1)
                    cell_range = f"{col_letter}{row_num}"
                    updates.append({"range": cell_range, "values": [[value]]})

                stats["updated"] += 1
                print(f"  [UPDATE] #{issue_num}: {'; '.join(changes)}")
            else:
                stats["unchanged"] += 1

            # Store metadata
            new_metadata_issues[str(issue_num)] = {
                "state": state,
                "updated_at": updated_at,
                "comments": comments,
                "labels": labels,
            }

        else:
            # --- New issue: add to sheet ---
            num_cols = (max(col_map.values()) + 1) if col_map else 9
            row_values = [""] * num_cols

            if "title" in col_map:
                row_values[col_map["title"]] = title
            if "url" in col_map:
                row_values[col_map["url"]] = url
            if "closed" in col_map:
                row_values[col_map["closed"]] = is_closed
            if "close_time" in col_map:
                row_values[col_map["close_time"]] = close_time
            if "status_label" in col_map:
                row_values[col_map["status_label"]] = status_label
            if "type_label" in col_map:
                row_values[col_map["type_label"]] = type_label
            if "progress" in col_map:
                created_date = format_datetime(issue.get("created_at", ""))[:10]
                row_values[col_map["progress"]] = (
                    f"[auto-sync {today}] New issue (created: {created_date}, comments: {comments})"
                )

            new_rows.append(row_values)
            new_metadata_issues[str(issue_num)] = {
                "state": state,
                "updated_at": updated_at,
                "comments": comments,
                "labels": labels,
            }
            stats["new"] += 1
            print(f"  [NEW] #{issue_num}: {title[:60]}")

    # Carry over metadata for issues not seen this run (still tracked in sheet)
    for num_str, data in metadata["issues"].items():
        if num_str not in new_metadata_issues:
            new_metadata_issues[num_str] = data

    # --- Apply updates to sheet ---
    if updates:
        print(f"\nApplying {len(updates)} cell update(s) to sheet...")
        worksheet.batch_update(updates)

    # --- Append new rows ---
    if new_rows:
        print(f"Appending {len(new_rows)} new row(s) to sheet...")
        table_start = f"A{HEADER_ROW}"
        worksheet.append_rows(new_rows, value_input_option="USER_ENTERED", table_range=table_start)

    # --- Save metadata ---
    metadata["last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata["issues"] = new_metadata_issues
    save_metadata(metadata_path, metadata)

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"Sync Summary ({datetime.date.today()})")
    print(f"{'=' * 60}")
    print(f"  Tracked in sheet:    {len(existing_issues)}")
    print(f"  Open on GitHub:       {len(open_issues)}")
    print(f"  Closed detected:     {len(closed_issues)}")
    print(f"  Updated:             {stats['updated']}")
    print(f"  New:                 {stats['new']}")
    print(f"  Unchanged:           {stats['unchanged']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
