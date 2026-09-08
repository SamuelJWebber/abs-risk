"""Streaming parser for one Form ABS-EE exhibit 102 (auto-loan asset data XML).

`iter_loan_months(path, deal, lender)` walks the file with lxml iterparse, one `<assets>` record at a time, and
yields a normalised loan-month dict. Nothing bigger than one record is ever held in memory (files run to 350 MB,
design/scout-autos.md section 9).

Each yielded dict carries two groups of keys:

- the `loan_months` columns of design/analysis-plan.md section 1b (LOAN_MONTH_COLUMNS), and
- the origination attributes that the `loans` table of section 1a needs (ORIGINATION_KEYS): the plan's 1a columns
  can only be filled from these, so the parser carries them alongside the monthly fields. The loan_months parquet
  written by build.py keeps exactly the 1b columns.

Normalisations, each cited to design/scout-autos.md:

- credit score: null when 0, empty or non-numeric (section 6 item 3: three encodings of "no score"; section 11
  per-issuer table). `score_type` is carried verbatim (section 3).
- payment-to-income: a fraction. Divided by 100 when the issuer is Capital One or when the file's median exceeds
  1.0 (section 6 item 1: percent only at Capital One; use the median, never the max, because CarMax, Ford, Toyota
  and AmeriCredit have fraction-scale outliers above 1). The rule that fired is recorded in `info["pti_rule"]`.
- dates: MM/YYYY (origination, zero-balance effective) to the first of the month; MM-DD-YYYY (reporting period) to
  a date (section 6 item 5: lexicographic comparison of MM/YYYY is wrong).
- repeated elements: the first value wins and duplicates are counted (section 6 item 7: `subvented` twice in 53%
  of Ford records; a dict-per-record parser silently keeps the last).
- Ford commercial obligors: flagged when `obligorCreditScoreType` contains "Commercial" (section 6 item 9 and
  section 4a: "Commercial Bureau" records have a 1-670 score scale and no PTI).
- rates: `originalInterestRatePercentage` is a fraction in every file (section 6 item 4); carried as is, values
  above 1 are counted in `info["n_apr_gt_1"]` so a percent-scale file would be noticed.
- absent elements are nulls (section 6 item 6: zero-balance, recovery, repossession and, at AmeriCredit, CarMax
  and Toyota, `currentDelinquencyStatus` appear only when set).
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterator

from lxml import etree

NS = "http://www.sec.gov/edgar/document/absee/autoloan/assetdata"
RECORD_TAG = "assets"

# design/analysis-plan.md section 1b, in order.
LOAN_MONTH_COLUMNS = [
    "deal", "asset_id", "period", "balance_begin", "balance_end", "dpd", "zb_code", "scheduled_payment",
    "actual_payment", "interest_paid", "principal_paid", "chargeoff_amount", "recovered_amount", "repossessed",
    "servicing_flag",
]

# Origination attributes needed by the `loans` table (analysis-plan section 1a), carried on every record.
ORIGINATION_KEYS = [
    "orig_month", "orig_amount", "orig_apr", "orig_term", "pti", "score", "score_type", "vehicle_value", "new_used",
    "state", "income_verified", "employment_verified", "subvented", "commercial", "zb_date",
]

PTI_SAMPLE = 5000  # records used to detect the PTI unit before the main pass
CAPONE_LENDERS = {"capone", "capital-one", "capitalone"}


class ParseError(ValueError):
    """The file does not look like an EX-102 auto-loan exhibit; fail loudly (CLAUDE.md EDGAR rules)."""


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _num(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _int(v: str | None) -> int | None:
    x = _num(v)
    if x is None:
        return None
    try:
        return int(x)
    except (ValueError, OverflowError):
        return None


def _bool(v: str | None) -> bool | None:
    if v is None or v == "":
        return None
    s = v.strip().lower()
    if s in ("true", "1", "yes", "y"):
        return True
    if s in ("false", "0", "no", "n"):
        return False
    return None


def parse_month(v: str | None) -> date | None:
    """MM/YYYY -> first of that month. Anything else -> None."""
    if not v:
        return None
    s = v.strip()
    if len(s) == 7 and s[2] == "/":
        try:
            return date(int(s[3:7]), int(s[0:2]), 1)
        except ValueError:
            return None
    return None


def parse_date(v: str | None) -> date | None:
    """MM-DD-YYYY -> date. Anything else -> None."""
    if not v:
        return None
    s = v.strip()
    if len(s) == 10 and s[2] == "-" and s[5] == "-":
        try:
            return date(int(s[6:10]), int(s[0:2]), int(s[3:5]))
        except ValueError:
            return None
    return None


def score_value(raw: str | None) -> int | None:
    """scout-autos section 6 item 3: 0 (Santander, Exeter), non-numeric under type "None" (AmeriCredit) and
    empty (Ford) all mean no score."""
    x = _num(raw)
    if x is None or x <= 0:
        return None
    return int(x)


def iter_records(path: str | Path) -> Iterator[dict[str, str]]:
    """Yield one flat dict per <assets> record (first value wins for repeated elements; `__dups` counts them).

    Streams with iterparse and frees every record after yielding it.
    """
    ctx = etree.iterparse(str(path), events=("end",))
    seen_root = False
    for _ev, el in ctx:
        parent = el.getparent()
        if parent is None or parent.getparent() is not None:
            continue  # only direct children of the root are records
        if not seen_root:
            if _local(parent.tag) != "assetData":
                raise ParseError(f"{path}: root element is {parent.tag!r}, expected assetData")
            seen_root = True
        if _local(el.tag) != RECORD_TAG:
            raise ParseError(f"{path}: unexpected child of root {el.tag!r}")
        rec: dict[str, str] = {}
        dups: Counter[str] = Counter()
        for ch in el:
            if len(ch):
                raise ParseError(f"{path}: nested element {ch.tag!r} inside a record; EX-102 records are flat")
            name = _local(ch.tag)
            if name in rec:
                dups[name] += 1
                continue
            rec[name] = (ch.text or "").strip()
        if dups:
            rec["__dups"] = dups  # type: ignore[assignment]
        yield rec
        el.clear()
        while el.getprevious() is not None:
            del parent[0]


def detect_pti_scale(path: str | Path, lender: str | None, sample: int = PTI_SAMPLE) -> dict:
    """Decide whether paymentToIncomePercentage is a percent (divide by 100) or a fraction.

    scout-autos section 6 item 1 and section 11 "Detection rules": percent at Capital One, fraction elsewhere;
    detect by the median (5-11% as a fraction vs 4.95-5.61 as a percent), never the max. The median is taken over
    the first `sample` records with a numeric PTI, which is enough to separate 0.1 from 5.
    """
    vals: list[float] = []
    n = 0
    for rec in iter_records(path):
        n += 1
        x = _num(rec.get("paymentToIncomePercentage"))
        if x is not None:
            vals.append(x)
        if n >= sample:
            break
    median = statistics.median(vals) if vals else None
    issuer_rule = (lender or "").lower() in CAPONE_LENDERS
    median_rule = median is not None and median > 1.0
    if issuer_rule and median_rule:
        rule = "issuer+median"
    elif issuer_rule:
        rule = "issuer"
    elif median_rule:
        rule = "median"
    else:
        rule = None
    return {"pti_rule": rule, "pti_divisor": 100.0 if rule else 1.0, "pti_sample_median_raw": median,
            "pti_sample_n": len(vals)}


def normalise(rec: dict[str, str], deal: str, pti_divisor: float) -> dict:
    """One raw record -> one loan-month dict (LOAN_MONTH_COLUMNS + ORIGINATION_KEYS)."""
    score_type = rec.get("obligorCreditScoreType", "")
    pti = _num(rec.get("paymentToIncomePercentage"))
    if pti is not None and pti_divisor != 1.0:
        pti = pti / pti_divisor
    modified = _bool(rec.get("reportingPeriodModificationIndicator")) or bool(rec.get("modificationTypeCode"))
    extended = (_int(rec.get("paymentExtendedNumber")) or 0) > 0
    if modified and extended:
        flag = "modified+extended"
    elif modified:
        flag = "modified"
    elif extended:
        flag = "extended"
    else:
        flag = None
    return {
        # analysis-plan 1b
        "deal": deal,
        "asset_id": rec.get("assetNumber", ""),
        "period": parse_date(rec.get("reportingPeriodEndingDate")),
        "balance_begin": _num(rec.get("reportingPeriodBeginningLoanBalanceAmount")),
        "balance_end": _num(rec.get("reportingPeriodActualEndBalanceAmount")),
        "dpd": _int(rec.get("currentDelinquencyStatus")),
        "zb_code": rec.get("zeroBalanceCode") or None,
        "scheduled_payment": _num(rec.get("reportingPeriodScheduledPaymentAmount")),
        "actual_payment": _num(rec.get("totalActualAmountPaid")),
        "interest_paid": _num(rec.get("actualInterestCollectedAmount")),
        "principal_paid": _num(rec.get("actualPrincipalCollectedAmount")),
        "chargeoff_amount": _num(rec.get("chargedoffPrincipalAmount")),
        "recovered_amount": _num(rec.get("recoveredAmount")),
        "repossessed": _bool(rec.get("repossessedIndicator")),
        "servicing_flag": flag,
        # origination attributes for analysis-plan 1a
        "orig_month": parse_month(rec.get("originationDate")),
        "orig_amount": _num(rec.get("originalLoanAmount")),
        "orig_apr": _num(rec.get("originalInterestRatePercentage")),
        "orig_term": _int(rec.get("originalLoanTerm")),
        "pti": pti,
        "score": score_value(rec.get("obligorCreditScore")),
        "score_type": score_type,
        "vehicle_value": _num(rec.get("vehicleValueAmount")),
        "new_used": rec.get("vehicleNewUsedCode") or None,
        "state": rec.get("obligorGeographicLocation") or None,
        "income_verified": rec.get("obligorIncomeVerificationLevelCode") or None,
        "employment_verified": rec.get("obligorEmploymentVerificationCode") or None,
        "subvented": rec.get("subvented") or None,  # first value: iter_records keeps the first
        "commercial": "commercial" in score_type.lower(),
        "zb_date": parse_month(rec.get("zeroBalanceEffectiveDate")),
    }


def iter_loan_months(path: str | Path, deal: str, lender: str | None = None,
                     info: dict | None = None) -> Iterator[dict]:
    """Stream one EX-102 file as normalised loan-month dicts.

    `info`, if given, is filled in place: pti_rule, pti_divisor, pti_sample_median_raw, n_records, period,
    n_periods_other (records whose period differs from the file's first), dup_counts (element -> records with a
    repeat), n_apr_gt_1, n_score_missing, n_commercial. It is complete only after the iterator is exhausted.
    """
    scale = detect_pti_scale(path, lender)
    if info is None:
        info = {}
    info.update(scale)
    info.update({"n_records": 0, "period": None, "n_periods_other": 0, "dup_counts": Counter(),
                 "n_apr_gt_1": 0, "n_score_missing": 0, "n_commercial": 0, "n_pti_gt_1_after": 0})
    for rec in iter_records(path):
        row = normalise(rec, deal, scale["pti_divisor"])
        if "__dups" in rec:
            info["dup_counts"].update(rec["__dups"].keys())  # type: ignore[union-attr]
        info["n_records"] += 1
        if info["period"] is None:
            info["period"] = row["period"]
        elif row["period"] != info["period"]:
            info["n_periods_other"] += 1
        if row["orig_apr"] is not None and row["orig_apr"] > 1:
            info["n_apr_gt_1"] += 1
        if row["score"] is None:
            info["n_score_missing"] += 1
        if row["commercial"]:
            info["n_commercial"] += 1
        if row["pti"] is not None and row["pti"] > 1:
            info["n_pti_gt_1_after"] += 1
        yield row
    info["dup_counts"] = dict(info["dup_counts"])
    if info["period"] is None and info["n_records"]:
        raise ParseError(f"{path}: no reportingPeriodEndingDate parsed")


def file_period(path: str | Path) -> date | None:
    """The reporting period of a file from its first record (cheap: stops after one record)."""
    for rec in iter_records(path):
        return parse_date(rec.get("reportingPeriodEndingDate"))
    return None
