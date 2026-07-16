from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dykw.utils.time_util import parse_yyyy_mm_dd


@dataclass(frozen=True)
class AppConfig:
    platform: str
    keywords: List[str]
    keywords_file: Optional[str]
    locations: List[str]
    location_mode: str
    location_sep: str
    start_date: Optional[str]
    end_date: Optional[str]
    proxy: Optional[str]
    proxy_list: Optional[str]
    out_format: str
    out_path: str
    state_db_path: str
    browser_channel: str
    cdp_url: str
    min_sleep: float
    max_sleep: float
    max_pages: int
    max_items: int
    max_empty_pages: int
    max_responses: int
    max_seen_items: int
    risk_stop_count: int
    manual_verify: bool
    verify_retries: int
    verify_wait_seconds: float
    no_resume: bool
    reset_state: bool
    diagnose: bool
    log_level: str
    ip_filter: Optional[str]
    require_ip: bool


def _sanitize_filename_part(s: str) -> str:
    bad = '<>:"/\\|?*'
    for ch in bad:
        s = s.replace(ch, "_")
    s = s.strip()
    return s[:80] if len(s) > 80 else s


def _to_yymm(date_str: Optional[str]) -> str:
    if not date_str:
        return ""
    try:
        y, m, _d = date_str.split("-", 2)
        return f"{y[-2:]}{m}"
    except Exception:
        return ""


