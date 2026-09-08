"""Track B, autos: Form ABS-EE exhibit 102 fetcher and loan-level panel builder (TASKS.md B1 and B2).

`main(argv)` is the entry the top-level CLI delegates to (`absrisk autos ...`):

    absrisk autos fetch --deal <slug> [--all] --raw data/raw/autos [--deals data/deals.csv]
    absrisk autos build --deal <slug> --raw data/raw/autos --out data/autos [--loan-months] [--panel data/panel]
    absrisk autos run-local --deal <slug> [--out data/autos] [--scout-root data/raw/scout] [--loan-months]

`run-local` builds `loans` from the scouting files already on disk (design/scout-autos.md section 2) for a deal
that has them; it is the local stand-in for fetch + build while EDGAR is reachable only from Actions (PLAN.md 5).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Scout files per deal slug, relative to --scout-root (design/scout-autos.md section 2, R1/R2 paths).
_R2 = "edgar2/scout-edgar-second_pass-34192024913/autos"
SCOUT_FILES: dict[str, list[str]] = {
    "sdart-2026-1": [f"{_R2}/sdart-2026-1/0001193125-26-303622/sdart261ex102.xml",
                     f"{_R2}/sdart-2026-1/0001193125-26-352879/sdart261ex102.xml"],
    "carmax-2026-2": [f"{_R2}/carmax-2026-2/0002117307-26-000013/cart20262.xml",
                      f"{_R2}/carmax-2026-2/0002117307-26-000018/cart20262.xml"],
    "copar-2025-1": [f"{_R2}/copar-2025-1/0001193125-26-304245/copart251ex102_0714-1832.xml",
                     f"{_R2}/copar-2025-1/0001193125-26-353478/copart251ex102_0814-1819.xml"],
    "exeter-2025-5": [f"{_R2}/exeter-2025-5/0000929638-26-002770/eart2025-5_exhibit102.xml"],
    "exeter-2026-2": [f"{_R2}/exeter-2026-2/0000929638-26-003320/eart2026-2_exhibit102.xml"],
    "amcar-2024-1": [f"{_R2}/amcar-2024-1/0002020251-26-000030/exh1024650072026.xml"],
    "amcar-2023-1": [f"{_R2}/amcar-2023-1/0001963240-26-000029/exh1024460072026.xml"],
    "toyota-2025-a": [f"{_R2}/toyota-2025-a/0001193125-26-370139/taot25aex102.xml"],
    "ford-2025-a": [f"{_R2}/ford-2025-a/0002057342-26-000033/autoloanmonthlydeal1183pool.xml"],
}
# Lender family by slug prefix, for run-local on deals not in data/deals.csv.
_LENDER_BY_PREFIX = {"sdart": "santander", "drive": "santander", "carmax": "carmax", "copar": "capone",
                     "exeter": "exeter", "amcar": "americredit", "toyota": "toyota", "ford": "ford", "honda": "honda"}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="absrisk autos", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="list every ABS-EE filing of a deal and download the EX-102 files")
    f.add_argument("--deal", help="deal slug from data/deals.csv")
    f.add_argument("--all", action="store_true", help="every deal in data/deals.csv")
    f.add_argument("--raw", default="data/raw/autos", help="raw root; files land under <raw>/<deal>/<accession>/")
    f.add_argument("--deals", default="data/deals.csv")

    b = sub.add_parser("build", help="build the loans table for a fetched deal")
    b.add_argument("--deal", required=True)
    b.add_argument("--raw", default="data/raw/autos")
    b.add_argument("--out", default="data/autos", help="where <deal>.parquet and <deal>.diagnostics.json go")
    b.add_argument("--loan-months", action="store_true", help="also write loan_months parquet under --panel/<deal>/")
    b.add_argument("--panel", default="data/panel")
    b.add_argument("--include-offering-pool", action="store_true",
                   help="keep the pre-closing pool filing as the first period (default: start post-closing)")
    b.add_argument("--deals", default="data/deals.csv")

    r = sub.add_parser("run-local", help="build the loans table from the scouting files on disk")
    r.add_argument("--deal", required=True, choices=sorted(SCOUT_FILES))
    r.add_argument("--out", default="data/autos")
    r.add_argument("--scout-root", default="data/raw/scout")
    r.add_argument("--loan-months", action="store_true")
    r.add_argument("--panel", default="data/panel")
    r.add_argument("--deals", default="data/deals.csv")
    return p


def _deal_for(slug: str, deals_csv: str):
    from .deals import Deal, get_deal

    try:
        return get_deal(slug, deals_csv)
    except (KeyError, FileNotFoundError):
        lender = _LENDER_BY_PREFIX.get(slug.split("-", 1)[0], "")
        return Deal(deal=slug, lender=lender)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stderr)
    args = _parser().parse_args(argv)

    if args.cmd == "fetch":
        from .deals import load_deals
        from .fetch import fetch_deal

        if not args.deal and not args.all:
            print("fetch: give --deal <slug> or --all", file=sys.stderr)
            return 2
        deals = load_deals(args.deals)
        if args.deal:
            deals = [d for d in deals if d.deal == args.deal]
            if not deals:
                print(f"fetch: deal {args.deal!r} not in {args.deals}", file=sys.stderr)
                return 2
        rc = 0
        for d in deals:
            try:
                m = fetch_deal(d, args.raw)
                print(json.dumps({k: m[k] for k in ("deal", "filer_cik", "doc_prefix", "n_filings", "n_downloaded",
                                                    "n_skipped", "n_errors")}))
                if m["n_errors"]:
                    rc = 1
            except Exception as e:  # noqa: BLE001  one deal's failure must not stop --all
                logging.getLogger(__name__).exception("fetch %s failed: %s", d.deal, e)
                rc = 1
        return rc

    if args.cmd == "build":
        from .build import build_deal

        deal = _deal_for(args.deal, args.deals)
        df = build_deal(deal, args.raw, args.out, loan_months=args.loan_months, panel_root=args.panel,
                        include_offering_pool=args.include_offering_pool)
        print(json.dumps(_summary(df)))
        return 0

    if args.cmd == "run-local":
        from .build import build_loans, write_loans

        deal = _deal_for(args.deal, args.deals)
        files = [Path(args.scout_root) / p for p in SCOUT_FILES[args.deal]]
        missing = [str(p) for p in files if not p.exists()]
        if missing:
            print("run-local: scout files missing (re-fetch with `gh run download`): " + ", ".join(missing),
                  file=sys.stderr)
            return 2
        lm_dir = Path(args.panel) / deal.deal if args.loan_months else None
        df = build_loans(deal, files, loan_months_dir=lm_dir)
        write_loans(df, args.out, deal.deal)
        print(json.dumps(_summary(df)))
        return 0

    return 2


def _summary(df) -> dict:
    d = df.attrs.get("diagnostics", {})
    keys = ("deal", "n_files", "first_period", "last_period", "n_loans", "n_loan_months", "exit_type_counts",
            "exit_code_counts", "share_absent_without_code", "n_gaps", "n_added_after_first_file", "n_score_missing",
            "n_commercial", "seconds")
    return {k: d.get(k) for k in keys}
