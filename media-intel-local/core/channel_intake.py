import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.intake_schema import build_intake_item, deduplicate_intake_items


SUPPORTED_CHANNELS = ["douyin", "xiaohongshu", "wechat"]


def build_channel_intake_items(
    normalized_items: List[Dict[str, Any]],
    captured_at: str = "",
) -> Dict[str, List[Dict[str, Any]]]:
    captured = captured_at or _shanghai_now_iso()
    by_type = {
        "platform_trend": [],
        "social_hotspot": [],
    }  # type: Dict[str, List[Dict[str, Any]]]

    candidates = [
        item
        for item in normalized_items
        if _platform_key(item) in SUPPORTED_CHANNELS
    ]
    ranked = _rank_by_platform(candidates)

    for item, rank, score in ranked:
        source_type = _intake_source_type(item)
        intake_item = _to_intake_item(item, source_type, rank, score, captured)
        by_type[source_type].append(intake_item)

    return {
        "platform_trend": deduplicate_intake_items(by_type["platform_trend"]),
        "social_hotspot": deduplicate_intake_items(by_type["social_hotspot"]),
    }


def write_channel_intake_outputs(
    normalized_items: List[Dict[str, Any]],
    output_dir: Path,
    target_date: str,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = target_date.replace("-", "")
    intake_items = build_channel_intake_items(normalized_items)
    platform_path = output_dir / "platform_trends_{}.jsonl".format(stamp)
    social_path = output_dir / "social_hotspots_{}.jsonl".format(stamp)
    log_path = output_dir / "channel_intake_run_log_{}.json".format(stamp)

    _write_jsonl(platform_path, intake_items["platform_trend"])
    _write_jsonl(social_path, intake_items["social_hotspot"])

    log = {
        "date": target_date,
        "source": "normalized_items",
        "platform_trends": len(intake_items["platform_trend"]),
        "social_hotspots": len(intake_items["social_hotspot"]),
        "outputs": {
            "platform_trends": str(platform_path),
            "social_hotspots": str(social_path),
            "run_log": str(log_path),
        },
    }
    _write_json(log_path, log)
    return log


def _to_intake_item(
    item: Dict[str, Any],
    source_type: str,
    rank: int,
    score: float,
    captured_at: str,
) -> Dict[str, Any]:
    platform = _platform_key(item)
    metrics = _metrics(item)
    extra = _extra(item, platform, source_type, score)
    heat_signals = _heat_signals(platform, metrics, rank)

    return build_intake_item(
        source_type=source_type,
        platform=platform,
        source_name=str(item.get("source_name") or ""),
        source_url=str(item.get("url") or ""),
        captured_at=captured_at,
        title=str(item.get("title") or ""),
        raw_text=str(item.get("content_text") or item.get("content_excerpt") or ""),
        tags=_tags(item),
        heat_signals=heat_signals,
        time_window={"started_at": None, "ends_at": None},
        raw_media=_raw_media(item),
        extra=extra,
        notes="由 {} 内容通道按本地规则派生；未做业务相关性判断。".format(platform),
    )


def _rank_by_platform(
    items: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], int, float]]:
    grouped = {}  # type: Dict[str, List[Tuple[Dict[str, Any], float]]]
    for item in items:
        platform = _platform_key(item)
        grouped.setdefault(platform, []).append((item, _heat_score(platform, _metrics(item))))

    ranked = []
    for platform in sorted(grouped.keys()):
        rows = sorted(grouped[platform], key=lambda row: row[1], reverse=True)
        for index, (item, score) in enumerate(rows, start=1):
            ranked.append((item, index, score))
    return ranked


def _heat_score(platform: str, metrics: Dict[str, Any]) -> float:
    if platform == "douyin":
        return (
            _num(metrics.get("like_count"))
            + _num(metrics.get("favorite_count")) * 2.0
            + _num(metrics.get("comment_count")) * 4.0
            + _num(metrics.get("share_count")) * 6.0
        )
    if platform == "xiaohongshu":
        return (
            _num(metrics.get("like_count"))
            + _num(metrics.get("favorite_count")) * 3.0
            + _num(metrics.get("comment_count")) * 5.0
        )
    if platform == "wechat":
        return _num(metrics.get("read_count")) * 0.2 + _num(metrics.get("like_count")) * 3.0
    return 0.0


