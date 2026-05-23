# media-intel-local

本项目是本地媒体内容采集与格式化管道。当前阶段只做 crawler 接入、日期过滤、统一 schema、文本清洗、去重、日志输出；不做大模型判断、不做 router、不生成口播稿。

当前版本完全不消耗大模型 token。当前版本不进行内容价值判断。当前版本不生成口播稿。当前版本只负责把不同来源的数据统一成 `normalized_items.json`。后续 router 和 AI 轻判断只读取 `normalized_items.json`。

## 客户配置

客户只需要改 `config/client_sources.yaml`。这个文件尽量做到每个来源只填一个东西：

```yaml
websites:
  - https://mil.huanqiu.com/
  - https://mil.ifeng.com/
  - https://www.thepaper.cn/list_25430

xhs:
  - user_id: 小红书用户ID

douyin:
  - user_id: 抖音sec_user_id或主页链接

wechat:
  - link: https://mp.weixin.qq.com/s/公众号文章分享链接
```

运行时 `core/config_loader.py` 会自动把客户配置展开成完整 crawler 配置，包括工具路径、浏览器参数、抓取数量、日期窗口、正文补全、ASR 参数等。客户不需要理解 `source_registry.yaml`。

`config/source_registry.yaml` 仍然保留，作为工程调试配置。需要使用工程配置时：

```bash
python main.py --date 2026-05-23 --config config/source_registry.yaml
```

## 各平台输入规则

网站：客户填列表页 URL。系统会自动生成 source id、source name、文章 URL 过滤规则和 Crawl4AI 参数。当前已内置环球网军事、凤凰网军事、澎湃防务的解析规则；其他网站会用同域名链接作为默认文章候选。

小红书：跟踪账号时填 `user_id`。系统自动走 `xiaohongshu-skill` 的 `user_profile` 模式。关键词监控也支持填 `keyword`，例如：

```yaml
xhs:
  - keyword: 退役军人
```

抖音：跟踪账号时填 `user_id`，可以是 sec_user_id，也可以是主页链接。系统自动走 MediaCrawler 的 creator 模式，并保留 ASR 文本输出。关键词监控也支持填 `keyword`。

公众号：客户填一条 `https://mp.weixin.qq.com/s/...` 文章分享链接即可。系统会自动检查并启动本地 WeWe RSS 后端，调用 WeWe 的新增公众号源接口，把文章链接转换成 feed，再继续读取 `/feeds/{mpId}.rss`。已经有 WeWe feed 链接时也可以直接填 feed。

公众号第一次使用前需要有一个有效的微信读书登录账号。登录只需要扫码一次：

```bash
python tools/wewe_login.py
```

这个命令会自动启动 WeWe 后端、打开扫码 URL，并把登录 token 写入 WeWe 数据库。后续客户只需要填公众号文章链接。

## 运行方式

```bash
cd media-intel-local
pip install -r requirements.txt
python main.py --date yesterday
```

指定日期：

```bash
python main.py --date 2026-05-23
```

运行测试：

```bash
python tests/test_basic.py
```

## 输出文件

每次运行写入 `output/YYYY-MM-DD/`：

| 文件 | 说明 |
| --- | --- |
| `raw_items.json` | 日期过滤后的原始 crawler item，并补充来源 ID、来源名称、平台类型 |
| `normalized_items.json` | adapter 映射、清洗、去重后的统一 schema |
| `run_log.json` | 运行日期、成功失败源数量、数据条数、逐源错误 |

单个源失败会写入 `run_log.json.errors`，不会阻断其他源。配置文件本身无法读取时程序整体失败。

## 趋势与热点 Inbox

平台趋势和社会热点是另一条轻量 intake 链路，不和媒体正文 `normalized_items.json` 混在一起。客户或采集脚本先把原始信号写入：

```text
config/trend_hotspot_intake.yaml
```

然后运行：

```bash
python tools/trend_hotspot_intake.py --date today
```

输出到：

```text
data/inbox/platform_trends_YYYYMMDD.jsonl
data/inbox/social_hotspots_YYYYMMDD.jsonl
data/inbox/trend_hotspot_run_log_YYYYMMDD.json
```

这条链路只做字段标准化、极轻过滤和去重。它不会判断是否适合军旅教培，不生成 Idea Card、Topic Card 或脚本，也不调用 AI。

## 统一 Schema

所有平台最终都会输出为同一结构：

```json
{
  "item_id": "...",
  "source_type": "...",
  "source_id": "...",
  "source_name": "...",
  "platform": "...",
  "title": "...",
  "url": "...",
  "publish_time": "...",
  "crawl_time": "...",
  "content_text": "...",
  "content_excerpt": "...",
  "metrics": {},
  "media": {},
  "tags": [],
  "raw": {}
}
```

视频平台也不单独另起结构：文案、ASR 文本、OCR 文本都会进入 `content_text`，封面、视频地址、音频地址进入 `media`，原始结果保留在 `raw`。

## 外部工具

本项目主流程兼容 Python 3.8。部分真实 crawler 由外部环境执行：

- WeWe RSS：提供公众号 feed。
- `wechat-article-crawler`：补公众号正文。
- Crawl4AI：抓网站正文，禁用 LLM extraction。
- `xiaohongshu-skill`：抓小红书账号或关键词。
- MediaCrawler：抓抖音账号或关键词。
- `faster-whisper`：抖音视频 ASR，本地模型，不调用大模型 API。

这些工具默认放在 `../external-tools/`，Python 环境默认放在 `../envs/`。客户版配置不暴露这些路径，由 `core/config_loader.py` 自动补齐。

WeWe RSS 后端默认监听 `http://127.0.0.1:4000`。公众号 crawler 会在需要时自动启动它，不需要客户手动打开 localhost 页面。启动日志写入 `.runtime/wewe_rss/server.stdout.log` 和 `.runtime/wewe_rss/server.stderr.log`。

## 后续接口

后续新增模块应只读取当前阶段输出，不改 crawler 主流程：

- `core/router.py`：读取 `normalized_items.json`，输出 `ranked_items.json`。
- `core/light_ai_judge.py`：读取少量候选，输出 `ai_decisions.json`。
- `core/script_writer.py`：读取 AI 决策和 normalized 数据，输出 `script_inputs.json` 和口播稿。

还可以继续增加快手、B站、视频号、ASR、OCR、客资分发模块，但当前阶段不实现这些业务判断逻辑。
