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


class RagStore:
    """RAG 文本存储，基于 SQLite"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._source_doc_aliases: Optional[Dict[str, List[str]]] = None

    # ============ 连接管理 ============

    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
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

    def init_tables(self):
        """初始化 Chunk 表 + 文档表（幂等，可重复调用）"""
        with self._lock:
            conn = self.connect()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id   TEXT PRIMARY KEY,
                    text       TEXT NOT NULL,
                    doc_name   TEXT NOT NULL,
                    chunk_index INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_name);
                CREATE INDEX IF NOT EXISTS idx_chunks_doc_idx ON chunks(doc_name, chunk_index);

                CREATE TABLE IF NOT EXISTS documents (
                    doc_name    TEXT PRIMARY KEY,
                    doc_path    TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    updated_at  TEXT DEFAULT (datetime('now','localtime'))
                );
            """)
            conn.commit()

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

    def _doc_name_patterns(self, doc_name: str) -> List[str]:
        """生成文档名匹配候选，减少 Neo4j source_doc 与 rag_docs 文件名不一致的影响。"""
        name = (doc_name or "").strip()
        if not name:
            return []
        candidates = [name]
        candidates.extend(self._source_doc_aliases_for(name))
        if not name.endswith((".txt", ".md")):
            candidates.extend([f"{name}.txt", f"{name}.md"])
        base = re.sub(r"^(企业信息|人事制度|理论题库|政策法规|无人机理论书籍)_", "", name)
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
            samples = conn.execute(
                "SELECT chunk_id, doc_name, chunk_index, LENGTH(text) AS len "
                "FROM chunks ORDER BY chunk_id"
            ).fetchall()
            h = hashlib.sha256()
            for item in samples:
                h.update(f"{item['chunk_id']}|{item['doc_name']}|{item['chunk_index']}|{item['len']}\n".encode("utf-8"))
            return {
                "chunk_count": row["chunk_count"],
                "doc_count": row["doc_count"],
                "text_bytes": row["text_bytes"],
                "max_created_at": row["max_created_at"],
                "schema": "chunks-v1",
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
if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_path = f.name

    store = RagStore(test_path)
    store.init_tables()

    # 写入测试数据
    store.store_chunks_batch([
        {"chunk_id": "doc_a_1", "text": "这是文档A的第一个段落", "doc_name": "doc_a.txt", "chunk_index": 0},
        {"chunk_id": "doc_a_2", "text": "这是文档A的第二个段落", "doc_name": "doc_a.txt", "chunk_index": 1},
        {"chunk_id": "doc_b_1", "text": "文档B的内容", "doc_name": "doc_b.txt", "chunk_index": 0},
    ])

    # 读取测试
    t = store.get_chunk_text("doc_a_2")
    assert t == "这是文档A的第二个段落", f"get_chunk_text failed: {t}"

    batch = store.get_chunks_batch(["doc_a_1", "doc_b_1", "nonexistent"])
    assert len(batch) == 2, f"batch should return 2, got {len(batch)}"

    stats = store.stats()
    print(f"✅ SQLiteStore 测试通过: {stats}")

    Path(test_path).unlink()
