#!/usr/bin/env python3
"""Semantic graph v2 contract shared by planning, manifests, and repairs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "semantic-graph-v2"

ENTITY_TYPES = (
    "Company",
    "Course",
    "Regulation",
    "QuestionBank",
    "KnowledgePoint",
    "Skill",
    "Policy",
    "Position",
    "Student",
    "Customer",
    "Instructor",
    "Document",
    "ChunkRef",
)

RELATION_TYPES = (
    "CONTAINS",
    "MENTIONS",
    "PART_OF",
    "REQUIRES",
    "REGULATES",
    "DEFINED_BY",
    "HAS_PROPERTY",
    "OFFERS",
    "AFFECTS",
    "BELONGS_TO",
    "REFERS_TO",
    "DESCRIBES",
    "AWARDS",
    "ISSUED_BY",
    "LOCATED_AT",
    "HAS_CLASS",
    "HAS_LEVEL",
    "REQUIRES_SKILL",
    "SUBCLASS_OF",
)

CRITICAL_EVIDENCE_REL_TYPES = (
    "REQUIRES",
    "REGULATES",
    "REFERS_TO",
    "HAS_PROPERTY",
    "REQUIRES_SKILL",
    "HAS_CLASS",
)

DEPRECATED_RELATION_TYPES = {
    "HAS_SALARY": {
        "replacement": "HAS_PROPERTY",
        "migration": "preserve description as property_name when it means price or salary",
    }
}

SYNC_ELIGIBLE_DOMAINS = ("regulation", "question_bank", "textbook")

DOMAIN_KEYWORDS = {
    "company": ("公司", "云技", "组织架构", "公司结构", "公司介绍", "企业信息", "业务发展"),
    "hr_policy": ("员工手册", "人事", "薪酬", "入职", "面试流程", "考勤", "制度"),
    "course": ("课程", "培训", "执照", "超视距", "多旋翼", "教员", "垂起", "产品"),
    "price": ("价格", "多少钱", "费用", "学费", "收费", "报价"),
    "regulation": ("法规", "民航法", "民用航空法", "无人驾驶航空器", "CCAR", "92部", "条款", "空域", "监管", "规章", "适航许可"),
    "question_bank": ("题库", "考试", "试题", "答案", "知识点", "气象", "任务规划", "风切变"),
    "textbook": ("教材", "理论书籍", "概论", "飞行原理", "系统结构", "操作注意事项", "核心概念"),
    "job_market": ("岗位", "岗位职责", "助教", "招聘", "职位", "薪资", "日报"),
    "customer": ("客户", "客资", "咨询", "跟进", "意向", "回访"),
}

DOMAIN_ENTITY_TYPES = {
    "company": ("Company", "Organization", "Position", "Course", "Document"),
    "hr_policy": ("Policy", "Position", "Person", "Document"),
    "course": ("Course", "Certification", "LicenseLevel", "Skill", "Document"),
    "price": ("Course", "Document"),
    "regulation": ("Regulation", "Policy", "KnowledgePoint", "Document"),
    "question_bank": ("QuestionBank", "KnowledgePoint", "Skill", "Document"),
    "textbook": ("KnowledgePoint", "Skill", "Chapter", "Section", "Document"),
    "job_market": ("Position", "Organization", "Location", "Document"),
    "customer": ("Customer", "Course", "Policy", "Document"),
}

DOMAIN_RELATION_HINTS = {
    "company": ("DESCRIBES", "OFFERS", "BELONGS_TO", "PART_OF"),
    "hr_policy": ("DEFINED_BY", "REQUIRES", "HAS_PROPERTY", "AFFECTS"),
    "course": ("OFFERS", "REQUIRES", "AWARDS", "HAS_LEVEL", "REQUIRES_SKILL"),
    "price": ("HAS_PROPERTY", "OFFERS"),
    "regulation": ("REGULATES", "DEFINED_BY", "REFERS_TO", "AFFECTS", "PART_OF"),
    "question_bank": ("MENTIONS", "REQUIRES", "DEFINED_BY", "PART_OF"),
    "textbook": ("PART_OF", "DEFINED_BY", "REQUIRES_SKILL", "MENTIONS"),
    "job_market": ("LOCATED_AT", "HAS_PROPERTY", "REQUIRES", "BELONGS_TO"),
    "customer": ("REFERS_TO", "AFFECTS", "REQUIRES", "DEFINED_BY"),
}

CANONICAL_TABLES = {
    "students": "student",
    "customers": "customer",
    "courses": "course",
    "instructors": "instructor",
    "jobs": "job_market",
    "regulations": "regulation",
    "question_banks": "question_bank",
    "documents": "document",
    "document_chunks": "chunk_ref",
}


def normalize_name(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def stable_entity_id(domain: str, entity_type: str, name: str) -> str:
    normalized = normalize_name(name)
    digest = hashlib.sha1(f"{domain}|{entity_type}|{normalized}".encode("utf-8")).hexdigest()[:12]
    return f"{domain}:{entity_type}:{digest}"


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(_nonempty(item) for item in value)
    return str(value).strip() != ""


def relationship_missing_evidence_reason(rel_type: str, props: dict[str, Any] | None) -> str:
    """Return an empty string when a relationship has required evidence."""
    rel_type = (rel_type or "").upper().strip()
    if rel_type not in CRITICAL_EVIDENCE_REL_TYPES:
        return ""
    props = props or {}
    if not _nonempty(props.get("source_doc")):
        return "missing_source_doc"
    if not _nonempty(props.get("source_chunk_ids")):
        return "missing_source_chunk_ids"
    return ""


def relationship_has_required_evidence(rel_type: str, props: dict[str, Any] | None) -> bool:
    return relationship_missing_evidence_reason(rel_type, props) == ""


def infer_domains(*texts: str) -> list[str]:
    blob = " ".join(text for text in texts if text)
    matched = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword.lower() in blob.lower() for keyword in keywords):
            matched.append(domain)
    return matched or ["general"]


def domain_for_doc_name(doc_name: str) -> str:
    domains = infer_domains(doc_name)
    if "regulation" in domains:
        return "regulation"
    if "question_bank" in domains:
        return "question_bank"
    if "textbook" in domains:
        return "textbook"
    if "hr_policy" in domains:
        return "hr_policy"
    if "price" in domains:
        return "price"
    if "course" in domains:
        return "course"
    if "company" in domains:
        return "company"
    if "job_market" in domains:
        return "job_market"
    if "customer" in domains:
        return "customer"
    return "general"


def semantic_schema_manifest() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "entity_types": list(ENTITY_TYPES),
        "relation_types": list(RELATION_TYPES),
        "deprecated_relation_types": DEPRECATED_RELATION_TYPES,
        "domains": sorted(DOMAIN_KEYWORDS),
        "sync_eligible_domains": list(SYNC_ELIGIBLE_DOMAINS),
        "entity_id_contract": "domain:type:sha1-12 over normalized domain/type/name",
        "evidence_contract": {
            "canonical_text_owner": "sqlite:rag_chunks.db",
            "join_key": "chunk_id",
            "critical_relationship_types": list(CRITICAL_EVIDENCE_REL_TYPES),
            "critical_relationship_required_fields": ["source_doc", "source_chunk_ids"],
            "graph_required_fields": [
                "entity_id",
                "domain",
                "canonical_name",
                "source_doc",
                "source_chunk_ids",
                "schema_version",
            ],
        },
    }


def build_semantic_plan(
    question: str,
    *,
    route_decision: str,
    rag_query: str,
    intent: str,
    keywords: list[str] | None = None,
    entities: list[dict[str, Any]] | None = None,
    csa_topic: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic graph-first plan before retrieval runs."""
    keywords = keywords or []
    entities = entities or []
    domains = infer_domains(question, rag_query, intent, " ".join(keywords), csa_topic or "")
    needs_graph_first = route_decision == "graph_first"
    needs_structured = route_decision in {"csa", "hybrid"} or bool(csa_topic)
    needs_graph = route_decision != "csa" or any(domain in domains for domain in SYNC_ELIGIBLE_DOMAINS)
    needs_rag_text = route_decision != "csa"
    needs_external = route_decision == "rag_external_candidate"
    entry_entities = [
        {
            "name": entity.get("name", ""),
            "type": entity.get("type") or "Entity",
            "domain": domain_for_doc_name(entity.get("source_doc") or entity.get("name") or ""),
        }
        for entity in entities
        if entity.get("name")
    ]
    relation_hints = []
    for domain in domains:
        for rel in DOMAIN_RELATION_HINTS.get(domain, ()):
            if rel not in relation_hints:
                relation_hints.append(rel)
    candidate_documents = [
        keyword for keyword in keywords if any(marker in keyword for marker in ("法", "题库", "教材", "公司", "制度", "价格"))
    ][:8]
    return {
        "schema_version": SCHEMA_VERSION,
        "route_decision": route_decision,
        "domains": domains,
        "needs": {
            "structured": needs_structured,
            "graph_first": needs_graph_first,
            "graph_reasoning": needs_graph,
            "rag_text": needs_rag_text,
            "external_completion": needs_external,
        },
        "graph_query_plan": {
            "entry_entities": entry_entities,
            "domain_anchors": [domain for domain in domains if domain != "general"],
            "relation_hints": relation_hints,
            "candidate_documents": candidate_documents,
            "evidence_required": ["source_doc", "source_chunk_ids", "sqlite_chunk_text"],
            "path_required": needs_graph_first,
        },
        "rag_query": rag_query,
        "intent": intent,
    }


def canonical_table_report(root: Path) -> dict[str, Any]:
    files = []
    totals = {"tables": 0, "rows": 0}
    for table, domain in CANONICAL_TABLES.items():
        path = root / f"{table}.csv"
        item: dict[str, Any] = {
            "table": table,
            "domain": domain,
            "path": str(path),
            "exists": path.exists(),
        }
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = __import__("csv").reader(f)
                header = next(reader, [])
                row_count = sum(1 for row in reader if any(cell.strip() for cell in row))
            item.update({"columns": header, "row_count": row_count})
            totals["tables"] += 1
            totals["rows"] += row_count
        files.append(item)
    return {
        "root": str(root),
        "exists": root.exists(),
        "tables": files,
        "totals": totals,
        "entity_id_mapping": "canonical business ids map to Neo4j entity_id; chunk_id remains text evidence only",
    }
