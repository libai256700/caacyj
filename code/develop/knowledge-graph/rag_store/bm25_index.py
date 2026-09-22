#!/usr/bin/env python3
"""
BM25 稀疏检索模块（基于 Whoosh + jieba 中文分词）

从 SQLite canonical text 构建 BM25 倒排索引，
提供关键词精确召回能力，与 Dense 向量检索互补。
"""

import json, os, shutil, time
from pathlib import Path
from typing import List, Dict

from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh import scoring
from whoosh.analysis import Tokenizer, LowercaseFilter, Token
import jieba

try:
    from .sqlite_store import RagStore
except ImportError:
    from sqlite_store import RagStore

# ============ 中文分词器（jieba） ============
class JiebaTokenizer(Tokenizer):
    """基于 jieba 的中文分词器"""
    def __call__(self, text, **kwargs):
        for w in jieba.cut(text, cut_all=False):
            w = w.strip()
            if w:
                t = Token()
                t.text = w
                t.pos = 0
                t.startchar = 0
                t.endchar = 0
                yield t

_jieba_analyzer = JiebaTokenizer() | LowercaseFilter()

# ============ 配置 ============
BASE_DIR = Path(__file__).parent.parent
INDEX_DIR = BASE_DIR / "rag_index" / "bm25"
SQLITE_DB = str(BASE_DIR / "rag_chunks.db")
MANIFEST_NAME = "manifest.json"

DOCNAME_BOOST_RULES = [
    (
        ("民航法", "民用航空法", "新版民航法", "最新民航法"),
        ["中华人民共和国民用航空法", "2025修订", "2026-07-01施行"],
    ),
    (("客户管理", "跟进制度", "客户跟进", "执照培训项目"), ["客户管理与跟进制度"]),
    (("智能培训解决方案", "AI智学", "人工智能", "职业教育"), ["公司介绍", "公司产品介绍"]),
    (("侧风", "横风"), ["气象", "飞行原理与飞行性能", "无人机航空气象教材"]),
    (("云高", "能见度", "最低天气标准", "天气标准", "云层高度"), ["气象", "无人机航空气象教材", "无人机运行规范"]),
]

CIVIL_LAW_ARTICLE_PREFIX = "regulation:cn_civil_aviation_law_2025"
CIVIL_LAW_ARTICLE_BOOST_RULES = [
    {
        "anchors": ("民航法", "民用航空法", "新版民航法", "最新民航法", "最新版民航法"),
        "triggers": ("施行", "实施", "生效", "什么时候", "哪天", "日期"),
        "chunk_ids": [f"{CIVIL_LAW_ARTICLE_PREFIX}:art_262"],
    },
    {
        "anchors": ("民航法", "民用航空法", "新版民航法", "最新民航法", "最新版民航法"),
        "triggers": ("管制空域", "无人驾驶航空器管制空域", "无人机管制空域"),
        "chunk_ids": [
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_061",
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_076",
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_077",
        ],
    },
    {
        "anchors": ("民航法", "民用航空法", "新版民航法", "最新民航法", "最新版民航法", "公共航空运输"),
        "triggers": ("经营许可证", "运行合格证", "公共航空运输企业经营许可证"),
        "chunk_ids": [
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_102",
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_103",
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_104",
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_105",
        ],
    },
    {
        "anchors": ("民航法", "民用航空法", "新版民航法", "最新民航法", "最新版民航法", "民用航空器"),
        "triggers": ("适航证书", "适航许可", "特许飞行证书"),
        "chunk_ids": [
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_015",
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_031",
            f"{CIVIL_LAW_ARTICLE_PREFIX}:art_033",
        ],
    },
]

BROAD_TRAINING_EXCLUDE_TERMS = (
    "客户管理", "跟进制度", "客户跟进", "执照培训项目",
    "智能培训解决方案", "AI智学", "人工智能", "职业教育",
)

SCHEMA = Schema(
    chunk_id=ID(stored=True, unique=True),
    text=TEXT(stored=True, analyzer=_jieba_analyzer),
    doc_name=TEXT(stored=True, analyzer=_jieba_analyzer),
)


