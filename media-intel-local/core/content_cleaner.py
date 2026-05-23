import html
import re
from typing import Any, Dict, List, Tuple


URL_RE = re.compile(r"https?://[^\s\]\)\"'<]+")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.I)
HTML_SRC_RE = re.compile(r"\b(?:src|data-src|data-original)=[\"']([^\"']+)[\"']", re.I)


DROP_LINE_KEYWORDS = [
    "首页",
    "登录",
    "注册",
    "下载客户端",
    "无障碍",
    "更多",
    "责任编辑",
    "责编",
    "Copyright",
    "站内",
    "用户",
    "评论",
]


def clean_website_content(
    raw_text: Any,
    raw_item: Dict[str, Any] = None,
    source: Dict[str, Any] = None,
) -> Tuple[str, List[str]]:
    text = "" if raw_text is None else str(raw_text)
    raw_item = raw_item or {}
    source = source or {}

    images = _filter_images_for_source(extract_image_urls(text, raw_item), source)
    article_html = _extract_article_html(text, source)
    if article_html:
        cleaned = _html_to_text(article_html)
    else:
        cleaned = _markdown_to_text(text)

    cleaned = _source_trim(cleaned, raw_item, source)
    cleaned = _post_clean_text(cleaned)
    return cleaned, images


def extract_image_urls(raw_text: Any, raw_item: Dict[str, Any] = None) -> List[str]:
    text = "" if raw_text is None else str(raw_text)
    raw_item = raw_item or {}
    urls = []

    for _alt, url in MARKDOWN_IMAGE_RE.findall(text):
        urls.append(url)
    for url in HTML_IMG_RE.findall(text):
        urls.append(url)
    for url in HTML_SRC_RE.findall(text):
        urls.append(url)

    crawl_raw = raw_item.get("crawl4ai_raw") or {}
    metadata = crawl_raw.get("metadata") if isinstance(crawl_raw, dict) else {}
    if isinstance(metadata, dict):
        for key in ("og:image", "image", "twitter:image"):
            value = metadata.get(key)
            if value:
                urls.append(str(value))

    return _dedupe_urls(_normalize_url(url) for url in urls if url)


def _extract_article_html(text: str, source: Dict[str, Any]) -> str:
    patterns = []
    source_id = str(source.get("id") or "")
    if source_id == "web_huanqiu_mil":
        patterns.extend(
            [
                r"<article\b[^>]*>.*?</article>",
                r"<section\b[^>]*data-type=[\"']rtext[\"'][^>]*>.*?</section>",
            ]
        )
    patterns.extend(
        [
            r"<article\b[^>]*>.*?</article>",
            r"<main\b[^>]*>.*?</main>",
        ]
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            return match.group(0)
    return ""


def _html_to_text(value: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<adv-loader\b[^>]*>.*?</adv-loader>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<img\b[^>]*>", " ", text, flags=re.I)
    text = re.sub(
        r"</?(?:p|div|section|article|h[1-6]|li|br|em|strong)\b[^>]*>",
        "\n",
        text,
        flags=re.I,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def _markdown_to_text(value: str) -> str:
    text = re.sub(r"\s+\*\s+", "\n", value)
    text = re.sub(r"\s+#{1,6}\s+", "\n", text)
    text = MARKDOWN_IMAGE_RE.sub(" ", text)
    text = MARKDOWN_LINK_RE.sub(lambda match: match.group(1) or " ", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", " ", text)
    text = re.sub(r"[*_#>`]+", " ", text)
    text = URL_RE.sub(" ", text)
    return html.unescape(text)


def _source_trim(value: str, raw_item: Dict[str, Any], source: Dict[str, Any]) -> str:
    text = value
    title = str(raw_item.get("headline") or "").strip()
    title_candidates = [title]
    if "_" in title:
        title_candidates.append(title.split("_", 1)[0].strip())
    for candidate in title_candidates:
        if candidate and candidate in text:
            index = text.find(candidate)
            if index > 0:
                text = text[index:]
            break

    source_id = str(source.get("id") or "")
    end_markers = [
        "为您推荐",
        "算法反馈",
        "网友评论",
        "发表评论",
        "查看全部评论",
        "相关推荐",
        "相关报道",
        "热门新闻",
        "责任编辑",
        "责编：",
    ]
    if source_id == "web_thepaper_defense":
        end_markers.extend(["澎湃新闻报料", "下载澎湃新闻客户端"])
    for marker in end_markers:
        index = text.find(marker)
        if index > 80:
            text = text[:index]
    text = re.sub(r"\s+推荐\d+\s+\d+\s+条评论.*$", " ", text, flags=re.S)
    text = re.sub(r"\s+\d+\s+条评论/\d+\s+人参与.*$", " ", text, flags=re.S)
    return text


def _post_clean_text(value: str) -> str:
    text = re.sub(r"/csr-component/[^\s]+", " ", value)
    text = re.sub(r"\b[a-z0-9.-]+\.(?:com|cn|net|org)\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{10,13}\b", " ", text)
    text = re.sub(r"\b[0-9A-Za-z]{8,}\b", " ", text)
    text = re.sub(r"javascript:void\\?\(0\\?\)", " ", text, flags=re.I)
    lines = []
    for line in re.split(r"[\r\n]+", text):
        cleaned = re.sub(r"\s+", " ", line).strip(" -*|_")
        if not _keep_line(cleaned):
            continue
        lines.append(cleaned)
    return "\n".join(_dedupe_lines(lines))


def _keep_line(line: str) -> bool:
    if not line or len(line) <= 1:
        return False
    if URL_RE.search(line):
        return False
    if line.count(" ") > 12 and len(line) < 80:
        return False
    if any(keyword == line for keyword in DROP_LINE_KEYWORDS):
        return False
    if sum(1 for keyword in DROP_LINE_KEYWORDS if keyword in line) >= 3:
        return False
    return True


def _dedupe_lines(lines: List[str]) -> List[str]:
    seen = set()
    result = []
    for line in lines:
        key = line.strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def _normalize_url(url: Any) -> str:
    text = str(url or "").strip().strip("\"'()")
    if not text or text.lower().startswith("data:"):
        return ""
    if text.startswith("//"):
        text = "https:" + text
    lower = text.lower()
    if any(token in lower for token in ("newsdetail_forward", "/article/", "javascript:")):
        return ""
    noise_tokens = (
        "logo",
        "common/200",
        "mediav.com",
        "sspservice.",
        "ad.png",
        "360ad",
        "/feprod/",
        "ifengimcp/pic/",
        "/ucms/qr/",
        "w56_h34",
        "_next/static",
        "defhead",
        "pp_report",
        "scalecode",
        "wechat.",
    )
    if any(token in lower for token in noise_tokens):
        return ""
    return text


def _filter_images_for_source(urls: List[str], source: Dict[str, Any]) -> List[str]:
    source_id = str(source.get("id") or "")
    if source_id == "web_huanqiu_mil":
        return [url for url in urls if "img.huanqiucdn.cn" in url][:12]
    if source_id == "web_ifeng_mil":
        article_images = [
            url
            for url in urls
            if (
                ("d.ifengimg.com" in url or "x0.ifengimg.com" in url)
                and "/ucms/" in url
            )
        ]
        return article_images[:5]
    if source_id == "web_thepaper_defense":
        return [
            url
            for url in urls
            if "imagecloud.thepaper.cn" in url or "file.thepaper.cn" in url
        ][:8]
    return urls[:10]


def _dedupe_urls(urls: Any) -> List[str]:
    seen = set()
    result = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result
