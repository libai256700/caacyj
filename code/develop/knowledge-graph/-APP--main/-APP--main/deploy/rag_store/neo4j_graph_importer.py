#!/usr/bin/env python3
"""Candidate-only Neo4j importer for a validated portable scoped graph."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from neo4j import Query, WRITE_ACCESS

from .scoped_graph_contract import ScopedGraphEdge, ScopedGraphNode, ScopedGraphPackage


IMPORT_CYPHER: Mapping[str, str] = {
    "release_absent": """
MATCH (node)
WHERE node.graph_release_id = $graph_release_id
RETURN count(node) AS existing_count
""".strip(),
    "documents": """
UNWIND $rows AS row
CREATE (node:Document {
  graph_release_id: $graph_release_id,
  authority_release_id: $authority_release_id,
  node_id: row.node_id,
  doc_name: row.doc_name
})
RETURN count(node) AS created_count
""".strip(),
    "chunks": """
UNWIND $rows AS row
CREATE (node:ChunkRef {
  graph_release_id: $graph_release_id,
  authority_release_id: $authority_release_id,
  node_id: row.node_id,
  chunk_id: row.chunk_id
})
RETURN count(node) AS created_count
""".strip(),
    "entities": """
UNWIND $rows AS row
CREATE (node:Entity {
  graph_release_id: $graph_release_id,
  authority_release_id: $authority_release_id,
  node_id: row.node_id,
  entity_id: row.node_id,
  canonical_name: row.canonical_name,
  entity_type: row.entity_type
})
RETURN count(node) AS created_count
""".strip(),
    "has_chunk": """
UNWIND $rows AS row
MATCH (source:Document {
  graph_release_id: $graph_release_id,
  node_id: row.from_node_id
})
MATCH (target:ChunkRef {
  graph_release_id: $graph_release_id,
  node_id: row.to_node_id
})
CREATE (source)-[edge:HAS_CHUNK {
  graph_release_id: $graph_release_id,
  authority_release_id: $authority_release_id,
  edge_id: row.edge_id,
  evidence_chunk_ids: row.evidence_chunk_ids
}]->(target)
RETURN count(edge) AS created_count
""".strip(),
    "mentions": """
