#!/usr/bin/env bash
# Complete offline verification for the portable skill.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERIFY_TMP="$(mktemp -d "${TMPDIR:-/tmp}/recruitment-crawler-verify.XXXXXX")"
trap 'rm -rf "$VERIFY_TMP"' EXIT

export PYTHONPYCACHEPREFIX="$VERIFY_TMP/pycache"
mkdir -p "$VERIFY_TMP/bin" "$VERIFY_TMP/reports" "$VERIFY_TMP/snapshots"
touch "$VERIFY_TMP/bin/agent-browser"
touch "$VERIFY_TMP/bin/lark-cli"
chmod 755 "$VERIFY_TMP/bin/agent-browser" "$VERIFY_TMP/bin/lark-cli"

"$PYTHON_BIN" - \
  "$SKILL_DIR/assets/config.example.json" \
  "$VERIFY_TMP/config.json" \
  "$VERIFY_TMP" <<'PY'
import json
import sys
from pathlib import Path

source, destination, root = map(Path, sys.argv[1:])
config = json.loads(source.read_text(encoding="utf-8"))
config.update(
    {
        "agent_browser": str(root / "bin" / "agent-browser"),
        "lark_cli": str(root / "bin" / "lark-cli"),
        "report_dir": str(root / "reports"),
        "snapshot_dir": str(root / "snapshots"),
        "folder_token": "test_folder",
        "chat_id": "test_chat",
        "staff": [["openid", "ou_test_user", "full_access", "owner"]],
    }
)
destination.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

export RECRUITMENT_CRAWLER_CONFIG="$VERIFY_TMP/config.json"
"$PYTHON_BIN" -m py_compile \
  "$SCRIPT_DIR/daily_job_crawler.py" \
  "$SCRIPT_DIR/job_crawler_watchdog.py" \
  "$SCRIPT_DIR/cron_detached_runner.py" \
  "$SCRIPT_DIR/render_launchd.py"

bash -n "$SCRIPT_DIR/run_daily.sh"
bash -n "$SCRIPT_DIR/install.sh"
bash -n "$SCRIPT_DIR/verify.sh"
if grep -q "send_failure_notification" "$SCRIPT_DIR/daily_job_crawler.py"; then
  echo "Crawler must not send failure notifications outside the receipt-aware runner" >&2
  exit 1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/daily_job_crawler.py" --self-test
"$PYTHON_BIN" "$SCRIPT_DIR/job_crawler_watchdog.py" --self-test
"$PYTHON_BIN" "$SCRIPT_DIR/cron_detached_runner.py" --self-test

"$PYTHON_BIN" - "$VERIFY_TMP/config.json" "$VERIFY_TMP/viewer-only-config.json" <<'PY'
import json
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
config = json.loads(source.read_text(encoding="utf-8"))
config["staff"] = [["openid", "ou_test_viewer", "view", "viewer"]]
destination.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
set +e
RECRUITMENT_CRAWLER_CONFIG="$VERIFY_TMP/viewer-only-config.json" \
  "$PYTHON_BIN" "$SCRIPT_DIR/daily_job_crawler.py" --self-test \
  >"$VERIFY_TMP/viewer-only.log" 2>&1
viewer_only_rc=$?
set -e
if [[ "$viewer_only_rc" -eq 0 ]] || ! grep -q "full_access" "$VERIFY_TMP/viewer-only.log"; then
  echo "Live config without full_access should fail before crawling" >&2
  exit 1
fi

printf '{broken-json' >"$VERIFY_TMP/broken-config.json"
set +e
RECRUITMENT_CRAWLER_CONFIG="$VERIFY_TMP/broken-config.json" \
  "$PYTHON_BIN" "$SCRIPT_DIR/daily_job_crawler.py" --dry-run \
  >"$VERIFY_TMP/broken-config.log" 2>&1
broken_config_rc=$?
set -e
if [[ "$broken_config_rc" -eq 0 ]] || ! grep -q "拒绝回退默认值" "$VERIFY_TMP/broken-config.log"; then
  echo "Malformed config should fail closed without default fallback" >&2
  exit 1
fi

"$PYTHON_BIN" - "$VERIFY_TMP/reports" "$VERIFY_TMP/snapshots" <<'PY'
import stat
import sys
from pathlib import Path

for raw_path in sys.argv[1:]:
    mode = stat.S_IMODE(Path(raw_path).stat().st_mode)
    assert mode == 0o700, (raw_path, oct(mode))
PY

