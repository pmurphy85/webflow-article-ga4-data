"""
Minimal web app for Webflow Article GA4 Traffic Tracker.
One page with a "Refresh article data" button. Protected by TRIGGER_TOKEN (in URL or form).
Streams sync log to the browser in real time so you see output even if the request is killed later.
"""
import html
import os
import sys
import threading
import time
import traceback
from queue import Empty, Queue

from flask import Flask, request, render_template_string, Response, stream_with_context, jsonify

from config import get_safe_diagnostics, validate_config
from main import main as run_sync

app = Flask(__name__)
APP_START_TS = time.time()
RUN_LOCK = threading.Lock()
RUN_STATE_LOCK = threading.Lock()
RUN_STATE = {
    "running": False,
    "started_at": None,
    "last_status": "idle",
    "last_exit_code": None,
    "last_duration_seconds": None,
    "last_finished_at": None,
}

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

# Streaming: send log to browser as it happens so you see output even if request is killed
STREAM_HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sync in progress</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    .log { background: #f5f5f5; padding: 1rem; margin-top: 1rem; white-space: pre-wrap; font-size: 0.875rem; }
    a { color: #06c; }
  </style>
</head>
<body>
  <h1>Sync in progress...</h1>
  <p><strong>Log streams below. If it stops, the last line is where it failed.</strong></p>
  <p><a href="{{ back_url }}">Back</a></p>
  <pre class="log">"""

STREAM_HTML_TAIL = """</pre>
</body>
</html>"""


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


@app.route("/health")
def health():
    """Safe diagnostics endpoint (no secret values)."""
    errors = validate_config()
    with RUN_STATE_LOCK:
        run_state = dict(RUN_STATE)
    payload = {
        "status": "ok" if not errors else "error",
        "uptime_seconds": int(time.time() - APP_START_TS),
        "config_errors": errors,
        "diagnostics": get_safe_diagnostics(),
        "run_state": run_state,
    }
    return jsonify(payload), (200 if not errors else 500)


@app.route("/run", methods=["POST", "GET"])
def run():
    if not _token_ok():
        return "Forbidden", 403
    if not RUN_LOCK.acquire(blocking=False):
        return (
            "Sync already in progress. Please wait for it to finish and try again.",
            409,
        )
    token = request.args.get("token") or request.form.get("token", "")
    back_url = "/" + (f"?token={token}" if token else "")

    log_queue = Queue()
    exit_code_ref = [0]
    status_ref = ["running"]
    failed_stage_ref = ["unknown"]
    started_ts = time.time()
    with RUN_STATE_LOCK:
        RUN_STATE["running"] = True
        RUN_STATE["started_at"] = int(started_ts)
        RUN_STATE["last_status"] = "running"
        RUN_STATE["last_exit_code"] = None

    class QueueWriter:
        def write(self, s):
            if s:
                log_queue.put(s)
        def flush(self):
            pass

    def run_sync_in_thread():
        old_stdout, old_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = sys.stderr = QueueWriter()
            print("Starting sync...")
            failed_stage_ref[0] = "main.sync"
            run_sync()
            exit_code_ref[0] = 0
            status_ref[0] = "succeeded"
            failed_stage_ref[0] = ""
        except SystemExit as e:
            exit_code_ref[0] = e.code if isinstance(e.code, int) else 1
            status_ref[0] = "failed"
            if not failed_stage_ref[0] or failed_stage_ref[0] == "unknown":
                failed_stage_ref[0] = "system_exit"
        except Exception as e:
            exit_code_ref[0] = 1
            status_ref[0] = "failed"
            if not failed_stage_ref[0] or failed_stage_ref[0] == "unknown":
                failed_stage_ref[0] = "unhandled_exception"
            QueueWriter().write(f"Error: {e}\n")
            QueueWriter().write(traceback.format_exc())
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
            ended_ts = time.time()
            duration = int(ended_ts - started_ts)
            with RUN_STATE_LOCK:
                RUN_STATE["running"] = False
                RUN_STATE["last_status"] = status_ref[0]
                RUN_STATE["last_exit_code"] = exit_code_ref[0]
                RUN_STATE["last_duration_seconds"] = duration
                RUN_STATE["last_finished_at"] = int(ended_ts)
            RUN_LOCK.release()
            log_queue.put(None)

    thread = threading.Thread(target=run_sync_in_thread)
    thread.start()

    def generate():
        yield render_template_string(STREAM_HTML_HEAD, back_url=back_url)
        while True:
            try:
                chunk = log_queue.get(timeout=0.3)
            except Empty:
                yield ""
                continue
            if chunk is None:
                break
            yield html.escape(chunk)
        # Final status line
        status = status_ref[0]
        duration = int(time.time() - started_ts)
        final_lines = [f"\n\n--- {status.upper()} ---"]
        final_lines.append(f"exit_code={exit_code_ref[0]}")
        final_lines.append(f"duration_seconds={duration}")
        if status != "succeeded":
            final_lines.append(f"failed_stage={failed_stage_ref[0]}")
        yield "\n".join(final_lines) + "\n"
        yield STREAM_HTML_TAIL

    return Response(
        stream_with_context(generate()),
        mimetype="text/html",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
