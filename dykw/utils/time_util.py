from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional


def parse_yyyy_mm_dd(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def ts_to_local_datetime_str(ts: Optional[int]) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ts))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


@dataclass(frozen=True)
class DateRange:
    start: Optional[date]
    end: Optional[date]

    def contains_ts(self, ts: Optional[int]) -> bool:
        if not ts:
            return False
        try:
            d = datetime.fromtimestamp(int(ts)).date()
        except Exception:
            return False

        if self.start and d < self.start:
            return False
        if self.end and d > self.end:
            return False
        return True

