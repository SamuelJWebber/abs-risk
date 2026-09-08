"""Prospectus composition tables -> `cards_composition` rows, and the FICO-bucket -> CFPB-tier crosswalk.

Tables (FICO or VantageScore, credit limit, account age) are found by their header row text inside the
424B prospectus, never by table position. Bucket labels are parsed to integer edges (open ends null),
shares are recomputed from the printed dollar and account columns and checked against the printed
percentages. Schema: design/analysis-plan.md section 3b (plus `bucket_label`, kept for legibility).

Crosswalk rule: a bucket's receivables are spread over the six CFPB tiers uniformly in score
(deep_subprime <= 579, subprime 580-619, near_prime 620-659, prime 660-719, prime_plus 720-799,
superprime 800+), open ends clamped to the 300-850 score range; unscored buckets get weight zero and tier
shares are renormalised over scored receivables. Every straddle and every caveat is a flag on the row.
"""

from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .tables import ParseError, Row, is_number_cell, normalise, parse_date, read_text, tables

COLUMNS = ["trust", "as_of", "table", "bucket_lo", "bucket_hi", "share_receivables", "share_accounts", "score_type",
           "sample_note", "prospectus_accession", "prospectus_file", "bucket_label"]

CROSSWALK_COLUMNS = ["trust", "score_type", "bucket_label", "bucket_lo", "bucket_hi", "w_deep_subprime", "w_subprime",
                     "w_near_prime", "w_prime", "w_prime_plus", "w_superprime", "rule", "flags"]

TIERS = [("deep_subprime", 300, 579), ("subprime", 580, 619), ("near_prime", 620, 659),
         ("prime", 660, 719), ("prime_plus", 720, 799), ("superprime", 800, 850)]
SCORE_MIN, SCORE_MAX = 300, 850
PCT_TOL = 2e-3  # printed share vs recomputed share; one-decimal tables are shaved to sum to 100.0 (0.1pp)

KINDS = ("fico", "credit_limit", "account_age")

# Per-trust facts that the tables themselves do not state (design/scout-cards.md section C).
TRUST_INFO: dict[str, dict] = {
    "amex": {"score_type": "FICO", "note": "FICO refreshed monthly (Standardized Credit Score); buckets 560/660/700/760 "
                                          "do not align with the other trusts"},
    "comet": {"score_type": "FICO", "segments": ("Consumer Segment", "Small Business Segment"),
              "note": "Equifax Enhanced Beacon 5.0 FICO refreshed monthly (April 2026 scores against June 10, 2026 "
                      "receivables)"},
    "chase": {"score_type": "FICO", "note": "FICO table is a statistically significant RANDOM SAMPLE of the Trust Portfolio "
                                           "(Experian/FICO Bankcard Score 8, March 2026); sample receivables are about 5% "
                                           "of the pool"},
    "citi": {"score_type": "FICO", "note": "FICO refreshed monthly on most accounts; the only trust giving the "
                                          "distribution by accounts as well as by receivables"},
    "discover": {"score_type": "FICO", "note": "STALE: last prospectus filed 2023-06-23; DCENT notes defeased "
                                              "2025-12-18; amounts in $000s"},
    "synchrony": {"score_type": "VantageScore", "note": "VantageScore, not FICO, refreshed at least quarterly; "
                                                        "private-label/retail pool"},
    "bofa": {"score_type": "FICO", "note": "single-bureau FICO refreshed within the six months to April 1, 2026"},
}

_KIND_HEADER = {
    "fico": re.compile(r"\b(FICO|VantageScore|Credit Score)\b", re.I),
    "credit_limit": re.compile(r"\bCredit Limit\b", re.I),
    "account_age": re.compile(r"\b(Account Age|Age of Accounts|Age Range|Account Age Range)\b|^Age\b", re.I),
}
_COL_ACCOUNTS = re.compile(r"^(number of accounts|accounts)$", re.I)
_COL_ACCOUNTS_PCT = re.compile(r"(percentage|%) of (total )?(number of )?accounts", re.I)
_COL_RECV_PCT = re.compile(r"(percentage|%) of (total )?(amount of )?receivables", re.I)
_COL_RECV = re.compile(r"receivables", re.I)
_TOTAL = re.compile(r"^(grand )?total\b", re.I)
_SUBTOTAL = re.compile(r"^total \(", re.I)
_AS_OF = re.compile(r"as of (?:the beginning of the day on )?([A-Z][a-z]+ \d{1,2}, \d{4})")


