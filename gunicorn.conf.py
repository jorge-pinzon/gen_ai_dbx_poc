"""Production Gunicorn settings for the Flask application."""

import os


bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
# Chat requests spend almost all their time waiting on Databricks, so threads
# are cheap concurrency. Keep workers low: conversation history is per worker.
threads = int(os.getenv("WEB_THREADS", "16"))
worker_class = "gthread"
# gthread workers use this as a heartbeat, not a per-request limit; keep it
# above the longest expected answer so busy workers are not recycled.
timeout = int(os.getenv("GUNICORN_TIMEOUT_SECONDS", "180"))
graceful_timeout = 30
keepalive = 5
# Flask emits the structured request-completion record; avoid a duplicate
# unstructured Gunicorn access line for every request.
accesslog = None
errorlog = "-"
capture_output = True


def post_worker_init(worker):
    """Start the OAuth token and citation cache before the first chat reaches this worker."""
    from mariner_genai_dbx.web import start_warm_up

    start_warm_up(worker.wsgi)