UNWIND $rows AS row
MATCH (source:ChunkRef {
  graph_release_id: $graph_release_id,
  node_id: row.from_node_id
})
MATCH (target:Entity {
  graph_release_id: $graph_release_id,
  node_id: row.to_node_id
})
CREATE (source)-[edge:MENTIONS {
  graph_release_id: $graph_release_id,
  authority_release_id: $authority_release_id,
  edge_id: row.edge_id,
  evidence_chunk_ids: row.evidence_chunk_ids
}]->(target)
RETURN count(edge) AS created_count
""".strip(),
}


class ScopedNeo4jImportError(RuntimeError):
    """A candidate import failed without exposing driver or secret details."""


def _positive_int(value: int, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{field} must be between 1 and {maximum}")
    return value


def _positive_number(value: float, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field} must be positive")
    return float(value)


def _required_database(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 63
        or not all(character.isalnum() or character in "._-" for character in value)
    ):
        raise ValueError("database must be one exact safe name")
    return value


def _batches(rows: Sequence[Mapping[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for offset in range(0, len(rows), size):
        yield [dict(item) for item in rows[offset : offset + size]]


def _record_mapping(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    data = getattr(record, "data", None)
    if callable(data):
        value = data()
        if isinstance(value, Mapping):
            return dict(value)
    raise ScopedNeo4jImportError("Neo4j import returned an invalid result")


def _single_count(result: Any, field: str) -> int:
    records = [_record_mapping(item) for item in result]
    if len(records) != 1:
        raise ScopedNeo4jImportError("Neo4j import returned an invalid count")
    value = records[0].get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScopedNeo4jImportError("Neo4j import returned an invalid count")
    return value


def _edge_id(edge: ScopedGraphEdge) -> str:
    payload = json.dumps(
        [
            edge.relationship_type,
            edge.from_node_id,
            edge.to_node_id,
            list(edge.evidence_chunk_ids),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "edge:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _node_rows(nodes: Sequence[ScopedGraphNode], label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in nodes:
        if node.label != label:
            continue
        row: dict[str, Any] = {"node_id": node.node_id}
        if label == "Document":
            row["doc_name"] = node.properties["doc_name"]
        elif label == "ChunkRef":
            row["chunk_id"] = node.properties["chunk_id"]
        elif label == "Entity":
            row["canonical_name"] = node.properties["canonical_name"]
            row["entity_type"] = node.properties["entity_type"]
        rows.append(row)
    return rows


def _edge_rows(
    edges: Sequence[ScopedGraphEdge], relationship_type: str
) -> list[dict[str, Any]]:
    return [
        {
            "edge_id": _edge_id(edge),
            "from_node_id": edge.from_node_id,
            "to_node_id": edge.to_node_id,
            "evidence_chunk_ids": list(edge.evidence_chunk_ids),
        }
        for edge in edges
        if edge.relationship_type == relationship_type
    ]


class ScopedNeo4jImporter:
    """Import one release namespace without switching or deleting active data."""

    def __init__(
        self,
        *,
        driver: Any,
        database: str,
        batch_size: int = 500,
        query_timeout_seconds: float = 30.0,
    ) -> None:
        if driver is None or not callable(getattr(driver, "session", None)):
            raise TypeError("driver must provide Neo4j sessions")
        self._driver = driver
        self.database = _required_database(database)
        self.batch_size = _positive_int(batch_size, "batch_size", maximum=5000)
        self.query_timeout_seconds = _positive_number(
            query_timeout_seconds, "query_timeout_seconds"
        )

    def _run_count(
        self,
        session: Any,
        query_name: str,
        parameters: Mapping[str, Any],
        field: str,
    ) -> int:
        try:
            result = session.run(
                Query(
                    IMPORT_CYPHER[query_name],
                    timeout=self.query_timeout_seconds,
                ),
                dict(parameters),
            )
            return _single_count(result, field)
        except ScopedNeo4jImportError:
            raise
        except Exception as exc:
            raise ScopedNeo4jImportError("Neo4j candidate import failed") from exc

    def import_candidate(self, package: ScopedGraphPackage) -> dict[str, Any]:
        if not isinstance(package, ScopedGraphPackage):
            raise TypeError("package must be a validated ScopedGraphPackage")
        if package.status != "candidate":
            raise ScopedNeo4jImportError("only candidate graph packages may be imported")
        shared = {
            "graph_release_id": package.graph_release_id,
            "authority_release_id": package.authority_release_id,
        }
        groups = (
            ("documents", _node_rows(package.nodes, "Document")),
            ("chunks", _node_rows(package.nodes, "ChunkRef")),
            ("entities", _node_rows(package.nodes, "Entity")),
            ("has_chunk", _edge_rows(package.edges, "HAS_CHUNK")),
            ("mentions", _edge_rows(package.edges, "MENTIONS")),
        )
        write_query_count = 0
        imported_counts: dict[str, int] = {}
        try:
            with self._driver.session(
                database=self.database,
                default_access_mode=WRITE_ACCESS,
            ) as session:
                existing = self._run_count(
                    session,
                    "release_absent",
                    {"graph_release_id": package.graph_release_id},
                    "existing_count",
                )
                if existing != 0:
                    raise ScopedNeo4jImportError(
                        "graph candidate release namespace already exists"
                    )
                for query_name, rows in groups:
                    created_total = 0
                    for batch in _batches(rows, self.batch_size):
                        created = self._run_count(
                            session,
                            query_name,
                            {**shared, "rows": batch},
                            "created_count",
                        )
                        write_query_count += 1
                        if created != len(batch):
                            raise ScopedNeo4jImportError(
                                "Neo4j candidate import coverage mismatch"
                            )
                        created_total += created
                    imported_counts[query_name] = created_total
        except ScopedNeo4jImportError:
            raise
        except Exception as exc:
            raise ScopedNeo4jImportError("Neo4j candidate import failed") from exc

        expected_counts = {
            "documents": sum(node.label == "Document" for node in package.nodes),
            "chunks": len(package.chunk_ids),
            "entities": len(package.entity_ids),
            "has_chunk": sum(
                edge.relationship_type == "HAS_CHUNK" for edge in package.edges
            ),
            "mentions": sum(
                edge.relationship_type == "MENTIONS" for edge in package.edges
            ),
        }
        if imported_counts != expected_counts:
            raise ScopedNeo4jImportError("Neo4j candidate import totals mismatch")
        query_hashes = {
            name: hashlib.sha256(value.encode("utf-8")).hexdigest()
            for name, value in IMPORT_CYPHER.items()
        }
        return {
            "schema_version": "cloud-scoped-neo4j-import-receipt-v1",
            "status": "candidate-imported",
            "graph_release_id": package.graph_release_id,
            "authority_release_id": package.authority_release_id,
            "manifest_sha256": package.manifest_sha256,
            "graph_sha256": package.graph_sha256,
            "database": self.database,
            "counts": imported_counts,
            "write_query_count": write_query_count,
            "query_sha256": query_hashes,
            "active_switched": False,
            "deleted_release_ids": [],
        }


__all__ = [
    "IMPORT_CYPHER",
    "ScopedNeo4jImportError",
    "ScopedNeo4jImporter",
]
