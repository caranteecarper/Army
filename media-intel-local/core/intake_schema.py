import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


INTAKE_SOURCE_TYPES = ["platform_trend", "social_hotspot"]

HEAT_SIGNAL_FIELDS = [
    "rank",
    "views",
    "likes",
    "comments",
    "shares",
    "search_index",
]

TIME_WINDOW_FIELDS = ["started_at", "ends_at"]

DEFAULT_PLATFORM_EXTRA = {
    "official_tags": [],
    "recommended_formats": [],
    "participation_rule": "",
    "traffic_hint": "",
    "deadline": "",
}

DEFAULT_SOCIAL_EXTRA = {
    "hotspot_rank": None,
    "hotspot_category": "unknown",
    "event_status": "unknown",
    "fact_confidence": "unknown",
    "sensitive_level": "unknown",
    "related_entities": [],
    "public_emotion": [],
}


def shanghai_now_iso() -> str:
    china_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
    return datetime.now(china_timezone).isoformat(timespec="seconds")


def make_intake_id(item: Dict[str, Any]) -> str:
    locator = "{}|{}|{}|{}".format(
        item.get("source_type") or "",
        item.get("platform") or "",
        item.get("source_url") or "",
        item.get("title") or "",
    )
    digest = hashlib.sha256(locator.encode("utf-8")).hexdigest()[:24]
    return "intake_{}".format(digest)


def build_intake_item(
    source_type: str,
    platform: str,
    source_name: str,
    source_url: str,
    title: str,
    raw_text: str,
    captured_at: Optional[str] = None,
    tags: Optional[List[Any]] = None,
    heat_signals: Optional[Dict[str, Any]] = None,
    time_window: Optional[Dict[str, Any]] = None,
    raw_media: Optional[List[Dict[str, Any]]] = None,
    extra: Optional[Dict[str, Any]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    if source_type not in INTAKE_SOURCE_TYPES:
        raise ValueError("unsupported intake source_type {}".format(source_type))

    item = {
        "item_id": "",
        "source_type": source_type,
        "platform": _clean_text(platform),
        "source_name": _clean_text(source_name),
        "source_url": _clean_text(source_url),
        "captured_at": captured_at or shanghai_now_iso(),
        "title": _clean_text(title),
        "raw_text": _clean_text(raw_text),
        "tags": [_clean_text(tag) for tag in list(tags or []) if _clean_text(tag)],
        "heat_signals": _build_heat_signals(heat_signals),
        "time_window": _build_time_window(time_window),
        "raw_media": _build_raw_media(raw_media),
        "extra": _build_extra(source_type, extra),
        "notes": _clean_text(notes),
    }
    item["item_id"] = make_intake_id(item)
    return item


def normalize_intake_item(raw_item: Dict[str, Any]) -> Dict[str, Any]:
    item = build_intake_item(
        source_type=str(raw_item.get("source_type") or ""),
        platform=str(raw_item.get("platform") or ""),
        source_name=str(raw_item.get("source_name") or ""),
        source_url=str(raw_item.get("source_url") or ""),
        captured_at=str(raw_item.get("captured_at") or "") or None,
        title=str(raw_item.get("title") or ""),
        raw_text=str(raw_item.get("raw_text") or raw_item.get("text") or ""),
        tags=list(raw_item.get("tags") or []),
        heat_signals=_as_dict(raw_item.get("heat_signals")),
        time_window=_as_dict(raw_item.get("time_window")),
        raw_media=_as_list_of_dicts(raw_item.get("raw_media")),
        extra=_as_dict(raw_item.get("extra")),
        notes=str(raw_item.get("notes") or ""),
    )
    if raw_item.get("exclude") is True:
        item["exclude"] = True
        item["exclude_reason"] = str(raw_item.get("exclude_reason") or "")
    return item


def should_keep_intake_item(item: Dict[str, Any]) -> Tuple[bool, str]:
    title = str(item.get("title") or "").strip()
    raw_text = str(item.get("raw_text") or "").strip()
    if not title and not raw_text:
        return False, "missing_title_and_raw_text"

    if item.get("exclude") is True:
        return False, str(item.get("exclude_reason") or "manually_excluded")

    text = "{} {}".format(title, raw_text)
    if _looks_like_machine_garbage(text):
        return False, "machine_garbage"
    return True, ""


def deduplicate_intake_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduplicated = []
    seen = set()
    for item in items:
        key = "{}|{}|{}|{}".format(
            item.get("source_type") or "",
            item.get("platform") or "",
            item.get("source_url") or "",
            item.get("title") or "",
        )
        if not item.get("source_url"):
            key = "{}|{}|{}".format(
                item.get("source_type") or "",
                item.get("platform") or "",
                item.get("title") or item.get("raw_text") or "",
            )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)
    return deduplicated


def _build_heat_signals(heat_signals: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    provided = heat_signals or {}
    return {field: provided.get(field) for field in HEAT_SIGNAL_FIELDS}


def _build_time_window(time_window: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    provided = time_window or {}
    return {field: provided.get(field) for field in TIME_WINDOW_FIELDS}


def _build_raw_media(raw_media: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    media = []
    for item in raw_media or []:
        if not isinstance(item, dict):
            continue
        media.append(
            {
                "type": _clean_text(item.get("type") or ""),
                "url": _clean_text(item.get("url") or ""),
                "caption": _clean_text(item.get("caption") or ""),
            }
        )
    return media


def _build_extra(source_type: str, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if source_type == "platform_trend":
        built = dict(DEFAULT_PLATFORM_EXTRA)
    else:
        built = dict(DEFAULT_SOCIAL_EXTRA)
    built.update(extra or {})
    return built


def _clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text).strip()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _looks_like_machine_garbage(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 20:
        return False
    visible = re.sub(r"\s+", "", stripped)
    if not visible:
        return True
    punctuation = re.findall(r"[^0-9A-Za-z\u4e00-\u9fff]", visible)
    return float(len(punctuation)) / float(len(visible)) > 0.65
