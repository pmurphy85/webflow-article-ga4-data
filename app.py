"""
Minimal web app for Webflow Article GA4 Traffic Tracker.
One page with a "Refresh article data" button. Protected by TRIGGER_TOKEN (in URL or form).
"""
import os
import sys
import traceback
from io import StringIO

from flask import Flask, request, render_template_string

from main import main as run_sync

app = Flask(__name__)

TRIGGER_TOKEN = os.getenv("TRIGGER_TOKEN", "").strip()


def _token_ok() -> bool:
    """True if request has valid token (query or form)."""
    if not TRIGGER_TOKEN:
        return True  # no token configured: allow (e.g. local dev)
    return request.args.get("token") == TRIGGER_TOKEN or request.form.get("token") == TRIGGER_TOKEN


INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Refresh Article Traffic</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.25rem; }
    button { font-size: 1rem; padding: 0.5rem 1rem; cursor: pointer; }
    .log { background: #f5f5f5; padding: 1rem; margin-top: 1rem; white-space: pre-wrap; font-size: 0.875rem; }
    .success { color: #0a0; }
    .error { color: #c00; }
  </style>
</head>
<body>
  <h1>Article traffic sync</h1>
  <p>Updates the Google Sheet with Webflow articles and GA4 traffic.</p>
  <form method="post" action="{{ run_url }}">
    <input type="hidden" name="token" value="{{ token }}">
    <button type="submit">Refresh article data</button>
  </form>
</body>
</html>
"""

RESULT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sync {{ status }}</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    .log { background: #f5f5f5; padding: 1rem; margin-top: 1rem; white-space: pre-wrap; font-size: 0.875rem; }
    .success { color: #0a0; }
    .error { color: #c00; }
    a { color: #06c; }
  </style>
</head>
<body>
  <h1>Sync {{ status }}</h1>
  <p><a href="{{ back_url }}">Back</a></p>
  <pre class="log {{ log_class }}">{{ log_output }}</pre>
</body>
</html>
"""


@app.route("/")
def index():
    if not _token_ok():
        return "Forbidden", 403
    token = request.args.get("token", "")
    run_url = "/run"
    if token:
        run_url = f"/run?token={token}"
    return render_template_string(
        INDEX_HTML,
        run_url=run_url,
        token=token,
    )


@app.route("/run", methods=["POST", "GET"])
def run():
    if not _token_ok():
        return "Forbidden", 403
    log = StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = log
    exit_code = 0
    try:
        run_sync()
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        exit_code = 1
        log.write(f"Error: {e}\n")
        log.write(traceback.format_exc())
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    log_output = log.getvalue() or "(no output)"
    status = "succeeded" if exit_code == 0 else "failed"
    log_class = "success" if exit_code == 0 else "error"
    token = request.args.get("token") or request.form.get("token", "")
    back_url = "/" + (f"?token={token}" if token else "")
    return render_template_string(
        RESULT_HTML,
        status=status,
        log_output=log_output,
        log_class=log_class,
        back_url=back_url,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
