from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from dykw.browser.guard import RiskGuard, RiskStopped


@dataclass
class SearchResult:
    items: List[Dict[str, Any]]
    stopped: bool = False
    reason: str = ""


@dataclass(frozen=True)
class SearchProgress:
    keyword: str
    raw_count: int
    max_items: int
    page: int
    max_pages: int
    status: str = "采集中"


ProgressCallback = Callable[[SearchProgress], None]
ItemCallback = Callable[[List[Dict[str, Any]]], Optional[bool]]


class BrowserSearchClient:
    platform = ""

    def __init__(self, *, page: Any, guard: RiskGuard, max_pages: int, max_empty_pages: int = 2) -> None:
        self.page = page
        self.guard = guard
        self.max_pages = max_pages
        self.max_empty_pages = max_empty_pages

    async def search_keyword(
        self,
        keyword: str,
        *,
        max_items: int,
        progress_callback: Optional[ProgressCallback] = None,
        item_callback: Optional[ItemCallback] = None,
    ) -> SearchResult:
        raise NotImplementedError

    async def _read_json_response(self, response: Any) -> Any:
        content_type = ""
        headers = getattr(response, "headers", {}) or {}
        if isinstance(headers, dict):
            content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
        if "json" not in content_type.lower():
            self.guard.record_response(url=response.url, status=response.status, text="")
            raise ValueError(f"非 JSON 响应：{response.url}")
        text = await response.text()
        self.guard.record_response(url=response.url, status=response.status, text=text)
        return json.loads(text)


def walk_dicts(value: Any) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(walk_dicts(child))
    return found


def unique_items(items: List[Dict[str, Any]], *keys: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        item_id = ""
        for key in keys:
            v = item.get(key)
            if v:
                item_id = str(v)
                break
        marker = item_id or str(id(item))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


__all__ = [
    "BrowserSearchClient",
    "ItemCallback",
    "ProgressCallback",
    "RiskStopped",
    "SearchProgress",
    "SearchResult",
    "unique_items",
    "walk_dicts",
]
