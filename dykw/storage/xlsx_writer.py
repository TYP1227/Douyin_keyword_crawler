from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook


def csv_to_xlsx(csv_path: str, xlsx_path: str) -> None:
    Path(xlsx_path).parent.mkdir(parents=True, exist_ok=True)
    csv_file = Path(csv_path)
    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    if csv_file.exists():
        with open(csv_file, "r", newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                ws.append(row)

    wb.save(xlsx_path)
