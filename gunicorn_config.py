import os


bind = "0.0.0.0:5000"

# Render-friendly defaults with env overrides.
cpu_count = int(os.getenv("RENDER_CPU_COUNT", os.cpu_count() or 1))
default_workers = max(2, min(4, cpu_count * 2))
workers = int(os.getenv("WEB_CONCURRENCY", str(default_workers)))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")
threads = int(os.getenv("GUNICORN_THREADS", "4"))

max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1200"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "120"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "90"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "10"))

# Use stdout/stderr on Render for centralized platform logs.
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
