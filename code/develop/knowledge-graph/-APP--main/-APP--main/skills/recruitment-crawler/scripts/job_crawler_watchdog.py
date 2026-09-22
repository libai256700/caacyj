#!/usr/bin/env python3
"""岗位爬虫看门狗：只检测+飞书提醒，绝不自动修复（2026-07-02 约定）。

每日 10:00 由独立 macOS LaunchAgent 触发（正班 09:00 跑完约 09:05-09:10）。检查三件事：
1. 今日正班是否真的跑了、跑完了（状态文件 + 进程活性，兜住 runner 中途死亡的静默模式）
2. 运行状态是否 ok
3. 质量告警是否出现"同一 平台/关键词/指标 连续≥3天"（Runbook 修复触发线），
   第 3/6/9... 天各提醒一次，避免看门狗自己变成告警疲劳源

发现问题 → 飞书私信配置中的 full_access 维护者；一切正常 → 静默退出。
"""

import datetime
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

OPENCLAW_HOME = os.path.expanduser(os.environ.get("OPENCLAW_HOME", "~/.openclaw"))
WORKSPACE = os.path.expanduser(
    os.environ.get("OPENCLAW_WORKSPACE", os.path.join(OPENCLAW_HOME, "workspace"))
)
REPORT_DIR = os.path.expanduser(
    os.environ.get("RECRUITMENT_CRAWLER_REPORT_DIR", os.path.join(WORKSPACE, "reports"))
)
STATE_FILE = os.path.expanduser(
    os.environ.get(
        "RECRUITMENT_CRAWLER_STATE_FILE",
        os.path.join(OPENCLAW_HOME, "tmp", "cron-detached", "daily-job-crawler.json"),
    )
)
HISTORY_FILE = os.path.join(REPORT_DIR, "job_crawler_history.jsonl")
CONFIG_FILE = os.path.expanduser(
    os.environ.get(
        "RECRUITMENT_CRAWLER_CONFIG",
        os.path.join(WORKSPACE, "projects", "recruitment-crawler", "config.json"),
    )
)
PUBLISH_RECEIPT_FILE = os.path.join(REPORT_DIR, "job_crawler_publish_state.json")
LOG_DIR = os.path.expanduser(
    os.environ.get(
        "RECRUITMENT_CRAWLER_LOG_DIR",
        os.path.join(OPENCLAW_HOME, "logs", "cron-detached"),
    )
)

# 信息型质量指标：无代码可修（平台真没某类岗），不进连续 3 天修复触发线，
# 仅在日报信息栏可见。真·解析故障（DOM变更抽不出标题）仍走 parsed_jobs，照常升级。
NON_ESCALATING_METRICS = {"no_relevant_jobs", "possible_truncation"}
DELIVERED_STATUSES = {"published", "delivered_degraded"}

EXIT_HEALTHY = 0
EXIT_ALERT_SENT = 10
EXIT_NOTIFY_FAILED = 11
EXIT_CONFIG_OR_READ_ERROR = 12


class WatchdogConfigError(Exception):
    """看门狗配置无法安全使用。"""


def redact_sensitive_text(value):
    """屏蔽飞书目标、文档标识和常见密钥字段。"""
    text = str(value or "")
    text = re.sub(
        r"(?i)\b(?:ou|oc|om|on|cli)_[A-Za-z0-9_-]+\b",
        "[REDACTED_ID]",
        text,
    )
    text = re.sub(
        r"(?i)(https?://[^\s\"']+/(?:docx|wiki|base|sheets)/)[A-Za-z0-9_-]+",
        r"\1[REDACTED]",
        text,
    )
    sensitive_keys = (
        "token",
        "open[_-]?id",
        "chat[_-]?id",
        "user[_-]?id",
        "message[_-]?id",
        "docx[_-]?id",
    )
    key_pattern = "|".join(sensitive_keys)
    text = re.sub(
        rf"(?i)([\"']?(?:{key_pattern})[\"']?\s*[:=]\s*)[\"'][^\"']*[\"']",
        r'\1"[REDACTED]"',
        text,
    )
    text = re.sub(
        rf"(?i)(\b(?:{key_pattern})\b\s*[:=]\s*)[^\s,;)}}]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(\bauthorization\s*[:=]\s*)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        text,
    )
    return text


def safe_error(error):
    return f"{type(error).__name__}: {redact_sensitive_text(error)}"


