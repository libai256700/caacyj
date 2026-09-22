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

# ============ 配置 ============
BASE_DIR = Path(__file__).parent.parent
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")

_PASS_PATH = BASE_DIR / "neo4j" / ".neo4j_pass"
if not _PASS_PATH.exists():
    raise FileNotFoundError(f"Neo4j 密码文件缺失: {_PASS_PATH}")
NEO4J_PASS = _PASS_PATH.read_text().strip()

KG_RECALL_CACHE_TTL = float(os.environ.get("KG_RECALL_CACHE_TTL", "120"))
KG_RECALL_CACHE_MAX = int(os.environ.get("KG_RECALL_CACHE_MAX", "128"))
KG_RECALL_MAX_RESULTS = int(os.environ.get("KG_RECALL_MAX_RESULTS", "20"))
KG_RECALL_MAX_PATHS = int(os.environ.get("KG_RECALL_MAX_PATHS", "10"))
KG_RECALL_MATCH_LIMIT = int(os.environ.get("KG_RECALL_MATCH_LIMIT", "3"))
KG_RECALL_ANCHOR_LIMIT = int(os.environ.get("KG_RECALL_ANCHOR_LIMIT", "5"))
KG_RECALL_ONE_HOP_LIMIT = int(os.environ.get("KG_RECALL_ONE_HOP_LIMIT", "30"))
KG_RECALL_TWO_HOP_LIMIT = int(os.environ.get("KG_RECALL_TWO_HOP_LIMIT", "20"))
KG_RECALL_EXCLUDE_UNRESOLVED_EVIDENCE = os.environ.get("KG_RECALL_EXCLUDE_UNRESOLVED_EVIDENCE", "1") != "0"
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
        entity_names = [e["name"] for e in entities]
        cache_key = self._cache_key(entities, intent, keywords, query, semantic_plan)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        
        try:
            matched = self._match_entities(entity_names) if entity_names else []
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
            "entities": sorted(e.get("name", "") for e in entities or [] if e.get("name")),
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
    
    def _match_entities(self, names: List[str]) -> List[Dict]:
        """在 Neo4j 中按名称匹配实体"""
        with self.driver.session() as s:
            matched = []
            for name in names:
                result = s.run("""
                    MATCH (n)
                    WHERE toLower(n.name) = toLower($name) OR n.name CONTAINS $name
                    RETURN n.name AS name,
                           """ + TYPE_EXPR + """ AS type,
                           n.description AS description,
                           n.source_doc AS source_doc,
                           n.source_chunk_ids AS source_chunk_ids,
                           n.entity_id AS entity_id,
                           n.domain AS domain,
                           n.canonical_name AS canonical_name,
                           n.id AS id
                    LIMIT $limit
                """, name=name, limit=KG_RECALL_MATCH_LIMIT).data()
                matched.extend(result)
            
            # 去重
            seen = set()
            unique = []
            for m in matched:
                key = m["name"]
                if key not in seen:
                    seen.add(key)
                    unique.append(m)
            return unique

    def _match_anchor_entities(self, query: str, intent: str, keywords: List[str]) -> List[Dict]:
        """没有显式实体时，用关键词和文档锚点从图谱中找少量入口节点。"""
        anchors = self._anchor_terms(query, intent, keywords)
        if not anchors:
            return []

        with self.driver.session() as s:
            rows = s.run("""
                MATCH (n)
                WHERE NOT n:Document
                  AND any(term IN $anchors WHERE
                    toLower(coalesce(n.name, "")) CONTAINS toLower(term)
                    OR toLower(coalesce(n.source_doc, "")) CONTAINS toLower(term)
                    OR toLower(coalesce(n.description, "")) CONTAINS toLower(term)
                  )
                WITH n,
                     reduce(score = 0, term IN $anchors |
                       score
                       + CASE WHEN toLower(coalesce(n.name, "")) = toLower(term) THEN 5 ELSE 0 END
                       + CASE WHEN toLower(coalesce(n.name, "")) CONTAINS toLower(term) THEN 3 ELSE 0 END
                       + CASE WHEN toLower(coalesce(n.source_doc, "")) CONTAINS toLower(term) THEN 2 ELSE 0 END
                       + CASE WHEN toLower(coalesce(n.description, "")) CONTAINS toLower(term) THEN 1 ELSE 0 END
                     ) AS score
                RETURN n.name AS name,
                       """ + TYPE_EXPR + """ AS type,
                       n.description AS description,
                       n.source_doc AS source_doc,
                       n.source_chunk_ids AS source_chunk_ids,
                       n.entity_id AS entity_id,
                       n.domain AS domain,
                       n.canonical_name AS canonical_name,
                       n.id AS id,
                       score
                ORDER BY score DESC, size(coalesce(n.name, "")) ASC
                LIMIT $limit
            """, anchors=anchors, limit=KG_RECALL_ANCHOR_LIMIT).data()
        return rows

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
        if intent == "company":
            terms.extend(["云技科技", "公司介绍", "培训基地", "课程"])
        terms.extend(kw for kw in keywords if kw and 2 <= len(kw) <= 20)

        seen = set()
        return [term for term in terms if not (term in seen or seen.add(term))][:10]
    
    def _expand_relationships(
        self,
        entities: List[Dict],
        domains: List[str] = None,
        relation_hints: List[str] = None,
    ) -> List[Dict]:
        """对匹配到的实体做 1-2 跳关系扩展"""
        paths = []
        entity_names = [e["name"] for e in entities]
        domains = domains or []
        relation_hints = relation_hints or []
        
        if not entity_names:
            return paths
        
        with self.driver.session() as s:
            try:
                # 1-hop: 直接关系
                one_hop = s.run("""
                    MATCH (a)-[r]->(b)
                    WHERE a.name IN $names
                    AND NOT b:Document AND NOT b:Chunk
                    AND (
                      $allow_unresolved_evidence
                      OR NOT (
                        type(r) IN $governed_rel_types
                        AND r.evidence_governance_status = 'unresolved'
                      )
                    )
                    RETURN a.name AS from_entity,
                           """ + FROM_TYPE_EXPR + """ AS from_type,
                           type(r) AS relation,
                           b.name AS to_entity,
                           """ + TO_TYPE_EXPR + """ AS to_type,
                           coalesce(a.domain, a.source_doc, "") AS from_domain,
                           coalesce(b.domain, b.source_doc, "") AS to_domain
                    LIMIT $limit
                """,
                    names=entity_names,
                    limit=KG_RECALL_ONE_HOP_LIMIT,
                    allow_unresolved_evidence=not KG_RECALL_EXCLUDE_UNRESOLVED_EVIDENCE,
                    governed_rel_types=EVIDENCE_GOVERNED_REL_TYPES,
                ).data()
                
                for row in one_hop:
                    paths.append({
                        "path": f"{row['from_entity']} -[{row['relation']}]-> {row['to_entity']}",
                        "nodes": [row['from_entity'], row['to_entity']],
                        "relation": row['relation'],
                        "domain": self._path_domain(row.get("from_domain"), row.get("to_domain"), domains),
                        "confidence": self._path_confidence(row["relation"], domains, relation_hints, hop=1),
                        "relation_reason": self._relation_reason(row["relation"], domains, relation_hints),
                        "evidence_required": ["source_doc", "sqlite_chunk_text"],
                    })
                
                # 2-hop: 扩展关联
                from_names = list(set(p["nodes"][-1] for p in paths if p["nodes"]))
                if from_names:
                    two_hop = s.run("""
                        MATCH (b)-[r2]->(c)
                        WHERE b.name IN $mid_names
                        AND NOT c:Document AND NOT c:Chunk
                        AND (
                          $allow_unresolved_evidence
                          OR NOT (
                            type(r2) IN $governed_rel_types
                            AND r2.evidence_governance_status = 'unresolved'
                          )
                        )
                        RETURN b.name AS mid,
                               type(r2) AS rel2,
                               c.name AS end,
                               coalesce(b.domain, b.source_doc, "") AS mid_domain,
                               coalesce(c.domain, c.source_doc, "") AS end_domain
                        LIMIT $limit
                    """,
                        mid_names=from_names,
                        limit=KG_RECALL_TWO_HOP_LIMIT,
                        allow_unresolved_evidence=not KG_RECALL_EXCLUDE_UNRESOLVED_EVIDENCE,
                        governed_rel_types=EVIDENCE_GOVERNED_REL_TYPES,
                    ).data()
                    
                    for row in two_hop:
                        path_str = (
                            f"{row['mid']} -[{row['rel2']}]-> {row['end']}"
                        )
                        paths.append({
                            "path": path_str,
                            "nodes": [row['mid'], row['end']],
                            "relation": row['rel2'],
                            "domain": self._path_domain(row.get("mid_domain"), row.get("end_domain"), domains),
                            "confidence": self._path_confidence(row["rel2"], domains, relation_hints, hop=2),
                            "relation_reason": self._relation_reason(row["rel2"], domains, relation_hints),
                            "evidence_required": ["source_doc", "sqlite_chunk_text"],
                        })
            except Exception as e:
                print(f"[KGRecall] 关系扩展失败: {e}")
        
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

    def _build_evidence_bindings(
        self,
        chunk_ids: List[str],
        paths: List[Dict],
        entities: List[Dict],
        domains: List[str],
    ) -> List[Dict]:
        chunks = self._store.get_chunks_batch(chunk_ids)
        by_id = {row["chunk_id"]: row for row in chunks}
        path_sample = paths[:3]
        entity_names = [entity.get("name", "") for entity in entities[:5] if entity.get("name")]
        bindings = []
        for cid in chunk_ids:
            row = by_id.get(cid, {})
            bindings.append({
                "chunk_id": cid,
                "doc_name": row.get("doc_name", ""),
                "chunk_index": row.get("chunk_index", 0),
                "domains": domains,
                "matched_entities": entity_names,
                "graph_paths": [path.get("path", "") for path in path_sample],
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
        """从匹配实体和关系路径中收集 chunk_id
        
        策略：
        1. 从实体的 source_doc 到 SQLite 匹配文档 chunks
        2. 用实体名/路径节点名在 SQLite 文本中做轻量关键词兜底
        """
        keywords = keywords or []
        chunks_by_id: Dict[str, Dict] = {}

        def add_chunk(row: Dict):
            cid = row.get("chunk_id")
            if cid and cid not in chunks_by_id:
                chunks_by_id[cid] = row
        
        # 策略 1: 通过 source_doc 收集
        doc_names = set()
        for e in entities:
            if e.get("source_doc"):
                doc_names.add(e["source_doc"])
        
        for row in self._store.find_chunks_by_doc_names(sorted(doc_names), limit_per_doc=8):
            add_chunk(row)

        # 策略 1b: 按查询意图主动 probe 目标文档名，避免泛实体只召回人事制度。
        probe_terms = self._query_doc_probe_terms(query, intent, keywords)
        for row in self._store.search_chunks(probe_terms, limit=self._max_results):
            add_chunk(row)
        
        # 策略 2: 通过路径中的实体名搜索相关 Chunk
        all_node_names = set()
        for e in entities:
            all_node_names.add(e["name"])
        for p in paths:
            for n in p.get("nodes", []):
                all_node_names.add(n)
        
        for row in self._store.search_chunks(list(all_node_names)[:8], limit=self._max_results):
            add_chunk(row)
        
        ranked = sorted(
            chunks_by_id.values(),
            key=lambda row: (
                -self._doc_intent_boost(row.get("doc_name", ""), row.get("text", ""), query, intent, keywords),
                row.get("doc_name", ""),
                row.get("chunk_index", 0),
            ),
        )
        return [row["chunk_id"] for row in ranked]

    def _query_doc_probe_terms(self, query: str, intent: str, keywords: List[str]) -> List[str]:
        """把查询意图转成 doc_name/text probe 词。"""
        q = query or ""
        terms = []
        if any(term in q for term in ("地址", "电话", "联系", "联系方式")):
            terms.extend(["公司介绍", "地址", "电话"])
        if any(term in q for term in ("课程", "产品", "培训", "价格", "费用", "多少钱", "收费")):
            terms.extend(["公司产品介绍", "新员工培训资料", "价格表", "课程", "产品"])
        if any(term in q for term in ("考勤", "员工手册")):
            terms.extend(["员工手册", "考勤"])
        if any(term in q for term in ("薪酬", "工资", "待遇")):
            terms.extend(["薪酬体系", "薪酬"])
        if any(term in q for term in ("入职", "面试", "新员工")):
            terms.extend(["入职流程", "面试", "新员工"])

        terms.extend(kw for kw in keywords if kw and len(kw) >= 2)
        seen = set()
        return [term for term in terms if not (term in seen or seen.add(term))]

    def _doc_intent_boost(self, doc_name: str, text: str, query: str, intent: str, keywords: List[str]) -> float:
        """按查询意图给 KG 候选文档做轻量排序，避免泛实体文档劫持。"""
        q = query or ""
        doc = doc_name or ""
        boost = 0.0

        if any(term in q for term in ("地址", "电话", "联系", "联系方式")):
            if "公司介绍" in doc:
                boost += 5.0
            if "企业信息" in doc:
                boost += 1.0

        if any(term in q for term in ("课程", "产品", "培训", "价格", "费用", "多少钱", "收费")):
            if "公司产品介绍" in doc:
                boost += 5.0
            if "新员工培训资料" in doc:
                boost += 4.0
            if "价格表" in doc:
                boost += 3.0
            if "企业信息" in doc:
                boost += 1.0

        if any(term in q for term in ("考勤", "员工手册")) and "员工手册" in doc:
            boost += 5.0
        if any(term in q for term in ("薪酬", "工资", "待遇")) and "薪酬体系" in doc:
            boost += 5.0
        if any(term in q for term in ("入职", "面试", "新员工")) and "入职流程" in doc:
            boost += 5.0

        boost += sum(0.2 for kw in keywords if kw and kw in doc)
        boost += min(sum(1 for kw in keywords if kw and kw in text), 5) * 0.05
        return boost


# ============ 测试 ============
if __name__ == "__main__":
    kg = KGRecall()
    
    test_cases = [
        {
            "query": "CCAR-92关于罚款的规定是什么？",
            "entities": [{"name": "CCAR-92", "type": "Regulation", "confidence": 0.95}],
            "intent": "regulation",
            "keywords": ["CCAR-92", "罚款", "规定"],
        },
        {
            "query": "云技科技有哪些培训课程？",
            "entities": [{"name": "云技科技", "type": "Company", "confidence": 0.95}],
            "intent": "company",
            "keywords": ["云技科技", "培训", "课程"],
        },
    ]
    
    for tc in test_cases:
        result = kg.recall(tc["entities"], tc["intent"], tc["keywords"], tc["query"])
        print(f"\n   Q: {tc['query']}")
        print(f"   → 匹配实体: {[e['name'] for e in result['matched_entities']]}")
        print(f"   → 路径数: {len(result['paths'])}")
        print(f"   → chunk_id 数: {len(result['chunk_ids'])}")
        if result["chunk_ids"]:
            print(f"   → 示例: {list(result['chunk_ids'])[:3]}")
    
    kg.close()
