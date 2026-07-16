from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, urlsplit

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

    def _is_direct_url(self, value: str) -> bool:
        value = value.lower().strip()
        return value.startswith(("http://", "https://")) and (
            "kuaishou.com/" in value or "chenzhongtech.com/" in value
        )

    def _is_search_response(self, url: str) -> bool:
        url = url.lower()
        if "kuaishou.com/search/" in url:
            return False
        if "kuaishou.com/rest/v/search/feed" in url:
            return True
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

    def _target_ids_from_url(self, url: str) -> List[str]:
        ids: List[str] = []
        try:
            parsed = urlsplit(url)
        except Exception:
            return ids
        patterns = [
            r"/short-video/([^/?#]+)",
            r"/fw/photo/([^/?#]+)",
            r"/photo/([^/?#]+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, parsed.path)
            if m:
                ids.append(m.group(1))
        query = parse_qs(parsed.query)
        for key in ["photoId", "shareObjectId"]:
            for value in query.get(key, []):
                if value:
                    ids.append(value)
        out: List[str] = []
        seen = set()
        for item_id in ids:
            if item_id and item_id not in seen:
                seen.add(item_id)
                out.append(item_id)
        return out

    def _json_object_at(self, text: str, start: int) -> Optional[Dict[str, Any]]:
        if start < 0 or start >= len(text) or text[start] != "{":
            return None
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            ch = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : index + 1])
                    except Exception:
                        return None
                    return obj if isinstance(obj, dict) else None
        return None

    def _ids_from_share_info(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, dict):
            values = []
            for key in ["photoId", "shareObjectId"]:
                item = value.get(key)
                if item:
                    values.append(str(item))
            return values
        text = str(value)
        query_text = urlsplit(text).query if "?" in text else text
        parsed = parse_qs(query_text)
        ids: List[str] = []
        for key in ["photoId", "shareObjectId"]:
            for item in parsed.get(key, []):
                if item:
                    ids.append(str(item))
        return ids

    def _normalize_embedded_photo_id(self, photo: Dict[str, Any]) -> str:
        ids: List[str] = []
        current_id = photo.get("id")
        if current_id:
            ids.append(str(current_id))
        for key in ["share_info", "shareInfo"]:
            ids.extend(self._ids_from_share_info(photo.get(key)))
        for key in ["photoId", "shareObjectId"]:
            value = photo.get(key)
            if value:
                ids.append(str(value))

        for item_id in ids:
            if item_id and not item_id.isdigit():
                photo["id"] = item_id
                return item_id
        if ids:
            photo["id"] = ids[0]
            return ids[0]
        return ""

    def _extract_embedded_items(self, texts: List[str], *, target_ids: List[str]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for text in texts:
            for match in re.finditer(r'"photo"\s*:', text):
                photo_start = text.find("{", match.end())
                photo = self._json_object_at(text, photo_start)
                if not isinstance(photo, dict):
                    continue
                photo_id = self._normalize_embedded_photo_id(photo)
                if not photo_id:
                    continue

                author: Dict[str, Any] = {}
                author_key = text.rfind('"author"', max(0, match.start() - 5000), match.start())
                if author_key >= 0:
                    author_start = text.find("{", author_key)
                    parsed_author = self._json_object_at(text, author_start)
                    if isinstance(parsed_author, dict):
                        author = parsed_author

                if not author.get("id"):
                    author["id"] = photo.get("userEid") or photo.get("userId") or ""
                if not author.get("name"):
                    author["name"] = photo.get("userName") or ""

                item: Dict[str, Any] = {"photo": photo, "author": author, "_item_id": photo_id}
                items.append(item)

        unique = unique_items(items, "_item_id")
        if target_ids:
            matched = [item for item in unique if str((item.get("photo") or {}).get("id") or "") in target_ids]
            if matched:
                return matched
        with_poi = [item for item in unique if isinstance((item.get("photo") or {}).get("poi"), dict)]
        if with_poi:
            return with_poi
        return unique

    async def _extract_items_from_page_scripts(self, *, target_ids: List[str]) -> List[Dict[str, Any]]:
        try:
            texts = await self.page.evaluate(
                "() => Array.from(document.scripts).map(s => s.textContent || '').filter(Boolean)"
            )
        except Exception:
            return []
        if not isinstance(texts, list):
            return []
        return self._extract_embedded_items([str(text) for text in texts], target_ids=target_ids)

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
        direct_url = self._is_direct_url(keyword)

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
            url = keyword if direct_url else f"https://www.kuaishou.com/search/video?searchKey={quote(keyword)}"
            report(page=0, status="打开页面")
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            report(page=0, status="等待响应")
            await self.guard.sleep()

            if direct_url:
                target_ids = self._target_ids_from_url(str(getattr(self.page, "url", "") or "")) or self._target_ids_from_url(url)
                embedded = await self._extract_items_from_page_scripts(target_ids=target_ids)
                if embedded:
                    items = embedded[:max_items]
                    if item_callback:
                        item_callback(items)
                report(page=0, status="详情解析")
                return SearchResult(items=unique_items(items, "_item_id")[:max_items], stopped=bool(stop_reason), reason=stop_reason)

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
