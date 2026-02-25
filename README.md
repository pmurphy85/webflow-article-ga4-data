# Webflow Article GA4 Traffic Tracker

Pulls article URLs and publish dates from Webflow CMS, fetches their traffic from GA4 for recently published articles, and writes the combined data to a Google Sheet. Older articles keep their last-known traffic from the sheet.

- **Local / scheduled:** Run `python main.py` (or `run_scheduled.bat` on Windows). Uses `.env` and optional `SERVICE_ACCOUNT_FILE` path.
- **Web trigger:** Run the Flask app and use the one-button page so someone can refresh the sheet from a browser (e.g. when deployed to Railway or Render).

## Local setup

1. Copy `.env.example` to `.env` and fill in Webflow, GA4, Google Sheet, and `SERVICE_ACCOUNT_FILE` (path to your service account JSON).
2. `pip install -r requirements.txt`
3. Run: `python main.py`

## Web app (local)

```bash
python app.py
```

Open http://localhost:5000 . Optional: set `TRIGGER_TOKEN` in `.env` and use `http://localhost:5000?token=your-token` so only people with the link can run the sync.

## Deploy to Railway or Render

So the script runs when your computer is off and your content person can trigger it with one button:

1. **Push this repo to GitHub** (ensure `.env` is not committed).

2. **Create a new project** on [Railway](https://railway.app) or [Render](https://render.com) and connect the GitHub repo.

3. **Set environment variables** in the host’s dashboard. Use the same names as in `.env.example`.

   Required:

   - `WEBFLOW_API_TOKEN`
   - `WEBFLOW_COLLECTION_ID`
   - `WEBFLOW_SITE_DOMAIN` (example: `https://www.prizepicks.com`)
   - `WEBFLOW_URL_PREFIX` (example: `/playbook-article/`)
   - `GA4_PROPERTY_ID`
   - `GOOGLE_SHEET_ID`
   - `SHEET_NAME` (example: `Article Traffic`)
   - `TRIGGER_TOKEN` (long random secret string)
   - **Exactly one** credentials source:
     - Preferred cloud option: `GOOGLE_SERVICE_ACCOUNT_JSON` (entire JSON pasted as one value), or
     - Alternative cloud option: `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` (base64 encoded JSON), or
     - Local only: `SERVICE_ACCOUNT_FILE` path on your machine.

   Optional:

   - `TRAFFIC_DAYS` (default `30`)
   - `REFRESH_DAYS` (default `7`)
   - `BACKFILL_YEAR` (one-time full-year backfill)

4. **Deploy.** Railway and Render will use the `Procfile` (`web: gunicorn ...`) and `requirements.txt` automatically.

5. **Verify deployment health first** by opening:
   - `https://your-app.up.railway.app/health?token=your-long-random-string`
   - `status: ok` means config is valid.
   - If `status: error`, check `config_errors` and fix env vars in Railway.

6. **Share the link with your content person.** Give them:
   - `https://your-app.up.railway.app/?token=your-long-random-string`
   - They bookmark it and click **Refresh article data**.
   - Tell them not to share the URL (token is secret).

## Scheduled daily runs (cloud)

Use a URL monitor/scheduler (for example UptimeRobot, EasyCron, or another scheduler your team uses) to hit:

- `GET https://your-app.up.railway.app/run?token=your-long-random-string`

Recommended schedule:

- Once daily, off-peak (for example 6:00 AM ET).
- Keep manual button available for ad hoc refreshes.

Important behavior:

- The app now has a run lock. If one sync is already running, a second trigger returns HTTP `409` instead of overlapping runs.
- Every run ends with deterministic summary lines (`SUCCEEDED`/`FAILED`, `exit_code`, `duration_seconds`, and `failed_stage` when failed).

## Troubleshooting checklist

1. Open `/health` and confirm `status: ok`.
2. Confirm service account has:
   - GA4 read access to the GA4 property
   - Editor access to the Google Sheet
3. Confirm `WEBFLOW_URL_PREFIX` matches your actual article URL path.
4. If GA4 values look like zeros, verify the GA4 property is the same property tracking the site path data.
5. For first historical load, temporarily set a wider `REFRESH_DAYS` or use one-time `BACKFILL_YEAR`.

## Google-native fallback

If you prefer a fully Google-managed option (button inside Google Sheets + scheduled trigger), see:

- `README_google_native.md`

## Security

- All secrets (Webflow, GA4, Sheets, service account) belong only in environment variables, never in the repo or in the page.
- Use `TRIGGER_TOKEN` so only people with the link can trigger the sync. The page never displays or sends API keys.