"$PYTHON_BIN" "$SCRIPT_DIR/render_launchd.py" \
  --workspace "$VERIFY_TMP/workspace" \
  --openclaw-home "$VERIFY_TMP/openclaw" \
  --output "$VERIFY_TMP/watchdog.plist" \
  --python "$(command -v "$PYTHON_BIN")"

"$PYTHON_BIN" - "$VERIFY_TMP/watchdog.plist" <<'PY'
import plistlib
import sys
from pathlib import Path

payload = plistlib.loads(Path(sys.argv[1]).read_bytes())
assert payload["Label"] == "ai.openclaw.job-crawler-watchdog"
assert payload["StartCalendarInterval"] == {"Hour": 10, "Minute": 0}
assert "RunAtLoad" not in payload
assert "KeepAlive" not in payload
PY

INSTALL_OPENCLAW_HOME="$VERIFY_TMP/install-openclaw"
OPENCLAW_HOME="$INSTALL_OPENCLAW_HOME" \
  bash "$SCRIPT_DIR/install.sh" --workspace "$VERIFY_TMP/install-workspace"
diff -qr "$SKILL_DIR" "$VERIFY_TMP/install-workspace/skills/recruitment-crawler"

"$PYTHON_BIN" - "$VERIFY_TMP/install-workspace/projects/recruitment-crawler/config.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = json.loads(path.read_text(encoding="utf-8"))
assert config["folder_token"] == ""
assert config["chat_id"] == ""
assert config["staff"] == []
config["local_marker"] = "preserve"
path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

printf '\nlocal install drift\n' >> \
  "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/SKILL.md"
printf 'must not survive force update\n' > \
  "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/stale-secret.env"
set +e
OPENCLAW_HOME="$INSTALL_OPENCLAW_HOME" \
  bash "$SCRIPT_DIR/install.sh" --workspace "$VERIFY_TMP/install-workspace" \
  >"$VERIFY_TMP/install-without-force.log" 2>&1
install_rc=$?
set -e
if [[ "$install_rc" -ne 4 ]]; then
  echo "Installer should reject a different existing skill without --force (rc=$install_rc)" >&2
  exit 1
fi

OPENCLAW_HOME="$INSTALL_OPENCLAW_HOME" \
  bash "$SCRIPT_DIR/install.sh" --workspace "$VERIFY_TMP/install-workspace" --force
diff -qr "$SKILL_DIR" "$VERIFY_TMP/install-workspace/skills/recruitment-crawler"
if [[ -e "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/stale-secret.env" ]]; then
  echo "Force update retained a stale file in the active skill" >&2
  exit 1
fi
backup_stale_file="$(find "$INSTALL_OPENCLAW_HOME/backups/recruitment-crawler" \
  -path '*/recruitment-crawler/stale-secret.env' -type f -print -quit)"
if [[ -z "$backup_stale_file" ]]; then
  echo "Force update did not retain the previous skill outside the workspace" >&2
  exit 1
fi
"$PYTHON_BIN" - "$VERIFY_TMP/install-workspace/projects/recruitment-crawler/config.json" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert config["local_marker"] == "preserve"
PY

"$PYTHON_BIN" - "$VERIFY_TMP/stub_crawler.py" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ["STUB_ARGS_FILE"]).write_text(
    json.dumps(sys.argv[1:]), encoding="utf-8"
)
raise SystemExit(int(os.environ.get("STUB_EXIT_CODE", "0")))
""",
    encoding="utf-8",
)
PY

"$PYTHON_BIN" - "$VERIFY_TMP/stub_lark_cli.py" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    """#!/usr/bin/env python3
import json
import os
from pathlib import Path

