#!/usr/bin/env python3
"""
Dense 向量索引（SQLite 本地版）。

职责：
- 从 canonical SQLite chunks 读取文本并构建 bge-m3 embedding 索引
- 只保存 chunk_id、归一化向量和最小元数据，不保存 authoritative text
- 查询时返回标准 retriever result，由 ContextBuilder 统一回源取文本
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
import urllib.request as ureq
from array import array
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    from .sqlite_store import RagStore
except ImportError:
    from sqlite_store import RagStore


BASE_DIR = Path(__file__).parent.parent
DEFAULT_INDEX_PATH = BASE_DIR / "rag_index" / "dense_bge_m3.sqlite"
DEFAULT_CHUNK_DB = BASE_DIR / "rag_chunks.db"
INDEX_VERSION = "sqlite-dense-bge-m3-v1"
MODEL_NAME = "bge-m3"
MODEL_DIM = 1024


def ollama_embedding(text: str) -> List[float]:
    """调用本地 Ollama bge-m3 embedding。"""
    body = json.dumps({"model": MODEL_NAME, "prompt": text}).encode()
    req = ureq.Request(
        "http://127.0.0.1:11434/api/embeddings",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with ureq.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("embedding", [])


class DenseIndex:
    """本地 Dense chunk 向量索引。"""

    def __init__(self, index_path: str = None, db_path: str = None):
        self.index_path = Path(index_path or DEFAULT_INDEX_PATH)
        self.db_path = str(db_path or DEFAULT_CHUNK_DB)
        self._conn: Optional[sqlite3.Connection] = None
        self._opened_signature = None

    def _file_signature(self):
        try:
            stat = self.index_path.stat()
            return (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            return None

    def connect(self) -> sqlite3.Connection:
        current_signature = self._file_signature()
        if self._conn is not None and self._opened_signature is not None and current_signature != self._opened_signature:
            self.close()
        if self._conn is None:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.index_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._init_tables()
            self._opened_signature = self._file_signature()
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
            self._opened_signature = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _init_tables(self):
        conn = self._conn
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id    TEXT PRIMARY KEY,
                embedding   BLOB NOT NULL,
                dim         INTEGER NOT NULL,
                model       TEXT NOT NULL,
                doc_name    TEXT,
                chunk_index INTEGER DEFAULT 0,
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_dense_doc ON embeddings(doc_name, chunk_index);

            CREATE TABLE IF NOT EXISTS manifest (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()

    def exists(self) -> bool:
        if not self.index_path.exists():
            return False
        try:
            conn = self.connect()
            row = conn.execute("SELECT COUNT(*) AS cnt FROM embeddings").fetchone()
            return bool(row and row["cnt"] > 0)
        except Exception:
            return False

    def manifest(self) -> Dict:
        if not self.index_path.exists():
            return {}
        try:
            conn = self.connect()
            rows = conn.execute("SELECT key, value FROM manifest").fetchall()
            return {row["key"]: json.loads(row["value"]) for row in rows}
        except Exception:
            return {}

    def source_fingerprint(self) -> Dict:
        with RagStore(self.db_path) as store:
            store.init_tables()
            return store.fingerprint()

    def is_fresh(self) -> bool:
        if not self.exists():
            return False
        manifest = self.manifest()
        return (
            manifest.get("index") == INDEX_VERSION
            and manifest.get("model") == MODEL_NAME
            and manifest.get("dim") == MODEL_DIM
            and manifest.get("source") == self.source_fingerprint()
        )

    def ensure_fresh(self, auto_rebuild: bool = False, embed_func: Callable[[str], List[float]] = None) -> Dict:
        fresh = self.is_fresh()
        if fresh:
            return {"fresh": True, "rebuilt": False, "manifest": self.manifest()}
        if not auto_rebuild:
            return {"fresh": False, "rebuilt": False, "manifest": self.manifest()}
        stat = self.build(force=True, embed_func=embed_func)
        return {"fresh": True, "rebuilt": True, "manifest": self.manifest(), "build": stat}

    def build(self, force: bool = False, embed_func: Callable[[str], List[float]] = None) -> Dict:
        embed_func = embed_func or ollama_embedding
        if force and self.index_path.exists():
            self.close()
            self.index_path.unlink()
            wal = self.index_path.with_name(self.index_path.name + "-wal")
            shm = self.index_path.with_name(self.index_path.name + "-shm")
            for extra in (wal, shm):
                if extra.exists():
                    extra.unlink()

        conn = self.connect()
        conn.execute("DELETE FROM embeddings")
        conn.execute("DELETE FROM manifest")

        with RagStore(self.db_path) as store:
            store.init_tables()
            source = store.fingerprint()
            rows = store.connect().execute(
                "SELECT chunk_id, text, doc_name, chunk_index FROM chunks ORDER BY doc_name, chunk_index"
            ).fetchall()

        started = time.time()
        indexed = 0
        skipped = 0
        errors = []

        for i, row in enumerate(rows, start=1):
            text = (row["text"] or "").strip()
            if len(text) < 5:
                skipped += 1
                continue
            try:
                emb = self._embed_with_retry(embed_func, text)
                normed = self._normalize(emb)
                if len(normed) != MODEL_DIM:
                    raise ValueError(f"unexpected embedding dim {len(normed)}")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO embeddings
                    (chunk_id, embedding, dim, model, doc_name, chunk_index)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["chunk_id"],
                        self._pack(normed),
                        MODEL_DIM,
                        MODEL_NAME,
                        row["doc_name"] or "",
                        row["chunk_index"] or 0,
                    ),
                )
                indexed += 1
            except Exception as e:
                errors.append({"chunk_id": row["chunk_id"], "error": f"{type(e).__name__}: {e}"})
                if len(errors) >= 10:
                    raise RuntimeError(f"dense build failed too many chunks: {errors[:3]}")

            if i % 25 == 0:
                conn.commit()
                elapsed = max(time.time() - started, 0.1)
                print(f"  dense {i}/{len(rows)} | indexed={indexed} | {indexed / elapsed:.1f}/s", end="\r")

        conn.commit()
        manifest = {
            "index": INDEX_VERSION,
            "model": MODEL_NAME,
            "dim": MODEL_DIM,
            "source": source,
            "indexed_count": indexed,
            "skipped_count": skipped,
            "error_count": len(errors),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        for key, value in manifest.items():
            conn.execute(
                "INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        conn.commit()

        elapsed = time.time() - started
        return {
            "indexed": indexed,
            "skipped": skipped,
            "errors": len(errors),
            "elapsed_s": round(elapsed, 1),
            "rate": round(indexed / max(elapsed, 0.1), 2),
        }

    def search_by_embedding(self, embedding: List[float], limit: int = 10) -> List[Dict]:
        if not embedding:
            return []
        q = self._normalize(embedding)
        if not q:
            return []
        conn = self.connect()
        rows = conn.execute(
            "SELECT chunk_id, embedding, doc_name, chunk_index FROM embeddings"
        ).fetchall()
        scored = []
        for row in rows:
            vec = self._unpack(row["embedding"])
            score = self._dot(q, vec)
            scored.append({
                "chunk_id": row["chunk_id"],
                "score": float(score),
                "text": "",
                "doc_name": row["doc_name"] or "",
                "chunk_index": row["chunk_index"] or 0,
                "type": "chunk",
                "source": "dense",
            })
        scored.sort(key=lambda item: -item["score"])
        return scored[:limit]

    def stats(self) -> Dict:
        conn = self.connect()
        count = conn.execute("SELECT COUNT(*) AS cnt FROM embeddings").fetchone()["cnt"]
        return {
            "index_path": str(self.index_path),
            "embeddings": count,
            "fresh": self.is_fresh(),
            "manifest": self.manifest(),
        }

    def _embed_with_retry(self, embed_func: Callable[[str], List[float]], text: str, retries: int = 3) -> List[float]:
        last_error = None
        for attempt in range(retries):
            try:
                return embed_func(text)
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        raise last_error

    def _normalize(self, values: List[float]) -> List[float]:
        norm = math.sqrt(sum(float(v) * float(v) for v in values))
        if norm <= 0:
            return []
        return [float(v) / norm for v in values]

    def _dot(self, a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def _pack(self, values: List[float]) -> bytes:
        return array("f", values).tobytes()

    def _unpack(self, blob: bytes) -> List[float]:
        values = array("f")
        values.frombytes(blob)
        return values.tolist()


if __name__ == "__main__":
    idx = DenseIndex()
    print(json.dumps(idx.stats(), ensure_ascii=False, indent=2))
