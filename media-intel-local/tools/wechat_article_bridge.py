"""
Expose wechat-article-crawler library output as one JSON object.

Run this bridge with the Python environment that has the third-party crawler
and its Crawl4AI dependencies installed.
"""

import argparse
import asyncio
from contextlib import redirect_stdout
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge wechat-article-crawler output")
    parser.add_argument("--crawler-dir", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        help="Crawl4AI browser channel. Defaults to the locally installed Chrome.",
    )
    args = parser.parse_args()

    crawler_dir = Path(args.crawler_dir).resolve()
    sys.path.insert(0, str(crawler_dir))
    from scripts import crawl_wechat

    browser_config = crawl_wechat.BrowserConfig

    def local_browser_config(*browser_args, **browser_kwargs):
        browser_kwargs.setdefault("chrome_channel", args.browser_channel)
        return browser_config(*browser_args, **browser_kwargs)

    crawl_wechat.BrowserConfig = local_browser_config

    with redirect_stdout(sys.stderr):
        article = asyncio.run(crawl_wechat.crawl_wechat_article(args.url))
    print(json.dumps(article, ensure_ascii=False))


if __name__ == "__main__":
    main()