counter = Path(os.environ["STUB_LARK_CALLS_FILE"])
calls = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
counter.write_text(str(calls + 1), encoding="utf-8")
print(json.dumps({"ok": True, "data": {"message_id": "om_offline_test"}}))
""",
    encoding="utf-8",
)
PY
chmod 755 "$VERIFY_TMP/stub_lark_cli.py"

"$PYTHON_BIN" - "$VERIFY_TMP/config.json" "$VERIFY_TMP/notify-config.json" \
  "$VERIFY_TMP/stub_lark_cli.py" <<'PY'
import json
import sys
from pathlib import Path

source, destination, lark_cli = map(Path, sys.argv[1:])
config = json.loads(source.read_text(encoding="utf-8"))
config["lark_cli"] = str(lark_cli)
destination.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

launcher_env=(
  "OPENCLAW_HOME=$VERIFY_TMP/launcher-openclaw"
  "OPENCLAW_WORKSPACE=$VERIFY_TMP/install-workspace"
  "RECRUITMENT_CRAWLER_CONFIG=$VERIFY_TMP/config.json"
  "RECRUITMENT_CRAWLER_SCRIPT=$VERIFY_TMP/stub_crawler.py"
)

env "${launcher_env[@]}" "STUB_ARGS_FILE=$VERIFY_TMP/live-args.json" \
  bash "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/scripts/run_daily.sh" \
  >"$VERIFY_TMP/live-default-launch.log"
"$PYTHON_BIN" - "$VERIFY_TMP/live-args.json" <<'PY'
import json
import sys
from pathlib import Path

assert json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) == []
PY

env "${launcher_env[@]}" "STUB_ARGS_FILE=$VERIFY_TMP/force-args.json" \
  bash "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/scripts/run_daily.sh" --force \
  >"$VERIFY_TMP/live-launch.log"
"$PYTHON_BIN" - "$VERIFY_TMP/force-args.json" <<'PY'
import json
import sys
from pathlib import Path

assert json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) == ["--force"]
PY

env "${launcher_env[@]}" "STUB_ARGS_FILE=$VERIFY_TMP/dry-run-args.json" \
  bash "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/scripts/run_daily.sh" --dry-run \
  >"$VERIFY_TMP/dry-run-launch.log"
"$PYTHON_BIN" - "$VERIFY_TMP/dry-run-args.json" <<'PY'
import json
import sys
from pathlib import Path

assert json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) == ["--dry-run"]
PY

# 失败路径只允许 runner 发一次通知，且必须保留子进程退出码与 message_id 回执。
set +e
env "${launcher_env[@]}" \
  "RECRUITMENT_CRAWLER_CONFIG=$VERIFY_TMP/notify-config.json" \
  "STUB_ARGS_FILE=$VERIFY_TMP/failure-args.json" \
  "STUB_EXIT_CODE=9" \
  "STUB_LARK_CALLS_FILE=$VERIFY_TMP/lark-call-count.txt" \
  bash "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/scripts/run_daily.sh" \
  >"$VERIFY_TMP/failure-launch.log" 2>&1
failure_launcher_rc=$?
set -e
if [[ "$failure_launcher_rc" -ne 9 ]]; then
  echo "Failed crawler should preserve child exit code 9 (rc=$failure_launcher_rc)" >&2
  exit 1
fi
"$PYTHON_BIN" - \
  "$VERIFY_TMP/lark-call-count.txt" \
  "$VERIFY_TMP/launcher-openclaw/tmp/cron-detached/daily-job-crawler.json" <<'PY'
import json
import sys
from pathlib import Path

counter, state_path = map(Path, sys.argv[1:])
assert counter.read_text(encoding="utf-8") == "1"
state = json.loads(state_path.read_text(encoding="utf-8"))
assert state["child_exit_code"] == 9
assert state["job_status"] == "error"
assert state["notification_status"] == "sent"
assert state["runner_exit_code"] == 9
PY

env -u OPENCLAW_WORKSPACE -u RECRUITMENT_CRAWLER_CONFIG \
  "OPENCLAW_HOME=$VERIFY_TMP/inferred-openclaw" \
  "RECRUITMENT_CRAWLER_SCRIPT=$VERIFY_TMP/stub_crawler.py" \
  "STUB_ARGS_FILE=$VERIFY_TMP/inferred-workspace-args.json" \
  bash "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/scripts/run_daily.sh" --dry-run \
  >"$VERIFY_TMP/inferred-workspace-launch.log"
"$PYTHON_BIN" - "$VERIFY_TMP/inferred-workspace-args.json" <<'PY'
import json
import sys
from pathlib import Path

assert json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) == ["--dry-run"]
PY

set +e
OPENCLAW_HOME="$VERIFY_TMP/launcher-openclaw" \
OPENCLAW_WORKSPACE="$VERIFY_TMP/install-workspace" \
RECRUITMENT_CRAWLER_CONFIG="$VERIFY_TMP/install-workspace/projects/recruitment-crawler/config.json" \
  bash "$VERIFY_TMP/install-workspace/skills/recruitment-crawler/scripts/run_daily.sh" \
  >"$VERIFY_TMP/blank-config-launch.log" 2>&1
launcher_rc=$?
set -e
if [[ "$launcher_rc" -ne 3 ]]; then
  echo "Blank live config should fail closed before crawl (rc=$launcher_rc)" >&2
  exit 1
fi

echo "PORTABLE_VERIFY ok"
