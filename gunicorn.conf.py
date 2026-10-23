"""Production server settings, shared by Docker, Render, Railway and Replit.

Every host tells the app which port to listen on through the PORT
environment variable (Render and Railway set it; Replit uses 8080), so the
port is read here instead of hardcoded in the Dockerfile.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# One process with several threads: free hosts give ~512 MB of RAM, and a
# single process keeps the in-memory price cache and rate limiter shared by
# every request (two processes would each have their own copy).
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# A first-time analysis of many tickers waits on Yahoo Finance; gunicorn's
# default 30-second timeout could kill it mid-request and show a 502 page.
timeout = 120
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
