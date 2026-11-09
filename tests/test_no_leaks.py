"""This repository is public: tracked text carries no local paths, sync folders or personal email addresses.

REVIEW.md R1-2: 22 tracked files held absolute Windows paths that named the account, the cloud-sync folder and a
private sibling project, in a commit whose message said the tree had been scanned. A manual read missed them once,
so the check is a test. R1-16: commits now carry the GitHub noreply address; a test keeps it that way.

The patterns are written so that none of them matches its own source text, and no private name appears here.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

SEP = r"(?:/|\\{1,2})"
PATTERNS = {
    "Windows user-profile path": re.compile(r"[A-Za-z]:" + SEP + r"Users" + SEP + r"[^\s/\\\"'<>]"),
    "AppData folder": re.compile(r"\bAppData" + SEP),
    "project-folder slug of a user path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]--Users-[A-Za-z0-9]"),
    "OneDrive folder": re.compile(r"\bOneDrive(?:" + SEP + r"|-[A-Z])"),
    "Unix home path": re.compile(r"(?<![\w.~-])/(?:home|Users)/[a-z][\w.-]*/"),
}
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
ALLOWED_EMAIL = re.compile(r"@(?:users\.noreply\.github\.com|noreply\.github\.com|example\.(?:com|org|net)|anthropic\.com)$",
                           re.I)

# One known line waits on the user: CLAUDE.md is the assistants' own instruction file, and an assistant may not edit it
# on a workflow's say-so (HANDOFF.md, "Needs the user"). The exception is this one line, not the file.
KNOWN = {("CLAUDE.md", "Windows user-profile path", "credit-dashboard); do not merge them.")}

# Verbatim third-party filings: byte-checked by other tests, never edited, so not held to the email rule.
THIRD_PARTY = ("tests/fixtures/",)


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [p for p in out.decode("utf-8").split("\0") if p]


def scan_text(text: str, path: str = "") -> list[tuple[str, str]]:
    """(rule, line) for every leak in `text`; emails are checked only outside verbatim third-party files."""
    hits = []
    for line in text.splitlines():
        for name, pat in PATTERNS.items():
            if pat.search(line):
                hits.append((name, line.strip()))
        if not path.startswith(THIRD_PARTY):
            for m in EMAIL.finditer(line):
                if not ALLOWED_EMAIL.search(m.group(0)):
                    hits.append(("email address", line.strip()))
    return hits


def scan_file(path: str) -> list[tuple[str, str]]:
    data = (REPO / path).read_bytes()
    if b"\0" in data[:8192]:
        return []                                   # binary (parquet and the like)
    return scan_text(data.decode("utf-8", errors="replace"), path)


def test_tracked_text_has_no_local_paths_or_personal_emails():
    found = []
    for path in tracked_files():
        if not (REPO / path).is_file():
            continue
        for name, line in scan_file(path):
            if any(path == kp and name == kn and ks in line for kp, kn, ks in KNOWN):
                continue
            found.append(f"{path}: {name}: {line[:160]}")
    assert not found, "leaks in tracked files:\n" + "\n".join(found)


def test_the_scanner_catches_planted_leaks(tmp_path):
    """Each rule fires on a planted example; the examples are assembled at run time so this file stays clean."""
    user, folder = "someone", "Sync"
    planted = {
        "Windows user-profile path": "C:" + "\\" + "Users" + "\\" + user + "\\" + "code",
        "AppData folder": "x/" + "App" + "Data/" + "Local/Temp",
        "project-folder slug of a user path": "c--" + "Users-" + user + "-Documents",
        "OneDrive folder": "One" + "Drive" + "/" + folder,
        "Unix home path": "/" + "home/" + user + "/data",
    }
    for name, text in planted.items():
        assert name in {n for n, _ in scan_text(f"read from {text} today")}, name
    assert scan_text("mail " + user + "@" + "gmail.com")[0][0] == "email address"
    assert scan_text("bot abs-risk-bot@users.noreply.github.com and contact@example.com") == []
    # the forms this repository legitimately uses do not trip it
    assert scan_text("data/raw/cards/<slug>/<accession>/ and the <scratch>/ placeholder, C:[/\\]Users as a regex") == []


def test_commits_since_the_review_carry_noreply_addresses():
    """No commit after REVIEW.md round 1 (6a18549) uses a personal address as author or committer."""
    try:
        shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=REPO, capture_output=True,
                                 text=True, check=True).stdout.strip()
        if shallow == "true":
            pytest.skip("shallow clone")
        subprocess.run(["git", "cat-file", "-e", "6a18549^{commit}"], cwd=REPO, capture_output=True, check=True)
        out = subprocess.run(["git", "log", "6a18549..HEAD", "--format=%h %ae %ce"], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("history before this review is not available")
    bad = [ln for ln in out.splitlines() for e in ln.split()[1:] if not ALLOWED_EMAIL.search(e)]
    assert not bad, "commits with a personal email address:\n" + "\n".join(bad)
