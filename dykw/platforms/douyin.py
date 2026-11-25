from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, urlparse

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
from dykw.utils.logging_util import get_logger


logger = get_logger()

TRANSIENT_NAVIGATION_STATUSES = {500, 502, 503, 504}
NAVIGATION_ATTEMPTS = 2


class DouyinBrowserClient(BrowserSearchClient):
    platform = "douyin"

    def _is_search_response(self, url: str) -> bool:
        url = url.lower()
        if "douyin.com/search/" in url:
            return False
        return "douyin.com" in url and (
            "/aweme/v1/web/general/search" in url
            or "/aweme/v1/web/search" in url
            or "/aweme/v1/web/aweme/detail" in url
        )

    def _normalize_entry_url(self, keyword: str) -> str:
        if not keyword.startswith("https://www.douyin.com/"):
            return f"https://www.douyin.com/search/{quote(keyword)}?type=video"
        parsed = urlparse(keyword)
        modal_id = (parse_qs(parsed.query).get("modal_id") or [""])[0]
        if modal_id:
            return f"https://www.douyin.com/video/{modal_id}"
        return keyword

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for d in walk_dicts(data):
            aweme_info = d.get("aweme_info")
            if isinstance(aweme_info, dict):
                items.append(aweme_info)
            elif d.get("aweme_detail") and isinstance(d.get("aweme_detail"), dict):
                items.append(d["aweme_detail"])
            elif d.get("aweme_id") and isinstance(d.get("author"), dict):
                items.append(d)
        return unique_items(items, "aweme_id")

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
                    raw_count=len(unique_items(items, "aweme_id")),
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
                if not found and isinstance(data, dict):
                    logger.debug("抖音接口未解析到作品：url=%s keys=%s", response.url.split("?", 1)[0], list(data.keys()))
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
            url = self._normalize_entry_url(keyword)
            report(page=0, status="打开页面")
            for attempt in range(1, NAVIGATION_ATTEMPTS + 1):
                response = await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                if response is None:
                    stop_reason = "搜索页未返回导航响应"
                    logger.warning("抖音搜索页未返回导航响应：keyword=%s", keyword)
                    break

                status = int(response.status)
                response_url = str(response.url or url)
                try:
                    page_text = await self.page.evaluate(
                        "() => `${document.title || ''}\n${document.body?.innerText || ''}`.slice(0, 4000)"
                    )
                except Exception as exc:
                    logger.debug(
                        "读取抖音搜索页可见文本失败：url=%s err=%s",
                        response_url.split("?", 1)[0],
                        type(exc).__name__,
                    )
                    page_text = ""

                try:
                    self.guard.record_response(url=response_url, status=status, text=str(page_text or ""))
                except RiskStopped as exc:
                    stop_reason = str(exc)
                    report(page=0, status="需要人工验证")
                    break

                if status < 400:
                    break
                if status in TRANSIENT_NAVIGATION_STATUSES and attempt < NAVIGATION_ATTEMPTS:
                    logger.warning(
                        "抖音搜索页响应异常，等待后重试：status=%s attempt=%s/%s keyword=%s",
                        status,
                        attempt,
                        NAVIGATION_ATTEMPTS,
                        keyword,
                    )
                    report(page=0, status=f"页面异常 {status}，等待重试")
                    await self.guard.sleep()
                    continue

                stop_reason = f"搜索页响应异常：status={status}"
                logger.warning("抖音搜索页响应异常，停止当前关键词：status=%s keyword=%s", status, keyword)
                report(page=0, status=f"页面异常 {status}")
                break

            if not stop_reason:
                report(page=0, status="等待响应")
                await self.guard.sleep()
                empty_pages = 0
                for page_no in range(1, self.max_pages + 1):
                    if stop_reason or len(unique_items(items, "aweme_id")) >= max_items:
                        break
                    before = len(unique_items(items, "aweme_id"))
                    await self.page.mouse.wheel(0, self.guard.scroll_delta())
                    report(page=page_no, status="滚动加载")
                    await self.guard.sleep()
                    after = len(unique_items(items, "aweme_id"))
                    report(page=page_no)
                    empty_pages = empty_pages + 1 if after <= before else 0
                    if empty_pages >= self.max_empty_pages:
                        break
        finally:
            remove = getattr(self.page, "remove_listener", None)
            if remove:
                remove("response", on_response)

        uniq = unique_items(items, "aweme_id")[:max_items]
        return SearchResult(items=uniq, stopped=bool(stop_reason), reason=stop_reason)
