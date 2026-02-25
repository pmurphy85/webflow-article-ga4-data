"""
Webflow Article GA4 Traffic Tracker

Pulls article URLs and publish dates from Webflow CMS, fetches their traffic from GA4
for recently published articles only, and writes the combined data to a Google Sheet.
Older articles keep their last-known traffic from the sheet. Run manually or on a schedule.
"""
import sys
from datetime import datetime, timedelta

from config import (
    BACKFILL_YEAR,
    HYDRATE_MISSING_LIMIT,
    HYDRATE_ZERO_OLDER,
    REFRESH_DAYS,
    validate_config,
)
from webflow_client import get_articles
from ga4_client import fetch_traffic_by_path
from sheets_writer import read_article_traffic, write_article_traffic


def _publish_year(article: dict) -> int | None:
    """Return publish date year (e.g. 2025) or None if unparseable."""
    pub_date, ok = _parse_publish_date(article.get("publish_date", "") or "")
    return pub_date.year if ok else None


def _parse_publish_date(s: str):
    """Return (date, True) if s is valid date (YYYY-MM-DD or YYYY-MM-DD HH:MM) else (None, False)."""
    if not s or not (s := s.strip()):
        return None, False
    if s.endswith(" ET"):
        s = s[:-3].strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:16] if len(s) > 16 else s, fmt)
            return dt.date(), True
        except ValueError:
            continue
    return None, False


def _is_recent(article: dict) -> bool:
    """True if article publish_date is within last REFRESH_DAYS."""
    pub_date, ok = _parse_publish_date(article.get("publish_date", "") or "")
    if not ok:
        return False
    cutoff = (datetime.now() - timedelta(days=REFRESH_DAYS)).date()
    return pub_date >= cutoff


def _is_zero_history(prev: dict) -> bool:
    """True when an existing sheet row has all traffic metrics at zero."""
    return (
        int(prev.get("Sessions", 0)) == 0
        and int(prev.get("Users", 0)) == 0
        and int(prev.get("Pageviews", 0)) == 0
    )


