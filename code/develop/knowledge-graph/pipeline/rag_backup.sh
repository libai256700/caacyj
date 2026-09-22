#!/bin/bash
# RAG 专项备份：一致性 SQLite 快照 + 原始文档 + 可重建索引元数据。
# Usage: bash pipeline/rag_backup.sh [backup_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${1:-/Users/xiaoji/Downloads/同步空间/openclaw/rag_backups}"
KEEP_DAYS="${RAG_BACKUP_KEEP_DAYS:-30}"
DATE=$(date +%Y%m%d_%H%M)
NAME="rag_backup_$DATE"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/rag-backup.XXXXXX")
ROOT="$TMP_DIR/$NAME"
TMP_ARCHIVE="$TMP_DIR/$NAME.tar.gz"
TMP_MANIFEST="$TMP_DIR/$NAME.manifest.json"
FINAL_ARCHIVE="$BACKUP_DIR/$NAME.tar.gz"
FINAL_MANIFEST="$BACKUP_DIR/$NAME.manifest.json"
FINAL_SHA="$FINAL_ARCHIVE.sha256"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$BACKUP_DIR" "$ROOT/rag_index"

copy_if_exists() {
  local rel="$1"
  if [ -e "$PROJECT_DIR/$rel" ]; then
    mkdir -p "$ROOT/$(dirname "$rel")"
    cp -R "$PROJECT_DIR/$rel" "$ROOT/$rel"
  fi
}

echo "Creating consistent SQLite snapshots..."
export PROJECT_DIR ROOT
python3 - <<'PY'
import json
import os
import sqlite3
from pathlib import Path

project = Path(os.environ["PROJECT_DIR"])
root = Path(os.environ["ROOT"])

stats = {
    "rag_chunks": None,
    "dense_bge_m3": None,
}

def backup_sqlite(src: Path, dst: Path) -> dict | None:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(src)) as source, sqlite3.connect(str(dst)) as target:
        source.backup(target)
    with sqlite3.connect(str(dst)) as check:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [
            row[0]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        counts = {}
        for table in tables:
            try:
                counts[table] = check.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            except sqlite3.DatabaseError:
                pass
    return {
        "source": str(src),
        "snapshot": str(dst.relative_to(root)),
        "integrity_check": integrity,
        "tables": tables,
        "counts": counts,
        "size_bytes": dst.stat().st_size,
    }

stats["rag_chunks"] = backup_sqlite(project / "rag_chunks.db", root / "rag_chunks.db")
stats["dense_bge_m3"] = backup_sqlite(
    project / "rag_index" / "dense_bge_m3.sqlite",
    root / "rag_index" / "dense_bge_m3.sqlite",
)

if not stats["rag_chunks"]:
    raise SystemExit("rag_chunks.db is missing")
if stats["rag_chunks"]["integrity_check"] != "ok":
    raise SystemExit("rag_chunks.db snapshot failed integrity_check")
if stats["dense_bge_m3"] and stats["dense_bge_m3"]["integrity_check"] != "ok":
    raise SystemExit("dense_bge_m3.sqlite snapshot failed integrity_check")

(root / "manifest.json").write_text(
    json.dumps(
        {
            "kind": "rag-snapshot",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "source_project": str(project),
            "sqlite": stats,
            "notes": [
                "rag_chunks.db is the canonical chunk_id-to-text store.",
                "Dense, BM25, and Neo4j layers are derived from the canonical store and source documents.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
PY

echo "Copying RAG source material and metadata..."
copy_if_exists "rag_docs"
copy_if_exists "feishu_raw"
copy_if_exists "rag_store"
copy_if_exists "rag_index/bm25"
copy_if_exists "PROJECT.md"
copy_if_exists "KG_GUIDE.md"
copy_if_exists "test_questions.txt"
copy_if_exists "pipeline/config.json"

echo "Packing RAG snapshot in staging..."
tar czf "$TMP_ARCHIVE" -C "$TMP_DIR" "$NAME"
gzip -t "$TMP_ARCHIVE"
tar tzf "$TMP_ARCHIVE" >/dev/null

SIZE_BYTES=$(stat -f '%z' "$TMP_ARCHIVE")
SIZE_HUMAN=$(du -h "$TMP_ARCHIVE" | cut -f1)
SHA256=$(shasum -a 256 "$TMP_ARCHIVE" | awk '{print $1}')

cat > "$TMP_MANIFEST" <<EOF
{
  "kind": "rag-snapshot-archive",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "archive": "$NAME.tar.gz",
  "source": "$PROJECT_DIR",
  "size_bytes": $SIZE_BYTES,
  "sha256": "$SHA256",
  "validated": {
    "sqlite_backup": true,
    "gzip_test": true,
    "tar_list": true
  },
  "restore_hint": "Extract this archive and restore rag_chunks.db plus rag_docs/feishu_raw/rag_store. Rebuild dense/BM25/Neo4j if derived indexes drift."
}
EOF

mv "$TMP_ARCHIVE" "$FINAL_ARCHIVE"
mv "$TMP_MANIFEST" "$FINAL_MANIFEST"
printf '%s  %s\n' "$SHA256" "$NAME.tar.gz" > "$FINAL_SHA"
(cd "$BACKUP_DIR" && shasum -a 256 -c "$(basename "$FINAL_SHA")" >/dev/null)

find "$BACKUP_DIR" -name "rag_backup_*.tar.gz" -mtime +"$KEEP_DAYS" -print | while IFS= read -r old; do
  rm -f "$old" "$old.sha256" "${old%.tar.gz}.manifest.json"
done

COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -name 'rag_backup_*.tar.gz' -type f | wc -l | tr -d ' ')
echo "RAG backup created: $FINAL_ARCHIVE ($SIZE_HUMAN)"
echo "SHA256: $SHA256"
echo "Manifest: $FINAL_MANIFEST"
echo "Total RAG backups: $COUNT"