def _heat_signals(platform: str, metrics: Dict[str, Any], rank: int) -> Dict[str, Any]:
    signals = {
        "rank": rank,
        "views": None,
        "likes": metrics.get("like_count"),
        "comments": metrics.get("comment_count"),
        "shares": metrics.get("share_count"),
        "search_index": None,
    }
    if platform == "wechat":
        signals["views"] = metrics.get("read_count")
        signals["comments"] = None
        signals["shares"] = None
    return signals


def _extra(
    item: Dict[str, Any],
    platform: str,
    source_type: str,
    score: float,
) -> Dict[str, Any]:
    if source_type == "platform_trend":
        return {
            "official_tags": _tags(item),
            "recommended_formats": [],
            "participation_rule": "",
            "traffic_hint": "",
            "deadline": "",
            "local_heat_score": score,
            "rank_method": _rank_method(platform),
        }
    return {
        "hotspot_rank": None,
        "hotspot_category": "unknown",
        "event_status": "unknown",
        "fact_confidence": "unknown",
        "sensitive_level": "unknown",
        "related_entities": [],
        "public_emotion": [],
        "local_heat_score": score,
        "rank_method": _rank_method(platform),
        "source_item_id": item.get("item_id") or "",
    }


def _rank_method(platform: str) -> str:
    if platform == "douyin":
        return "likes + favorites*2 + comments*4 + shares*6"
    if platform == "xiaohongshu":
        return "likes + favorites*3 + comments*5"
    if platform == "wechat":
        return "reads*0.2 + likes*3"
    return "unknown"


def _intake_source_type(item: Dict[str, Any]) -> str:
    text = "{} {} {}".format(
        item.get("source_name") or "",
        item.get("title") or "",
        item.get("content_text") or "",
    )
    platform_keywords = [
        "创作者中心",
        "创作灵感",
        "官方活动",
        "热门话题",
        "话题挑战",
        "内容挑战",
        "平台扶持",
    ]
    for keyword in platform_keywords:
        if keyword in text:
            return "platform_trend"
    return "social_hotspot"


def _platform_key(item: Dict[str, Any]) -> str:
    source_type = str(item.get("source_type") or "").lower()
    platform = str(item.get("platform") or "").lower()
    if source_type in ("douyin", "xiaohongshu", "wechat"):
        return source_type
    if "douyin" in platform or "抖音" in platform:
        return "douyin"
    if "xiao" in platform or "小红书" in platform:
        return "xiaohongshu"
    if "wechat" in platform or "微信" in platform:
        return "wechat"
    return source_type


def _metrics(item: Dict[str, Any]) -> Dict[str, Any]:
    metrics = item.get("metrics") or {}
    if isinstance(metrics, dict):
        return metrics
    return {}


def _tags(item: Dict[str, Any]) -> List[str]:
    tags = [str(tag).strip() for tag in list(item.get("tags") or []) if str(tag).strip()]
    text = "{} {}".format(item.get("title") or "", item.get("content_text") or "")
    for tag in re.findall(r"#([\w\u4e00-\u9fff-]+)", text):
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _raw_media(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_media = []
    media = item.get("media") or {}
    if not isinstance(media, dict):
        return raw_media
    for image in media.get("images") or []:
        if isinstance(image, str):
            raw_media.append({"type": "image", "url": image, "caption": ""})
        elif isinstance(image, dict):
            raw_media.append(
                {
                    "type": "image",
                    "url": str(image.get("url") or image.get("src") or ""),
                    "caption": str(image.get("caption") or ""),
                }
            )
    for video in media.get("videos") or []:
        if isinstance(video, dict):
            raw_media.append(
                {
                    "type": "video",
                    "url": str(
                        video.get("url")
                        or video.get("video_download_url")
                        or video.get("cover_url")
                        or ""
                    ),
                    "caption": str(video.get("aweme_id") or ""),
                }
            )
    return raw_media


def _num(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        for item in items:
            json.dump(item, file_obj, ensure_ascii=False, separators=(",", ":"))
            file_obj.write("\n")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")


def _shanghai_now_iso() -> str:
    china_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
    return datetime.now(china_timezone).isoformat(timespec="seconds")