class BM25Index:
    """BM25 稀疏索引"""

    def __init__(self, index_dir: str = None, db_path: str = None):
        self.index_dir = index_dir or str(INDEX_DIR)
        self.db_path = db_path or SQLITE_DB
        self._ix = None
        self._manifest_path = Path(self.index_dir) / MANIFEST_NAME

    @property
    def ix(self):
        if self._ix is None:
            if not self.exists():
                raise FileNotFoundError(f"BM25 索引不存在，请先 build()")
            self._ix = self._open()
        return self._ix

    def exists(self) -> bool:
        try:
            return exists_in(self.index_dir)
        except Exception:
            return False

    def manifest(self) -> Dict:
        if not self._manifest_path.exists():
            return {}
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
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
        if not manifest:
            return False
        return (
            manifest.get("index") == "whoosh-bm25-jieba-v2-docname"
            and manifest.get("source") == self.source_fingerprint()
        )

    def ensure_fresh(self, auto_rebuild: bool = False) -> Dict:
        """校验 BM25 是否匹配 SQLite。可选自动重建。"""
        fresh = self.is_fresh()
        if fresh:
            return {"fresh": True, "rebuilt": False, "manifest": self.manifest()}
        if not auto_rebuild:
            return {"fresh": False, "rebuilt": False, "manifest": self.manifest()}
        stat = self.build(force=True)
        return {"fresh": True, "rebuilt": True, "manifest": self.manifest(), "build": stat}

    def _open(self):
        """打开索引，使用当前模块的 SCHEMA 避免 pickle 反序列化问题"""
        return open_dir(self.index_dir, schema=SCHEMA)

    def build(self, force: bool = False):
        """从 SQLite 全量构建 BM25 索引"""
        index_path = Path(self.index_dir)
        if force and index_path.exists():
            shutil.rmtree(index_path)
        index_path.mkdir(parents=True, exist_ok=True)

        ix = create_in(self.index_dir, SCHEMA)
        writer = ix.writer(limitmb=512)

        store = RagStore(self.db_path)
        store.init_tables()
        source = store.fingerprint()
        conn = store.connect()
        rows = conn.execute(
            "SELECT chunk_id, text, doc_name FROM chunks ORDER BY doc_name, chunk_index"
        ).fetchall()

        t0 = time.time()
        for i, row in enumerate(rows):
            text = row["text"] or ""
            if len(text.strip()) >= 5:
                writer.add_document(
                    chunk_id=row["chunk_id"],
                    text=text,
                    doc_name=row["doc_name"] or "",
                )
            if (i + 1) % 200 == 0:
                print(f"  {i+1}/{len(rows)}", end="\r")

        writer.commit(optimize=True)
        elapsed = time.time() - t0

        with ix.searcher() as s:
            dc = s.doc_count()
        manifest = {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "index": "whoosh-bm25-jieba-v2-docname",
            "source": source,
            "indexed_docs": dc,
        }
        self._manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        store.close()
        ix.close()
        return {"total_docs": dc, "elapsed_s": round(elapsed, 1)}

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        if not query.strip():
            return []
        searcher = self.ix.searcher(weighting=scoring.BM25F)
        try:
            parser = MultifieldParser(
                ["text", "chunk_id", "doc_name"],
                schema=self.ix.schema,
                group=OrGroup,
                fieldboosts={"doc_name": 3.0, "chunk_id": 1.5, "text": 1.0},
            )
            results = searcher.search(parser.parse(query), limit=limit)
            ranked = [{
                "chunk_id": r["chunk_id"],
                "text": r["text"],
                "score": float(r.score),
                "doc_name": r.get("doc_name", ""),
                "source": "bm25",
            } for r in results]
            ranked = self._merge_docname_boosts(query, ranked, limit)
            return self._merge_article_boosts(query, ranked, limit)
        finally:
            searcher.close()

    def search_by_keywords(self, keywords: List[str], limit: int = 20) -> List[Dict]:
        if not keywords:
            return []
        return self.search(" ".join(keywords), limit=limit)

    def _merge_docname_boosts(self, query: str, ranked: List[Dict], limit: int) -> List[Dict]:
        boost_terms = self._docname_boost_terms(query)
        if not boost_terms:
            return ranked[:limit]

        ranked = self._apply_existing_docname_boosts(ranked, boost_terms)
        seen = {item["chunk_id"] for item in ranked}
        max_score = max((float(item.get("score", 0)) for item in ranked), default=1.0)
        with RagStore(self.db_path) as store:
            boosted = self._docname_boost_candidates(store, query, boost_terms, max(limit * 40, 300))

        inserts = []
        for item in boosted:
            if item["chunk_id"] in seen:
                continue
            doc_name = item.get("doc_name", "")
            if not any(term in doc_name for term in boost_terms):
                continue
            insert_index = len(inserts)
            inserts.append({
                "chunk_id": item["chunk_id"],
                "text": item.get("text", ""),
                "score": max_score + 10.0 - insert_index,
                "doc_name": doc_name,
                "source": "bm25_docname",
                "boost": 0.04,
                "exact_match": "doc_name",
            })

        merged = inserts + ranked
        return merged[:limit]

    def _merge_article_boosts(self, query: str, ranked: List[Dict], limit: int) -> List[Dict]:
        chunk_ids = self._article_boost_chunk_ids(query)
        if not chunk_ids:
            return ranked[:limit]

        seen = {item["chunk_id"] for item in ranked}
        max_score = max((float(item.get("score", 0)) for item in ranked), default=1.0)
        with RagStore(self.db_path) as store:
            chunks = self._chunks_by_ids(store, chunk_ids)

        inserts = []
        for chunk_id in chunk_ids:
            if chunk_id in seen:
                continue
            item = chunks.get(chunk_id)
            if not item:
                continue
            insert_index = len(inserts)
            inserts.append({
                "chunk_id": item["chunk_id"],
                "text": item.get("text", ""),
                "score": max_score + 20.0 - insert_index,
                "doc_name": item.get("doc_name", ""),
                "source": "bm25_article",
                "boost": 0.06,
                "exact_match": "chunk_id",
            })

        return (inserts + ranked)[:limit]

    def _article_boost_chunk_ids(self, query: str) -> List[str]:
        chunk_ids = []
        for rule in CIVIL_LAW_ARTICLE_BOOST_RULES:
            if any(term in query for term in rule["anchors"]) and any(term in query for term in rule["triggers"]):
                chunk_ids.extend(rule["chunk_ids"])

        seen = set()
        return [chunk_id for chunk_id in chunk_ids if not (chunk_id in seen or seen.add(chunk_id))]

    def _chunks_by_ids(self, store: RagStore, chunk_ids: List[str]) -> Dict[str, Dict]:
        if not chunk_ids:
            return {}
        conn = store.connect()
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = conn.execute(
            f"SELECT chunk_id, text, doc_name, chunk_index FROM chunks WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        return {row["chunk_id"]: dict(row) for row in rows}

    def _apply_existing_docname_boosts(self, ranked: List[Dict], boost_terms: List[str]) -> List[Dict]:
        boosted = []
        for item in ranked:
            doc_name = item.get("doc_name", "")
            if any(term in doc_name for term in boost_terms):
                item = {**item}
                item["boost"] = max(float(item.get("boost", 0.0)), 0.04)
                item["exact_match"] = "doc_name"
            boosted.append(item)
        return boosted

    def _docname_boost_terms(self, query: str) -> List[str]:
        boost_terms = []
        for triggers, terms in DOCNAME_BOOST_RULES:
            if any(term in query for term in triggers):
                boost_terms.extend(terms)

        if any(term in query for term in ("价格", "价格表", "费用", "收费", "多少钱")):
            boost_terms.extend(["价格表", "价格"])
        if any(term in query for term in ("地址", "电话", "联系", "联系方式")):
            boost_terms.append("公司介绍")

        is_broad_training = any(term in query for term in ("课程", "产品"))
        is_excluded = any(term in query for term in BROAD_TRAINING_EXCLUDE_TERMS)
        if is_broad_training and not is_excluded:
            boost_terms.extend(["公司产品介绍", "新员工培训资料", "价格表"])

        seen = set()
        return [term for term in boost_terms if term and not (term in seen or seen.add(term))]

    def _docname_boost_candidates(
        self,
        store: RagStore,
        query: str,
        boost_terms: List[str],
        limit: int,
    ) -> List[Dict]:
        relevance_terms = self._query_relevance_terms(query)
        conn = store.connect()
        candidates: Dict[str, Dict] = {}
        for term in boost_terms:
            rows = conn.execute(
                "SELECT chunk_id, text, doc_name, chunk_index FROM chunks "
                "WHERE doc_name LIKE ? ESCAPE '\\' "
                "ORDER BY doc_name, chunk_index LIMIT ?",
                (f"%{self._escape_like(term)}%", limit),
            ).fetchall()
            for row in rows:
                item = dict(row)
                text = f"{item.get('doc_name', '')}\n{item.get('text', '')}"
                item["_score"] = sum(text.count(term) for term in relevance_terms)
                candidates.setdefault(item["chunk_id"], item)

        ranked = sorted(
            candidates.values(),
            key=lambda item: (-item.get("_score", 0), item.get("doc_name", ""), item.get("chunk_index", 0)),
        )
        for item in ranked:
            item.pop("_score", None)
        return ranked[:limit]

    def _query_relevance_terms(self, query: str) -> List[str]:
        phrase_terms = [
            phrase
            for phrase in ("无人驾驶航空器", "民用航空法", "民航法")
            if phrase in query
        ]
        query_terms = [
            term.strip()
            for term in jieba.cut(query, cut_all=False)
            if len(term.strip()) >= 2
        ]
        weak_terms = {"新版", "最新", "什么", "哪些", "如何", "要求", "规定"}
        seen = set()
        return [
            term
            for term in phrase_terms + query_terms
            if term and term not in weak_terms and not (term in seen or seen.add(term))
        ]

    @staticmethod
    def _escape_like(term: str) -> str:
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def close(self):
        if self._ix:
            self._ix.close()
            self._ix = None


if __name__ == "__main__":
    import sys
    idx = BM25Index()

    if "--rebuild" in sys.argv or not idx.exists():
        print(f"{'🔧 重建' if '--rebuild' in sys.argv else '⏳ 首次构建'} BM25 索引...")
        stat = idx.build(force="--rebuild" in sys.argv)
        print(f"   ✅ {stat}")

    tests = [
        "培训 课程 价格",
        "云技科技 无人机 培训",
        "CCAR 飞行 空域 管制",
        "CAAC 实操 考试 考核",
    ]
    for q in tests:
        r = idx.search(q, limit=5)
        print(f"\n🔍 '{q}' → {len(r)} 条")
        for x in r[:5]:
            print(f"   {x['score']:.3f} | {x['chunk_id'][:45]}")
