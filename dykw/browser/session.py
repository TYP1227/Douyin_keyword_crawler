from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass
class BrowserSession:
    playwright: Any
    browser: Any
    context: Any
    page: Any


class BrowserConnectionError(RuntimeError):
    pass


@asynccontextmanager
async def connect_cdp_session(cdp_url: str) -> AsyncIterator[BrowserSession]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 Playwright，请先运行：pip install -r requirements.txt") from exc

    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
    except Exception as exc:
        await playwright.stop()
        raise BrowserConnectionError(
            f"无法连接浏览器 CDP：{cdp_url}。请先用 --remote-debugging-port=9222 启动 Chrome/Edge，并确认浏览器仍在运行。"
        ) from exc

    try:
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        yield BrowserSession(playwright=playwright, browser=browser, context=context, page=page)
    finally:
        # 复用的是用户自己打开的 Chrome/Edge，这里只停止 Playwright。
        await playwright.stop()
