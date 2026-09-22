#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CANONICAL_ROOT="/Users/xiaoji/Documents/知识库分析"
LOG_DIR="$ROOT/logs/business_graph_sync"
LOCK_DIR="/tmp/business_graph_sync_gate.lock"

mkdir -p "$LOG_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "business graph sync gate is already running: $LOCK_DIR" >&2
  exit 75
fi
trap 'rm -rf "$LOCK_DIR"' EXIT

ts="$(date '+%Y%m%d-%H%M%S')"
log_file="$LOG_DIR/business_graph_sync_${ts}.log"
latest_log="$LOG_DIR/business_graph_sync_latest.log"

{
  echo "=== business graph sync gate started at $(date '+%Y-%m-%d %H:%M:%S %z') ==="

  echo
  echo "=== 1. rebuild canonical entity tables ==="
  cd "$CANONICAL_ROOT"
  python3 scripts/build_canonical_entities.py

  echo
  echo "=== 2. validate canonical entity tables ==="
  python3 scripts/validate_canonical_entities.py

  echo
  echo "=== 3. sync canonical business entities to Neo4j ==="
  cd "$ROOT"
  python3 scripts/sync_business_entities_to_neo4j.py

  echo
  echo "=== 4. type conflict governance ==="
  python3 scripts/govern_type_conflicts.py --confirm

  echo
  echo "=== 5. job company duplicate governance ==="
  python3 scripts/govern_job_company_duplicates.py --confirm

  echo
  echo "=== 6. graph coverage report ==="
  python3 scripts/graph_coverage_report.py

  echo
  echo "=== 7. multihop business graph eval ==="
  python3 scripts/eval_multihop_business_graph.py

  echo
  echo "=== 8. multihop bridge governance dry-run ==="
  python3 scripts/govern_multihop_bridges.py

  echo
  echo "=== 9. type conflict governance dry-run ==="
  python3 scripts/govern_type_conflicts.py

  echo
  echo "=== 10. job company duplicate governance dry-run ==="
  python3 scripts/govern_job_company_duplicates.py

  echo
  echo "=== 11. business graph governance gate ==="
  python3 scripts/check_business_graph_governance.py

  echo
  echo "=== 12. route policy eval ==="
  cd "$ROOT"
  python3 scripts/eval_route_policy.py

  echo
  echo "=== business graph sync gate finished at $(date '+%Y-%m-%d %H:%M:%S %z') ==="
} 2>&1 | tee "$log_file"

cp "$log_file" "$latest_log"
echo "$log_file"
