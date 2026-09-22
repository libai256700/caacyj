#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$REPO_ROOT/deploy" \
  python3 -m unittest discover \
  -s "$REPO_ROOT/skills/knowledge-graph-cloud/tests" \
  -p 'test_*.py'

PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT_DIR/verify_package.py" --root "$REPO_ROOT"
