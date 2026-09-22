#!/usr/bin/env python3
"""Build a deterministic scoped graph package bound to SQLite chunk evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .authority_builder import _write_json_impl as write_json
from .source_scope import sha256_file
from deploy.rag_store.scoped_graph_contract import (
    GRAPH_IMPORT_SCHEMA_VERSION,
    NEO4J_DRIVER_NAME,
    NEO4J_DRIVER_VERSION,
    NODE_LABELS,
    RELATIONSHIP_TYPES,
)


GRAPH_SCHEMA_VERSION = "cloud-scoped-graph-v1"
ENTITY_LEXICON: tuple[tuple[str, str], ...] = (
    ("无人驾驶航空器", "aircraft"),
    ("无人机", "aircraft"),
    ("民用航空器", "aircraft"),
    ("操控员", "role"),
    ("驾驶员", "role"),
    ("教员", "role"),
    ("训练机构", "organization_type"),
    ("中国民用航空局", "authority"),
    ("CCAR-92", "regulation"),
    ("民用航空法", "regulation"),
    ("飞行管理暂行条例", "regulation"),
    ("实名制登记", "regulatory_topic"),
    ("适航", "regulatory_topic"),
    ("空域", "operations_topic"),
    ("气象", "operations_topic"),
    ("航行灯", "operations_topic"),
    ("飞行原理", "theory_topic"),
    ("任务规划", "theory_topic"),
    ("地面站", "system_topic"),
    ("罗盘", "system_topic"),
    ("经纬度", "navigation_topic"),
    ("航向", "navigation_topic"),
)


class GraphBuildError(RuntimeError):
    """The scoped graph failed an authority or evidence binding gate."""


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _id(prefix: str, *parts: str) -> str:
    return prefix + ":" + hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:40]


def _load_authority(authority_root: Path) -> tuple[dict[str, Any], Path]:
    manifest_path = authority_root / "authority-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GraphBuildError("authority manifest is unavailable") from exc
    if not isinstance(manifest, dict) or manifest.get("status") != "candidate":
        raise GraphBuildError("authority input is not an exact candidate")
    database = manifest.get("database") or {}
    database_name = database.get("path")
    if not isinstance(database_name, str) or Path(database_name).name != database_name:
        raise GraphBuildError("authority database path is not an exact filename")
    database_path = authority_root / database_name
    if not database_path.is_file() or database_path.is_symlink():
        raise GraphBuildError("authority database is missing or unsafe")
    if sha256_file(database_path) != database.get("sha256"):
        raise GraphBuildError("authority database hash mismatch")
    return manifest, database_path


def _rows(database_path: Path) -> Iterable[sqlite3.Row]:
    connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise GraphBuildError("authority SQLite integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise GraphBuildError("authority SQLite foreign-key check failed")
        yield from connection.execute(
            "SELECT chunk_id, text, doc_name, chunk_index FROM chunks ORDER BY doc_name, chunk_index"
        )
    finally:
        connection.close()


def build_graph(authority_root: str | Path, candidate_root: str | Path) -> dict[str, Any]:
    authority_root = Path(authority_root).resolve(strict=True)
    output_root = Path(candidate_root).resolve()
    if not any(part in {"candidate", "candidates"} for part in output_root.parts):
        raise GraphBuildError("graph output must be inside an explicit candidate root")
    if output_root.exists():
        raise GraphBuildError("graph candidate output already exists")
    output_root.mkdir(parents=True, mode=0o700)
    manifest, database_path = _load_authority(authority_root)
    authority_release_id = str(manifest["release_id"])

    chunks = list(_rows(database_path))
    chunk_ids = {str(row["chunk_id"]) for row in chunks}
    documents = sorted({str(row["doc_name"]) for row in chunks})
    entity_evidence: dict[tuple[str, str], set[str]] = {}
    for row in chunks:
        text = str(row["text"])
        for name, entity_type in ENTITY_LEXICON:
            if name.casefold() in text.casefold():
                entity_evidence.setdefault((name, entity_type), set()).add(str(row["chunk_id"]))
    if not entity_evidence:
        raise GraphBuildError("scoped entity extraction produced no evidence-bound entities")

    graph_path = output_root / "scoped-graph.jsonl"
    counts = {"document_nodes": 0, "chunk_nodes": 0, "entity_nodes": 0, "edges": 0}
    entity_records: list[dict[str, Any]] = []
    with graph_path.open("wb") as handle:
        for doc_name in documents:
            handle.write(
                _canonical_line(
                    {
                        "kind": "node",
                        "label": "Document",
                        "node_id": _id("document", doc_name),
                        "properties": {
                            "doc_name": doc_name,
                            "authority_release_id": authority_release_id,
                        },
                    }
                )
            )
            counts["document_nodes"] += 1
        for row in chunks:
            chunk_id = str(row["chunk_id"])
            doc_name = str(row["doc_name"])
            chunk_node_id = "chunkref:" + chunk_id.removeprefix("chunk:")
            handle.write(
                _canonical_line(
                    {
                        "kind": "node",
                        "label": "ChunkRef",
                        "node_id": chunk_node_id,
                        "properties": {
                            "chunk_id": chunk_id,
                            "authority_release_id": authority_release_id,
                        },
                    }
                )
            )
            handle.write(
                _canonical_line(
                    {
                        "kind": "edge",
                        "type": "HAS_CHUNK",
                        "from": _id("document", doc_name),
                        "to": chunk_node_id,
                        "evidence_chunk_ids": [chunk_id],
                    }
                )
            )
            counts["chunk_nodes"] += 1
            counts["edges"] += 1
        for (name, entity_type), evidence_ids in sorted(entity_evidence.items()):
            entity_id = _id("entity", entity_type, name)
            ordered_evidence = sorted(evidence_ids)
            handle.write(
                _canonical_line(
                    {
                        "kind": "node",
                        "label": "Entity",
                        "node_id": entity_id,
                        "properties": {
                            "canonical_name": name,
                            "entity_type": entity_type,
                            "authority_release_id": authority_release_id,
                        },
                    }
                )
            )
            counts["entity_nodes"] += 1
            entity_records.append(
                {
                    "entity_id": entity_id,
                    "canonical_name": name,
                    "entity_type": entity_type,
                    "evidence_chunk_ids": ordered_evidence,
                }
            )
            for chunk_id in ordered_evidence:
                if chunk_id not in chunk_ids:
                    raise GraphBuildError("entity edge does not resolve to SQLite authority")
                handle.write(
                    _canonical_line(
                        {
                            "kind": "edge",
                            "type": "MENTIONS",
                            "from": "chunkref:" + chunk_id.removeprefix("chunk:"),
                            "to": entity_id,
                            "evidence_chunk_ids": [chunk_id],
                        }
                    )
                )
                counts["edges"] += 1

    graph_sha256 = sha256_file(graph_path)
    graph_release_id = "graph:" + authority_release_id.split(":", 1)[-1] + ":" + graph_sha256[:16]
    graph_manifest = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "release_id": graph_release_id,
        "status": "candidate",
        "authority_release_id": authority_release_id,
        "authority_database_sha256": manifest["database"]["sha256"],
        "graph": {"path": graph_path.name, "sha256": graph_sha256},
        "counts": counts,
        "binding": {
            "text_edge_count": counts["edges"],
            "unresolved_sqlite_chunk_id_count": 0,
            "authoritative_text_stored_in_graph": False,
        },
        "neo4j": {
            "import_schema_version": GRAPH_IMPORT_SCHEMA_VERSION,
            "driver": NEO4J_DRIVER_NAME,
            "driver_version": NEO4J_DRIVER_VERSION,
            "node_labels": list(NODE_LABELS),
            "relationship_types": list(RELATIONSHIP_TYPES),
            "release_property": "graph_release_id",
            "runtime_access": "read_only",
        },
        "entities": entity_records,
    }
    write_json(output_root / "graph-manifest.json", graph_manifest)
    graph_manifest["manifest_sha256"] = sha256_file(output_root / "graph-manifest.json")
    return graph_manifest
