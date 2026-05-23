from datetime import datetime
from typing import Any, Dict, List

from crawlers.base import BaseCrawler
from crawlers.external import python_command, run_json_command


class DouyinCrawler(BaseCrawler):
    source_type = "douyin"

    def fetch(self, source: Dict[str, Any], target_date: str) -> List[Dict[str, Any]]:
        if self._is_mock_source(source):
            items = self._read_mock_items(source)
            return self._filter_by_date(items, "publish_time", target_date)

        results = self._crawl_with_mediacrawler(source)
        items = [self._to_raw_item(item, source) for item in results]
        return self._filter_by_date(items, "publish_time", target_date)

    def _crawl_with_mediacrawler(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        tool_dir = source.get("mediacrawler_dir")
        if not tool_dir:
            raise ValueError("douyin source {} is missing mediacrawler_dir".format(source.get("id", "")))

        bridge = self.project_root / "tools" / "douyin_mediacrawler_bridge.py"
        command = python_command(source.get("douyin_python"), self.project_root)
        command.append(str(bridge))
        payload = {
            "tool_dir": str(tool_dir),
            "save_path": str(
                self.project_root
                / ".runtime"
                / "douyin"
                / "mediacrawler-output"
                / str(source.get("id") or "source")
                / datetime.now().strftime("%Y%m%dT%H%M%S")
            ),
            "mode": source.get("mode") or "keyword_search",
            "keyword": source.get("keyword") or "",
            "specified_ids": source.get("specified_ids")
            or source.get("video_urls")
            or source.get("aweme_ids")
            or [],
            "creator_ids": source.get("creator_ids") or source.get("user_ids") or [],
            "limit": int(source.get("limit") or 10),
            "publish_time": source.get("publish_time") or "one_day",
            "login_type": source.get("login_type") or "qrcode",
            "cookies": source.get("cookies") or "",
            "headless": bool(source.get("headless", False)),
            "enable_cdp": bool(source.get("enable_cdp", True)),
            "cdp_connect_existing": bool(source.get("cdp_connect_existing", False)),
            "auto_close_browser": bool(source.get("auto_close_browser", True)),
            "fetch_comments": bool(source.get("fetch_comments", False)),
            "fetch_sub_comments": bool(source.get("fetch_sub_comments", False)),
            "max_comments_per_video": int(source.get("max_comments_per_video") or 10),
            "download_video": bool(source.get("download_video", False)),
            "max_concurrency": int(source.get("max_concurrency") or 1),
        }
        results = run_json_command(
            command,
            payload=payload,
            timeout_seconds=int(source.get("crawl_timeout_seconds") or 600),
        )
        if not isinstance(results, list):
            raise ValueError("Douyin MediaCrawler bridge must return a JSON list")
        return [item for item in results if isinstance(item, dict)]

    def _to_raw_item(self, item: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
        create_time = item.get("create_time")
        publish_time = self._normalized_datetime(create_time)
        aweme_id = str(item.get("aweme_id") or "")
        url = str(item.get("aweme_url") or "")
        if not url and aweme_id:
            url = "https://www.douyin.com/video/{}".format(aweme_id)

        return {
            "aweme_id": aweme_id,
            "title": item.get("title") or item.get("desc") or "",
            "desc": item.get("desc") or item.get("title") or "",
            "url": url,
            "publish_time": publish_time,
            "create_time": create_time,
            "author": {
                "user_id": item.get("user_id"),
                "sec_uid": item.get("sec_uid"),
                "short_user_id": item.get("short_user_id"),
                "unique_id": item.get("user_unique_id"),
                "nickname": item.get("nickname"),
                "avatar": item.get("avatar"),
                "signature": item.get("user_signature"),
            },
            "metrics": {
                "like_count": self._to_int(item.get("liked_count")),
                "favorite_count": self._to_int(item.get("collected_count")),
                "comment_count": self._to_int(item.get("comment_count")),
                "share_count": self._to_int(item.get("share_count")),
            },
            "media": {
                "cover_url": item.get("cover_url") or "",
                "video_download_url": item.get("video_download_url") or "",
                "music_download_url": item.get("music_download_url") or "",
                "note_image_urls": self._split_urls(item.get("note_download_url")),
            },
            "source_keyword": item.get("source_keyword") or source.get("keyword") or "",
            "ip_location": item.get("ip_location") or "",
            "asr_text": item.get("asr_text") or "",
            "ocr_text": item.get("ocr_text") or "",
            "mediacrawler_raw": item,
        }

    def _to_int(self, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return value
        text = str(value).replace(",", "").strip()
        if text.isdigit():
            return int(text)
        return value

    def _split_urls(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return [part.strip() for part in str(value).split(",") if part.strip()]
