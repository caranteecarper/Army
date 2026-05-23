# 老板即开即用说明

解压后请保持目录结构不变：

```text
ArmyBossPackage/
├── envs/
├── external-tools/
└── media-intel-local/
```

进入 `media-intel-local` 后可直接双击：

```text
start_daily.bat     每日采集，默认抓昨天
login_wewe.bat      公众号第一次使用或登录失效时扫码
rebuild_inbox.bat   从已有 normalized_items.json 重建热点 inbox
run_tests.bat       环境自检
```

日常只需要改：

```text
media-intel-local/config/client_sources.yaml
```

填法尽量只填一个 ID 或链接：

```yaml
websites:
  - https://mil.huanqiu.com/

wechat:
  - link: https://mp.weixin.qq.com/s/公众号文章分享链接

xhs:
  - user_id: 小红书用户ID

douyin:
  - user_id: 抖音sec_user_id或主页链接
```

输出位置：

```text
media-intel-local/output/YYYY-MM-DD/
media-intel-local/data/inbox/
```

注意：

- 当前版本不调用大模型，不做内容价值判断，不生成口播稿。
- 公众号、小红书、抖音第一次真实抓取可能需要扫码或登录。
- 登录态、cookie、历史输出没有默认打包进交付包，需要在老板电脑上首次登录生成。
