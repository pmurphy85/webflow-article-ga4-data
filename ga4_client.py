"""
GA4 Data API client. Fetches page-level traffic (sessions, users, pageviews) for given paths.
"""
import json
import time
from datetime import datetime, timedelta
from typing import Any

from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import GA4_PROPERTY_ID, GOOGLE_SERVICE_ACCOUNT_JSON, SERVICE_ACCOUNT_FILE, TRAFFIC_DAYS

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
MAX_RETRIES = 4
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
PATH_BATCH_SIZE = 25


def get_credentials():
    """Load service account credentials for GA4 (from file or env JSON)."""
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )


def get_ga4_service():
    """Build GA4 Data API service."""
    creds = get_credentials()
    return build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)


def _date_range() -> tuple[str, str]:
    """Return (start_date, end_date) for the last TRAFFIC_DAYS (YYYY-MM-DD)."""
    end = datetime.now() - timedelta(days=1)
    start = end - timedelta(days=TRAFFIC_DAYS - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _normalize_path(path: str) -> str:
    """Normalize page path for GA4 comparisons."""
    if not path:
        return "/"
    p = path.strip().split("?", 1)[0].split("#", 1)[0]
    if not p.startswith("/"):
        p = "/" + p
    while "//" in p:
        p = p.replace("//", "/")
    if p != "/" and p.endswith("/"):
        p = p[:-1]
    return p


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def _run_report_with_retries(service: Any, property_name: str, request_body: dict[str, Any]) -> dict[str, Any]:
    """Run GA4 report with retry/backoff on transient API errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return (
                service.properties()
                .runReport(property=property_name, body=request_body)
                .execute()
            )
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))
                continue
            raise RuntimeError(f"GA4 runReport failed (status={status}) after {attempt} attempt(s).") from e
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))
                continue
            raise RuntimeError(f"GA4 runReport failed after {attempt} attempt(s): {e}") from e


def fetch_traffic_by_path(
    paths: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, dict[str, float]]:
    """
    Fetch GA4 traffic (sessions, totalUsers, screenPageViews) for the given page paths.
    paths: list of path strings e.g. ["/blog/article-1", "/blog/article-2"].
    start_date, end_date: optional YYYY-MM-DD; when both provided, use instead of TRAFFIC_DAYS range.
    Returns dict mapping path -> { "sessions": n, "totalUsers": n, "screenPageViews": n }.
    Paths with no data get zeros.
    """
    if not paths:
        return {}
    original_paths = list(paths)
    normalized_to_originals: dict[str, list[str]] = {}
    for p in original_paths:
        n = _normalize_path(p)
        normalized_to_originals.setdefault(n, []).append(p)
    normalized_targets = list(normalized_to_originals.keys())

    if start_date and end_date:
        date_range = (start_date, end_date)
    else:
        date_range = _date_range()
    start_date, end_date = date_range
    service = get_ga4_service()
    property_name = f"properties/{GA4_PROPERTY_ID}"
    normalized_result = {
        p: {"sessions": 0, "totalUsers": 0, "screenPageViews": 0}
        for p in normalized_targets
    }

    for batch in _chunked(normalized_targets, PATH_BATCH_SIZE):
        request_body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "screenPageViews"},
            ],
            "limit": 10000,
            "dimensionFilter": {
                "filter": {
                    "fieldName": "pagePath",
                    "inListFilter": {"values": batch},
                }
            },
        }
        response = _run_report_with_retries(service, property_name, request_body)
        rows = response.get("rows", [])

        for row in rows:
            dims = row.get("dimensionValues", [])
            metrics = row.get("metricValues", [])
            if not dims:
                continue
            path = _normalize_path(dims[0].get("value", ""))
            if path not in normalized_result:
                continue
            normalized_result[path]["sessions"] = int(metrics[0].get("value", 0))
            normalized_result[path]["totalUsers"] = int(metrics[1].get("value", 0))
            normalized_result[path]["screenPageViews"] = int(metrics[2].get("value", 0))

    # Map normalized values back to the original requested keys.
    result: dict[str, dict[str, float]] = {}
    for normalized_path, originals in normalized_to_originals.items():
        stats = normalized_result.get(normalized_path, {"sessions": 0, "totalUsers": 0, "screenPageViews": 0})
        for original in originals:
            result[original] = dict(stats)
    return result