@dataclass
class Bucket:
    label: str
    lo: int | None
    hi: int | None
    note: str
    amount: float | None
    accounts: float | None
    pct_recv: float | None
    pct_accts: float | None
    share_recv: float | None = None
    share_accts: float | None = None


@dataclass
class CompTable:
    trust: str
    kind: str
    segment: str | None
    as_of: date | None
    table_index: int
    header: list[str]
    buckets: list[Bucket]
    total_amount: float | None
    total_accounts: float | None
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- bucket labels

_NUM = re.compile(r"\d+(?:\.\d+)?")


def _clean_label(label: str) -> str:
    s = normalise(label)
    s = re.sub(r"\(\d\)", " ", s)          # footnote markers
    s = s.replace("*", " ").replace("$", " ").replace(",", "")
    s = re.sub(r"\s+", " ", s).strip(" :")
    return s


def parse_bucket(label: str, kind: str) -> tuple[int | None, int | None, str]:
    """Integer edges of a bucket label; (None, None, note) for unscored / other rows.

    Amount edges: lo = ceil(x), hi = floor(x) ("$1,500.01-$5,000.00" -> 1501..5000, "Less than $1,000.99" -> ..1000).
    """
    s = _clean_label(label)
    low = s.lower()
    if re.match(r"^(no (fico )?score|unscored|refreshed fico unavailable|000$|other$|no pre-?set spending limit)", low):
        if "less than or equal to" in low:
            n = _NUM.findall(low)
            return None, int(math.floor(float(n[-1]))), "includes unscored"
        return None, None, "unscored" if kind == "fico" else low
    nums = [float(x) for x in _NUM.findall(s)]
    if not nums:
        raise ParseError(f"bucket label without a number: {label!r}")
    a, b = nums[0], nums[-1]
    if re.search(r"^(less than or equal to|not more than|up to)\b", low) or re.search(r"\bor (less|fewer)\b", low):
        return None, int(math.floor(b)), ""
    if re.search(r"^(less than|under)\b", low):
        return None, int(math.ceil(a)) - 1, ""
    if re.search(r"^over\b", low) and len(nums) >= 2:
        return int(math.floor(a)) + 1, int(math.floor(b)), ""
    if re.search(r"^(over|greater than|more than)\b", low):
        return int(math.floor(a)) + 1, None, ""
    if re.search(r"\b(or more|and above|and over|or greater|or above|or higher)\b", low) or re.search(r"\d\+", s):
        return int(math.ceil(a)), None, ""
    if len(nums) >= 2:
        return int(math.ceil(a)), int(math.floor(b)), ""
    raise ParseError(f"cannot parse bucket label {label!r}")


# ----------------------------------------------------------------------------- table extraction


def _preceding_text(node, chars: int = 6000) -> str:
    parts: list[str] = []
    n = 0
    for s in node.find_all_previous(string=True):
        t = re.sub(r"\s+", " ", str(s)).strip()
        if t:
            parts.append(t)
            n += len(t) + 1
            if n >= chars:
                break
    return normalise(" ".join(reversed(parts)))


def _values(r: Row):
    """Numbers after the first cell (the label, which may itself look numeric, e.g. Citi's FICO bucket '000')."""
    return Row(r.table, r.index, r.cells[1:]).numbers() if len(r.cells) > 1 else []


def _header_row(rows: list[Row]) -> Row | None:
    for r in rows:
        if len(r.cells) >= 3 and sum(1 for c in r.cells if re.search(r"receivables|accounts", c, re.I)) >= 2 \
                and not any(is_number_cell(c) for c in r.cells):
            return r
    return None


def _column_roles(header: list[str]) -> dict[str, int]:
    roles: dict[str, int] = {}
    for i, h in enumerate(header):
        if _COL_ACCOUNTS_PCT.search(h):
            roles.setdefault("pct_accts", i)
        elif _COL_RECV_PCT.search(h):
            roles.setdefault("pct_recv", i)
        elif _COL_ACCOUNTS.match(h.strip()):
            roles.setdefault("accounts", i)
        elif _COL_RECV.search(h):
            roles.setdefault("amount", i)
    return roles



