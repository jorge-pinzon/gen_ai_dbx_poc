"""Production Gunicorn settings for the Flask application."""

import os


bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = int(os.getenv("WEB_THREADS", "4"))
worker_class = "gthread"
timeout = int(os.getenv("GUNICORN_TIMEOUT_SECONDS", "65"))
graceful_timeout = 30
keepalive = 5
# Flask emits the structured request-completion record; avoid a duplicate
# unstructured Gunicorn access line for every request.
accesslog = None
errorlog = "-"
capture_output = True
