---
name: recruitment-crawler
description: 采集和维护无人机、CAAC、低空经济、eVTOL 与无人机教员招聘岗位，支持猎聘、前程无忧、国聘和智联招聘的分页抓取、相关性过滤、跨平台去重、质量分层、飞书日报幂等发布、缺跑监控及解析漂移排障。用于用户要求迁移或运行无人机岗位爬虫、生成每日招聘岗位日报、检查岗位采集质量、回放招聘页面快照、配置 OpenClaw 定时任务，或排查 recruitment crawler 时；不负责 BOSS/猎聘候选人打招呼。
---

# 无人机岗位爬取

使用技能内的现役解析核心采集四个平台的无人机和低空经济岗位。先保全页面证据，再判断真实空结果、抓取失败或解析漂移；没有可信结果页时禁止生成“0 岗位成功日报”。

## 首次安装

1. 在技能目录运行 `bash scripts/install.sh`。默认安装到 `~/.openclaw/workspace/skills/recruitment-crawler`，已有不同版本时必须显式加 `--force`；现有运行配置永不覆盖。
2. 编辑 `~/.openclaw/workspace/projects/recruitment-crawler/config.json`。必须自行填写飞书 `folder_token`、`chat_id` 和至少一名 `full_access` 成员；禁止把真实配置提交到 Git。
3. 安装 Python 3、`agent-browser` 和 `lark-cli`。在目标电脑重新执行 `agent-browser install`、建立浏览器登录态并完成 `lark-cli` 授权；不得复制其他电脑的 Cookie 或凭据目录。
4. 运行 `bash scripts/verify.sh` 做完全离线验证。部署、OpenClaw cron 和 macOS 看门狗步骤见 [deployment.md](references/deployment.md)。

## 执行方式

以下命令均以技能目录为当前目录：

~~~bash
# 完全离线：语法、解析、去重、发布事务、监控与安装回归
bash scripts/verify.sh

# 回放本地 HTML 快照；不会联网、发布或写签名
RECRUITMENT_CRAWLER_CONFIG=/path/to/config.json \
  python3 scripts/daily_job_crawler.py --replay /path/to/snapshot.html [平台] [关键词]

# 真实访问招聘网站，但不写签名、不创建飞书文档、不发消息
RECRUITMENT_CRAWLER_CONFIG=/path/to/config.json \
  python3 scripts/daily_job_crawler.py --dry-run

# 安装后执行正式任务；取得当天成功回执后，同日重跑会幂等跳过
bash ~/.openclaw/workspace/skills/recruitment-crawler/scripts/run_daily.sh
~~~

仅在用户明确要求人工重发并接受重复建档/发消息风险时运行 `run_daily.sh --force`。定时任务不得带 `--force`。

## 维护工作流

1. 先读最新 runner 状态、发布收据和日志，再判断是未触发、超时、浏览器失败、发布失败还是解析质量下降。
2. 再核对实际安装脚本和本机配置。配置项只能放在 `config.json`，不要硬编码进 Python 或启动器。
3. 解析异常时先回放 `reports/job_crawler_snapshots/` 中的真实 HTML；不要凭网站印象改选择器。
4. 修改后依次运行 `verify.sh`、受影响快照的 `--replay`，必要时再运行 `--dry-run`。只有用户要求真实交付时才执行正式任务。
5. 对比修改前后的岗位数及链接、公司、薪资、地点覆盖率；下一次定时运行与完整发布回执才是线上确认。

平台选择器、相关性、去重、质量和发布事务的维护约束见 [parser-governance.md](references/parser-governance.md)。

## 不可破坏的边界

- 将浏览器/网络失败记为失败组合，不得伪装为合法零结果；任一平台全部关键词失败或失败比例越界时拒绝发布。
- 同公司、归一化标题和城市才允许文本跨平台合并；公司缺失时使用更窄的“平台+标题+城市+薪资”键。
- 非法地点或薪资只进入脱敏质量样本，不得进入岗位列表、签名、日报或通知。
- 只有飞书群消息返回明确 `message_id` 后才能落签名和成功历史。建档超时等模糊失败禁止自动重试。
- 配置、浏览器会话、`lark-cli` 凭据、签名、历史、发布收据、快照、日志和状态均为本机数据，不属于技能包。
- 生产切机若需保持去重连续性，只能把签名库单独加密传输并人工校验，不得放入 Git。
- 看门狗只检测并通知，不自动修复。不要同时启用 launchd 看门狗和旧的 OpenClaw watchdog cron。
- 候选人自动打招呼是独立流程，不得并入本技能。

## 资源

- `scripts/daily_job_crawler.py`：四平台采集、解析、相关性、去重、质量分析和飞书发布。
- `scripts/cron_detached_runner.py`：互斥运行、超时、私有日志、状态收据及失败通知。
- `scripts/run_daily.sh`：只包含本技能的便携调度入口。
- `scripts/job_crawler_watchdog.py`：缺跑、交付收据和连续解析告警检查。
- `scripts/install.sh`：幂等安装技能与空白配置，保留本机配置。
- `scripts/render_launchd.py`：渲染不含凭据的 macOS 看门狗 LaunchAgent。
- `scripts/verify.sh`：完全离线的迁移验收。
- `assets/config.example.json`：无凭据配置模板。
- `assets/ai.openclaw.job-crawler-watchdog.plist.template`：参数化 launchd 模板。
