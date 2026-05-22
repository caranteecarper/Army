import hashlib
from datetime import date, datetime
from typing import Any, Dict, List, Optional


METRIC_FIELDS = [
    "read_count",
    "like_count",
    "favorite_count",
    "comment_count",
    "share_count",
]


def make_item_id(source_id: str, url: str, title: str) -> str:
    """
    用 source_id + url 或 title 生成稳定 hash。
    """
    locator = url or title or ""
    digest = hashlib.sha256("{}|{}".format(source_id or "", locator).encode("utf-8"))
    return "item_{}".format(digest.hexdigest()[:24])


def make_excerpt(text: str, max_len: int = 260) -> str:
    """
    用代码截断文本，生成 content_excerpt。
    不调用 AI。
    """
    if not text or max_len <= 0:
        return ""
    return str(text)[:max_len].strip()


def _to_iso_string(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""

    if len(text) == 10:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        pass

    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return text


def _build_metrics(metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    provided = metrics or {}
    return {field: provided.get(field) for field in METRIC_FIELDS}


def _build_media(media: Optional[Dict[str, Any]]) -> Dict[str, List[Any]]:
    provided = media or {}
    return {
        "images": list(provided.get("images") or []),
        "videos": list(provided.get("videos") or []),
    }


def build_normalized_item(
    source_type: str,
    source_id: str,
    source_name: str,
    platform: str,
    title: str,
    url: str,
    publish_time: str,
    content_text: str,
    metrics: Optional[Dict[str, Any]] = None,
    media: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    生成统一 schema item。
    """
    item_title = "" if title is None else str(title)
    item_url = "" if url is None else str(url)
    item_content = "" if content_text is None else str(content_text)
    return {
        "item_id": make_item_id(source_id, item_url, item_title),
        "source_type": source_type,
        "source_id": source_id,
        "source_name": source_name,
        "platform": platform,
        "title": item_title,
        "url": item_url,
        "publish_time": _to_iso_string(publish_time),
        "crawl_time": datetime.now().isoformat(timespec="seconds"),
        "content_text": item_content,
        "content_excerpt": make_excerpt(item_content),
        "metrics": _build_metrics(metrics),
        "media": _build_media(media),
        "tags": list(tags or []),
        "raw": dict(raw or {}),
    }
