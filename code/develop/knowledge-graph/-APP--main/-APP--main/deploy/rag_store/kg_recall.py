#!/usr/bin/env python3
"""
Neo4j 知识图谱召回模块

职责：实体匹配 → 关系扩展 → 多跳路径 → 收集 chunk_id

Neo4j 不自存储文本。返回的 chunk_id 由调用方通过 SQLite 回源取文本。
"""

import copy
import hashlib
import json, os, sys
import time
from pathlib import Path
from typing import List, Dict, Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

try:
    from .sqlite_store import RagStore
    from .semantic_schema import SCHEMA_VERSION, domain_for_doc_name, infer_domains
except ImportError:
    from sqlite_store import RagStore
    from semantic_schema import SCHEMA_VERSION, domain_for_doc_name, infer_domains

sys.path.insert(0, str(Path(__file__).parent.parent))
from neo4j_runtime import DEFAULT_NEO4J_URI, DEFAULT_NEO4J_USER, ensure_runtime_secret_files, resolve_neo4j_password

# ============ 配置 ============
BASE_DIR = Path(__file__).parent.parent
NEO4J_URI = DEFAULT_NEO4J_URI
NEO4J_USER = DEFAULT_NEO4J_USER
ensure_runtime_secret_files()
NEO4J_PASS = resolve_neo4j_password()

KG_RECALL_CACHE_TTL = float(os.environ.get("KG_RECALL_CACHE_TTL", "120"))
KG_RECALL_CACHE_MAX = int(os.environ.get("KG_RECALL_CACHE_MAX", "128"))
KG_RECALL_MAX_RESULTS = int(os.environ.get("KG_RECALL_MAX_RESULTS", "20"))
KG_RECALL_MAX_PATHS = int(os.environ.get("KG_RECALL_MAX_PATHS", "10"))
KG_RECALL_MATCH_LIMIT = int(os.environ.get("KG_RECALL_MATCH_LIMIT", "3"))
KG_RECALL_ANCHOR_LIMIT = int(os.environ.get("KG_RECALL_ANCHOR_LIMIT", "5"))
KG_RECALL_ONE_HOP_LIMIT = int(os.environ.get("KG_RECALL_ONE_HOP_LIMIT", "30"))
KG_RECALL_TWO_HOP_LIMIT = int(os.environ.get("KG_RECALL_TWO_HOP_LIMIT", "20"))
KG_RECALL_REVERSE_MATCH_PER_CHUNK = int(
    os.environ.get("KG_RECALL_REVERSE_MATCH_PER_CHUNK", "3")
)
KG_RECALL_REVERSE_MATCH_LIMIT = int(
    os.environ.get("KG_RECALL_REVERSE_MATCH_LIMIT", "10")
)
KG_RECALL_EXCLUDE_UNRESOLVED_EVIDENCE = os.environ.get("KG_RECALL_EXCLUDE_UNRESOLVED_EVIDENCE", "1") != "0"
BIDIRECTIONAL_HIERARCHY_REL_TYPES = ["CONTAINS", "PART_OF", "SUBCLASS_OF"]
STRUCTURAL_ENTITY_TYPES = frozenset({"Chapter", "Section"})
APPROVED_GOVERNANCE_REVIEW_STATUSES = ("approved", "auto_approved")
BLOCKED_CONFLICT_STATUS_PREFIXES = (
    "pending",
    "in_review",
    "unresolved",
    "blocking",
    "rejected",
)
BLOCKED_EVIDENCE_STATUS_PREFIXES = (
    "pending",
    "in_review",
    "unresolved",
    "rejected",
)
EXACT_EVIDENCE_ORIGINS = frozenset({
    "entity_source_chunk_ids",
    "relationship_source_chunk_ids",
    "path_node_source_chunk_ids",
})
EXACT_ENTITY_MATCH_MODES = frozenset({"semantic_key", "entity_id"})
EVIDENCE_GOVERNED_REL_TYPES = [
    "REQUIRES",
    "REGULATES",
    "REFERS_TO",
    "HAS_PROPERTY",
    "REQUIRES_SKILL",
    "HAS_CLASS",
]


TYPE_EXPR = "coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity')"
FROM_TYPE_EXPR = "coalesce([label IN labels(a) WHERE label <> 'Entity'][0], 'Entity')"
TO_TYPE_EXPR = "coalesce([label IN labels(b) WHERE label <> 'Entity'][0], 'Entity')"


