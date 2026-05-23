from typing import Any, Dict

from core.content_cleaner import clean_website_content
from core.schema import build_normalized_item


def adapt(raw_item: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    content_text, images = clean_website_content(
        raw_item.get("markdown", ""),
        raw_item=raw_item,
        source=source,
    )
    return build_normalized_item(
        source_type="website",
        source_id=source["id"],
        source_name=source["name"],
        platform="网站",
        title=raw_item.get("headline", ""),
        url=raw_item.get("link", ""),
        publish_time=raw_item.get("date", ""),
        content_text=content_text,
        media={
            "images": images,
            "videos": [],
        },
        raw=raw_item,
    )
