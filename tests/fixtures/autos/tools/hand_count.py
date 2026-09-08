"""Hand count for the two-month build fixtures; the numbers it prints are frozen in tests/test_autos_build.py.

Independent of absrisk.autos on purpose: plain regex over the raw XML text, no lxml, so a parser bug cannot hide
inside the expected values. Applies the exit rule of design/analysis-plan.md section 1a by hand:
  code in month 1 -> exit month 1 with that code; else code in month 2 -> exit month 2; else present in month 1
  but not month 2 -> absent (exit month 1); else censored.

Run from the repo root:  python tests/fixtures/autos/tools/hand_count.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FIX = ROOT / "tests/fixtures/autos"
REC = re.compile(r"<assets>(.*?)</assets>", re.S)
EXIT = {"4": "chargeoff", "1": "prepay", "3": "repurchase", "2": "other", "5": "other", "99": "other"}


def field(rec: str, name: str) -> str | None:
    m = re.search(rf"<{name}>([^<]*)</{name}>", rec)  # first occurrence, so repeated elements keep the first
    return m.group(1).strip() if m else None


def load(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    out = {}
    for r in REC.findall(text):
        out[field(r, "assetNumber")] = r
    return out


def count(slug: str, m1: str, m2: str) -> dict:
    a = load(FIX / slug / f"{m1}.xml")
    b = load(FIX / slug / f"{m2}.xml")
    exit_types: Counter[str] = Counter()
    exit_codes: Counter[str] = Counter()
    months = Counter()
    max_dpd_ge30 = 0
    for aid, r1 in a.items():
        r2 = b.get(aid)
        months[2 if r2 else 1] += 1
        c1, c2 = field(r1, "zeroBalanceCode"), (field(r2, "zeroBalanceCode") if r2 else None)
        if c1:
            t, c = EXIT.get(c1, "other"), c1
        elif c2:
            t, c = EXIT.get(c2, "other"), c2
        elif r2 is None:
            t, c = "absent", None
        else:
            t, c = "censored", None
        exit_types[t] += 1
        if c:
            exit_codes[c] += 1
        dpds = [int(x) for x in (field(r1, "currentDelinquencyStatus"), field(r2, "currentDelinquencyStatus") if r2 else None)
                if x not in (None, "")]
        if dpds and max(dpds) >= 30:
            max_dpd_ge30 += 1
    new_in_b = len(set(b) - set(a))
    return {
        "n_month1": len(a), "n_month2": len(b), "n_loans": len(set(a) | set(b)), "new_in_month2": new_in_b,
        "months_observed": {str(k): v for k, v in sorted(months.items())},
        "exit_type_counts": dict(exit_types), "exit_code_counts": dict(exit_codes),
        "n_max_dpd_ge30": max_dpd_ge30,
        "subvented_first_values_month1": dict(Counter(field(r, "subvented") for r in a.values())),
        "score_zero_month1": sum(1 for r in a.values() if field(r, "obligorCreditScore") in ("0", "", None)),
    }


if __name__ == "__main__":
    res = {slug: count(slug, "2026-06", "2026-07") for slug in ("sdart-2026-1", "carmax-2026-2", "copar-2025-1")}
    print(json.dumps(res, indent=1))
