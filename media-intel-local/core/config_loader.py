import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import yaml


CLIENT_CONFIG_NAME = "client_sources.yaml"

DEFAULT_PROJECT = {
    "name": "daily-media-intel-local",
    "timezone": "Asia/Shanghai",
    "output_dir": "output",
}


def load_registry_config(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file_obj:
        config = yaml.safe_load(file_obj)
    if not isinstance(config, dict):
        raise ValueError("config file must contain a YAML mapping")
    if _looks_like_full_registry(config):
        return config
    return expand_client_config(config)


def expand_client_config(config: Dict[str, Any]) -> Dict[str, Any]:
    project = dict(DEFAULT_PROJECT)
    project.update(config.get("project") or {})
    return {
        "project": project,
        "wechat": [_wechat_source(item) for item in _source_items(config.get("wechat"))],
        "websites": [_website_source(item) for item in _source_items(config.get("websites"))],
        "xhs": [_xhs_source(item) for item in _source_items(config.get("xhs"))],
        "douyin": [_douyin_source(item) for item in _source_items(config.get("douyin"))],
    }


def _looks_like_full_registry(config: Dict[str, Any]) -> bool:
    for key in ("wechat", "websites", "xhs", "douyin"):
        value = config.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and item.get("type"):
                return True
    return False


def _source_items(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _mapping(item: Any, value_key: str) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    return {value_key: str(item or "")}


def _enabled(data: Dict[str, Any]) -> bool:
    return bool(data.get("enabled", True))


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return "{}_{}".format(prefix, digest)


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_").lower()
    return cleaned or "source"


def _host_name(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    return host.replace("www.", "") or "网站"


def _website_defaults(url: str) -> Dict[str, Any]:
    parsed = urlparse(url)
    host = parsed.netloc
    if host == "mil.huanqiu.com":
        return {
            "article_seed_mode": "huanqiu_aid_textarea",
            "article_url_pattern": r"^https://mil\.huanqiu\.com/article/",
        }
    if host == "mil.ifeng.com":
        return {"article_url_pattern": r"^https://mil\.ifeng\.com/c/(?!special/)"}
    if host == "www.thepaper.cn" and parsed.path.startswith("/list_25430"):
        return {"article_url_pattern": r"/newsDetail_forward_[0-9]+$"}
    escaped_host = re.escape(host)
    return {"article_url_pattern": r"^https?://{}/".format(escaped_host)}


def _website_source(item: Any) -> Dict[str, Any]:
    data = _mapping(item, "url")
    url = str(data.get("url") or data.get("list_url") or "").strip()
    if not url:
        raise ValueError("website source is missing url")

    parsed = urlparse(url)
    source = {
        "id": data.get("id") or _stable_id("web", url),
        "name": data.get("name") or _host_name(url),
        "type": "website",
        "enabled": _enabled(data),
        "fetch_mode": "crawl4ai",
        "crawl4ai_python": data.get("crawl4ai_python") or "../envs/media-crawlers/python.exe",
        "browser_channel": data.get("browser_channel") or "chrome",
        "list_url": url,
        "max_articles": int(data.get("max_articles") or data.get("limit") or 80),
        "crawl_timeout_seconds": int(data.get("crawl_timeout_seconds") or 600),
    }
    source.update(_website_defaults(url))
    for key in ("article_seed_mode", "article_url_pattern", "article_urls", "word_count_threshold"):
        if data.get(key) is not None:
            source[key] = data[key]
    if data.get("name"):
        source["name"] = data["name"]
    elif parsed.netloc == "mil.huanqiu.com":
        source["name"] = "环球网军事"
    elif parsed.netloc == "mil.ifeng.com":
        source["name"] = "凤凰网军事"
    elif parsed.netloc == "www.thepaper.cn" and parsed.path.startswith("/list_25430"):
        source["name"] = "澎湃防务"
    return source


def _wechat_source(item: Any) -> Dict[str, Any]:
    data = _mapping(item, "link")
    link = str(data.get("feed_url") or data.get("link") or data.get("url") or "").strip()
    if not link:
        raise ValueError("wechat source is missing link")

    source = {
        "id": data.get("id") or _stable_id("wx", link),
        "name": data.get("name") or "微信公众号",
        "type": "wechat",
        "enabled": _enabled(data),
        "fetch_mode": "wewe_rss",
        "article_enrichment": bool(data.get("article_enrichment", True)),
        "browser_channel": data.get("browser_channel") or "chrome",
        "wechat_article_python": data.get("wechat_article_python") or "../envs/media-crawlers/python.exe",
        "wechat_article_crawler_dir": data.get("wechat_article_crawler_dir") or "../external-tools/wechat-article-crawler",
        "feed_timeout_seconds": int(data.get("feed_timeout_seconds") or 30),
    }
    if _is_wewe_feed(link):
        source["feed_url"] = link
    else:
        source["feed_url"] = ""
        source["pending_link"] = link
        source["setup_hint"] = (
            "这个公众号链接还需要先通过 WeWe RSS 添加成 feed。"
            "当前自动抓取入口需要 feed_url；后续可接 WeWe 的新增源 API 做全自动添加。"
        )
    return source


def _is_wewe_feed(value: str) -> bool:
    lowered = value.lower()
    return "/feeds/" in lowered or lowered.endswith(".rss") or lowered.endswith(".atom")


def _xhs_source(item: Any) -> Dict[str, Any]:
    data = _mapping(item, "user_id")
    keyword = str(data.get("keyword") or "").strip()
    user_id = str(
        data.get("user_id")
        or data.get("xhs_id")
        or data.get("account_id")
        or data.get("profile_url")
        or ""
    ).strip()
    if user_id and user_id.startswith("http"):
        user_id = _last_url_part(user_id)
    if not keyword and not user_id:
        raise ValueError("xiaohongshu source needs user_id or keyword")

    source = {
        "id": data.get("id") or _stable_id("xhs", keyword or user_id),
        "name": data.get("name") or ("小红书关键词-{}".format(keyword) if keyword else "小红书账号-{}".format(user_id)),
        "type": "xiaohongshu",
        "enabled": _enabled(data),
        "fetch_mode": "xiaohongshu_skill",
        "skill_python": data.get("skill_python") or "../envs/media-crawlers/python.exe",
        "skill_dir": data.get("skill_dir") or "../external-tools/xiaohongshu-skill",
        "cookie_path": data.get("cookie_path") or ".runtime/xiaohongshu/cookies.json",
        "headless": bool(data.get("headless", True)),
        "fetch_detail": bool(data.get("fetch_detail", True)),
        "require_content": bool(data.get("require_content", True)),
        "detail_timeout_seconds": int(data.get("detail_timeout_seconds") or 180),
        "limit": int(data.get("limit") or 20),
    }
    if keyword:
        source.update(
            {
                "mode": "keyword_search",
                "keyword": keyword,
                "sort_by": data.get("sort_by") or "最新",
                "publish_time": data.get("publish_time") or "一天内",
                "fallback_xsec_sources": data.get("fallback_xsec_sources")
                or ["pc_search", "pc_feed", "pc_note"],
            }
        )
    else:
        source.update({"mode": "user_profile", "user_id": user_id})
        if data.get("xsec_token"):
            source["xsec_token"] = data["xsec_token"]
    return source


def _douyin_source(item: Any) -> Dict[str, Any]:
    data = _mapping(item, "user_id")
    keyword = str(data.get("keyword") or "").strip()
    user_id = str(
        data.get("user_id")
        or data.get("douyin_id")
        or data.get("account_id")
        or data.get("profile_url")
        or ""
    ).strip()
    if not keyword and not user_id:
        raise ValueError("douyin source needs user_id or keyword")

    source = {
        "id": data.get("id") or _stable_id("dy", keyword or user_id),
        "name": data.get("name") or ("抖音关键词-{}".format(keyword) if keyword else "抖音账号-{}".format(user_id)),
        "type": "douyin",
        "enabled": _enabled(data),
        "fetch_mode": "mediacrawler",
        "douyin_python": data.get("douyin_python") or "../envs/media-douyin/Scripts/python.exe",
        "mediacrawler_dir": data.get("mediacrawler_dir") or "../external-tools/MediaCrawler",
        "publish_time": data.get("publish_time") or "one_day",
        "limit": int(data.get("limit") or 30),
        "login_type": data.get("login_type") or "qrcode",
        "headless": bool(data.get("headless", False)),
        "enable_cdp": bool(data.get("enable_cdp", True)),
        "cdp_connect_existing": bool(data.get("cdp_connect_existing", False)),
        "auto_close_browser": bool(data.get("auto_close_browser", True)),
        "reuse_last_success_on_empty": bool(data.get("reuse_last_success_on_empty", True)),
        "fetch_comments": bool(data.get("fetch_comments", False)),
        "download_video": bool(data.get("download_video", False)),
        "asr_enabled": bool(data.get("asr_enabled", True)),
        "asr_python": data.get("asr_python") or "../envs/media-douyin/Scripts/python.exe",
        "asr_model": data.get("asr_model") or "small",
        "asr_language": data.get("asr_language") or "zh",
        "asr_device": data.get("asr_device") or "cpu",
        "asr_compute_type": data.get("asr_compute_type") or "int8",
        "asr_timeout_seconds": int(data.get("asr_timeout_seconds") or 1800),
        "crawl_timeout_seconds": int(data.get("crawl_timeout_seconds") or 900),
    }
    if keyword:
        source.update({"mode": "keyword_search", "keyword": keyword})
    else:
        source.update({"mode": "creator", "creator_ids": [user_id]})
    return source


def _last_url_part(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[-1] if parts else url
