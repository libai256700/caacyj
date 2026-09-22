#!/usr/bin/env python3
"""
RAG 文本存储 —— SQLite 方案

Neo4j 只负责实体关系推理，Chunk 原文存在 SQLite 中。
通过 chunk_id 作为唯一契约串联三个系统：
  Neo4j (chunk_id) ←→ SQLite (chunk_id) ←→ RAG Index (chunk_id)
"""

import sqlite3
import json
import re
import threading
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# ============ 默认数据库路径 ============
import os
_DEFAULT_DB_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB_PATH = str(_DEFAULT_DB_DIR / "rag_chunks.db")
_DEFAULT_ALIAS_PATH = Path(__file__).resolve().parent / "source_doc_aliases.json"

try:
    from .knowledge_governance import (
        CORE_RAG_SCHEMA_SQL,
        ensure_governance_tables,
        fetch_chunk_governance,
        governance_schema_state as classify_governance_schema,
        stable_cross_cluster_claim_key,
    )
except ImportError:  # pragma: no cover - direct script execution
    from knowledge_governance import (
        CORE_RAG_SCHEMA_SQL,
        ensure_governance_tables,
        fetch_chunk_governance,
        governance_schema_state as classify_governance_schema,
        stable_cross_cluster_claim_key,
    )


class RagStore:
    """RAG 文本存储，基于 SQLite"""

    def __init__(self, db_path: str = None, *, read_only: bool = False):
        if read_only and not db_path:
            raise ValueError("read-only RagStore requires an explicit db_path")
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.read_only = bool(read_only)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._source_doc_aliases: Optional[Dict[str, List[str]]] = None

    # ============ 连接管理 ============

    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                if self.read_only:
                    uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"
                    self._conn = sqlite3.connect(
                        uri,
                        uri=True,
                        check_same_thread=False,
                    )
                else:
                    self._conn = sqlite3.connect(
                        self.db_path,
                        check_same_thread=False,
                    )
                self._conn.row_factory = sqlite3.Row
                if self.read_only:
                    self._conn.execute("PRAGMA query_only=ON")
                else:
                    self._conn.execute("PRAGMA journal_mode=WAL")
                    self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
                self._conn.execute("PRAGMA foreign_keys=ON")
            return self._conn

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ============ 建表 ============

    def init_tables(self, *, governance: bool = False):
        """初始化 Chunk 表 + 文档表（幂等，可重复调用）。

        治理旁表只在 governance=True 时创建。建治理表是显式迁移动作，不能挂在
        服务启动或读路径上：那样一张丢失的治理表会被静默补成空表并重新判为
        ready，已裁决的冲突与人工决定随之消失且外部无从察觉。缺表必须保持
        partial 并由 assert_governance_available 拒答。
        """
        if self.read_only:
            raise RuntimeError("read-only RagStore cannot initialize tables")
        with self._lock:
            conn = self.connect()
            conn.executescript(CORE_RAG_SCHEMA_SQL)
            if governance:
                ensure_governance_tables(conn)
            conn.commit()

    def init_governance_tables(self):
        """显式创建治理旁表（迁移/导入 apply 专用，禁止由读路径调用）。"""
        self.init_tables(governance=True)

    # ============ Chunk 读写 ============

    def store_chunk(self, chunk_id: str, text: str, doc_name: str, chunk_index: int = 0):
        """写入一个 Chunk（UPSERT）"""
        with self._lock:
            conn = self.connect()
            conn.execute(
                """INSERT OR REPLACE INTO chunks (chunk_id, text, doc_name, chunk_index)
                   VALUES (?, ?, ?, ?)""",
                (chunk_id, text, doc_name, chunk_index)
            )
            conn.commit()

    def store_chunks_batch(self, chunks: List[Dict]):
        """批量写入 Chunks（事务包裹）"""
        with self._lock:
            conn = self.connect()
            conn.executemany(
                """INSERT OR REPLACE INTO chunks (chunk_id, text, doc_name, chunk_index)
                   VALUES (:chunk_id, :text, :doc_name, :chunk_index)""",
                chunks
            )
            conn.commit()

    def get_chunk_text(self, chunk_id: str) -> Optional[str]:
        """根据 chunk_id 获取文本"""
        with self._lock:
            conn = self.connect()
            row = conn.execute(
                "SELECT text FROM chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
            return row["text"] if row else None

    def get_chunks_batch(self, chunk_ids: List[str]) -> List[Dict]:
        """批量获取 chunks，保持输入顺序"""
        if not chunk_ids:
            return []
        with self._lock:
            conn = self.connect()
            placeholders = ",".join("?" for _ in chunk_ids)
            rows = conn.execute(
                f"SELECT chunk_id, text, doc_name, chunk_index FROM chunks "
                f"WHERE chunk_id IN ({placeholders})",
                chunk_ids
            ).fetchall()
            return [dict(r) for r in rows]

    def get_chunks_by_doc(self, doc_name: str) -> List[Dict]:
        """按文档名获取所有 chunks，按 index 排序"""
        with self._lock:
            conn = self.connect()
            rows = conn.execute(
                "SELECT chunk_id, text, chunk_index FROM chunks "
                "WHERE doc_name = ? ORDER BY chunk_index",
                (doc_name,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_neighbor_chunks(
        self,
        doc_name: str,
        chunk_index: int,
        before: int = 1,
        after: int = 1,
    ) -> List[Dict]:
        """取同一文档中命中 chunk 前后的相邻 chunks。"""
        if not doc_name:
            return []
        start = max(0, int(chunk_index) - max(0, before))
        end = int(chunk_index) + max(0, after)
        with self._lock:
            conn = self.connect()
            rows = conn.execute(
                "SELECT chunk_id, text, doc_name, chunk_index FROM chunks "
                "WHERE doc_name = ? AND chunk_index BETWEEN ? AND ? "
                "ORDER BY chunk_index",
                (doc_name, start, end),
            ).fetchall()
            return [dict(r) for r in rows]

    def find_chunks_by_doc_names(self, doc_names: List[str], limit_per_doc: int = 10) -> List[Dict]:
        """按来源文档名查 chunks，兼容 Neo4j source_doc 缺少 .txt/前缀的情况。"""
        if not doc_names:
            return []

        with self._lock:
            conn = self.connect()
            results = []
            seen = set()
            for raw_name in doc_names:
                for pattern in self._doc_name_patterns(raw_name):
                    rows = conn.execute(
                        "SELECT chunk_id, text, doc_name, chunk_index FROM chunks "
                        "WHERE doc_name = ? OR doc_name LIKE ? ESCAPE '\\' "
                        "ORDER BY chunk_index LIMIT ?",
                        (pattern, f"%{self._escape_like(pattern)}%", limit_per_doc),
                    ).fetchall()
                    for row in rows:
                        item = dict(row)
                        if item["chunk_id"] not in seen:
                            seen.add(item["chunk_id"])
                            results.append(item)
                    if len([r for r in results if r["doc_name"] == pattern]) >= limit_per_doc:
                        break
            return results

    def search_chunks(self, terms: List[str], limit: int = 20) -> List[Dict]:
        """在 SQLite 文本中查找关键词，作为 KG chunk_id 映射和 BM25 前的轻量兜底。"""
        terms = [t.strip() for t in terms if t and len(t.strip()) >= 2]
        if not terms:
            return []

        with self._lock:
            conn = self.connect()
            scored: Dict[str, Dict] = {}
            for term in terms[:8]:
                rows = conn.execute(
                    "SELECT chunk_id, text, doc_name, chunk_index FROM chunks "
                    "WHERE text LIKE ? ESCAPE '\\' OR doc_name LIKE ? ESCAPE '\\' LIMIT ?",
                    (f"%{self._escape_like(term)}%", f"%{self._escape_like(term)}%", limit),
                ).fetchall()
                for row in rows:
                    item = dict(row)
                    entry = scored.setdefault(item["chunk_id"], {**item, "_score": 0})
                    entry["_score"] += item.get("text", "").count(term) + 1

            ranked = sorted(scored.values(), key=lambda x: (-x["_score"], x["doc_name"], x["chunk_index"]))
            for item in ranked:
                item.pop("_score", None)
            return ranked[:limit]

    def get_chunks_by_ids_with_text(self, chunk_ids: List[str]) -> List[Dict]:
        """获取 chunks 详情（含文本），用于上下文组装"""
        return self.get_chunks_batch(chunk_ids)

    def get_chunk_governance(self, chunk_ids: List[str]) -> Dict:
        """Return canonical claim and unresolved-conflict sidecar data."""
        if not chunk_ids:
            return {
                "by_chunk": {},
                "supporting_sources": {},
                "unresolved_conflicts": {},
                "provenance": {},
            }
        with self._lock:
            conn = self.connect()
            started_read = not conn.in_transaction
            if started_read:
                conn.execute("BEGIN")
            try:
                return fetch_chunk_governance(conn, chunk_ids)
            finally:
                if started_read and conn.in_transaction:
                    conn.rollback()

    def governance_schema_state(self) -> str:
        """Classify the core and sidecar schema without creating or repairing it."""
        with self._lock:
            return classify_governance_schema(self.connect())

    def ensure_runtime_conflicts(self, conflicts: List[Dict]) -> List[str]:
        """Persist newly detected claim-signature conflicts for human review."""
        if not conflicts:
            return []
        persisted = []
        with self._lock:
            conn = self.connect()
            with conn:
                for conflict in conflicts:
                    conflict_id = str(conflict.get("conflict_id") or "")
                    claim_key = str(conflict.get("claim_key") or "")
                    cluster_id = str(conflict.get("concept_cluster_id") or "")
                    claim_ids = sorted({
                        str(claim_id)
                        for claim_id in conflict.get("claim_ids") or []
                        if claim_id
                    })
                    cross_cluster = bool(conflict.get("cross_cluster"))
                    if not conflict_id or not claim_key or not cluster_id or not claim_ids:
                        raise ValueError("runtime conflict is missing stable identity or claims")
                    conn.execute(
                        """
                        INSERT INTO knowledge_conflicts (
                            conflict_id, conflict_key, concept_cluster_id,
                            claim_key, severity, reason, status, suggested_action
                        ) VALUES (?, ?, ?, ?, 'blocking', ?, 'pending', 'prefer_source')
                        ON CONFLICT(conflict_id) DO UPDATE SET
                            severity = 'blocking',
                            reason = CASE
                                WHEN trim(knowledge_conflicts.reason) = ''
                                THEN excluded.reason
                                ELSE knowledge_conflicts.reason
                            END,
                            status = CASE
                                WHEN knowledge_conflicts.status IN ('pending', 'in_review')
                                THEN knowledge_conflicts.status
                                ELSE 'in_review'
                            END,
                            suggested_action = coalesce(
                                knowledge_conflicts.suggested_action,
                                excluded.suggested_action
                            ),
                            updated_at = datetime('now','localtime')
                        """,
                        (
                            conflict_id,
                            claim_key,
                            cluster_id,
                            claim_key,
                            "runtime_detected_claim_signature_mismatch",
                        ),
                    )
                    # Link the detected claims first so a stale/missing claim id
                    # fails the entire transaction through the declared FK.
                    conn.executemany(
                        "INSERT OR IGNORE INTO conflict_claims (conflict_id, claim_id) "
                        "VALUES (?, ?)",
                        [(conflict_id, claim_id) for claim_id in claim_ids],
                    )

                    placeholders = ",".join("?" for _ in claim_ids)
                    detected_rows = conn.execute(
                        f"""
                        SELECT claim.claim_id, claim.concept_cluster_id,
                               claim.claim_key, claim.predicate, claim.scope_json,
                               cluster.normalized_name
                        FROM knowledge_claims AS claim
                        JOIN concept_clusters AS cluster
                          ON cluster.concept_cluster_id = claim.concept_cluster_id
                        WHERE claim.claim_id IN ({placeholders})
                        """,
                        claim_ids,
                    ).fetchall()
                    if len(detected_rows) != len(claim_ids):
                        raise RuntimeError(
                            "runtime governance conflict references missing claims"
                        )

                    if cross_cluster:
                        topic_keys = {
                            (
                                str(row["normalized_name"] or ""),
                                str(row["predicate"] or "").upper().strip(),
                                str(row["scope_json"] or ""),
                            )
                            for row in detected_rows
                        }
                        detected_clusters = {
                            str(row["concept_cluster_id"] or "")
                            for row in detected_rows
                        }
                        if len(topic_keys) != 1 or len(detected_clusters) < 2:
                            raise ValueError(
                                "cross-cluster runtime conflict is not one shared topic"
                            )
                        normalized_name, predicate, scope_json = next(iter(topic_keys))
                        try:
                            expected_claim_key = stable_cross_cluster_claim_key(
                                normalized_name,
                                predicate,
                                json.loads(scope_json),
                            )
                        except (TypeError, ValueError, json.JSONDecodeError) as exc:
                            raise ValueError(
                                "cross-cluster runtime conflict has invalid scope"
                            ) from exc
                        if (
                            claim_key != expected_claim_key
                            or cluster_id not in detected_clusters
                        ):
                            raise ValueError(
                                "cross-cluster runtime conflict identity is invalid"
                            )
                        target_rows = conn.execute(
                            """
                            SELECT claim.claim_id
                            FROM knowledge_claims AS claim
                            JOIN concept_clusters AS cluster
                              ON cluster.concept_cluster_id = claim.concept_cluster_id
                            WHERE cluster.normalized_name = ?
                              AND upper(claim.predicate) = ?
                              AND claim.scope_json = ?
                            """,
                            (normalized_name, predicate, scope_json),
                        ).fetchall()
                    else:
                        if any(
                            str(row["concept_cluster_id"] or "") != cluster_id
                            or str(row["claim_key"] or "") != claim_key
                            for row in detected_rows
                        ):
                            raise ValueError(
                                "runtime conflict claims do not belong to its slot"
                            )
                        target_rows = conn.execute(
                            """
                            SELECT claim_id
                            FROM knowledge_claims
                            WHERE concept_cluster_id = ? AND claim_key = ?
                            """,
                            (cluster_id, claim_key),
                        ).fetchall()

                    target_claim_ids = sorted({
                        str(row["claim_id"])
                        for row in target_rows
                    })
                    if not set(claim_ids).issubset(target_claim_ids):
                        raise RuntimeError(
                            "runtime conflict slot expansion lost detected claims"
                        )
                    conn.executemany(
                        "INSERT OR IGNORE INTO conflict_claims (conflict_id, claim_id) "
                        "VALUES (?, ?)",
                        [(conflict_id, claim_id) for claim_id in target_claim_ids],
                    )
                    target_placeholders = ",".join("?" for _ in target_claim_ids)
                    conn.execute(
                        f"UPDATE knowledge_claims "
                        f"SET conflict_status = 'blocking', "
                        f"updated_at = datetime('now','localtime') "
                        f"WHERE claim_id IN ({target_placeholders})",
                        target_claim_ids,
                    )
                    queued = conn.execute(
                        """
                        SELECT conflict_key, concept_cluster_id, claim_key,
                               severity, reason, status
                        FROM knowledge_conflicts
                        WHERE conflict_id = ?
                        """,
                        (conflict_id,),
                    ).fetchone()
                    linked_claim_ids = {
                        str(row["claim_id"])
                        for row in conn.execute(
                            "SELECT claim_id FROM conflict_claims WHERE conflict_id = ?",
                            (conflict_id,),
                        ).fetchall()
                    }
                    queued_claims = {
                        str(row["claim_id"]): row
                        for row in conn.execute(
                            """
                            SELECT claim.claim_id, claim.concept_cluster_id,
                                   claim.claim_key, claim.conflict_status
                            FROM knowledge_claims AS claim
                            JOIN conflict_claims AS link
                              ON link.claim_id = claim.claim_id
                            WHERE link.conflict_id = ?
                            """,
                            (conflict_id,),
                        ).fetchall()
                    }
                    if (
                        queued is None
                        or str(queued["conflict_key"] or "") != claim_key
                        or str(queued["concept_cluster_id"] or "") != cluster_id
                        or str(queued["claim_key"] or "") != claim_key
                        or str(queued["severity"] or "") != "blocking"
                        or not str(queued["reason"] or "").strip()
                        or str(queued["status"] or "") not in {"pending", "in_review"}
                        or linked_claim_ids != set(target_claim_ids)
                        or set(queued_claims) != linked_claim_ids
                        or any(
                            str(row["conflict_status"] or "") != "blocking"
                            for row in queued_claims.values()
                        )
                    ):
                        raise RuntimeError(
                            "runtime governance conflict queue verification failed"
                        )
                    persisted.append(conflict_id)
        return persisted

    def _doc_name_patterns(self, doc_name: str) -> List[str]:
        """生成文档名匹配候选，减少 Neo4j source_doc 与 rag_docs 文件名不一致的影响。"""
        name = (doc_name or "").strip()
        if not name:
            return []
        candidates = [name]
        candidates.extend(self._source_doc_aliases_for(name))
        if not name.endswith((".txt", ".md")):
            candidates.extend([f"{name}.txt", f"{name}.md"])
        base = re.sub(r"^(理论题库|实操题库|政策法规|无人机理论书籍)_", "", name)
        if base != name:
            candidates.append(base)
            if not base.endswith((".txt", ".md")):
                candidates.extend([f"{base}.txt", f"{base}.md"])
        seen = set()
        return [c for c in candidates if c and not (c in seen or seen.add(c))]

    def _source_doc_aliases_for(self, doc_name: str) -> List[str]:
        aliases = self._load_source_doc_aliases()
        direct = aliases.get(doc_name, [])
        normalized = doc_name.removesuffix(".txt").removesuffix(".md")
        if normalized != doc_name:
            direct = [*direct, *aliases.get(normalized, [])]
        return direct

    def _load_source_doc_aliases(self) -> Dict[str, List[str]]:
        if self._source_doc_aliases is not None:
            return self._source_doc_aliases
        if not _DEFAULT_ALIAS_PATH.exists():
            self._source_doc_aliases = {}
            return self._source_doc_aliases
        try:
            data = json.loads(_DEFAULT_ALIAS_PATH.read_text(encoding="utf-8"))
            raw_aliases = data.get("aliases", {})
            aliases: Dict[str, List[str]] = {}
            for key, values in raw_aliases.items():
                if isinstance(values, str):
                    values = [values]
                if isinstance(values, list):
                    cleaned = [str(v).strip() for v in values if str(v).strip()]
                    if cleaned:
                        aliases[str(key).strip()] = cleaned
            self._source_doc_aliases = aliases
        except Exception:
            self._source_doc_aliases = {}
        return self._source_doc_aliases

    def _escape_like(self, value: str) -> str:
        return value.replace("%", r"\%").replace("_", r"\_")

    # ============ 统计 ============

    def count_chunks(self) -> int:
        with self._lock:
            conn = self.connect()
            return conn.execute("SELECT COUNT(*) AS cnt FROM chunks").fetchone()["cnt"]

    def count_docs(self) -> int:
        with self._lock:
            conn = self.connect()
            return conn.execute("SELECT COUNT(DISTINCT doc_name) AS cnt FROM chunks").fetchone()["cnt"]

    def list_docs(self) -> List[Dict]:
        with self._lock:
            conn = self.connect()
            return [dict(r) for r in conn.execute(
                "SELECT doc_name, COUNT(*) AS chunk_count FROM chunks GROUP BY doc_name ORDER BY doc_name"
            ).fetchall()]

    def fingerprint(self) -> Dict:
        """返回 chunks 表指纹，用于判断外部索引是否陈旧。"""
        with self._lock:
            conn = self.connect()
            row = conn.execute(
                "SELECT COUNT(*) AS chunk_count, "
                "COUNT(DISTINCT doc_name) AS doc_count, "
                "COALESCE(SUM(LENGTH(text)), 0) AS text_bytes, "
                "COALESCE(MAX(created_at), '') AS max_created_at "
                "FROM chunks"
            ).fetchone()
            h = hashlib.sha256()
            samples = conn.execute(
                "SELECT chunk_id, doc_name, chunk_index, text "
                "FROM chunks ORDER BY chunk_id"
            )
            for item in samples:
                canonical_row = json.dumps(
                    [
                        item["chunk_id"],
                        item["doc_name"],
                        item["chunk_index"],
                        item["text"],
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                h.update(canonical_row.encode("utf-8"))
                h.update(b"\n")
            return {
                "chunk_count": row["chunk_count"],
                "doc_count": row["doc_count"],
                "text_bytes": row["text_bytes"],
                "max_created_at": row["max_created_at"],
                "schema": "chunks-v1",
                "fingerprint_algorithm": "sha256-jsonl-chunk-content-v1",
                "fingerprint": h.hexdigest(),
            }

    # ============ 维护 ============

    def delete_chunks_by_doc(self, doc_name: str):
        """删除某文档的所有 Chunk 记录"""
        with self._lock:
            conn = self.connect()
            conn.execute("DELETE FROM chunks WHERE doc_name = ?", (doc_name,))
            conn.commit()

    def vacuum(self):
        """回收空间"""
        with self._lock:
            conn = self.connect()
            conn.execute("VACUUM")
            conn.commit()

    def stats(self) -> Dict:
        """返回统计信息"""
        return {
            "db_path": self.db_path,
            "chunks": self.count_chunks(),
            "documents": self.count_docs(),
            "size_mb": round(Path(self.db_path).stat().st_size / 1024 / 1024, 2)
            if Path(self.db_path).exists() else 0,
        }


# ============ 快速测试 ============
