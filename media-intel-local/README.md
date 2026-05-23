# media-intel-local

## 项目目标

`media-intel-local` 是一个本地媒体内容采集与格式化管道。当前阶段只做 crawler 接入、日期过滤、统一 schema、文本清洗、去重和运行日志：

```text
source_registry.yaml
        -> platform crawler
        -> adapter
        -> normalize
        -> deduplicate
        -> raw_items.json / normalized_items.json / run_log.json
```

当前版本完全不消耗大模型 token。
当前版本不进行内容价值判断。
当前版本不生成口播稿。
当前版本只负责把不同来源的数据统一成 `normalized_items.json`。
后续 router 和 AI 轻判断只读取 `normalized_items.json`。

## 当前边界

主流程、schema、adapter、日期过滤、去重和日志都兼容 Python 3.8。本项目本身只安装 `PyYAML`，不依赖大模型、Hermes 或云端服务。

当前 crawler 支持两种输入：

- `fetch_mode: mock`：读取仓库内 JSON，用于本地回归和离线验证。
- 真实模式：微信公众号走 WeWe RSS 和 `wechat-article-crawler`，网站走 Crawl4AI，小红书走 `xiaohongshu-skill` CLI。

当前 Crawl4AI 与 `xiaohongshu-skill` 的上游环境要求高于 Python 3.8。为保持本项目每日命令仍可由 Python 3.8 执行，网站和公众号正文解析使用 `tools/*_bridge.py` 由配置指定的外部 Python 解释器运行，小红书使用配置指定的 skill Python/CLI 运行。

## 目录结构

```text
media-intel-local/
|-- README.md
|-- requirements.txt
|-- main.py
|-- config/source_registry.yaml
|-- mock_data/
|-- crawlers/
|   |-- base.py
|   |-- external.py
|   |-- wechat_crawler.py
|   |-- website_crawler.py
|   `-- xhs_crawler.py
|-- adapters/
|-- core/
|   |-- schema.py
|   |-- normalize.py
|   `-- deduplicate.py
|-- tools/
|   |-- crawl4ai_bridge.py
|   `-- wechat_article_bridge.py
|-- output/
`-- tests/test_basic.py
```

## 运行方式

安装本项目依赖：

```bash
cd media-intel-local
pip install -r requirements.txt
```

抓取指定日期：

```bash
python main.py --date 2026-05-21
```

抓取配置时区的前一天：

```bash
python main.py --date yesterday
```

运行最小测试：

```bash
python tests/test_basic.py
```

## 输出文件

每次运行写到 `output/YYYY-MM-DD/`：

| 文件 | 说明 |
| --- | --- |
| `raw_items.json` | 日期过滤后的原始 crawler item，并补充源 ID、源名称和平台类型 |
| `normalized_items.json` | adapter 映射、基础清洗和去重后的统一 schema list |
| `run_log.json` | 运行日期、起止时间、源成功失败数、数据条数和逐源错误 |

单个源失败会进入 `run_log.json.errors`，不会阻断其他源。配置文件本身无法读取时程序整体失败。

## 源配置

源配置在 `config/source_registry.yaml`。新增同类源只追加 YAML 节点；主流程仍按 `type` 选择 crawler 与 adapter。`enabled: false` 的源跳过。

| type | mock 日期字段 | 真实抓取方式 |
| --- | --- | --- |
| `wechat` | `published_at` | WeWe RSS feed + `wechat-article-crawler` 正文补全 |
| `website` | `date` | Crawl4AI 页面 Markdown |
| `xiaohongshu` | `time` | `xiaohongshu-skill` 用户主页或关键词 CLI |

### 微信公众号

WeWe RSS 负责固定公众号文章列表。`wechat_crawler.py` 可解析 RSS、Atom 或 JSON feed，再对目标日期文章调用 `wechat-article-crawler` bridge 补 Markdown 正文。

```yaml
- id: wx_real
  name: 真实公众号
  type: wechat
  enabled: true
  fetch_mode: wewe_rss
  feed_url: http://127.0.0.1:4000/feeds/replace-me.rss
  article_enrichment: true
  browser_channel: chrome
  wechat_article_python: ../envs/media-crawlers/python.exe
  wechat_article_crawler_dir: ../external-tools/wechat-article-crawler
```

`article_enrichment: false` 时只保留 feed 自带正文。正文补全开启时，`wechat_article_crawler_dir` 必须指向本地 `wechat-article-crawler` 仓库目录。
本地已安装 Chrome 时保留 `browser_channel: chrome`，公众号正文 bridge 会让 Crawl4AI 使用系统 Chrome，不要求把 Playwright Chromium 下载到用户目录。

### 网站

Crawl4AI bridge 不使用 LLM extraction。它可以抓配置的 `article_urls`，也可以先抓 `list_url`，再用 `article_url_pattern` 从 Crawl4AI 提取的链接里筛文章 URL。

```yaml
- id: web_real
  name: 真实网站
  type: website
  enabled: true
  fetch_mode: crawl4ai
  crawl4ai_python: ../envs/media-crawlers/python.exe
  list_url: https://example.com/news
  article_url_pattern: /news/
  max_articles: 20
```

