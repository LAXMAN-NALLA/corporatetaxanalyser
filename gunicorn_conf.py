# gunicorn_conf.py

import os

# Server socket
host = os.environ.get("HOST", "0.0.0.0")
port = os.environ.get("PORT", "8000")
bind = f"{host}:{port}"

# Worker processes
workers = int(os.environ.get("WEB_CONCURRENCY", 3))
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout setting (THIS IS THE FIX)
# The number of seconds to wait for a worker to send a response.
# Default is 30s. We are increasing it to 2 minutes.
timeout = 120

# Logging
loglevel = os.environ.get("LOG_LEVEL", "info")
accesslog = "-"
errorlog = "-"