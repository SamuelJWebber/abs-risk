"""One HTTP session for every fetcher. Identifies itself to EDGAR, throttles, retries, never hangs.

SEC fair-access rules: declare a User-Agent that names the project and a way to reach it, stay under
10 requests per second (we cap at 5), never disguise as a browser. Set ABSRISK_CONTACT to append an
email address to the User-Agent if the SEC ever asks for one.

The SEC's limit is per user, not per process. Jobs that fetch in parallel under one User-Agent (autos-build runs
two deal jobs at once) split the project's 5 a second between them with ABSRISK_MAX_RPS (REVIEW.md R2-12); it can
lower the rate, never raise it.
"""

from __future__ import annotations

import os
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__

DEFAULT_TIMEOUT = 120
MAX_RPS = 5.0
MIN_INTERVAL = 1.0 / MAX_RPS  # seconds between requests, 5/s


def min_interval() -> float:
    """Seconds between requests in this process: 1 / ABSRISK_MAX_RPS, never faster than the project's 5 a second."""
    raw = os.environ.get("ABSRISK_MAX_RPS", "").strip()
    try:
        rps = float(raw) if raw else MAX_RPS
    except ValueError:
        raise ValueError(f"ABSRISK_MAX_RPS={raw!r} is not a number") from None
    if not rps > 0:
        raise ValueError(f"ABSRISK_MAX_RPS={raw!r} must be positive")
    return 1.0 / min(rps, MAX_RPS)


class _ThrottledAdapter(HTTPAdapter):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._lock = threading.Lock()
        self._last = 0.0
        self.interval = min_interval()

    def send(self, request, **kwargs):  # type: ignore[override]
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        with self._lock:
            wait = self._last + self.interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        return super().send(request, **kwargs)


def user_agent() -> str:
    """SEC format only: `<name> <contact>`. Verified 2026-09-08 on a GitHub runner (scripts/scout/ua_diag.py, removed
    on 2026-11-09 because it still sent the refused forms; it is in git history before commit 6a18549):
    any User-Agent carrying a URL in parentheses is refused as an "Undeclared Automated Tool" on every SEC
    host; `abs-risk contact@example.com` and `Name abs-risk contact@example.com` are accepted everywhere.
    Without ABSRISK_CONTACT the string still names the project, and EDGAR will refuse it."""
    name = os.environ.get("ABSRISK_NAME", "").strip()
    contact = os.environ.get("ABSRISK_CONTACT", "").strip()
    return " ".join(p for p in (name, f"abs-risk/{__version__}", contact) if p)


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = _ThrottledAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = user_agent()
    session.headers["Accept-Encoding"] = "gzip, deflate"
    return session