网站日期过滤优先读取显式种子日期、页面 metadata 和 HTML 中常见 publish meta 或 `<time datetime>`。缺少可解析发布时间的页面不会进入目标日期输出。对日期标注不稳定的网站，可以把文章 URL 写成带日期的种子：

```yaml
article_urls:
  - url: https://example.com/news/a
    title: 已知文章标题
    published_at: 2026-05-21
```

### 小红书

`xiaohongshu-skill` 被当成本地 CLI，不由大模型调度。keyword 模式先搜索，再按 note id 和 `xsec_token` 拉 detail；user profile 模式读取主页 feeds，默认也拉 detail 以补正文和互动字段。

```yaml
- id: xhs_real
  name: 小红书关键词
  type: xiaohongshu
  enabled: true
  fetch_mode: xiaohongshu_skill
  skill_python: ../envs/media-crawlers/python.exe
  skill_dir: ../external-tools/xiaohongshu-skill
  cookie_path: .runtime/xiaohongshu/cookies.json
  headless: true
  mode: keyword_search
  keyword: 退役军人
  sort_by: 最新
  publish_time: 一天内
  fetch_detail: true
  fallback_xsec_sources:
    - pc_search
    - pc_feed
    - pc_note
  require_content: true
  detail_timeout_seconds: 180
  limit: 20
```

小红书真实抓取前要在 skill 环境完成登录并保留 cookie。设置 `cookie_path` 时，crawler 会把它传给 skill CLI。
当前默认先抓搜索卡片，再打开详情页补正文。详情页会按 `pc_search`、`pc_feed`、`pc_note` 多路重试，并用 DOM 兜底提取标题、正文和图片。搜索卡片没有严格可用的目标日期时，crawler 会用本次 `target_date` 作为搜索窗口日期，并在 raw item 中保留 `raw_publish_time`、`time_source`、`detail_status` 和 `detail_source`。配置 `require_content: true` 时，正文为空的条目不会进入最终输出。

## 外部工具准备

本仓库不自动安装或启动外部抓取工具：

1. WeWe RSS 由你本地现有部署提供 feed URL。
2. `wechat-article-crawler` 仓库目录由 `wechat_article_crawler_dir` 指定；它依赖 Crawl4AI。
3. Crawl4AI 装在 `crawl4ai_python` 指向的外部 Python 环境，并先完成它要求的浏览器 setup。
4. `xiaohongshu-skill` 装在 `skill_dir` 指向的目录，使用 `skill_python` 对应环境安装依赖并完成 Playwright Chromium 与登录准备。

当前工作区的外部抓取依赖可放在 `../envs/media-crawlers/` 和 `../external-tools/`。外部命令运行时默认把 Crawl4AI、Playwright 和小红书会话目录写到本项目 `.runtime/`，避免依赖默认写入用户目录；需要改位置时设置 `MEDIA_INTEL_RUNTIME_DIR`。

源码参考：

- https://github.com/cooderl/wewe-rss
- https://github.com/gxcsoccer/wechat-article-crawler
- https://github.com/unclecode/crawl4ai
- https://github.com/DeliciousBuding/xiaohongshu-skill

## 后续扩展

保留的阶段边界是 `normalized_items.json`：

- 后续新增 `core/router.py`，读取 `normalized_items.json`，输出 `ranked_items.json`。
- 后续新增 `core/light_ai_judge.py`，只处理 router 选出的少量候选，输出 `ai_decisions.json`。
- 后续新增 `core/script_writer.py`，读取 `ai_decisions.json` 与 `normalized_items.json`，再输出 `script_inputs.json` 和口播稿。
- 后续可继续新增抖音、快手、B 站、视频号 crawler，以及 ASR、OCR、客资分发模块。

这些扩展当前都没有实现。当前阶段没有 AI 判断、router、口播、Hermes 或云端部署逻辑。

## 抖音接入

抖音链路通过 `tools/douyin_mediacrawler_bridge.py` 调用本地 `../external-tools/MediaCrawler`。主流程仍然只接收 raw JSON，再交给 `adapters/douyin_adapter.py` 统一成 `normalized_items.json`。

```yaml
- id: dy_keyword_veteran
  name: 抖音关键词-退役军人
  type: douyin
  enabled: true
  fetch_mode: mediacrawler
  douyin_python: ../envs/media-douyin/Scripts/python.exe
  mediacrawler_dir: ../external-tools/MediaCrawler
  mode: keyword_search
  keyword: 退役军人
  publish_time: one_day
  limit: 10
  login_type: qrcode
  headless: false
  enable_cdp: true
  fetch_comments: false
  download_video: false
```

抖音输出沿用统一 schema：视频文案进入 `content_text`，后续 ASR/OCR 文本也追加进 `content_text`；封面、视频下载地址、音频地址、视频 ID 等放进 `media.videos[0]`；原始 MediaCrawler 结果保留在 `raw.mediacrawler_raw`。当前阶段不做视频理解、不调大模型、不生成口播稿。

抖音真实抓取需要登录时会打开浏览器二维码。扫码完成后，登录状态由 MediaCrawler 保存在外部工具目录的 `browser_data` 下；后续同一环境可复用。MediaCrawler 仓库声明为非商业学习用途，正式使用前需要自行确认平台规则和授权边界。
