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


def personal_commit_addresses(repo: Path, since: str) -> list[str]:
    """'<hash> <author> <committer>' for every commit after `since` whose author or committer address is not a noreply
    (or example) address. Raises CalledProcessError when `since` is not in the history."""
    subprocess.run(["git", "cat-file", "-e", f"{since}^{{commit}}"], cwd=repo, capture_output=True, check=True)
    out = subprocess.run(["git", "log", f"{since}..HEAD", "--format=%h %ae %ce"], cwd=repo, capture_output=True,
                         text=True, check=True).stdout
    return [ln for ln in out.splitlines() if any(not ALLOWED_EMAIL.search(e) for e in ln.split()[1:])]


# Commit metadata is history: a bad address is undone only by rewriting public history. So this check runs locally
# and on every push by a person (.github/workflows/hygiene.yml), and the scheduled card refresh deselects it with
# `-m "not repo_hygiene"`: one commit from a machine without email privacy must not stop every refresh (REVIEW.md R2-6).
@pytest.mark.repo_hygiene
def test_commits_since_the_review_carry_noreply_addresses():
    """No commit after REVIEW.md round 1 (6a18549) uses a personal address as author or committer."""
    try:
        shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=REPO, capture_output=True,
                                 text=True, check=True).stdout.strip()
        if shallow == "true":
            pytest.skip("shallow clone")
        bad = personal_commit_addresses(REPO, "6a18549")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("history before this review is not available")
    assert not bad, "commits with a personal email address:\n" + "\n".join(bad)


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    import os

    e = {**os.environ, **(env or {})}
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=e).stdout.strip()


def test_a_planted_personal_commit_is_caught_and_the_refresh_does_not_run_the_check(tmp_path):
    """The check finds a commit made with an ordinary address; the refresh's test command deselects it."""
    import yaml

    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    bot = {"GIT_AUTHOR_NAME": "bot", "GIT_AUTHOR_EMAIL": "bot@users.noreply.github.com",
           "GIT_COMMITTER_NAME": "bot", "GIT_COMMITTER_EMAIL": "bot@users.noreply.github.com"}
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "base", env=bot)
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("b\n")
    _git(repo, "commit", "-q", "-am", "clean", env=bot)
    assert personal_commit_addresses(repo, base) == []
    person = "someone" + "@" + "mail" + "box.org"                     # assembled so this file stays clean
    (repo / "a.txt").write_text("c\n")
    _git(repo, "commit", "-q", "-am", "planted", env={**bot, "GIT_AUTHOR_EMAIL": person})
    bad = personal_commit_addresses(repo, base)
    assert len(bad) == 1 and person in bad[0]
    wf = yaml.safe_load((REPO / ".github" / "workflows" / "cards-refresh.yml").read_text(encoding="utf-8"))
    tests = [s for s in wf["jobs"]["refresh"]["steps"] if s.get("name") == "Tests"]
    assert len(tests) == 1 and "not repo_hygiene" in tests[0]["run"]
    hygiene = yaml.safe_load((REPO / ".github" / "workflows" / "hygiene.yml").read_text(encoding="utf-8"))
    on = hygiene.get("on", hygiene.get(True))                          # YAML 1.1 reads a bare `on` as True
    assert "push" in on and any("repo_hygiene" in str(s.get("run", "")) for s in hygiene["jobs"]["hygiene"]["steps"])
