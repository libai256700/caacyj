#!/bin/bash
# Neo4j 知识图谱备份脚本（适配 Docker 版 v3）
# 停容器 -> tar 数据目录 -> 校验 -> 原子落盘 -> 重启

set -euo pipefail

BACKUP_DIR="/Users/xiaoji/Downloads/同步空间/openclaw/kg_backups"
DATE=$(date +%Y%m%d_%H%M)
NAME="kg_backup_$DATE"
CONTAINER="yunji-knowledge-graph"
DATA_DIR="/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j-docker/data"
KEEP_DAYS="${KG_BACKUP_KEEP_DAYS:-14}"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/kg-backup.XXXXXX")
TMP_ARCHIVE="$TMP_DIR/$NAME.tar.gz"
TMP_MANIFEST="$TMP_DIR/$NAME.manifest.json"
FINAL_ARCHIVE="$BACKUP_DIR/$NAME.tar.gz"
FINAL_MANIFEST="$BACKUP_DIR/$NAME.manifest.json"
FINAL_SHA="$FINAL_ARCHIVE.sha256"
STOPPED=0

cleanup() {
  rm -rf "$TMP_DIR"
  if [ "$STOPPED" = "1" ]; then
    docker start "$CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

mkdir -p "$BACKUP_DIR"

echo "Stopping Neo4j..."
docker stop "$CONTAINER" >/dev/null
STOPPED=1
sleep 5

echo "Packing Neo4j data in staging..."
tar czf "$TMP_ARCHIVE" -C "$DATA_DIR" databases/
gzip -t "$TMP_ARCHIVE"
tar tzf "$TMP_ARCHIVE" >/dev/null

SIZE_BYTES=$(stat -f '%z' "$TMP_ARCHIVE")
SIZE_HUMAN=$(du -h "$TMP_ARCHIVE" | cut -f1)
SHA256=$(shasum -a 256 "$TMP_ARCHIVE" | awk '{print $1}')

cat > "$TMP_MANIFEST" <<EOF
{
  "kind": "neo4j-knowledge-graph-backup",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "archive": "$NAME.tar.gz",
  "container": "$CONTAINER",
  "source": "$DATA_DIR/databases",
  "size_bytes": $SIZE_BYTES,
  "sha256": "$SHA256",
  "validated": {
    "gzip_test": true,
    "tar_list": true
  }
}
EOF

mv "$TMP_ARCHIVE" "$FINAL_ARCHIVE"
mv "$TMP_MANIFEST" "$FINAL_MANIFEST"
printf '%s  %s\n' "$SHA256" "$NAME.tar.gz" > "$FINAL_SHA"
(cd "$BACKUP_DIR" && shasum -a 256 -c "$(basename "$FINAL_SHA")" >/dev/null)

echo "Restarting Neo4j..."
docker start "$CONTAINER" >/dev/null
STOPPED=0

for i in $(seq 1 10); do
  sleep 3
  ST=$(docker inspect "$CONTAINER" --format '{{.State.Health.Status}}' 2>/dev/null || true)
  [ "$ST" = "healthy" ] && break
done

find "$BACKUP_DIR" -name "kg_backup_*.tar.gz" -mtime +"$KEEP_DAYS" -print | while IFS= read -r old; do
  rm -f "$old" "$old.sha256" "${old%.tar.gz}.manifest.json"
done

COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -name 'kg_backup_*.tar.gz' -type f | wc -l | tr -d ' ')
echo "Backup created: $FINAL_ARCHIVE ($SIZE_HUMAN)"
echo "SHA256: $SHA256"
echo "Manifest: $FINAL_MANIFEST"
echo "Total backups: $COUNT"
