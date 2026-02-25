# Google-Native Fallback (Apps Script + Google Sheet)

This option avoids Railway/Render and gives your content manager a button directly in Google Sheets.

## What this gives you

- Manual refresh from a menu button in the sheet
- Automatic daily refresh using a time trigger
- No local machine required
- Everything managed in Google (Apps Script + Sheet + service account)

## Tradeoffs vs Python cloud app

- Pros: simpler for non-technical users, no external hosting
- Cons: Apps Script runtime/time limits and less control for complex retry logic

## Setup steps

1. Open your Google Sheet.
2. Click `Extensions` -> `Apps Script`.
3. Create script properties (`Project Settings` -> `Script properties`) for:
   - `WEBFLOW_API_TOKEN`
   - `WEBFLOW_COLLECTION_ID`
   - `WEBFLOW_SITE_DOMAIN`
   - `WEBFLOW_URL_PREFIX`
   - `GA4_PROPERTY_ID`
   - `SHEET_NAME` (for example `Article Traffic`)
   - `REFRESH_DAYS` (for example `7`)
4. In Webflow and GA4, confirm the same tokens/IDs you currently use in Python.
5. Paste Apps Script code (below), save, then run the setup function once to authorize.
6. Create a daily trigger in Apps Script for unattended updates.

## Suggested Apps Script structure

Use this as a blueprint (high-level structure, not a full drop-in):

```javascript
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Article Sync")
    .addItem("Refresh Article Data", "runSync")
    .addToUi();
}

function runSync() {
  const cfg = getConfig_();
  const articles = fetchWebflowArticles_(cfg);
  const recent = filterRecentArticles_(articles, cfg.refreshDays);
  const traffic = fetchGa4ForPaths_(cfg, recent.map(a => a.path));
  const mergedRows = mergeRows_(articles, traffic);
  writeSheet_(cfg.sheetName, mergedRows);
}
```

## Data columns to match current Python output

Keep the same layout so stakeholders see identical output:

- `Title`
- `Publish Date`
- `Pageviews`
- `URL`
- `Sessions`
- `Users`

## Trigger setup (daily)

1. In Apps Script: click clock icon (`Triggers`).
2. Add trigger for `runSync`.
3. Choose `Time-driven` -> `Day timer` -> select time window (for example morning ET).

## Operational notes

- Add a top-row `Last Updated: YYYY-MM-DD HH:MM` value, same as Python version.
- Guard against overlapping runs with a script lock (`LockService`) so two runs cannot overlap.
- Add retries for Webflow and GA4 HTTP calls with small exponential backoff.
- Log concise error messages to `Executions` so failures are diagnosable.

## Recommendation

Keep Python + Railway as your primary production path (more robust retries and diagnostics), and keep this Google-native approach as a fallback if your content workflow prefers living entirely in Google Sheets.
