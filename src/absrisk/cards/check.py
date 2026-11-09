"""The alert contract for the unattended card refresh (REVIEW.md R1-3).

`absrisk cards parse` logs a filing it cannot read and carries on, which is right for a corpus with three known bad
COMET statements, but it also meant a trust whose new layout broke the parser stayed a month behind while the
weekly run went green. This check turns those cases into a failed run, which GitHub emails about:

  failure   the parse-failure log lists a filing that the committed copy does not (a new parse failure, or a new
            month filed twice with different numbers);
  failure   a trust's latest month trails the newest trust's by more than `max_lag` calendar months;
  warning   a trust's prospectus score-mix snapshot is more than `max_mix_age` months older than the newest month.

The snapshot age is a warning, not a failure: a trust that issues no notes files no prospectus (Citi's newest is
from March 2025), so failing on age would turn every weekly run red with nothing anyone could fix. It is printed
in the run log and on the cards page instead.
"""

from __future__ import annotations

import csv
import io
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

MAX_LAG_MONTHS = 1
MAX_MIX_AGE_MONTHS = 18


@dataclass
class CheckResult:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _month_number(ts) -> int:
    ts = pd.Timestamp(ts)
    return ts.year * 12 + ts.month - 1


def read_failure_log(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text))) if text.strip() else []


def committed_failure_log(path: Path, repo: Path | None = None, rev: str = "HEAD") -> str:
    """The failure log as committed at `rev`, or '' when the file is not in that commit."""
    repo = Path(repo) if repo is not None else Path.cwd()
    rel = Path(path)
    rel = rel.relative_to(repo) if rel.is_absolute() else rel
    r = subprocess.run(["git", "show", f"{rev}:{rel.as_posix()}"], cwd=repo, capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else ""


def new_failures(now: list[dict], before: list[dict]) -> list[dict]:
    """Rows of the current failure log whose (trust, accession) the committed log does not have."""
    seen = {(r.get("trust", ""), r.get("accession", "")) for r in before}
    return [r for r in now if (r.get("trust", ""), r.get("accession", "")) not in seen]


def trailing_trusts(monthly: pd.DataFrame, max_lag: int = MAX_LAG_MONTHS) -> list[tuple[str, str, int]]:
    """(trust, latest month, months behind the newest trust) for every trust more than `max_lag` behind."""
    if monthly.empty:
        return []
    latest = pd.to_datetime(monthly["period_end"]).groupby(monthly["trust"]).max()
    newest = max(_month_number(t) for t in latest)
    out = []
    for trust, t in latest.items():
        lag = newest - _month_number(t)
        if lag > max_lag:
            out.append((str(trust), pd.Timestamp(t).strftime("%Y-%m"), lag))
    return out


def stale_mixes(composition: pd.DataFrame, monthly: pd.DataFrame,
                max_age: int = MAX_MIX_AGE_MONTHS) -> list[tuple[str, str, int]]:
    """(trust, snapshot date, age in months against the newest monthly row) for every FICO snapshot older than
    `max_age`; only the newest snapshot of each trust counts."""
    if composition.empty or monthly.empty:
        return []
    fico = composition[composition["table"] == "fico"]
    newest = _month_number(pd.to_datetime(monthly["period_end"]).max())
    out = []
    for trust, g in fico.groupby("trust"):
        if trust not in set(monthly["trust"]):
            continue
        as_of = pd.to_datetime(g["as_of"]).max()
        age = newest - _month_number(as_of)
        if age > max_age:
            out.append((str(trust), as_of.strftime("%Y-%m-%d"), age))
    return out


def run_check(monthly: pd.DataFrame, failures_now: list[dict], failures_before: list[dict],
              composition: pd.DataFrame | None = None, max_lag: int = MAX_LAG_MONTHS,
              max_mix_age: int = MAX_MIX_AGE_MONTHS) -> CheckResult:
    res = CheckResult()
    for r in new_failures(failures_now, failures_before):
        res.failures.append(f"new parse failure: {r.get('trust')} {r.get('accession')}: {r.get('error', '')[:200]}")
    for trust, last, lag in trailing_trusts(monthly, max_lag):
        res.failures.append(f"{trust} ends at {last}, {lag} months behind the newest trust (allowed: {max_lag})")
    if composition is not None:
        for trust, as_of, age in stale_mixes(composition, monthly, max_mix_age):
            res.warnings.append(f"{trust} score mix is from {as_of}, {age} months before the newest month "
                                f"(over {max_mix_age}); every residual for {trust} rests on it")
    return res
