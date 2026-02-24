"""
Write article + traffic data to a Google Sheet. Clears the sheet and writes fresh data.
"""
import json
import time
from datetime import datetime
from typing import Any

import gspread
from google.oauth2 import service_account

from config import GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, SHEET_NAME, SERVICE_ACCOUNT_FILE

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheets_client() -> gspread.Client:
    """Authenticate with service account and return gspread client (from file or env JSON)."""
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
        )
    return gspread.authorize(creds)


def read_article_traffic() -> dict[str, dict[str, Any]]:
    """
    Read existing traffic from the configured sheet. Returns URL -> { Sessions, Users, Pageviews }.
    Skips meta row and header; returns empty dict if sheet is missing, empty, or has no data rows.
    """
    client = get_sheets_client()
    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    except gspread.SpreadsheetNotFound:
        return {}
    try:
        worksheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        return {}
    try:
        all_values = worksheet.get_all_values()
    except Exception:
        return {}
    # Row 0 = meta, row 1 = headers, row 2+ = data (Title=0, Publish Date=1, Pageviews=2, URL=3, Sessions=4, Users=5)
    if len(all_values) < 3:
        return {}
    result = {}
    for row in all_values[2:]:
        if len(row) < 6:
            continue
        url = (row[3] or "").strip()
        if not url:
            continue
        try:
            pageviews = int(str(row[2] or "").replace(",", "")) or 0
        except (ValueError, TypeError):
            pageviews = 0
        try:
            sessions = int(str(row[4] or "").replace(",", "")) or 0
        except (ValueError, TypeError):
            sessions = 0
        try:
            users = int(str(row[5] or "").replace(",", "")) or 0
        except (ValueError, TypeError):
            users = 0
        result[url] = {"Sessions": sessions, "Users": users, "Pageviews": pageviews}
    return result


def write_article_traffic(rows: list[dict[str, Any]]) -> None:
    """
    Write combined article traffic to the configured Google Sheet.
    rows: list of dicts with keys Title, URL, Publish Date, Sessions, Users, Pageviews.
    Sheet is cleared and rewritten; first row is "Last Updated: <timestamp>", then headers, then data (caller should sort by Publish Date before passing).
    """
    client = get_sheets_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=10)

    headers = ["Title", "Publish Date", "Pageviews", "URL", "Sessions", "Users"]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta_row = [f"Last Updated: {timestamp}"]
    header_row = headers
    def _num(val):
        try:
            return int(val) if val not in (None, "") else 0
        except (TypeError, ValueError):
            return 0

    data_rows = [
        [
            r.get("Title", ""),
            r.get("Publish Date", ""),
            f"{_num(r.get('Pageviews')):,}",
            r.get("URL", ""),
            f"{_num(r.get('Sessions')):,}",
            f"{_num(r.get('Users')):,}",
        ]
        for r in rows
    ]

    all_cells = [meta_row] + [header_row] + data_rows
    worksheet.clear()
    if all_cells:
        # Smaller batches (250 rows) to reduce chance of connection reset / rate limit
        batch_size = 250
        max_retries = 3
        for i in range(0, len(all_cells), batch_size):
            chunk = all_cells[i : i + batch_size]
            start_cell = f"A{i + 1}"
            for attempt in range(max_retries):
                try:
                    worksheet.update(chunk, start_cell)
                    print(f"  Wrote rows {i + 1}-{i + len(chunk)}...")
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = (attempt + 1) * 2
                        print(f"  Sheet write failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"  Sheet write failed after {max_retries} attempts: {e}")
                        raise
    print(f"[OK] Wrote {len(rows)} rows to sheet '{SHEET_NAME}' (last updated: {timestamp})")
