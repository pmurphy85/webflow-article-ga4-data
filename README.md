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

3. **Set environment variables** in the host’s dashboard. Use the same names as in `.env.example`:
   - Webflow: `WEBFLOW_API_TOKEN`, `WEBFLOW_COLLECTION_ID`, `WEBFLOW_SITE_DOMAIN`, `WEBFLOW_URL_PREFIX`
   - Google: `GA4_PROPERTY_ID`, `GOOGLE_SHEET_ID`, `SHEET_NAME`
   - **Service account:** Paste the **entire contents** of your service account JSON file into one variable: `GOOGLE_SERVICE_ACCOUNT_JSON` (as a single-line string). Do not commit this value.
   - Optional: `TRAFFIC_DAYS`, `REFRESH_DAYS`, `BACKFILL_YEAR`
   - **Trigger protection:** Set `TRIGGER_TOKEN` to a long random string (e.g. generate a password). Only requests that include this token (in the URL or form) can run the sync.

4. **Deploy.** Railway and Render will use the `Procfile` (`web: gunicorn ...`) and `requirements.txt` automatically.

5. **Share the link with your content person.** Give them the app URL including the token, e.g. `https://your-app.up.railway.app/?token=your-long-random-string`. They bookmark it and click “Refresh article data” when they need the sheet updated. Tell them not to share the link (the token is secret).

## Security

- All secrets (Webflow, GA4, Sheets, service account) belong only in environment variables, never in the repo or in the page.
- Use `TRIGGER_TOKEN` so only people with the link can trigger the sync. The page never displays or sends API keys.
