"""
GA4 Data API client. Fetches page-level traffic (sessions, users, pageviews) for given paths.
"""
import json
from datetime import datetime, timedelta
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import GA4_PROPERTY_ID, GOOGLE_SERVICE_ACCOUNT_JSON, SERVICE_ACCOUNT_FILE, TRAFFIC_DAYS

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


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

    if start_date and end_date:
        date_range = (start_date, end_date)
    else:
        date_range = _date_range()
    start_date, end_date = date_range
    service = get_ga4_service()
    property_name = f"properties/{GA4_PROPERTY_ID}"

    # GA4 dimension filter: pagePath is in our list. Build filter for "match any of these paths".
    # The API uses dimensionFilter with a single filter; for "in list" we use inListFilter.
    request_body = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "screenPageViews"},
        ],
        "limit": 10000,
    }

    # Filter to only our paths: use inListFilter for pagePath
    request_body["dimensionFilter"] = {
        "filter": {
            "fieldName": "pagePath",
            "inListFilter": {"values": paths},
        }
    }

    response = (
        service.properties()
        .runReport(property=property_name, body=request_body)
        .execute()
    )

    rows = response.get("rows", [])
    result = {p: {"sessions": 0, "totalUsers": 0, "screenPageViews": 0} for p in paths}

    for row in rows:
        dims = row.get("dimensionValues", [])
        metrics = row.get("metricValues", [])
        if not dims:
            continue
        path = dims[0].get("value", "")
        if path not in result:
            result[path] = {"sessions": 0, "totalUsers": 0, "screenPageViews": 0}
        result[path]["sessions"] = int(metrics[0].get("value", 0))
        result[path]["totalUsers"] = int(metrics[1].get("value", 0))
        result[path]["screenPageViews"] = int(metrics[2].get("value", 0))

    return result
