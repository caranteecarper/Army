import re
from typing import Any, Dict

from core.schema import make_excerpt


def normalize_text(text: Any) -> str:
    """
    基础文本清洗。
    """
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单个统一 schema item 做基础清洗。
    """
    normalized = dict(item)
    normalized["title"] = normalize_text(normalized.get("title")) or "无标题"
    normalized["content_text"] = normalize_text(normalized.get("content_text"))
    normalized["content_excerpt"] = make_excerpt(normalized["content_text"])
    normalized["url"] = normalize_text(normalized.get("url"))
    return normalized
