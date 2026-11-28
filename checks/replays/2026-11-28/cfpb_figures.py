"""Save or replay the seven CFPB figure blocks used in the card calibration."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import openpyxl
import pandas as pd

from absrisk.shape.build_level import WB_2023, WB_2025, build

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIGURES = {
    WB_2023: {"Section 3 - Use of credit": [5, 7, 18], "Section 5 - Avail of Credit": [17]},
    WB_2025: {"Section 4 - Pmts, Debt, Coll.": [53], "Section 2 - Use of credit": [3, 16]},
}
ORIGINAL_SHA256 = {
    WB_2023: "faf96ecc841310ac4c0ba27deef96fb1dbc7bad36e87ca2c164b39f35c1c8254",
    WB_2025: "b7ce8050d956436cdabf64e439ad38f85694b91402075f2b4ea26275b98d914c",
}


def extract(source):
    data = {}
    for filename, sheets in FIGURES.items():
        path = source / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != ORIGINAL_SHA256[filename]:
            raise ValueError(f"Unexpected source workbook: {filename}")
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        data[filename] = {}
        for sheet, figures in sheets.items():
            rows = list(book[sheet].values)
            blocks = []
            for figure in figures:
                label = f"Figure {figure}"
                indexes = [i for i, row in enumerate(rows) if str(row[0]).strip().lower() == label.lower()]
                if len(indexes) != 1:
                    raise ValueError(f"{sheet}: expected one {label}")
                i = indexes[0]
                end = i + 3
                while end < len(rows) and any(v is not None for v in rows[end]):
                    end += 1
                width = max(j for j, v in enumerate(rows[i + 2]) if v is not None) + 1
                for row in rows[i:end]:
                    blocks.append([{"datetime": v.isoformat()} if isinstance(v, datetime) else v for v in row[:width]])
                blocks.append([])
            data[filename][sheet] = blocks
        book.close()
    return data


def replay(data):
    with TemporaryDirectory() as directory:
        raw = Path(directory)
        for filename, sheets in data.items():
            book = openpyxl.Workbook()
            book.remove(book.active)
            for name, rows in sheets.items():
                ws = book.create_sheet(name)
                for row in rows:
                    ws.append([datetime.fromisoformat(v["datetime"]) if isinstance(v, dict) else v for v in row])
            book.save(raw / filename)
        out = raw / "level.csv"
        build(raw).to_csv(out, index=False)
        expected = pd.read_csv(ROOT / "data/ccmr_level.csv")
        pd.testing.assert_frame_equal(pd.read_csv(out), expected, check_dtype=False)
        print(f"Matched all {len(expected)} calibration rows from seven official figure blocks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-originals", type=Path, help="folder containing both original CFPB workbooks")
    args = parser.parse_args()
    data = json.loads((HERE / "cfpb_figure_cells.json").read_text())
    if args.verify_originals and extract(args.verify_originals) != data:
        raise ValueError("Workbook cells differ from the saved source extract")
    replay(data)
