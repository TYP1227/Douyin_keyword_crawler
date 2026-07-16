from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Set


SCHEMA = """
CREATE TABLE IF NOT EXISTS progress (
  keyword TEXT PRIMARY KEY,
  next_offset INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS seen_aweme (
  aweme_id TEXT PRIMARY KEY,
  keyword TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS progress_v2 (
  platform TEXT NOT NULL,
  keyword TEXT NOT NULL,
  next_offset INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY(platform, keyword)
);

CREATE TABLE IF NOT EXISTS seen_item (
  platform TEXT NOT NULL,
  item_id TEXT NOT NULL,
  keyword TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY(platform, item_id)
);
"""


@dataclass
class StateStore:
    db_path: str

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self._connection() as conn:
            conn.executescript(SCHEMA)

    def reset_keywords(self, *, platform: str, keywords: Iterable[str]) -> None:
        keyword_list = [kw for kw in keywords if kw]
        if not keyword_list:
            return
        with self._connection() as conn:
            for keyword in keyword_list:
                conn.execute("DELETE FROM progress_v2 WHERE platform=? AND keyword=?", (platform, keyword))
                conn.execute("DELETE FROM seen_item WHERE platform=? AND keyword=?", (platform, keyword))
                if platform == "douyin":
                    conn.execute("DELETE FROM progress WHERE keyword=?", (keyword,))
                    conn.execute("DELETE FROM seen_aweme WHERE keyword=?", (keyword,))

    def keyword_summaries(self, *, platform: str, keywords: Iterable[str]) -> List[Dict[str, int | str]]:
        keyword_list = [kw for kw in keywords if kw]
        summaries: List[Dict[str, int | str]] = []
        if not keyword_list:
            return summaries
        with self._connection() as conn:
            for keyword in keyword_list:
                row = conn.execute(
                    "SELECT next_offset FROM progress_v2 WHERE platform=? AND keyword=?",
                    (platform, keyword),
                ).fetchone()
                next_offset = int(row[0]) if row else 0
                seen_count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM seen_item WHERE platform=? AND keyword=?",
                        (platform, keyword),
                    ).fetchone()[0]
                )
                summaries.append(
                    {
                        "platform": platform,
                        "keyword": keyword,
                        "next_offset": next_offset,
                        "seen_count": seen_count,
                    }
                )
        return summaries

    def get_next_offset(self, keyword: str, platform: str = "douyin") -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT next_offset FROM progress_v2 WHERE platform=? AND keyword=?",
                (platform, keyword),
            ).fetchone()
            if row:
                return int(row[0])
            if platform == "douyin":
                old_row = conn.execute("SELECT next_offset FROM progress WHERE keyword=?", (keyword,)).fetchone()
                return int(old_row[0]) if old_row else 0
            return 0

    def set_next_offset(self, keyword: str, next_offset: int, platform: str = "douyin") -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO progress_v2(platform, keyword, next_offset, updated_at)
                VALUES(?, ?, ?, datetime('now'))
                ON CONFLICT(platform, keyword) DO UPDATE SET
                  next_offset=excluded.next_offset,
                  updated_at=datetime('now')
                """,
                (platform, keyword, int(next_offset)),
            )
            if platform == "douyin":
                conn.execute(
                    """
                    INSERT INTO progress(keyword, next_offset, updated_at)
                    VALUES(?, ?, datetime('now'))
                    ON CONFLICT(keyword) DO UPDATE SET
                      next_offset=excluded.next_offset,
                      updated_at=datetime('now')
                    """,
                    (keyword, int(next_offset)),
                )

    def is_seen(self, item_id: str, platform: str = "douyin") -> bool:
        if not item_id:
            return False
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_item WHERE platform=? AND item_id=? LIMIT 1",
                (platform, item_id),
            ).fetchone()
            if row:
                return True
            if platform == "douyin":
                old_row = conn.execute("SELECT 1 FROM seen_aweme WHERE aweme_id=? LIMIT 1", (item_id,)).fetchone()
                return bool(old_row)
            return False

    def seen_item_ids(self, platform: str = "douyin") -> Set[str]:
        with self._connection() as conn:
            ids = {
                str(row[0])
                for row in conn.execute("SELECT item_id FROM seen_item WHERE platform=?", (platform,)).fetchall()
                if row[0]
            }
            if platform == "douyin":
                ids.update(
                    str(row[0])
                    for row in conn.execute("SELECT aweme_id FROM seen_aweme").fetchall()
                    if row[0]
                )
            return ids

    def mark_seen(self, item_id: str, keyword: str, platform: str = "douyin") -> None:
        if not item_id:
            return
        with self._connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_item(platform, item_id, keyword) VALUES(?, ?, ?)",
                (platform, item_id, keyword),
            )
            if platform == "douyin":
                conn.execute(
                    "INSERT OR IGNORE INTO seen_aweme(aweme_id, keyword) VALUES(?, ?)",
                    (item_id, keyword),
                )
