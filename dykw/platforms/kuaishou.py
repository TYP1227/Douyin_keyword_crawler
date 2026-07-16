from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from dykw.browser.guard import RiskStopped
from dykw.platforms.base import (
    BrowserSearchClient,
    ItemCallback,
    ProgressCallback,
    SearchProgress,
    SearchResult,
    unique_items,
    walk_dicts,
)


class KuaishouBrowserClient(BrowserSearchClient):
    platform = "kuaishou"

    def _is_search_response(self, url: str) -> bool:
        url = url.lower()
        if "kuaishou.com/search/" in url:
            return False
        return "kuaishou.com" in url and ("graphql" in url or "vision" in url)

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for d in walk_dicts(data):
            photo = d.get("photo")
            author = d.get("author")
            if isinstance(photo, dict) and isinstance(author, dict) and photo.get("id"):
                item = dict(d)
                item["_item_id"] = str(photo.get("id") or "")
                items.append(item)
        return unique_items(items, "_item_id")

    async def search_keyword(
        self,
        keyword: str,
        *,
        max_items: int,
        progress_callback: Optional[ProgressCallback] = None,
        item_callback: Optional[ItemCallback] = None,
    ) -> SearchResult:
        items: List[Dict[str, Any]] = []
        stop_reason = ""
        current_page = 0

        def report(page: int, status: str = "采集中") -> None:
            nonlocal current_page
            current_page = max(current_page, page)
            if not progress_callback:
                return
            progress_callback(
                SearchProgress(
                    keyword=keyword,
                    raw_count=len(unique_items(items, "_item_id")),
                    max_items=max_items,
                    page=current_page,
                    max_pages=self.max_pages,
                    status=status,
                )
            )

        async def on_response(response: Any) -> None:
            nonlocal stop_reason
            if not self._is_search_response(response.url):
                return
            try:
                data = await self._read_json_response(response)
                found = self._extract_items(data)
                items.extend(found)
                if found and item_callback and item_callback(found):
                    stop_reason = "连续 seen 达到阈值"
                report(page=current_page)
            except RiskStopped as exc:
                stop_reason = str(exc)
            except Exception:
                return

        self.page.on("response", on_response)
        try:
            url = keyword if keyword.startswith("https://www.kuaishou.com/") else f"https://www.kuaishou.com/search/video?searchKey={quote(keyword)}"
            report(page=0, status="打开页面")
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            report(page=0, status="等待响应")
            await self.guard.sleep()
            empty_pages = 0
            for page_no in range(1, self.max_pages + 1):
                if stop_reason or len(unique_items(items, "_item_id")) >= max_items:
                    break
                before = len(unique_items(items, "_item_id"))
                await self.page.mouse.wheel(0, self.guard.scroll_delta())
                report(page=page_no, status="滚动加载")
                await self.guard.sleep()
                after = len(unique_items(items, "_item_id"))
                report(page=page_no)
                empty_pages = empty_pages + 1 if after <= before else 0
                if empty_pages >= self.max_empty_pages:
                    break
        finally:
            remove = getattr(self.page, "remove_listener", None)
            if remove:
                remove("response", on_response)

        uniq = unique_items(items, "_item_id")[:max_items]
        return SearchResult(items=uniq, stopped=bool(stop_reason), reason=stop_reason)
