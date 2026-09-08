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
    "–": "-", "—": "-", "‑": "-", "‒": "-", "­": "",
    " ": " ", " ": " ", " ": " ",
    "�": " ",  # EDGAR serves some files with a literal replacement character where a dash was
}


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
            cells = [c.strip() for c in cells if c and c.strip()]
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


def find_row_after(rs: list[Row], anchor: Row, pattern: str, within: int = 12) -> Row:
    """First row after `anchor` (same table) whose label matches; used for 'i. | Current | x' sub-rows."""
    pat = re.compile(pattern, re.I)
    seen = 0
    for r in rs:
        if r.table != anchor.table or r.index <= anchor.index:
            continue
        seen += 1
        if pat.search(r.label):
            return r
        if seen > within:
            break
    raise ParseError(f"no row matching {pattern!r} within {within} rows after {anchor.text!r}")


_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_DATE_LONG = re.compile(r"([A-Z][a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")
_DATE_NUM = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def parse_date(s: str) -> date:
    """'July 31, 2026', 'Jul 31 2026' or '07/31/2026'."""
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
