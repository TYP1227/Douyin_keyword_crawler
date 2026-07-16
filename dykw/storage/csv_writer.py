from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_COLUMNS = [
    "user_id",
    "username",
    "ip_location",
    "poi_name",
    "poi_address",
    "location_lng",
    "location_lat",
    "inferred_location",
    "publish_time",
    "content_text",
    "post_url",
    "media_type",
    "like_count",
    "comment_count",
]


class CsvWriter:
    def __init__(self, path: str, columns: List[str] = DEFAULT_COLUMNS) -> None:
        self.path = path
        self.columns = columns
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def ensure_exists(self) -> None:
        if Path(self.path).exists():
            return
        with open(self.path, "w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(f, fieldnames=self.columns).writeheader()

    def append_rows(self, rows: Iterable[Dict[str, str]]) -> int:
        rows_list = list(rows)
        if not rows_list:
            return 0

        file_exists = Path(self.path).exists()
        with open(self.path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=self.columns, extrasaction="ignore")
            if not file_exists:
                w.writeheader()
            for r in rows_list:
                w.writerow({k: (r.get(k, "") or "") for k in self.columns})
        return len(rows_list)