def main() -> None:
    errors = validate_config()
    if errors:
        print("Missing or invalid config in .env:")
        for e in errors:
            print(f"  - {e}")
        print("\nCopy .env.example to .env and fill in your values.")
        sys.exit(1)

    backfill_mode = bool(BACKFILL_YEAR)
    if backfill_mode:
        try:
            backfill_year_int = int(BACKFILL_YEAR)
        except ValueError:
            print(f"Invalid BACKFILL_YEAR: {BACKFILL_YEAR}. Use a year e.g. 2025.")
            sys.exit(1)
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = f"{backfill_year_int}-01-01"
        print(f"Backfill mode: {BACKFILL_YEAR} articles only, GA4 range {start_date} to {end_date}.")

    print("Reading existing traffic from sheet...")
    existing_sheet = read_article_traffic()
    print(f"Loaded traffic for {len(existing_sheet)} URLs from sheet.")

    print("Fetching articles from Webflow...")
    articles = get_articles()
    if not articles:
        print("No articles found in the collection. Check WEBFLOW_COLLECTION_ID and URL prefix.")
        sys.exit(1)
    print(f"Found {len(articles)} articles.")

    if backfill_mode:
        articles = [a for a in articles if _publish_year(a) == backfill_year_int]
        if not articles:
            print(f"No articles published in {BACKFILL_YEAR}. Nothing to backfill.")
            sys.exit(0)
        print(f"Filtered to {len(articles)} articles published in {BACKFILL_YEAR}.")
        paths_recent = [a["path"] for a in articles]
        traffic = fetch_traffic_by_path(paths_recent, start_date=start_date, end_date=end_date) if paths_recent else {}
        rows = []
        for a in articles:
            path = a["path"]
            t = traffic.get(path, {})
            rows.append({
                "Title": a["title"],
                "URL": a["url"],
                "Publish Date": a["publish_date"],
                "Sessions": t.get("sessions", 0),
                "Users": t.get("totalUsers", 0),
                "Pageviews": t.get("screenPageViews", 0),
            })
    else:
        recent_articles = [a for a in articles if _is_recent(a)]
        paths_recent = [a["path"] for a in recent_articles]
        traffic = {}
        if paths_recent:
            print(f"Fetching GA4 traffic for {len(paths_recent)} recent articles (published in last {REFRESH_DAYS} days)...")
            traffic = fetch_traffic_by_path(paths_recent)
        else:
            print("No recent articles; skipping GA4.")

        # One-time historical hydration:
        # 1) older articles with no row in the sheet
        # 2) optional: older articles with existing row but all-zero metrics
        older_missing = [a for a in articles if (not _is_recent(a)) and (a["url"] not in existing_sheet)]
        older_zero = []
        if HYDRATE_ZERO_OLDER:
            older_zero = [
                a
                for a in articles
                if (not _is_recent(a))
                and (a["url"] in existing_sheet)
                and _is_zero_history(existing_sheet.get(a["url"], {}))
            ]

        hydrate_pool = {}
        for a in older_missing + older_zero:
            hydrate_pool[a["url"]] = a
        hydrate_candidates_all = list(hydrate_pool.values())
        hydrate_candidates_all.sort(
            key=lambda a: _parse_publish_date(a.get("publish_date", "") or "")[0] or datetime.min.date(),
            reverse=True,
        )
        hydrate_candidates = (
            hydrate_candidates_all[:HYDRATE_MISSING_LIMIT] if HYDRATE_MISSING_LIMIT > 0 else []
        )
        historical_traffic = {}
        if hydrate_candidates:
            hydro_end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            # GA4 Data API rejects dates earlier than the supported lower bound.
            hydro_start = "2015-08-14"
            print(
                f"Hydrating all-time GA4 for {len(hydrate_candidates)} older articles "
                f"(missing rows: {len(older_missing)}, zero rows: {len(older_zero)})..."
            )
            historical_traffic = fetch_traffic_by_path(
                [a["path"] for a in hydrate_candidates],
                start_date=hydro_start,
                end_date=hydro_end,
            )
            remaining = len(hydrate_candidates_all) - len(hydrate_candidates)
            if remaining > 0:
                print(
                    f"Hydration limit reached; {remaining} older articles still need hydration. "
                    "They will be hydrated on future runs."
                )
        elif hydrate_candidates_all and HYDRATE_MISSING_LIMIT == 0:
            print("Historical hydration disabled (HYDRATE_MISSING_LIMIT=0).")

        rows = []
        for a in articles:
            path = a["path"]
            url = a["url"]
            if _is_recent(a):
                t = traffic.get(path, {})
                rows.append({
                    "Title": a["title"],
                    "URL": url,
                    "Publish Date": a["publish_date"],
                    "Sessions": t.get("sessions", 0),
                    "Users": t.get("totalUsers", 0),
                    "Pageviews": t.get("screenPageViews", 0),
                })
            else:
                prev = existing_sheet.get(url, {})
                should_replace_from_hydration = (not prev) or (HYDRATE_ZERO_OLDER and _is_zero_history(prev))
                if should_replace_from_hydration and path in historical_traffic:
                    t = historical_traffic.get(path, {})
                    prev = {
                        "Sessions": t.get("sessions", 0),
                        "Users": t.get("totalUsers", 0),
                        "Pageviews": t.get("screenPageViews", 0),
                    }
                rows.append({
                    "Title": a["title"],
                    "URL": url,
                    "Publish Date": a["publish_date"],
                    "Sessions": prev.get("Sessions", 0),
                    "Users": prev.get("Users", 0),
                    "Pageviews": prev.get("Pageviews", 0),
                })

    def _sort_key(r):
        s = (r.get("Publish Date") or "").strip()
        # Strip " ET" if present for parsing
        if s.endswith(" ET"):
            s = s[:-3].strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s[:16] if len(s) > 16 else s, fmt)
                return dt
            except ValueError:
                continue
        return datetime.min  # invalid/empty at end when sorting desc

    rows.sort(key=_sort_key, reverse=True)

    print("Writing to Google Sheet...")
    write_article_traffic(rows)

    if backfill_mode:
        print(f"\nDone. Backfill: {len(rows)} articles for {BACKFILL_YEAR} with full-year traffic.")
    else:
        print(f"\nDone. GA4 refreshed: {len(paths_recent)} recent; {len(articles) - len(paths_recent)} historical (from sheet).")
    if rows:
        newest = rows[0]
        print(f"Newest (by publish date): \"{newest['Title']}\" — {newest['Sessions']} sessions.")


if __name__ == "__main__":
    main()
