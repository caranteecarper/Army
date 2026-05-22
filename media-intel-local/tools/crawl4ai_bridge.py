"""
Crawl website pages with Crawl4AI in an external Python environment.

The parent pipeline stays Python 3.8 compatible. Current Crawl4AI releases
need a newer Python, so this bridge accepts JSON on stdin and prints JSON only.
"""

import asyncio
from contextlib import redirect_stdout
import json
import re
import sys
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


def _read_payload() -> Dict[str, Any]:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("stdin payload must be a JSON object")
    return payload


def _seed(url_or_seed: Any) -> Dict[str, Any]:
    if isinstance(url_or_seed, dict):
        return dict(url_or_seed)
    return {"url": str(url_or_seed)}


def _markdown(result: Any) -> str:
    markdown = getattr(result, "markdown", "")
    if isinstance(markdown, str):
        return markdown
    return str(
        getattr(markdown, "fit_markdown", "")
        or getattr(markdown, "raw_markdown", "")
        or ""
    )


def _links(result: Any, base_url: str) -> List[str]:
    collected = []
    links = getattr(result, "links", {}) or {}
    pools = []
    if isinstance(links, dict):
        pools.extend(links.values())
    for pool in pools:
        if not isinstance(pool, list):
            continue
        for link in pool:
            href = link.get("href") if isinstance(link, dict) else link
            if href:
                absolute = urljoin(base_url, str(href))
                if absolute not in collected:
                    collected.append(absolute)
    return collected


def _huanqiu_aid_links(result: Any, base_url: str) -> List[str]:
    html = str(getattr(result, "html", "") or "")
    host = urlparse(base_url).netloc
    aids = re.findall(
        r'<textarea[^>]+class=["\']item-aid["\'][^>]*>\s*([A-Za-z0-9]+)\s*</textarea>',
        html,
        flags=re.IGNORECASE,
    )
    return [
        "https://{}/article/{}".format(host, aid)
        for aid in aids
        if host and aid
    ]


def _list_links(payload: Dict[str, Any], result: Any, base_url: str) -> List[str]:
    links = _links(result, base_url)
    if payload.get("article_seed_mode") == "huanqiu_aid_textarea":
        links.extend(_huanqiu_aid_links(result, base_url))
    collected = []
    for link in links:
        if link not in collected:
            collected.append(link)
    return collected


def _serialize(result: Any, seed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": str(getattr(result, "url", "") or seed.get("url", "")),
        "title": str((getattr(result, "metadata", {}) or {}).get("title", "")),
        "markdown": _markdown(result),
        # Keep head/script metadata for local publish-time extraction.
        "html": str(getattr(result, "html", "") or getattr(result, "cleaned_html", "") or ""),
        "metadata": getattr(result, "metadata", {}) or {},
        "seed": seed,
    }


async def _crawl(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    config = CrawlerRunConfig(
        word_count_threshold=int(payload.get("word_count_threshold") or 10)
    )
    browser_config = BrowserConfig(
        chrome_channel=str(payload.get("browser_channel") or "chrome"),
        verbose=False,
    )
    seeds = [_seed(value) for value in payload.get("article_urls") or []]

    async with AsyncWebCrawler(config=browser_config) as crawler:
        list_url = str(payload.get("list_url") or "").strip()
        if list_url:
            list_result = await crawler.arun(list_url, config=config)
            pattern = str(payload.get("article_url_pattern") or "")
            matcher = re.compile(pattern) if pattern else None
            for link in _list_links(payload, list_result, list_url):
                if matcher and not matcher.search(link):
                    continue
                if not any(seed.get("url") == link for seed in seeds):
                    seeds.append({"url": link})

        max_articles = int(payload.get("max_articles") or 20)
        output = []
        for seed in seeds[:max_articles]:
            url = str(seed.get("url") or "").strip()
            if not url:
                continue
            result = await crawler.arun(url, config=config)
            output.append(_serialize(result, seed))
        return output


def main() -> None:
    payload = _read_payload()
    with redirect_stdout(sys.stderr):
        output = asyncio.run(_crawl(payload))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
