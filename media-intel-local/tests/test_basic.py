import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.deduplicate import deduplicate_items
from core.normalize import normalize_text
from core.schema import build_normalized_item, make_excerpt, make_item_id
from crawlers.wechat_crawler import WechatCrawler
from crawlers.website_crawler import WebsiteCrawler
from crawlers.xhs_crawler import XiaohongshuCrawler


class BasicPipelineTest(unittest.TestCase):
    def test_make_item_id_is_stable_for_source_and_url(self):
        first = make_item_id("wx_001", "https://example.com/a", "first title")
        second = make_item_id("wx_001", "https://example.com/a", "changed title")
        self.assertEqual(first, second)

    def test_make_excerpt_truncates_long_text(self):
        excerpt = make_excerpt("a" * 400, max_len=260)
        self.assertEqual(len(excerpt), 260)

    def test_build_normalized_item_fills_missing_metric_fields(self):
        item = build_normalized_item(
            source_type="wechat",
            source_id="wx_001",
            source_name="公众号A",
            platform="微信公众号",
            title="测试",
            url="https://example.com/a",
            publish_time="2026-05-21 09:00:00",
            content_text="正文",
            metrics={"like_count": 2},
        )

        self.assertEqual(item["metrics"]["like_count"], 2)
        self.assertIsNone(item["metrics"]["read_count"])
        self.assertIsNone(item["metrics"]["favorite_count"])
        self.assertIsNone(item["metrics"]["comment_count"])
        self.assertIsNone(item["metrics"]["share_count"])

    def test_deduplicate_items_keeps_first_url(self):
        first = {"url": "https://example.com/a", "title": "A", "source_id": "one"}
        duplicate = {
            "url": "https://example.com/a",
            "title": "B",
            "source_id": "two",
        }
        unique = {"url": "https://example.com/b", "title": "C", "source_id": "one"}

        self.assertEqual(deduplicate_items([first, duplicate, unique]), [first, unique])

    def test_normalize_text_compresses_whitespace(self):
        self.assertEqual(normalize_text("  one\n\t two   three  "), "one two three")

    def test_wechat_xml_feed_keeps_date_for_filtering(self):
        crawler = WechatCrawler(PROJECT_ROOT)
        items = crawler._parse_xml_feed(
            "<rss><channel><item><title>文章</title>"
            "<link>https://mp.weixin.qq.com/s/a</link>"
            "<pubDate>Thu, 21 May 2026 09:00:00 +0800</pubDate>"
            "<description>正文</description></item></channel></rss>"
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_at"][:10], "2026-05-21")

    def test_wechat_xml_feed_converts_gmt_to_shanghai_date(self):
        crawler = WechatCrawler(PROJECT_ROOT)
        items = crawler._parse_xml_feed(
            "<rss><channel><item><title>文章</title>"
            "<link>https://mp.weixin.qq.com/s/a</link>"
            "<pubDate>Thu, 21 May 2026 16:04:25 GMT</pubDate>"
            "<description>正文</description></item></channel></rss>"
        )

        self.assertEqual(items[0]["published_at"][:10], "2026-05-22")

    def test_wechat_chinese_publish_time_becomes_iso(self):
        crawler = WechatCrawler(PROJECT_ROOT)

        self.assertEqual(
            crawler._normalized_datetime("2026年5月22日 00:04"),
            "2026-05-22T00:04:00+08:00",
        )

    def test_website_publish_date_can_come_from_time_tag(self):
        crawler = WebsiteCrawler(PROJECT_ROOT)
        raw_item = crawler._to_raw_item(
            {
                "url": "https://example.com/a",
                "metadata": {"title": "网页标题"},
                "html": '<time datetime="2026-05-21T08:00:00+08:00"></time>',
                "markdown": "正文",
            },
            {"name": "网站A"},
        )

        self.assertEqual(raw_item["date"], "2026-05-21T08:00:00+08:00")

    def test_website_publish_date_can_come_from_site_html(self):
        crawler = WebsiteCrawler(PROJECT_ROOT)
        ifeng = crawler._html_date(
            '<meta name="og:time " content="2026-05-21 11:19:15">'
        )
        thepaper = crawler._html_date('"pubTime":"2026-05-21 14:32"')
        huanqiu = crawler._html_date(
            '<textarea class="article-time">1779404566895</textarea>'
        )

        self.assertEqual(ifeng, "2026-05-21 11:19:15")
        self.assertEqual(thepaper, "2026-05-21 14:32")
        self.assertEqual(huanqiu, "1779404566895")

    def test_xhs_detail_maps_to_existing_adapter_shape(self):
        crawler = XiaohongshuCrawler(PROJECT_ROOT)
        raw_item = crawler._to_raw_item(
            {"id": "note-1", "xsec_token": "token"},
            {
                "note": {
                    "title": "笔记",
                    "desc": "正文",
                    "time": 1789952400000,
                    "interactInfo": {
                        "likedCount": "12",
                        "collectedCount": "3",
                        "commentCount": "2",
                    },
                }
            },
        )

        self.assertEqual(raw_item["note_title"], "笔记")
        self.assertEqual(raw_item["likes"], 12)
        self.assertEqual(raw_item["note_url"], "https://www.xiaohongshu.com/explore/note-1")


if __name__ == "__main__":
    unittest.main()
