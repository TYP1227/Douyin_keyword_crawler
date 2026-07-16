from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlsplit


RISK_WORDS = (
    "验证码",
    "安全验证",
    "访问频繁",
    "操作频繁",
    "滑块",
    "captcha",
    "sec_verify",
    "login_required",
)
RESPONSE_BUDGET_PREFIX = "响应预算耗尽"


class RiskStopped(RuntimeError):
    pass


@dataclass
class RiskGuard:
    min_sleep: float
    max_sleep: float
    max_responses: int
    risk_stop_count: int
    risk_words: Iterable[str] = RISK_WORDS
    response_count: int = 0
    risk_count: int = 0
    stop_reason: str = field(default="", init=False)

    def sleep_seconds(self) -> float:
        hi = max(self.min_sleep, self.max_sleep)
        lo = min(self.min_sleep, self.max_sleep)
        return random.uniform(lo, hi)

    async def sleep(self) -> float:
        seconds = self.sleep_seconds()
        await asyncio.sleep(seconds)
        return seconds

    def scroll_delta(self) -> int:
        return random.randint(900, 2200)

    def reset_risk(self) -> None:
        self.response_count = 0
        self.risk_count = 0
        self.stop_reason = ""

    def record_response(self, *, url: str, status: int, text: str = "") -> None:
        self.response_count += 1
        if self.response_count > self.max_responses:
            self._stop(f"响应预算耗尽：max_responses={self.max_responses}")
        if status in {403, 429}:
            self._risk(f"风险状态码：status={status} url={_safe_url_label(url)}")
        sample = text[:4000]
        if any(word and word in sample for word in self.risk_words):
            self._risk(f"命中明确风控提示：url={_safe_url_label(url)}")

    def _risk(self, reason: str) -> None:
        self.risk_count += 1
        if self.risk_count >= self.risk_stop_count:
            self._stop(reason)

    def _stop(self, reason: str) -> None:
        self.stop_reason = reason
        raise RiskStopped(reason)


def _safe_url_label(url: str) -> str:
    try:
        p = urlsplit(url)
        return f"{p.netloc}{p.path}"
    except Exception:
        return url.split("?", 1)[0]


def is_response_budget_reason(reason: str) -> bool:
    return str(reason or "").startswith(RESPONSE_BUDGET_PREFIX)
