"""Cut small, valid EX-102 fixtures from the scout files (design/scout-autos.md section 2).

Run from the repo root:  python -m uv run python tests/fixtures/autos/tools/make_fixtures.py

Reads the raw scout artifacts under data/raw/scout/ (not committed, re-fetchable with `gh run download`) and writes
tests/fixtures/autos/<slug>/<period>.xml. Each fixture keeps the source file's XML declaration, root element and
namespace declarations, the record separator and the closing tags verbatim; only the set of <assets> records is cut.

- First month: the first N (300) <assets> records, verbatim.
- Second month (where a same-deal pair exists): every record whose assetNumber is in the first month's set. Record
  order differs between months at CarMax and Capital One (scout-autos section 5a shows zero overlap in the first 25
  ids), so "first 300 of each month" would share no loans; matching on id keeps persistence and the exit rule testable.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[4]
R2 = ROOT / "data/raw/scout/edgar2/scout-edgar-second_pass-34192024913/autos"
OUT = ROOT / "tests/fixtures/autos"
N = 300

SPEC = {
    "sdart-2026-1": [("2026-06", R2 / "sdart-2026-1/0001193125-26-303622/sdart261ex102.xml"),
                     ("2026-07", R2 / "sdart-2026-1/0001193125-26-352879/sdart261ex102.xml")],
    "carmax-2026-2": [("2026-06", R2 / "carmax-2026-2/0002117307-26-000013/cart20262.xml"),
                      ("2026-07", R2 / "carmax-2026-2/0002117307-26-000018/cart20262.xml")],
    "copar-2025-1": [("2026-06", R2 / "copar-2025-1/0001193125-26-304245/copart251ex102_0714-1832.xml"),
                     ("2026-07", R2 / "copar-2025-1/0001193125-26-353478/copart251ex102_0814-1819.xml")],
    "exeter-2025-5": [("2026-06", R2 / "exeter-2025-5/0000929638-26-002770/eart2025-5_exhibit102.xml")],
    "amcar-2024-1": [("2026-07", R2 / "amcar-2024-1/0002020251-26-000030/exh1024650072026.xml")],
    "toyota-2025-a": [("2026-07", R2 / "toyota-2025-a/0001193125-26-370139/taot25aex102.xml")],
    "ford-2025-a": [("2026-07", R2 / "ford-2025-a/0002057342-26-000033/autoloanmonthlydeal1183pool.xml")],
}

XMLNS_RE = re.compile(r'\s+xmlns(?::\w+)?="[^"]*"')


def local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def head_tail_sep(path: Path) -> tuple[bytes, bytes, bytes]:
    """Bytes before the first <assets>, bytes after the last </assets>, and the separator between records."""
    with open(path, "rb") as f:
        head = f.read(1 << 16)
        f.seek(max(0, path.stat().st_size - (1 << 12)))
        tail = f.read()
    i = head.index(b"<assets>")
    header = head[:i]
    j = head.index(b"</assets>", i) + len(b"</assets>")
    k = head.index(b"<assets>", j)
    sep = head[j:k]
    t = tail.rindex(b"</assets>") + len(b"</assets>")
    return header, tail[t:], sep


def records(path: Path, want: set[str] | None, limit: int | None):
    """Yield (assetNumber, serialized record) streaming; stops after `limit` records when set."""
    n = 0
    ctx = etree.iterparse(str(path), events=("end",))
    for _ev, el in ctx:
        if el.getparent() is None or el.getparent().getparent() is not None:
            continue  # only children of the root
        assert local(el.tag) == "assets", el.tag
        aid = next(c.text.strip() for c in el if local(c.tag) == "assetNumber")
        if want is None or aid in want:
            xml = etree.tostring(el, encoding="unicode", with_tail=False)
            xml = XMLNS_RE.sub("", xml, count=2)  # the root already declares the namespaces
            yield aid, xml
            n += 1
            if limit is not None and n >= limit:
                return
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]


def cut(src: Path, dst: Path, want: set[str] | None, limit: int | None) -> set[str]:
    header, tail, sep = head_tail_sep(src)
    ids: set[str] = set()
    parts: list[str] = []
    for aid, xml in records(src, want, limit):
        ids.add(aid)
        parts.append(xml)
    body = sep.decode("utf-8").join(parts)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(header + body.encode("utf-8") + tail)
    etree.parse(str(dst))  # must be well-formed
    print(f"{dst.relative_to(ROOT)}: {len(ids)} records, {dst.stat().st_size:,} bytes", file=sys.stderr)
    return ids


def main() -> None:
    only = set(sys.argv[1:])
    for slug, months in SPEC.items():
        if only and slug not in only:
            continue
        first_ids: set[str] | None = None
        for i, (period, src) in enumerate(months):
            dst = OUT / slug / f"{period}.xml"
            if i == 0:
                first_ids = cut(src, dst, None, N)
            else:
                cut(src, dst, first_ids, None)


if __name__ == "__main__":
    main()