class KGRecall:
    """Neo4j 图谱召回引擎"""
    
    def __init__(self, db_path: str = None):
        self._driver = None
        self._store = RagStore(db_path)
        self._store.init_tables()
        self._max_hops = 2
        self._max_results = max(1, KG_RECALL_MAX_RESULTS)
        self._max_paths = max(1, KG_RECALL_MAX_PATHS)
        self._cache_ttl = max(0.0, KG_RECALL_CACHE_TTL)
        self._cache_max = max(0, KG_RECALL_CACHE_MAX)
        self._cache: Dict[str, tuple[float, Dict]] = {}
    
    @property
    def driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        return self._driver
    
    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None
        self._store.close()
    
    def recall(
        self,
        entities: List[Dict],
        intent: str,
        keywords: List[str],
        query: str,
        semantic_plan: Optional[Dict] = None,
    ) -> Dict:
        """
        主入口：根据抽取的实体 + 意图，从图谱中召回相关结果
        
        Returns:
        {
            "chunk_ids": [chunk_id列表],
            "paths": [{path描述}],
            "matched_entities": [{entity详情}],
            "total": int
        }
        """
        cache_key = self._cache_key(entities, intent, keywords, query, semantic_plan)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        
        try:
            matched = self._match_entities(entities) if entities else []
            if not matched:
                matched = self._match_anchor_entities(query=query, intent=intent, keywords=keywords)
            if not matched:
                return {"chunk_ids": [], "paths": [], "matched_entities": [], "total": 0}
            
            domains = (semantic_plan or {}).get("domains") or infer_domains(query, intent, " ".join(keywords or []))
            relation_hints = (semantic_plan or {}).get("graph_query_plan", {}).get("relation_hints", [])
            paths = self._expand_relationships(matched, domains=domains, relation_hints=relation_hints)
            chunk_ids = self._collect_chunk_ids(matched, paths, intent=intent, keywords=keywords, query=query)
            evidence_bindings = self._build_evidence_bindings(chunk_ids[:self._max_results], paths, matched, domains)
            
            result = {
                "chunk_ids": chunk_ids[:self._max_results],
                "paths": paths[:self._max_paths],
                "matched_entities": matched[:10],
                "domains": domains,
                "relation_hints": relation_hints,
                "evidence_required": ["source_doc", "source_chunk_ids", "sqlite_chunk_text"],
                "evidence_bindings": evidence_bindings,
                "total": len(chunk_ids),
                "cache_hit": False,
            }
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[KGRecall] 召回失败: {e}")
            return {
                "chunk_ids": [],
                "paths": [],
                "matched_entities": [],
                "domains": [],
                "relation_hints": [],
                "evidence_required": ["source_doc", "source_chunk_ids", "sqlite_chunk_text"],
                "evidence_bindings": [],
                "total": 0,
                "cache_hit": False,
            }

    def _cache_key(
        self,
        entities: List[Dict],
        intent: str,
        keywords: List[str],
        query: str,
        semantic_plan: Optional[Dict],
    ) -> str:
        payload = {
            "entities": sorted(
                (
                    str(e.get("semantic_key") or ""),
                    str(e.get("entity_id") or ""),
                    str(e.get("name") or ""),
                    str(e.get("type") or ""),
                    str(e.get("domain") or ""),
                )
                for e in entities or []
                if isinstance(e, dict)
                and (e.get("semantic_key") or e.get("entity_id") or e.get("name"))
            ),
            "intent": intent or "",
            "keywords": sorted(str(kw) for kw in keywords or [] if kw),
            "query": query or "",
            "domains": sorted((semantic_plan or {}).get("domains") or []),
            "relation_hints": sorted((semantic_plan or {}).get("graph_query_plan", {}).get("relation_hints", [])),
            "max_results": self._max_results,
            "max_paths": self._max_paths,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[Dict]:
        if self._cache_ttl <= 0 or self._cache_max <= 0:
            return None
        item = self._cache.get(key)
        if not item:
            return None
        cached_at, value = item
        if time.time() - cached_at > self._cache_ttl:
            self._cache.pop(key, None)
            return None
        result = copy.deepcopy(value)
        result["cache_hit"] = True
        return result

    def _cache_set(self, key: str, value: Dict) -> None:
        if self._cache_ttl <= 0 or self._cache_max <= 0:
            return
        if len(self._cache) >= self._cache_max:
            oldest_key = min(self._cache, key=lambda item: self._cache[item][0])
            self._cache.pop(oldest_key, None)
        self._cache[key] = (time.time(), copy.deepcopy(value))
    
    @staticmethod
    def _governance_allowed(row: Dict, prefixes: tuple[str, ...] = ("",)) -> bool:
        """Allow legacy rows, but require every explicit review status to be approved."""
        for prefix in prefixes:
            stem = f"{prefix}_" if prefix else ""
            review_status = str(row.get(f"{stem}review_status") or "").strip().lower()
            if (
                review_status
                and review_status not in APPROVED_GOVERNANCE_REVIEW_STATUSES
            ):
                return False
            conflict_status = str(
                row.get(f"{stem}conflict_status") or ""
            ).strip().lower()
            if conflict_status.startswith(BLOCKED_CONFLICT_STATUS_PREFIXES):
                return False
            evidence_status = str(
                row.get(f"{stem}evidence_governance_status") or ""
            ).strip().lower()
            if evidence_status.startswith(BLOCKED_EVIDENCE_STATUS_PREFIXES):
                return False
        return True

    @staticmethod
    def _governance_predicate(alias: str) -> str:
        review = (
            f"toLower(toString(coalesce({alias}.review_status, '')))"
        )
        conflict = (
            f"toLower(toString(coalesce({alias}.conflict_status, '')))"
        )
        evidence = (
            "toLower(toString(coalesce("
            f"{alias}.evidence_governance_status, '')))"
        )
        checks = [
            f"({review} = '' OR {review} IN ['approved', 'auto_approved'])",
            f"NOT ({conflict} STARTS WITH 'pending')",
            f"NOT ({conflict} STARTS WITH 'in_review')",
            f"NOT ({conflict} STARTS WITH 'unresolved')",
            f"NOT ({conflict} STARTS WITH 'blocking')",
            f"NOT ({conflict} STARTS WITH 'rejected')",
            f"NOT ({evidence} STARTS WITH 'pending')",
            f"NOT ({evidence} STARTS WITH 'in_review')",
            f"NOT ({evidence} STARTS WITH 'unresolved')",
            f"NOT ({evidence} STARTS WITH 'rejected')",
        ]
        return " AND ".join(checks)

    @staticmethod
    def _match_identity(row: Dict) -> str:
        return str(
            row.get("semantic_key")
            or row.get("entity_id")
            or row.get("node_ref")
            or row.get("id")
            or f"{row.get('type', '')}|{row.get('name', '')}|{row.get('source_doc', '')}"
        )

    def _match_entities(self, entities: List[Dict]) -> List[Dict]:
        """Match stable identities first; use name matching only as a compatibility fallback."""
        projection = """
            RETURN elementId(n) AS node_ref,
                   coalesce(n.name, n.canonical_name, '') AS name,
                   """ + TYPE_EXPR + """ AS type,
                   coalesce(n.description, n.evidence, '') AS description,
                   n.source_doc AS source_doc,
                   n.source_chunk_ids AS source_chunk_ids,
                   n.semantic_key AS semantic_key,
                   n.entity_id AS entity_id,
                   n.domain AS domain,
                   n.canonical_name AS canonical_name,
                   n.id AS id,
                   n.review_status AS review_status,
                   n.conflict_status AS conflict_status,
                   n.evidence_governance_status AS evidence_governance_status
        """
        governance = self._governance_predicate("n")
        matched = []

        with self.driver.session() as s:
            for raw_entity in entities:
                entity = raw_entity if isinstance(raw_entity, dict) else {"name": str(raw_entity or "")}
                name = str(entity.get("name") or "").strip()
                semantic_key = str(entity.get("semantic_key") or "").strip()
                entity_id = str(entity.get("entity_id") or "").strip()
                rows = []
                match_mode = ""

                if semantic_key:
                    rows = s.run(
                        "MATCH (n) WHERE n.semantic_key = $semantic_key AND "
                        + governance
                        + projection
                        + " ORDER BY elementId(n) LIMIT 1",
                        semantic_key=semantic_key,
                    ).data()
                    match_mode = "semantic_key"

                if not rows and entity_id:
                    rows = s.run(
                        "MATCH (n) WHERE n.entity_id = $entity_id AND "
                        + governance
                        + projection
                        + " ORDER BY elementId(n) LIMIT 1",
                        entity_id=entity_id,
                    ).data()
                    match_mode = "entity_id"

                if not rows and name and not (semantic_key or entity_id):
                    # Name matching is compatibility-only. Modern nodes must be
                    # reached through semantic_key/entity_id so a partial name
                    # cannot manufacture an exact cross-book binding.
                    legacy_only = True
                    name_query = (
                        """
                        MATCH (n)
                        WHERE (
                          toLower(coalesce(n.name, '')) = toLower($name)
                          OR toLower(coalesce(n.name, '')) CONTAINS toLower($name)
                        )
                        AND (
                          NOT $legacy_only
                          OR (
                            n.semantic_key IS NULL
                            AND n.entity_id IS NULL
                          )
                        )
                        AND """
                        + governance
                        + """
                        WITH n,
                             CASE WHEN toLower(coalesce(n.name, '')) = toLower($name) THEN 0 ELSE 1 END AS name_rank,
                             CASE WHEN $entity_type <> ''
                                       AND ($entity_type IN labels(n) OR n.type = $entity_type)
                                  THEN 0 ELSE 1 END AS type_rank
                        ORDER BY name_rank, type_rank,
                                 coalesce(
                                   n.semantic_key,
                                   n.entity_id,
                                   n.id,
                                   elementId(n)
                                 )
                        """
                        + projection
                        + " LIMIT $limit"
                    )
                    rows = s.run(
                        name_query,
                        name=name,
                        entity_type=str(entity.get("type") or ""),
                        legacy_only=legacy_only,
                        limit=KG_RECALL_MATCH_LIMIT,
                    ).data()
                    match_mode = "legacy_name"

                for row in rows:
                    if match_mode == "legacy_name" and (
                        row.get("semantic_key") or row.get("entity_id")
                    ):
                        continue
                    if self._governance_allowed(row):
                        row["match_mode"] = match_mode
                        matched.append(row)

        seen = set()
        unique = []
        for row in matched:
            key = self._match_identity(row)
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique

    def _match_anchor_entities(self, query: str, intent: str, keywords: List[str]) -> List[Dict]:
        """没有显式实体时，用关键词和文档锚点从图谱中找少量入口节点。"""
        anchors = self._anchor_terms(query, intent, keywords)
        if not anchors:
            return []

        governance = self._governance_predicate("n")
        with self.driver.session() as s:
            rows = s.run("""
                MATCH (n)
                WHERE NOT n:Document
                  AND """ + governance + """
                  AND any(term IN $anchors WHERE
                    toLower(coalesce(n.name, n.canonical_name, "")) CONTAINS toLower(term)
                    OR toLower(coalesce(n.source_doc, "")) CONTAINS toLower(term)
                    OR toLower(coalesce(n.description, n.evidence, "")) CONTAINS toLower(term)
                  )
                WITH n,
                     reduce(score = 0, term IN $anchors |
                       score
                       + CASE WHEN toLower(coalesce(n.name, n.canonical_name, "")) = toLower(term) THEN 5 ELSE 0 END
                       + CASE WHEN toLower(coalesce(n.name, n.canonical_name, "")) CONTAINS toLower(term) THEN 3 ELSE 0 END
                       + CASE WHEN toLower(coalesce(n.source_doc, "")) CONTAINS toLower(term) THEN 2 ELSE 0 END
                       + CASE WHEN toLower(coalesce(n.description, n.evidence, "")) CONTAINS toLower(term) THEN 1 ELSE 0 END
                     ) AS score
                RETURN elementId(n) AS node_ref,
                       coalesce(n.name, n.canonical_name, '') AS name,
                       """ + TYPE_EXPR + """ AS type,
                       coalesce(n.description, n.evidence, '') AS description,
                       n.source_doc AS source_doc,
                       n.source_chunk_ids AS source_chunk_ids,
                       n.semantic_key AS semantic_key,
                       n.entity_id AS entity_id,
                       n.domain AS domain,
                       n.canonical_name AS canonical_name,
                       n.id AS id,
                       n.review_status AS review_status,
                       n.conflict_status AS conflict_status,
                       n.evidence_governance_status AS evidence_governance_status,
                       score
                ORDER BY score DESC, size(coalesce(n.name, n.canonical_name, "")) ASC
                LIMIT $limit
            """, anchors=anchors, limit=KG_RECALL_ANCHOR_LIMIT).data()
        matched = []
        for row in rows:
            if self._governance_allowed(row):
                row["match_mode"] = "anchor_substring"
                matched.append(row)
        return matched

    def _match_entities_by_chunk_ids(self, chunk_ids: List[str]) -> List[Dict]:
        """Reverse-map retrieved SQLite chunks to modern, governed graph nodes."""
        chunk_ids = list(dict.fromkeys(self._normalize_chunk_ids(chunk_ids)))
        if not chunk_ids:
            return []
        governance = self._governance_predicate("n")
        query = (
            """
            MATCH (n)
            WHERE NOT n:Document AND NOT n:Chunk AND NOT n:ChunkRef
              AND (n.semantic_key IS NOT NULL
                   OR n.entity_id IS NOT NULL)
              AND $chunk_id IN coalesce(n.source_chunk_ids, [])
              AND """
            + governance
            + """
            WITH n,
                 CASE
                   WHEN n:Chapter OR n.type = 'Chapter' THEN 2
                   WHEN n:Section OR n.type = 'Section' THEN 1
                   ELSE 0
                 END AS structural_rank
            ORDER BY structural_rank,
                     coalesce(
                       n.semantic_key,
                       n.entity_id,
                       n.id,
                       elementId(n)
                     )
            RETURN elementId(n) AS node_ref,
                   coalesce(n.name, n.canonical_name, '') AS name,
                   """
            + TYPE_EXPR
            + """ AS type,
                   coalesce(n.description, n.evidence, '') AS description,
                   n.source_doc AS source_doc,
                   n.source_chunk_ids AS source_chunk_ids,
                   n.semantic_key AS semantic_key,
                   n.entity_id AS entity_id,
                   n.domain AS domain,
                   n.canonical_name AS canonical_name,
                   n.id AS id,
                   n.review_status AS review_status,
                   n.conflict_status AS conflict_status,
                   n.evidence_governance_status AS evidence_governance_status
            LIMIT $limit
            """
        )
        rows_by_chunk: list[list[Dict]] = []
        with self.driver.session() as session:
            for chunk_id in chunk_ids:
                rows = session.run(
                    query,
                    chunk_id=chunk_id,
                    limit=max(1, KG_RECALL_REVERSE_MATCH_PER_CHUNK),
                ).data()
                governed = []
                for row in rows:
                    if not self._governance_allowed(row):
                        continue
                    if chunk_id not in self._normalize_chunk_ids(
                        row.get("source_chunk_ids")
                    ):
                        continue
                    governed.append(row)
                governed.sort(
                    key=lambda row: (
                        1 if str(row.get("type") or "") in STRUCTURAL_ENTITY_TYPES else 0,
                        1 if str(row.get("type") or "") == "Chapter" else 0,
                        self._match_identity(row),
                    )
                )
                rows_by_chunk.append(governed)

        selected: dict[str, Dict] = {}
        selection_order: list[str] = []
        per_chunk_limit = max(1, KG_RECALL_REVERSE_MATCH_PER_CHUNK)
        global_limit = max(1, KG_RECALL_REVERSE_MATCH_LIMIT)
        for ordinal in range(per_chunk_limit):
            for chunk_rank, rows in enumerate(rows_by_chunk):
                if ordinal >= len(rows):
                    continue
                row = rows[ordinal]
                identity = self._match_identity(row)
                existing = selected.get(identity)
                if existing is None:
                    if len(selection_order) >= global_limit:
                        continue
                    existing = dict(row)
                    existing["match_mode"] = (
                        "semantic_key" if row.get("semantic_key") else "entity_id"
                    )
                    existing["match_origin"] = "retrieved_chunk"
                    existing["matched_chunk_ids"] = []
                    existing["retrieved_chunk_rank"] = chunk_rank
                    selected[identity] = existing
                    selection_order.append(identity)
                chunk_id = chunk_ids[chunk_rank]
                if chunk_id not in existing["matched_chunk_ids"]:
                    existing["matched_chunk_ids"].append(chunk_id)
                existing["retrieved_chunk_rank"] = min(
                    int(existing.get("retrieved_chunk_rank") or 0), chunk_rank
                )
        return [selected[identity] for identity in selection_order]

    def augment_from_retrieved_chunks(
        self,
        kg_result: Dict,
        chunk_ids: List[str],
        *,
        query: str,
        intent: str,
        keywords: List[str],
        semantic_plan: Optional[Dict] = None,
    ) -> Dict:
        """Add exact graph coordinates discovered from top RAG chunks."""
        candidate_ids = list(dict.fromkeys(self._normalize_chunk_ids(chunk_ids)))[:10]
        if not candidate_ids:
            return kg_result
        matched = self._match_entities_by_chunk_ids(candidate_ids)
        if not matched:
            return kg_result
        domains = (
            (semantic_plan or {}).get("domains")
            or kg_result.get("domains")
            or infer_domains(query, intent, " ".join(keywords or []))
        )
        relation_hints = (
            (semantic_plan or {}).get("graph_query_plan", {}).get("relation_hints", [])
        )
        paths = self._expand_relationships(
            matched,
            domains=domains,
            relation_hints=relation_hints,
        )
        exact_chunk_ids = self._collect_chunk_ids(
            matched,
            paths,
            intent=intent,
            keywords=keywords,
            query=query,
        )
        preferred = [item for item in candidate_ids if item in set(exact_chunk_ids)]
        ordered_chunk_ids = list(dict.fromkeys(preferred + exact_chunk_ids))
        bindings = self._build_evidence_bindings(
            ordered_chunk_ids[: self._max_results],
            paths,
            matched,
            domains,
        )

        result = dict(kg_result)
        result["matched_entities"] = self._dedupe_by_identity(
            matched + list(kg_result.get("matched_entities") or [])
        )
        result["paths"] = self._dedupe_paths(
            paths + list(kg_result.get("paths") or [])
        )
        result["chunk_ids"] = list(
            dict.fromkeys(
                ordered_chunk_ids + list(kg_result.get("chunk_ids") or [])
            )
        )[: self._max_results]
        by_chunk = {
            str(binding.get("chunk_id") or ""): binding
            for binding in list(kg_result.get("evidence_bindings") or [])
            if binding.get("chunk_id")
        }
        for binding in reversed(bindings):
            by_chunk[str(binding.get("chunk_id") or "")] = binding
        result["evidence_bindings"] = [
            by_chunk[chunk_id]
            for chunk_id in result["chunk_ids"]
            if chunk_id in by_chunk
        ]
        result["domains"] = domains
        result["relation_hints"] = relation_hints
        result["total"] = len(result["chunk_ids"])
        return result

    @classmethod
    def _dedupe_by_identity(cls, rows: List[Dict]) -> List[Dict]:
        seen = set()
        return [
            row
            for row in rows
            if (identity := cls._match_identity(row))
            and not (identity in seen or seen.add(identity))
        ]

    @staticmethod
    def _dedupe_paths(paths: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for path in paths:
            key = (
                path.get("from_node_ref"),
                path.get("relationship_ref") or path.get("relation"),
                path.get("to_node_ref"),
                path.get("direction"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _anchor_terms(self, query: str, intent: str, keywords: List[str]) -> List[str]:
        q = query or ""
        terms = []
        if any(term in q for term in ("民航法", "民用航空法")):
            terms.extend(["民用航空法", "无人驾驶航空器", "航空人员", "适航许可"])
        if "CCAR-92" in q or "92部" in q:
            terms.extend(["CCAR-92", "飞行空域", "运行安全管理规则"])
        if any(term in q for term in ("空域", "管制空域", "低空")):
            terms.extend(["空域管理", "管制空域", "低空空域"])
        if any(term in q for term in ("起飞前", "检查", "失联", "风切变", "中空", "BEC")):
            terms.extend(["起飞前检查", "失联", "风切变", "中空飞行", "BEC模块"])
        terms.extend(kw for kw in keywords if kw and 2 <= len(kw) <= 20)

        seen = set()
        unique = [
            str(term).strip()
            for term in terms
            if str(term).strip()
            and not (
                str(term).strip() in seen
                or seen.add(str(term).strip())
            )
        ]
        # Query rewriters often put generic tokens such as “系统” before the
        # discriminating phrases.  The anchor budget is intentionally small,
        # so preserve terms that occur in the user's question and rank the
        # more specific phrases first; otherwise modern textbook nodes can be
        # crowded out before Neo4j sees their canonical names.
        indexed = list(enumerate(unique))
        indexed.sort(
            key=lambda item: (
                0 if item[1] in q else 1,
                -len(item[1]),
                item[0],
            )
        )
        return [term for _, term in indexed[:10]]
    
    def _expand_relationships(
        self,
        entities: List[Dict],
        domains: List[str] = None,
        relation_hints: List[str] = None,
    ) -> List[Dict]:
        """Expand from exact node references so same-name nodes cannot cross-multiply."""
        domains = domains or []
        relation_hints = relation_hints or []
        root_refs = list(dict.fromkeys(str(e.get("node_ref") or "") for e in entities if e.get("node_ref")))
        if not root_refs:
            return []

        paths = []
        with self.driver.session() as s:
            try:
                one_hop_rows = []
                one_hop_limit = max(0, KG_RECALL_ONE_HOP_LIMIT)
                fair_root_refs = root_refs[:one_hop_limit]
                if fair_root_refs:
                    per_root_limit, extra_slots = divmod(
                        one_hop_limit,
                        len(fair_root_refs),
                    )
                    # Each root gets its own ORDER BY/LIMIT so an earlier
                    # elementId cannot consume the entire first-hop budget.
                    for index, root_ref in enumerate(fair_root_refs):
                        root_limit = per_root_limit + (index < extra_slots)
                        one_hop_rows.extend(
                            self._fetch_hop_rows(
                                s,
                                [root_ref],
                                limit=root_limit,
                            )
                        )
                paths.extend(self._rows_to_paths(one_hop_rows, domains, relation_hints, hop=1))

                mid_refs = list(
                    dict.fromkeys(
                        str(path.get("to_node_ref") or "")
                        for path in paths
                        if path.get("to_node_ref")
                    )
                )
                if mid_refs:
                    two_hop_rows = self._fetch_hop_rows(
                        s,
                        mid_refs,
                        limit=KG_RECALL_TWO_HOP_LIMIT,
                        exclude_node_refs=root_refs,
                    )
                    paths.extend(self._rows_to_paths(two_hop_rows, domains, relation_hints, hop=2))
            except Exception as e:
                print(f"[KGRecall] 关系扩展失败: {e}")

        seen = set()
        unique = []
        for path in paths:
            key = (
                path.get("from_node_ref"),
                path.get("relationship_ref") or path.get("relation"),
                path.get("to_node_ref"),
                path.get("direction"),
            )
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    def _fetch_hop_rows(
        self,
        session,
        node_refs: List[str],
        limit: int,
        exclude_node_refs: List[str] = None,
    ) -> List[Dict]:
        """Fetch outgoing edges plus incoming structural edges from exact Neo4j node refs."""
        if not node_refs:
            return []
        exclude_node_refs = exclude_node_refs or []
        node_governance = self._governance_predicate("start")
        neighbor_governance = self._governance_predicate("neighbor")
        relation_governance = self._governance_predicate("rel")
        projection = """
            RETURN elementId(start) AS from_node_ref,
                   coalesce(start.name, start.canonical_name, '') AS from_entity,
                   coalesce([label IN labels(start) WHERE label <> 'Entity'][0], 'Entity') AS from_type,
                   start.semantic_key AS from_semantic_key,
                   start.entity_id AS from_entity_id,
                   start.source_chunk_ids AS from_source_chunk_ids,
                   coalesce(start.domain, start.source_doc, '') AS from_domain,
                   elementId(rel) AS relationship_ref,
                   type(rel) AS relation,
                   rel.source_chunk_ids AS relation_source_chunk_ids,
                   rel.review_status AS relation_review_status,
                   rel.conflict_status AS relation_conflict_status,
                   rel.evidence_governance_status AS relation_evidence_governance_status,
                   elementId(neighbor) AS to_node_ref,
                   coalesce(neighbor.name, neighbor.canonical_name, '') AS to_entity,
                   coalesce([label IN labels(neighbor) WHERE label <> 'Entity'][0], 'Entity') AS to_type,
                   neighbor.semantic_key AS to_semantic_key,
                   neighbor.entity_id AS to_entity_id,
                   neighbor.source_chunk_ids AS to_source_chunk_ids,
                   coalesce(neighbor.domain, neighbor.source_doc, '') AS to_domain,
                   start.review_status AS from_review_status,
                   start.conflict_status AS from_conflict_status,
                   start.evidence_governance_status AS from_evidence_governance_status,
                   neighbor.review_status AS to_review_status,
                   neighbor.conflict_status AS to_conflict_status,
                   neighbor.evidence_governance_status AS to_evidence_governance_status
            ORDER BY from_node_ref, relation, to_node_ref
            LIMIT $limit
        """
        common_where = (
            "elementId(start) IN $node_refs "
            "AND NOT neighbor:Chunk AND NOT neighbor:ChunkRef "
            "AND NOT elementId(neighbor) IN $exclude_node_refs "
            f"AND {node_governance} AND {neighbor_governance} AND {relation_governance} "
        )
        outgoing_query = (
            "MATCH (start)-[rel]->(neighbor) WHERE "
            + common_where
            + "AND (NOT neighbor:Document OR type(rel) IN $hierarchy_rel_types) "
            + projection
        )
        incoming_query = (
            "MATCH (start)<-[rel]-(neighbor) WHERE "
            + common_where
            + "AND type(rel) IN $hierarchy_rel_types "
            + projection
        )
        params = {
            "node_refs": node_refs,
            "exclude_node_refs": exclude_node_refs,
            "hierarchy_rel_types": BIDIRECTIONAL_HIERARCHY_REL_TYPES,
        }
        outgoing_rows = []
        for row in session.run(outgoing_query, **params, limit=limit).data():
            row["direction"] = "outgoing"
            if self._governance_allowed(row, prefixes=("from", "to", "relation")):
                outgoing_rows.append(row)

        # Reserve a bounded share for incoming hierarchy edges. Querying both
        # directions with the full limit and truncating the concatenation lets
        # high out-degree nodes erase every parent/section edge.
        hierarchy_quota = min(limit, max(1, limit // 5))
        incoming_rows = []
        for row in session.run(
            incoming_query,
            **params,
            limit=hierarchy_quota,
        ).data():
            row["direction"] = "incoming"
            if self._governance_allowed(row, prefixes=("from", "to", "relation")):
                incoming_rows.append(row)

        selected_incoming = incoming_rows[:hierarchy_quota]
        outgoing_quota = max(0, limit - len(selected_incoming))
        return outgoing_rows[:outgoing_quota] + selected_incoming

    def _rows_to_paths(
        self,
        rows: List[Dict],
        domains: List[str],
        relation_hints: List[str],
        hop: int,
    ) -> List[Dict]:
        paths = []
        for row in rows:
            direction = row.get("direction") or "outgoing"
            if direction == "incoming":
                path_text = f"{row['from_entity']} <-[{row['relation']}]- {row['to_entity']}"
            else:
                path_text = f"{row['from_entity']} -[{row['relation']}]-> {row['to_entity']}"
            paths.append(
                {
                    "path": path_text,
                    "nodes": [row.get("from_entity", ""), row.get("to_entity", "")],
                    "node_refs": [row.get("from_node_ref", ""), row.get("to_node_ref", "")],
                    "from_node_ref": row.get("from_node_ref", ""),
                    "to_node_ref": row.get("to_node_ref", ""),
                    "from_semantic_key": row.get("from_semantic_key"),
                    "to_semantic_key": row.get("to_semantic_key"),
                    "from_entity_id": row.get("from_entity_id"),
                    "to_entity_id": row.get("to_entity_id"),
                    "from_type": row.get("from_type", "Entity"),
                    "to_type": row.get("to_type", "Entity"),
                    "hop": hop,
                    "relationship_ref": row.get("relationship_ref"),
                    "direction": direction,
                    "relation": row.get("relation", ""),
                    "source_chunk_ids": self._normalize_chunk_ids(row.get("relation_source_chunk_ids")),
                    "from_source_chunk_ids": self._normalize_chunk_ids(row.get("from_source_chunk_ids")),
                    "to_source_chunk_ids": self._normalize_chunk_ids(row.get("to_source_chunk_ids")),
                    "domain": self._path_domain(row.get("from_domain"), row.get("to_domain"), domains),
                    "confidence": self._path_confidence(row.get("relation", ""), domains, relation_hints, hop=hop),
                    "relation_reason": self._relation_reason(row.get("relation", ""), domains, relation_hints),
                    "evidence_required": ["source_doc", "source_chunk_ids", "sqlite_chunk_text"],
                }
            )
        return paths

    def _path_domain(self, left: str, right: str, fallback_domains: List[str]) -> str:
        for value in (left, right):
            if value and value in fallback_domains:
                return value
            inferred = domain_for_doc_name(value or "")
            if inferred != "general":
                return inferred
        return next((domain for domain in fallback_domains if domain != "general"), "general")

    def _path_confidence(self, relation: str, domains: List[str], relation_hints: List[str], hop: int) -> float:
        score = 0.58 if hop == 1 else 0.42
        if relation in relation_hints:
            score += 0.22
        if any(domain != "general" for domain in domains):
            score += 0.08
        return round(min(score, 0.95), 3)

    def _relation_reason(self, relation: str, domains: List[str], relation_hints: List[str]) -> str:
        if relation in relation_hints:
            return f"relation matches semantic plan for {','.join(domains)}"
        return "graph expansion from matched semantic entity"

    @staticmethod
    def _normalize_chunk_ids(value) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    value = parsed
                else:
                    value = [text]
            else:
                value = [text]
        elif not isinstance(value, (list, tuple, set)):
            value = [value]
        seen = set()
        return [
            chunk_id
            for item in value
            if (chunk_id := str(item or "").strip())
            and not (chunk_id in seen or seen.add(chunk_id))
        ]

    @classmethod
    def _entity_evidence_chunk_ids(cls, entity: Dict) -> List[str]:
        """Return only coordinates that establish this exact entity match."""
        if entity.get("match_mode") not in EXACT_ENTITY_MATCH_MODES:
            return []
        matched_chunk_ids = cls._normalize_chunk_ids(
            entity.get("matched_chunk_ids")
        )
        if entity.get("match_origin") == "retrieved_chunk" or str(
            entity.get("type") or ""
        ) in STRUCTURAL_ENTITY_TYPES:
            return matched_chunk_ids
        return cls._normalize_chunk_ids(entity.get("source_chunk_ids"))

    @classmethod
    def _path_evidence_coordinates(cls, path: Dict) -> Dict[str, List[str]]:
        """Bound path evidence without promoting structural document spans."""
        from_type = str(path.get("from_type") or "")
        to_type = str(path.get("to_type") or "")
        try:
            hop = int(path.get("hop") or 1)
        except (TypeError, ValueError):
            hop = 1
        if hop >= 2 and {
            from_type,
            to_type,
        }.intersection(STRUCTURAL_ENTITY_TYPES):
            return {"relationship": [], "nodes": []}

        node_ids: List[str] = []
        if from_type not in STRUCTURAL_ENTITY_TYPES:
            node_ids.extend(
                cls._normalize_chunk_ids(path.get("from_source_chunk_ids"))
            )
        if to_type not in STRUCTURAL_ENTITY_TYPES:
            node_ids.extend(
                cls._normalize_chunk_ids(path.get("to_source_chunk_ids"))
            )
        return {
            "relationship": cls._normalize_chunk_ids(path.get("source_chunk_ids")),
            "nodes": list(dict.fromkeys(node_ids)),
        }

    @staticmethod
    def exact_evidence_bindings(bindings: List[Dict]) -> List[Dict]:
        """Keep only bindings backed by an exact graph provenance coordinate."""
        return [
            binding
            for binding in bindings or []
            if isinstance(binding, dict)
            and EXACT_EVIDENCE_ORIGINS.intersection(
                str(origin)
                for origin in binding.get("evidence_origins") or []
            )
        ]

    @classmethod
    def prompt_graph_evidence(cls, kg_result: Dict) -> tuple[List[Dict], List[Dict]]:
        """Return only graph paths/entities backed by exact SQLite coordinates."""
        bindings = cls.exact_evidence_bindings(kg_result.get("evidence_bindings", []))
        path_chunk_ids = {
            str(binding.get("chunk_id") or "")
            for binding in bindings
            if {
                "relationship_source_chunk_ids",
                "path_node_source_chunk_ids",
            }.intersection(binding.get("evidence_origins") or [])
            and binding.get("chunk_id")
        }
        entity_chunk_ids = {
            str(binding.get("chunk_id") or "")
            for binding in bindings
            if "entity_source_chunk_ids" in (binding.get("evidence_origins") or [])
            and binding.get("chunk_id")
        }

        paths = []
        for path in kg_result.get("paths") or []:
            effective = cls._path_evidence_coordinates(path)
            coordinates = set(
                effective["relationship"] + effective["nodes"]
            )
            if coordinates.intersection(path_chunk_ids):
                paths.append(path)

        entities = []
        for entity in kg_result.get("matched_entities") or []:
            coordinates = set(cls._entity_evidence_chunk_ids(entity))
            if (
                entity.get("match_mode") in EXACT_ENTITY_MATCH_MODES
                and coordinates.intersection(entity_chunk_ids)
            ):
                entities.append(entity)
        return paths, entities

    def _build_evidence_bindings(
        self,
        chunk_ids: List[str],
        paths: List[Dict],
        entities: List[Dict],
        domains: List[str],
    ) -> List[Dict]:
        chunks = self._store.get_chunks_batch(chunk_ids)
        by_id = {row["chunk_id"]: row for row in chunks}
        bindings = []
        entry_match_modes = sorted(
            {
                str(entity.get("match_mode") or "unknown")
                for entity in entities
                if isinstance(entity, dict)
            }
        )
        path_coordinates = [
            (path, self._path_evidence_coordinates(path)) for path in paths
        ]
        for cid in chunk_ids:
            row = by_id.get(cid, {})
            exact_entities = [
                entity.get("name", "")
                for entity in entities
                if entity.get("name")
                and entity.get("match_mode") in EXACT_ENTITY_MATCH_MODES
                and cid in self._entity_evidence_chunk_ids(entity)
            ]
            exact_paths = [
                path.get("path", "")
                for path, coordinates in path_coordinates
                if path.get("path")
                and cid in (coordinates["relationship"] + coordinates["nodes"])
            ]
            origins = []
            if exact_entities:
                origins.append("entity_source_chunk_ids")
            relationship_match = any(
                cid in coordinates["relationship"]
                for _, coordinates in path_coordinates
            )
            path_node_match = any(
                cid in coordinates["nodes"]
                for _, coordinates in path_coordinates
            )
            if relationship_match:
                origins.append("relationship_source_chunk_ids")
            if path_node_match:
                origins.append("path_node_source_chunk_ids")
            if not origins:
                continue
            bindings.append({
                "chunk_id": cid,
                "doc_name": row.get("doc_name", ""),
                "chunk_index": row.get("chunk_index", 0),
                "domains": domains,
                "matched_entities": exact_entities,
                "graph_paths": exact_paths,
                "evidence_origins": origins,
                "entry_match_modes": entry_match_modes,
                "text_owner": "sqlite:rag_chunks.db",
                "schema_version": SCHEMA_VERSION,
            })
        return bindings
    
    def _collect_chunk_ids(
        self,
        entities: List[Dict],
        paths: List[Dict],
        intent: str = "general",
        keywords: List[str] = None,
        query: str = "",
    ) -> List[str]:
        """Collect exact graph evidence first, then progressively broader SQLite fallbacks."""
        keywords = keywords or []
        chunks_by_id: Dict[str, Dict] = {}
        insertion_order = 0

        def add_chunk(row: Dict, priority: int):
            nonlocal insertion_order
            cid = row.get("chunk_id")
            if not cid:
                return
            existing = chunks_by_id.get(cid)
            if existing is None:
                item = dict(row)
                item["_kg_priority"] = priority
                item["_kg_order"] = insertion_order
                insertion_order += 1
                chunks_by_id[cid] = item
            elif priority < existing.get("_kg_priority", priority):
                existing["_kg_priority"] = priority

        entity_chunk_ids = []
        for entity in entities:
            entity_chunk_ids.extend(self._entity_evidence_chunk_ids(entity))
        relation_chunk_ids = []
        path_node_chunk_ids = []
        for path in paths:
            coordinates = self._path_evidence_coordinates(path)
            relation_chunk_ids.extend(coordinates["relationship"])
            path_node_chunk_ids.extend(coordinates["nodes"])

        exact_groups = (
            (0, entity_chunk_ids),
            (1, relation_chunk_ids),
            (2, path_node_chunk_ids),
        )
        all_exact_ids = list(
            dict.fromkeys(chunk_id for _, group in exact_groups for chunk_id in group)
        )
        exact_rows = {
            row["chunk_id"]: row
            for row in self._store.get_chunks_batch(all_exact_ids)
            if row.get("chunk_id")
        }
        for priority, group in exact_groups:
            for chunk_id in dict.fromkeys(group):
                row = exact_rows.get(chunk_id)
                if row:
                    add_chunk(row, priority)

        # Fallback 1: source document aliases.
        doc_names = set()
        for e in entities:
            if e.get("source_doc"):
                doc_names.add(e["source_doc"])
        for row in self._store.find_chunks_by_doc_names(sorted(doc_names), limit_per_doc=8):
            add_chunk(row, 10)

        # Fallback 2: query-intent document probes.
        probe_terms = self._query_doc_probe_terms(query, intent, keywords)
        for row in self._store.search_chunks(probe_terms, limit=self._max_results):
            add_chunk(row, 20)

        # Fallback 3: entity/path names.
        all_node_names = set()
        for e in entities:
            if e.get("name"):
                all_node_names.add(e["name"])
        for p in paths:
            for n in p.get("nodes", []):
                if n:
                    all_node_names.add(n)
        for row in self._store.search_chunks(list(all_node_names)[:8], limit=self._max_results):
            add_chunk(row, 30)

        ranked = sorted(
            chunks_by_id.values(),
            key=lambda row: (
                row.get("_kg_priority", 99),
                -self._doc_intent_boost(row.get("doc_name", ""), row.get("text", ""), query, intent, keywords),
                row.get("_kg_order", 0) if row.get("_kg_priority", 99) <= 2 else 0,
                row.get("doc_name", ""),
                row.get("chunk_index", 0),
            ),
        )
        return [row["chunk_id"] for row in ranked]

    def _query_doc_probe_terms(self, query: str, intent: str, keywords: List[str]) -> List[str]:
        """把查询意图转成 doc_name/text probe 词。"""
        q = query or ""
        terms = []
        terms.extend(kw for kw in keywords if kw and len(kw) >= 2)
        seen = set()
        return [term for term in terms if not (term in seen or seen.add(term))]

    def _doc_intent_boost(self, doc_name: str, text: str, query: str, intent: str, keywords: List[str]) -> float:
        """按查询意图给 KG 候选文档做轻量排序，避免泛实体文档劫持。"""
        q = query or ""
        doc = doc_name or ""
        boost = 0.0

        if any(term in q for term in ("地址", "电话", "联系", "联系方式")):
                boost += 5.0
        if any(term in q for term in ("课程", "产品", "培训", "价格", "费用", "多少钱", "收费")):
                boost += 5.0
        boost += sum(0.2 for kw in keywords if kw and kw in doc)
        boost += min(sum(1 for kw in keywords if kw and kw in text), 5) * 0.05
        return boost


# ============ 测试 ============
