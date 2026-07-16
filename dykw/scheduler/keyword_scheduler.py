from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from dykw.browser.guard import RiskStopped, is_response_budget_reason
from dykw.parser.common import ParsedPost
from dykw.platforms.base import SearchProgress
from dykw.storage.state_sqlite import StateStore
from dykw.utils.logging_util import get_logger
from dykw.utils.progress import ConsoleProgress, ProgressSnapshot
from dykw.utils.time_util import DateRange, parse_yyyy_mm_dd


logger = get_logger()


@dataclass(frozen=True)
class SchedulerConfig:
    platform: str
    keywords: List[str]
    locations: List[str]
    location_mode: str
    location_sep: str
    start_date: Optional[str]
    end_date: Optional[str]
    max_items: int
    no_resume: bool
    max_seen_items: int = 50
    manual_verify: bool = True
    verify_retries: int = 3
    verify_wait_seconds: float = 45.0
    ip_filter: Optional[str] = None
    require_ip: bool = False


class KeywordScheduler:
    def __init__(
        self,
        *,
        cfg: SchedulerConfig,
        client: Any,
        parser_func: Callable[[Dict[str, Any], str], ParsedPost],
        state: StateStore,
        writer: Any,
        prompt_func: Callable[[str], str] = input,
        sleep_func: Optional[Callable[[float], Awaitable[None]]] = None,
        progress: Optional[ConsoleProgress] = None,
    ) -> None:
        self.cfg = cfg
        self.client = client
        self.parser_func = parser_func
        self.state = state
        self.writer = writer
        self.prompt_func = prompt_func
        self.sleep_func = sleep_func or asyncio.sleep
        self.progress = progress or ConsoleProgress()
        self.date_range = DateRange(
            parse_yyyy_mm_dd(cfg.start_date) if cfg.start_date else None,
            parse_yyyy_mm_dd(cfg.end_date) if cfg.end_date else None,
        )
        self.seen_cache = set() if cfg.no_resume else self.state.seen_item_ids(platform=cfg.platform)

    async def run(self) -> None:
        self.state.init()
        keywords = self._expand_keywords()
        try:
            for index, keyword in enumerate(keywords):
                await self._run_one_keyword(keyword, keyword_index=index + 1, keyword_total=len(keywords))
                guard = getattr(self.client, "guard", None)
                if guard and index < len(keywords) - 1:
                    seconds = guard.sleep_seconds()
                    self.progress.message(
                        f"[{self.cfg.platform}] {index + 1}/{len(keywords)} 关键词间休息 {int(seconds)}s | 已完成：{keyword}"
                    )
                    await asyncio.sleep(seconds)
        finally:
            self.progress.done()

    def _expand_keywords(self) -> List[str]:
        if not self.cfg.locations or self.cfg.location_mode == "none":
            return list(self.cfg.keywords)
        out: List[str] = []
        seen = set()
        for kw in self.cfg.keywords:
            for loc in self.cfg.locations:
                x = f"{loc}{self.cfg.location_sep}{kw}".strip()
                if self.cfg.location_mode == "append":
                    x = f"{kw}{self.cfg.location_sep}{loc}".strip()
                if x not in seen:
                    seen.add(x)
                    out.append(x)
        return out

    def _in_date_range(self, publish_time: str) -> bool:
        if not (self.cfg.start_date or self.cfg.end_date):
            return True
        if not publish_time or len(publish_time) < 10:
            return False
        try:
            d = parse_yyyy_mm_dd(publish_time[:10])
        except Exception:
            return False
        if d is None:
            return False
        if self.date_range.start and d < self.date_range.start:
            return False
        if self.date_range.end and d > self.date_range.end:
            return False
        return True

    async def _run_one_keyword(self, keyword: str, *, keyword_index: int = 1, keyword_total: int = 1) -> None:
        self._show_progress(
            SearchProgress(keyword=keyword, raw_count=0, max_items=self.cfg.max_items, page=0, max_pages=1, status="准备"),
            keyword_index=keyword_index,
            keyword_total=keyword_total,
        )
        result = None
        attempt = 0
        processed_ids = set()
        wrote_count = 0
        consecutive_seen = 0
        stop_current_keyword = False
        date_samples: List[str] = []
        missing_time_samples: List[str] = []
        reasons: Dict[str, int] = {
            "invalid_item": 0,
            "seen": 0,
            "missing_time": 0,
            "date": 0,
            "ip_filter": 0,
            "require_ip": 0,
            "missing_url": 0,
            "missing_text": 0,
        }
        reset = getattr(getattr(self.client, "guard", None), "reset_risk", None)
        if reset:
            reset()

        def process_item(item: Dict[str, Any]) -> None:
            nonlocal wrote_count, consecutive_seen, stop_current_keyword
            if stop_current_keyword:
                return
            if not isinstance(item, dict):
                reasons["invalid_item"] += 1
                return

            parsed = self.parser_func(item, keyword)
            item_id = parsed.aweme_id
            marker = item_id or parsed.post_url
            if marker and marker in processed_ids:
                return
            if marker:
                processed_ids.add(marker)

            if not self.cfg.no_resume and item_id and item_id in self.seen_cache:
                reasons["seen"] += 1
                consecutive_seen += 1
                if consecutive_seen >= self.cfg.max_seen_items:
                    stop_current_keyword = True
                return
            consecutive_seen = 0
            if not (parsed.publish_time or "").strip():
                reasons["missing_time"] += 1
                if len(missing_time_samples) < 3:
                    missing_time_samples.append(item_id or parsed.content_text[:20] or "<no-id>")
                return
            if not self._in_date_range(parsed.publish_time):
                reasons["date"] += 1
                if len(date_samples) < 5:
                    date_samples.append(f"{parsed.publish_time[:10]}:{parsed.content_text[:18]}")
                return
            if self.cfg.ip_filter and self.cfg.ip_filter not in (parsed.ip_location or ""):
                reasons["ip_filter"] += 1
                return
            if self.cfg.require_ip and not (parsed.ip_location or "").strip():
                reasons["require_ip"] += 1
                return
            if not (parsed.post_url or "").strip():
                reasons["missing_url"] += 1
                return
            if not (parsed.content_text or "").strip():
                reasons["missing_text"] += 1
                return

            wrote = self.writer.append_rows([parsed.to_row()])
            wrote_count += wrote
            if wrote and item_id:
                self.state.mark_seen(item_id=item_id, keyword=keyword, platform=self.cfg.platform)
                self.seen_cache.add(item_id)

        def process_items(items: List[Dict[str, Any]]) -> bool:
            for item in items:
                process_item(item)
                if stop_current_keyword:
                    return True
            return stop_current_keyword

        while True:
            try:
                result = await self.client.search_keyword(
                    keyword,
                    max_items=self.cfg.max_items,
                    progress_callback=lambda p: self._show_progress(
                        p, keyword_index=keyword_index, keyword_total=keyword_total
                    ),
                    item_callback=process_items,
                )
            except RiskStopped:
                raise
            except TypeError:
                result = await self.client.search_keyword(keyword, max_items=self.cfg.max_items)
            except Exception as exc:
                self.progress.clear()
                logger.exception("[%s] 关键词失败，跳过 keyword=%s err=%s", self.cfg.platform, keyword, exc)
                return

            if stop_current_keyword:
                self.progress.clear()
                logger.info(
                    "[%s] 连续 seen 达到阈值，提前停止当前关键词：keyword=%s max_seen_items=%s",
                    self.cfg.platform,
                    keyword,
                    self.cfg.max_seen_items,
                )
                break
            if not result.stopped:
                break
            if is_response_budget_reason(result.reason):
                self.progress.clear()
                logger.warning("[%s] 当前关键词响应预算耗尽，停止当前关键词：keyword=%s reason=%s", self.cfg.platform, keyword, result.reason)
                break
            if not self.cfg.manual_verify:
                self.progress.clear()
                logger.warning("[%s] 检测到风险提示，已按配置跳过等待：%s", self.cfg.platform, result.reason)
                break
            if attempt >= self.cfg.verify_retries:
                self.progress.clear()
                logger.warning(
                    "[%s] 当前关键词已达到人工验证重试上限，跳过 keyword=%s reason=%s",
                    self.cfg.platform,
                    keyword,
                    result.reason,
                )
                break

            action = await self._wait_for_manual_verification(keyword=keyword, reason=result.reason, attempt=attempt + 1)
            if action == "skip":
                self.progress.clear()
                logger.warning("[%s] 用户选择跳过当前关键词：%s", self.cfg.platform, keyword)
                return
            reset = getattr(getattr(self.client, "guard", None), "reset_risk", None)
            if reset:
                reset()
            attempt += 1

        if result is None:
            return

        process_items(result.items)
        self.state.set_next_offset(keyword=keyword, next_offset=len(result.items), platform=self.cfg.platform)

        reason_text = ", ".join(f"{k}={v}" for k, v in reasons.items() if v) or "none"
        if reasons["date"]:
            self.progress.clear()
            logger.info(
                "[%s] 日期过滤摘要 keyword=%s range=%s..%s samples=%s",
                self.cfg.platform,
                keyword,
                self.cfg.start_date or "",
                self.cfg.end_date or "",
                " | ".join(date_samples) or "<none>",
            )
        if reasons["missing_time"]:
            self.progress.clear()
            logger.warning(
                "[%s] 发布时间缺失 keyword=%s count=%s samples=%s",
                self.cfg.platform,
                keyword,
                reasons["missing_time"],
                " | ".join(missing_time_samples) or "<none>",
            )
        self.progress.message(
            (
                f"[{self.cfg.platform}] {keyword_index}/{keyword_total} {keyword} | 完成 | "
                f"raw={len(result.items)} wrote={wrote_count} stopped={result.reason if result.stopped else 'no'} reasons={reason_text}"
            )
        )

    async def _wait_for_manual_verification(self, *, keyword: str, reason: str, attempt: int) -> str:
        self.progress.clear()
        total = max(1, self.cfg.verify_retries)
        wait_seconds = max(0.0, float(self.cfg.verify_wait_seconds))
        border = "=" * 72
        logger.warning(border)
        logger.warning("!!! 需要人工验证 / 图形验证 / 滑块验证 / 登录确认 !!!")
        logger.warning("平台：%s", self.cfg.platform)
        logger.warning("关键词：%s", keyword)
        logger.warning("原因：%s", reason or "<unknown>")
        logger.warning("第 %s/%s 次人工验证", attempt, total)
        logger.warning("请立即到已连接的 Chrome/Edge 页面完成验证。程序不会绕过验证。")
        logger.warning("程序将先等待 %s 秒；完成后回到终端按 Enter 重试当前关键词，输入 s 跳过。", int(wait_seconds))
        logger.warning(border)
        if wait_seconds > 0:
            await self.sleep_func(wait_seconds)
        prompt = f"[{self.cfg.platform}] 人工验证第 {attempt}/{total} 次：已完成后按 Enter 重试；输入 s 跳过当前关键词："
        try:
            answer = await asyncio.to_thread(self.prompt_func, prompt)
        except EOFError:
            logger.warning("当前终端无法读取输入，跳过人工等待。")
            return "skip"
        if str(answer).strip().lower() in {"s", "skip", "q", "quit"}:
            return "skip"
        return "retry"

    def _show_progress(self, progress: SearchProgress, *, keyword_index: int, keyword_total: int) -> None:
        self.progress.update(
            ProgressSnapshot(
                platform=self.cfg.platform,
                keyword=progress.keyword,
                keyword_index=keyword_index,
                keyword_total=keyword_total,
                status=progress.status,
                raw_count=progress.raw_count,
                max_items=progress.max_items,
                page=progress.page,
                max_pages=progress.max_pages,
            )
        )
