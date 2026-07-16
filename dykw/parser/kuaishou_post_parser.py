from __future__ import annotations

from typing import Any, Dict

from dykw.parser.common import ParsedPost
from dykw.utils.time_util import ts_to_local_datetime_str


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _extract_poi_fields(feed: Dict[str, Any]) -> tuple[str, str]:
    photo = feed.get("photo") or {}
    for obj in [photo.get("poi"), photo.get("poiInfo"), feed.get("poi"), feed.get("poiInfo")]:
        if not isinstance(obj, dict):
            continue
        name = _clean_text(obj.get("name") or obj.get("title") or obj.get("poi_name"))
        address = _clean_text(obj.get("address") or obj.get("poi_address"))
        if name or address:
            return name, address
    return "", ""


def _extract_location_coordinates(feed: Dict[str, Any]) -> tuple[str, str]:
    photo = feed.get("photo") or {}
    for obj in [photo, feed, photo.get("poi"), photo.get("poiInfo"), feed.get("poi"), feed.get("poiInfo")]:
        if not isinstance(obj, dict):
            continue
        lng = _clean_text(obj.get("longitude") or obj.get("lng") or obj.get("poi_longitude"))
        lat = _clean_text(obj.get("latitude") or obj.get("lat") or obj.get("poi_latitude"))
        if lng or lat:
            return lng, lat
    return "", ""


def _media_type(photo: Dict[str, Any]) -> str:
    if str(photo.get("photoUrl") or "").strip():
        return "video"
    cover_urls = photo.get("coverUrls") or []
    if isinstance(cover_urls, list) and cover_urls:
        return "images"
    if str(photo.get("coverUrl") or "").strip():
        return "images"
    return "unknown"


def parse_kuaishou_feed(feed: Dict[str, Any], keyword: str) -> ParsedPost:
    photo = feed.get("photo") or {}
    author = feed.get("author") or {}

    photo_id = str(photo.get("id") or "")
    caption = str(photo.get("caption") or photo.get("originCaption") or "")
    publish_time = ts_to_local_datetime_str(photo.get("timestamp") if isinstance(photo.get("timestamp"), int) else None)
    post_url = f"https://www.kuaishou.com/short-video/{photo_id}" if photo_id else ""
    poi_name, poi_address = _extract_poi_fields(feed)
    location_lng, location_lat = _extract_location_coordinates(feed)
    media_type = _media_type(photo)

    return ParsedPost(
        user_id=str(author.get("id") or ""),
        username=str(author.get("name") or ""),
        ip_location="",
        poi_name=poi_name,
        poi_address=poi_address,
        location_lng=location_lng,
        location_lat=location_lat,
        inferred_location="",
        publish_time=publish_time,
        content_text=caption,
        post_url=post_url,
        media_type=media_type,
        like_count=str(photo.get("realLikeCount") or photo.get("likeCount") or ""),
        comment_count=str(photo.get("commentCount") or ""),
        keyword=keyword,
        aweme_id=photo_id,
    )
