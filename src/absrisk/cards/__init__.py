"""Track A: card master trust pools.

    absrisk cards fetch [--trust <slug>] [--since 2019-01-01] --raw data/raw/cards [--force] [--no-prospectus] [--limit N]
    absrisk cards parse --raw data/raw/cards --out data/cards_monthly.csv
    absrisk cards composition --raw data/raw/cards --out data/cards_composition.csv [--crosswalk crosswalks/fico_buckets.csv]

`fetch` needs EDGAR (runs on a GitHub Actions runner, PLAN.md section 5); `parse` and `composition` run on
downloaded files only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="absrisk cards", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="download 10-D filings and the latest prospectus per trust")
    p.add_argument("--trust", action="append", help="slug (repeatable); default all six live trusts")
    p.add_argument("--since", default="2019-01-01", help="earliest filing date, YYYY-MM-DD")
    p.add_argument("--raw", default="data/raw/cards", type=Path)
    p.add_argument("--force", action="store_true", help="re-download filings that already have a complete manifest")
    p.add_argument("--no-prospectus", action="store_true")
    p.add_argument("--limit", type=int, default=None, help="only the N newest filings per trust (smoke tests)")

    p = sub.add_parser("parse", help="parse every downloaded 10-D into cards_monthly.csv")
    p.add_argument("--raw", default="data/raw/cards", type=Path)
    p.add_argument("--out", default="data/cards_monthly.csv", type=Path)
    p.add_argument("--trust", action="append")

    p = sub.add_parser("composition", help="parse prospectus composition tables and write the tier crosswalk")
    p.add_argument("--raw", default="data/raw/cards", type=Path)
    p.add_argument("--out", default="data/cards_composition.csv", type=Path)
    p.add_argument("--crosswalk", default="crosswalks/fico_buckets.csv", type=Path)
    p.add_argument("--trust", action="append")

    args = parser.parse_args(argv)
    if args.cmd == "fetch":
        return _fetch(args)
    if args.cmd == "parse":
        return _parse(args)
    if args.cmd == "composition":
        return _composition(args)
    parser.print_help()
    return 1


def _fetch(args) -> int:
    from absrisk.http import make_session

    from .fetch import fetch_all

    summaries = fetch_all(make_session(), args.raw, trusts=args.trust, since=args.since, force=args.force,
                          prospectus=not args.no_prospectus, limit=args.limit)
    bad = 0
    for s in summaries:
        pros = s.get("prospectus")
        print(f"{s['slug']:<10} filings {s['n_filings']:>4}  fetched {s['fetched']:>4}  skipped {s['skipped']:>4}  "
              f"errors {len(s['errors']):>3}  prospectus {pros.get('accession') if pros else None}")
        bad += len(s["errors"]) + (1 if pros and pros.get("error") else 0)
    return 1 if bad else 0


def _parse(args) -> int:
    from .parse import TRUSTS, coverage, parse_raw, write_csv

    trusts = tuple(args.trust) if args.trust else TRUSTS
    rows, errors = parse_raw(args.raw, trusts)
    write_csv(rows, args.out)
    print(f"{len(rows)} rows -> {args.out}")
    print(coverage(rows))
    for trust, acc, err in errors:
        print(f"ERROR {trust} {acc}: {err}", file=sys.stderr)
    return 1 if errors else 0


def _composition(args) -> int:
    from .composition import (CROSSWALK_COLUMNS, TIERS, build_composition, build_crosswalk, tier_shares, write_csv)

    trusts = tuple(args.trust) if args.trust else None
    rows, tabs = build_composition(args.raw, trusts)
    write_csv(rows, args.out)
    xw = build_crosswalk(rows)
    write_csv(xw, args.crosswalk, CROSSWALK_COLUMNS)
    print(f"{len(rows)} rows -> {args.out}; {len(xw)} crosswalk rows -> {args.crosswalk}")
    print(f"{'trust':<10}{'table':<14}{'as_of':<12}{'buckets':>8}  notes")
    for t in tabs:
        print(f"{t.trust:<10}{t.kind:<14}{t.as_of.isoformat():<12}{len(t.buckets):>8}  {'; '.join(t.notes)}")
    shares = tier_shares(rows, xw)
    print("\ntier shares under the crosswalk (renormalised over scored buckets)")
    print(f"{'trust':<10}{'basis':<12}" + "".join(f"{n:>14}" for n, _, _ in TIERS) + f"{'unscored':>10}")
    for (trust, basis), s in sorted(shares.items()):
        print(f"{trust:<10}{basis:<12}" + "".join(f"{s[n]:>14.4f}" for n, _, _ in TIERS) + f"{s['unscored']:>10.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
