from typing import Any, Dict

from core.schema import build_normalized_item


def adapt(raw_item: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    return build_normalized_item(
        source_type="xiaohongshu",
        source_id=source["id"],
        source_name=source["name"],
        platform="小红书",
        title=raw_item.get("note_title", ""),
        url=raw_item.get("note_url", ""),
        publish_time=raw_item.get("time", ""),
        content_text=raw_item.get("desc", ""),
        metrics={
            "like_count": raw_item.get("likes"),
            "favorite_count": raw_item.get("favorites"),
            "comment_count": raw_item.get("comments"),
        },
        media={
            "images": raw_item.get("images", []),
            "videos": [],
        },
        raw=raw_item,
    )
