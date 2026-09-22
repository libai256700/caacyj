# 目标电脑部署

## 前置条件

- OpenClaw 工作区，默认 `~/.openclaw/workspace`
- Python 3.9 或更高版本；爬虫 Python 代码只使用标准库
- `agent-browser` 0.27.0
- `@larksuite/cli`（`lark-cli`）1.0.67
- macOS 仅在使用 launchd 看门狗时需要

目标电脑必须重新建立认证：

~~~bash
npm install -g agent-browser@0.27.0 @larksuite/cli@1.0.67
agent-browser install
lark-cli config init --new
lark-cli auth login --domain docs --domain drive --domain im
agent-browser --version
lark-cli --version
lark-cli auth status --json --verify
~~~

用 `agent-browser --session-name zhaopin open <URL>` 建立登录态，并分别确认四个招聘网站可访问。不要复制 `.agent-browser`、`.lark-cli`、`Application Support/lark-cli` 或 OpenClaw 密钥文件。

## 安装技能

在仓库根目录运行：

~~~bash
bash skills/recruitment-crawler/scripts/install.sh
~~~

自定义 OpenClaw 工作区：

~~~bash
bash skills/recruitment-crawler/scripts/install.sh \
  --workspace /absolute/path/to/openclaw/workspace
~~~

安装器会：

- 把完整技能放入工作区的 `skills/recruitment-crawler`
- 首次创建 `projects/recruitment-crawler/config.json`
- 将配置权限设为 `0600`
- 在目标已有不同技能文件时失败关闭；确认更新后用 `--force`
- `--force` 先把旧技能移入安装器打印的工作区外私有回滚目录，再分阶段替换整个技能目录，旧的多余文件不会混入新版本；更新时避开定时任务运行窗口
- 永不覆盖已有 `config.json`

## 配置

编辑 `projects/recruitment-crawler/config.json`：

- `agent_browser`：可写命令名 `agent-browser` 或绝对路径。脚本也会搜索 PATH 和备用路径。
- `report_dir`、`snapshot_dir`：默认指向 OpenClaw 工作区；自定义工作区时一并修改。爬虫和看门狗读取同一 `report_dir`。
- `folder_token`：飞书日报目标文件夹 token。
- `chat_id`：接收日报和失败提醒的飞书群。
- `lark_cli`：命令名或绝对路径；爬虫、runner 失败通知和看门狗共同使用。
- `staff`：每项为 `[member_type, member_id, perm, display_name]`。常用 `member_type` 为 `openid` 或 `userid`，`member_id` 必须与类型匹配，`perm` 可为 `view`、`edit` 或 `full_access`。至少配置一项 `openid` + `full_access`（例如 `["openid", "ou_replace_me", "full_access", "维护者"]`），用于文档授权和看门狗私信。
- `keywords`、`platforms`：采集范围。
- `max_pages_per_query`、`pagination_pause_seconds`：分页上限和节流。
- `quality_thresholds`、`max_failed_combination_rate`：发布质量门禁。

不要把真实配置放回仓库。空 `folder_token`、`chat_id` 或 `staff` 会让正式发布快速失败；`--dry-run` 不需要飞书目标。

## 验收

在已安装技能目录运行：

~~~bash
cd ~/.openclaw/workspace/skills/recruitment-crawler
bash scripts/verify.sh

# 联网但不发布
python3 scripts/daily_job_crawler.py --dry-run

# 确认配置、登录态和 dry-run 后再执行一次正式任务
bash scripts/run_daily.sh
~~~

验收正式任务时检查：

- runner 退出码为 0
- 状态文件 `~/.openclaw/tmp/cron-detached/daily-job-crawler.json` 中 `job_status=ok`
- 发布收据包含文档 ID、文档 URL 和群消息 `message_id`
- 签名与成功历史只在群消息回执后写入
- 飞书目标文件夹和群聊确实收到本次日报

## 创建 OpenClaw 定时任务

不要复制旧电脑的 SQLite、旧 job ID 或整个 OpenClaw 状态目录。使用目标电脑的 CLI 重建：

~~~bash
CRAWLER_WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"

openclaw cron add \
  --name "每日招聘岗位爬虫-9:00" \
  --display-name "每日招聘岗位爬虫-9:00" \
  --description "无人机/CAAC 四平台岗位采集与飞书日报" \
  --declaration-key "recruitment-crawler-daily" \
  --cron "0 9 * * *" \
  --tz "Asia/Kuala_Lumpur" \
  --exact \
  --session isolated \
  --timeout-seconds 1980 \
  --no-deliver \
  --command-cwd "$CRAWLER_WORKSPACE" \
  --command-argv "[\"bash\",\"$CRAWLER_WORKSPACE/skills/recruitment-crawler/scripts/run_daily.sh\"]"
~~~

创建后用 `openclaw cron list` 核对命令、时区、启用状态和超时，再做一次手动运行。调度器成功只证明命令返回；仍需核对 runner 和飞书发布收据。

## 安装独立看门狗

看门狗应在日报任务之后独立运行，避免主调度器自身故障时无人报警。macOS 示例：

~~~bash
CRAWLER_WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
PLIST="$HOME/Library/LaunchAgents/ai.openclaw.job-crawler-watchdog.plist"

python3 "$CRAWLER_WORKSPACE/skills/recruitment-crawler/scripts/render_launchd.py" \
  --workspace "$CRAWLER_WORKSPACE" \
  --output "$PLIST" \
  --hour 10 \
  --minute 0 \
  --timezone "Asia/Kuala_Lumpur"

plutil -lint "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/ai.openclaw.job-crawler-watchdog"
~~~

模板不设置 `RunAtLoad` 或 `KeepAlive`。`StartCalendarInterval` 始终按目标 Mac 的系统时区触发；`--timezone` 只设置看门狗进程的日期与日志时区，不会改变 launchd 的触发时区。目标 Mac 不是 `Asia/Kuala_Lumpur` 时，应把 `--hour` 换算为目标机器的本地钟点，并留意夏令时，或先统一系统时区。若更新已有服务，先按本机 launchctl 状态选择 `bootout`/`bootstrap`；不要同时创建另一个 OpenClaw watchdog cron。

## 不迁移的数据

以下内容不得进 Git：真实配置、浏览器 Cookie/localStorage、飞书认证、OpenClaw 密钥、岗位签名、历史 JSONL、发布收据、HTML 快照、日志和 runner 状态。

生产切机需要延续“新增/持续在招”判定时，只单独加密迁移 `job_signatures.json` 及其校验通过的备份。先停旧机调度、核对文件权限和 JSON 结构，再在新机首次正式运行前放入报告目录。
