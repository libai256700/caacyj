#!/usr/bin/env python3
"""Sync canonical business CSV entities into Neo4j.

The source of truth for full text remains rag_chunks.db. This script only
syncs business entities, graph paths, source hints, and chunk ids that can be
resolved by the Hybrid RAG context builder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from neo4j import GraphDatabase

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEFAULT_PROJECT_ROOT))
from rag_store.semantic_schema import relationship_missing_evidence_reason


DEFAULT_CANONICAL_DIR = Path("/Users/xiaoji/Documents/知识库分析/data/canonical")
DEFAULT_REPORT = DEFAULT_PROJECT_ROOT / "review_reports" / "business_entity_sync_report.json"
SCHEMA_VERSION = "semantic-graph-v2"
SYNC_VERSION = "business-entity-sync-v1"
SYNC_SOURCE = "canonical_business_entities"
MAX_CHUNKS_PER_NODE = 120
MAX_REL_CHUNKS = 20
VALID_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SKILL_NAME_SUFFIX = "（能力）"
EVIDENCE_KP_SUFFIX = "（知识点证据）"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def clean(value: Any) -> str:
    return str(value or "").strip()


def skill_display_name(name: str) -> str:
    name = clean(name)
    return name if name.endswith(SKILL_NAME_SUFFIX) else f"{name}{SKILL_NAME_SUFFIX}"


def evidence_kp_name(name: str) -> str:
    name = clean(name)
    return name if name.endswith(EVIDENCE_KP_SUFFIX) else f"{name}{EVIDENCE_KP_SUFFIX}"


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(nonempty(item) for item in value)
    return clean(value) != ""


def compact_props(props: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in props.items():
        if value is None:
            continue
        if isinstance(value, str):
            cleaned[key] = value.strip()
        elif isinstance(value, list):
            cleaned[key] = [item for item in value if nonempty(item)]
        else:
            cleaned[key] = value
    return {key: value for key, value in cleaned.items() if nonempty(value)}


def freeze_value(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, freeze_value(item)) for key, item in value.items()))
    return value


def thaw_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [thaw_value(item) for item in value]
    return value


def split_values(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    parts = re.split(r"[;；,，/、|]+", text)
    return [part.strip() for part in parts if part.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=2):
            cleaned = {key: clean(value) for key, value in row.items() if key is not None}
            if any(cleaned.values()):
                cleaned["_source_row_number"] = str(index)
                rows.append(cleaned)
    return rows


def source_row_id(csv_name: str, row: dict[str, str]) -> str:
    return f"{csv_name}:{row.get('_source_row_number', '')}"


def domain_for_document(domain: str, doc_name: str) -> str:
    domain = clean(domain)
    if domain == "hr":
        return "company"
    if domain == "business":
        return "course"
    if domain == "textbook":
        return "question_bank"
    if domain in {"regulation", "question_bank", "course", "company"}:
        return domain
    if "法规" in doc_name or "CCAR" in doc_name:
        return "regulation"
    if "题库" in doc_name or "教材" in doc_name:
        return "question_bank"
    return domain or "company"


def validate_label(label: str) -> str:
    if not VALID_TOKEN.match(label):
        raise ValueError(f"Unsafe Neo4j label: {label}")
    return label


def validate_rel_type(rel_type: str) -> str:
    if not VALID_TOKEN.match(rel_type):
        raise ValueError(f"Unsafe Neo4j relationship type: {rel_type}")
    return rel_type


@dataclass
class NodeSpec:
    label: str
    entity_id: str
    name: str
    domain: str
    props: dict[str, Any] = field(default_factory=dict)

    def neo4j_props(self) -> dict[str, Any]:
        props = {
            "entity_id": self.entity_id,
            "name": self.name,
            "canonical_name": self.props.get("canonical_name") or self.name,
            "domain": self.domain,
            "type": self.label,
            "schema_version": SCHEMA_VERSION,
            "sync_version": SYNC_VERSION,
            "sync_source": SYNC_SOURCE,
        }
        props.update(self.props)
        return compact_props(props)


@dataclass(frozen=True)
class RelSpec:
    start_id: str
    rel_type: str
    end_id: str
    props_key: str
    props: tuple[tuple[str, Any], ...]

    @classmethod
    def make(cls, start_id: str, rel_type: str, end_id: str, props: dict[str, Any] | None = None) -> "RelSpec":
        props = compact_props(props or {})
        props_key = stable_id("rel", start_id, rel_type, end_id, props.get("source_table"), props.get("source_doc"))
        return cls(start_id, rel_type, end_id, props_key, tuple(sorted((key, freeze_value(value)) for key, value in props.items())))

    def neo4j_props(self) -> dict[str, Any]:
        props = {key: thaw_value(value) for key, value in self.props}
        props.update(
            {
                "sync_key": self.props_key,
                "schema_version": SCHEMA_VERSION,
                "sync_version": SYNC_VERSION,
                "sync_source": SYNC_SOURCE,
            }
        )
        return compact_props(props)


class CanonicalData:
    def __init__(self, canonical_dir: Path):
        self.canonical_dir = canonical_dir
        self.tables = {
            path.stem: read_csv(path)
            for path in sorted(canonical_dir.glob("*.csv"))
        }
        self.documents = self.tables.get("documents", [])
        self.document_chunks = self.tables.get("document_chunks", [])
        self.chunks_by_document_id: dict[str, list[str]] = defaultdict(list)
        self.chunks_by_doc_name: dict[str, list[str]] = defaultdict(list)
        for row in self.document_chunks:
            chunk_id = row.get("chunk_id")
            if not chunk_id:
                continue
            self.chunks_by_document_id[row.get("document_id", "")].append(chunk_id)
            self.chunks_by_doc_name[row.get("doc_name", "")].append(chunk_id)
        self.document_by_id = {row["document_id"]: row for row in self.documents if row.get("document_id")}
        self.document_by_name = {row["doc_name"]: row for row in self.documents if row.get("doc_name")}

    def table(self, name: str) -> list[dict[str, str]]:
        return self.tables.get(name, [])

    def chunks_for_document(self, document_id: str = "", doc_name: str = "", limit: int = MAX_CHUNKS_PER_NODE) -> list[str]:
        chunks = self.chunks_by_document_id.get(document_id) or self.chunks_by_doc_name.get(doc_name) or []
        return chunks[:limit]

    def chunks_for_keywords(self, keywords: Iterable[str], domain: str | None = None, limit: int = MAX_REL_CHUNKS) -> list[str]:
        keywords = [kw for kw in keywords if kw]
        scored: list[tuple[int, str, list[str]]] = []
        for row in self.documents:
            if domain and row.get("domain") != domain:
                continue
            text = f"{row.get('doc_name', '')} {row.get('title', '')}"
            score = sum(1 for kw in keywords if kw and kw in text)
            if score:
                scored.append((score, row.get("document_id", ""), self.chunks_for_document(row.get("document_id", ""), row.get("doc_name", ""), limit)))
        scored.sort(key=lambda item: (-item[0], item[1]))
        chunks: list[str] = []
        for _, _, item_chunks in scored:
            for chunk in item_chunks:
                if chunk not in chunks:
                    chunks.append(chunk)
                if len(chunks) >= limit:
                    return chunks
        return chunks

    def default_chunks(self, purpose: str = "business", limit: int = MAX_REL_CHUNKS) -> list[str]:
        keyword_map = {
            "business": ["产品", "培训", "公司"],
            "course": ["产品", "培训", "课程"],
            "hr": ["员工", "薪酬", "面试", "制度"],
            "regulation": ["法规", "CCAR", "训练机构"],
            "question_bank": ["题库", "飞行", "气象", "法规"],
        }
        chunks = self.chunks_for_keywords(keyword_map.get(purpose, [purpose]), limit=limit)
        if chunks:
            return chunks
        for row in self.documents:
            chunks = self.chunks_for_document(row.get("document_id", ""), row.get("doc_name", ""), limit)
            if chunks:
                return chunks
        return []


class GraphPlan:
    def __init__(self, data: CanonicalData):
        self.data = data
        self.nodes: dict[str, NodeSpec] = {}
        self.rels: set[RelSpec] = set()
        self.rejected_rels: list[dict[str, Any]] = []
        self.company_id = "company_yunji"
        self.skill_ids: dict[str, str] = {}
        self.knowledge_point_ids: dict[str, str] = {}
        self.course_ids: list[str] = []
        self.regulation_ids: list[str] = []
        self.question_bank_ids: list[str] = []
        self.training_track_ids: list[str] = []

    def add_node(self, node: NodeSpec) -> str:
        existing = self.nodes.get(node.entity_id)
        if existing:
            merged = existing.neo4j_props()
            merged.update(node.neo4j_props())
            self.nodes[node.entity_id] = NodeSpec(node.label, node.entity_id, node.name or existing.name, node.domain or existing.domain, merged)
        else:
            self.nodes[node.entity_id] = node
        return node.entity_id

    def add_rel(self, start_id: str, rel_type: str, end_id: str, props: dict[str, Any] | None = None) -> None:
        if start_id in self.nodes and end_id in self.nodes:
            reason = relationship_missing_evidence_reason(rel_type, props)
            if reason:
                self.rejected_rels.append(
                    {
                        "start_id": start_id,
                        "rel_type": rel_type,
                        "end_id": end_id,
                        "reason": reason,
                        "props": compact_props(props or {}),
                    }
                )
                return
            self.rels.add(RelSpec.make(start_id, rel_type, end_id, props))

    def add_skill(self, name: str, chunks: list[str] | None = None, source_doc: str = "") -> str:
        name = clean(name)
        if not name:
            name = "无人机综合能力"
        if name in self.skill_ids:
            return self.skill_ids[name]
        entity_id = stable_id("skill", name)
        display_name = skill_display_name(name)
        chunks = chunks or self.data.default_chunks("question_bank")
        self.add_node(
            NodeSpec(
                "Skill",
                entity_id,
                display_name,
                "question_bank",
                {
                    "canonical_name": name,
                    "skill_name": name,
                    "source_doc": source_doc or "canonical_skill_rules",
                    "source_table": "derived_from_canonical_csv",
                    "source_chunk_ids": chunks[:MAX_CHUNKS_PER_NODE],
                    "evidence_contract": "source_doc_or_source_chunk_ids_to_sqlite",
                },
            )
        )
        self.skill_ids[name] = entity_id
        kp_id = self.add_knowledge_point(evidence_kp_name(name), chunks, source_doc)
        self.add_rel(entity_id, "MENTIONS", kp_id, self.rel_evidence("derived_from_canonical_csv", source_doc, chunks))
        return entity_id

    def add_knowledge_point(self, name: str, chunks: list[str] | None = None, source_doc: str = "") -> str:
        name = clean(name)
        if not name:
            name = "无人机综合知识点"
        if name in self.knowledge_point_ids:
            return self.knowledge_point_ids[name]
        entity_id = stable_id("kp", name)
        chunks = chunks or self.data.default_chunks("question_bank")
        self.add_node(
            NodeSpec(
                "KnowledgePoint",
                entity_id,
                name,
                "question_bank",
                {
                    "source_doc": source_doc or "canonical_knowledge_point_rules",
                    "source_table": "derived_from_canonical_csv",
                    "source_chunk_ids": chunks[:MAX_CHUNKS_PER_NODE],
                    "evidence_contract": "source_doc_or_source_chunk_ids_to_sqlite",
                },
            )
        )
        self.knowledge_point_ids[name] = entity_id
        return entity_id

    def rel_evidence(self, source_table: str, source_doc: str = "", chunks: list[str] | None = None, **extra: Any) -> dict[str, Any]:
        props = {
            "source_table": source_table,
            "source_doc": source_doc or source_table,
            "source_chunk_ids": (chunks or [])[:MAX_REL_CHUNKS],
            "evidence_contract": "source_doc_and_source_chunk_ids_to_sqlite" if chunks else "rejected_without_source_chunk_ids",
        }
        props.update(extra)
        return props

    def infer_skills(self, *texts: Any) -> list[str]:
        haystack = " ".join(clean(text) for text in texts)
        rules = [
            ("多旋翼操控", ["多旋翼", "旋翼"]),
            ("垂直起降固定翼操控", ["垂起", "垂直起降", "固定翼"]),
            ("单旋翼操控", ["单旋翼"]),
            ("超视距运行", ["超视距"]),
            ("视距内运行", ["视距内"]),
            ("教员教学能力", ["教员", "导师", "教学"]),
            ("地面站任务规划", ["地面站", "任务规划", "预规划"]),
            ("飞行原理", ["飞行原理", "飞行性能"]),
            ("气象判断", ["气象"]),
            ("空中交通管制", ["空中交通", "管制"]),
            ("法律法规合规", ["法规", "CCAR", "合规", "执照"]),
            ("客户跟进", ["客户", "销售", "跟进", "咨询"]),
            ("维修装配", ["维修", "装配"]),
            ("市场销售", ["市场", "销售", "大客户"]),
        ]
        found = [name for name, keywords in rules if any(keyword in haystack for keyword in keywords)]
        return found or ["无人机综合能力"]

    def infer_course_ids(self, *texts: Any, fallback_limit: int = 3) -> list[str]:
        haystack = " ".join(clean(text) for text in texts)
        scored: list[tuple[int, str]] = []
        for course_id in self.course_ids:
            course = self.nodes[course_id]
            text = f"{course.name} {course.props.get('content', '')} {course.props.get('course_type', '')}"
            score = 0
            for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", haystack):
                if len(token) >= 2 and token in text:
                    score += 1
            if any(keyword in haystack and keyword in text for keyword in ("多旋翼", "垂起", "固定翼", "单旋翼", "教员", "超视距", "视距内")):
                score += 3
            if score:
                scored.append((score, course_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        ids = [course_id for _, course_id in scored[:fallback_limit]]
        return ids or self.course_ids[:fallback_limit]

    def build(self) -> None:
        self.add_documents()
        self.add_company_and_policies()
        self.add_regulations()
        self.add_question_banks()
        self.add_courses()
        self.add_training_tracks()
        self.add_instructors()
        self.add_students()
        self.add_customers()
        self.add_jobs()
        self.add_core_cross_domain_links()

    def add_documents(self) -> None:
        for row in self.data.table("documents"):
            doc_name = row.get("doc_name", "")
            chunks = self.data.chunks_for_document(row.get("document_id", ""), doc_name)
            domain = domain_for_document(row.get("domain", ""), doc_name)
            entity_id = row.get("document_id") or stable_id("doc", doc_name)
            self.add_node(
                NodeSpec(
                    "Document",
                    entity_id,
                    row.get("title") or doc_name,
                    domain,
                    {
                        "document_id": entity_id,
                        "canonical_doc_name": doc_name,
                        "source_doc": doc_name,
                        "doc_name": doc_name,
                        "chunk_count": row.get("chunk_count"),
                        "source_table": "documents.csv",
                        "source_csv": "documents.csv",
                        "source_row_id": source_row_id("documents.csv", row),
                        "source_chunk_ids": chunks,
                        "evidence_contract": "source_doc_and_source_chunk_ids_to_sqlite",
                    },
                )
            )
        for row in self.data.table("document_chunks"):
            chunk_id = row.get("chunk_id")
            document_id = row.get("document_id")
            if not chunk_id or document_id not in self.nodes:
                continue
            self.add_node(
                NodeSpec(
                    "ChunkRef",
                    chunk_id,
                    chunk_id,
                    domain_for_document(row.get("domain", ""), row.get("doc_name", "")),
                    {
                        "chunk_id": chunk_id,
                        "source_doc": row.get("doc_name"),
                        "doc_name": row.get("doc_name"),
                        "chunk_index": row.get("chunk_index"),
                        "source_table": "document_chunks.csv",
                        "source_csv": "document_chunks.csv",
                        "source_row_id": source_row_id("document_chunks.csv", row),
                        "source_chunk_ids": [chunk_id],
                        "evidence_contract": "sqlite_chunk_text",
                    },
                )
            )
            self.add_rel(
                document_id,
                "CONTAINS",
                chunk_id,
                self.rel_evidence("document_chunks.csv", row.get("doc_name", ""), [chunk_id], source_row_id=source_row_id("document_chunks.csv", row)),
            )

    def add_company_and_policies(self) -> None:
        hr_chunks = self.data.default_chunks("hr")
        self.add_node(
            NodeSpec(
                "Company",
                self.company_id,
                "湖北云技科技有限公司",
                "company",
                {
                    "source_doc": "documents.csv",
                    "source_table": "documents.csv",
                    "source_chunk_ids": hr_chunks,
                    "evidence_contract": "source_doc_or_source_chunk_ids_to_sqlite",
                },
            )
        )
        policy_docs = [
            row for row in self.data.table("documents")
            if row.get("domain") == "hr" or any(keyword in row.get("title", "") for keyword in ("制度", "薪酬", "员工", "面试"))
        ]
        for row in policy_docs:
            chunks = self.data.chunks_for_document(row.get("document_id", ""), row.get("doc_name", ""))
            policy_id = stable_id("policy", row.get("document_id") or row.get("title"))
            self.add_node(
                NodeSpec(
                    "Policy",
                    policy_id,
                    row.get("title") or row.get("doc_name"),
                    "company",
                    {
                        "source_doc": row.get("doc_name"),
                        "source_table": "documents.csv",
                        "source_chunk_ids": chunks,
                        "evidence_contract": "source_doc_and_source_chunk_ids_to_sqlite",
                    },
                )
            )
            self.add_rel(policy_id, "DEFINED_BY", row.get("document_id"), self.rel_evidence("documents.csv", row.get("doc_name"), chunks))
            self.add_rel(policy_id, "AFFECTS", self.company_id, self.rel_evidence("documents.csv", row.get("doc_name"), chunks))

    def add_regulations(self) -> None:
        for row in self.data.table("regulations"):
            chunks = self.data.chunks_for_document(row.get("document_id", ""), row.get("doc_name", ""))
            entity_id = row.get("regulation_id") or stable_id("reg", row.get("title"))
            self.regulation_ids.append(entity_id)
            self.add_node(
                NodeSpec(
                    "Regulation",
                    entity_id,
                    row.get("title") or row.get("doc_name"),
                    "regulation",
                    {
                        "document_id": row.get("document_id"),
                        "source_doc": row.get("doc_name"),
                        "source_table": "regulations.csv",
                        "source_csv": "regulations.csv",
                        "source_row_id": source_row_id("regulations.csv", row),
                        "chunk_count": row.get("chunk_count"),
                        "source_chunk_ids": chunks,
                        "evidence_contract": "source_doc_and_source_chunk_ids_to_sqlite",
                    },
                )
            )
            if row.get("document_id") in self.nodes:
                self.add_rel(entity_id, "PART_OF", row["document_id"], self.rel_evidence("regulations.csv", row.get("doc_name"), chunks))
            for skill_name in ("法律法规合规", "超视距运行", "飞行原理"):
                skill_id = self.add_skill(skill_name, chunks, row.get("doc_name"))
                kp_id = self.add_knowledge_point(evidence_kp_name(skill_name), chunks, row.get("doc_name"))
                self.add_rel(skill_id, "DEFINED_BY", entity_id, self.rel_evidence("regulations.csv", row.get("doc_name"), chunks))
                self.add_rel(kp_id, "DEFINED_BY", entity_id, self.rel_evidence("regulations.csv", row.get("doc_name"), chunks))
                self.add_rel(entity_id, "MENTIONS", kp_id, self.rel_evidence("regulations.csv", row.get("doc_name"), chunks))

    def add_question_banks(self) -> None:
        for row in self.data.table("question_banks"):
            chunks = self.data.chunks_for_document(row.get("document_id", ""), row.get("doc_name", ""))
            entity_id = row.get("question_bank_id") or stable_id("qbank", row.get("bank_title"))
            self.question_bank_ids.append(entity_id)
            self.add_node(
                NodeSpec(
                    "QuestionBank",
                    entity_id,
                    row.get("bank_title") or row.get("doc_name"),
                    "question_bank",
                    {
                        "document_id": row.get("document_id"),
                        "source_doc": row.get("doc_name"),
                        "source_table": "question_banks.csv",
                        "source_csv": "question_banks.csv",
                        "source_row_id": source_row_id("question_banks.csv", row),
                        "chunk_count": row.get("chunk_count"),
                        "source_chunk_ids": chunks,
                        "evidence_contract": "source_doc_and_source_chunk_ids_to_sqlite",
                    },
                )
            )
            if row.get("document_id") in self.nodes:
                self.add_rel(entity_id, "PART_OF", row["document_id"], self.rel_evidence("question_banks.csv", row.get("doc_name"), chunks))
            for skill_name in self.infer_skills(row.get("bank_title"), row.get("doc_name")) + ["法律法规合规", "飞行原理"]:
                kp_id = self.add_knowledge_point(evidence_kp_name(skill_name), chunks, row.get("doc_name"))
                self.add_rel(entity_id, "MENTIONS", kp_id, self.rel_evidence("question_banks.csv", row.get("doc_name"), chunks))

    def add_courses(self) -> None:
        course_chunks = self.data.default_chunks("course")
        for row in self.data.table("courses"):
            entity_id = row.get("course_id") or stable_id("crs", row.get("course_name"))
            self.course_ids.append(entity_id)
            self.add_node(
                NodeSpec(
                    "Course",
                    entity_id,
                    row.get("course_name"),
                    "course",
                    {
                        "course_type": row.get("course_type"),
                        "price": row.get("price"),
                        "duration": row.get("duration"),
                        "content": row.get("content"),
                        "source_doc": row.get("source_table") or "courses.csv",
                        "source_table": "courses.csv",
                        "source_csv": "courses.csv",
                        "source_row_id": source_row_id("courses.csv", row),
                        "natural_key": row.get("natural_key"),
                        "source_chunk_ids": course_chunks,
                        "evidence_contract": "canonical_csv_source_row",
                    },
                )
            )
            self.add_rel(self.company_id, "OFFERS", entity_id, self.rel_evidence("courses.csv", row.get("source_table"), course_chunks))
            for doc in self.data.table("documents"):
                if doc.get("domain") == "business" or "产品" in doc.get("title", "") or "培训" in doc.get("title", ""):
                    chunks = self.data.chunks_for_document(doc.get("document_id", ""), doc.get("doc_name", ""))
                    self.add_rel(entity_id, "DESCRIBES", doc["document_id"], self.rel_evidence("documents.csv", doc.get("doc_name"), chunks))
            for skill_name in self.infer_skills(row.get("course_name"), row.get("duration"), row.get("content")):
                skill_id = self.add_skill(skill_name, self.data.default_chunks("question_bank"), "question_banks.csv")
                self.add_rel(entity_id, "REQUIRES", skill_id, self.rel_evidence("courses.csv", row.get("source_table"), course_chunks))
                for reg_id in self.regulation_ids:
                    self.add_rel(skill_id, "DEFINED_BY", reg_id, self.rel_evidence("regulations.csv", "regulations.csv", self.data.default_chunks("regulation")))
            for reg_id in self.regulation_ids:
                self.add_rel(entity_id, "REGULATES", reg_id, self.rel_evidence("regulations.csv", "regulations.csv", self.data.default_chunks("regulation")))
            for prop_name in ("price", "duration", "content"):
                if not row.get(prop_name):
                    continue
                value_id = stable_id("value", entity_id, prop_name, row.get(prop_name))
                self.add_node(
                    NodeSpec(
                        "Value",
                        value_id,
                        f"{row.get('course_name')} {prop_name} {row.get(prop_name)}",
                        "course",
                        {
                            "property_name": prop_name,
                            "value": row.get(prop_name),
                            "source_doc": row.get("source_table") or "courses.csv",
                            "source_table": "courses.csv",
                            "source_csv": "courses.csv",
                            "source_row_id": source_row_id("courses.csv", row),
                            "source_chunk_ids": course_chunks,
                            "evidence_contract": "canonical_csv_source_row",
                        },
                    )
                )
                self.add_rel(entity_id, "HAS_PROPERTY", value_id, self.rel_evidence("courses.csv", row.get("source_table"), course_chunks, property_name=prop_name))
                for doc in self.data.table("documents"):
                    if doc.get("domain") == "business" or "产品" in doc.get("title", ""):
                        chunks = self.data.chunks_for_document(doc.get("document_id", ""), doc.get("doc_name", ""))
                        self.add_rel(value_id, "DEFINED_BY", doc["document_id"], self.rel_evidence("documents.csv", doc.get("doc_name"), chunks))

    def add_training_tracks(self) -> None:
        track_chunks = self.data.default_chunks("course")
        for row in self.data.table("training_tracks"):
            entity_id = row.get("training_track_id") or stable_id("trk", row.get("machine_type"), row.get("level"), row.get("class_type"))
            self.training_track_ids.append(entity_id)
            name = " ".join(part for part in (row.get("machine_type"), row.get("level"), row.get("class_type")) if part)
            self.add_node(
                NodeSpec(
                    "TrainingTrack",
                    entity_id,
                    name,
                    "course",
                    {
                        "machine_type": row.get("machine_type"),
                        "level": row.get("level"),
                        "class_type": row.get("class_type"),
                        "start_rule": row.get("start_rule"),
                        "cycle": row.get("cycle"),
                        "lodging": row.get("lodging"),
                        "capacity": row.get("capacity"),
                        "source_doc": row.get("source_table") or "training_tracks.csv",
                        "source_table": "training_tracks.csv",
                        "source_csv": "training_tracks.csv",
                        "source_row_id": source_row_id("training_tracks.csv", row),
                        "source_chunk_ids": track_chunks,
                        "evidence_contract": "canonical_csv_source_row",
                    },
                )
            )
            for course_id in self.infer_course_ids(row.get("machine_type"), row.get("level"), row.get("class_type"), fallback_limit=3):
                self.add_rel(course_id, "HAS_CLASS", entity_id, self.rel_evidence("training_tracks.csv", row.get("source_table"), track_chunks))
            for reg_id in self.regulation_ids:
                self.add_rel(entity_id, "REGULATES", reg_id, self.rel_evidence("regulations.csv", "regulations.csv", self.data.default_chunks("regulation")))
            for prop_name in ("cycle", "capacity", "lodging", "start_rule"):
                if not row.get(prop_name):
                    continue
                value_id = stable_id("value", entity_id, prop_name, row.get(prop_name))
                self.add_node(
                    NodeSpec(
                        "Value",
                        value_id,
                        f"{name} {prop_name} {row.get(prop_name)}",
                        "course",
                        {
                            "property_name": prop_name,
                            "value": row.get(prop_name),
                            "source_doc": row.get("source_table") or "training_tracks.csv",
                            "source_table": "training_tracks.csv",
                            "source_csv": "training_tracks.csv",
                            "source_row_id": source_row_id("training_tracks.csv", row),
                            "source_chunk_ids": track_chunks,
                            "evidence_contract": "canonical_csv_source_row",
                        },
                    )
                )
                self.add_rel(entity_id, "HAS_PROPERTY", value_id, self.rel_evidence("training_tracks.csv", row.get("source_table"), track_chunks, property_name=prop_name))

    def add_instructors(self) -> None:
        chunks = self.data.default_chunks("course")
        for row in self.data.table("instructors"):
            entity_id = row.get("instructor_id") or stable_id("ins", row.get("name"))
            self.add_node(
                NodeSpec(
                    "Instructor",
                    entity_id,
                    row.get("name"),
                    "instructor",
                    {
                        "source_doc": "instructors.csv",
                        "source_table": "instructors.csv",
                        "source_csv": "instructors.csv",
                        "source_row_id": source_row_id("instructors.csv", row),
                        "source_tables": row.get("source_tables"),
                        "source_chunk_ids": chunks,
                        "evidence_contract": "canonical_csv_source_row",
                    },
                )
            )
            for skill_name in ("教员教学能力", "无人机综合能力"):
                skill_id = self.add_skill(skill_name, self.data.default_chunks("question_bank"), "question_banks.csv")
                self.add_rel(entity_id, "REQUIRES_SKILL", skill_id, self.rel_evidence("instructors.csv", "instructors.csv", chunks))
                for course_id in self.course_ids[:5]:
                    self.add_rel(entity_id, "REFERS_TO", course_id, self.rel_evidence("instructors.csv", "instructors.csv", chunks))

    def add_students(self) -> None:
        chunks = self.data.default_chunks("course")
        for row in self.data.table("students"):
            entity_id = row.get("student_id") or stable_id("stu", row.get("student_name"))
            self.add_node(
                NodeSpec(
                    "Student",
                    entity_id,
                    row.get("student_name"),
                    "student",
                    {
                        "instructor_id": row.get("instructor_id"),
                        "instructor_name": row.get("instructor_name"),
                        "aircraft_type": row.get("aircraft_type"),
                        "class_type": row.get("class_type"),
                        "theory_exam_plan": row.get("theory_exam_plan"),
                        "practical_exam_plan": row.get("practical_exam_plan"),
                        "source_doc": row.get("source_table") or "students.csv",
                        "source_table": "students.csv",
                        "source_csv": "students.csv",
                        "source_row_id": source_row_id("students.csv", row),
                        "source_chunk_ids": chunks,
                        "evidence_contract": "canonical_csv_source_row",
                    },
                )
            )
            if row.get("instructor_id") in self.nodes:
                self.add_rel(row["instructor_id"], "REFERS_TO", entity_id, self.rel_evidence("students.csv", row.get("source_table"), chunks))
            for course_id in self.infer_course_ids(row.get("aircraft_type"), row.get("class_type"), row.get("practical_exam_plan"), fallback_limit=2):
                self.add_rel(entity_id, "REFERS_TO", course_id, self.rel_evidence("students.csv", row.get("source_table"), chunks))
            for skill_name in self.infer_skills(row.get("aircraft_type"), row.get("class_type"), row.get("practical_exam_plan")):
                skill_id = self.add_skill(skill_name, self.data.default_chunks("question_bank"), "question_banks.csv")
                self.add_rel(entity_id, "REQUIRES", skill_id, self.rel_evidence("students.csv", row.get("source_table"), chunks))

    def add_customers(self) -> None:
        source_rows: dict[str, list[str]] = defaultdict(list)
        notes_by_customer: dict[str, list[str]] = defaultdict(list)
        for row in self.data.table("customer_source_rows"):
            if row.get("customer_id"):
                source_rows[row["customer_id"]].append(f"{row.get('source_table')}:{row.get('source_row')}")
                notes_by_customer[row["customer_id"]].extend([row.get("intention", ""), row.get("notes", ""), row.get("region", "")])
        chunks = self.data.default_chunks("course")
        for row in self.data.table("customers"):
            entity_id = row.get("customer_id") or stable_id("cus", row.get("display_name"), row.get("best_contact_key"))
            self.add_node(
                NodeSpec(
                    "Customer",
                    entity_id,
                    row.get("display_name") or row.get("primary_contact") or entity_id,
                    "customer",
                    {
                        "primary_contact": row.get("primary_contact"),
                        "customer_class": row.get("customer_class"),
                        "regions": row.get("regions"),
                        "intentions": row.get("intentions"),
                        "sources": row.get("sources"),
                        "source_doc": "customers.csv",
                        "source_table": "customers.csv;customer_source_rows.csv",
                        "source_csv": "customers.csv",
                        "source_row_id": source_row_id("customers.csv", row),
                        "source_row": source_rows.get(entity_id, []),
                        "source_tables": row.get("source_tables"),
                        "source_chunk_ids": chunks,
                        "evidence_contract": "canonical_csv_source_row",
                    },
                )
            )
            texts = [row.get("intentions"), row.get("regions"), row.get("customer_class"), " ".join(notes_by_customer.get(entity_id, []))]
            for course_id in self.infer_course_ids(*texts, fallback_limit=3):
                self.add_rel(entity_id, "REFERS_TO", course_id, self.rel_evidence("customers.csv", "customers.csv", chunks))
            for policy_id, node in self.nodes.items():
                if node.label == "Policy" and ("客户" in node.name or "制度" in node.name):
                    self.add_rel(policy_id, "AFFECTS", entity_id, self.rel_evidence("documents.csv", node.props.get("source_doc"), node.props.get("source_chunk_ids", [])))

    def add_jobs(self) -> None:
        chunks = self.data.default_chunks("business")
        job_titles = {clean(row.get("job_title")) for row in self.data.table("jobs") if clean(row.get("job_title"))}
        for row in self.data.table("jobs"):
            entity_id = row.get("job_id") or stable_id("job", row.get("job_title"), row.get("company"), row.get("location"))
            job_title = clean(row.get("job_title")) or clean(row.get("category")) or entity_id
            self.add_node(
                NodeSpec(
                    "Position",
                    entity_id,
                    job_title,
                    "job_market",
                    {
                        "platform": row.get("platform"),
                        "company": row.get("company"),
                        "location": row.get("location"),
                        "category": row.get("category"),
                        "salary_values": row.get("salary_values"),
                        "education": row.get("education"),
                        "experience": row.get("experience"),
                        "source_doc": "jobs.csv",
                        "source_table": "jobs.csv",
                        "source_csv": "jobs.csv",
                        "source_row_id": source_row_id("jobs.csv", row),
                        "source_chunk_ids": chunks,
                        "evidence_contract": "canonical_csv_source_row",
                    },
                )
            )
            raw_company_name = clean(row.get("company"))
            company_name = raw_company_name or "未标注招聘公司"
            company_id_prefix = "company"
            company_extra: dict[str, Any] = {}
            if company_name in job_titles:
                company_id_prefix = "company_unknown"
                company_extra = {
                    "raw_company_name": raw_company_name,
                    "company_name_disambiguated": True,
                    "company_name_disambiguation_reason": "company_name_matches_job_title",
                }
                company_name = f"未标注招聘公司（{job_title[:28]}）"
            company_id = (
                stable_id(company_id_prefix, company_name, entity_id)
                if company_id_prefix == "company_unknown"
                else stable_id(company_id_prefix, company_name)
            )
            company_props = {
                "source_doc": "jobs.csv",
                "source_table": "jobs.csv",
                "source_csv": "jobs.csv",
                "source_row_id": source_row_id("jobs.csv", row),
                "source_chunk_ids": chunks,
                "evidence_contract": "canonical_csv_source_row",
            }
            company_props.update(company_extra)
            self.add_node(
                NodeSpec(
                    "Company",
                    company_id,
                    company_name,
                    "job_market",
                    company_props,
                )
            )
            self.add_rel(entity_id, "BELONGS_TO", company_id, self.rel_evidence("jobs.csv", "jobs.csv", chunks))
            self.add_rel(self.company_id, "BELONGS_TO", entity_id, self.rel_evidence("jobs.csv", "jobs.csv", chunks))
            for skill_name in self.infer_skills(row.get("job_title"), row.get("category"), row.get("education"), row.get("experience")):
                skill_id = self.add_skill(skill_name, self.data.default_chunks("question_bank"), "question_banks.csv")
                self.add_rel(entity_id, "REQUIRES_SKILL", skill_id, self.rel_evidence("jobs.csv", "jobs.csv", chunks))

    def add_core_cross_domain_links(self) -> None:
        reg_chunks = self.data.default_chunks("regulation")
        qbank_chunks = self.data.default_chunks("question_bank")
        for course_id in self.course_ids:
            for track_id in self.training_track_ids:
                if course_id in self.nodes and track_id in self.nodes:
                    course_name = self.nodes[course_id].name
                    track_name = self.nodes[track_id].name
                    if any(token and token in course_name for token in split_values(track_name.replace(" ", "、"))) or len(self.training_track_ids) <= 5:
                        self.add_rel(course_id, "HAS_CLASS", track_id, self.rel_evidence("training_tracks.csv", "training_tracks.csv", self.data.default_chunks("course")))
        for skill_id in list(self.skill_ids.values()):
            for reg_id in self.regulation_ids:
                self.add_rel(skill_id, "DEFINED_BY", reg_id, self.rel_evidence("regulations.csv", "regulations.csv", reg_chunks))
            for qbank_id in self.question_bank_ids:
                for kp_id in self.knowledge_point_ids.values():
                    self.add_rel(qbank_id, "MENTIONS", kp_id, self.rel_evidence("question_banks.csv", "question_banks.csv", qbank_chunks))
        for doc_id, node in list(self.nodes.items()):
            if node.label == "Document" and node.domain in {"question_bank", "regulation", "company", "course"}:
                for kp_id in self.knowledge_point_ids.values():
                    self.add_rel(doc_id, "MENTIONS", kp_id, self.rel_evidence("documents.csv", node.props.get("source_doc"), node.props.get("source_chunk_ids", [])))
        for policy_id, node in list(self.nodes.items()):
            if node.label != "Policy":
                continue
            chunks = node.props.get("source_chunk_ids", [])
            for course_id in self.course_ids[:5]:
                self.add_rel(policy_id, "AFFECTS", course_id, self.rel_evidence("documents.csv", node.props.get("source_doc"), chunks))
            for position_id, position in list(self.nodes.items()):
                if position.label == "Position" and (position.domain == "job_market" or "入职" in node.name or "薪酬" in node.name):
                    self.add_rel(policy_id, "AFFECTS", position_id, self.rel_evidence("documents.csv", node.props.get("source_doc"), chunks))


class Neo4jSync:
    def __init__(self, uri: str, user: str, password: str, dry_run: bool = False):
        self.driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5)
        self.dry_run = dry_run

    def close(self) -> None:
        self.driver.close()

    def merge_node(self, session, node: NodeSpec, run_id: str) -> bool:
        label = validate_label(node.label)
        props = node.neo4j_props()
        query = f"""
        MERGE (n:Entity:{label} {{entity_id: $entity_id}})
        ON CREATE SET n._business_sync_created_run_id = $run_id,
                      n._business_sync_created_at = datetime()
        SET n += $props,
            n._business_sync_last_run_id = $run_id,
            n._business_sync_updated_at = datetime()
        RETURN n._business_sync_created_run_id = $run_id AS created
        """
        record = session.run(query, entity_id=node.entity_id, props=props, run_id=run_id).single()
        return bool(record and record["created"])

    def merge_rel(self, session, rel: RelSpec, run_id: str) -> bool:
        rel_type = validate_rel_type(rel.rel_type)
        props = rel.neo4j_props()
        reason = relationship_missing_evidence_reason(rel.rel_type, props)
        if reason:
            raise ValueError(f"Refusing to sync {rel.rel_type} without required evidence: {reason}")
        query = f"""
        MATCH (a {{entity_id: $start_id}})
        MATCH (b {{entity_id: $end_id}})
        MERGE (a)-[r:{rel_type} {{sync_key: $sync_key}}]->(b)
        ON CREATE SET r._business_sync_created_run_id = $run_id,
                      r._business_sync_created_at = datetime()
        SET r += $props,
            r._business_sync_last_run_id = $run_id,
            r._business_sync_updated_at = datetime()
        RETURN r._business_sync_created_run_id = $run_id AS created
        """
        record = session.run(
            query,
            start_id=rel.start_id,
            end_id=rel.end_id,
            sync_key=rel.props_key,
            props=props,
            run_id=run_id,
        ).single()
        return bool(record and record["created"])

    def missing_evidence(self, session, run_id: str) -> dict[str, Any]:
        node_rows = session.run(
            """
            MATCH (n)
            WHERE n._business_sync_last_run_id = $run_id
              AND NOT (
                (n.source_doc IS NOT NULL AND toString(n.source_doc) <> '') OR
                (n.source_table IS NOT NULL AND toString(n.source_table) <> '') OR
                (n.source_csv IS NOT NULL AND toString(n.source_csv) <> '') OR
                (n.source_chunk_ids IS NOT NULL AND size(n.source_chunk_ids) > 0) OR
                (n.chunk_id IS NOT NULL AND toString(n.chunk_id) <> '')
              )
            RETURN labels(n) AS labels, count(n) AS count
            ORDER BY count DESC
            """,
            run_id=run_id,
        ).data()
        rel_rows = session.run(
            """
            MATCH ()-[r]->()
            WHERE r._business_sync_last_run_id = $run_id
              AND NOT (
                (r.source_doc IS NOT NULL AND toString(r.source_doc) <> '') OR
                (r.source_table IS NOT NULL AND toString(r.source_table) <> '') OR
                (r.source_chunk_ids IS NOT NULL AND size(r.source_chunk_ids) > 0)
              )
            RETURN type(r) AS type, count(r) AS count
            ORDER BY count DESC
            """,
            run_id=run_id,
        ).data()
        return {
            "nodes": node_rows,
            "relationships": rel_rows,
            "total": sum(int(row["count"]) for row in node_rows) + sum(int(row["count"]) for row in rel_rows),
        }

    def sync(self, plan: GraphPlan, run_id: str) -> dict[str, Any]:
        if self.dry_run:
            return {
                "dry_run": True,
                "planned_nodes": len(plan.nodes),
                "planned_relationships": len(plan.rels),
                "rejected_relationships": len(plan.rejected_rels),
                "rejected_relationship_reasons": dict(Counter(item["reason"] for item in plan.rejected_rels)),
                "planned_node_labels": dict(Counter(node.label for node in plan.nodes.values())),
                "planned_relationship_types": dict(Counter(rel.rel_type for rel in plan.rels)),
            }

        stats = {
            "nodes_created": 0,
            "nodes_updated": 0,
            "relationships_created": 0,
            "relationships_updated": 0,
            "rejected_relationships": len(plan.rejected_rels),
            "rejected_relationship_reasons": dict(Counter(item["reason"] for item in plan.rejected_rels)),
            "node_labels": dict(Counter(node.label for node in plan.nodes.values())),
            "relationship_types": dict(Counter(rel.rel_type for rel in plan.rels)),
        }
        with self.driver.session() as session:
            for node in plan.nodes.values():
                created = self.merge_node(session, node, run_id)
                stats["nodes_created" if created else "nodes_updated"] += 1
            for rel in sorted(plan.rels, key=lambda item: (item.rel_type, item.start_id, item.end_id, item.props_key)):
                created = self.merge_rel(session, rel, run_id)
                stats["relationships_created" if created else "relationships_updated"] += 1
            stats["missing_evidence"] = self.missing_evidence(session, run_id)
        return {"dry_run": False, **stats}


def read_password(project_root: Path) -> str:
    return os.environ.get("NEO4J_PASSWORD") or os.environ.get("NEO4J_PASS") or (project_root / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-dir", default=str(DEFAULT_CANONICAL_DIR))
    parser.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT))
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    canonical_dir = Path(args.canonical_dir).expanduser()
    project_root = Path(args.project_root).expanduser()
    data = CanonicalData(canonical_dir)
    plan = GraphPlan(data)
    plan.build()
    run_id = f"{SYNC_VERSION}:{now_utc()}"
    sync = Neo4jSync(args.neo4j_uri, args.neo4j_user, read_password(project_root), dry_run=args.dry_run)
    try:
        result = sync.sync(plan, run_id)
    finally:
        sync.close()

    report = {
        "generated_at": now_utc(),
        "run_id": run_id,
        "canonical_dir": str(canonical_dir),
        "neo4j_uri": args.neo4j_uri,
        "schema_version": SCHEMA_VERSION,
        "sync_version": SYNC_VERSION,
        "source_tables": {name: len(rows) for name, rows in sorted(data.tables.items())},
        **result,
    }
    report_path = Path(args.report).expanduser()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(report_path),
                "dry_run": report["dry_run"],
                "nodes_created": report.get("nodes_created", 0),
                "nodes_updated": report.get("nodes_updated", 0),
                "relationships_created": report.get("relationships_created", 0),
                "relationships_updated": report.get("relationships_updated", 0),
                "missing_evidence_total": (report.get("missing_evidence") or {}).get("total", 0),
                "planned_nodes": report.get("planned_nodes"),
                "planned_relationships": report.get("planned_relationships"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