def extract_tables(trust: str, path: Path) -> list[CompTable]:
    """Every FICO / credit-limit / account-age composition table in the prospectus, by header text."""
    text = read_text(path)
    out: list[CompTable] = []
    for t in tables(text):
        hdr = _header_row(t.rows)
        if hdr is None:
            continue
        kind = next((k for k, pat in _KIND_HEADER.items() if pat.search(hdr.cells[0])), None)
        if kind is None:
            continue
        roles = _column_roles(hdr.cells[1:])
        if "amount" not in roles and "pct_recv" not in roles and "pct_accts" not in roles:
            continue
        ncols = len(hdr.cells) - 1
        data = [r for r in t.rows if r.index > hdr.index and len(_values(r)) == ncols]
        if len(data) < 3:
            continue
        pre = _preceding_text(t.node)
        in_table = " ".join(r.text for r in t.rows if r.index < hdr.index)
        m = _AS_OF.findall(in_table) or _AS_OF.findall(pre)
        as_of = parse_date(m[-1]) if m else None
        seg = None
        best = -1
        for s in TRUST_INFO.get(trust, {}).get("segments", ()) or ():
            pos = pre.lower().rfind(s.lower())
            if pos > best:  # the segment heading nearest the table wins
                seg, best = s, pos
        buckets: list[Bucket] = []
        tot_amount = tot_accounts = None
        for r in data:
            vals = [n.value for n in _values(r)]
            label = r.cells[0]
            if _SUBTOTAL.match(label):
                continue
            if _TOTAL.match(label):
                tot_amount = vals[roles["amount"]] if "amount" in roles else None
                tot_accounts = vals[roles["accounts"]] if "accounts" in roles else None
                continue
            lo, hi, note = parse_bucket(label, kind)
            buckets.append(Bucket(
                label=normalise(label), lo=lo, hi=hi, note=note,
                amount=vals[roles["amount"]] if "amount" in roles else None,
                accounts=vals[roles["accounts"]] if "accounts" in roles else None,
                pct_recv=vals[roles["pct_recv"]] / 100.0 if "pct_recv" in roles else None,
                pct_accts=vals[roles["pct_accts"]] / 100.0 if "pct_accts" in roles else None,
            ))
        ct = CompTable(trust, kind, seg, as_of, t.index, hdr.cells, buckets, tot_amount, tot_accounts)
        _finalise_shares(ct)
        out.append(ct)
    return out


def _finalise_shares(ct: CompTable) -> None:
    """Shares from amounts where printed (checked against the printed percentages), else from the percentages."""
    for basis, amt_key, pct_key, tot in (("recv", "amount", "pct_recv", ct.total_amount),
                                         ("accts", "accounts", "pct_accts", ct.total_accounts)):
        have_amt = all(getattr(b, amt_key) is not None for b in ct.buckets) and bool(ct.buckets)
        have_pct = all(getattr(b, pct_key) is not None for b in ct.buckets) and bool(ct.buckets)
        if not have_amt and not have_pct:
            continue
        if have_amt:
            s = sum(getattr(b, amt_key) for b in ct.buckets)
            if tot is None:
                tot = s
                ct.notes.append(f"no total row for {basis}; sum of buckets used")
            elif tot > 0 and abs(s - tot) / tot > 1e-6:
                raise ParseError(f"{ct.trust} {ct.kind} table {ct.table_index}: {basis} buckets sum {s} != total {tot}")
            for b in ct.buckets:
                share = getattr(b, amt_key) / tot if tot else 0.0
                setattr(b, f"share_{basis}", share)
                if have_pct:
                    printed = getattr(b, pct_key)
                    if abs(printed - share) > PCT_TOL:
                        raise ParseError(f"{ct.trust} {ct.kind} {b.label!r}: printed {printed:.5f} vs computed "
                                         f"{share:.5f} ({basis})")
        else:
            for b in ct.buckets:
                setattr(b, f"share_{basis}", getattr(b, pct_key))
            ct.notes.append(f"{basis} shares taken from printed percentages (no amount column)")
        total_share = sum(getattr(b, f"share_{basis}") for b in ct.buckets)
        if abs(total_share - 1.0) > 1e-3:
            raise ParseError(f"{ct.trust} {ct.kind} table {ct.table_index}: {basis} shares sum to {total_share:.5f}")



# ----------------------------------------------------------------------------- per-trust assembly


