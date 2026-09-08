"""Build the `loans` table (design/analysis-plan.md section 1a) from a deal's EX-102 files in period order.

One pass over each monthly file, streaming (parse.iter_loan_months); one small state object per loan is kept for
the deal's life (100k loans at most, scout-autos section 9), never a whole file.

Exit rule (analysis-plan 1a; scout-autos section 5b "Consequences for the panel builder" and section 11
"Retention rule"): a loan's exit period is the earlier of

  (a) the first period in which it carries a non-empty zeroBalanceCode, and
  (b) the last period it is present before its first absence from the deal's file.

exit_type: chargeoff (code 4) / prepay (1) / repurchase (3) / other (2, 5, 99 and any unlisted code) / absent
(dropped with no code) / censored (present with no code in the last file). Code meanings: scout-autos section 4d.

The rule needs no per-issuer branch: CarMax, Capital One and Exeter keep every loan (exits come from the code),
Santander, AmeriCredit and Toyota keep charge-offs but drop payoffs the month after (the code is seen in the payoff
month, so (a) wins), and Ford drops every closed loan after one month (the code is still seen once, in that month).
A loan that vanishes without ever showing a code is `absent`; the share is reported per deal (analysis-plan 1a:
censored in the main run, prepay-like in sensitivity).

Extra column beyond the plan's 1a list: `zb_date`, the zeroBalanceEffectiveDate month at exit. For keep-all
issuers a loan that closed before the panel's first file carries its code in every file, so `exit_period` (rule
(a), first file seen) is the panel start rather than the event month; `zb_date` is the event month.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .deals import RETENTION, Deal
from .parse import LOAN_MONTH_COLUMNS, ParseError, file_period, iter_loan_months

log = logging.getLogger(__name__)

EXIT_TYPES = {"4": "chargeoff", "1": "prepay", "3": "repurchase", "2": "other", "5": "other", "99": "other"}

# analysis-plan 1a, in order, plus zb_date (see module docstring).
LOANS_SCHEMA = pa.schema([
    ("deal", pa.string()), ("lender", pa.string()), ("cik", pa.string()), ("asset_id", pa.string()),
    ("first_period", pa.date32()), ("last_period", pa.date32()), ("orig_month", pa.date32()),
    ("orig_amount", pa.float64()), ("orig_apr", pa.float64()), ("orig_term", pa.int32()), ("pti", pa.float64()),
    ("score", pa.int32()), ("score_type", pa.string()), ("score_missing", pa.bool_()),
    ("vehicle_value", pa.float64()), ("ltv", pa.float64()), ("new_used", pa.string()), ("state", pa.string()),
    ("income_verified", pa.string()), ("employment_verified", pa.string()), ("subvented", pa.string()),
    ("commercial", pa.bool_()),
    ("exit_period", pa.date32()), ("exit_type", pa.string()), ("exit_code", pa.string()),
    ("months_observed", pa.int32()), ("max_dpd", pa.int32()),
    ("first_30_period", pa.date32()), ("first_60_period", pa.date32()), ("first_90_period", pa.date32()),
    ("chargeoff_amount", pa.float64()), ("recovered_amount", pa.float64()),
    ("bal_first", pa.float64()), ("bal_last", pa.float64()),
    ("zb_date", pa.date32()),
])
LOANS_COLUMNS = LOANS_SCHEMA.names

LOAN_MONTHS_SCHEMA = pa.schema([
    ("deal", pa.string()), ("asset_id", pa.string()), ("period", pa.date32()),
    ("balance_begin", pa.float64()), ("balance_end", pa.float64()), ("dpd", pa.int32()), ("zb_code", pa.string()),
    ("scheduled_payment", pa.float64()), ("actual_payment", pa.float64()), ("interest_paid", pa.float64()),
    ("principal_paid", pa.float64()), ("chargeoff_amount", pa.float64()), ("recovered_amount", pa.float64()),
    ("repossessed", pa.bool_()), ("servicing_flag", pa.string()),
])
assert LOAN_MONTHS_SCHEMA.names == LOAN_MONTH_COLUMNS


class _Loan:
    __slots__ = (
        "asset_id", "first_period", "last_period", "orig_month", "orig_amount", "orig_apr", "orig_term", "pti",
        "score", "score_type", "vehicle_value", "new_used", "state", "income_verified", "employment_verified",
        "subvented", "commercial", "code_period", "exit_code", "zb_date", "chargeoff_amount", "recovered_amount",
        "months_observed", "max_dpd", "first_30", "first_60", "first_90", "bal_first", "bal_last", "last_idx",
        "gap_period",
    )

    def __init__(self, row: dict, idx: int) -> None:
        self.asset_id = row["asset_id"]
        self.first_period = row["period"]
        self.last_period = row["period"]
        for k in ("orig_month", "orig_amount", "orig_apr", "orig_term", "pti", "score", "score_type", "vehicle_value",
                  "new_used", "state", "income_verified", "employment_verified", "subvented", "commercial"):
            setattr(self, k, row[k])
        self.code_period = None
        self.exit_code = None
        self.zb_date = None
        self.chargeoff_amount = None
        self.recovered_amount = 0.0
        self.months_observed = 0
        self.max_dpd = None
        self.first_30 = self.first_60 = self.first_90 = None
        self.bal_first = row["balance_end"]
        self.bal_last = None
        self.last_idx = idx - 1
        self.gap_period = None  # last period present before the first absence (rule (b))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def order_files(files: list[str | Path]) -> list[tuple[date, Path]]:
    """Read each file's reporting period (first record only) and return (period, path) in period order.

    Two files with the same period is a caller error (the fetcher keeps one filing per period): fail loudly.
    """
    out: list[tuple[date, Path]] = []
    for f in files:
        p = Path(f)
        period = file_period(p)
        if period is None:
            raise ParseError(f"{p}: could not read a reporting period from the first record")
        out.append((period, p))
    out.sort()
    for (a, pa_), (b, pb) in zip(out, out[1:]):
        if a == b:
            raise ValueError(f"two files share period {a}: {pa_} and {pb}")
    return out


def build_loans(deal: Deal | str, files: list[str | Path], *, lender: str | None = None, cik: str | None = None,
                loan_months_dir: str | Path | None = None) -> pd.DataFrame:
    """One row per loan, columns LOANS_COLUMNS; diagnostics in `df.attrs["diagnostics"]`.

    `files` are the deal's EX-102 files, one per reporting period; they are sorted by period here.
    `loan_months_dir`, if given, receives one parquet per period with exactly the analysis-plan 1b columns.
    """
    if isinstance(deal, Deal):
        slug, lender, cik = deal.deal, deal.lender, deal.cik
    else:
        slug = deal
    lender = (lender or "").lower()
    cik = cik or ""
    t0 = time.monotonic()
    ordered = order_files(files)
    loans: dict[str, _Loan] = {}
    periods: list[date] = []
    file_diags: list[dict] = []
    n_gaps = n_added_late = n_dup_in_file = n_loan_months = n_stubs = n_stubs_unknown = 0
    lm_dir = Path(loan_months_dir) if loan_months_dir else None
    if lm_dir:
        lm_dir.mkdir(parents=True, exist_ok=True)

    for k, (period, path) in enumerate(ordered):
        info: dict = {}
        lm_rows: list[dict] | None = [] if lm_dir else None
        n = 0
        for row in iter_loan_months(path, slug, lender, info):
            n += 1
            aid = row["asset_id"]
            if not aid:
                raise ParseError(f"{path}: record {n} has no assetNumber")
            if row["period"] != period:
                raise ParseError(f"{path}: record {n} period {row['period']} differs from the file's {period}")
            L = loans.get(aid)
            if row["orig_amount"] is None and row["balance_end"] is None:
                # Recovery-only stub (Ford: assetNumber, period and recoveredAmount only, on a loan that has
                # already left the file). scout-autos 11 says drop them; the recovery is still credited to a
                # known loan (analysis-plan 1a: recovered_amount is the sum), presence is not.
                n_stubs += 1
                if L is not None and row["recovered_amount"]:
                    L.recovered_amount += row["recovered_amount"]
                else:
                    n_stubs_unknown += 1
                continue
            if L is None:
                L = loans[aid] = _Loan(row, k)
                if k > 0:
                    n_added_late += 1
            elif L.last_idx == k:
                n_dup_in_file += 1
                continue
            elif L.last_idx != k - 1 and L.gap_period is None:
                n_gaps += 1
                L.gap_period = L.last_period
            L.last_idx = k
            L.last_period = period
            L.months_observed += 1
            L.bal_last = row["balance_end"]
            dpd = row["dpd"]
            if dpd is not None:
                if L.max_dpd is None or dpd > L.max_dpd:
                    L.max_dpd = dpd
                if dpd >= 30 and L.first_30 is None:
                    L.first_30 = period
                if dpd >= 60 and L.first_60 is None:
                    L.first_60 = period
                if dpd >= 90 and L.first_90 is None:
                    L.first_90 = period
            if row["recovered_amount"]:
                L.recovered_amount += row["recovered_amount"]
            if row["zb_code"] and L.code_period is None:
                L.code_period = period
                L.exit_code = row["zb_code"]
                L.zb_date = row["zb_date"]
                L.chargeoff_amount = row["chargeoff_amount"]
            if lm_rows is not None:
                lm_rows.append({c: row[c] for c in LOAN_MONTH_COLUMNS})
        n_loan_months += n
        periods.append(period)
        fd = {"path": str(path), "period": period.isoformat(), "n_records": n, "sha256": _sha256(path),
              **{key: info.get(key) for key in ("pti_rule", "pti_divisor", "pti_sample_median_raw", "dup_counts",
                                                "n_apr_gt_1", "n_periods_other", "n_score_missing", "n_commercial",
                                                "n_pti_gt_1_after")}}
        file_diags.append(fd)
        if info.get("pti_rule") and info.get("n_pti_gt_1_after", 0) > n * 0.01:
            raise ParseError(f"{path}: PTI still above 1 for {info['n_pti_gt_1_after']} records after dividing by 100")
        if lm_rows is not None:
            _write_loan_months(lm_rows, lm_dir / f"{period.isoformat()}.parquet")  # type: ignore[operator]
        log.info("%s: %s %d records (%d loans so far)", slug, period, n, len(loans))

    last_period = periods[-1] if periods else None
    rows = []
    exit_types: Counter[str] = Counter()
    exit_codes: Counter[str] = Counter()
    for L in loans.values():
        absent_period = L.gap_period
        if absent_period is None and last_period is not None and L.last_period < last_period:
            absent_period = L.last_period
        if L.code_period is not None and (absent_period is None or L.code_period <= absent_period):
            exit_period, exit_type, exit_code = L.code_period, EXIT_TYPES.get(L.exit_code, "other"), L.exit_code
        elif absent_period is not None:
            exit_period, exit_type, exit_code = absent_period, "absent", None
        else:
            exit_period, exit_type, exit_code = None, "censored", None
        exit_types[exit_type] += 1
        if exit_code is not None:
            exit_codes[exit_code] += 1
        ltv = (L.orig_amount / L.vehicle_value) if (L.orig_amount is not None and L.vehicle_value
                                                    and L.vehicle_value > 0) else None
        rows.append({
            "deal": slug, "lender": lender, "cik": cik, "asset_id": L.asset_id,
            "first_period": L.first_period, "last_period": L.last_period, "orig_month": L.orig_month,
            "orig_amount": L.orig_amount, "orig_apr": L.orig_apr, "orig_term": L.orig_term, "pti": L.pti,
            "score": L.score, "score_type": L.score_type, "score_missing": L.score is None,
            "vehicle_value": L.vehicle_value, "ltv": ltv, "new_used": L.new_used, "state": L.state,
            "income_verified": L.income_verified, "employment_verified": L.employment_verified,
            "subvented": L.subvented, "commercial": bool(L.commercial),
            "exit_period": exit_period, "exit_type": exit_type, "exit_code": exit_code,
            "months_observed": L.months_observed, "max_dpd": L.max_dpd,
            "first_30_period": L.first_30, "first_60_period": L.first_60, "first_90_period": L.first_90,
            "chargeoff_amount": L.chargeoff_amount, "recovered_amount": L.recovered_amount,
            "bal_first": L.bal_first, "bal_last": L.bal_last, "zb_date": L.zb_date,
        })
    df = _frame(rows)
    n_loans = len(df)
    n_absent = exit_types.get("absent", 0)
    df.attrs["diagnostics"] = {
        "deal": slug, "lender": lender, "cik": cik,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seconds": round(time.monotonic() - t0, 1),
        "n_files": len(ordered), "periods": [p.isoformat() for p in periods],
        "first_period": periods[0].isoformat() if periods else None,
        "last_period": last_period.isoformat() if last_period else None,
        "n_loans": n_loans, "n_loan_months": n_loan_months,
        "exit_type_counts": dict(exit_types), "exit_code_counts": dict(exit_codes),
        "n_absent_without_code": n_absent,
        "share_absent_without_code": round(n_absent / n_loans, 6) if n_loans else None,
        "n_gaps": n_gaps, "n_added_after_first_file": n_added_late, "n_duplicate_ids_within_file": n_dup_in_file,
        "n_recovery_stub_records": n_stubs, "n_recovery_stubs_for_unknown_loans": n_stubs_unknown,
        "n_score_missing": int(df["score_missing"].sum()) if n_loans else 0,
        "n_commercial": int(df["commercial"].sum()) if n_loans else 0,
        "n_ltv_null": int(df["ltv"].isna().sum()) if n_loans else 0,
        "retention_rule": RETENTION.get(lender, "not measured"),
        "exit_rule": "earlier of first non-empty zeroBalanceCode and last period before first absence "
                     "(analysis-plan 1a; scout-autos 5b, 11)",
        "files": file_diags,
    }
    return df


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame.from_records(rows, columns=LOANS_COLUMNS)
    for c in ("first_period", "last_period", "orig_month", "exit_period", "first_30_period", "first_60_period",
              "first_90_period", "zb_date"):
        df[c] = pd.to_datetime(df[c], errors="raise")
    for c in ("orig_term", "score", "max_dpd", "months_observed"):
        df[c] = df[c].astype("Int32")
    for c in ("orig_amount", "orig_apr", "pti", "vehicle_value", "ltv", "chargeoff_amount", "recovered_amount",
              "bal_first", "bal_last"):
        df[c] = df[c].astype("float64")
    for c in ("score_missing", "commercial"):
        df[c] = df[c].astype("bool")
    for c in ("deal", "lender", "cik", "asset_id", "score_type", "new_used", "state", "income_verified",
              "employment_verified", "subvented", "exit_type", "exit_code"):
        df[c] = df[c].astype("string")
    return df


def to_arrow(df: pd.DataFrame, schema: pa.Schema = LOANS_SCHEMA) -> pa.Table:
    cols = []
    for f in schema:
        s = df[f.name]
        if pa.types.is_date32(f.type):
            arr = pa.Array.from_pandas(s).cast(pa.timestamp("ms")).cast(pa.date32())
        else:
            arr = pa.Array.from_pandas(s, type=f.type)
        cols.append(arr)
    return pa.Table.from_arrays(cols, schema=schema)


def _write_loan_months(rows: list[dict], out: Path) -> None:
    df = pd.DataFrame.from_records(rows, columns=LOAN_MONTH_COLUMNS)
    df["period"] = pd.to_datetime(df["period"])
    df["dpd"] = df["dpd"].astype("Int32")
    df["repossessed"] = df["repossessed"].astype("boolean")
    for c in ("deal", "asset_id", "zb_code", "servicing_flag"):
        df[c] = df[c].astype("string")
    pq.write_table(to_arrow(df, LOAN_MONTHS_SCHEMA), out, compression="zstd")


def write_loans(df: pd.DataFrame, out_dir: str | Path, slug: str) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pq_path = out_dir / f"{slug}.parquet"
    js_path = out_dir / f"{slug}.diagnostics.json"
    pq.write_table(to_arrow(df), pq_path, compression="zstd")
    js_path.write_text(json.dumps(df.attrs.get("diagnostics", {}), indent=1, default=str), encoding="utf-8")
    return pq_path, js_path


def files_from_manifest(deal_dir: str | Path, include_offering_pool: bool = False) -> list[Path]:
    """The EX-102 files a fetch left under raw/<deal>/, in period order, from its manifest.json.

    Offering-pool filings (lp/sp/mp variants, scout-autos section 6 item 10) are excluded unless asked for: the
    panel starts at the first post-closing filing.
    """
    deal_dir = Path(deal_dir)
    mf = deal_dir / "manifest.json"
    if mf.exists():
        m = json.loads(mf.read_text(encoding="utf-8"))
        out = []
        for e in sorted(m["filings"], key=lambda e: (e.get("period") or "", e["accession"])):
            if not e.get("file"):
                continue
            if e.get("offering_pool") and not include_offering_pool:
                continue
            out.append(deal_dir / e["file"])
        return out
    # No manifest (e.g. files placed by hand): every .xml not named 103 under an accession folder.
    return sorted(p for p in deal_dir.glob("*/*.xml") if "103" not in p.name.lower())


def build_deal(deal: Deal, raw_root: str | Path, out_dir: str | Path, *, loan_months: bool = False,
               panel_root: str | Path = "data/panel", include_offering_pool: bool = False) -> pd.DataFrame:
    files = files_from_manifest(Path(raw_root) / deal.deal, include_offering_pool)
    if not files:
        raise FileNotFoundError(f"no EX-102 files for {deal.deal} under {raw_root}")
    lm_dir = Path(panel_root) / deal.deal if loan_months else None
    df = build_loans(deal, files, loan_months_dir=lm_dir)
    pq_path, js_path = write_loans(df, out_dir, deal.deal)
    log.info("wrote %s (%d loans) and %s", pq_path, len(df), js_path)
    return df
