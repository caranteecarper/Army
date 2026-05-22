from typing import Any, Dict

from core.schema import build_normalized_item


def adapt(raw_item: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    return build_normalized_item(
        source_type="wechat",
        source_id=source["id"],
        source_name=source["name"],
        platform="微信公众号",
        title=raw_item.get("title", ""),
        url=raw_item.get("url", ""),
        publish_time=raw_item.get("published_at", ""),
        content_text=raw_item.get("content", ""),
        metrics={
            "read_count": raw_item.get("read_count"),
            "like_count": raw_item.get("like_count"),
        },
        raw=raw_item,
    )
