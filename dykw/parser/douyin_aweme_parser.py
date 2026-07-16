from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import unquote

from dykw.parser.common import ParsedPost
from dykw.utils.time_util import ts_to_local_datetime_str


COMMON_LOCATION_NAMES = (
    "北京",
    "上海",
    "天津",
    "重庆",
    "广州",
    "深圳",
    "武汉",
    "杭州",
    "南京",
    "成都",
    "西安",
    "郑州",
    "长沙",
    "南昌",
    "合肥",
    "福州",
    "厦门",
    "济南",
    "青岛",
    "沈阳",
    "大连",
    "长春",
    "哈尔滨",
    "石家庄",
    "太原",
    "呼和浩特",
    "兰州",
    "银川",
    "西宁",
    "乌鲁木齐",
    "拉萨",
    "昆明",
    "贵阳",
    "南宁",
    "海口",
    "三亚",
    "宁波",
    "温州",
    "苏州",
    "无锡",
    "常州",
    "佛山",
    "东莞",
    "珠海",
    "中山",
    "惠州",
    "泉州",
    "襄阳",
    "宜昌",
    "荆州",
    "黄石",
    "孝感",
)


def _safe_get(d: Any, *path: str, default: Any = "") -> Any:
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _join_unique_texts(values: List[Any]) -> str:
    out: List[str] = []
    seen = set()
    for value in values:
        text = _clean_text(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return " / ".join(out)


def _json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _pick_poi_fields(poi: Any) -> tuple[str, str]:
    if not isinstance(poi, dict):
        return "", ""
    name = _clean_text(poi.get("poi_name") or poi.get("name") or poi.get("title"))
    address = _clean_text(poi.get("poi_address") or poi.get("address"))
    address_info = poi.get("address_info") or {}
    if isinstance(address_info, dict):
        address = _clean_text(
            address_info.get("simple_addr")
            or address_info.get("address")
            or _join_unique_texts(
                [address_info.get("province"), address_info.get("city"), address_info.get("district")]
            )
        ) or address
    return name, address


def _coordinate_pair(poi: Any) -> tuple[str, str]:
    if not isinstance(poi, dict):
        return "", ""
    lng = _clean_text(poi.get("poi_longitude") or poi.get("longitude") or poi.get("lng"))
    lat = _clean_text(poi.get("poi_latitude") or poi.get("latitude") or poi.get("lat"))
    return lng, lat


def _extract_anchor_location(aweme_info: Dict[str, Any]) -> tuple[str, str, str, str]:
    poi_name = ""
    poi_address = ""
    lng = ""
    lat = ""
    anchor_objs: List[Any] = [aweme_info.get("anchor_info")]
    anchors = aweme_info.get("anchors") or []
    if isinstance(anchors, list):
        anchor_objs.extend(anchors)

    for anchor in anchor_objs:
        if not isinstance(anchor, dict):
            continue
        if not poi_name or not poi_address:
            name, address = _pick_poi_fields(anchor)
            poi_name = poi_name or name
            poi_address = poi_address or address
        if not lng or not lat:
            lng, lat = _coordinate_pair(anchor)
        for parsed in [_json_dict(anchor.get("extra")), _json_dict(anchor.get("content"))]:
            if not poi_name or not poi_address:
                name, address = _pick_poi_fields(parsed)
                poi_name = poi_name or name
                poi_address = poi_address or address
            if not lng or not lat:
                lng, lat = _coordinate_pair(parsed)

    return poi_name, poi_address, lng, lat


def _extract_location_fields(aweme_info: Dict[str, Any]) -> tuple[str, str, str, str]:
    poi_name = ""
    poi_address = ""
    lng = ""
    lat = ""
    poi = aweme_info.get("poi_info") or aweme_info.get("poi") or {}
    poi_name, poi_address = _pick_poi_fields(poi)
    lng, lat = _coordinate_pair(poi)
    poi_name = poi_name or _clean_text(aweme_info.get("poi_name"))
    poi_address = poi_address or _clean_text(
        aweme_info.get("poi_address") or aweme_info.get("address") or aweme_info.get("location")
    )

    geofencing = aweme_info.get("geofencing") or []
    if isinstance(geofencing, list):
        for item in geofencing:
            if isinstance(item, dict):
                poi_name = poi_name or _clean_text(item.get("name"))
                poi_address = poi_address or _join_unique_texts([item.get("province"), item.get("city")])
            else:
                poi_name = poi_name or _clean_text(item)

    anchor_poi_name, anchor_poi_address, anchor_lng, anchor_lat = _extract_anchor_location(aweme_info)
    poi_name = poi_name or anchor_poi_name
    poi_address = poi_address or anchor_poi_address
    if not lng or not lat:
        lng, lat = anchor_lng, anchor_lat
    return poi_name, poi_address, lng, lat


def _infer_location_from_visible_text(*texts: str) -> str:
    joined = unquote(" ".join(t for t in texts if t)).replace("\n", " ")
    for name in COMMON_LOCATION_NAMES:
        if name in joined:
            return name
    m = re.search(r"#?([\u4e00-\u9fa5]{2,6})(?:暴雨|大雨|内涝|积水|看海|水淹|被淹|洪水|划船)", joined)
    return m.group(1) if m else ""


def _has_images(aweme_info: Dict[str, Any]) -> bool:
    images = aweme_info.get("images") or aweme_info.get("image_infos") or []
    return isinstance(images, list) and len(images) > 0


def _has_video(aweme_info: Dict[str, Any]) -> bool:
    video = aweme_info.get("video") or {}
    if not isinstance(video, dict) or not video:
        return False
    play_addr = _safe_get(video, "play_addr", default={})
    url_list = play_addr.get("url_list") if isinstance(play_addr, dict) else []
    if isinstance(url_list, list) and url_list:
        return True
    if video.get("duration") or video.get("bit_rate"):
        return True
    return False


def _media_type(aweme_info: Dict[str, Any]) -> str:
    has_images = _has_images(aweme_info)
    has_video = _has_video(aweme_info)
    if has_images and has_video:
        return "mixed"
    if has_images:
        return "images"
    if has_video:
        return "video"
    return "unknown"


def parse_aweme_info(aweme_info: Dict[str, Any], keyword: str) -> ParsedPost:
    aweme_id = str(aweme_info.get("aweme_id") or "")

    author = aweme_info.get("author") or {}
    user_id = str(author.get("uid") or author.get("sec_uid") or author.get("sec_user_id") or "")
    username = str(author.get("nickname") or "")

    ip_location = ""
    ip_attr = aweme_info.get("ip_attribution")
    if isinstance(ip_attr, str):
        ip_location = ip_attr
    elif isinstance(ip_attr, dict):
        ip_location = str(ip_attr.get("ip_location") or ip_attr.get("ip_region") or "")
    if not ip_location:
        ip_location = str(aweme_info.get("ip_location") or "")

    publish_ts = aweme_info.get("create_time") or aweme_info.get("publish_time")
    if isinstance(publish_ts, str) and publish_ts.isdigit():
        publish_ts = int(publish_ts)
    publish_time = ts_to_local_datetime_str(publish_ts if isinstance(publish_ts, int) else None)

    content_text = str(aweme_info.get("desc") or aweme_info.get("content") or "")
    poi_name, poi_address, location_lng, location_lat = _extract_location_fields(aweme_info)
    inferred_location = _infer_location_from_visible_text(content_text, keyword)
    post_url = f"https://www.douyin.com/video/{aweme_id}" if aweme_id else ""
    media_type = _media_type(aweme_info)

    stat = aweme_info.get("statistics") or aweme_info.get("stats") or {}
    like_count = str(_safe_get(stat, "digg_count", default=_safe_get(stat, "like_count", default="")) or "")
    comment_count = str(_safe_get(stat, "comment_count", default="") or "")

    return ParsedPost(
        user_id=user_id,
        username=username,
        ip_location=ip_location,
        poi_name=poi_name,
        poi_address=poi_address,
        location_lng=location_lng,
        location_lat=location_lat,
        inferred_location=inferred_location,
        publish_time=publish_time,
        content_text=content_text,
        post_url=post_url,
        media_type=media_type,
        like_count=like_count,
        comment_count=comment_count,
        keyword=keyword,
        aweme_id=aweme_id,
    )
