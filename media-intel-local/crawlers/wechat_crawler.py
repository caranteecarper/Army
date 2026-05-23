import json
from pathlib import Path
from typing import Any, Dict, List
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from crawlers.base import BaseCrawler
from crawlers.external import python_command, run_json_command


class WechatCrawler(BaseCrawler):
    source_type = "wechat"

    def fetch(self, source: Dict[str, Any], target_date: str) -> List[Dict[str, Any]]:
        if self._is_mock_source(source):
            items = self._read_mock_items(source)
            return self._filter_by_date(items, "published_at", target_date)

        items = self._read_wewe_feed(source)
        dated_items = self._filter_by_date(items, "published_at", target_date)
        if source.get("article_enrichment", True):
            return [self._enrich_article(item, source) for item in dated_items]
        return dated_items

    def _read_wewe_feed(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        feed_url = str(source.get("feed_url") or "").strip()
        if not feed_url:
            hint = source.get("setup_hint") or "wechat source is missing feed_url"
            raise ValueError(
                "wechat source {} is missing feed_url: {}".format(
                    source.get("id", ""), hint
                )
            )

        timeout = int(source.get("feed_timeout_seconds") or 30)
        request = Request(
            feed_url,
            headers={"User-Agent": "media-intel-local/1.0 RSS reader"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError("cannot read WeWe RSS feed {}: {}".format(feed_url, exc))

        stripped = payload.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return self._parse_json_feed(payload)
        return self._parse_xml_feed(payload)

    def _parse_json_feed(self, payload: str) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("invalid WeWe JSON feed: {}".format(exc))
        feed_items = parsed.get("items", []) if isinstance(parsed, dict) else parsed
        if not isinstance(feed_items, list):
            raise ValueError("WeWe JSON feed items must be a list")

        return [
            self._feed_item(
                title=item.get("title", ""),
                url=item.get("url") or item.get("external_url") or item.get("link", ""),
                published_at=item.get("date_published")
                or item.get("pubDate")
                or item.get("published_at")
                or item.get("published", ""),
                content=item.get("content_text")
                or item.get("content_html")
                or item.get("summary", ""),
                feed_raw=item,
            )
            for item in feed_items
            if isinstance(item, dict)
        ]

    def _parse_xml_feed(self, payload: str) -> List[Dict[str, Any]]:
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise RuntimeError("invalid WeWe RSS/Atom feed XML: {}".format(exc))

        entries = [
            node
            for node in root.iter()
            if self._local_name(node.tag) in ("item", "entry")
        ]
        return [self._xml_entry_to_item(entry) for entry in entries]

    def _xml_entry_to_item(self, entry: ElementTree.Element) -> Dict[str, Any]:
        fields = {}  # type: Dict[str, Any]
        links = []
        for child in list(entry):
            name = self._local_name(child.tag)
            if name == "link":
                links.append(child.attrib.get("href") or (child.text or ""))
            elif name not in fields:
                fields[name] = child.text or ""

        content = fields.get("encoded") or fields.get("content") or fields.get("description", "")
        published_at = (
            fields.get("pubDate")
            or fields.get("published")
            or fields.get("updated")
            or fields.get("date", "")
        )
        return self._feed_item(
            title=fields.get("title", ""),
            url=links[0] if links else fields.get("guid", ""),
            published_at=published_at,
            content=content,
            feed_raw={"fields": fields, "links": links},
        )

    def _feed_item(
        self,
        title: Any,
        url: Any,
        published_at: Any,
        content: Any,
        feed_raw: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "title": str(title or ""),
            "url": str(url or ""),
            "published_at": self._normalized_datetime(published_at),
            "content": str(content or ""),
            "feed_raw": feed_raw,
        }

    def _local_name(self, tag: str) -> str:
        return tag.split("}", 1)[-1]

    def _enrich_article(
        self, item: Dict[str, Any], source: Dict[str, Any]
    ) -> Dict[str, Any]:
        crawler_dir = source.get("wechat_article_crawler_dir")
        if not crawler_dir:
            raise ValueError(
                "wechat source {} needs wechat_article_crawler_dir for article enrichment".format(
                    source.get("id", "")
                )
            )

        bridge = self.project_root / "tools" / "wechat_article_bridge.py"
        command = python_command(source.get("wechat_article_python"), self.project_root)
        command.extend(
            [
                str(bridge),
                "--crawler-dir",
                str(self.project_root / Path(str(crawler_dir))),
                "--url",
                item.get("url", ""),
                "--browser-channel",
                str(source.get("browser_channel") or "chrome"),
            ]
        )
        article = run_json_command(
            command,
            timeout_seconds=int(source.get("article_timeout_seconds") or 180),
        )
        enriched = dict(item)
        enriched["title"] = article.get("title") or enriched.get("title", "")
        enriched["published_at"] = self._normalized_datetime(
            article.get("publish_time") or enriched.get("published_at", "")
        )
        enriched["content"] = article.get("markdown") or enriched.get("content", "")
        enriched["article_raw"] = article
        return enriched
