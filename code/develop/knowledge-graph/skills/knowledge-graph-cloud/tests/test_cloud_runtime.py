#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from deploy.cloud_v2.authority_builder import (
    AUTHORITY_SCHEMA_SQL,
    _write_json_impl as write_json,
)
from deploy.cloud_v2.candidate_builder import (
    _build_derived_candidate_impl as build_derived_candidate,
)
from deploy.cloud_v2.fake_providers import (
    FakeEmbeddingTransport,
    FakeServerAnswerTransport,
)
from deploy.cloud_v2.source_scope import sha256_file
import pipeline.cloud_runtime as CLOUD_RUNTIME
from pipeline.cloud_runtime import (
    CONFIG_SHA256_ENVIRONMENT_VARIABLE,
    CloudRuntimeConfig,
    CloudRuntimeConfigError,
    CloudRuntimeDependencyError,
    CloudRuntimeIntegrityError,
    CloudRuntimeResources,
    ReadOnlyAuthorityStore,
)
from rag_store.runtime_query_embedding import (
    EMBEDDING_RESPONSE_SCHEMA_VERSION,
    QueryEmbeddingClient,
    QueryEmbeddingIdentity,
    QueryEmbeddingPolicy,
)
from rag_store.runtime_neo4j_reader import READ_CYPHER
from rag_store.runtime_sqlite_reader import ReadOnlySQLiteError
import rag_store.runtime_vector_reader as RUNTIME_VECTOR
from rag_store.runtime_vector_reader import ReadOnlyVectorError
from rag_store.server_answer_coordinator import (
    CoordinatorPolicy,
    ServerAnswerCoordinator,
)
from rag_store.server_answer_model import (
    ServerAnswerChannel,
    ServerAnswerModelAdapter,
)
from rag_store.source_authority import (
    FROZEN_R9_SOURCE_SCOPE,
    filter_superseded,
    source_annotation,
    source_priority_key,
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _graph_edge_id(record: dict[str, object]) -> str:
    payload = json.dumps(
        [
            record["type"],
            record["from"],
            record["to"],
            record["evidence_chunk_ids"],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "edge:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utf8_byte_input_unit_meter(text: str) -> int:
    return len(text.encode("utf-8"))


class ByteMeterExternalEmbeddingTransport:
    """Pickle-safe transport fixture that enforces query-only byte metering."""

    def __call__(self, identity, payload, _deadline):
        if payload.get("purpose") != "query" or payload.get("input_type") != identity.input_type:
            raise AssertionError("runtime embedding purpose expanded")
        items = payload.get("items")
        if not isinstance(items, list) or len(items) != 1:
            raise AssertionError("runtime embedding request is not query-only")
        item = items[0]
        expected_units = _utf8_byte_input_unit_meter(str(item.get("text") or ""))
        if item.get("input_units") != expected_units:
            raise AssertionError("runtime embedding did not use the approved byte meter")
        values = [0.0] * identity.dimension
        values[0] = 1.0
        return {
            "schema_version": EMBEDDING_RESPONSE_SCHEMA_VERSION,
            "embedding_identity_sha256": identity.sha256,
            "vectors": [{"id": item["id"], "values": values}],
            "failed_ids": [],
            "usage": {
                "input_units": expected_units,
                "cost_microunits": 0,
            },
        }


class _FakeGraphResult:
    def __init__(self, records):
        self._records = [dict(item) for item in records]

    def __iter__(self):
        return iter(self._records)


class _FakeGraphSession:
    def __init__(self, driver, config):
        self.driver = driver
        self.config = dict(config)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return None

    def begin_transaction(self):
        self.driver.transaction_count += 1
        return self

    def run(self, query, parameters=None, **kwargs):
        text = getattr(query, "text", str(query))
        values = dict(parameters or {})
        values.update(kwargs)
        self.driver.calls.append(
            {
                "text": text,
                "parameters": values,
                "timeout": getattr(query, "timeout", None),
                "session": self.config,
            }
        )
        return _FakeGraphResult(self.driver.respond(text, values))


class _FakeGraphDriver:
    def __init__(self, entities, *, nodes, edges):
        self.entities = {str(item["entity_id"]): dict(item) for item in entities}
        self.nodes = [dict(item) for item in nodes]
        self.edges = [dict(item) for item in edges]
        self.calls = []
        self.closed = False
        self.transaction_count = 0

    def session(self, **config):
        return _FakeGraphSession(self, config)

    def close(self):
        self.closed = True

    def respond(self, text, parameters):
        if text == READ_CYPHER["entities_by_ids"]:
            selected = [
                self.entities[item]
                for item in parameters["entity_ids"]
                if item in self.entities
            ]
            selected.sort(key=lambda item: str(item["entity_id"]))
        elif text == READ_CYPHER["entities_by_terms"]:
            terms = [str(item).casefold() for item in parameters["terms"]]
            selected = [
                item
                for item in self.entities.values()
                if any(
                    str(item["canonical_name"]).lower() == term
                    or term in str(item["canonical_name"]).lower()
                    or str(item["canonical_name"]).lower() in term
                    for term in terms
                )
            ]
            selected.sort(
                key=lambda item: (
                    -len(str(item["canonical_name"])),
                    str(item["canonical_name"]),
                    str(item["entity_id"]),
                )
            )
        elif text == READ_CYPHER["entities_by_chunk_ids"]:
            chunk_ids = set(parameters["chunk_ids"])
            selected = [
                item
                for item in self.entities.values()
                if chunk_ids.intersection(item["evidence_chunk_ids"])
            ]
            selected.sort(key=lambda item: str(item["entity_id"]))
        elif text == READ_CYPHER["audit_nodes"]:
            selected = [
                item
                for item in sorted(self.nodes, key=lambda value: value["cursor"])
                if item["cursor"] > parameters["after_cursor"]
            ]
        elif text == READ_CYPHER["audit_edges"]:
            selected = [
                item
                for item in sorted(self.edges, key=lambda value: value["cursor"])
                if item["cursor"] > parameters["after_cursor"]
            ]
        else:
            raise AssertionError("unexpected Cypher")
        return selected[: int(parameters["limit"])]


class CloudRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="kg-cloud-runtime-test-")
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self._cleanup)
        self.channel = ServerAnswerChannel(
            channel_id="fake-primary",
            provider="fake-offline",
            base_url="https://fake.invalid/v1/answers",
            region="offline",
            model="fake-answer-v1",
            model_version="fake-answer-model-v1",
            api_version="v1",
            timeout_seconds=1.0,
            max_input_units=10000,
            max_output_units=1000,
            max_cost_microunits=0,
        )
        self.config_path = self._build_active_runtime()
        self.config_sha256 = sha256_file(self.config_path)
        runtime_config = json.loads(self.config_path.read_text(encoding="utf-8"))
        graph_manifest_path = (
            Path(runtime_config["active_root"])
            / runtime_config["graph"]["manifest_path"]
        )
        graph_manifest = json.loads(
            graph_manifest_path.read_text(encoding="utf-8")
        )
        self.graph_entities = [
            {
                **item,
                "authority_release_id": graph_manifest["authority_release_id"],
                "graph_release_id": graph_manifest["release_id"],
            }
            for item in graph_manifest["entities"]
        ]
        graph_records = [
            json.loads(line)
            for line in (
                graph_manifest_path.parent / graph_manifest["graph"]["path"]
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.graph_nodes = []
        self.graph_edges = []
        for index, record in enumerate(graph_records):
            if record["kind"] == "node":
                properties = {
                    "graph_release_id": graph_manifest["release_id"],
                    "authority_release_id": graph_manifest["authority_release_id"],
                    "node_id": record["node_id"],
                    **record["properties"],
                }
                if record["label"] == "Entity":
                    properties["entity_id"] = record["node_id"]
                self.graph_nodes.append(
                    {
                        "cursor": f"node:{index:08d}",
                        "labels": [record["label"]],
                        "properties": properties,
                    }
                )
            else:
                self.graph_edges.append(
                    {
                        "cursor": f"edge:{index:08d}",
                        "relationship_type": record["type"],
                        "from_node_id": record["from"],
                        "to_node_id": record["to"],
                        "properties": {
                            "graph_release_id": graph_manifest["release_id"],
                            "authority_release_id": graph_manifest[
                                "authority_release_id"
                            ],
                            "edge_id": _graph_edge_id(record),
                            "evidence_chunk_ids": record["evidence_chunk_ids"],
                        },
                    }
                )
        self.neo4j_environment = {
            "KG_TEST_NEO4J_URI": "bolt://127.0.0.1:7687",
            "KG_TEST_NEO4J_USERNAME": "kg-reader",
            "KG_TEST_NEO4J_PASSWORD": "fake-neo4j-credential",
            "KG_TEST_NEO4J_DATABASE": "kg-active",
        }
        self.graph_drivers = []

    def _graph_driver_factory(self, _uri, *, auth, **_config):
        self.assertEqual(("kg-reader", "fake-neo4j-credential"), auth)
        driver = _FakeGraphDriver(
            self.graph_entities,
            nodes=self.graph_nodes,
            edges=self.graph_edges,
        )
        self.graph_drivers.append(driver)
        return driver

    def _open_runtime(self) -> CloudRuntimeResources:
        return CloudRuntimeResources.open(
            self.config_path,
            expected_config_sha256=self.config_sha256,
            environment=self.neo4j_environment,
            graph_driver_factory=self._graph_driver_factory,
        )

    def _refresh_config_anchor(self) -> None:
        self.config_sha256 = sha256_file(self.config_path)

    def _cleanup(self) -> None:
        if self.root.exists():
            for directory, directories, files in os.walk(self.root):
                Path(directory).chmod(0o755)
                for name in directories:
                    (Path(directory) / name).chmod(0o755)
                for name in files:
                    (Path(directory) / name).chmod(0o644)
        self.temporary.cleanup()

    def _synthetic_authority(self) -> Path:
        authority_root = self.root / "candidate" / "authority"
        authority_root.mkdir(parents=True)
        database_path = authority_root / "rag_chunks.db"
        self.regulation_specs = tuple(
            {
                "doc_name": f"政策法规/合成法规-{index:02d}.txt",
                "short_name": f"合成法规{index}",
                "doc_type": "synthetic_regulation",
                "authority_rank": 800 - index * 50,
                "number": f"SYN-R9-{index:02d}",
                "effective_date": f"2026-09-{index:02d}",
                "status": "partially_superseded" if index == 7 else "current",
            }
            for index in range(1, 8)
        )
        row_specs: list[tuple[str, str, str]] = [
            (
                item["doc_name"],
                (
                    f"{item['short_name']}，编号 {item['number']}，"
                    f"自 {item['effective_date']} 起施行，适用于无人机。"
                ),
                "regulation",
            )
            for item in self.regulation_specs
        ]
        row_specs.extend(
            [
                (
                    "无人机理论书籍/合成气象教材.txt",
                    "气象条件会影响无人机飞行安全。",
                    "textbook",
                ),
                (
                    "无人机理论书籍/合成系统教材.txt",
                    "罗盘为无人机提供航向参考。",
                    "textbook",
                ),
                (
                    "无人机理论书籍/合成旧版教材.txt",
                    "旧版无人机驾驶员等级应让位于现行合成法规。",
                    "textbook",
                ),
            ]
        )
        row_specs.extend(
            (
                f"理论题库/合成题库-{index:02d}.txt",
                f"无人机合成离线题目 {index:02d}。",
                "question_bank",
            )
            for index in range(1, 26)
        )
        rows = [
            (
                "chunk:"
                + hashlib.sha1(
                    f"{doc_name}\0{text}".encode("utf-8"), usedforsecurity=False
                ).hexdigest(),
                text,
                doc_name,
                content_type,
            )
            for doc_name, text, content_type in row_specs
        ]
        self.synthetic_rows = {
            doc_name: {"chunk_id": chunk_id, "text": text}
            for chunk_id, text, doc_name, _content_type in rows
        }
        import_run_id = "cloud-v2:revision-a-r9:synthetic-offline-test"
        source_records: list[dict[str, object]] = []
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("PRAGMA user_version=1")
            connection.executescript(AUTHORITY_SCHEMA_SQL)
            for index, (chunk_id, text, doc_name, content_type) in enumerate(rows):
                source_id = "docsrc:" + hashlib.sha1(
                    doc_name.encode("utf-8"), usedforsecurity=False
                ).hexdigest()
                source_sha = hashlib.sha256(doc_name.encode("utf-8")).hexdigest()
                extracted_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                metadata = {
                    "byte_disposition": (
                        "unchanged-from-original-stop-a"
                        if index < 28
                        else "approved-redacted-copy"
                    ),
                    "chunking_policy": "cloud-v2-paragraph-1200-v1",
                    "source_relative_path_sha256": hashlib.sha256(
                        doc_name.encode("utf-8")
                    ).hexdigest(),
                }
                connection.execute(
                    """INSERT INTO document_sources (
                           document_source_id, doc_name, source_path, source_sha256,
                           source_page_count, authority, extractor_version, import_run_id,
                           metadata_json, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        source_id,
                        doc_name,
                        f"kb://knowledge_base/synthetic/{index}",
                        source_sha,
                        1,
                        "rag_chunks.db",
                        "cloud-v2-source-extractor-v1",
                        import_run_id,
                        json.dumps(
                            metadata,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "2026-09-02T00:00:00Z",
                        "2026-09-02T00:00:00Z",
                    ),
                )
                connection.execute(
                    "INSERT INTO documents (doc_name, doc_path, chunk_count, updated_at) VALUES (?, ?, ?, ?)",
                    (
                        doc_name,
                        f"kb://knowledge_base/synthetic/{index}",
                        1,
                        "2026-09-02T00:00:00Z",
                    ),
                )
                connection.execute(
                    "INSERT INTO chunks (chunk_id, text, doc_name, chunk_index, created_at) VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, text, doc_name, 0, "2026-09-02T00:00:00Z"),
                )
                connection.execute(
                    """INSERT INTO chunk_provenance (
                           chunk_id, document_source_id, source_sha256, import_run_id,
                           pdf_page_start, pdf_page_end, content_type, confidence,
                           review_status, evidence_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk_id,
                        source_id,
                        source_sha,
                        import_run_id,
                        1,
                        1,
                        content_type,
                        1.0,
                        "approved",
                        "{}",
                        "2026-09-02T00:00:00Z",
                    ),
                )
                source_records.append(
                    {
                        "relative_path": doc_name,
                        "source_sha256": source_sha,
                        "extracted_text_sha256": extracted_sha,
                        "page_count": 1,
                        "chunk_count": 1,
                    }
                )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        database_path.chmod(0o600)
        database_sha256 = sha256_file(database_path)
        manifest = {
            "schema_version": "cloud-rag-authority-v1",
            "release_id": f"rag-authority:revision-a-r9:{database_sha256[:16]}",
            "status": "candidate",
            "authority": {"owner": "rag_chunks.db", "join_key": "chunk_id"},
            "source_scope": dict(FROZEN_R9_SOURCE_SCOPE),
            "database": {
                "path": database_path.name,
                "sha256": database_sha256,
                "mode": "0600",
                "sqlite_user_version": 1,
                "integrity_check": "ok",
                "foreign_key_violation_count": 0,
            },
            "build": {
                "chunking_policy": "cloud-v2-paragraph-1200-v1",
                "extractor_version": "cloud-v2-source-extractor-v1",
                "import_run_id": import_run_id,
                "network_calls": 0,
                "old_authority_reused": False,
                "ocr_runtime": None,
            },
            "counts": {
                "documents": len(rows),
                "chunks": len(rows),
                "provenance": len(rows),
            },
            "sources": source_records,
        }
        write_json(authority_root / "authority-manifest.json", manifest)
        return authority_root

    def _write_synthetic_registries(
        self, authority_manifest: dict[str, object], governance_root: Path
    ) -> tuple[Path, Path]:
        governance_root.mkdir()
        authority_binding = {
            "release_id": authority_manifest["release_id"],
            "database_sha256": authority_manifest["database"]["sha256"],
        }
        documents = []
        for item in self.regulation_specs:
            row = self.synthetic_rows[item["doc_name"]]
            documents.append(
                {
                    **item,
                    "evidence": [
                        {
                            "chunk_id": row["chunk_id"],
                            "text_sha256": hashlib.sha256(
                                row["text"].encode("utf-8")
                            ).hexdigest(),
                            "proofs": ["number", "effective_date"],
                            "required_markers": [
                                item["number"],
                                item["effective_date"],
                            ],
                        }
                    ],
                }
            )
        timeline = {
            "schema_version": "cloud-v2-regulation-timeline-r9-v1",
            "authority": {
                **authority_binding,
                "regulation_document_count": 7,
            },
            "documents": documents,
        }
        source_doc = "无人机理论书籍/合成旧版教材.txt"
        source_row = self.synthetic_rows[source_doc]
        target_doc = self.regulation_specs[0]["doc_name"]
        target_row = self.synthetic_rows[target_doc]
        superseded = {
            "schema_version": "cloud-v2-superseded-passages-r9-v1",
            "authority": authority_binding,
            "passages": [
                {
                    "id": "synthetic-legacy-pilot-grades",
                    "doc_name": source_doc,
                    "chunks": [
                        {
                            "chunk_id": source_row["chunk_id"],
                            "text_sha256": hashlib.sha256(
                                source_row["text"].encode("utf-8")
                            ).hexdigest(),
                        }
                    ],
                    "topic": "synthetic legacy pilot grades",
                    "topic_markers": ["驾驶员", "等级"],
                    "keep_when_exact_question_match": False,
                    "superseded_by": [
                        {
                            "doc_name": target_doc,
                            "chunk_id": target_row["chunk_id"],
                            "text_sha256": hashlib.sha256(
                                target_row["text"].encode("utf-8")
                            ).hexdigest(),
                        }
                    ],
                    "reason_code": "synthetic_later_regulation",
                }
            ],
        }
        timeline_path = governance_root / "regulation_timeline.json"
        superseded_path = governance_root / "superseded_passages.json"
        timeline_path.write_bytes(_canonical_bytes(timeline))
        superseded_path.write_bytes(_canonical_bytes(superseded))
        return timeline_path, superseded_path

    def _build_active_runtime(self) -> Path:
        authority_candidate = self._synthetic_authority()
        derived_candidate = self.root / "candidate" / "derived"
        build_derived_candidate(authority_candidate, derived_candidate)

        active_root = self.root / "active" / "runtime-r1"
        authority_active = active_root / "authority"
        bm25_active = active_root / "bm25"
        graph_active = active_root / "graph"
        governance_active = active_root / "governance"
        authority_active.mkdir(parents=True)
        bm25_active.mkdir()
        graph_active.mkdir()
        shutil.copy2(authority_candidate / "authority-manifest.json", authority_active)
        shutil.copy2(authority_candidate / "rag_chunks.db", authority_active)
        shutil.copy2(derived_candidate / "bm25.sqlite3", bm25_active)
        shutil.copy2(derived_candidate / "bm25-manifest.json", bm25_active)
        shutil.copy2(derived_candidate / "graph" / "graph-manifest.json", graph_active)
        shutil.copy2(derived_candidate / "graph" / "scoped-graph.jsonl", graph_active)
        authority_manifest = json.loads(
            (authority_active / "authority-manifest.json").read_text(encoding="utf-8")
        )
        self.timeline_path, self.superseded_path = self._write_synthetic_registries(
            authority_manifest, governance_active
        )

        bm25_manifest_path = bm25_active / "bm25-manifest.json"
        bm25_manifest = json.loads(bm25_manifest_path.read_text(encoding="utf-8"))
        bm25_manifest.setdefault("tokenizer", "trigram")
        bm25_manifest.setdefault("minimum_effective_query_codepoints", 3)
        bm25_manifest.setdefault(
            "short_query_fallback", "authority-sqlite-substring-v1"
        )
        bm25_manifest_path.write_bytes(_canonical_bytes(bm25_manifest))

        derived_manifest = json.loads(
            (derived_candidate / "derived-candidate-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        vector_release_id = derived_manifest["local_vector"]["data_release_id"]
        vector_candidate = (
            derived_candidate / "local-vector" / "candidate" / vector_release_id
        )
        vector_active = active_root / "local-vector" / "active" / vector_release_id
        vector_active.parent.mkdir(parents=True)
        shutil.copytree(vector_candidate, vector_active)
        vector_manifest_path = vector_active / "local_vector_manifest.json"
        vector_manifest = json.loads(vector_manifest_path.read_text(encoding="utf-8"))
        vector_identity = vector_manifest["identity"]
        embedding_manifest = json.loads(
            (derived_candidate / "fake-embedding-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        graph_manifest_path = graph_active / "graph-manifest.json"
        graph_manifest = json.loads(graph_manifest_path.read_text(encoding="utf-8"))

        config = {
            "schema_version": "kg-cloud-runtime-config-v1",
            "runtime_release_id": "runtime-r1",
            "active_root": str(active_root),
            "provider_runtime": {"config_sha256": "0" * 64},
            "authority": {
                "manifest_path": "authority/authority-manifest.json",
                "manifest_sha256": sha256_file(
                    authority_active / "authority-manifest.json"
                ),
                "data_path": "authority/rag_chunks.db",
                "data_sha256": sha256_file(authority_active / "rag_chunks.db"),
            },
            "bm25": {
                "manifest_path": "bm25/bm25-manifest.json",
                "manifest_sha256": sha256_file(bm25_manifest_path),
                "data_path": "bm25/bm25.sqlite3",
                "data_sha256": sha256_file(bm25_active / "bm25.sqlite3"),
            },
            "graph": {
                "manifest_path": "graph/graph-manifest.json",
                "manifest_sha256": sha256_file(graph_manifest_path),
                "release_id": graph_manifest["release_id"],
                "driver": "neo4j",
                "driver_version": "6.2.0",
                "uri_env": "KG_TEST_NEO4J_URI",
                "username_env": "KG_TEST_NEO4J_USERNAME",
                "password_env": "KG_TEST_NEO4J_PASSWORD",
                "database_env": "KG_TEST_NEO4J_DATABASE",
                "query_timeout_seconds": 2.0,
                "max_records": 100,
            },
            "regulation_governance": {
                "timeline_path": "governance/regulation_timeline.json",
                "timeline_sha256": sha256_file(self.timeline_path),
                "superseded_path": "governance/superseded_passages.json",
                "superseded_sha256": sha256_file(self.superseded_path),
            },
            "embedding": {
                "identity_sha256": embedding_manifest["identity_sha256"],
                "policy_sha256": embedding_manifest["policy_sha256"],
            },
            "local_vector": {
                "data_root": "local-vector",
                "data_release_id": vector_release_id,
                "manifest_sha256": sha256_file(vector_manifest_path),
                "authority_manifest_sha256": vector_identity[
                    "authority_manifest_sha256"
                ],
                "chunking_identity_sha256": vector_identity[
                    "chunking_identity_sha256"
                ],
                "embedding_identity_sha256": vector_identity[
                    "embedding_identity_sha256"
                ],
                "dimension": vector_identity["dimension"],
                "metric": vector_identity["metric"],
                "schema_version": vector_identity["schema_version"],
                "chunk_index_name": vector_identity["index_names"]["chunk"],
                "entity_index_name": vector_identity["index_names"]["entity"],
                "top_k_max": vector_identity["top_k_max"],
                "max_vectors_per_index": vector_identity["max_vectors_per_index"],
                "metadata_allowlist": vector_identity["metadata_allowlist"],
                "engine": vector_identity["engine"],
                "engine_version": vector_identity["engine_version"],
            },
            "server_answer": {
                "strategy": "single",
                "winner_policy": "ordered_success",
                "ordered_channels": [
                    {
                        "channel_id": self.channel.channel_id,
                        "identity_sha256": self.channel.identity_sha256,
                    }
                ],
                "total_budget_seconds": 1.0,
                "total_cost_budget_microunits": 1,
                "circuit_breaker_failure_threshold": 2,
                "circuit_breaker_cooldown_seconds": 1.0,
            },
        }
        config_path = self.root / "runtime-config.json"
        config_path.write_bytes(_canonical_bytes(config))
        for path in sorted(
            active_root.rglob("*"), key=lambda item: len(item.parts), reverse=True
        ):
            path.chmod(0o555 if path.is_dir() else 0o444)
        active_root.chmod(0o555)
        return config_path

    def _embedding_identity(self) -> QueryEmbeddingIdentity:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        vector_manifest = json.loads(
            (
                Path(config["active_root"])
                / config["local_vector"]["data_root"]
                / "active"
                / config["local_vector"]["data_release_id"]
                / "local_vector_manifest.json"
            ).read_text(encoding="utf-8")
        )
        identity = vector_manifest["identity"]
        fake_manifest = json.loads(
            (
                self.root
                / "candidate"
                / "derived"
                / "fake-embedding-manifest.json"
            ).read_text(encoding="utf-8")
        )["identity"]
        self.assertEqual(identity["embedding_identity_sha256"], config["embedding"]["identity_sha256"])
        return QueryEmbeddingIdentity(
            provider=fake_manifest["provider"],
            base_url=fake_manifest["base_url"],
            region=fake_manifest["region"],
            model=fake_manifest["model"],
            model_version=fake_manifest["model_version"],
            api_version=fake_manifest["api_version"],
            dimension=fake_manifest["dimension"],
            normalization=fake_manifest["normalization"],
            input_type=fake_manifest["input_type"],
        )

    def _bindings(self):
        embedding_transport = FakeEmbeddingTransport()
        embedding = QueryEmbeddingClient(
            self._embedding_identity(),
            policy=QueryEmbeddingPolicy(
                batch_size=64,
                max_input_units=4096,
                timeout_seconds=2.0,
                max_retries=0,
                max_requests_per_operation=10000,
                max_cost_microunits_per_request=0,
                total_cost_budget_microunits=0,
            ),
            transport=embedding_transport,
        )
        answer_transport = FakeServerAnswerTransport(answer="离线合成回答")
        answer_adapter = ServerAnswerModelAdapter(
            self.channel,
            transport=answer_transport,
        )
        coordinator = ServerAnswerCoordinator(
            (answer_adapter,),
            policy=CoordinatorPolicy(
                strategy="single",
                ordered_channel_ids=(self.channel.channel_id,),
                winner_policy="ordered_success",
                total_budget_seconds=1.0,
                total_cost_budget_microunits=1,
                circuit_breaker_failure_threshold=2,
                circuit_breaker_cooldown_seconds=1.0,
            ),
        )
        return embedding, embedding_transport, coordinator, answer_transport

    def test_open_is_read_only_and_short_queries_use_sqlite_backfill(self) -> None:
        active_root = Path(
            json.loads(self.config_path.read_text(encoding="utf-8"))["active_root"]
        )
        before = {
            str(path.relative_to(active_root)): (
                sha256_file(path),
                path.stat().st_mtime_ns,
            )
            for path in active_root.rglob("*")
            if path.is_file()
        }
        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ):
            runtime = self._open_runtime()
            self.addCleanup(runtime.close)
            short_hits = runtime.bm25_index.search("气象", limit=5)
            trigram_hits = runtime.bm25_index.search("无人机", limit=5)

        self.assertEqual(7, runtime.regulation_governance["regulation_document_count"])
        self.assertEqual(1, runtime.regulation_governance["superseded_passage_count"])
        configured_regulations = {
            item["doc_name"] for item in self.regulation_specs
        }
        self.assertEqual(configured_regulations, set(runtime.regulation_timeline))
        self.assertEqual(
            "synthetic-legacy-pilot-grades",
            runtime.superseded_passages[0]["id"],
        )
        first_regulation = self.regulation_specs[0]
        self.assertIn(
            first_regulation["number"],
            source_annotation(
                first_regulation["doc_name"],
                timeline=runtime.regulation_timeline,
            ),
        )
        partially_superseded = self.regulation_specs[-1]
        self.assertLess(
            source_priority_key(
                {"doc_name": first_regulation["doc_name"], "score": 0.1},
                timeline=runtime.regulation_timeline,
            ),
            source_priority_key(
                {"doc_name": partially_superseded["doc_name"], "score": 1.0},
                timeline=runtime.regulation_timeline,
            ),
        )
        legacy_doc = "无人机理论书籍/合成旧版教材.txt"
        kept, yielded = filter_superseded(
            "驾驶员等级",
            [
                {
                    "chunk_id": self.synthetic_rows[legacy_doc]["chunk_id"],
                    "doc_name": legacy_doc,
                }
            ],
            passages=runtime.superseded_passages,
        )
        self.assertEqual([], kept)
        self.assertEqual("synthetic-legacy-pilot-grades", yielded[0]["passage_id"])
        with self.assertRaises(TypeError):
            runtime.regulation_timeline[first_regulation["doc_name"]][
                "status"
            ] = "superseded"
        with self.assertRaises(TypeError):
            runtime.superseded_passages[0]["reason"] = "changed"
        self.assertTrue(short_hits)
        self.assertEqual("sqlite_lexical_short_query", short_hits[0]["source"])
        self.assertIn("气象条件", short_hits[0]["text"])
        self.assertTrue(trigram_hits)
        self.assertTrue(all(item["text"] for item in trigram_hits))
        for forbidden in (
            "connect",
            "init_tables",
            "init_governance_tables",
            "store_chunk",
            "store_chunks_batch",
            "delete_chunks_by_doc",
            "vacuum",
        ):
            self.assertFalse(hasattr(runtime.authority_store, forbidden))
        self.assertFalse(hasattr(runtime.bm25_index, "ensure_fresh"))
        self.assertFalse(hasattr(runtime.vector_index, "ensure_fresh"))
        after = {
            str(path.relative_to(active_root)): (
                sha256_file(path),
                path.stat().st_mtime_ns,
            )
            for path in active_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertFalse(any(active_root.rglob("*-wal")))
        self.assertFalse(any(active_root.rglob("*-shm")))

    def test_open_rejects_live_graph_drift_before_runtime_is_returned(self) -> None:
        driver = _FakeGraphDriver(
            self.graph_entities,
            nodes=self.graph_nodes[:-1],
            edges=self.graph_edges,
        )

        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ):
            with self.assertRaisesRegex(
                CloudRuntimeDependencyError, "scoped Neo4j runtime binding failed"
            ):
                CloudRuntimeResources.open(
                    self.config_path,
                    expected_config_sha256=self.config_sha256,
                    environment=self.neo4j_environment,
                    graph_driver_factory=lambda *_args, **_kwargs: driver,
                )

        self.assertTrue(driver.closed)
        self.assertEqual(1, driver.transaction_count)

    def test_close_is_idempotent_and_releases_all_read_views(self) -> None:
        runtime = self._open_runtime()
        runtime.bm25_index.search("无人机", limit=1)

        runtime.close()
        runtime.close()

        self.assertIsNone(runtime.authority_store._connection_handle)
        self.assertIsNone(runtime.bm25_index._connection_handle)
        self.assertTrue(runtime._vector_view.closed)
        self.assertTrue(runtime.authority_store.closed)
        self.assertTrue(runtime.bm25_index.closed)

        with self.assertRaisesRegex(
            ReadOnlySQLiteError, "^immutable SQLite reader is closed$"
        ):
            runtime.authority_store.all_chunks()
        with self.assertRaisesRegex(
            ReadOnlySQLiteError, "^immutable SQLite reader is closed$"
        ):
            runtime.bm25_index.search("无人机", limit=1)
        with self.assertRaises(ReadOnlyVectorError):
            runtime.vector_index.search_by_embedding([1.0] * 32, limit=1)

        closed_operations = (
            lambda: runtime.bind_provider_adapters(
                embedding_adapter=object(), answer_coordinator=object()
            ),
            lambda: runtime.embed_query("气象"),
            lambda: runtime.search_entity_evidence([1.0] * 32, limit=1),
            lambda: runtime.recall_scoped_graph(
                query="气象", entities=(), keywords=(), limit=1
            ),
            lambda: runtime.augment_scoped_graph_from_chunks({}, ()),
            lambda: runtime.exact_scoped_graph_bindings(()),
            lambda: runtime.prompt_scoped_graph_evidence({}),
            lambda: runtime.coordinate_answer(
                request_id="closed-runtime",
                question="气象是什么？",
                sources=(),
            ),
        )
        for operation in closed_operations:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(
                    CloudRuntimeDependencyError, "^cloud runtime is closed$"
                ):
                    operation()

    def test_fixed_sqlite_read_errors_are_sanitized(self) -> None:
        database_path = self.root / "malformed-authority.db"
        sqlite3.connect(database_path).close()
        reader = ReadOnlyAuthorityStore(database_path)
        self.addCleanup(reader.close)

        with self.assertRaisesRegex(
            ReadOnlySQLiteError, "^immutable SQLite fixed read failed$"
        ) as raised:
            reader.all_chunks()

        self.assertIsInstance(raised.exception.__cause__, sqlite3.Error)
        self.assertNotIn("chunks", str(raised.exception))
        self.assertNotIn(str(database_path), str(raised.exception))

    def test_hash_mismatch_fails_before_opening_artifacts(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["authority"]["data_sha256"] = "0" * 64
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()

        with self.assertRaises(CloudRuntimeIntegrityError):
            self._open_runtime()

    def test_external_runtime_config_hash_anchor_rejects_replacement(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["runtime_release_id"] = "runtime-replaced"
        self.config_path.write_bytes(_canonical_bytes(config))

        with self.assertRaisesRegex(
            CloudRuntimeConfigError, "runtime config hash mismatch"
        ):
            self._open_runtime()

    def test_runtime_config_rejects_text_and_manifest_path_aliases(self) -> None:
        base_config = json.loads(self.config_path.read_text(encoding="utf-8"))
        cases = (
            ("trimmed-text", ("runtime_release_id",), " runtime-r1 "),
            (
                "dot-prefix",
                ("authority", "manifest_path"),
                "./authority/authority-manifest.json",
            ),
            (
                "intermediate-dot",
                ("authority", "manifest_path"),
                "authority/./authority-manifest.json",
            ),
            (
                "trailing-slash",
                ("authority", "manifest_path"),
                "authority/authority-manifest.json/",
            ),
            (
                "trimmed-path",
                ("authority", "manifest_path"),
                " authority/authority-manifest.json ",
            ),
        )
        for suffix, fields, value in cases:
            with self.subTest(suffix=suffix):
                config = json.loads(json.dumps(base_config))
                target = config
                for field in fields[:-1]:
                    target = target[field]
                target[fields[-1]] = value
                self.config_path.write_bytes(_canonical_bytes(config))
                self._refresh_config_anchor()
                with self.assertRaises(CloudRuntimeConfigError):
                    CloudRuntimeConfig.load(
                        self.config_path,
                        expected_sha256=self.config_sha256,
                    )

    def test_environment_loader_requires_and_passes_external_config_hash(self) -> None:
        config_environment_name = CLOUD_RUNTIME.CONFIG_ENVIRONMENT_VARIABLE
        with mock.patch.dict(
            os.environ,
            {config_environment_name: str(self.config_path)},
            clear=True,
        ):
            with self.assertRaisesRegex(
                CloudRuntimeConfigError,
                CONFIG_SHA256_ENVIRONMENT_VARIABLE,
            ):
                CLOUD_RUNTIME.load_cloud_runtime_from_environment()

        sentinel = object()
        with mock.patch.dict(
            os.environ,
            {
                config_environment_name: str(self.config_path),
                CONFIG_SHA256_ENVIRONMENT_VARIABLE: self.config_sha256,
            },
            clear=True,
        ), mock.patch.object(
            CloudRuntimeResources,
            "open",
            return_value=sentinel,
        ) as open_runtime:
            self.assertIs(
                sentinel,
                CLOUD_RUNTIME.load_cloud_runtime_from_environment(),
            )
        open_runtime.assert_called_once_with(
            str(self.config_path),
            expected_config_sha256=self.config_sha256,
        )

    def test_authority_manifest_rejects_schema_drift_and_boolean_zeroes(self) -> None:
        base_config = json.loads(self.config_path.read_text(encoding="utf-8"))
        manifest_path = (
            Path(base_config["active_root"])
            / base_config["authority"]["manifest_path"]
        )
        base_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = (
            ("sqlite-user-version", "database", "sqlite_user_version", 2),
            (
                "foreign-key-bool",
                "database",
                "foreign_key_violation_count",
                False,
            ),
            ("network-bool", "build", "network_calls", False),
        )
        for name, section, field, value in cases:
            with self.subTest(name=name):
                manifest = json.loads(json.dumps(base_manifest))
                manifest[section][field] = value
                manifest_path.chmod(0o644)
                manifest_path.write_bytes(_canonical_bytes(manifest))
                manifest_path.chmod(0o444)
                config = json.loads(json.dumps(base_config))
                manifest_sha256 = sha256_file(manifest_path)
                config["authority"]["manifest_sha256"] = manifest_sha256
                config["local_vector"][
                    "authority_manifest_sha256"
                ] = manifest_sha256
                self.config_path.write_bytes(_canonical_bytes(config))
                self._refresh_config_anchor()
                with self.assertRaisesRegex(
                    CloudRuntimeIntegrityError,
                    "authority manifest binding mismatch",
                ):
                    self._open_runtime()

    def test_authority_manifest_stable_read_rejects_named_path_replacement(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        manifest_path = (
            Path(config["active_root"])
            / config["authority"]["manifest_path"]
        )
        manifest_parent = manifest_path.parent
        original = self.root / "authority-manifest-original.json"
        replacement = self.root / "authority-manifest-replacement.json"
        replacement.write_bytes(manifest_path.read_bytes() + b" ")
        replacement.chmod(0o444)
        real_open = os.open
        replaced = False

        def open_then_replace(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is None:
                descriptor = real_open(path, flags, mode)
            else:
                descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            if not replaced and Path(os.fspath(path)) == manifest_path:
                manifest_parent.chmod(0o755)
                os.replace(manifest_path, original)
                os.replace(replacement, manifest_path)
                manifest_parent.chmod(0o555)
                replaced = True
            return descriptor

        try:
            with mock.patch.object(CLOUD_RUNTIME.os, "open", side_effect=open_then_replace):
                with self.assertRaises(CloudRuntimeIntegrityError):
                    self._open_runtime()
            self.assertTrue(replaced)
        finally:
            manifest_parent.chmod(0o755)
            if original.exists():
                if manifest_path.exists():
                    os.replace(manifest_path, replacement)
                os.replace(original, manifest_path)
            manifest_parent.chmod(0o555)

    def test_authority_actual_chunk_ownership_must_match_source_counts(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        active_root = Path(config["active_root"])
        manifest = json.loads(
            (active_root / config["authority"]["manifest_path"]).read_text(
                encoding="utf-8"
            )
        )
        with ReadOnlyAuthorityStore(
            active_root / config["authority"]["data_path"]
        ) as reader:
            altered_rows = reader.all_chunks()
            altered_rows[0]["doc_name"] = altered_rows[1]["doc_name"]
            altered_map = {
                str(row["chunk_id"]): str(row["doc_name"])
                for row in altered_rows
            }
            altered_reader = mock.Mock(wraps=reader)
            altered_reader.all_chunks.return_value = altered_rows
            altered_reader.chunk_document_map.return_value = altered_map
            with self.assertRaisesRegex(
                CloudRuntimeIntegrityError,
                "authority document identity mismatch",
            ):
                CLOUD_RUNTIME._validate_authority_database(
                    altered_reader,
                    manifest,
                )

    def test_authority_source_page_count_must_remain_an_integer(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        active_root = Path(config["active_root"])
        manifest = json.loads(
            (active_root / config["authority"]["manifest_path"]).read_text(
                encoding="utf-8"
            )
        )
        with ReadOnlyAuthorityStore(
            active_root / config["authority"]["data_path"]
        ) as reader:
            source_rows = reader.source_records()
            source_rows[0]["source_page_count"] = str(
                source_rows[0]["source_page_count"]
            )
            altered_reader = mock.Mock(wraps=reader)
            altered_reader.source_records.return_value = source_rows
            with self.assertRaisesRegex(
                CloudRuntimeIntegrityError,
                "authority document identity mismatch",
            ):
                CLOUD_RUNTIME._validate_authority_database(
                    altered_reader,
                    manifest,
                )

    def test_exact_authority_and_bm25_sqlite_schemas_are_required(self) -> None:
        cases = (
            (
                "authority",
                CLOUD_RUNTIME.ReadOnlyAuthorityStore,
                "authority SQLite schema mismatch",
            ),
            (
                "bm25",
                CLOUD_RUNTIME.ReadOnlyFtsIndex,
                "BM25 SQLite schema mismatch",
            ),
        )
        for label, reader_type, expected_error in cases:
            with self.subTest(label=label):
                with mock.patch.object(
                    reader_type,
                    "schema_records",
                    return_value=(),
                ):
                    with self.assertRaisesRegex(
                        CloudRuntimeIntegrityError,
                        expected_error,
                    ):
                        self._open_runtime()

    def test_sqlite_readers_reject_same_inode_rewrites_after_open(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        cases = (
            ("authority", "authority", "authority_store", "authority"),
            ("bm25", "bm25", "bm25_index", "BM25"),
        )
        for label, config_key, reader_attribute, error_label in cases:
            with self.subTest(label=label):
                runtime = self._open_runtime()
                database_path = (
                    Path(config["active_root"]) / config[config_key]["data_path"]
                )
                descriptor = -1
                try:
                    opened_inode = database_path.stat().st_ino
                    database_path.chmod(0o644)
                    descriptor = os.open(database_path, os.O_RDWR)
                    first_byte = os.pread(descriptor, 1, 0)
                    os.pwrite(descriptor, first_byte, 0)
                    os.fsync(descriptor)
                    os.close(descriptor)
                    descriptor = -1
                    database_path.chmod(0o444)
                    self.assertEqual(opened_inode, database_path.stat().st_ino)

                    reader = getattr(runtime, reader_attribute)
                    with self.assertRaisesRegex(
                        ReadOnlySQLiteError,
                        f"{error_label} database path binding changed after open",
                    ):
                        if label == "authority":
                            reader.all_chunks()
                        else:
                            reader.search("无人机", limit=1)
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                    database_path.chmod(0o444)
                    runtime.close()

    def test_bm25_manifest_requires_exact_fields_and_strict_integers(self) -> None:
        base_config = json.loads(self.config_path.read_text(encoding="utf-8"))
        manifest_path = (
            Path(base_config["active_root"]) / base_config["bm25"]["manifest_path"]
        )
        base_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = (
            ("root-extra", (), "unexpected", "value"),
            ("index-extra", ("index",), "unexpected", "value"),
            ("source-extra", ("source",), "unexpected", "value"),
            ("indexed-count-bool", (), "indexed_chunk_count", True),
            (
                "minimum-codepoints-bool",
                (),
                "minimum_effective_query_codepoints",
                True,
            ),
            ("source-chunk-count-bool", ("source",), "chunk_count", True),
            ("source-document-count-bool", ("source",), "document_count", True),
            ("source-byte-count-bool", ("source",), "text_byte_count", True),
            (
                "source-codepoint-count-bool",
                ("source",),
                "text_codepoint_count",
                True,
            ),
        )
        for name, location, field, value in cases:
            with self.subTest(name=name):
                manifest = json.loads(json.dumps(base_manifest))
                target = manifest
                for component in location:
                    target = target[component]
                target[field] = value
                manifest_path.chmod(0o644)
                manifest_path.write_bytes(_canonical_bytes(manifest))
                manifest_path.chmod(0o444)
                config = json.loads(json.dumps(base_config))
                config["bm25"]["manifest_sha256"] = sha256_file(manifest_path)
                self.config_path.write_bytes(_canonical_bytes(config))
                self._refresh_config_anchor()

                with self.assertRaisesRegex(
                    CloudRuntimeIntegrityError,
                    "BM25 manifest binding mismatch",
                ):
                    self._open_runtime()

    def test_authority_reader_descriptor_must_match_approved_hash(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        database_path = Path(config["active_root"]) / config["authority"]["data_path"]
        original = self.root / "authority-original.db"
        replacement = self.root / "authority-replacement.db"
        replacement.write_bytes(database_path.read_bytes() + b"descriptor-drift")
        replacement.chmod(0o444)
        database_parent = database_path.parent
        real_reader = CLOUD_RUNTIME.ReadOnlyAuthorityStore

        class ReplaceBeforeOpenReader:
            def __new__(cls, path):
                database_parent.chmod(0o755)
                os.replace(database_path, original)
                os.replace(replacement, database_path)
                database_parent.chmod(0o555)
                return real_reader(path)

        try:
            with mock.patch.object(
                CLOUD_RUNTIME, "ReadOnlyAuthorityStore", ReplaceBeforeOpenReader
            ):
                with self.assertRaisesRegex(
                    CloudRuntimeIntegrityError, "authority database descriptor hash mismatch"
                ):
                    self._open_runtime()
        finally:
            database_parent.chmod(0o755)
            if original.exists():
                if database_path.exists():
                    os.replace(database_path, replacement)
                os.replace(original, database_path)
            database_parent.chmod(0o555)

    def test_bm25_reader_descriptor_must_match_approved_hash(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        database_path = Path(config["active_root"]) / config["bm25"]["data_path"]
        original = self.root / "bm25-original.db"
        replacement = self.root / "bm25-replacement.db"
        replacement.write_bytes(database_path.read_bytes() + b"descriptor-drift")
        replacement.chmod(0o444)
        database_parent = database_path.parent
        real_reader = CLOUD_RUNTIME.ReadOnlyFtsIndex

        class ReplaceBeforeOpenReader:
            def __new__(cls, path, authority):
                database_parent.chmod(0o755)
                os.replace(database_path, original)
                os.replace(replacement, database_path)
                database_parent.chmod(0o555)
                return real_reader(path, authority)

        try:
            with mock.patch.object(
                CLOUD_RUNTIME, "ReadOnlyFtsIndex", ReplaceBeforeOpenReader
            ):
                with self.assertRaisesRegex(
                    CloudRuntimeIntegrityError, "BM25 database descriptor hash mismatch"
                ):
                    self._open_runtime()
        finally:
            database_parent.chmod(0o755)
            if original.exists():
                if database_path.exists():
                    os.replace(database_path, replacement)
                os.replace(original, database_path)
            database_parent.chmod(0o555)

    def test_bm25_manifest_stable_read_rejects_named_path_replacement(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        manifest_path = Path(config["active_root"]) / config["bm25"]["manifest_path"]
        manifest_parent = manifest_path.parent
        original = self.root / "bm25-manifest-original.json"
        replacement = self.root / "bm25-manifest-replacement.json"
        replacement.write_bytes(manifest_path.read_bytes() + b" ")
        replacement.chmod(0o444)
        real_open = os.open
        replaced = False

        def open_then_replace(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is None:
                descriptor = real_open(path, flags, mode)
            else:
                descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            if not replaced and Path(os.fspath(path)) == manifest_path:
                manifest_parent.chmod(0o755)
                os.replace(manifest_path, original)
                os.replace(replacement, manifest_path)
                manifest_parent.chmod(0o555)
                replaced = True
            return descriptor

        try:
            with mock.patch.object(CLOUD_RUNTIME.os, "open", side_effect=open_then_replace):
                with self.assertRaises(CloudRuntimeIntegrityError):
                    self._open_runtime()
            self.assertTrue(replaced)
        finally:
            manifest_parent.chmod(0o755)
            if original.exists():
                if manifest_path.exists():
                    os.replace(manifest_path, replacement)
                os.replace(original, manifest_path)
            manifest_parent.chmod(0o555)

    def test_vector_manifest_rejects_named_path_replacement_during_read(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        local = config["local_vector"]
        manifest_path = (
            Path(config["active_root"])
            / local["data_root"]
            / "active"
            / local["data_release_id"]
            / "local_vector_manifest.json"
        )
        manifest_parent = manifest_path.parent
        original = self.root / "vector-manifest-original.json"
        replacement = self.root / "vector-manifest-replacement.json"
        replacement.write_bytes(manifest_path.read_bytes() + b" ")
        replacement.chmod(0o444)
        real_open = os.open
        replaced = False

        def open_then_replace(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is None:
                descriptor = real_open(path, flags, mode)
            else:
                descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            if not replaced and Path(os.fspath(path)) == manifest_path:
                manifest_parent.chmod(0o755)
                os.replace(manifest_path, original)
                os.replace(replacement, manifest_path)
                manifest_parent.chmod(0o555)
                replaced = True
            return descriptor

        try:
            with mock.patch.object(
                RUNTIME_VECTOR.os,
                "open",
                side_effect=open_then_replace,
            ):
                with self.assertRaises(CloudRuntimeIntegrityError):
                    self._open_runtime()
            self.assertTrue(replaced)
        finally:
            manifest_parent.chmod(0o755)
            if original.exists():
                if manifest_path.exists():
                    os.replace(manifest_path, replacement)
                os.replace(original, manifest_path)
            manifest_parent.chmod(0o555)

    def test_vector_index_rejects_named_path_replacement_during_open(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        local = config["local_vector"]
        index_path = (
            Path(config["active_root"])
            / local["data_root"]
            / "active"
            / local["data_release_id"]
            / local["chunk_index_name"]
            / "index.usearch"
        )
        index_parent = index_path.parent
        original = self.root / "vector-index-original.usearch"
        replacement = self.root / "vector-index-replacement.usearch"
        replacement.write_bytes(index_path.read_bytes() + b"descriptor-drift")
        replacement.chmod(0o444)
        real_open = os.open
        replaced = False

        def open_then_replace(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is None:
                descriptor = real_open(path, flags, mode)
            else:
                descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            if not replaced and Path(os.fspath(path)) == index_path:
                index_parent.chmod(0o755)
                os.replace(index_path, original)
                os.replace(replacement, index_path)
                index_parent.chmod(0o555)
                replaced = True
            return descriptor

        try:
            with mock.patch.object(
                RUNTIME_VECTOR.os,
                "open",
                side_effect=open_then_replace,
            ):
                with self.assertRaises(CloudRuntimeIntegrityError):
                    self._open_runtime()
            self.assertTrue(replaced)
        finally:
            index_parent.chmod(0o755)
            if original.exists():
                if index_path.exists():
                    os.replace(index_path, replacement)
                os.replace(original, index_path)
            index_parent.chmod(0o555)

    def test_vector_view_rejects_named_path_replacement_after_open(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        local = config["local_vector"]
        index_path = (
            Path(config["active_root"])
            / local["data_root"]
            / "active"
            / local["data_release_id"]
            / local["chunk_index_name"]
            / "index.usearch"
        )
        index_parent = index_path.parent
        original = self.root / "live-vector-index-original.usearch"
        replacement = self.root / "live-vector-index-replacement.usearch"
        replacement.write_bytes(index_path.read_bytes())
        replacement.chmod(0o444)
        runtime = self._open_runtime()
        try:
            index_parent.chmod(0o755)
            os.replace(index_path, original)
            os.replace(replacement, index_path)
            index_parent.chmod(0o555)
            query = tuple(
                1.0 if index == 0 else 0.0
                for index in range(int(local["dimension"]))
            )
            with self.assertRaisesRegex(
                ReadOnlyVectorError,
                "vector index path binding changed",
            ):
                runtime._vector_view.query_chunk(query, top_k=1)
        finally:
            runtime.close()
            index_parent.chmod(0o755)
            if original.exists():
                if index_path.exists():
                    os.replace(index_path, replacement)
                os.replace(original, index_path)
            index_parent.chmod(0o555)

    def test_vector_query_rejects_float32_overflow_and_underflow(self) -> None:
        runtime = self._open_runtime()
        self.addCleanup(runtime.close)
        dimension = runtime._vector_view.contract.dimension
        cases = (
            ("overflow", 1e100, "remain finite"),
            ("underflow", 1e-100, "remain non-zero"),
        )
        for name, first_value, expected_error in cases:
            with self.subTest(name=name):
                query = [0.0] * dimension
                query[0] = first_value
                with self.assertRaisesRegex(ReadOnlyVectorError, expected_error):
                    runtime._vector_view.query_chunk(query, top_k=1)

    def test_scoped_graph_term_lookup_rejects_post_audit_omission(self) -> None:
        runtime = self._open_runtime()
        self.addCleanup(runtime.close)
        driver = self.graph_drivers[-1]
        canonical_name = str(self.graph_entities[0]["canonical_name"])
        original_respond = driver.respond

        def omit_term_results(text, parameters):
            if text == READ_CYPHER["entities_by_terms"]:
                return []
            return original_respond(text, parameters)

        driver.respond = omit_term_results
        with self.assertRaisesRegex(
            CloudRuntimeIntegrityError,
            "term lookup does not match the sealed graph",
        ):
            runtime.recall_scoped_graph(
                query=canonical_name,
                entities=(),
                keywords=(),
                limit=20,
            )

    def test_scoped_graph_chunk_lookup_rejects_post_audit_omission(self) -> None:
        runtime = self._open_runtime()
        self.addCleanup(runtime.close)
        driver = self.graph_drivers[-1]
        chunk_id = str(self.graph_entities[0]["evidence_chunk_ids"][0])
        original_respond = driver.respond

        def omit_chunk_results(text, parameters):
            if text == READ_CYPHER["entities_by_chunk_ids"]:
                return []
            return original_respond(text, parameters)

        driver.respond = omit_chunk_results
        with self.assertRaisesRegex(
            CloudRuntimeIntegrityError,
            "chunk lookup does not match the sealed graph",
        ):
            runtime.augment_scoped_graph_from_chunks({}, (chunk_id,))

    def test_regulation_registry_hash_mismatch_fails_closed(self) -> None:
        self.timeline_path.chmod(0o644)
        self.timeline_path.write_bytes(self.timeline_path.read_bytes() + b" ")
        self.timeline_path.chmod(0o444)

        with self.assertRaisesRegex(
            CloudRuntimeIntegrityError, "regulation timeline hash mismatch"
        ):
            self._open_runtime()

    def test_regulation_registries_reject_named_path_replacement_during_read(self) -> None:
        for label, registry_path in (
            ("timeline", self.timeline_path),
            ("superseded", self.superseded_path),
        ):
            with self.subTest(label=label):
                registry_parent = registry_path.parent
                original = self.root / f"{label}-original.json"
                replacement = self.root / f"{label}-replacement.json"
                replacement.write_bytes(registry_path.read_bytes() + b" ")
                replacement.chmod(0o444)
                real_open = os.open
                replaced = False

                def open_then_replace(path, flags, mode=0o777, *, dir_fd=None):
                    nonlocal replaced
                    if dir_fd is None:
                        descriptor = real_open(path, flags, mode)
                    else:
                        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
                    if not replaced and Path(os.fspath(path)) == registry_path:
                        registry_parent.chmod(0o755)
                        os.replace(registry_path, original)
                        os.replace(replacement, registry_path)
                        registry_parent.chmod(0o555)
                        replaced = True
                    return descriptor

                try:
                    with mock.patch.object(
                        CLOUD_RUNTIME.os, "open", side_effect=open_then_replace
                    ):
                        with self.assertRaises(CloudRuntimeIntegrityError):
                            self._open_runtime()
                    self.assertTrue(replaced)
                finally:
                    registry_parent.chmod(0o755)
                    if original.exists():
                        if registry_path.exists():
                            os.replace(registry_path, replacement)
                        os.replace(original, registry_path)
                    registry_parent.chmod(0o555)

    def test_regulation_marker_binding_mismatch_fails_closed(self) -> None:
        timeline = json.loads(self.timeline_path.read_text(encoding="utf-8"))
        timeline["documents"][0]["evidence"][0]["required_markers"].append(
            "missing synthetic marker"
        )
        self.timeline_path.chmod(0o644)
        self.timeline_path.write_bytes(_canonical_bytes(timeline))
        self.timeline_path.chmod(0o444)
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["regulation_governance"]["timeline_sha256"] = sha256_file(
            self.timeline_path
        )
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()

        with self.assertRaisesRegex(
            CloudRuntimeIntegrityError, "regulation governance binding mismatch"
        ):
            self._open_runtime()

    def test_regulation_authority_binding_mismatch_fails_closed(self) -> None:
        timeline = json.loads(self.timeline_path.read_text(encoding="utf-8"))
        timeline["authority"]["database_sha256"] = "0" * 64
        self.timeline_path.chmod(0o644)
        self.timeline_path.write_bytes(_canonical_bytes(timeline))
        self.timeline_path.chmod(0o444)
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["regulation_governance"]["timeline_sha256"] = sha256_file(
            self.timeline_path
        )
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()

        with self.assertRaisesRegex(
            CloudRuntimeIntegrityError, "regulation governance binding mismatch"
        ):
            self._open_runtime()

    def test_superseding_text_hash_mismatch_fails_closed(self) -> None:
        superseded = json.loads(self.superseded_path.read_text(encoding="utf-8"))
        superseded["passages"][0]["superseded_by"][0]["text_sha256"] = "0" * 64
        self.superseded_path.chmod(0o644)
        self.superseded_path.write_bytes(_canonical_bytes(superseded))
        self.superseded_path.chmod(0o444)
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["regulation_governance"]["superseded_sha256"] = sha256_file(
            self.superseded_path
        )
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()

        with self.assertRaisesRegex(
            CloudRuntimeIntegrityError, "regulation governance binding mismatch"
        ):
            self._open_runtime()

    def test_regulation_registry_path_must_be_relative(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["regulation_governance"]["timeline_path"] = str(self.timeline_path)
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()

        with self.assertRaisesRegex(
            CloudRuntimeConfigError,
            "regulation_governance.timeline_path must be a relative POSIX path",
        ):
            self._open_runtime()

    def test_bm25_orphan_id_fails_complete_sqlite_backfill_gate(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        active_root = Path(config["active_root"])
        database_path = active_root / config["bm25"]["data_path"]
        manifest_path = active_root / config["bm25"]["manifest_path"]
        database_path.parent.chmod(0o755)
        database_path.chmod(0o644)
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                "INSERT INTO chunks_fts (text, chunk_id, doc_name) VALUES (?, ?, ?)",
                ("气象孤儿记录", "chunk:orphan", "outside.txt"),
            )
            connection.commit()
        finally:
            connection.close()
        manifest_path.chmod(0o644)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["index"]["sha256"] = sha256_file(database_path)
        manifest["indexed_chunk_count"] += 1
        manifest_path.write_bytes(_canonical_bytes(manifest))
        config["bm25"]["data_sha256"] = sha256_file(database_path)
        config["bm25"]["manifest_sha256"] = sha256_file(manifest_path)
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()
        database_path.chmod(0o444)
        manifest_path.chmod(0o444)
        database_path.parent.chmod(0o555)

        original_close = ReadOnlyAuthorityStore.close
        with mock.patch.object(
            ReadOnlyAuthorityStore,
            "close",
            autospec=True,
            side_effect=original_close,
        ) as close_authority:
            with self.assertRaises(CloudRuntimeIntegrityError):
                self._open_runtime()

        close_authority.assert_called_once()

    def test_server_answer_requires_at_least_one_configured_channel(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["server_answer"]["ordered_channels"] = []
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()

        with self.assertRaises(CloudRuntimeConfigError):
            self._open_runtime()

    def test_provider_runtime_config_hash_is_required_and_frozen(self) -> None:
        runtime = self._open_runtime()
        self.addCleanup(runtime.close)
        self.assertEqual(
            "0" * 64, runtime.config.provider_runtime_config_sha256
        )

        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["provider_runtime"]["config_sha256"] = "not-a-sha"
        self.config_path.write_bytes(_canonical_bytes(config))
        self._refresh_config_anchor()
        with self.assertRaises(CloudRuntimeConfigError):
            self._open_runtime()

    def test_fake_adapters_bind_exact_identities_and_keep_ledger_sanitized(self) -> None:
        runtime = self._open_runtime()
        self.addCleanup(runtime.close)
        embedding, embedding_transport, coordinator, answer_transport = self._bindings()
        runtime.bind_provider_adapters(
            embedding_adapter=embedding,
            answer_coordinator=coordinator,
        )

        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ):
            query_vector = runtime.embed_query("气象")
            chunk_hits = runtime.vector_index.search_by_embedding(query_vector, limit=2)
            entity_hits = runtime.search_entity_evidence(query_vector, limit=2)
            selected_sources = runtime.bm25_index.search("气象", limit=2)
            selected_sources[0]["text"] = "UNTRUSTED RETRIEVAL TEXT"
            outcome = runtime.coordinate_answer(
                request_id="request-1",
                question="气象是什么？",
                sources=selected_sources,
            )

        self.assertEqual(1, embedding_transport.call_count)
        self.assertEqual(1, answer_transport.call_count)
        disclosed_payload = answer_transport.request_payloads[0]
        self.assertIn("<claim-map>", disclosed_payload["question"])
        self.assertIn("每个有意义的正文句都必须被一个 claim.text 逐字覆盖", disclosed_payload["question"])
        disclosed_texts = [item["text"] for item in disclosed_payload["evidence"]]
        self.assertNotIn("UNTRUSTED RETRIEVAL TEXT", disclosed_texts)
        self.assertIn("气象条件会影响无人机飞行安全。", disclosed_texts)
        self.assertTrue(all(item["text"] for item in chunk_hits))
        self.assertTrue(entity_hits)
        self.assertTrue(all(item["source_chunk_ids"] for item in entity_hits))
        telemetry = runtime.answer_telemetry(
            outcome=outcome,
            selected_channel_id=outcome.winner_channel_id,
            latency_ms=outcome.latency_ms,
            recovery_status="not_required",
            extractive_fallback_used=True,
            extractive_fallback_recovered=False,
            extractive_policy_version="extractive-v3",
            answer_method="coordinator_model",
            answer_status="answered",
        )
        self.assertEqual("fake-primary", telemetry["selected_channel_id"])
        self.assertEqual(1, len(telemetry["coordinator"]["ledger"]))
        serialized = json.dumps(telemetry, ensure_ascii=False).lower()
        self.assertNotIn('"error', serialized)
        self.assertNotIn('"provider":', serialized)
        with self.assertRaises(CloudRuntimeDependencyError):
            runtime.bind_provider_adapters(
                embedding_adapter=embedding,
                answer_coordinator=coordinator,
            )

    def test_external_process_query_uses_approved_byte_meter(self) -> None:
        runtime = self._open_runtime()
        self.addCleanup(runtime.close)
        cooperative, _, coordinator, _ = self._bindings()
        embedding = QueryEmbeddingClient(
            cooperative.identity,
            policy=cooperative.policy,
            transport=ByteMeterExternalEmbeddingTransport(),
            transport_mode="external_process",
            input_unit_meter=_utf8_byte_input_unit_meter,
        )
        runtime.bind_provider_adapters(
            embedding_adapter=embedding,
            answer_coordinator=coordinator,
        )

        self.assertEqual(6, embedding.measure_input_units("气象"))
        vector = runtime.embed_query("气象")

        self.assertEqual(embedding.identity.dimension, len(vector))
        self.assertEqual(1.0, vector[0])
        self.assertTrue(all(value == 0.0 for value in vector[1:]))

    def test_embedding_policy_hash_mismatch_fails_before_binding(self) -> None:
        runtime = self._open_runtime()
        self.addCleanup(runtime.close)
        embedding, _, coordinator, _ = self._bindings()
        mismatched = QueryEmbeddingClient(
            embedding.identity,
            policy=QueryEmbeddingPolicy(
                batch_size=1,
                max_input_units=4096,
                timeout_seconds=2.0,
                max_retries=0,
                max_requests_per_operation=10000,
                max_cost_microunits_per_request=0,
                total_cost_budget_microunits=0,
            ),
            transport=FakeEmbeddingTransport(),
        )

        with self.assertRaisesRegex(
            CloudRuntimeDependencyError, "embedding adapter policy mismatch"
        ):
            runtime.bind_provider_adapters(
                embedding_adapter=mismatched,
                answer_coordinator=coordinator,
            )

    def test_process_level_socket_block_allows_only_fake_runtime_paths(self) -> None:
        blocker = self.root / "socket-blocker"
        blocker.mkdir()
        (blocker / "sitecustomize.py").write_text(
            """import socket
def blocked(*args, **kwargs):
    raise AssertionError('network forbidden by process policy')
socket.create_connection = blocked
socket.getaddrinfo = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
""",
            encoding="utf-8",
        )
        script = self.root / "runtime_probe.py"
        script.write_text(
            """import hashlib
import json
import sys
from pathlib import Path
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / 'deploy'))
from pipeline.cloud_runtime import CloudRuntimeResources
from deploy.cloud_v2.fake_providers import FakeEmbeddingTransport, FakeServerAnswerTransport, fake_embedding_identity
from rag_store.runtime_neo4j_reader import READ_CYPHER
from rag_store.runtime_query_embedding import QueryEmbeddingClient, QueryEmbeddingIdentity, QueryEmbeddingPolicy
from rag_store.server_answer_model import ServerAnswerChannel, ServerAnswerModelAdapter
from rag_store.server_answer_coordinator import CoordinatorPolicy, ServerAnswerCoordinator

class Result:
    def __init__(self, records):
        self.records = records
    def __iter__(self):
        return iter(self.records)

class Session:
    def __init__(self, driver, config):
        self.driver = driver
        self.config = config
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return None
    def begin_transaction(self):
        self.driver.transaction_count += 1
        return self
    def run(self, query, parameters=None, **kwargs):
        text = getattr(query, 'text', str(query))
        values = dict(parameters or {})
        values.update(kwargs)
        self.driver.calls.append((text, values, self.config))
        rows = self.driver.nodes if text == READ_CYPHER['audit_nodes'] else self.driver.edges
        selected = [
            item for item in sorted(rows, key=lambda value: value['cursor'])
            if item['cursor'] > values['after_cursor']
        ]
        return Result(selected[:int(values['limit'])])

class Driver:
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges
        self.calls = []
        self.transaction_count = 0
    def session(self, **config):
        return Session(self, config)
    def close(self):
        return None

runtime_config = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
graph_manifest_path = Path(runtime_config['active_root']) / runtime_config['graph']['manifest_path']
graph_manifest = json.loads(graph_manifest_path.read_text(encoding='utf-8'))
graph_records = [
    json.loads(line)
    for line in (graph_manifest_path.parent / graph_manifest['graph']['path']).read_text(encoding='utf-8').splitlines()
]
nodes = []
edges = []
for index, record in enumerate(graph_records):
    if record['kind'] == 'node':
        properties = {
            'graph_release_id': graph_manifest['release_id'],
            'authority_release_id': graph_manifest['authority_release_id'],
            'node_id': record['node_id'],
            **record['properties'],
        }
        if record['label'] == 'Entity':
            properties['entity_id'] = record['node_id']
        nodes.append({'cursor': f'node:{index:08d}', 'labels': [record['label']], 'properties': properties})
    else:
        edge_payload = json.dumps(
            [record['type'], record['from'], record['to'], record['evidence_chunk_ids']],
            ensure_ascii=False,
            separators=(',', ':'),
        )
        edges.append({
            'cursor': f'edge:{index:08d}',
            'relationship_type': record['type'],
            'from_node_id': record['from'],
            'to_node_id': record['to'],
            'properties': {
                'graph_release_id': graph_manifest['release_id'],
                'authority_release_id': graph_manifest['authority_release_id'],
                'edge_id': 'edge:' + hashlib.sha256(edge_payload.encode('utf-8')).hexdigest(),
                'evidence_chunk_ids': record['evidence_chunk_ids'],
            },
        })
graph_driver = Driver(nodes, edges)
def graph_driver_factory(_uri, *, auth, **_config):
    assert auth == ('kg-reader', 'fake-neo4j-credential')
    return graph_driver

runtime = CloudRuntimeResources.open(
    sys.argv[2],
    expected_config_sha256=sys.argv[3],
    graph_driver_factory=graph_driver_factory,
)
assert graph_driver.transaction_count == 1
assert {READ_CYPHER['audit_nodes'], READ_CYPHER['audit_edges']} == {item[0] for item in graph_driver.calls}
assert all(item[2]['default_access_mode'] == 'READ' for item in graph_driver.calls)
fake_identity = fake_embedding_identity()
identity = QueryEmbeddingIdentity(**fake_identity.manifest())
embedding = QueryEmbeddingClient(
    identity,
    policy=QueryEmbeddingPolicy(
        batch_size=64,
        max_input_units=4096,
        timeout_seconds=2.0,
        max_retries=0,
        max_requests_per_operation=10000,
        max_cost_microunits_per_request=0,
        total_cost_budget_microunits=0,
    ),
    transport=FakeEmbeddingTransport(),
)
channel = ServerAnswerChannel(
    channel_id='fake-primary',
    provider='fake-offline',
    base_url='https://fake.invalid/v1/answers',
    region='offline',
    model='fake-answer-v1',
    model_version='fake-answer-model-v1',
    api_version='v1',
    timeout_seconds=1.0,
    max_input_units=10000,
    max_output_units=1000,
    max_cost_microunits=0,
)
coordinator = ServerAnswerCoordinator(
    (ServerAnswerModelAdapter(channel, transport=FakeServerAnswerTransport()),),
    policy=CoordinatorPolicy(
        strategy='single',
        ordered_channel_ids=('fake-primary',),
        winner_policy='ordered_success',
        total_budget_seconds=1.0,
        total_cost_budget_microunits=1,
        circuit_breaker_failure_threshold=2,
        circuit_breaker_cooldown_seconds=1.0,
    ),
)
runtime.bind_provider_adapters(
    embedding_adapter=embedding,
    answer_coordinator=coordinator,
)
hits = runtime.bm25_index.search('气象', limit=2)
vector = runtime.embed_query('气象')
assert runtime.vector_index.search_by_embedding(vector, limit=1)
assert runtime.coordinate_answer(
    request_id='process-probe',
    question='气象是什么？',
    sources=hits,
).answer
runtime.close()
print('zero-network-runtime-ok')
""",
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment.update(self.neo4j_environment)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        python_path = [str(blocker), str(REPO_ROOT), str(REPO_ROOT / "deploy")]
        if environment.get("PYTHONPATH"):
            python_path.append(environment["PYTHONPATH"])
        environment["PYTHONPATH"] = os.pathsep.join(python_path)
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                str(REPO_ROOT),
                str(self.config_path),
                self.config_sha256,
            ],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("zero-network-runtime-ok", completed.stdout.strip())


if __name__ == "__main__":
    unittest.main()
