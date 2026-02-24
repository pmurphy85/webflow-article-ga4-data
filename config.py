"""
Load configuration from .env. All secrets and IDs stay in .env (never committed).
"""
import base64
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent / ".env")

# Webflow
WEBFLOW_API_TOKEN = os.getenv("WEBFLOW_API_TOKEN", "").strip()
WEBFLOW_COLLECTION_ID = os.getenv("WEBFLOW_COLLECTION_ID", "").strip()
WEBFLOW_SITE_DOMAIN = os.getenv("WEBFLOW_SITE_DOMAIN", "").strip().rstrip("/")
WEBFLOW_URL_PREFIX = os.getenv("WEBFLOW_URL_PREFIX", "/").strip()
if WEBFLOW_URL_PREFIX and not WEBFLOW_URL_PREFIX.startswith("/"):
    WEBFLOW_URL_PREFIX = "/" + WEBFLOW_URL_PREFIX
if WEBFLOW_URL_PREFIX and not WEBFLOW_URL_PREFIX.endswith("/"):
    WEBFLOW_URL_PREFIX = WEBFLOW_URL_PREFIX + "/"

# Google
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "").strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_NAME = os.getenv("SHEET_NAME", "Article Traffic").strip()
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "").strip()
# For cloud: paste entire service account JSON string (env var); file path not needed
_raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
_raw_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "").strip()
# Strip whitespace/newlines from base64 (Railway can add them when pasting)
if _raw_b64:
    _raw_b64 = "".join(_raw_b64.split())
if _raw_b64:
    try:
        # Fix padding if needed (base64 length must be multiple of 4)
        pad = 4 - (len(_raw_b64) % 4)
        if pad != 4:
            _raw_b64 += "=" * pad
        GOOGLE_SERVICE_ACCOUNT_JSON = base64.b64decode(_raw_b64).decode("utf-8")
    except Exception:
        GOOGLE_SERVICE_ACCOUNT_JSON = ""
else:
    GOOGLE_SERVICE_ACCOUNT_JSON = _raw_json

# Optional
TRAFFIC_DAYS = int(os.getenv("TRAFFIC_DAYS", "30"))
# Only fetch GA4 for articles published in the last N days; older articles keep last-known traffic from sheet
REFRESH_DAYS = int(os.getenv("REFRESH_DAYS", "7"))
# Optional one-time backfill: when set (e.g. "2025"), only that year's articles with full-year GA4 traffic
BACKFILL_YEAR = os.getenv("BACKFILL_YEAR", "").strip()


def _credentials_ok() -> tuple[bool, str]:
    """Return (True, '') if we have valid Google credentials; else (False, error_message)."""
    if SERVICE_ACCOUNT_FILE and os.path.isfile(SERVICE_ACCOUNT_FILE):
        return True, ""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return False, "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 (or SERVICE_ACCOUNT_FILE locally)"
    import json
    try:
        data = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        if data.get("type") != "service_account":
            return False, "GOOGLE_SERVICE_ACCOUNT_JSON is not valid service account JSON (missing type)"
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"GOOGLE_SERVICE_ACCOUNT_JSON is invalid JSON: {e}"


def validate_config() -> list[str]:
    """Return list of missing/invalid config keys. Empty list = OK."""
    errors = []
    if not WEBFLOW_API_TOKEN:
        errors.append("WEBFLOW_API_TOKEN")
    if not WEBFLOW_COLLECTION_ID:
        errors.append("WEBFLOW_COLLECTION_ID")
    if not WEBFLOW_SITE_DOMAIN:
        errors.append("WEBFLOW_SITE_DOMAIN")
    if not GA4_PROPERTY_ID:
        errors.append("GA4_PROPERTY_ID")
    if not GOOGLE_SHEET_ID:
        errors.append("GOOGLE_SHEET_ID")
    cred_ok, cred_err = _credentials_ok()
    if not cred_ok:
        errors.append(cred_err)
    if TRAFFIC_DAYS < 1:
        errors.append("TRAFFIC_DAYS (must be >= 1)")
    if REFRESH_DAYS < 1:
        errors.append("REFRESH_DAYS (must be >= 1)")
    return errors
