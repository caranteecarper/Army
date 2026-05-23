from typing import Any, Dict, List

from core.schema import build_normalized_item


def adapt(raw_item: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    media = raw_item.get("media") or {}
    if not isinstance(media, dict):
        media = {}

    desc = str(raw_item.get("desc") or "")
    content_text = _merge_video_text(desc, raw_item)
    video = {
        "aweme_id": raw_item.get("aweme_id") or "",
        "url": raw_item.get("url") or "",
        "cover_url": media.get("cover_url") or "",
        "video_download_url": media.get("video_download_url") or "",
        "music_download_url": media.get("music_download_url") or "",
        "asr_text": raw_item.get("asr_text") or "",
        "ocr_text": raw_item.get("ocr_text") or "",
    }

    metrics = raw_item.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    return build_normalized_item(
        source_type="douyin",
        source_id=source["id"],
        source_name=source["name"],
        platform="抖音",
        title=raw_item.get("title", ""),
        url=raw_item.get("url", ""),
        publish_time=raw_item.get("publish_time", ""),
        content_text=content_text,
        metrics={
            "like_count": metrics.get("like_count"),
            "favorite_count": metrics.get("favorite_count"),
            "comment_count": metrics.get("comment_count"),
            "share_count": metrics.get("share_count"),
        },
        media={
            "images": media.get("note_image_urls") or [],
            "videos": [video],
        },
        tags=_tags(raw_item),
        raw=raw_item,
    )


def _merge_video_text(desc: str, raw_item: Dict[str, Any]) -> str:
    parts = []
    if desc.strip():
        parts.append(desc.strip())
    asr_text = str(raw_item.get("asr_text") or "").strip()
    if asr_text:
        parts.append("ASR: {}".format(asr_text))
    ocr_text = str(raw_item.get("ocr_text") or "").strip()
    if ocr_text:
        parts.append("OCR: {}".format(ocr_text))
    return "\n\n".join(parts)


def _tags(raw_item: Dict[str, Any]) -> List[str]:
    tags = []
    keyword = str(raw_item.get("source_keyword") or "").strip()
    if keyword:
        tags.append(keyword)
    return tags
