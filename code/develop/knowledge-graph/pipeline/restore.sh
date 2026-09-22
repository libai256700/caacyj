#!/bin/bash
# restore.sh — 知识图谱灾难恢复一步式脚本
# 用法: bash pipeline/restore.sh <backup_tarball_path>
# 示例: bash pipeline/restore.sh ~/Downloads/同步空间/openclaw/kg_backups/kg_backup_20260525_0230.tar.gz

set -e
BACKUP_FILE="${1:?用法: bash restore.sh <backup.tar.gz>}"
DATA_DIR="$(cd "$(dirname "$0")/.." && pwd)/neo4j-docker/data"
CONTAINER="yunji-knowledge-graph"
NEO4J_IMAGE="neo4j:latest"

echo "📦 知识图谱恢复 — $(date)"
echo "   备份: $BACKUP_FILE"
echo "   数据目录: $DATA_DIR"
echo ""

# Step 1: 停容器
echo "🛑 停止 Neo4j..."
docker stop "$CONTAINER" 2>/dev/null || true

# Step 2: 提取备份
TMP_DIR=$(mktemp -d)
echo "📂 解压备份到 $TMP_DIR ..."
tar xzf "$BACKUP_FILE" -C "$TMP_DIR"

# Step 3: Dump
echo "📤 创建 dump..."
rm -rf "$DATA_DIR/databases/neo4j"
cp -r "$TMP_DIR/neo4j" "$DATA_DIR/databases/neo4j"
docker run --rm \
  -v "$DATA_DIR/databases:/data/databases" \
  --entrypoint neo4j-admin \
  "$NEO4J_IMAGE" database dump neo4j --to-path=/data/databases/
rm -rf "$DATA_DIR/databases/neo4j"

# Step 4: 启动干净 Neo4j（创 system 库）
echo "🚀 启动干净 Neo4j..."
docker start "$CONTAINER"
echo "   等待 healthy..."
for i in $(seq 1 20); do
  sleep 3
  ST=$(docker inspect "$CONTAINER" --format '{{.State.Health.Status}}' 2>/dev/null)
  echo "   [$(($i*3))s] $ST"
  [ "$ST" = "healthy" ] && break
done

# Step 5: Load dump
echo "🛑 暂停以加载数据..."
docker stop "$CONTAINER"
rm -rf "$DATA_DIR/databases/system" "$DATA_DIR/transactions/neo4j" "$DATA_DIR/transactions/system"
mkdir -p "$DATA_DIR/transactions/neo4j" "$DATA_DIR/transactions/system"
docker run --rm \
  -v "$DATA_DIR/databases:/data/databases" \
  -v "$DATA_DIR/transactions:/data/transactions" \
  --entrypoint neo4j-admin \
  "$NEO4J_IMAGE" database load neo4j --from-path=/data/databases/ --overwrite-destination=true
rm -f "$DATA_DIR/databases/neo4j.dump"

# Step 6: 启动并验证
echo "🚀 启动 Neo4j..."
docker start "$CONTAINER"
ST="" 
for i in $(seq 1 20); do
  sleep 3
  ST=$(docker inspect "$CONTAINER" --format '{{.State.Health.Status}}' 2>/dev/null)
  echo "   [$(($i*3))s] $ST"
  [ "$ST" = "healthy" ] && break
done

if [ "$ST" != "healthy" ]; then
  echo "❌ 容器未健康，查看 logs:"
  docker logs --tail 20 "$CONTAINER"
  exit 1
fi

# Step 7: 验证数据
echo "📊 验证数据..."
NEO4J_PASS=$(cat "$(dirname "$0")/../neo4j/.neo4j_pass")
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', '$NEO4J_PASS'))
with d.session() as s:
    n = s.run('MATCH (n) RETURN count(n)').single()[0]
    r = s.run('MATCH ()-[r]->() RETURN count(r)').single()[0]
    print(f'✅ 恢复完成: {n} 节点, {r} 关系')
d.close()
"

# Cleanup
rm -rf "$TMP_DIR"
echo "✅ 恢复流程完成"