def combine_segments(tabs: list[CompTable]) -> CompTable:
    """COMET: consumer + small business tables with identical bucket labels, summed by amount and accounts."""
    base = tabs[0]
    labels = [b.label for b in base.buckets]
    for t in tabs[1:]:
        if [b.label for b in t.buckets] != labels:
            raise ParseError(f"{base.trust} {base.kind}: segment tables have different buckets")
    out = CompTable(base.trust, base.kind, "combined", base.as_of, base.table_index, base.header, [], 0.0, 0.0)
    tot_amt = sum(t.total_amount or 0 for t in tabs)
    tot_acc = sum(t.total_accounts or 0 for t in tabs) if all(t.total_accounts is not None for t in tabs) else None
    for i, lab in enumerate(labels):
        bs = [t.buckets[i] for t in tabs]
        amt = sum(b.amount for b in bs)
        acc = sum(b.accounts for b in bs) if all(b.accounts is not None for b in bs) else None
        nb = Bucket(lab, bs[0].lo, bs[0].hi, bs[0].note, amt, acc, None, None,
                    share_recv=amt / tot_amt, share_accts=(acc / tot_acc if acc is not None and tot_acc else None))
        out.buckets.append(nb)
    out.total_amount, out.total_accounts = tot_amt, tot_acc
    weights = ", ".join(f"{t.segment} {100 * (t.total_amount or 0) / tot_amt:.1f}%" for t in tabs)
    out.notes.append(f"segments combined by dollar amount: {weights}")
    return out


def composition_rows(trust: str, path: Path, accession: str) -> tuple[list[dict], list[CompTable]]:
    """cards_composition rows for one prospectus; exactly one table per kind after segment combination."""
    tabs = extract_tables(trust, path)
    info = TRUST_INFO.get(trust, {"score_type": "FICO", "note": ""})
    by_kind: dict[str, list[CompTable]] = defaultdict(list)
    for t in tabs:
        by_kind[t.kind].append(t)
    rows_out: list[dict] = []
    final: list[CompTable] = []
    for kind in KINDS:
        ts = by_kind.get(kind, [])
        if info.get("segments"):
            if len(ts) != len(info["segments"]) or {t.segment for t in ts} != set(info["segments"]):
                raise ParseError(f"{trust} {kind}: expected segment tables {info['segments']}, "
                                 f"got {[(t.table_index, t.segment) for t in ts]}")
            ts.sort(key=lambda t: info["segments"].index(t.segment))
            t = combine_segments(ts)
        elif len(ts) != 1:
            raise ParseError(f"{trust} {kind}: expected exactly one table, got {[(t.table_index, t.header[0]) for t in ts]}")
        else:
            t = ts[0]
        if t.as_of is None:
            raise ParseError(f"{trust} {kind} table {t.table_index}: no 'as of <date>' found")
        final.append(t)
        note = "; ".join(x for x in [info.get("note", ""), *t.notes] if x)
        for b in t.buckets:
            bn = note if not b.note else f"{note}; bucket: {b.note}"
            rows_out.append({
                "trust": trust, "as_of": t.as_of.isoformat(), "table": kind, "bucket_lo": b.lo, "bucket_hi": b.hi,
                "share_receivables": b.share_recv, "share_accounts": b.share_accts,
                "score_type": info["score_type"] if kind == "fico" else "",
                "sample_note": bn, "prospectus_accession": accession, "prospectus_file": Path(path).name,
                "bucket_label": b.label,
            })
    return rows_out, final


def prospectus_files(raw: Path, trusts: tuple[str, ...] | None = None) -> list[tuple[str, str, Path]]:
    """(trust, accession, file) for the latest prospectus under raw/<slug>/prospectus/<accession>/."""
    out = []
    for slug_dir in sorted(Path(raw).iterdir()):
        if not slug_dir.is_dir() or (trusts and slug_dir.name not in trusts) or slug_dir.name not in TRUST_INFO:
            continue
        pdir = slug_dir / "prospectus"
        if not pdir.is_dir():
            continue
        accs = sorted(d for d in pdir.iterdir() if d.is_dir())
        if not accs:
            continue
        acc = max(accs, key=lambda d: (_filing_date(d), d.name))
        files = sorted(p for p in acc.iterdir() if p.suffix.lower() in (".htm", ".html") and not p.name.endswith("-index.html"))
        if not files:
            raise ParseError(f"no prospectus document under {acc}")
        out.append((slug_dir.name, acc.name, files[0]))
    return out


def _filing_date(acc_dir: Path) -> str:
    m = acc_dir / "manifest.json"
    if m.exists():
        import json
        return json.loads(m.read_text(encoding="utf-8")).get("filing_date", "") or ""
    return ""


def build_composition(raw: Path, trusts: tuple[str, ...] | None = None) -> tuple[list[dict], list[CompTable]]:
    rows_out, tabs = [], []
    for trust, acc, f in prospectus_files(raw, trusts):
        r, t = composition_rows(trust, f, acc)
        rows_out.extend(r)
        tabs.extend(t)
    return rows_out, tabs