def load_watchdog_settings(config_file=CONFIG_FILE, environ=None):
    """从爬虫配置解析看门狗共用的报告目录和 lark-cli。"""
    env = os.environ if environ is None else environ
    try:
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        raise WatchdogConfigError(f"读取看门狗配置失败: {safe_error(e)}") from e
    if not isinstance(cfg, dict):
        raise WatchdogConfigError("看门狗配置顶层必须是对象")

    report_dir = env.get("RECRUITMENT_CRAWLER_REPORT_DIR") or cfg.get("report_dir")
    if not isinstance(report_dir, str) or not report_dir.strip():
        report_dir = os.path.join(WORKSPACE, "reports")
    report_dir = os.path.expanduser(os.path.expandvars(report_dir.strip()))

    lark_cli = env.get("LARK_CLI") or cfg.get("lark_cli") or "lark-cli"
    if not isinstance(lark_cli, str) or not lark_cli.strip():
        raise WatchdogConfigError("lark_cli 必须是非空字符串")
    lark_cli = os.path.expanduser(os.path.expandvars(lark_cli.strip()))
    return {"report_dir": report_dir, "lark_cli": lark_cli}


def load_owner_open_id(config_file=CONFIG_FILE):
    """从爬虫 config 的 staff 名单里取 full_access 成员作为提醒对象。"""
    try:
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
        for item in cfg.get("staff", []):
            if (
                isinstance(item, (list, tuple))
                and len(item) >= 3
                and item[0] == "openid"
                and item[2] == "full_access"
            ):
                open_id = str(item[1] or "").strip()
                if open_id:
                    return open_id
    except Exception as e:
        raise WatchdogConfigError(f"读取提醒配置失败: {safe_error(e)}") from e
    raise WatchdogConfigError("提醒配置缺少 openid 类型的 full_access 对象")


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def check_today_run(today_str, problems, read_errors, state_file=STATE_FILE):
    """检查今日正班运行状态。"""
    if not os.path.exists(state_file):
        problems.append("状态文件不存在，爬虫可能从未在本机运行")
        return
    try:
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        read_errors.append(f"状态文件读取失败: {safe_error(e)}")
        return
    if not isinstance(state, dict):
        read_errors.append("状态文件顶层不是对象")
        return

    started = str(state.get("started_at", "") or "")
    status = str(state.get("status", "") or "")
    skip_at = str(state.get("last_skip_at", "") or "")

    if not started.startswith(today_str):
        problems.append(
            redact_sensitive_text(
                f"今日正班未运行（最近一次 started_at={started or '无'}，"
                f"status={status}）——调度或开机状态需检查"
            )
        )
        return

    if status == "running":
        pid = state.get("pid")
        if pid and pid_alive(pid):
            elapsed_note = f"（pid {pid} 仍在运行）"
            problems.append(f"10:00 仍未跑完，正常约5-6分钟{elapsed_note}，疑似卡死或超时")
        else:
            problems.append(
                redact_sensitive_text(
                    f"状态停留在 running 但进程已死（pid {pid}）——"
                    f"运行中途被杀/断电，今日日报缺失，"
                    f"日志: {state.get('log_path', '')}"
                )
            )
        return

    if status != "ok":
        problems.append(
            redact_sensitive_text(
                f"今日运行状态={status} rc={state.get('exit_code')}，"
                f"日志: {state.get('log_path', '')}"
            )
        )
    if skip_at.startswith(today_str):
        problems.append(
            redact_sensitive_text(
                f"今日发生过重复启动跳过（{skip_at}: "
                f"{state.get('last_skip_reason', '')}）"
            )
        )