def _build_default_out_base_name(
    *,
    platform: str,
    keywords: List[str],
    locations: List[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> str:
    top_keywords = [k for k in keywords if k.strip()][:2]
    kw_part = "-".join(_sanitize_filename_part(k) for k in top_keywords) or "keywords"
    loc_part = "-".join(_sanitize_filename_part(x) for x in locations if x.strip())
    date_part = "-".join(x for x in [_to_yymm(start_date), _to_yymm(end_date)] if x)
    base = f"{loc_part}+{kw_part}" if loc_part else kw_part
    if date_part:
        base = f"{base}-{date_part}"
    return f"{platform}-{base}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="抖音/快手关键词采集工具（Chrome/Edge CDP 登录态复用）")
    p.add_argument("--platform", default="douyin", choices=["douyin", "kuaishou"], help="目标平台")
    p.add_argument("--keywords", default="", help="关键词列表，英文逗号分隔")
    p.add_argument("--keywords-file", default="", help="关键词文件路径，每行一个关键词")
    p.add_argument("--locations", default="", help="地点列表，英文逗号分隔")
    p.add_argument(
        "--location-mode",
        default="prepend",
        choices=["none", "prepend", "append"],
        help="地点与关键词拼接方式",
    )
    p.add_argument("--location-sep", default="", help="地点与关键词之间的分隔符，默认空字符串")
    p.add_argument("--start-date", default="2015-01-01", help="开始日期，格式 YYYY-MM-DD")
    p.add_argument("--end-date", default="2026-06-30", help="结束日期，格式 YYYY-MM-DD")
    p.add_argument("--proxy", default="", help="可选稳定代理地址，如 http://127.0.0.1:7890")
    p.add_argument("--proxy-list", default="", help="可选代理列表；仅取第一条有效代理作为稳定出口")
    p.add_argument("--out-format", default="csv", choices=["csv", "xlsx", "both"], help="输出格式")
    p.add_argument("--out", default="", help="输出文件路径；both 模式可填 .csv 或 .xlsx，程序会生成另一份")
    p.add_argument("--state-db", default="", help="断点状态 SQLite 文件路径，默认 data/state.sqlite3")
    p.add_argument("--browser-channel", default="chrome", choices=["chrome", "msedge"], help="浏览器类型")
    p.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome/Edge 远程调试 CDP 地址")
    p.add_argument("--min-sleep", type=float, default=4, help="随机延迟最小秒数")
    p.add_argument("--max-sleep", type=float, default=10, help="随机延迟最大秒数")
    p.add_argument("--max-pages", type=int, default=15, help="每个关键词最多滚动页数")
    p.add_argument("--max-items", type=int, default=300, help="每个关键词最多保存条数")
    p.add_argument("--max-empty-pages", type=int, default=2, help="连续空页达到该值时停止当前关键词")
    p.add_argument("--max-responses", type=int, default=120, help="每个关键词最多处理的平台响应数")
    p.add_argument("--max-seen-items", type=int, default=50, help="当前关键词连续遇到多少条已 seen 作品后提前停止")
    p.add_argument("--risk-stop-count", type=int, default=1, help="命中风控信号次数达到该值时立即停机")
    p.add_argument("--no-manual-verify", action="store_true", help="检测到验证/登录风险时不等待人工处理，直接跳过")
    p.add_argument("--verify-retries", type=int, default=3, help="当前关键词最多人工验证次数")
    p.add_argument("--verify-wait-seconds", type=float, default=45, help="每次人工验证提示后至少等待秒数，低于 45 会按 45 处理")
    p.add_argument("--no-resume", action="store_true", help="忽略历史断点和 seen 去重，用于排查")
    p.add_argument("--reset-state", action="store_true", help="运行前清空当前平台与关键词的断点和 seen 状态")
    p.add_argument("--diagnose", action="store_true", help="只打印本地配置诊断，不连接平台")
    p.add_argument("--log-level", default="INFO", help="日志级别，如 DEBUG/INFO/WARNING/ERROR")
    p.add_argument("--ip-filter", default="", help="按 ip_location 字段做包含过滤，空值表示不过滤")
    p.add_argument("--require-ip", action="store_true", help="仅保存含有 ip_location 的记录")
    return p


def _load_keywords(args: argparse.Namespace) -> List[str]:
    keywords = [k.strip() for k in str(args.keywords).split(",") if k.strip()]
    keywords_file = str(args.keywords_file).strip()
    if keywords_file:
        fp = Path(keywords_file)
        if not fp.exists():
            raise SystemExit(f"关键词文件不存在：{keywords_file}")
        keywords.extend([line.strip() for line in fp.read_text(encoding="utf-8").splitlines() if line.strip()])

    dedup_keywords: List[str] = []
    seen = set()
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            dedup_keywords.append(kw)
    return dedup_keywords


def parse_args(argv: Optional[List[str]] = None) -> AppConfig:
    p = build_parser()
    args = p.parse_args(argv)

    keywords = _load_keywords(args)
    if not keywords:
        raise SystemExit("必须提供 --keywords 或 --keywords-file")

    locations = [x.strip() for x in str(args.locations).split(",") if x.strip()]
    start = parse_yyyy_mm_dd(args.start_date) if args.start_date else None
    end = parse_yyyy_mm_dd(args.end_date) if args.end_date else None
    if start and end and start > end:
        raise SystemExit("start-date 不能晚于 end-date")

    proxy_list = args.proxy_list.strip() or None
    if proxy_list and not Path(proxy_list).exists():
        raise SystemExit(f"代理列表文件不存在：{proxy_list}")

    out_format = str(args.out_format)
    default_base_name = _build_default_out_base_name(
        platform=str(args.platform),
        keywords=keywords,
        locations=locations,
        start_date=args.start_date.strip() or None,
        end_date=args.end_date.strip() or None,
    )
    default_suffix = ".csv" if out_format in {"csv", "both"} else ".xlsx"
    default_out = str(Path("output") / f"{default_base_name}{default_suffix}")

    return AppConfig(
        platform=str(args.platform),
        keywords=keywords,
        keywords_file=args.keywords_file.strip() or None,
        locations=locations,
        location_mode=str(args.location_mode),
        location_sep=str(args.location_sep),
        start_date=args.start_date.strip() or None,
        end_date=args.end_date.strip() or None,
        proxy=args.proxy.strip() or None,
        proxy_list=proxy_list,
        out_format=out_format,
        out_path=args.out.strip() or default_out,
        state_db_path=args.state_db.strip() or str(Path("data") / "state.sqlite3"),
        browser_channel=str(args.browser_channel),
        cdp_url=str(args.cdp_url).strip(),
        min_sleep=max(0.0, float(args.min_sleep)),
        max_sleep=max(0.0, float(args.max_sleep)),
        max_pages=max(1, int(args.max_pages)),
        max_items=max(1, int(args.max_items)),
        max_empty_pages=max(1, int(args.max_empty_pages)),
        max_responses=max(1, int(args.max_responses)),
        max_seen_items=max(1, int(args.max_seen_items)),
        risk_stop_count=max(1, int(args.risk_stop_count)),
        manual_verify=not bool(args.no_manual_verify),
        verify_retries=max(0, int(args.verify_retries)),
        verify_wait_seconds=max(45.0, float(args.verify_wait_seconds)),
        no_resume=bool(args.no_resume),
        reset_state=bool(args.reset_state),
        diagnose=bool(args.diagnose),
        log_level=str(args.log_level),
        ip_filter=args.ip_filter.strip() or None,
        require_ip=bool(args.require_ip),
    )
