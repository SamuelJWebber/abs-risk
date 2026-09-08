"""Parse one 10-D filing directory into one `cards_monthly` row (design/analysis-plan.md section 3a).

Rules (CLAUDE.md): exhibits are identified by their content, never by file name; every number is found by
its row label, never by position; the trust's printed rate is kept and recomputed from the dollar rows as a
self-check (agreement within 1e-4 or the filing fails loudly). Labels, bases and delinquency bucket edges
per trust are recorded in design/scout-cards.md and design/cards-build.md.

Rates are fractions (0.0296, not 2.96). `row_labels_json` records the labels matched, the printed values,
the recomputed values, the inputs, and the reason for every null.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from .tables import (
    ParseError,
    Row,
    close,
    doc_text,
    find_row,
    find_row_after,
    find_rows,
    is_number_cell,
    month_end,
    parse_date,
    read_text,
    rows,
    sgml_type,
)

TRUSTS = ("amex", "comet", "chase", "citi", "synchrony", "bofa")

COLUMNS = [
    "trust", "period_end", "receivables_principal", "gross_co_rate", "net_co_rate", "co_basis",
    "co_annualisation", "payment_rate", "yield", "delinq_30plus_share", "delinq_90plus_share", "delinq_basis",
    "excess_spread", "source_accession", "source_file", "row_labels_json",
]

RATE_FIELDS = ("gross_co_rate", "net_co_rate", "payment_rate", "yield", "delinq_30plus_share", "delinq_90plus_share",
               "excess_spread")
RATE_TOL = 1e-4      # printed vs recomputed rate, as a fraction (0.01 percentage points)
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
SKIP_FILES = ("index.json", "manifest.json")


# ----------------------------------------------------------------------------- filing directory


class Filing:
    """A downloaded 10-D: the documents in one accession directory, read lazily by content."""

    def __init__(self, path: Path, trust: str):
        self.path = Path(path)
        self.trust = trust
        self.accession = self.path.name
        if not ACCESSION_RE.match(self.accession):
            raise ParseError(f"{self.path} is not an accession directory")
        self.manifest = self._load_manifest()
        self._text: dict[str, str] = {}
        self._doc_text: dict[str, str] = {}
        self._rows: dict[str, list[Row]] = {}
        self.docs = self._documents()

    def _load_manifest(self) -> dict | None:
        p = self.path / "manifest.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _documents(self) -> list[str]:
        out = []
        for p in sorted(self.path.iterdir()):
            n = p.name
            if not p.is_file() or n in SKIP_FILES or n.endswith("-index-headers.html") or n.endswith("-index.html"):
                continue
            if n == f"{self.accession}.txt":  # full submission text file, duplicates every exhibit
                continue
            if p.suffix.lower() in (".htm", ".html", ".txt"):
                out.append(n)
        if not out:
            raise ParseError(f"no documents in {self.path}")
        return out

    def text(self, name: str) -> str:
        if name not in self._text:
            self._text[name] = read_text(self.path / name)
        return self._text[name]

    def plain(self, name: str) -> str:
        if name not in self._doc_text:
            self._doc_text[name] = doc_text(self.text(name))
        return self._doc_text[name]

    def rows(self, name: str) -> list[Row]:
        if name not in self._rows:
            self._rows[name] = rows(self.text(name))
        return self._rows[name]

    def find_exhibit(self, *patterns: str, optional: bool = False) -> str | None:
        """The one document whose text matches every pattern. Zero or several matches is an error."""
        pats = [re.compile(p, re.I) for p in patterns]
        hits = [n for n in self.docs if all(p.search(self.plain(n)) for p in pats)]
        if len(hits) == 1:
            return hits[0]
        if not hits and optional:
            return None
        raise ParseError(f"{self.trust} {self.accession}: expected one document matching {patterns}, got {hits}")

    def manifest_period(self) -> date | None:
        if self.manifest and self.manifest.get("period"):
            return date.fromisoformat(self.manifest["period"])
        hdr = next((p for p in self.path.iterdir() if p.name.endswith("-index-headers.html")), None)
        if hdr:
            m = re.search(r"<PERIOD>(\d{8})", hdr.read_text(encoding="utf-8", errors="replace"))
            if m:
                return date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:]))
        return None


class Rec:
    """Accumulates one output row plus its audit trail."""

    def __init__(self, filing: Filing):
        self.f = filing
        self.out: dict = {c: None for c in COLUMNS}
        self.out["trust"] = filing.trust
        self.out["source_accession"] = filing.accession
        self.labels: dict[str, str] = {}
        self.printed: dict[str, float] = {}
        self.recomputed: dict[str, float] = {}
        self.inputs: dict[str, float | int | str] = {}
        self.null_reasons: dict[str, str] = {}
        self.checks: list[str] = []
        self.notes: dict[str, str] = {}
        self.exhibits: dict[str, str] = {}

    def set(self, field: str, value: float | None, row: Row | None = None, *, label: str | None = None):
        self.out[field] = value
        if row is not None:
            self.labels[field] = label or row.label
        elif label:
            self.labels[field] = label

    def null(self, field: str, reason: str):
        self.out[field] = None
        self.null_reasons[field] = reason

    def check(self, name: str, printed: float, recomputed: float, tol: float = RATE_TOL):
        self.printed[name] = printed
        self.recomputed[name] = recomputed
        ok = close(printed, recomputed, tol)
        self.checks.append(f"{name}: printed {printed:.6f} recomputed {recomputed:.6f} {'ok' if ok else 'FAIL'}")
        if not ok:
            raise ParseError(f"{self.f.trust} {self.f.accession}: {name} printed {printed:.6f} != recomputed "
                             f"{recomputed:.6f} (tol {tol})")

    def finish(self, period_end: date, source_files: list[str]) -> dict:
        mp = self.f.manifest_period()
        if mp and (mp.year, mp.month) != (period_end.year, period_end.month):
            raise ParseError(f"{self.f.trust} {self.f.accession}: exhibit period {period_end} vs EDGAR period {mp}")
        self.out["period_end"] = period_end.isoformat()
        self.out["source_file"] = ";".join(source_files)
        for k in RATE_FIELDS:  # printed rates carry at most 6 decimals as fractions; drop float noise
            if self.out[k] is not None:
                self.out[k] = round(self.out[k], 8)
        self.out["row_labels_json"] = json.dumps({
            "labels": self.labels, "printed": self.printed, "recomputed": self.recomputed, "inputs": self.inputs,
            "null_reasons": self.null_reasons, "checks": self.checks, "notes": self.notes, "exhibits": self.exhibits,
            "edgar_period": mp.isoformat() if mp else None,
        }, separators=(",", ":"))
        return self.out


def _share(numer: float, denom: float) -> float:
    if denom <= 0:
        raise ParseError(f"non-positive denominator {denom}")
    return numer / denom


def _bucket_dollars(rs: list[Row], patterns: dict[str, str], *, table: int | None = None) -> dict[str, float]:
    out = {}
    for name, pat in patterns.items():
        out[name] = find_row(rs, pat, table=table).dollars()
    return out


# ----------------------------------------------------------------------------- Amex


def parse_amex(f: Filing) -> dict:
    ex = f.find_exhibit(r"Trust Totals", r"Annualized Default Rate, Net of Recoveries", r"Monthly Payment Rate")
    r = Rec(f)
    r.exhibits = {"pool": ex, "type": sgml_type(f.text(ex))}
    rs = f.rows(ex)
    text = f.plain(ex)
    m = re.search(r"covers activity from ([A-Z][a-z]+ \d{1,2}, \d{4}) through ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if not m:
        raise ParseError("amex: period sentence not found")
    period_end = parse_date(m.group(2))

    # Trust block "A. Trust Activity / Trust Totals": the first table carrying these labels (per-series blocks repeat some).
    days_row = find_row(rs, r"^Number of days in Monthly Period")
    t = days_row.table
    days = int(days_row.first())
    beg_prin = find_row(rs, r"^Beginning Principal Receivable Balance", table=t).first()
    end_prin_row = find_row(rs, r"^Ending Principal Receivables Balance", table=t)
    end_prin = end_prin_row.first()
    end_total = find_row(rs, r"^Ending Total Receivables", table=t).first()
    defaulted = find_row(rs, r"^Defaulted Amount", table=t).first()
    recoveries = find_row(rs, r"^Recoveries$", table=t).first()
    fc_coll = find_row(rs, r"^Total Collections of Finance Charge Receivables", table=t).first()
    prin_coll = find_row(rs, r"^Total Collections of Principal Receivables", table=t).first()
    gross_row = find_row(rs, r"^Annualized Default Rate$", table=t)
    net_row = find_row(rs, r"^Annualized Default Rate, Net of Recoveries", table=t)
    pay_row = find_row(rs, r"^Monthly Payment Rate", table=t)
    yield_row = find_row(rs, r"^Trust Portfolio Yield", table=t)

    r.set("receivables_principal", end_prin, end_prin_row)
    r.set("gross_co_rate", gross_row.pct(), gross_row)
    r.set("net_co_rate", net_row.pct(), net_row)
    r.out["co_basis"] = "ending"
    r.out["co_annualisation"] = "x365_over_days"
    r.set("payment_rate", pay_row.pct(), pay_row)
    r.set("yield", yield_row.pct(), yield_row)
    r.null("excess_spread", "Amex prints Excess Spread Percentage per series only (base rates differ by series); "
                            "no trust-level excess spread")
    r.inputs.update(days_in_period=days, beginning_principal=beg_prin, ending_principal=end_prin,
                    ending_total_receivables=end_total, defaulted_amount=defaulted, recoveries=recoveries,
                    finance_charge_collections=fc_coll, principal_collections=prin_coll)
    # Self-check: Defaulted Amount x 365/days / ending principal receivables (design/scout-cards.md B1).
    r.check("gross_co_rate", gross_row.pct(), defaulted * 365 / days / end_prin)
    r.check("net_co_rate", net_row.pct(), (defaulted - recoveries) * 365 / days / end_prin)
    # Loss Experience block repeats the rates at 2 decimals; cross-check that block's Net Default Amount.
    loss_net = find_rows(rs, r"^Net Default Amount")
    if loss_net:
        r.check("net_default_amount_dollars", loss_net[0].first() / 1e6, (defaulted - recoveries) / 1e6, tol=1e-3)
    r.notes["payment_rate"] = ("denominator not printed; principal collections / Monthly Payment Rate implies "
                               "beginning total receivables")
    r.notes["yield"] = "Trust Portfolio Yield; denominator not printed in the certificate"

    # Delinquency: section D, "% of Ending Total Receivables"; buckets 31-60 / 61-90 / 91-120 / 120+.
    b = _bucket_dollars(rs, {"31-60": r"^31-60 Days Delinquent", "61-90": r"^61-90 Days Delinquent",
                             "91-120": r"^91-120 Days Delinquent", "120+": r"^120\+ Days Delinquent"})
    tot_row = find_row(rs, r"^Total 30\+ Days Delinquent")
    tot30 = tot_row.dollars()
    if not close(tot30, sum(b.values()), 2.0):
        raise ParseError(f"amex: Total 30+ {tot30} != sum of buckets {sum(b.values())}")
    r.set("delinq_30plus_share", _share(tot30, end_total), tot_row)
    r.set("delinq_90plus_share", _share(b["91-120"] + b["120+"], end_total),
          label="91-120 Days Delinquent + 120+ Days Delinquent")
    r.out["delinq_basis"] = ("dollar share of Ending Total Receivables; buckets 31-60/61-90/91-120/120+; "
                             "30plus = trust's Total 30+ row (exact); 90plus = 91-120 + 120+ (exact)")
    r.check("delinq_30plus_share", tot_row.pct(), r.out["delinq_30plus_share"])
    for k, pat in {"31-60": r"^31-60 Days", "61-90": r"^61-90 Days", "91-120": r"^91-120 Days", "120+": r"^120\+ Days"}.items():
        r.check(f"delinq_{k}", find_row(rs, pat).pct(), b[k] / end_total)
    r.inputs["delinquency_buckets"] = b
    return r.finish(period_end, [ex])


# ----------------------------------------------------------------------------- COMET


def parse_comet(f: Filing) -> dict:
    ex = f.find_exhibit(r"CAPITAL ONE MASTER TRUST \(RECEIVABLES\)", r"Annualized Default Rate")
    r = Rec(f)
    r.exhibits = {"pool": ex, "type": sgml_type(f.text(ex))}
    rs = f.rows(ex)
    m = re.search(r"MONTHLY PERIOD:\s*([A-Z][a-z]+)\s+(\d{4})", f.plain(ex))
    if not m:
        raise ParseError("comet: 'MONTHLY PERIOD: <Month YYYY>' not found")
    period_end = month_end(m.group(1), int(m.group(2)))

    beg_prin = find_row(rs, r"Beginning of the Month Principal Receivables").dollars()
    add_prin = find_row(rs, r"^\d+\)\s*Additional Principal Receivables").dollars()
    end_prin_row = find_row(rs, r"End of the Month Principal Receivables")
    end_total = find_row(rs, r"End of the Month Total Receivables").dollars()
    defaulted = find_row(rs, r"Defaulted Accounts during the Month").dollars()
    recov = find_row(rs, r"Recoveries of Charged-Off Accounts during the Month").dollars()
    net_def = find_row(rs, r"Defaulted Accounts, net of Recoveries, during the Month").dollars()
    gross_row = find_row(rs, r"^\d+\)\s*Annualized Default Rate as a Percent of Adjusted Beginning")
    net_row = find_row(rs, r"Annualized Net Default Rate as a Percent of Adjusted Beginning")
    pay_row = find_row(rs, r"Collections of Principal Receivables and Principal Payment Rate")
    tot_pay_row = find_row(rs, r"Total Collections and Gross Payment Rate")
    yield_row = find_row(rs, r"Collections of Finance Charge Receivables and Annualized Yield")
    adj_beg = beg_prin + add_prin

    r.set("receivables_principal", end_prin_row.dollars(), end_prin_row)
    r.set("gross_co_rate", gross_row.pct(), gross_row)
    r.set("net_co_rate", net_row.pct(), net_row)
    r.out["co_basis"] = "beginning"
    r.out["co_annualisation"] = "x12"
    r.set("payment_rate", pay_row.pct(), pay_row)
    r.set("yield", yield_row.pct(), yield_row)
    r.null("excess_spread", "COMET 10-D prints only the dollar Excess Spread Amount (EX-99.2); no percentage, "
                            "no base rate, no portfolio yield label")
    r.inputs.update(beginning_principal=beg_prin, additional_principal=add_prin, adjusted_beginning_principal=adj_beg,
                    ending_total_receivables=end_total, defaulted_amount=defaulted, recoveries=recov,
                    net_defaulted_amount=net_def, principal_collections=pay_row.dollars(),
                    finance_charge_collections=yield_row.dollars(), total_payment_rate=tot_pay_row.pct())
    r.check("gross_co_rate", gross_row.pct(), defaulted * 12 / adj_beg)
    r.check("net_co_rate", net_row.pct(), net_def * 12 / adj_beg)
    r.check("net_defaulted_amount", net_def / 1e6, (defaulted - recov) / 1e6, tol=1e-3)
    r.check("payment_rate", pay_row.pct(), pay_row.dollars() / adj_beg)
    r.check("yield", yield_row.pct(), yield_row.dollars() * 12 / adj_beg)
    r.notes["payment_rate"] = "principal payment rate (principal collections / adjusted beginning principal); " \
                              "gross payment rate on total receivables kept in inputs.total_payment_rate"

    # EX-99.2 excess spread dollars, when the exhibit is present (informational only).
    ex2 = f.find_exhibit(r"Current Month Excess Spread Amount", optional=True)
    if ex2:
        r.exhibits["noteholders"] = ex2
        r.inputs["excess_spread_amount_dollars"] = find_row(f.rows(ex2), r"^Current Month Excess Spread Amount").dollars()

    # Delinquency section B: buckets 30-59 / 60-89 / 90-119 / 120-149 / 150+, % of End of the Month Total Receivables.
    b = _bucket_dollars(rs, {"30-59": r"30 - 59 Days Delinquent", "60-89": r"60 - 89 Days Delinquent",
                             "90-119": r"90 - 119 Days Delinquent", "120-149": r"120 - 149 Days Delinquent",
                             "150+": r"150 \+ Days Delinquent"})
    tot_row = find_row(rs, r"Total 30\+ Days Delinquent")
    tot30 = tot_row.dollars()
    if not close(tot30, sum(b.values()), 2.0):
        raise ParseError(f"comet: Total 30+ {tot30} != sum of buckets {sum(b.values())}")
    r.set("delinq_30plus_share", _share(tot30, end_total), tot_row)
    r.set("delinq_90plus_share", _share(b["90-119"] + b["120-149"] + b["150+"], end_total),
          label="90 - 119 + 120 - 149 + 150 + Days Delinquent")
    r.out["delinq_basis"] = ("dollar share of End of the Month Total Receivables; buckets 30-59/60-89/90-119/120-149/150+; "
                             "30plus = trust's Total 30+ row (exact); 90plus = 90-119 + 120-149 + 150+ (exact)")
    pct30 = find_row(rs, r"Delinquencies 30 \+ Days as a Percent of End of the Month Total Receivables")
    r.check("delinq_30plus_share", pct30.pct(), r.out["delinq_30plus_share"])
    pct60 = find_row(rs, r"Delinquencies 60 \+ Days as a Percent of End of the Month Total Receivables")
    r.check("delinq_60plus_share", pct60.pct(), (tot30 - b["30-59"]) / end_total)
    r.inputs["delinquency_buckets"] = b
    return r.finish(period_end, [ex])


# ----------------------------------------------------------------------------- Chase


_MONTH_WORD = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b")


def _current_column(rs: list[Row], table: int, period_end: date) -> int:
    """Index (among a row's values) of the column headed by the period's month.

    The header row is found by content: the first row of the table whose cells carry month names and no
    numbers ("July Monthly Period | June ...", "July | June | May", "July 31, 2026 | June 30, 2026").
    """
    month = period_end.strftime("%B")
    for r in rs:
        if r.table != table:
            continue
        heads = [c for c in r.cells if _MONTH_WORD.search(c)]
        if not heads or any(is_number_cell(c) for c in r.cells):
            continue
        for i, h in enumerate(heads):
            if month in h and (str(period_end.year) in h or not re.search(r"\d{4}", h)):
                return i
        raise ParseError(f"table {table} header {r.text!r} has no {month} {period_end.year} column")
    raise ParseError(f"no month header row in table {table}")


def parse_chase(f: Filing) -> dict:
    pool = f.find_exhibit(r"Asset Pool One", r"Losses and Recoveries")
    series = f.find_exhibit(r"CHASEseries", r"Excess Spread Percentage", r"Principal Payment Rate")
    r = Rec(f)
    r.exhibits = {"pool": pool, "series": series, "type": sgml_type(f.text(pool))}
    rs = f.rows(pool)
    m = re.search(r"Monthly Period:\s*([A-Z][a-z]+)\s+(\d{4})", f.plain(pool))
    if not m:
        raise ParseError("chase: 'Monthly Period: <Month YYYY>' not found")
    period_end = month_end(m.group(1), int(m.group(2)))

    prin_row = find_row(rs, r"^Principal Receivables$")
    beg_prin, end_prin = prin_row.numbers()[0].value, prin_row.numbers()[1].value
    avg_row = find_row(rs, r"^Average Pool Balance")
    avg = avg_row.first()
    gross_d = find_row(rs, r"^Gross Losses \(\d\)$").first()
    recov = find_row(rs, r"^Recoveries \(\d\)$").first()
    net_d = find_row(rs, r"^Net Losses \(\d\)$").first()
    gross_row = find_row(rs, r"^Gross Losses as a Percentage of Average Pool Balance")
    net_row = find_row(rs, r"^Net Losses as a percentage of Average Pool Balance")
    prin_coll = find_row(rs, r"aggregate amount of Collections of Principal Receivables received by Asset Pool One").first()
    pool_default = find_row(rs, r"The Asset Pool One Default Amount for the related Monthly Period").first()

    r.set("receivables_principal", end_prin, prin_row, label="Principal Receivables (Ending Balance)")
    r.set("gross_co_rate", gross_row.pct(), gross_row)
    r.set("net_co_rate", net_row.pct(), net_row)
    r.out["co_basis"] = "average"
    r.out["co_annualisation"] = "x12"
    r.inputs.update(beginning_principal=beg_prin, ending_principal=end_prin, average_pool_balance=avg,
                    gross_losses=gross_d, recoveries=recov, net_losses=net_d, principal_collections=prin_coll,
                    asset_pool_one_default_amount=pool_default)
    r.check("gross_co_rate", gross_row.pct(), gross_d * 12 / avg)
    r.check("net_co_rate", net_row.pct(), net_d * 12 / avg)
    r.check("net_losses", net_d / 1e6, (gross_d - recov) / 1e6, tol=1e-3)
    r.notes["co_basis"] = "Average Pool Balance (Asset Pool One Average Principal Balance); recoveries are an " \
                          "allocated share of managed-portfolio recoveries (EX-99.2 footnote 4)"

    # EX-99.3 section C: three month columns; take the column headed by the period month.
    ss = f.rows(series)
    yrow = find_row(ss, r"^Yield - Finance Charge, Fees & Interchange")
    col = _current_column(ss, yrow.table, period_end)
    pyrow = find_row(ss, r"^\(a\) Portfolio Yield")
    brow = find_row(ss, r"^\(b\) Base Rate")
    esrow = find_row(ss, r"Excess Spread Percentage$")
    prow = find_row(ss, r"^Principal Payment Rate")
    ncl = find_row(ss, r"^Less: Net Credit Losses")

    def pcol(row: Row) -> float:
        ps = [x for x in row.numbers() if x.pct]
        if len(ps) <= col:
            raise ParseError(f"chase: column {col} missing in {row.text!r}")
        return ps[col].value / 100.0

    r.set("yield", pcol(yrow), yrow)
    r.set("payment_rate", pcol(prow), prow)
    r.set("excess_spread", pcol(esrow), esrow)
    r.inputs.update(portfolio_yield=pcol(pyrow), base_rate=pcol(brow), net_credit_losses_ex993=pcol(ncl))
    r.check("net_credit_losses_ex993", pcol(ncl), net_row.pct())
    r.check("payment_rate", pcol(prow), prin_coll / beg_prin)
    r.notes["yield"] = "gross yield (finance charge, fees and interchange) from EX-99.3; (a) Portfolio Yield in inputs"

    # Delinquency item 10: buckets 30-59 ... 180+, % of Pool Balance (total receivables incl. finance charges and fees).
    dtab = find_row(rs, r"^30-59 days").table
    pool_bal = find_row(rs, r"^Pool Balance", table=dtab)
    denom = pool_bal.numbers()[1].value if len(pool_bal.numbers()) > 1 else pool_bal.last()
    b = {}
    for k, pat in {"30-59": r"^30-59 days", "60-89": r"^60-89 days", "90-119": r"^90-119 days",
                   "120-149": r"^120-149 days", "150-179": r"^150-179 days", "180+": r"^180 or more days"}.items():
        row = find_row(rs, pat, table=dtab)
        b[k] = row.numbers()[1].value  # accounts | dollars | pct
        r.check(f"delinq_{k}", row.pct(), b[k] / denom)
    tot_row = find_row(rs, r"^TOTAL$", table=dtab)
    tot30 = tot_row.numbers()[1].value
    if not close(tot30, sum(b.values()), 2.0):
        raise ParseError(f"chase: delinquency TOTAL {tot30} != sum {sum(b.values())}")
    r.set("delinq_30plus_share", _share(tot30, denom), tot_row, label="TOTAL (delinquencies item 10)")
    r.set("delinq_90plus_share", _share(b["90-119"] + b["120-149"] + b["150-179"] + b["180+"], denom),
          label="90-119 + 120-149 + 150-179 + 180 or more days")
    r.out["delinq_basis"] = ("dollar share of Pool Balance in item 10 (principal + finance charge + fee receivables); "
                             "buckets 30-59/60-89/90-119/120-149/150-179/180+; 30plus = TOTAL row (exact); "
                             "90plus = 90-119 + 120-149 + 150-179 + 180+ (exact)")
    r.check("delinq_30plus_share", tot_row.pct(), r.out["delinq_30plus_share"])
    r.inputs.update(delinquency_buckets=b, delinquency_denominator=denom)
    return r.finish(period_end, [pool, series])


# ----------------------------------------------------------------------------- Citi


def parse_citi(f: Filing) -> dict:
    ex = f.find_exhibit(r"Portfolio Yield for the Collateral Certificate", r"Credit Loss Component")
    r = Rec(f)
    r.exhibits = {"pool": ex, "type": sgml_type(f.text(ex))}
    rs = f.rows(ex)
    text = f.plain(ex)
    m = re.search(r"Due Period ending ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if not m:
        raise ParseError("citi: 'Due Period ending <date>' not found")
    period_end = parse_date(m.group(1))
    days = None
    md = re.search(r"from ([A-Z][a-z]+ \d{1,2}, \d{4}) to ([A-Z][a-z]+ \d{1,2}, \d{4}), (\d+) days", text)
    if md:
        days = int(md.group(3))
        r.inputs.update(due_period_start=parse_date(md.group(1)).isoformat(), due_period_days=days)

    yrow = find_row(rs, r"Portfolio Yield for the Collateral Certificate")
    t = yrow.table
    yc = find_row(rs, r"^Yield Component", table=t)
    clc = find_row(rs, r"^Credit Loss Component", table=t)
    tot_pay = find_row(rs, r"Total Payment Rate", table=t)
    prin_pay = find_row(rs, r"Principal Payment Rate", table=t)
    beg = find_row(rs, r"^Principal Receivables Beginning of Due Period", table=t).dollars()
    avg = find_row(rs, r"^Principal Receivables Average", table=t).dollars()
    end_row = find_row(rs, r"^Principal Receivables End of Due Period", table=t)
    fc_end = find_row(rs, r"^Finance Charge Receivables - End of Due Period", table=t).dollars()
    inv_def = find_row(rs, r"Investor Default Amount").dollars()
    surplus = find_row(rs, r"^\d\.\s*Surplus Finance Charge Collections$")

    r.set("receivables_principal", end_row.dollars(), end_row)
    r.set("gross_co_rate", clc.pct(), clc)
    r.null("net_co_rate", "Citi publishes no net charge-off rate and no pool-level dollar charge-off row; "
                          "Credit Loss Component is inferred gross (recoveries are credited to collections, "
                          "prospectus Annex I)")
    r.out["co_basis"] = "invested_amount"
    r.out["co_annualisation"] = "actual_365"
    r.set("payment_rate", prin_pay.pct(), prin_pay)
    r.set("yield", yc.pct(), yc)
    r.set("excess_spread", surplus.pct(), surplus)
    r.inputs.update(portfolio_yield=yrow.pct(), total_payment_rate=tot_pay.pct(), beginning_principal=beg,
                    average_principal=avg, finance_charge_receivables_end=fc_end, investor_default_amount=inv_def)
    r.check("portfolio_yield_identity", yrow.pct(), yc.pct() - clc.pct())
    r.notes["gross_co_rate"] = ("Credit Loss Component of Portfolio Yield for the Collateral Certificate: investor "
                                "default amount over the collateral certificate invested amount, annualised "
                                f"actual/365 over the {days}-day due period (design/scout-cards.md B4); pro rata "
                                "to the master trust, so the pool default rate on principal receivables")
    r.notes["excess_spread"] = "Surplus Finance Charge Collections (actual basis), Citi's excess-spread analogue"

    # Delinquency item 6: Current + 1-30/31-60/61-90/91-120/121-150/151-180 dollars; % of the sum.
    drows = find_rows(rs, r"days delinquent$", table=t)
    dollars = [x for x in drows if any(n.dollar for n in x.numbers())]
    pcts = [x for x in drows if any(n.pct for n in x.numbers())]
    if len(dollars) != 6 or len(pcts) != 6:
        raise ParseError(f"citi: expected 6 dollar and 6 percent delinquency rows, got {len(dollars)}/{len(pcts)}")
    b = {x.label: x.dollars() for x in dollars}
    cur_rows = find_rows(rs, r"^Current$", table=t)
    cur = next(x.dollars() for x in cur_rows if any(n.dollar for n in x.numbers()))
    denom = cur + sum(b.values())
    for x in pcts:
        r.check(f"delinq_{x.label.split()[0]}", x.pct(), b[x.label] / denom)
    cur_pct = next(x for x in cur_rows if any(n.pct for n in x.numbers()))
    r.check("delinq_current", cur_pct.pct(), cur / denom)

    def bucket(prefix: str) -> float:
        return next(v for k, v in b.items() if k.startswith(prefix))

    d30 = bucket("31-60") + bucket("61-90") + bucket("91-120") + bucket("121-150") + bucket("151-180")
    d90 = bucket("91-120") + bucket("121-150") + bucket("151-180")
    r.set("delinq_30plus_share", _share(d30, denom), label="31-60 + 61-90 + 91-120 + 121-150 + 151-180 days delinquent")
    r.set("delinq_90plus_share", _share(d90, denom), label="91-120 + 121-150 + 151-180 days delinquent")
    r.out["delinq_basis"] = ("dollar share of total receivables (Current + all delinquency buckets, item 6); buckets "
                             "1-30/31-60/61-90/91-120/121-150/151-180; 30plus = 31+ (NEAREST CUT: Citi buckets start at "
                             "31, no 30-day edge); 90plus = 91+ (NEAREST CUT); no 180+ bucket (charged off at 180)")
    r.inputs.update(delinquency_buckets=b, delinquency_current=cur, delinquency_denominator=denom)
    return r.finish(period_end, [ex])


# ----------------------------------------------------------------------------- Synchrony


def parse_synchrony(f: Filing) -> dict:
    ex = f.find_exhibit(r"Gross Charge-Off Rate", r"BOP Aggregate Principal Receivables")
    r = Rec(f)
    r.exhibits = {"pool": ex, "type": sgml_type(f.text(ex))}
    rs = f.rows(ex)
    end_row = find_row(rs, r"^Monthly Period Ending")
    period_end = parse_date(end_row.cells[-1])
    days_row = find_rows(rs, r"Number of Days at Balance")

    bop = find_row(rs, r"BOP Aggregate Principal Receivables").last()
    eop_row = find_row(rs, r"EOP Aggregate Principal Receivables")
    eop_total = find_row(rs, r"EOP Total Receivables").last()
    bop_total = find_row(rs, r"BOP Total Receivables").last()
    gy = find_row(rs, r"Gross Trust Yield \(")
    pr = find_row(rs, r"^b\.\s*Payment Rate \(")
    gc = find_row(rs, r"Gross Charge-Off Rate \(")
    nc = find_row(rs, r"Net Charge-Off Rate \(")
    gy_cur, pr_cur = find_row_after(rs, gy, r"^i\.\s*Current"), find_row_after(rs, pr, r"^i\.\s*Current")
    gc_cur, nc_cur = find_row_after(rs, gc, r"^i\.\s*Current"), find_row_after(rs, nc, r"^i\.\s*Current")
    default_amt = find_row(rs, r"Default Amount for Defaulted Accounts$").last()
    recov = find_row(rs, r"^f\.\s*Recovery Amount").last()
    net_amt = find_row(rs, r"Net Charge-Off \(Default Amount for Defaulted Accounts - Recoveries\)").last()
    prin_coll = find_row(rs, r"^c\.\s*Principal Collections$").numbers()[0].value  # Trust column first

    r.set("receivables_principal", eop_row.last(), eop_row)
    r.set("gross_co_rate", gc_cur.pct(), gc_cur, label=gc.label + " / i. Current")
    r.set("net_co_rate", nc_cur.pct(), nc_cur, label=nc.label + " / i. Current")
    r.out["co_basis"] = "beginning"
    r.out["co_annualisation"] = "x12"
    r.set("payment_rate", pr_cur.pct(), pr_cur, label=pr.label + " / i. Current")
    r.set("yield", gy_cur.pct(), gy_cur, label=gy.label + " / i. Current")
    r.inputs.update(bop_principal=bop, bop_total_receivables=bop_total, eop_total_receivables=eop_total,
                    default_amount=default_amt, recoveries=recov, net_charge_off=net_amt,
                    principal_collections=prin_coll)
    if days_row:
        r.inputs["days_at_balance"] = int(days_row[0].last())
    r.check("gross_co_rate", gc_cur.pct(), default_amt * 12 / bop)
    r.check("net_co_rate", nc_cur.pct(), net_amt * 12 / bop)
    r.check("net_charge_off", net_amt / 1e6, (default_amt - recov) / 1e6, tol=1e-3)
    r.check("payment_rate", pr_cur.pct(), prin_coll / bop)
    r.notes["co_annualisation"] = "label does not say annualised; Default Amount x 12 / BOP principal reproduces the rate"

    # Yield block: (a) Portfolio Yield / (b) Base Rate / excess spread; three columns, current first (header checked).
    py = find_row(rs, r"^\(a\) Portfolio Yield")
    col = _current_column(rs, py.table, period_end)
    br = find_row(rs, r"^\(b\) Base Rate")
    es = find_row(rs, r"Excess Spread Percentage$")

    def pcol(row: Row) -> float:
        return [x for x in row.numbers() if x.pct][col].value / 100.0

    r.set("excess_spread", pcol(es), es)
    r.inputs.update(portfolio_yield=pcol(py), base_rate=pcol(br))
    r.check("excess_spread_identity", pcol(es), pcol(py) - pcol(br), tol=1.5e-4)

    # Delinquency j.: 1-29/30-59/.../180+; dollars and "% of Tot. Recv." (EOP Total Receivables).
    dtab = find_row(rs, r"1-29 Days Delinquent").table
    b = {}
    for k, pat in {"1-29": r"1-29 Days", "30-59": r"30-59 Days", "60-89": r"60-89 Days", "90-119": r"90-119 Days",
                   "120-149": r"120-149 Days", "150-179": r"150-179 Days", "180+": r"180 or Greater Days"}.items():
        row = find_row(rs, pat, table=dtab)
        nums = row.numbers()  # accounts | pct accts | dollars | pct recv
        b[k] = nums[2].value
        r.check(f"delinq_{k}", nums[3].value / 100.0, b[k] / eop_total)
    tot = find_row(rs, r"^Total$", table=dtab)
    if not close(tot.numbers()[2].value, sum(b.values()), 2.0):
        raise ParseError("synchrony: delinquency Total != sum of buckets")
    d30 = sum(v for k, v in b.items() if k != "1-29")
    d90 = b["90-119"] + b["120-149"] + b["150-179"] + b["180+"]
    r.set("delinq_30plus_share", _share(d30, eop_total), label="30-59 + 60-89 + 90-119 + 120-149 + 150-179 + 180+")
    r.set("delinq_90plus_share", _share(d90, eop_total), label="90-119 + 120-149 + 150-179 + 180+")
    r.out["delinq_basis"] = ("dollar share of EOP Total Receivables; buckets 1-29/30-59/60-89/90-119/120-149/150-179/180+; "
                             "30plus = sum from 30-59 (exact); 90plus = sum from 90-119 (exact)")
    r.inputs["delinquency_buckets"] = b
    return r.finish(period_end, [ex])


# ----------------------------------------------------------------------------- BofA


def parse_bofa(f: Filing) -> dict:
    ex = f.find_exhibit(r"MONTHLY CERTIFICATEHOLDERS.{0,3}STATEMENT",
                        r"Charge-Offs as a percentage of Average Principal Receivables Outstanding")
    r = Rec(f)
    r.exhibits = {"pool": ex, "type": sgml_type(f.text(ex))}
    rs = f.rows(ex)
    m = re.search(r"MONTHLY PERIOD ENDING ([A-Z][a-z]+ \d{1,2}, \d{4})", f.plain(ex))
    if not m:
        raise ParseError("bofa: 'MONTHLY PERIOD ENDING <date>' not found")
    period_end = parse_date(m.group(1))
    date_str = period_end.strftime("%B %d, %Y").replace(" 0", " ")

    beg_total = find_row(rs, r"aggregate amount of Receivables in the Trust as of the beginning").dollars()
    beg_prin = find_row(rs, r"aggregate amount of Principal Receivables in the Trust as of the beginning").dollars()
    end_total = find_row(rs, r"aggregate amount of Receivables in the Trust as of the end of the day").dollars()
    end_row = find_row(rs, r"aggregate amount of Principal Receivables in the Trust as of the end of the day")
    pay_row = find_row(rs, r"Collections of Principal Receivables as a percentage of prior month Principal Receivables")
    tot_pay = find_row(rs, r"Collections as a percentage of prior month Principal Receivables and Finance Charge")
    cash_yield = find_row(rs, r"^\(i\)\s*Total Cash Yield for the related Monthly Period as a percentage")
    port_yield = find_row(rs, r"^\(m\)\s*The Portfolio Yield for the related Monthly Period as a percentage")
    base = find_row(rs, r"^\(n\)\s*Base Rate for the related Monthly Period")
    eaf = find_row(rs, r"^\(o\)\s*Excess Available Funds Percentage for the related Monthly Period")
    inv_gross = find_row(rs, r"^\(k\)\s*Aggregate Class D Investor Default Amount for the related Monthly Period as a percentage")
    inv_net = find_row(rs, r"^\(l\)\s*Aggregate Class D Investor Default Amount net of Recoveries")

    # Pool charge-off table ($ thousands): two copies (current|prior, and two months earlier); pick by the date header.
    co_tables = [x.table for x in find_rows(rs, r"^Total Charge-Offs$")]
    ct = None
    for t in co_tables:
        if any(x.table == t and date_str in x.text for x in rs):
            ct = t
            break
    if ct is None:
        raise ParseError(f"bofa: no charge-off table headed {date_str!r}")
    col = _current_column(rs, ct, period_end)
    avg_row = find_row(rs, r"^Average Principal Receivables Outstanding", table=ct)
    gross_amt = find_row(rs, r"^Total Charge-Offs$", table=ct)
    gross_row = find_row(rs, r"^Total Charge-Offs as a percentage of Average Principal Receivables Outstanding", table=ct)
    rec_amt = find_row(rs, r"^Recoveries$", table=ct)
    net_amt = find_row(rs, r"^Net Charge-Offs$", table=ct)
    net_row = find_row(rs, r"^Net Charge-Offs as a percentage of Average Principal Receivables Outstanding", table=ct)

    def v(row: Row, pct: bool = False) -> float:
        xs = [x for x in row.numbers() if x.pct == pct]
        if len(xs) <= col:
            raise ParseError(f"bofa: column {col} missing in {row.text!r}")
        return xs[col].value / (100.0 if pct else 1.0)

    avg_k, gross_k, rec_k, net_k = v(avg_row), v(gross_amt), v(rec_amt), v(net_amt)
    r.set("receivables_principal", end_row.dollars(), end_row)
    r.set("gross_co_rate", v(gross_row, True), gross_row)
    r.set("net_co_rate", v(net_row, True), net_row)
    r.out["co_basis"] = "average"
    r.out["co_annualisation"] = "x12"
    r.set("payment_rate", pay_row.pct(), pay_row)
    r.set("yield", cash_yield.pct(), cash_yield)
    r.set("excess_spread", eaf.pct(), eaf)
    r.inputs.update(beginning_total_receivables=beg_total, beginning_principal=beg_prin,
                    ending_total_receivables=end_total, average_principal_thousands=avg_k,
                    total_charge_offs_thousands=gross_k, recoveries_thousands=rec_k, net_charge_offs_thousands=net_k,
                    total_payment_rate=tot_pay.pct(), portfolio_yield=port_yield.pct(), base_rate=base.pct(),
                    investor_interest_gross_default_rate=inv_gross.pct(), investor_interest_net_default_rate=inv_net.pct())
    r.check("gross_co_rate", v(gross_row, True), gross_k * 12 / avg_k)
    r.check("net_co_rate", v(net_row, True), net_k * 12 / avg_k)
    r.check("net_charge_offs_thousands", net_k / 1e3, (gross_k - rec_k) / 1e3, tol=2e-3)
    r.notes["co_basis"] = "average daily principal receivables, dollars in thousands; label does not say annualised, " \
                          "x12 reproduces the rate; the investor-interest default rates (k)/(l) are kept in inputs"
    r.notes["yield"] = "Total Cash Yield (incl. recoveries) on the Series 2001-D floating allocation investor interest"

    # Delinquency item 6: dollars 30-59 ... 180+, "Percentage of Total Receivables" = ending total receivables (k).
    b = {}
    for k, pat in {"30-59": r"^\(i\)\s*30 - 59 days", "60-89": r"^\(ii\)\s*60 - 89 days", "90-119": r"^\(iii\)\s*90 - 119 days",
                   "120-149": r"^\(iv\)\s*120 - 149 days", "150-179": r"^\(v\)\s*150 - 179 days",
                   "180+": r"^\(vi\)\s*180\s*-?\s*or more days"}.items():
        row = find_row(rs, pat)
        b[k] = row.dollars()
        r.check(f"delinq_{k}", row.pct(), b[k] / end_total)
    d60 = find_row(rs, r"60\+-Day Delinquency Rate$")
    r.check("delinq_60plus_share", d60.pct(), (sum(b.values()) - b["30-59"]) / end_total)
    r.set("delinq_30plus_share", _share(sum(b.values()), end_total), label="30 - 59 + ... + 180 - or more days")
    r.set("delinq_90plus_share", _share(b["90-119"] + b["120-149"] + b["150-179"] + b["180+"], end_total),
          label="90 - 119 + 120 - 149 + 150 - 179 + 180 - or more days")
    r.out["delinq_basis"] = ("dollar share of total Receivables in the Trust at month end (item 2(k)); buckets "
                             "30-59/60-89/90-119/120-149/150-179/180+; 30plus = sum of all buckets (exact); "
                             "90plus = sum from 90-119 (exact)")
    r.inputs["delinquency_buckets"] = b
    return r.finish(period_end, [ex])


PARSERS = {"amex": parse_amex, "comet": parse_comet, "chase": parse_chase, "citi": parse_citi,
           "synchrony": parse_synchrony, "bofa": parse_bofa}


# ----------------------------------------------------------------------------- driver


def parse_filing_dir(path: Path, trust: str) -> dict:
    if trust not in PARSERS:
        raise ParseError(f"no parser for trust {trust!r}")
    return PARSERS[trust](Filing(Path(path), trust))


def filing_dirs(raw: Path, trusts: tuple[str, ...] = TRUSTS) -> list[tuple[str, Path]]:
    """(trust, accession dir) for every 10-D directory under raw/<slug>/ or raw/<slug>/10D/ (scout layout)."""
    out = []
    for slug in trusts:
        base = Path(raw) / slug
        if not base.is_dir():
            continue
        for parent in (base, base / "10D"):
            if parent.is_dir():
                for d in sorted(parent.iterdir()):
                    if d.is_dir() and ACCESSION_RE.match(d.name):
                        out.append((slug, d))
    return out


def parse_raw(raw: Path, trusts: tuple[str, ...] = TRUSTS) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Parse every filing directory; returns (rows sorted by trust and period, [(trust, accession, error)])."""
    out, errors = [], []
    for slug, d in filing_dirs(raw, trusts):
        try:
            out.append(parse_filing_dir(d, slug))
        except Exception as e:  # noqa: BLE001 - reported, not hidden
            errors.append((slug, d.name, f"{type(e).__name__}: {e}"))
    out.sort(key=lambda r: (r["trust"], r["period_end"]))
    return out, errors


def write_csv(rows_: list[dict], out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows_:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in COLUMNS})


def coverage(rows_: list[dict]) -> str:
    """Trust x year table of months parsed."""
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    years: set[int] = set()
    for r in rows_:
        y = int(r["period_end"][:4])
        counts[r["trust"]][y] += 1
        years.add(y)
    ys = sorted(years)
    lines = ["trust      " + "".join(f"{y:>6}" for y in ys) + "  total"]
    for t in sorted(counts):
        lines.append(f"{t:<11}" + "".join(f"{counts[t].get(y, 0):>6}" for y in ys) + f"{sum(counts[t].values()):>7}")
    return "\n".join(lines)
