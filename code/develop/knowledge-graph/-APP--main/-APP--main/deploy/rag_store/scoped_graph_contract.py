#!/usr/bin/env python3
"""Strict portable scoped-graph package validation.

The JSONL file is a portable import artifact and an offline fixture. It is not
the public runtime query engine. Every graph node and relationship is bound to
the authoritative SQLite ``chunk_id`` set before an importer or reader may use
the package identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Mapping, Sequence


GRAPH_SCHEMA_VERSION = "cloud-scoped-graph-v1"
GRAPH_IMPORT_SCHEMA_VERSION = "cloud-scoped-neo4j-import-v1"
NEO4J_DRIVER_NAME = "neo4j"
NEO4J_DRIVER_VERSION = "6.2.0"
NODE_LABELS = ("ChunkRef", "Document", "Entity")
RELATIONSHIP_TYPES = ("HAS_CHUNK", "MENTIONS")
RELEASE_PROPERTY = "graph_release_id"
MAX_GRAPH_RECORDS = 1_000_000
MAX_GRAPH_LINE_BYTES = 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHUNK_ID = re.compile(r"^chunk:[0-9a-f]{40}$")


class ScopedGraphContractError(RuntimeError):
    """A graph package is malformed or not bound to SQLite authority."""


@dataclass(frozen=True)
class ScopedGraphNode:
    label: str
    node_id: str
    properties: Mapping[str, str]


@dataclass(frozen=True)
class ScopedGraphEdge:
    relationship_type: str
    from_node_id: str
    to_node_id: str
    evidence_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScopedGraphPackage:
    manifest_path: Path
    manifest_sha256: str
    graph_path: Path
    graph_sha256: str
    graph_release_id: str
    authority_release_id: str
    authority_database_sha256: str
    status: str
    nodes: tuple[ScopedGraphNode, ...]
    edges: tuple[ScopedGraphEdge, ...]
    entities: tuple[Mapping[str, Any], ...]

    @property
    def chunk_ids(self) -> tuple[str, ...]:
        return tuple(
            str(node.properties["chunk_id"])
            for node in self.nodes
            if node.label == "ChunkRef"
        )

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(node.node_id for node in self.nodes if node.label == "Entity")


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _open_regular_file(
    raw: str | Path,
    field: str,
) -> tuple[Path, BinaryIO, os.stat_result]:
    path = Path(raw)
    if not path.is_absolute():
        raise ScopedGraphContractError(f"{field} must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ScopedGraphContractError(f"{field} is unavailable") from exc
    if resolved != path:
        raise ScopedGraphContractError(f"{field} must be a canonical regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScopedGraphContractError(f"{field} is unavailable") from exc
    try:
        opened_stat = os.fstat(descriptor)
        named_stat = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or not stat.S_ISREG(named_stat.st_mode)
            or not _same_file(opened_stat, named_stat)
        ):
            raise ScopedGraphContractError(
                f"{field} changed while its descriptor was opened"
            )
        handle = os.fdopen(descriptor, "rb", closefd=True)
    except Exception:
        os.close(descriptor)
        raise
    return resolved, handle, opened_stat


def _require_open_path_binding(
    path: Path,
    handle: BinaryIO,
    opened_stat: os.stat_result,
    field: str,
) -> None:
    try:
        descriptor_stat = os.fstat(handle.fileno())
        named_stat = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ScopedGraphContractError(f"{field} path binding is unavailable") from exc
    if (
        not stat.S_ISREG(descriptor_stat.st_mode)
        or not stat.S_ISREG(named_stat.st_mode)
        or not _same_file(opened_stat, descriptor_stat)
        or not _same_file(descriptor_stat, named_stat)
    ):
        raise ScopedGraphContractError(f"{field} path binding changed during read")


def _strict_object(payload: bytes, field: str) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ScopedGraphContractError(f"{field} contains a duplicate key")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise ScopedGraphContractError(f"{field} contains a non-finite number")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except ScopedGraphContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScopedGraphContractError(f"{field} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ScopedGraphContractError(f"{field} must contain an object")
    return value


def _exact_mapping(
    value: Any,
    field: str,
    expected_fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ScopedGraphContractError(f"{field} field set is invalid")
    return dict(value)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ScopedGraphContractError(f"{field} must be exact non-empty text")
    return value


def _required_sha256(value: Any, field: str) -> str:
    text = _required_text(value, field)
    if not _SHA256.fullmatch(text):
        raise ScopedGraphContractError(f"{field} must be a lowercase SHA-256")
    return text


def _count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScopedGraphContractError(f"{field} must be a non-negative integer")
    return value


def _string_list(value: Any, field: str, *, non_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (non_empty and not value):
        raise ScopedGraphContractError(f"{field} must be a string list")
    items = tuple(_required_text(item, field) for item in value)
    if len(items) != len(set(items)):
        raise ScopedGraphContractError(f"{field} contains duplicates")
    return items


def _node_from_record(
    record: Mapping[str, Any],
    *,
    authority_release_id: str,
) -> ScopedGraphNode:
    item = _exact_mapping(
        record,
        "scoped graph node",
        {"kind", "label", "node_id", "properties"},
    )
    if item["kind"] != "node":
        raise ScopedGraphContractError("scoped graph node kind is invalid")
    label = _required_text(item["label"], "scoped graph node label")
    node_id = _required_text(item["node_id"], "scoped graph node id")
    property_fields = {
        "Document": {"doc_name", "authority_release_id"},
        "ChunkRef": {"chunk_id", "authority_release_id"},
        "Entity": {"canonical_name", "entity_type", "authority_release_id"},
    }
    if label not in property_fields:
        raise ScopedGraphContractError("scoped graph node label is not allowed")
    properties = _exact_mapping(
        item["properties"],
        f"scoped graph {label} properties",
        property_fields[label],
    )
    normalized = {
        key: _required_text(value, f"scoped graph {label}.{key}")
        for key, value in properties.items()
    }
    if normalized["authority_release_id"] != authority_release_id:
        raise ScopedGraphContractError("scoped graph node authority release mismatch")
    if label == "Document":
        expected_node_id = "document:" + hashlib.sha256(
            normalized["doc_name"].encode("utf-8")
        ).hexdigest()[:40]
    elif label == "ChunkRef":
        chunk_id = normalized["chunk_id"]
        if not _CHUNK_ID.fullmatch(chunk_id):
            raise ScopedGraphContractError("ChunkRef chunk id is invalid")
        expected_node_id = "chunkref:" + chunk_id.removeprefix("chunk:")
    else:
        entity_identity = (
            normalized["entity_type"] + "\0" + normalized["canonical_name"]
        )
        expected_node_id = "entity:" + hashlib.sha256(
            entity_identity.encode("utf-8")
        ).hexdigest()[:40]
    if node_id != expected_node_id:
        raise ScopedGraphContractError(f"{label} node id is not canonical")
    return ScopedGraphNode(label, node_id, MappingProxyType(normalized))


def _edge_from_record(record: Mapping[str, Any]) -> ScopedGraphEdge:
    item = _exact_mapping(
        record,
        "scoped graph edge",
        {"kind", "type", "from", "to", "evidence_chunk_ids"},
    )
    if item["kind"] != "edge":
        raise ScopedGraphContractError("scoped graph edge kind is invalid")
    relationship_type = _required_text(item["type"], "scoped graph edge type")
    if relationship_type not in RELATIONSHIP_TYPES:
        raise ScopedGraphContractError("scoped graph relationship type is not allowed")
    return ScopedGraphEdge(
        relationship_type=relationship_type,
        from_node_id=_required_text(item["from"], "scoped graph edge source"),
        to_node_id=_required_text(item["to"], "scoped graph edge target"),
        evidence_chunk_ids=_string_list(
            item["evidence_chunk_ids"], "scoped graph edge evidence"
        ),
    )


def load_scoped_graph_package(
    manifest_path: str | Path,
    *,
    authority_chunk_documents: Mapping[str, str],
) -> ScopedGraphPackage:
    """Load and fully bind one portable graph package to SQLite ownership."""

    manifest_file, manifest_handle, manifest_opened_stat = _open_regular_file(
        manifest_path,
        "graph manifest",
    )
    try:
        with manifest_handle:
            manifest_payload = manifest_handle.read()
            _require_open_path_binding(
                manifest_file,
                manifest_handle,
                manifest_opened_stat,
                "graph manifest",
            )
    except OSError as exc:
        raise ScopedGraphContractError("graph manifest is unreadable") from exc
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    manifest = _strict_object(manifest_payload, "graph manifest")
    root = _exact_mapping(
        manifest,
        "graph manifest",
        {
            "schema_version",
            "release_id",
            "status",
            "authority_release_id",
            "authority_database_sha256",
            "graph",
            "counts",
            "binding",
            "neo4j",
            "entities",
        },
    )
    if root["schema_version"] != GRAPH_SCHEMA_VERSION:
        raise ScopedGraphContractError("graph schema version mismatch")
    status = _required_text(root["status"], "graph status")
    if status not in {"candidate", "active"}:
        raise ScopedGraphContractError("graph status is invalid")
    graph_release_id = _required_text(root["release_id"], "graph release id")
    authority_release_id = _required_text(
        root["authority_release_id"], "graph authority release id"
    )
    authority_database_sha256 = _required_sha256(
        root["authority_database_sha256"], "graph authority database hash"
    )

    neo4j = _exact_mapping(
        root["neo4j"],
        "graph Neo4j contract",
        {
            "import_schema_version",
            "driver",
            "driver_version",
            "node_labels",
            "relationship_types",
            "release_property",
            "runtime_access",
        },
    )
    if (
        neo4j["import_schema_version"] != GRAPH_IMPORT_SCHEMA_VERSION
        or neo4j["driver"] != NEO4J_DRIVER_NAME
        or neo4j["driver_version"] != NEO4J_DRIVER_VERSION
        or tuple(neo4j["node_labels"] or ()) != NODE_LABELS
        or tuple(neo4j["relationship_types"] or ()) != RELATIONSHIP_TYPES
        or neo4j["release_property"] != RELEASE_PROPERTY
        or neo4j["runtime_access"] != "read_only"
    ):
        raise ScopedGraphContractError("graph Neo4j contract mismatch")

    graph = _exact_mapping(root["graph"], "graph data", {"path", "sha256"})
    graph_name = _required_text(graph["path"], "graph data path")
    if Path(graph_name).name != graph_name or Path(graph_name).is_absolute():
        raise ScopedGraphContractError("graph data path must be one exact filename")
    graph_sha256 = _required_sha256(graph["sha256"], "graph data hash")

    if not isinstance(authority_chunk_documents, Mapping):
        raise ScopedGraphContractError("authority chunk document map is invalid")
    authority_documents: dict[str, str] = {}
    for raw_chunk_id, raw_doc_name in authority_chunk_documents.items():
        chunk_id = _required_text(raw_chunk_id, "authority chunk id")
        doc_name = _required_text(raw_doc_name, "authority document name")
        if not _CHUNK_ID.fullmatch(chunk_id):
            raise ScopedGraphContractError("authority chunk id is invalid")
        authority_documents[chunk_id] = doc_name
    if not authority_documents:
        raise ScopedGraphContractError("authority chunk document map is empty")
    authority_ids = set(authority_documents)
    graph_file, graph_handle, graph_opened_stat = _open_regular_file(
        manifest_file.parent / graph_name,
        "graph data",
    )

    nodes: list[ScopedGraphNode] = []
    edges: list[ScopedGraphEdge] = []
    graph_digest = hashlib.sha256()
    try:
        with graph_handle:
            for line_number, line in enumerate(graph_handle, start=1):
                graph_digest.update(line)
                if line_number > MAX_GRAPH_RECORDS:
                    raise ScopedGraphContractError("graph record limit exceeded")
                if not line.endswith(b"\n") or not line.strip():
                    raise ScopedGraphContractError("graph JSONL line framing is invalid")
                if len(line) > MAX_GRAPH_LINE_BYTES:
                    raise ScopedGraphContractError("graph JSONL line is too large")
                record = _strict_object(line, f"graph JSONL line {line_number}")
                kind = record.get("kind")
                if kind == "node":
                    nodes.append(
                        _node_from_record(
                            record,
                            authority_release_id=authority_release_id,
                        )
                    )
                elif kind == "edge":
                    edges.append(_edge_from_record(record))
                else:
                    raise ScopedGraphContractError("graph JSONL record kind is invalid")
            _require_open_path_binding(
                graph_file,
                graph_handle,
                graph_opened_stat,
                "graph data",
            )
    except OSError as exc:
        raise ScopedGraphContractError("graph data is unreadable") from exc
    if graph_digest.hexdigest() != graph_sha256:
        raise ScopedGraphContractError("graph data hash mismatch")
    if not nodes or not edges:
        raise ScopedGraphContractError("graph data must contain nodes and edges")

    node_by_id: dict[str, ScopedGraphNode] = {}
    for node in nodes:
        if node.node_id in node_by_id:
            raise ScopedGraphContractError("graph contains a duplicate node id")
        node_by_id[node.node_id] = node
    edge_identities: set[tuple[Any, ...]] = set()
    has_chunk_targets: set[str] = set()
    entity_evidence: dict[str, set[str]] = {
        node.node_id: set() for node in nodes if node.label == "Entity"
    }
    for edge in edges:
        identity = (
            edge.relationship_type,
            edge.from_node_id,
            edge.to_node_id,
            edge.evidence_chunk_ids,
        )
        if identity in edge_identities:
            raise ScopedGraphContractError("graph contains a duplicate edge")
        edge_identities.add(identity)
        source = node_by_id.get(edge.from_node_id)
        target = node_by_id.get(edge.to_node_id)
        if source is None or target is None:
            raise ScopedGraphContractError("graph edge endpoint is missing")
        if len(edge.evidence_chunk_ids) != 1:
            raise ScopedGraphContractError("graph edge must bind one SQLite chunk")
        evidence_id = edge.evidence_chunk_ids[0]
        if evidence_id not in authority_ids:
            raise ScopedGraphContractError("graph edge evidence is absent from SQLite")
        if edge.relationship_type == "HAS_CHUNK":
            if source.label != "Document" or target.label != "ChunkRef":
                raise ScopedGraphContractError("HAS_CHUNK endpoint labels are invalid")
            if target.properties["chunk_id"] != evidence_id:
                raise ScopedGraphContractError("HAS_CHUNK evidence binding mismatch")
            if source.properties["doc_name"] != authority_documents[evidence_id]:
                raise ScopedGraphContractError("HAS_CHUNK document ownership mismatch")
            if target.node_id in has_chunk_targets:
                raise ScopedGraphContractError("ChunkRef has multiple Document owners")
            has_chunk_targets.add(target.node_id)
        elif edge.relationship_type == "MENTIONS":
            if source.label != "ChunkRef" or target.label != "Entity":
                raise ScopedGraphContractError("MENTIONS endpoint labels are invalid")
            if source.properties["chunk_id"] != evidence_id:
                raise ScopedGraphContractError("MENTIONS evidence binding mismatch")
            entity_evidence[target.node_id].add(evidence_id)

    chunk_nodes = [node for node in nodes if node.label == "ChunkRef"]
    document_nodes = [node for node in nodes if node.label == "Document"]
    chunk_ids = {str(node.properties["chunk_id"]) for node in chunk_nodes}
    if len(chunk_ids) != len(chunk_nodes) or chunk_ids != authority_ids:
        raise ScopedGraphContractError("graph ChunkRef coverage does not match SQLite")
    if has_chunk_targets != {node.node_id for node in chunk_nodes}:
        raise ScopedGraphContractError("graph Document to ChunkRef coverage is incomplete")
    document_names = {str(node.properties["doc_name"]) for node in document_nodes}
    if (
        len(document_names) != len(document_nodes)
        or document_names != set(authority_documents.values())
    ):
        raise ScopedGraphContractError("graph Document coverage does not match SQLite")
    if not entity_evidence or any(not values for values in entity_evidence.values()):
        raise ScopedGraphContractError("graph Entity evidence coverage is incomplete")

    manifest_entities_raw = root["entities"]
    if not isinstance(manifest_entities_raw, list) or not manifest_entities_raw:
        raise ScopedGraphContractError("graph manifest entities are invalid")
    manifest_entities: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(manifest_entities_raw):
        item = _exact_mapping(
            value,
            f"graph manifest entity {index}",
            {"entity_id", "canonical_name", "entity_type", "evidence_chunk_ids"},
        )
        entity_id = _required_text(item["entity_id"], "graph manifest entity id")
        if entity_id in manifest_entities:
            raise ScopedGraphContractError("graph manifest entity id is duplicated")
        evidence = _string_list(
            item["evidence_chunk_ids"], "graph manifest entity evidence"
        )
        manifest_entities[entity_id] = {
            "entity_id": entity_id,
            "canonical_name": _required_text(
                item["canonical_name"], "graph manifest entity name"
            ),
            "entity_type": _required_text(
                item["entity_type"], "graph manifest entity type"
            ),
            "evidence_chunk_ids": sorted(evidence),
        }
    graph_entities: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if node.label != "Entity":
            continue
        graph_entities[node.node_id] = {
            "entity_id": node.node_id,
            "canonical_name": node.properties["canonical_name"],
            "entity_type": node.properties["entity_type"],
            "evidence_chunk_ids": sorted(entity_evidence[node.node_id]),
        }
    if manifest_entities != graph_entities:
        raise ScopedGraphContractError("manifest entities do not match graph JSONL")

    counts = _exact_mapping(
        root["counts"],
        "graph counts",
        {"document_nodes", "chunk_nodes", "entity_nodes", "edges"},
    )
    expected_counts = {
        "document_nodes": sum(node.label == "Document" for node in nodes),
        "chunk_nodes": len(chunk_nodes),
        "entity_nodes": len(graph_entities),
        "edges": len(edges),
    }
    actual_counts = {key: _count(value, f"graph counts.{key}") for key, value in counts.items()}
    if actual_counts != expected_counts:
        raise ScopedGraphContractError("graph manifest counts mismatch")
    binding = _exact_mapping(
        root["binding"],
        "graph binding",
        {
            "text_edge_count",
            "unresolved_sqlite_chunk_id_count",
            "authoritative_text_stored_in_graph",
        },
    )
    if (
        _count(binding["text_edge_count"], "graph binding text edge count")
        != len(edges)
        or _count(
            binding["unresolved_sqlite_chunk_id_count"],
            "graph binding unresolved SQLite chunk id count",
        )
        != 0
        or binding["authoritative_text_stored_in_graph"] is not False
    ):
        raise ScopedGraphContractError("graph authority binding flags are invalid")

    return ScopedGraphPackage(
        manifest_path=manifest_file,
        manifest_sha256=manifest_sha256,
        graph_path=graph_file,
        graph_sha256=graph_sha256,
        graph_release_id=graph_release_id,
        authority_release_id=authority_release_id,
        authority_database_sha256=authority_database_sha256,
        status=status,
        nodes=tuple(nodes),
        edges=tuple(edges),
        entities=tuple(
            MappingProxyType(dict(manifest_entities[entity_id]))
            for entity_id in sorted(manifest_entities)
        ),
    )


__all__ = [
    "GRAPH_IMPORT_SCHEMA_VERSION",
    "GRAPH_SCHEMA_VERSION",
    "NEO4J_DRIVER_NAME",
    "NEO4J_DRIVER_VERSION",
    "NODE_LABELS",
    "RELATIONSHIP_TYPES",
    "ScopedGraphContractError",
    "ScopedGraphEdge",
    "ScopedGraphNode",
    "ScopedGraphPackage",
    "load_scoped_graph_package",
]