def write_csv(rows_out: list[dict], out: Path, columns: list[str] = COLUMNS) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        for r in rows_out:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ----------------------------------------------------------------------------- crosswalk


def tier_weights(lo: int | None, hi: int | None) -> dict[str, float]:
    """Uniform-in-score split of [lo, hi] over the six tiers; open ends clamped to 300 / 850."""
    a = SCORE_MIN if lo is None else max(lo, SCORE_MIN)
    b = SCORE_MAX if hi is None else min(hi, SCORE_MAX)
    if b < a:
        raise ParseError(f"empty bucket {lo}-{hi}")
    width = b - a + 1
    out = {}
    for name, t_lo, t_hi in TIERS:
        overlap = max(0, min(b, t_hi) - max(a, t_lo) + 1)
        out[name] = overlap / width
    return out


def build_crosswalk(comp_rows: list[dict]) -> list[dict]:
    """One row per (trust, FICO bucket) in cards_composition, with tier weights, the rule, and flags."""
    out: list[dict] = []
    seen = set()
    for r in comp_rows:
        if r["table"] != "fico":
            continue
        key = (r["trust"], r["bucket_label"])
        if key in seen:
            continue
        seen.add(key)
        lo = _int(r["bucket_lo"])
        hi = _int(r["bucket_hi"])
        flags = []
        if lo is None and hi is None:
            w = {name: 0.0 for name, _, _ in TIERS}
            rule = "unscored: weight 0; tier shares renormalised over scored buckets"
            flags.append("unscored")
        else:
            w = tier_weights(lo, hi)
            a = SCORE_MIN if lo is None else max(lo, SCORE_MIN)
            b = SCORE_MAX if hi is None else min(hi, SCORE_MAX)
            clamp = f" (open end clamped to {SCORE_MIN}/{SCORE_MAX})" if (lo is None or hi is None or lo < SCORE_MIN) else ""
            rule = f"uniform in score over [{a},{b}]{clamp}; weight = tier points / bucket width {b - a + 1}"
            if sum(1 for v in w.values() if v > 0) > 1:
                flags.append("straddle")
                if lo is not None and hi is not None and any(v * (b - a + 1) <= 1.0 + 1e-9 and v > 0 for v in w.values()):
                    flags.append("one_point_offset")
        if "unscored" in (r.get("sample_note") or "").split("bucket: ")[-1] and "includes" in (r.get("sample_note") or ""):
            flags.append("includes_unscored")
        if r["trust"] == "amex":
            flags.append("amex_nonstandard_buckets")
        if r["trust"] == "synchrony":
            flags.append("vantagescore")
        if r["trust"] == "chase":
            flags.append("sample_5pct")
        if r["trust"] == "discover":
            flags.append("stale_2023")
        out.append({"trust": r["trust"], "score_type": r["score_type"], "bucket_label": r["bucket_label"],
                    "bucket_lo": lo, "bucket_hi": hi,
                    **{f"w_{name}": round(w[name], 6) for name, _, _ in TIERS}, "rule": rule, "flags": ",".join(flags)})
    return out


def _int(v) -> int | None:
    if v is None or v == "":
        return None
    return int(float(v))


def tier_shares(comp_rows: list[dict], crosswalk: list[dict]) -> dict[tuple[str, str], dict[str, float]]:
    """{(trust, basis): {tier: share, 'unscored': share}} from FICO rows and the crosswalk, renormalised."""
    xw = {(x["trust"], x["bucket_label"]): x for x in crosswalk}
    out: dict[tuple[str, str], dict[str, float]] = {}
    for basis, col in (("receivables", "share_receivables"), ("accounts", "share_accounts")):
        acc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        unscored: dict[str, float] = defaultdict(float)
        for r in comp_rows:
            if r["table"] != "fico" or r.get(col) in (None, ""):
                continue
            share = float(r[col])
            x = xw.get((r["trust"], r["bucket_label"]))
            if x is None:
                raise ParseError(f"crosswalk has no row for {r['trust']} {r['bucket_label']!r}")
            ws = {name: float(x[f"w_{name}"]) for name, _, _ in TIERS}
            if sum(ws.values()) == 0:
                unscored[r["trust"]] += share
                continue
            for name, wv in ws.items():
                acc[r["trust"]][name] += share * wv
        for trust, tiers in acc.items():
            scored = sum(tiers.values())
            out[(trust, basis)] = {name: tiers[name] / scored for name, _, _ in TIERS}
            out[(trust, basis)]["unscored"] = unscored.get(trust, 0.0)
    return out
