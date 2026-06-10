"""
keep_alive.py — Add this to your backend
=========================================
Pings itself every 13 minutes to prevent Render free tier sleep.
Import and call start_keep_alive() in main.py startup.
"""

import threading
import time
import logging
import os
import requests

logger = logging.getLogger(__name__)

def _ping_self():
    # Get own URL from env or default
    url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    while True:
        try:
            time.sleep(13 * 60)  # 13 minutes
            r = requests.get(f"{url}/", timeout=10)
            logger.info("Keep-alive ping: %s", r.status_code)
        except Exception as e:
            logger.warning("Keep-alive ping failed: %s", e)

def start_keep_alive():
    """Call this once at startup."""
    t = threading.Thread(target=_ping_self, daemon=True)
    t.start()
    logger.info("Keep-alive thread started")
