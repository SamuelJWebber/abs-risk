"""Deal metadata (data/deals.csv) and the per-lender facts the fetcher and builder rely on.

Columns of data/deals.csv: deal, lender, cik, doc_prefix, name, depositor_cik, notes.

- `cik`: the CIK whose submissions JSON lists the deal's ABS-EE filings. For self-filed trusts (CarMax, Exeter,
  AmeriCredit, GM Financial, Ford, BMW, Toyota trusts) it is the trust; for depositor-filed shelves (Santander,
  Capital One, Honda, Nissan, Hyundai, World Omni, Ally, Carvana, Mercedes, VW, Harley) it is the depositor and
  `doc_prefix` picks the deal's filings out of the shelf by primary-document name (scout-autos section 11,
  "Design inputs for the fetcher"). Blank `cik` means: resolve on the runner by full-text search on `name`.
- `depositor_cik`: set for depositor-filed shelves; used when `cik` is blank and to derive `doc_prefix` when
  that is blank too (fetch.resolve_deal).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

DEALS_CSV = Path("data/deals.csv")

DEAL_COLUMNS = ["deal", "lender", "cik", "doc_prefix", "name", "depositor_cik", "notes"]


@dataclass
class Deal:
    deal: str
    lender: str
    cik: str = ""
    doc_prefix: str = ""
    name: str = ""
    depositor_cik: str = ""
    notes: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self.cik = _cik10(self.cik)
        self.depositor_cik = _cik10(self.depositor_cik)
        self.doc_prefix = (self.doc_prefix or "").strip().lower()
        self.lender = (self.lender or "").strip().lower()

    @property
    def depositor_filed(self) -> bool:
        """The filings sit in a depositor's shelf submissions and must be filtered by primary-document prefix."""
        return bool(self.depositor_cik) and (not self.cik or self.cik == self.depositor_cik)


def _cik10(v: str | None) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    if not s.isdigit():
        raise ValueError(f"CIK must be digits, got {v!r}")
    return s.zfill(10)


def load_deals(path: str | Path = DEALS_CSV) -> list[Deal]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in DEAL_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns {missing}")
        return [Deal(**{c: (row.get(c) or "") for c in DEAL_COLUMNS}) for row in reader]


def get_deal(slug: str, path: str | Path = DEALS_CSV) -> Deal:
    for d in load_deals(path):
        if d.deal == slug:
            return d
    raise KeyError(f"deal {slug!r} not in {path}")


# scout-autos section 5b: what each issuer keeps in later monthly files after a loan's balance goes to zero.
# Documentation and diagnostics only; the exit rule in build.py does not depend on it.
RETENTION = {
    "santander": "keeps charge-offs (code 4); drops payoffs (1) and repurchases (3) the month after",
    "carmax": "keeps every loan for the deal's life",
    "capone": "keeps every loan for the deal's life",
    "exeter": "keeps every loan for the deal's life; delinquency reset to 0 at zero balance",
    "americredit": "keeps charge-offs; drops payoffs the month after",
    "toyota": "keeps charge-offs; drops payoffs the month after",
    "ford": "drops every closed loan after one month",
    "honda": "not yet measured (scout-autos section 10 item 8)",
}

# scout-autos section 6 item 2 and section 8: what the reported score is, per issuer.
SCORE_NOTES = {
    "santander": '"Bureau", scale unstated (369-900), 424B5 located but not read (section 10 item 1)',
    "carmax": '"Bureau" = FICO at application on the auto-industry scale (650-900), co-obligor average',
    "capone": '"FICO" (700-889), auto scale',
    "exeter": '"Consumer Credit Bureau" = VantageScore for 98.9% of the pool (section 8)',
    "americredit": '"Credit Bureau Score" (375-832), scale unstated; type "None" = no score',
    "toyota": '"FICO Score 8 Auto" (620-900)',
    "ford": '"Consumer Bureau" (424-900); "Commercial Bureau" records are on a 1-670 scale and flagged commercial',
    "honda": "not yet measured",
}
