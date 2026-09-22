#!/usr/bin/env bash
# Portable synchronous launcher for the recruitment-crawler skill.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INFERRED_WORKSPACE="$(cd "$SKILL_DIR/../.." && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
WORKSPACE="${OPENCLAW_WORKSPACE:-$INFERRED_WORKSPACE}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNNER="${RECRUITMENT_CRAWLER_RUNNER:-$SCRIPT_DIR/cron_detached_runner.py}"
CRAWLER="${RECRUITMENT_CRAWLER_SCRIPT:-$SCRIPT_DIR/daily_job_crawler.py}"
CONFIG="${RECRUITMENT_CRAWLER_CONFIG:-$WORKSPACE/projects/recruitment-crawler/config.json}"
LOG_DIR="${RECRUITMENT_CRAWLER_LOG_DIR:-$OPENCLAW_HOME/logs/cron-detached}"
STATE_DIR="${RECRUITMENT_CRAWLER_STATE_DIR:-$OPENCLAW_HOME/tmp/cron-detached}"

dry_run=0
force_publish=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      dry_run=1
      ;;
    --force)
      force_publish=1
      ;;
    -h|--help)
      echo "Usage: $0 [--dry-run | --force]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ "$dry_run" -eq 1 && "$force_publish" -eq 1 ]]; then
  echo "--dry-run and --force cannot be combined" >&2
  exit 2
fi

for required_file in "$RUNNER" "$CRAWLER" "$CONFIG"; do
  if [[ ! -f "$required_file" ]]; then
    echo "Required file not found: $required_file" >&2
    exit 3
  fi
done

mkdir -p "$LOG_DIR" "$STATE_DIR"
chmod 700 "$LOG_DIR" "$STATE_DIR"
export RECRUITMENT_CRAWLER_CONFIG="$CONFIG"

crawler_command=("$PYTHON_BIN" -u "$CRAWLER")
job_key="daily-job-crawler"
notify_mode="failure"

if [[ "$dry_run" -eq 1 ]]; then
  crawler_command+=(--dry-run)
  job_key="daily-job-crawler-dry-run"
  notify_mode="none"
else
  chat_id="$("$PYTHON_BIN" - "$CONFIG" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = str(json.load(handle).get("chat_id") or "").strip()
if not value:
    raise SystemExit(1)
print(value)
PY
  )" || {
    echo "config.json has no valid chat_id; refusing live run" >&2
    exit 3
  }
  lark_cli="$("$PYTHON_BIN" - "$CONFIG" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = str(json.load(handle).get("lark_cli") or "").strip()
if not value or "\n" in value or "\r" in value:
    raise SystemExit(1)
print(value)
PY
  )" || {
    echo "config.json has no valid lark_cli; refusing live run" >&2
    exit 3
  }
  if [[ "$force_publish" -eq 1 ]]; then
    crawler_command+=(--force)
  fi
fi

runner_args=(
  --job-key "$job_key"
  --name "每日招聘岗位爬虫"
  --cwd "$WORKSPACE"
)
if [[ "$dry_run" -ne 1 ]]; then
  runner_args+=(--chat-id "$chat_id" --lark-cli "$lark_cli")
fi
runner_args+=(
  --notify "$notify_mode"
  --timeout-seconds 1800
  --log-dir "$LOG_DIR"
  --state-dir "$STATE_DIR"
)

set +e
"$PYTHON_BIN" "$RUNNER" "${runner_args[@]}" \
  -- "${crawler_command[@]}"
runner_rc=$?
set -e

state_file="$STATE_DIR/$job_key.json"
if [[ -r "$state_file" ]]; then
  "$PYTHON_BIN" - "$state_file" "$runner_rc" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
keys = (
    "job_key",
    "child_exit_code",
    "job_status",
    "notification_status",
    "runner_exit_code",
)
receipt = {key: state.get(key) for key in keys}
receipt["launcher_exit_code"] = int(sys.argv[2])
print("FINAL_RECEIPT " + json.dumps(receipt, ensure_ascii=False, sort_keys=True))
PY
else
  echo "FINAL_RECEIPT job_key=$job_key launcher_exit_code=$runner_rc state=unavailable"
fi

exit "$runner_rc"
