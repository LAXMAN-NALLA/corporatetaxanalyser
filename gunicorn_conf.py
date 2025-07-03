# gunicorn_conf.py

import os

# Server socket
# Gunicorn will listen on this host and port. Render provides the PORT env var.
host = os.environ.get("HOST", "0.0.0.0")
port = os.environ.get("PORT", "8000")
bind = f"{host}:{port}"

# Worker processes
# The number of worker processes to spawn. A good starting point is (2 x $num_cores) + 1
workers = int(os.environ.get("WEB_CONCURRENCY", 3))
worker_class = "uvicorn.workers.UvicornWorker"

# Logging
loglevel = os.environ.get("LOG_LEVEL", "info")
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr