"""
Write article + traffic data to a Google Sheet. Clears the sheet and writes fresh data.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Any

# Max seconds for any single Sheets API call (clear or batch update)
SHEETS_REQUEST_TIMEOUT = 120

import gspread
from gspread.exceptions import APIError
from google.oauth2 import service_account

from config import GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, SHEET_NAME, SERVICE_ACCOUNT_FILE

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_RETRIES = 4
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _is_retryable_error(e: Exception) -> bool:
    if isinstance(e, APIError):
        status = getattr(getattr(e, "response", None), "status_code", None)
        return status in RETRYABLE_STATUS_CODES
    return isinstance(e, (TimeoutError, FuturesTimeoutError, ConnectionError))


def _retry_call(fn, stage: str):
    """Run a callable with retry/backoff for transient Google Sheets failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            if attempt < MAX_RETRIES and _is_retryable_error(e):
                time.sleep(2 ** (attempt - 1))
                continue
            raise RuntimeError(f"Google Sheets failed at '{stage}' after {attempt} attempt(s): {e}") from e


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
        spreadsheet = _retry_call(lambda: client.open_by_key(GOOGLE_SHEET_ID), "open_by_key")
    except gspread.SpreadsheetNotFound:
        return {}
    try:
        worksheet = _retry_call(lambda: spreadsheet.worksheet(SHEET_NAME), "worksheet_lookup")
    except gspread.WorksheetNotFound:
        return {}
    try:
        all_values = _retry_call(lambda: worksheet.get_all_values(), "read_all_values")
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
    spreadsheet = _retry_call(lambda: client.open_by_key(GOOGLE_SHEET_ID), "open_by_key")
    try:
        worksheet = _retry_call(lambda: spreadsheet.worksheet(SHEET_NAME), "worksheet_lookup")
    except gspread.WorksheetNotFound:
        worksheet = _retry_call(
            lambda: spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=10),
            "worksheet_create",
        )

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
    print("Clearing sheet...")
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            _retry_call(
                lambda: ex.submit(worksheet.clear).result(timeout=SHEETS_REQUEST_TIMEOUT),
                "worksheet_clear",
            )
    except FuturesTimeoutError:
        raise RuntimeError(f"Sheet clear timed out after {SHEETS_REQUEST_TIMEOUT}s. Try a smaller sheet or check network.") from None
    print("Cleared. Writing in batches...")
    if all_cells:
        batch_size = 250
        for i in range(0, len(all_cells), batch_size):
            chunk = all_cells[i : i + batch_size]
            start_cell = f"A{i + 1}"
            print(f"  Writing rows {i + 1}-{i + len(chunk)}...")
            with ThreadPoolExecutor(max_workers=1) as ex:
                _retry_call(
                    lambda: ex.submit(worksheet.update, chunk, start_cell).result(timeout=SHEETS_REQUEST_TIMEOUT),
                    f"worksheet_update_{start_cell}",
                )
            print(f"  Wrote rows {i + 1}-{i + len(chunk)}.")
    print(f"[OK] Wrote {len(rows)} rows to sheet '{SHEET_NAME}' (last updated: {timestamp})")
