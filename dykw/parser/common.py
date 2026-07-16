from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict


@dataclass(frozen=True)
class ParsedPost:
    user_id: str
    username: str
    ip_location: str
    poi_name: str
    poi_address: str
    location_lng: str
    location_lat: str
    inferred_location: str
    publish_time: str
    content_text: str
    post_url: str
    media_type: str
    like_count: str
    comment_count: str
    keyword: str
    aweme_id: str

    def to_row(self) -> Dict[str, str]:
        d = asdict(self)
        return {
            "user_id": d["user_id"],
            "username": d["username"],
            "ip_location": d["ip_location"],
            "poi_name": d["poi_name"],
            "poi_address": d["poi_address"],
            "location_lng": d["location_lng"],
            "location_lat": d["location_lat"],
            "inferred_location": d["inferred_location"],
            "publish_time": d["publish_time"],
            "content_text": d["content_text"],
            "post_url": d["post_url"],
            "media_type": d["media_type"],
            "like_count": d["like_count"],
            "comment_count": d["comment_count"],
        }