def load_history_entries(history_file, read_errors):
    if not os.path.exists(history_file):
        return []
    entries = []
    try:
        with open(history_file, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                entry = json.loads(line)
                if not isinstance(entry, dict) or not entry.get("date"):
                    raise ValueError(f"第{line_no}行缺少 date")
                entries.append(entry)
    except Exception as e:
        read_errors.append(f"历史文件读取失败: {safe_error(e)}")
        return []
    return entries


def load_today_receipt(today_str, receipt_file, read_errors):
    if not os.path.exists(receipt_file):
        return None
    try:
        with open(receipt_file, encoding="utf-8") as f:
            receipt = json.load(f)
    except Exception as e:
        read_errors.append(f"发布收据读取失败: {safe_error(e)}")
        return None
    if not isinstance(receipt, dict):
        read_errors.append("发布收据顶层不是对象")
        return None
    if receipt.get("date") != today_str:
        return None
    return receipt


def delivery_receipt_complete(entry):
    """published/delivered_degraded 且文档和群消息回执齐全才算交付。"""
    if not isinstance(entry, dict) or entry.get("status") not in DELIVERED_STATUSES:
        return False
    document_complete = bool(entry.get("docx_url") and entry.get("docx_id"))
    message_complete = bool(entry.get("message_id"))
    return document_complete and message_complete


def receipt_missing_fields(entry):
    missing = []
    if not entry.get("docx_url"):
        missing.append("docx_url")
    if not entry.get("docx_id"):
        missing.append("docx_id")
    if not entry.get("message_id"):
        missing.append("message_id")
    return missing


def check_history(
    today_str,
    problems,
    read_errors,
    history_file=HISTORY_FILE,
    receipt_file=PUBLISH_RECEIPT_FILE,
):
    """检查新发布收据、历史 JSONL 和告警连续天数。"""
    history_exists = os.path.exists(history_file)
    entries_list = load_history_entries(history_file, read_errors)
    receipt = load_today_receipt(today_str, receipt_file, read_errors)
    today_entries = [entry for entry in entries_list if entry.get("date") == today_str]
    today_entry = today_entries[-1] if today_entries else None

    receipt_complete = delivery_receipt_complete(receipt)
    history_complete = delivery_receipt_complete(today_entry)
    delivered = receipt_complete or history_complete

    if receipt is not None and not receipt_complete:
        status = redact_sensitive_text(receipt.get("status", "缺失"))
        if status in DELIVERED_STATUSES:
            missing = ", ".join(receipt_missing_fields(receipt)) or "未知字段"
            problems.append(f"今日发布收据状态={status}，但回执不完整（缺少 {missing}）")
        else:
            stage = redact_sensitive_text(receipt.get("stage", "未知"))
            detail = redact_sensitive_text(receipt.get("error", ""))[:200]
            suffix = f"，错误={detail}" if detail else ""
            problems.append(f"今日发布未收口（status={status}, stage={stage}{suffix}）")

    if today_entry is not None and not history_complete:
        status = redact_sensitive_text(today_entry.get("status", "缺失"))
        if status in DELIVERED_STATUSES:
            missing = ", ".join(receipt_missing_fields(today_entry)) or "未知字段"
            problems.append(f"今日历史记录状态={status}，但回执不完整（缺少 {missing}）")
        else:
            problems.append(f"今日历史记录不是有效交付状态（status={status}）")

    if not delivered:
        run_missing = any(p.startswith("今日正班未运行") or "running" in p for p in problems)
        if not run_missing:
            problems.append("今日无完整发布交付收据——文档或群消息回执缺失")
    else:
        delivered_entry = receipt if receipt_complete else today_entry
        if delivered_entry.get("status") == "delivered_degraded":
            stage = redact_sensitive_text(delivered_entry.get("stage", "未知"))
            detail = redact_sensitive_text(delivered_entry.get("error", ""))[:200]
            suffix = f"，原因={detail}" if detail else ""
            problems.append(f"今日日报已交付但后续处理降级（stage={stage}{suffix}）")

        if receipt_complete and not history_complete and receipt.get("status") == "published":
            problems.append("今日发布收据完整，但历史无完整交付记录")
        if history_complete and not receipt_complete:
            problems.append("今日历史显示已交付，但新发布收据缺失或不完整")

    if not history_exists:
        print("[INFO] 历史文件尚不存在，跳过趋势检查")

    # 趋势只使用已验证的终态交付记录，旧的 docx_url-only 行不再充当成功证据。
    entries = {
        entry["date"]: entry
        for entry in entries_list
        if delivery_receipt_complete(entry)
    }
    today_entry = entries.get(today_str)
    if today_entry is None:
        return

    # 告警连续性：同 (platform, keyword, metric) 连续≥3天，第3/6/9天提醒。
    # NON_ESCALATING_METRICS = 信息型事件，无代码可修（如"平台真没这类岗"），不进修复触发线，
    # 仅在日报信息栏可见。真解析失败仍用 parsed_jobs（照常升级）。
    today_keys = {
        (w.get("platform", ""), w.get("keyword", ""), w.get("metric", ""))
        for w in today_entry.get("warnings", [])
        if w.get("metric", "") not in NON_ESCALATING_METRICS
    }
    for key in sorted(today_keys):
        streak = 1
        day = datetime.date.fromisoformat(today_str)
        while True:
            day -= datetime.timedelta(days=1)
            prev = entries.get(day.isoformat())
            if prev is None:
                break
            prev_keys = {
                (w.get("platform", ""), w.get("keyword", ""), w.get("metric", ""))
                for w in prev.get("warnings", [])
                if w.get("metric", "") not in NON_ESCALATING_METRICS
            }
            if key not in prev_keys:
                break
            streak += 1
        if streak >= 3 and (streak - 3) % 3 == 0:
            platform, keyword, metric = key
            kw_part = f"/{keyword}" if keyword else ""
            problems.append(
                f"质量告警已连续 {streak} 天：{platform}{kw_part} {metric}"
                f"——达 Runbook 修复触发线，请进入人工修复会话"
            )


def find_message_id(value):
    """从 lark-cli JSON 响应中递归提取消息回执。"""
    if isinstance(value, dict):
        for key in ("message_id", "messageId"):
            if value.get(key):
                return str(value[key])
        for child in value.values():
            found = find_message_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_message_id(child)
            if found:
                return found
    return ""


def notify(open_id, text, run_fn=subprocess.run, lark_cli=None):
    """发送提醒并且只在拿到服务端消息回执时返回 True。"""
    lark_cli = lark_cli or os.environ.get("LARK_CLI", "lark-cli")
    cmd = [lark_cli, "im", "+messages-send", "--user-id", open_id, "--text", text]
    try:
        result = run_fn(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            detail = redact_sensitive_text(result.stderr or result.stdout)[:200]
            print(f"[WARN] 飞书发送失败(rc={result.returncode}): {detail}")
            return False
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            print("[WARN] 飞书发送响应不是有效 JSON，无法确认投递")
            return False
        if not isinstance(payload, dict) or payload.get("ok") is False:
            print(f"[WARN] 飞书服务端拒绝提醒: {redact_sensitive_text(result.stdout)[:200]}")
            return False
        message_id = find_message_id(payload)
        if not message_id:
            print("[WARN] 飞书发送命令成功但缺少 message_id，无法确认投递")
            return False
        print("[OK] 已发送飞书提醒并取得消息回执")
        return True
    except Exception as e:
        print(f"[WARN] 飞书发送异常: {safe_error(e)}")
        return False


def run_watchdog(
    *,
    dry_run=False,
    today_str=None,
    state_file=STATE_FILE,
    history_file=HISTORY_FILE,
    receipt_file=PUBLISH_RECEIPT_FILE,
    config_file=CONFIG_FILE,
    notify_fn=notify,
):
    today_str = today_str or datetime.date.today().isoformat()
    problems = []
    read_errors = []
    check_today_run(today_str, problems, read_errors, state_file=state_file)
    check_history(
        today_str,
        problems,
        read_errors,
        history_file=history_file,
        receipt_file=receipt_file,
    )

    if not problems and not read_errors:
        print(f"[OK] {today_str} 岗位爬虫运行正常，无连续告警")
        return EXIT_HEALTHY

    if read_errors:
        print(f"[ERROR] 发现 {len(read_errors)} 个配置/读取错误:")
        for error in read_errors:
            print(f"  - {redact_sensitive_text(error)}")
    print(f"[ALERT] 发现 {len(problems)} 个运行问题:")
    for p in problems:
        print(f"  - {redact_sensitive_text(p)}")

    if dry_run:
        print("[DRY-RUN] 跳过飞书发送")
        return EXIT_CONFIG_OR_READ_ERROR if read_errors else EXIT_ALERT_SENT

    try:
        open_id = load_owner_open_id(config_file=config_file)
    except WatchdogConfigError as e:
        print(f"[ERROR] {e}")
        return EXIT_CONFIG_OR_READ_ERROR

    alert_items = [redact_sensitive_text(item) for item in read_errors + problems]
    text = "岗位爬虫看门狗提醒（只通知不修复）:\n" + "\n".join(
        f"- {item}" for item in alert_items
    )
    text += "\n\n请按 recruitment-crawler SKILL.md Runbook 进入修复会话"
    notified = bool(notify_fn(open_id, text))
    if read_errors:
        return EXIT_CONFIG_OR_READ_ERROR
    return EXIT_ALERT_SENT if notified else EXIT_NOTIFY_FAILED


def self_test():
    """离线验证收据判断、退出码、脱敏和通知确认，不调用飞书。"""
    today_str = "2026-08-03"
    with tempfile.TemporaryDirectory(prefix="job-watchdog-selftest-") as tmp_dir:
        state_file = os.path.join(tmp_dir, "state.json")
        history_file = os.path.join(tmp_dir, "history.jsonl")
        receipt_file = os.path.join(tmp_dir, "receipt.json")
        config_file = os.path.join(tmp_dir, "config.json")
        state = {
            "started_at": f"{today_str} 09:00:00 MYT",
            "finished_at": f"{today_str} 09:05:00 MYT",
            "status": "ok",
            "exit_code": 0,
        }
        delivered = {
            "date": today_str,
            "status": "published",
            "docx_url": "https://example.test/docx/test",
            "docx_id": "doc_test",
            "message_id": "om_test",
            "warnings": [],
        }
        with open(state_file, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        with open(history_file, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(delivered, ensure_ascii=False) + "\n")
        with open(receipt_file, "w", encoding="utf-8") as handle:
            json.dump(delivered, handle)
        with open(config_file, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "report_dir": os.path.join(tmp_dir, "configured-reports"),
                    "lark_cli": os.path.join(tmp_dir, "bin", "lark-cli"),
                    "staff": [["openid", "ou_test", "full_access", "owner"]],
                },
                handle,
            )

        settings = load_watchdog_settings(config_file=config_file, environ={})
        if settings["report_dir"] != os.path.join(tmp_dir, "configured-reports"):
            raise AssertionError("看门狗未采用 config.report_dir")
        if settings["lark_cli"] != os.path.join(tmp_dir, "bin", "lark-cli"):
            raise AssertionError("看门狗未采用 config.lark_cli")

        common = {
            "today_str": today_str,
            "state_file": state_file,
            "history_file": history_file,
            "receipt_file": receipt_file,
            "config_file": config_file,
        }
        with contextlib.redirect_stdout(io.StringIO()):
            if run_watchdog(dry_run=True, **common) != EXIT_HEALTHY:
                raise AssertionError("完整收据和健康状态应返回 0")

            incomplete = dict(delivered, message_id="")
            with open(history_file, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(incomplete, ensure_ascii=False) + "\n")
            with open(receipt_file, "w", encoding="utf-8") as handle:
                json.dump(incomplete, handle)
            if run_watchdog(dry_run=True, **common) != EXIT_ALERT_SENT:
                raise AssertionError("published 缺少消息回执应返回 10")

            truncation_warning = [
                {
                    "platform": "example",
                    "keyword": "飞手",
                    "metric": "possible_truncation",
                }
            ]
            streak_entries = []
            for date_str in ("2026-08-01", "2026-08-02", today_str):
                streak_entries.append(
                    dict(
                        delivered,
                        date=date_str,
                        warnings=truncation_warning,
                    )
                )
            with open(history_file, "w", encoding="utf-8") as handle:
                for entry in streak_entries:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            with open(receipt_file, "w", encoding="utf-8") as handle:
                json.dump(delivered, handle)
            if run_watchdog(dry_run=True, **common) != EXIT_HEALTHY:
                raise AssertionError("possible_truncation 连续三天不应升级")

            with open(history_file, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(delivered, ensure_ascii=False) + "\n")
            degraded = dict(delivered, status="delivered_degraded", error="local finalize failed")
            with open(receipt_file, "w", encoding="utf-8") as handle:
                json.dump(degraded, handle)
            if run_watchdog(dry_run=True, **common) != EXIT_ALERT_SENT:
                raise AssertionError("dry-run 发现问题应返回 10")

            with open(history_file, "w", encoding="utf-8") as handle:
                handle.write("{broken-json")
            with open(receipt_file, "w", encoding="utf-8") as handle:
                json.dump(delivered, handle)
            if run_watchdog(dry_run=True, **common) != EXIT_CONFIG_OR_READ_ERROR:
                raise AssertionError("历史读取失败应返回 12")

            with open(history_file, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(delivered, ensure_ascii=False) + "\n")
            with open(receipt_file, "w", encoding="utf-8") as handle:
                handle.write("{broken-json")
            if run_watchdog(dry_run=True, **common) != EXIT_CONFIG_OR_READ_ERROR:
                raise AssertionError("发布收据读取失败应返回 12")

            with open(receipt_file, "w", encoding="utf-8") as handle:
                json.dump(delivered, handle)
            with open(state_file, "w", encoding="utf-8") as handle:
                handle.write("{broken-json")
            if run_watchdog(dry_run=True, **common) != EXIT_CONFIG_OR_READ_ERROR:
                raise AssertionError("状态读取失败应返回 12")
            if (
                run_watchdog(
                    notify_fn=lambda _open_id, _text: False,
                    **common,
                )
                != EXIT_CONFIG_OR_READ_ERROR
            ):
                raise AssertionError("读取错误应优先于通知失败返回 12")

            os.remove(state_file)
            os.remove(history_file)
            os.remove(receipt_file)
            if run_watchdog(notify_fn=lambda _open_id, _text: True, **common) != EXIT_ALERT_SENT:
                raise AssertionError("发现问题且通知成功应返回 10")
            if run_watchdog(notify_fn=lambda _open_id, _text: False, **common) != EXIT_NOTIFY_FAILED:
                raise AssertionError("通知失败应返回 11")

    if "possible_truncation" not in NON_ESCALATING_METRICS:
        raise AssertionError("possible_truncation 必须是非升级信息指标")
    secret = (
        "chat_id=oc_secret message_id=om_secret token=token-secret "
        "Authorization Bearer bearer-secret https://x.feishu.cn/docx/abc"
    )
    redacted = redact_sensitive_text(secret)
    for sensitive_value in (
        "oc_secret",
        "om_secret",
        "token-secret",
        "bearer-secret",
        "/docx/abc",
    ):
        if sensitive_value in redacted:
            raise AssertionError(f"脱敏失败: {sensitive_value}")

    success_result = subprocess.CompletedProcess(
        [],
        0,
        stdout=json.dumps({"ok": True, "data": {"message_id": "om_test"}}),
        stderr="",
    )
    failure_result = subprocess.CompletedProcess(
        [],
        1,
        stdout="",
        stderr="open_id=ou_leak token=failure-secret",
    )
    missing_receipt_result = subprocess.CompletedProcess(
        [],
        0,
        stdout=json.dumps({"ok": True}),
        stderr="",
    )
    notify_output = io.StringIO()
    with contextlib.redirect_stdout(notify_output):
        notify_results = (
            notify(
                "ou_test",
                "offline",
                run_fn=lambda *_args, **_kwargs: success_result,
            ),
            notify(
                "ou_test",
                "offline",
                run_fn=lambda *_args, **_kwargs: failure_result,
            ),
            notify(
                "ou_test",
                "offline",
                run_fn=lambda *_args, **_kwargs: missing_receipt_result,
            ),
            notify(
                "ou_test",
                "offline",
                run_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("token=exception-secret")
                ),
            ),
        )
    if notify_results != (True, False, False, False):
        raise AssertionError(f"notify 布尔返回不正确: {notify_results}")
    output_text = notify_output.getvalue()
    if "ou_leak" in output_text or "failure-secret" in output_text or "exception-secret" in output_text:
        raise AssertionError("notify 错误输出未完成脱敏")

    unknown_output = io.StringIO()
    with contextlib.redirect_stdout(unknown_output):
        if main(["--unknown=ou_secret"]) != EXIT_CONFIG_OR_READ_ERROR:
            raise AssertionError("未知参数应返回 12")
    if "ou_secret" in unknown_output.getvalue():
        raise AssertionError("未知参数输出未完成脱敏")
    print("SELF_TEST ok")
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    unknown = [arg for arg in args if arg not in {"--dry-run", "--self-test"}]
    if unknown:
        print(f"[ERROR] 未知参数: {', '.join(redact_sensitive_text(arg) for arg in unknown)}")
        return EXIT_CONFIG_OR_READ_ERROR
    if "--self-test" in args:
        return self_test()
    try:
        settings = load_watchdog_settings()
    except WatchdogConfigError as e:
        print(f"[ERROR] {e}")
        return EXIT_CONFIG_OR_READ_ERROR
    report_dir = settings["report_dir"]
    return run_watchdog(
        dry_run="--dry-run" in args,
        history_file=os.path.join(report_dir, "job_crawler_history.jsonl"),
        receipt_file=os.path.join(report_dir, "job_crawler_publish_state.json"),
        notify_fn=lambda open_id, text: notify(
            open_id,
            text,
            lark_cli=settings["lark_cli"],
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
