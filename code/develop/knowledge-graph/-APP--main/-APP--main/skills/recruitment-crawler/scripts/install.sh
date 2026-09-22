#!/usr/bin/env bash
# Install the self-contained skill without copying local credentials or state.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
BACKUP_BASE="${RECRUITMENT_CRAWLER_BACKUP_DIR:-$OPENCLAW_HOME/backups/recruitment-crawler}"
force=0

usage() {
  cat <<'EOF'
Usage: install.sh [--workspace ABSOLUTE_PATH] [--force]

Installs the skill and creates a blank runtime config if one does not exist.
Existing runtime config is never overwritten.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --workspace)
      [[ "$#" -ge 2 ]] || {
        echo "--workspace requires a path" >&2
        exit 2
      }
      WORKSPACE="$2"
      shift 2
      ;;
    --force)
      force=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$WORKSPACE" in
  /)
    echo "--workspace cannot be the filesystem root" >&2
    exit 2
    ;;
  /*) ;;
  *)
    echo "--workspace must resolve to an absolute path: $WORKSPACE" >&2
    exit 2
    ;;
esac

case "$BACKUP_BASE" in
  /)
    echo "backup directory cannot be the filesystem root" >&2
    exit 2
    ;;
  /*) ;;
  *)
    echo "backup directory must resolve to an absolute path: $BACKUP_BASE" >&2
    exit 2
    ;;
esac

DEST_SKILL="$WORKSPACE/skills/recruitment-crawler"
CONFIG_DIR="$WORKSPACE/projects/recruitment-crawler"
CONFIG_FILE="$CONFIG_DIR/config.json"
CONFIG_EXAMPLE="$PACKAGE_ROOT/assets/config.example.json"

if [[ -L "$DEST_SKILL" || -L "$CONFIG_DIR" || -L "$CONFIG_FILE" ]]; then
  echo "Refusing to install through a symlinked skill or config path" >&2
  exit 5
fi

install_code=1
if [[ "$DEST_SKILL" == "$PACKAGE_ROOT" ]]; then
  install_code=0
elif [[ -e "$DEST_SKILL" ]]; then
  if diff -qr "$PACKAGE_ROOT" "$DEST_SKILL" >/dev/null 2>&1; then
    echo "Skill files are already up to date: $DEST_SKILL"
    install_code=0
  elif [[ "$force" -ne 1 ]]; then
    echo "A different recruitment-crawler is already installed at $DEST_SKILL" >&2
    echo "Review it, then rerun with --force to update code. Config will remain untouched." >&2
    exit 4
  fi
fi

if [[ "$install_code" -eq 1 ]]; then
  SKILLS_DIR="$(dirname "$DEST_SKILL")"
  mkdir -p "$SKILLS_DIR"
  STAGE_ROOT="$(mktemp -d "$SKILLS_DIR/.recruitment-crawler.install.XXXXXX")"
  STAGED_SKILL="$STAGE_ROOT/recruitment-crawler"
  cleanup_stage() {
    rm -rf -- "$STAGE_ROOT"
  }
  trap cleanup_stage EXIT

  mkdir -p "$STAGED_SKILL"
  cp -R "$PACKAGE_ROOT/." "$STAGED_SKILL/"

  if [[ -e "$DEST_SKILL" ]]; then
    if [[ -L "$BACKUP_BASE" ]]; then
      echo "Refusing to use a symlinked backup directory: $BACKUP_BASE" >&2
      exit 5
    fi
    mkdir -p "$BACKUP_BASE"
    chmod 700 "$BACKUP_BASE"
    BACKUP_ROOT="$(mktemp -d "$BACKUP_BASE/backup.XXXXXX")"
    BACKUP_SKILL="$BACKUP_ROOT/recruitment-crawler"
    mv "$DEST_SKILL" "$BACKUP_SKILL"
    if ! mv "$STAGED_SKILL" "$DEST_SKILL"; then
      mv "$BACKUP_SKILL" "$DEST_SKILL" || true
      rmdir "$BACKUP_ROOT" 2>/dev/null || true
      echo "Install failed; restored previous skill" >&2
      exit 6
    fi
    echo "Previous skill retained for rollback: $BACKUP_SKILL"
  else
    mv "$STAGED_SKILL" "$DEST_SKILL"
  fi
  rmdir "$STAGE_ROOT"
  trap - EXIT
fi

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
if [[ ! -e "$CONFIG_FILE" ]]; then
  install -m 600 "$CONFIG_EXAMPLE" "$CONFIG_FILE"
  echo "Created blank config: $CONFIG_FILE"
else
  chmod 600 "$CONFIG_FILE"
  echo "Preserved existing config: $CONFIG_FILE"
fi

find "$DEST_SKILL/scripts" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod 755 {} +
echo "Installed skill: $DEST_SKILL"
echo "Next: edit $CONFIG_FILE, then run $DEST_SKILL/scripts/verify.sh"
