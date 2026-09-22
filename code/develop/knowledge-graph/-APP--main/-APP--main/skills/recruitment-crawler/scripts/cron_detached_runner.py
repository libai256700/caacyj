#!/usr/bin/env python3
"""Synchronously supervise OpenClaw cron commands with private receipts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


NOTIFICATION_FAILURE_EXIT_CODE = 70


_DOC_URL_RE = re.compile(
    r"https?://[^\s<>()\]]+/(?:docx|docs?|wiki|sheets?|base|file)/(?:[^\s<>()\]]+)",
    re.IGNORECASE,
)
_LARK_URL_RE = re.compile(
    r"https?://[^\s<>()\]]*(?:feishu\.cn|larksuite\.com|larkoffice\.com)[^\s<>()\]]*",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_RE = re.compile(
    r"(?i)(--(?:[a-z0-9-]*(?:token|secret|password|api-key|open-id|chat-id|user-id|member-id|"
    r"message-id|document-id|doc-id|docx-id|file-id|folder-id)"
    r"[a-z0-9-]*))"
    r"(?:=|\s+)\S+"
)
_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)([\"']?(?:[a-z0-9_-]*(?:token|secret|password|api_?key|open_?id|chat_?id|user_?id|"
    r"member_?id|message_?id|document_?id|docx?_?id|file_?id|folder_?id)"
    r"[a-z0-9_-]*)[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}\[\]]+)"
)
_LARK_ID_RE = re.compile(r"\b(?:ou|oc|om|on|cli)_[A-Za-z0-9_-]+\b")


def redact_sensitive(value: object) -> str:
    """Redact document locations and Lark identifier/token-like values."""
    text = str(value or "")
    text = _LARK_URL_RE.sub("[REDACTED_LARK_URL]", text)
    text = _DOC_URL_RE.sub("[REDACTED_DOC_URL]", text)
    text = _SENSITIVE_FLAG_RE.sub(lambda match: f"{match.group(1)} [REDACTED]", text)
    text = _SENSITIVE_FIELD_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    return _LARK_ID_RE.sub("[REDACTED_LARK_ID]", text)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def write_private_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", opener=_private_opener) as handle:
        handle.write(text)
    path.chmod(0o600)


def _private_opener(path: str, flags: int) -> int:
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    return fd


def open_private_log(path: Path, mode: str):
    handle = open(path, mode, encoding="utf-8", errors="replace", opener=_private_opener)
    path.chmod(0o600)
    return handle


def runner_exit_code(child_exit_code: int) -> int:
    """Map signal-style negative child codes to a shell-visible exit status."""
    if child_exit_code < 0:
        return 128 + abs(child_exit_code)
    return child_exit_code


def final_runner_exit_code(child_exit_code: int, notification_status: str) -> int:
    """Return a non-zero runner code when a successful job lacks its required notification."""
    code = runner_exit_code(child_exit_code)
    if child_exit_code == 0 and notification_status == "failed":
        return NOTIFICATION_FAILURE_EXIT_CODE
    return code


class _Terminated(Exception):
    """SIGTERM/SIGINT 转异常，保证 finally（锁清理/状态落盘）一定执行。"""

    def __init__(self, signum):
        self.signum = signum
        super().__init__(f"terminated by signal {signum}")


def _install_signal_handlers():
    def _on_term(signum, frame):
        raise _Terminated(signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_term)
        except (ValueError, OSError):
            pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _kill_process_group(proc, log):
    """先 TERM 后 KILL 整个进程组，防止 agent-browser 拉起的 Chromium 变孤儿。"""
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        pgid = None
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGTERM)
        else:
            proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGKILL)
            else:
                proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log.write(f"{now_local()} WARN: child did not exit after SIGKILL\n")


DEFAULT_LOG_DIR = Path.home() / ".openclaw" / "logs" / "cron-detached"
DEFAULT_STATE_DIR = Path.home() / ".openclaw" / "tmp" / "cron-detached"


def now_local() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def slug(value: str) -> str:
    safe = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_"):
            safe.append(ch)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or "cron-job"


def tail_text(path: Path, max_lines: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    return "\n".join(lines[-max_lines:]).strip()


def find_message_id(value: object) -> str:
    """Recursively extract a Lark message receipt from a JSON response."""
    if isinstance(value, dict):
        for key in ("message_id", "messageId"):
            if value.get(key):
                return str(value[key])
        for child in value.values():
            message_id = find_message_id(child)
            if message_id:
                return message_id
    elif isinstance(value, list):
        for child in value:
            message_id = find_message_id(child)
            if message_id:
                return message_id
    return ""


def validate_lark_send_receipt(stdout: str) -> str:
    """Require an explicit service success and message receipt."""
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("notification response is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError("notification service did not return ok=true")
    message_id = find_message_id(payload)
    if not message_id:
        raise RuntimeError("notification response is missing message_id")
    return message_id


def send_lark(args: argparse.Namespace, text: str, run_fn=subprocess.run) -> str:
    if not args.chat_id and not args.user_id:
        raise RuntimeError("notification recipient missing")
    lark_cli = shutil.which(args.lark_cli)
    if not lark_cli:
        raise RuntimeError("lark-cli not found")

    cmd = [lark_cli, "im", "+messages-send"]
    if args.chat_id:
        cmd.extend(["--chat-id", args.chat_id])
    else:
        cmd.extend(["--user-id", args.user_id])
    cmd.extend(["--text", text])
    result = run_fn(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"notification command failed with exit code {result.returncode}")
    return validate_lark_send_receipt(result.stdout)


def write_status(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        write_private_text(tmp, json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(path)
        path.chmod(0o600)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def build_message(args: argparse.Namespace, status: str, rc: int, elapsed: int, log_path: Path) -> str:
    tail = tail_text(log_path, args.summary_lines)
    title = "完成" if status == "ok" else "失败"
    header = f"{'✅' if status == 'ok' else '❌'} {args.name} {title}"
    body = [
        header,
        f"状态: {status}",
        f"退出码: {rc}",
        f"耗时: {elapsed}s",
        f"日志: {log_path}",
    ]
    if tail:
        body.append("")
        body.append("最近输出:")
        body.append(redact_sensitive(tail)[-args.summary_chars :])
    return redact_sensitive("\n".join(body))


def main() -> int:
    os.umask(0o077)
    _install_signal_handlers()
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-key", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--cwd", default=str(Path.home() / ".openclaw" / "workspace"))
    parser.add_argument("--chat-id")
    parser.add_argument("--user-id")
    parser.add_argument("--lark-cli", default=os.environ.get("LARK_CLI", "lark-cli"))
    parser.add_argument("--notify", choices=["all", "success", "failure", "none"], default="all")
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--summary-lines", type=int, default=60)
    parser.add_argument("--summary-chars", type=int, default=3500)
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("missing command", file=sys.stderr)
        return 2

    job_key = slug(args.job_key)
    log_dir = Path(args.log_dir).expanduser()
    state_dir = Path(args.state_dir).expanduser()
    ensure_private_dir(log_dir)
    ensure_private_dir(state_dir)

    lock_dir = state_dir / f"{job_key}.lock"
    status_path = state_dir / f"{job_key}.json"
    lock_pid_file = lock_dir / "pid"
    try:
        lock_dir.mkdir(mode=0o700)
        lock_dir.chmod(0o700)
    except FileExistsError:
        lock_dir.chmod(0o700)
        # 锁已存在：检查持锁进程是否还活着，死锁（强杀/断电残留）自动接管
        holder_pid = None
        try:
            holder_pid = int(lock_pid_file.read_text().strip())
        except (OSError, ValueError):
            pass
        if holder_pid is not None and _pid_alive(holder_pid):
            msg = f"{now_local()} {args.name}: another detached run is active (pid {holder_pid}); skip duplicate"
            print(msg)
            # 不覆写上次完整运行记录，只追加 skip 痕迹
            try:
                prev = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                prev = {"job_key": job_key, "name": args.name}
            prev.setdefault("child_exit_code", prev.get("exit_code"))
            prev.setdefault("job_status", prev.get("status", "unknown"))
            prev.setdefault("notification_status", "unknown")
            prev.setdefault("runner_exit_code", prev.get("exit_code"))
            prev["last_skip_at"] = now_local()
            prev["last_skip_reason"] = f"duplicate; holder pid {holder_pid}"
            write_status(status_path, prev)
            return 0
        # 持锁进程已死或无PID记录 → 残留锁，接管
        print(f"{now_local()} {args.name}: stale lock detected (holder pid {holder_pid}), taking over")
        try:
            if lock_pid_file.exists():
                lock_pid_file.unlink()
            lock_dir.rmdir()
        except OSError as exc:
            print(f"{now_local()} {args.name}: failed to clear stale lock: {exc}", file=sys.stderr)
            return 1
        lock_dir.mkdir(mode=0o700)
        lock_dir.chmod(0o700)
    try:
        write_private_text(lock_pid_file, str(os.getpid()))
    except OSError:
        pass

    started = time.time()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"{job_key}-{stamp}.log"

    status = {
        "job_key": job_key,
        "name": args.name,
        "status": "running",
        "exit_code": None,
        "child_exit_code": None,
        "job_status": "running",
        "notification_status": "not_evaluated",
        "runner_exit_code": None,
        "started_at": now_local(),
        "pid": os.getpid(),
        "cwd": args.cwd,
        "command": command,
        "log_path": str(log_path),
    }
    write_status(status_path, status)

    child_rc = 1
    job_status = "error"
    proc = None
    try:
        with open_private_log(log_path, "w") as log:
            log.write(f"{now_local()} START {args.name}\n")
            log.write(f"cwd: {args.cwd}\n")
            log.write(f"command: {' '.join(command)}\n\n")
            log.flush()

            proc = subprocess.Popen(
                command,
                cwd=args.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,  # 独立进程组：超时/终止时可整组击杀，防浏览器孤儿
            )
            status["child_pid"] = proc.pid
            write_status(status_path, status)

            deadline = started + args.timeout_seconds if args.timeout_seconds > 0 else None
            assert proc.stdout is not None
            _loop_terminated = None
            try:
                while True:
                    # deadline 先于读取检查：话痨卡死子进程会让每轮 select 都 readable→
                    # continue，若只在末尾判 deadline 则永不触发(饿死)，故提到循环首。
                    if deadline and time.time() > deadline:
                        log.write(f"\n{now_local()} TIMEOUT after {args.timeout_seconds}s; killing process group\n")
                        _kill_process_group(proc, log)
                        child_rc = 124
                        break
                    readable, _, _ = select.select([proc.stdout], [], [], 0.5)
                    if readable:
                        line = proc.stdout.readline()
                        if line:
                            log.write(line)
                            log.flush()
                            continue
                    if proc.poll() is not None:
                        for line in proc.stdout:
                            log.write(line)
                        log.flush()
                        break
                    if deadline and time.time() > deadline:
                        log.write(f"\n{now_local()} TIMEOUT after {args.timeout_seconds}s; killing process group\n")
                        _kill_process_group(proc, log)
                        child_rc = 124
                        break
                    else:
                        time.sleep(0.5)
            except _Terminated as term:
                # 信号可能落在循环内任意位置（select/sleep/写日志），循环级统一处理
                log.write(f"\n{now_local()} runner received signal {term.signum}; killing process group\n")
                _kill_process_group(proc, log)
                child_rc = 128 + int(term.signum)
                _loop_terminated = term

            if child_rc != 124 and _loop_terminated is None:
                try:
                    child_rc = proc.wait()
                except _Terminated as term:
                    log.write(f"\n{now_local()} runner received signal {term.signum}; killing process group\n")
                    _kill_process_group(proc, log)
                    child_rc = 128 + int(term.signum)

            elapsed = int(time.time() - started)
            job_status = "ok" if child_rc == 0 else "error"
            log.write(
                f"\n{now_local()} CHILD_END job_status={job_status} "
                f"child_exit_code={child_rc} elapsed={elapsed}s\n"
            )
            log.flush()

        status.update(
            {
                "child_exit_code": child_rc,
                "job_status": job_status,
                "elapsed_seconds": int(time.time() - started),
            }
        )

        should_notify = (
            args.notify == "all"
            or (args.notify == "success" and job_status == "ok")
            or (args.notify == "failure" and job_status != "ok")
        )
        notification_status = "not_requested"
        notification_error = ""
        if should_notify:
            notification_status = "pending"
            status["notification_status"] = notification_status
            write_status(status_path, status)
            message = build_message(args, job_status, child_rc, status["elapsed_seconds"], log_path)
            try:
                send_lark(args, message)
                notification_status = "sent"
                with open_private_log(log_path, "a") as log:
                    log.write(f"\n{now_local()} notification sent\n")
            except Exception as exc:  # noqa: BLE001 - result is recorded below
                notification_status = "failed"
                notification_error = redact_sensitive(exc)
                with open_private_log(log_path, "a") as log:
                    log.write(f"\n{now_local()} notification failed: {notification_error}\n")

        runner_rc = final_runner_exit_code(child_rc, notification_status)
        runner_status = "ok" if runner_rc == 0 else "error"
        status.update(
            {
                # Legacy fields remain for existing watchdog readers.
                "status": runner_status,
                "exit_code": runner_rc,
                "child_exit_code": child_rc,
                "job_status": job_status,
                "notification_status": notification_status,
                "runner_exit_code": runner_rc,
                "elapsed_seconds": int(time.time() - started),
                "finished_at": now_local(),
            }
        )
        if notification_error:
            status["notification_error"] = notification_error
        else:
            status.pop("notification_error", None)
        write_status(status_path, status)

        receipt = {
            "job_key": job_key,
            "child_exit_code": child_rc,
            "job_status": job_status,
            "notification_status": notification_status,
            "runner_exit_code": runner_rc,
        }
        with open_private_log(log_path, "a") as log:
            log.write(f"{now_local()} FINAL_RECEIPT {json.dumps(receipt, ensure_ascii=False)}\n")

        return runner_rc
    except _Terminated as term:
        runner_rc = 128 + int(term.signum)
        runner_error = redact_sensitive(term)
        try:
            with open_private_log(log_path, "a") as log:
                if proc is not None and proc.poll() is None:
                    _kill_process_group(proc, log)
                log.write(f"{now_local()} RUNNER_ERROR {runner_error}\n")
        except OSError:
            pass
        if proc is not None and proc.returncode not in (None, 0):
            child_rc = proc.returncode
        terminal_job_status = "not_started" if proc is None else ("ok" if child_rc == 0 else "error")
        status.update(
            {
                "status": "error",
                "exit_code": runner_rc,
                "child_exit_code": child_rc if proc is not None else None,
                "job_status": terminal_job_status,
                "notification_status": "not_attempted_runner_error",
                "runner_exit_code": runner_rc,
                "elapsed_seconds": int(time.time() - started),
                "finished_at": now_local(),
                "runner_error": runner_error,
            }
        )
        write_status(status_path, status)
        print(f"{now_local()} runner terminated: {runner_error}", file=sys.stderr)
        return runner_rc
    except Exception as exc:  # noqa: BLE001 - always leave a terminal receipt
        runner_error = redact_sensitive(f"{type(exc).__name__}: {exc}")
        try:
            with open_private_log(log_path, "a") as log:
                if proc is not None and proc.poll() is None:
                    _kill_process_group(proc, log)
                log.write(f"{now_local()} RUNNER_ERROR {runner_error}\n")
        except OSError:
            pass
        if proc is not None and proc.returncode not in (None, 0):
            child_rc = proc.returncode
        terminal_job_status = "not_started" if proc is None else ("ok" if child_rc == 0 else "error")
        runner_rc = runner_exit_code(child_rc) if child_rc != 0 else 1
        status.update(
            {
                "status": "error",
                "exit_code": runner_rc,
                "child_exit_code": child_rc if proc is not None else None,
                "job_status": terminal_job_status,
                "notification_status": "not_attempted_runner_error",
                "runner_exit_code": runner_rc,
                "elapsed_seconds": int(time.time() - started),
                "finished_at": now_local(),
                "runner_error": runner_error,
            }
        )
        write_status(status_path, status)
        print(f"{now_local()} runner error: {runner_error}", file=sys.stderr)
        return runner_rc
    finally:
        try:
            if lock_pid_file.exists():
                lock_pid_file.unlink()
            lock_dir.rmdir()
        except OSError:
            pass


def self_test() -> int:
    """Offline notification-receipt and runner-exit contract checks."""
    valid = json.dumps({"ok": True, "data": {"message_id": "om_test"}})
    if validate_lark_send_receipt(valid) != "om_test":
        raise AssertionError("nested message_id should be accepted")

    invalid_payloads = (
        json.dumps({"ok": False, "data": {"message_id": "om_test"}}),
        json.dumps({"ok": True, "data": {}}),
        "not-json",
    )
    for payload in invalid_payloads:
        try:
            validate_lark_send_receipt(payload)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"invalid notification receipt was accepted: {payload!r}")

    if final_runner_exit_code(0, "failed") != NOTIFICATION_FAILURE_EXIT_CODE:
        raise AssertionError("successful child with failed notification must return 70")
    if final_runner_exit_code(0, "sent") != 0:
        raise AssertionError("successful child with confirmed notification must remain successful")
    if final_runner_exit_code(9, "failed") != 9:
        raise AssertionError("child failure must remain the primary runner exit code")
    notification_args = argparse.Namespace(
        chat_id="oc_test",
        user_id=None,
        lark_cli=sys.executable,
    )
    captured = []
    message_id = send_lark(
        notification_args,
        "offline",
        run_fn=lambda cmd, **_kwargs: (
            captured.append(cmd)
            or subprocess.CompletedProcess(cmd, 0, stdout=valid, stderr="")
        ),
    )
    if message_id != "om_test" or not captured or captured[0][0] != sys.executable:
        raise AssertionError("configured lark-cli was not used for notifications")
    print("SELF_TEST ok (notification receipt + layered exit codes)")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(main())
