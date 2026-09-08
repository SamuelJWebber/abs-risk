"""HTML table helpers shared by the 10-D parser and the prospectus composition parser.

Everything here is label-driven: a document becomes a flat list of `Row`s (table index, row index, the
non-empty cell texts) and callers find rows by regex on the row's label text, never by position.
Files downloaded from EDGAR sometimes carry the SGML `<DOCUMENT>...<TEXT>` wrapper; it is stripped.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup


class ParseError(RuntimeError):
    """Anything unexpected in a filing. Raised, never swallowed."""


_SGML_HEAD = re.compile(r"^\s*<DOCUMENT>.*?<TEXT>", re.S | re.I)
_TYPE = re.compile(r"<TYPE>([^<\s]+)", re.I)
_NORMALISE = {
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "‑": "-", "‒": "-", "­": "", "−": "-",
    " ": " ", " ": " ", " ": " ",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    " ": " ", " ": " ", " ": " ", "　": " ", "​": "",
    "�": " ",  # EDGAR serves some files with a literal replacement character where a dash was
    # Windows-1252 punctuation written as numeric references (&#145;..&#151;, 13,157 times in the
    # 10-D corpus). lxml keeps those as the C1 control points U+0091..U+0097 rather than applying
    # the HTML5 cp1252 mapping, so Citi's "Finance Charge Receivables&#151;End of Due Period" and
    # Chase's "Yield&#151;Finance Charge, Fees & Interchange" would otherwise carry an unmatchable
    # character where the dash belongs.
    "": "'", "": "'", "": '"', "": '"', "": "*",
    "": "-", "": "-", "": "...", "": "(TM)",
}

# Footnote marks that EDGAR filings hang off a number ("28,776,718,144.36 †", BofA 2019-2021).
_FOOTNOTE_MARKS = "†‡§¶*•·"
_FOOTNOTE_TAIL = re.compile(r"^(.*?)\s*[" + re.escape(_FOOTNOTE_MARKS) + r"]+$", re.S)


def read_text(path: Path) -> str:
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return normalise(text)


def normalise(text: str) -> str:
    for k, v in _NORMALISE.items():
        text = text.replace(k, v)
    return text


def sgml_type(text: str) -> str | None:
    """Exhibit type from the SGML wrapper (`<TYPE>EX-99.1`), when the file carries one."""
    head = text[:2000]
    if "<DOCUMENT>" not in head.upper():
        return None
    m = _TYPE.search(head)
    return m.group(1).upper() if m else None


def strip_sgml(text: str) -> str:
    return _SGML_HEAD.sub("", text, count=1)


def soup(text: str) -> BeautifulSoup:
    return BeautifulSoup(strip_sgml(text), "lxml")


def doc_text(text: str) -> str:
    """Whole-document text with whitespace collapsed; for titles, period sentences, footnotes."""
    return normalise(re.sub(r"\s+", " ", soup(text).get_text(" ")).strip())


@dataclass
class Row:
    table: int
    index: int
    cells: list[str]

    @property
    def text(self) -> str:
        return " | ".join(self.cells)

    @property
    def label(self) -> str:
        """Leading non-numeric cells joined (row numbering like '12)' or 'c.' is kept, so match with search)."""
        out = []
        for c in self.cells:
            if is_number_cell(c) or c in ("$", "%"):
                break
            out.append(c)
        return " ".join(out)

    def numbers(self) -> list[Num]:
        """Numeric cells after the label, tagged with whether a `$` preceded or a `%` followed them."""
        out: list[Num] = []
        dollar = False
        cells = self.cells
        for i, c in enumerate(cells):
            if c == "$":
                dollar = True
                continue
            if c == "%":
                if out:
                    out[-1].pct = True
                continue
            if is_number_cell(c):
                v = parse_number(c)
                pct = c.endswith("%") or (i + 1 < len(cells) and cells[i + 1] == "%")
                out.append(Num(v, pct=pct, dollar=dollar or c.startswith("$")))
                dollar = False
        return out

    def first(self) -> float:
        n = self.numbers()
        if not n:
            raise ParseError(f"no number in row {self.text!r}")
        return n[0].value

    def last(self) -> float:
        n = self.numbers()
        if not n:
            raise ParseError(f"no number in row {self.text!r}")
        return n[-1].value

    def dollars(self) -> float:
        """The number that follows a `$` cell; else the first number that is not a percentage."""
        n = self.numbers()
        for x in n:
            if x.dollar:
                return x.value
        for x in n:
            if not x.pct:
                return x.value
        raise ParseError(f"no dollar amount in row {self.text!r}")

    def pct(self, which: int = 0) -> float:
        """The which-th percentage in the row, as a fraction (2.96% -> 0.0296)."""
        ps = [x for x in self.numbers() if x.pct]
        if len(ps) <= which:
            raise ParseError(f"no percentage #{which} in row {self.text!r}")
        return ps[which].value / 100.0


@dataclass
class Num:
    value: float
    pct: bool = False
    dollar: bool = False


_NUM_RE = re.compile(r"^\(?-?\$?\s?[\d,]*\d(\.\d+)?\)?%?$")


def strip_footnote(c: str) -> str:
    """Drop a trailing footnote mark from a cell whose remainder is a number.

    BofA 2018-2021 prints "$ | 28,776,718,144.36 †" (the dagger is a <sup> pointing at the
    "amounts are unaudited" note); the mark is presentation, not data. Only cells that are numbers
    once the mark is removed are touched, so a label such as "Total*" keeps its asterisk.
    """
    m = _FOOTNOTE_TAIL.match(c.strip())
    if m and m.group(1) and _NUM_RE.match(m.group(1).strip().replace(" ", "")):
        return m.group(1).strip()
    return c


def is_number_cell(c: str) -> bool:
    c = c.strip()
    if c in ("-", "--", "N/A", "n/a", "NA"):
        return True
    if c.count("(") != c.count(")"):  # row numbering such as "12)" is a label, not a number
        return False
    return bool(_NUM_RE.match(c.replace(" ", "")))


def parse_number(c: str) -> float:
    s = c.strip().replace(" ", "")
    if s in ("-", "--"):
        return 0.0
    if s.upper() in ("N/A", "NA"):
        return float("nan")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").rstrip("%")
    v = float(s)
    return -v if neg else v


@dataclass
class Table:
    index: int
    rows: list[Row] = field(default_factory=list)
    node: object = None

    def text(self) -> str:
        return "\n".join(r.text for r in self.rows)


def tables(text: str) -> list[Table]:
    out: list[Table] = []
    for ti, tbl in enumerate(soup(text).find_all("table")):
        t = Table(index=ti, node=tbl)
        ri = 0
        for tr in tbl.find_all("tr"):
            cells = [normalise(re.sub(r"\s+", " ", td.get_text(" ", strip=True))) for td in tr.find_all(["td", "th"])]
            cells = [strip_footnote(c.strip()) for c in cells if c and c.strip()]
            if cells:
                t.rows.append(Row(ti, ri, cells))
            ri += 1
        out.append(t)
    return out


def rows(text: str) -> list[Row]:
    return [r for t in tables(text) for r in t.rows]


def find_rows(rs: list[Row], pattern: str, *, table: int | None = None) -> list[Row]:
    pat = re.compile(pattern, re.I)
    return [r for r in rs if (table is None or r.table == table) and pat.search(r.label)]


def find_row(rs: list[Row], pattern: str, *, table: int | None = None, nth: int = 0) -> Row:
    """The nth row whose label matches. Raises if there is none."""
    hits = find_rows(rs, pattern, table=table)
    if len(hits) <= nth:
        raise ParseError(f"label {pattern!r} not found (match #{nth}, {len(hits)} hits)")
    return hits[nth]


def _position(rs: list[Row], row: Row) -> int:
    for i, r in enumerate(rs):
        if r is row:
            return i
    raise ParseError(f"row {row.text!r} is not in this row list")


def find_row_after(rs: list[Row], anchor: Row, pattern: str, within: int = 12, *,
                   cross_table: bool = False) -> Row:
    """First row after `anchor` whose label matches; used for 'i. | Current | x' sub-rows.

    `cross_table=True` continues into the following tables in document order. Synchrony's Nov-2019 to
    Mar-2022 statements put the block header ("a. Gross Trust Yield (...)") and its "i. Current" /
    "ii. Three-Month Average" sub-rows in two separate <table> elements; from Apr-2022 they are one
    table. The row window (`within`) is unchanged, so the search still cannot wander far.
    """
    pat = re.compile(pattern, re.I)
    for seen, r in enumerate(rs[_position(rs, anchor) + 1:], start=1):
        if not cross_table and r.table != anchor.table:
            break
        if pat.search(r.label):
            return r
        if seen > within:
            break
    raise ParseError(f"no row matching {pattern!r} within {within} rows after {anchor.text!r}")


def find_first(rs: list[Row], patterns, *, table: int | None = None, nth: int = 0) -> Row:
    """The row matching the first of `patterns` that matches anything, tried in order.

    `patterns` is the ordered list of label variants a field is known to appear under (one entry per
    layout era; see design/cards-build.md "Historical layout variants"). Every entry must be a label
    seen in a real filing - this is an alternation over known labels, not a relaxed pattern.
    """
    if isinstance(patterns, str):
        patterns = (patterns,)
    for pat in patterns:
        hits = find_rows(rs, pat, table=table)
        if len(hits) > nth:
            return hits[nth]
    raise ParseError(f"none of the label variants {tuple(patterns)!r} found (match #{nth})")


def join_wrapped(rs: list[Row], row: Row, full: str, *, max_rows: int = 3) -> Row:
    """`row` plus the following rows that carry the rest of a label wrapped across several <tr>s.

    Amex and Chase break a long row label over two or three physical table rows, and the number lands
    on whichever of them the wrap reached: five shapes occur for Amex's beginning-balance row alone
    (design/cards-build.md section 6), and they alternate month to month rather than by era.

    Rows are appended one at a time and the first join whose non-numeric cells match `full` - the
    complete label, anchored - and that carries a number is returned, so the join is verified against
    the known label rather than assumed from the layout.
    """
    pat = re.compile(full, re.I)
    cells = list(row.cells)
    start = _position(rs, row)
    for extra in range(max_rows + 1):
        if extra:
            nxt = rs[start + extra] if start + extra < len(rs) else None
            if nxt is None or nxt.table != row.table:
                break
            cells = cells + nxt.cells
        cand = Row(row.table, row.index, cells)
        text = " ".join(c for c in cells if not is_number_cell(c) and c not in ("$", "%"))
        if pat.search(text) and cand.numbers():
            return cand
    raise ParseError(f"label {full!r} not reproduced by row {row.text!r} joined with the "
                     f"{max_rows} rows after it")


_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
# Internal spacing inside a date is formatting, not data: BofA's charge-off table header prints
# "March 31,2023" (no space after the comma) and Synchrony's Jan/Feb 2020 statements print
# "01 /31/2020". Both forms are accepted; nothing else about the date is relaxed.
_DATE_LONG = re.compile(r"([A-Z][a-z]+)\.?\s+(\d{1,2})(?:\s*,\s*|\s+)(\d{4})")
_DATE_NUM = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})")


def parse_date(s: str) -> date:
    """'July 31, 2026', 'Jul 31 2026', 'March 31,2023', '07/31/2026' or '01 /31/2020'."""
    m = _DATE_LONG.search(s)
    if m and m.group(1).lower() in _MONTHS:
        return date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
    m = _DATE_NUM.search(s)
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    raise ParseError(f"no date in {s!r}")


def month_end(month_name: str, year: int) -> date:
    m = _MONTHS.get(month_name.lower())
    if not m:
        raise ParseError(f"unknown month {month_name!r}")
    return date(year, m, calendar.monthrange(year, m)[1])


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol
