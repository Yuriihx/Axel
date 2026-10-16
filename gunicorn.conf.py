"""Single-process server: AXEL uses process-local locks for JSON storage."""
import os

bind = "0.0.0.0:" + os.environ.get("PORT", "10000")
workers = 1
worker_class = "gthread"
threads = 4
timeout = 300
graceful_timeout = 300
keepalive = 5
preload_app = False
accesslog = None  # Avoid collecting URLs or accidental query-string secrets.
errorlog = "-"
loglevel = "warning"
