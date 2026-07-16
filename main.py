from __future__ import annotations

import asyncio
from typing import Dict, Iterable, List, Optional

from dykw.browser.guard import RiskGuard, RiskStopped
from dykw.browser.session import BrowserConnectionError, connect_cdp_session
from dykw.config.cli import parse_args
from dykw.storage.state_sqlite import StateStore
from dykw.utils.logging_util import get_logger, setup_logging
from dykw.utils.proxy_util import load_proxy_list


VALID_PROXY_PREFIXES = ("http://", "https://", "socks5://", "socks5h://")


def _expand_keywords_from_cfg(cfg) -> List[str]:
    if not cfg.locations or cfg.location_mode == "none":
        return list(cfg.keywords)
    out: List[str] = []
    seen = set()
    for kw in cfg.keywords:
        for loc in cfg.locations:
            x = f"{loc}{cfg.location_sep}{kw}".strip()
            if cfg.location_mode == "append":
                x = f"{kw}{cfg.location_sep}{loc}".strip()
            if x not in seen:
                seen.add(x)
                out.append(x)
    return out


def _proxy_summary(proxies: Iterable[str]) -> Dict[str, int]:
    proxy_list = list(proxies)
    unique = set(proxy_list)
    invalid_scheme = sum(1 for item in proxy_list if not item.startswith(VALID_PROXY_PREFIXES))
    return {
        "count": len(proxy_list),
        "unique_count": len(unique),
        "duplicate_count": len(proxy_list) - len(unique),
        "invalid_scheme_count": invalid_scheme,
    }


def _pick_stable_proxy(*, proxy: Optional[str], proxy_list_path: Optional[str]) -> Optional[str]:
    if proxy:
        return proxy
    if not proxy_list_path:
        return None
    proxies = [p for p in load_proxy_list(proxy_list_path) if p.startswith(VALID_PROXY_PREFIXES)]
    return proxies[0] if proxies else None


def _log_diagnostics(*, cfg, state: StateStore, keywords: List[str], proxies: List[str]) -> None:
    logger = get_logger()
    state.init()
    proxy = _proxy_summary(proxies)
    logger.info("诊断模式：不会连接浏览器，也不会访问平台")
    logger.info(
        "诊断配置：platform=%s browser=%s cdp=%s keywords=%s expanded_keywords=%s out_format=%s state_db=%s",
        cfg.platform,
        cfg.browser_channel,
        cfg.cdp_url,
        len(cfg.keywords),
        len(keywords),
        cfg.out_format,
        cfg.state_db_path,
    )
    logger.info(
        "诊断代理：single_proxy=%s proxy_list_count=%s unique=%s duplicates=%s invalid_scheme=%s",
        bool(cfg.proxy),
        proxy["count"],
        proxy["unique_count"],
        proxy["duplicate_count"],
        proxy["invalid_scheme_count"],
    )
    if cfg.proxy or cfg.proxy_list:
        logger.warning("代理只建议作为稳定出口使用；CDP 模式下应先让 Chrome/Edge 自身走该代理")
    for item in state.keyword_summaries(platform=cfg.platform, keywords=keywords):
        logger.info(
            "诊断状态：platform=%s keyword=%s last_raw_count=%s seen_count=%s",
            item["platform"],
            item["keyword"],
            item["next_offset"],
            item["seen_count"],
        )


def _build_platform_client(cfg, page, guard: RiskGuard):
    if cfg.platform == "douyin":
        from dykw.parser.douyin_aweme_parser import parse_aweme_info
        from dykw.platforms.douyin import DouyinBrowserClient

        return (
            DouyinBrowserClient(page=page, guard=guard, max_pages=cfg.max_pages, max_empty_pages=cfg.max_empty_pages),
            parse_aweme_info,
        )
    if cfg.platform == "kuaishou":
        from dykw.parser.kuaishou_post_parser import parse_kuaishou_feed
        from dykw.platforms.kuaishou import KuaishouBrowserClient

        return (
            KuaishouBrowserClient(page=page, guard=guard, max_pages=cfg.max_pages, max_empty_pages=cfg.max_empty_pages),
            parse_kuaishou_feed,
        )
    raise RuntimeError(f"不支持的平台：{cfg.platform}")


async def _run() -> None:
    cfg = parse_args()
    setup_logging(cfg.log_level)
    logger = get_logger()

    expanded_keywords = _expand_keywords_from_cfg(cfg)
    state = StateStore(db_path=cfg.state_db_path)
    proxies = load_proxy_list(cfg.proxy_list) if cfg.proxy_list else []
    stable_proxy = _pick_stable_proxy(proxy=cfg.proxy, proxy_list_path=cfg.proxy_list)

    if cfg.diagnose:
        _log_diagnostics(cfg=cfg, state=state, keywords=expanded_keywords, proxies=proxies)
        return

    state.init()
    if cfg.reset_state:
        state.reset_keywords(platform=cfg.platform, keywords=expanded_keywords)
        logger.warning("[%s] 状态已重置：keywords=%s db=%s", cfg.platform, len(expanded_keywords), cfg.state_db_path)

    if stable_proxy:
        logger.warning("检测到代理配置：请确认 %s 已在 Chrome/Edge 中作为稳定出口使用", stable_proxy)

    from dykw.scheduler.keyword_scheduler import KeywordScheduler, SchedulerConfig
    from dykw.storage.output_writer import OutputWriter

    writer = OutputWriter(out_path=cfg.out_path, out_format=cfg.out_format)
    writer.ensure_started()
    guard = RiskGuard(
        min_sleep=cfg.min_sleep,
        max_sleep=cfg.max_sleep,
        max_responses=cfg.max_responses,
        risk_stop_count=cfg.risk_stop_count,
    )

    logger.info(
        "连接浏览器：browser=%s cdp=%s。请确保该浏览器已经登录目标平台",
        cfg.browser_channel,
        cfg.cdp_url,
    )
    try:
        async with connect_cdp_session(cfg.cdp_url) as session:
            client, parser_func = _build_platform_client(cfg, session.page, guard)
            scheduler = KeywordScheduler(
                cfg=SchedulerConfig(
                    platform=cfg.platform,
                    keywords=cfg.keywords,
                    locations=cfg.locations,
                    location_mode=cfg.location_mode,
                    location_sep=cfg.location_sep,
                    start_date=cfg.start_date,
                    end_date=cfg.end_date,
                    max_items=cfg.max_items,
                    max_seen_items=cfg.max_seen_items,
                    no_resume=cfg.no_resume,
                    manual_verify=cfg.manual_verify,
                    verify_retries=cfg.verify_retries,
                    verify_wait_seconds=cfg.verify_wait_seconds,
                    ip_filter=cfg.ip_filter,
                    require_ip=cfg.require_ip,
                ),
                client=client,
                parser_func=parser_func,
                state=state,
                writer=writer,
            )
            await scheduler.run()
    except RiskStopped as exc:
        logger.error("为降低账号风险，已主动停止：%s", exc)
        raise SystemExit(2)
    except BrowserConnectionError as exc:
        logger.error("%s", exc)
        raise SystemExit(1)

    outputs = writer.finalize()
    logger.info("任务完成：platform=%s outputs=%s", cfg.platform, ", ".join(outputs))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
