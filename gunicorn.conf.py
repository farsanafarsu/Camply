"""Gunicorn settings, picked up automatically when gunicorn starts in this folder.

Threads let one small instance serve a page and its CSS, JS and icons at the same time
instead of one after another, and keep a single shared MongoDB client warm.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
keepalive = 5
timeout = 60
# Load the app once before forking, so the admin-setup step runs once per deploy.
preload_app = True
accesslog = "-"
