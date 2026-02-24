"""
Webflow CMS API v2 client. Pulls article URLs and publish dates from a single collection.
"""
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

from config import (
    WEBFLOW_API_TOKEN,
    WEBFLOW_COLLECTION_ID,
    WEBFLOW_SITE_DOMAIN,
    WEBFLOW_URL_PREFIX,
)

BASE_URL = "https://api.webflow.com/v2"
PAGE_SIZE = 100
EASTERN = ZoneInfo("America/New_York")


def _format_publish_datetime(iso_str: str) -> str:
    """Format Webflow ISO datetime to YYYY-MM-DD HH:MM ET (Eastern time)."""
    if not iso_str or not iso_str.strip():
        return ""
    s = iso_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt_utc = datetime.fromisoformat(s)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_et = dt_utc.astimezone(EASTERN)
        return dt_et.strftime("%Y-%m-%d %H:%M") + " ET"
    except (ValueError, TypeError):
        match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", s)
        if match:
            return f"{match.group(1)} {match.group(2)} ET"
        return s[:16] if len(s) >= 16 else s


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {WEBFLOW_API_TOKEN}",
        "Accept": "application/json",
    }


def fetch_all_items() -> list[dict[str, Any]]:
    """
    Fetch published items from the configured Webflow collection with pagination (live endpoint).
    Returns list of raw item dicts from the API.
    """
    all_items: list[dict[str, Any]] = []
    offset = 0

    while True:
        url = f"{BASE_URL}/collections/{WEBFLOW_COLLECTION_ID}/items/live"
        params = {"limit": PAGE_SIZE, "offset": offset}
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_items.extend(items)
        pagination = data.get("pagination", {})
        total = pagination.get("total", 0)
        if offset + len(items) >= total or len(items) == 0:
            break
        offset += len(items)

    return all_items


def get_articles() -> list[dict[str, Any]]:
    """
    Get articles from the configured collection: slug, title, publish date, and full URL.
    Returns list of dicts with keys: title, url, slug, publish_date.
    """
    items = fetch_all_items()
    articles = []

    for item in items:
        field_data = item.get("fieldData") or {}
        slug = (field_data.get("slug") or "").strip()
        name = (field_data.get("name") or "").strip()
        # Use lastPublished as publish date; fall back to createdOn (ISO format e.g. 2025-02-20T14:30:00.000Z)
        publish_raw = item.get("lastPublished") or item.get("createdOn") or ""
        publish_display = _format_publish_datetime(publish_raw)
        if not slug:
            continue
        path = f"{WEBFLOW_URL_PREFIX}{slug}".replace("//", "/")
        url = f"{WEBFLOW_SITE_DOMAIN}{path}"
        articles.append({
            "title": name or slug,
            "url": url,
            "slug": slug,
            "path": path,
            "publish_date": publish_display,
        })

    return articles
