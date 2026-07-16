from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from dykw.storage.csv_writer import CsvWriter


@dataclass
class OutputPaths:
    csv_path: str
    xlsx_path: str


def resolve_output_paths(out_path: str, out_format: str) -> OutputPaths:
    p = Path(out_path)
    if out_format == "csv":
        return OutputPaths(csv_path=str(p.with_suffix(".csv")), xlsx_path="")
    if out_format == "xlsx":
        return OutputPaths(csv_path=str(p.with_suffix(".csv")), xlsx_path=str(p.with_suffix(".xlsx")))
    return OutputPaths(csv_path=str(p.with_suffix(".csv")), xlsx_path=str(p.with_suffix(".xlsx")))


class OutputWriter:
    def __init__(self, *, out_path: str, out_format: str) -> None:
        self.out_format = out_format
        self.paths = resolve_output_paths(out_path, out_format)
        self.csv = CsvWriter(self.paths.csv_path)

    def ensure_started(self) -> None:
        self.csv.ensure_exists()

    def append_rows(self, rows: Iterable[Dict[str, str]]) -> int:
        return self.csv.append_rows(rows)

    def finalize(self) -> List[str]:
        outputs: List[str] = []
        self.csv.ensure_exists()
        from dykw.storage.dedup_util import dedup_csv_all_columns

        dedup_csv_all_columns(self.paths.csv_path)
        if self.out_format in {"csv", "both"}:
            outputs.append(self.paths.csv_path)
        if self.out_format in {"xlsx", "both"}:
            from dykw.storage.xlsx_writer import csv_to_xlsx

            csv_to_xlsx(self.paths.csv_path, self.paths.xlsx_path)
            outputs.append(self.paths.xlsx_path)
        if self.out_format == "xlsx":
            csv_file = Path(self.paths.csv_path)
            if csv_file.exists():
                csv_file.unlink()
        return outputs
