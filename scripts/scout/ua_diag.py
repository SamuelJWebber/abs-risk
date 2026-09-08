"""Diagnose SEC EDGAR access from wherever this runs: which User-Agent formats and which hosts answer 200.

Prints one line per (client, user-agent, url) with the HTTP status and the page <title>. Never sends a browser
User-Agent. ABSRISK_CONTACT supplies the contact address; without it the contact variants are skipped.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

import requests

CONTACT = os.environ.get("ABSRISK_CONTACT", "").strip()
NAME = os.environ.get("ABSRISK_NAME", "Samuel Webber").strip()

UAS = {
    "project-only": "absrisk/0.1.0 research (+https://github.com/SamuelJWebber/abs-risk)",
}
if CONTACT:
    UAS.update({
        "sec-canonical": f"{NAME} {CONTACT}",
        "project+contact": f"absrisk/0.1.0 research (+https://github.com/SamuelJWebber/abs-risk) {CONTACT}",
        "short+contact": f"abs-risk {CONTACT}",
        "name-project-contact": f"{NAME} abs-risk {CONTACT}",
    })

URLS = [
    "https://data.sec.gov/submissions/CIK0001163321.json",
    "https://www.sec.gov/files/company_tickers.json",
    "https://www.sec.gov/Archives/edgar/data/1163321/",
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001163321&type=10-D&output=atom",
    "https://efts.sec.gov/LATEST/search-index?q=%22Capital%20One%20Multi-asset%20Execution%20Trust%22&forms=10-D",
]


def title(body: str) -> str:
    m = re.search(r"<title>(.*?)</title>", body, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:80] if m else body[:60].replace("\n", " ")


def via_requests(ua: str, url: str) -> tuple[str, str]:
    try:
        r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=30)
        return str(r.status_code), title(r.text)
    except Exception as e:  # noqa: BLE001
        return "ERR", str(e)[:80]


def via_curl(ua: str, url: str) -> tuple[str, str]:
    r = subprocess.run(["curl", "-s", "-A", ua, "--compressed", "-w", "\n%{http_code}", url],
                       capture_output=True, text=True, timeout=60)
    body, _, code = r.stdout.rpartition("\n")
    return code.strip(), title(body)


def main() -> int:
    ip = requests.get("https://api.ipify.org", timeout=20).text.strip()
    org = requests.get(f"https://ipinfo.io/{ip}/org", timeout=20).text.strip()
    print(f"egress ip {ip} org {org}")
    print(f"contact set: {'yes' if CONTACT else 'no'}")
    ok = 0
    for label, ua in UAS.items():
        for url in URLS:
            for client, fn in (("requests", via_requests), ("curl", via_curl)):
                code, t = fn(ua, url)
                ok += code == "200"
                print(f"{code:>4} {client:8} {label:22} {url}  | {t}", flush=True)
                time.sleep(0.5)
    print(f"total 200s: {ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
