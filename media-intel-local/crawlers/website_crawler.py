import re
from typing import Any, Dict, List

from crawlers.base import BaseCrawler
from crawlers.external import python_command, run_json_command


class WebsiteCrawler(BaseCrawler):
    source_type = "website"

    def fetch(self, source: Dict[str, Any], target_date: str) -> List[Dict[str, Any]]:
        if self._is_mock_source(source):
            items = self._read_mock_items(source)
            return self._filter_by_date(items, "date", target_date)

        results = self._crawl_with_crawl4ai(source)
        items = [self._to_raw_item(result, source) for result in results]
        return self._filter_by_date(items, "date", target_date)

    def _crawl_with_crawl4ai(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        bridge = self.project_root / "tools" / "crawl4ai_bridge.py"
        command = python_command(source.get("crawl4ai_python"), self.project_root)
        command.append(str(bridge))
        payload = {
            "list_url": source.get("list_url", ""),
            "article_urls": source.get("article_urls") or source.get("urls") or [],
            "article_url_pattern": source.get("article_url_pattern", ""),
            "article_seed_mode": source.get("article_seed_mode", ""),
            "max_articles": int(source.get("max_articles") or 20),
            "word_count_threshold": int(source.get("word_count_threshold") or 10),
            "browser_channel": source.get("browser_channel", "chrome"),
        }
        results = run_json_command(
            command,
            payload=payload,
            timeout_seconds=int(source.get("crawl_timeout_seconds") or 300),
        )
        if not isinstance(results, list):
            raise ValueError("Crawl4AI bridge must return a JSON list")
        return [item for item in results if isinstance(item, dict)]

    def _to_raw_item(self, result: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
        seed = result.get("seed") or {}
        if not isinstance(seed, dict):
            seed = {}
        metadata = result.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        publish_time = (
            seed.get("published_at")
            or seed.get("date")
            or result.get("published_at")
            or self._metadata_date(metadata, source)
            or self._html_date(str(result.get("html") or ""))
        )
        title = (
            seed.get("title")
            or metadata.get("title")
            or metadata.get("og:title")
            or result.get("title")
            or ""
        )
        return {
            "headline": str(title or ""),
            "link": str(result.get("url") or seed.get("url") or ""),
            "date": self._normalized_datetime(publish_time),
            "markdown": str(result.get("markdown") or ""),
            "source": source.get("name", ""),
            "crawl4ai_raw": result,
        }

    def _metadata_date(self, metadata: Dict[str, Any], source: Dict[str, Any]) -> Any:
        configured_keys = source.get("publish_date_metadata_keys") or []
        if isinstance(configured_keys, str):
            configured_keys = [configured_keys]
        keys = list(configured_keys) + [
            "article:published_time",
            "og:published_time",
            "published_time",
            "publish_date",
            "datePublished",
            "date",
        ]
        for key in keys:
            if metadata.get(key):
                return metadata[key]
        return ""

    def _html_date(self, html: str) -> str:
        patterns = [
            r"<meta[^>]+(?:property|name|itemprop)=[\"'](?:article:published_time|og:published_time|og:time\s*|pubdate|publishdate|datePublished|date)[\"'][^>]+content=[\"']([^\"']+)",
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name|itemprop)=[\"'](?:article:published_time|og:published_time|og:time\s*|pubdate|publishdate|datePublished|date)[\"']",
            r"<time[^>]+datetime=[\"']([^\"']+)",
            r"<textarea[^>]+class=[\"']article-time[\"'][^>]*>\s*([0-9]{10,13})\s*</textarea>",
            r"[\"']pubTime[\"']\s*:\s*[\"']([0-9]{4}-[0-9]{2}-[0-9]{2}(?:\s+[0-9]{2}:[0-9]{2}(?::[0-9]{2})?)?)[\"']",
        ]
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return ""
