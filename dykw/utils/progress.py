from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Optional


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _shorten(text: str, max_len: int = 28) -> str:
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


@dataclass
class ProgressSnapshot:
    platform: str
    keyword: str
    keyword_index: int
    keyword_total: int
    status: str
    raw_count: int
    max_items: int
    page: int
    max_pages: int


class ConsoleProgress:
    def __init__(self, *, enabled: Optional[bool] = None) -> None:
        self.enabled = sys.stdout.isatty() if enabled is None else enabled
        self.started_at = time.monotonic()
        self._last_len = 0

    def update(self, snapshot: ProgressSnapshot) -> None:
        if not self.enabled:
            return
        elapsed = time.monotonic() - self.started_at
        progress_ratio = self._progress_ratio(snapshot)
        eta = elapsed / progress_ratio - elapsed if progress_ratio > 0.01 else 0
        line = (
            f"[{snapshot.platform}] {snapshot.keyword_index}/{snapshot.keyword_total} "
            f"{_shorten(snapshot.keyword)} | {snapshot.status} | "
            f"候选 {snapshot.raw_count}/{snapshot.max_items} | "
            f"滚动 {snapshot.page}/{snapshot.max_pages} | "
            f"已用 {_fmt_duration(elapsed)} | "
            f"预计剩余 {_fmt_duration(eta)}"
        )
        self._write_line(line)

    def message(self, text: str) -> None:
        if not self.enabled:
            return
        self._write_line(text)

    def clear(self) -> None:
        if not self.enabled or self._last_len <= 0:
            return
        sys.stdout.write("\r" + " " * self._last_len + "\r")
        sys.stdout.flush()
        self._last_len = 0

    def done(self) -> None:
        if self.enabled and self._last_len > 0:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._last_len = 0

    def _write_line(self, line: str) -> None:
        pad = max(0, self._last_len - len(line))
        sys.stdout.write("\r" + line + " " * pad)
        sys.stdout.flush()
        self._last_len = len(line)

    @staticmethod
    def _progress_ratio(snapshot: ProgressSnapshot) -> float:
        if snapshot.keyword_total <= 0:
            return 0
        current_page_ratio = min(1.0, max(snapshot.page, 0) / max(snapshot.max_pages, 1))
        current_item_ratio = min(1.0, max(snapshot.raw_count, 0) / max(snapshot.max_items, 1))
        current_ratio = max(current_page_ratio, current_item_ratio)
        completed = max(snapshot.keyword_index - 1, 0)
        return min(1.0, (completed + current_ratio) / snapshot.keyword_total)
