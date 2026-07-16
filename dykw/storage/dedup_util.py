from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, Tuple


def dedup_csv_all_columns(csv_path: str) -> Optional[Tuple[int, int]]:
    """
    对 CSV 按“所有列完全一致”去重，并覆盖原文件。
    返回 (去重前行数, 去重后行数)，如果文件不存在则返回 None。
    """
    p = Path(csv_path)
    if not p.exists():
        return None

    with open(p, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    before = len(rows)
    seen = set()
    deduped = []
    for row in rows:
        marker = tuple((name, row.get(name, "") or "") for name in fieldnames)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    after = len(deduped)

    if after != before:
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(deduped)

    return before, after
