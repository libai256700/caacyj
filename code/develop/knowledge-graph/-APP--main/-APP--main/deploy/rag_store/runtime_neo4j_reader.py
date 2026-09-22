#!/usr/bin/env python3
"""Fixed-query, read-only Neo4j access for the public knowledge runtime."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

import neo4j
from neo4j import GraphDatabase, Query, READ_ACCESS

from .scoped_graph_contract import (
    NEO4J_DRIVER_NAME,
    NEO4J_DRIVER_VERSION,
    ScopedGraphEdge,
    ScopedGraphPackage,
)


READ_CYPHER: Mapping[str, str] = {
    "entities_by_ids": """
MATCH (entity:Entity {graph_release_id: $graph_release_id})
WHERE entity.entity_id IN $entity_ids
MATCH (chunk:ChunkRef {graph_release_id: $graph_release_id})
      -[mention:MENTIONS {graph_release_id: $graph_release_id}]->(entity)
WHERE entity.authority_release_id = $authority_release_id
  AND chunk.authority_release_id = $authority_release_id
  AND mention.authority_release_id = $authority_release_id
WITH entity, collect(DISTINCT chunk.chunk_id) AS evidence_chunk_ids
RETURN entity.entity_id AS entity_id,
       entity.canonical_name AS canonical_name,
       entity.entity_type AS entity_type,
       entity.authority_release_id AS authority_release_id,
       entity.graph_release_id AS graph_release_id,
       evidence_chunk_ids
ORDER BY entity.entity_id
LIMIT $limit
""".strip(),
    "entities_by_terms": """
MATCH (entity:Entity {graph_release_id: $graph_release_id})
WHERE any(term IN $terms WHERE
  toLower(entity.canonical_name) = term
  OR toLower(entity.canonical_name) CONTAINS term
  OR term CONTAINS toLower(entity.canonical_name)
)
MATCH (chunk:ChunkRef {graph_release_id: $graph_release_id})
      -[mention:MENTIONS {graph_release_id: $graph_release_id}]->(entity)
WHERE entity.authority_release_id = $authority_release_id
  AND chunk.authority_release_id = $authority_release_id
  AND mention.authority_release_id = $authority_release_id
WITH entity, collect(DISTINCT chunk.chunk_id) AS evidence_chunk_ids
RETURN entity.entity_id AS entity_id,
       entity.canonical_name AS canonical_name,
       entity.entity_type AS entity_type,
       entity.authority_release_id AS authority_release_id,
       entity.graph_release_id AS graph_release_id,
       evidence_chunk_ids
ORDER BY size(entity.canonical_name) DESC,
         entity.canonical_name,
         entity.entity_id
LIMIT $limit
""".strip(),
    "entities_by_chunk_ids": """
MATCH (matched_chunk:ChunkRef {graph_release_id: $graph_release_id})
      -[matched_mention:MENTIONS {graph_release_id: $graph_release_id}]->
      (entity:Entity {graph_release_id: $graph_release_id})
WHERE matched_chunk.chunk_id IN $chunk_ids
  AND entity.authority_release_id = $authority_release_id
  AND matched_chunk.authority_release_id = $authority_release_id
  AND matched_mention.authority_release_id = $authority_release_id
WITH DISTINCT entity
MATCH (evidence_chunk:ChunkRef {graph_release_id: $graph_release_id})
      -[evidence_mention:MENTIONS {graph_release_id: $graph_release_id}]->(entity)
WHERE evidence_chunk.authority_release_id = $authority_release_id
  AND evidence_mention.authority_release_id = $authority_release_id
WITH entity, collect(DISTINCT evidence_chunk.chunk_id) AS evidence_chunk_ids
RETURN entity.entity_id AS entity_id,
       entity.canonical_name AS canonical_name,
       entity.entity_type AS entity_type,
       entity.authority_release_id AS authority_release_id,
       entity.graph_release_id AS graph_release_id,
       evidence_chunk_ids
ORDER BY entity.entity_id
LIMIT $limit
""".strip(),
    "audit_nodes": """
MATCH (node {graph_release_id: $graph_release_id})
WHERE elementId(node) > $after_cursor
RETURN elementId(node) AS cursor,
       labels(node) AS labels,
       properties(node) AS properties
ORDER BY cursor
LIMIT $limit
""".strip(),
    "audit_edges": """
MATCH (source)-[edge]->(target)
WHERE (edge.graph_release_id = $graph_release_id
   OR source.graph_release_id = $graph_release_id
   OR target.graph_release_id = $graph_release_id)
  AND elementId(edge) > $after_cursor
RETURN elementId(edge) AS cursor,
       type(edge) AS relationship_type,
       source.node_id AS from_node_id,
       target.node_id AS to_node_id,
       properties(edge) AS properties
ORDER BY cursor
LIMIT $limit
""".strip(),
}


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_SAFE_DATABASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_ALLOWED_URI_SCHEMES = frozenset({"bolt", "bolt+s"})
_VERIFIED_TLS_URI_SCHEMES = frozenset({"bolt+s"})
_PRIVATE_IPV4_NETWORKS = tuple(
    ipaddress.ip_network((network_address, prefix_length))
    for network_address, prefix_length in (
        (0x0A000000, 8),
        (0xAC100000, 12),
        (0xC0A80000, 16),
    )
)
_PRIVATE_IPV6_NETWORK = ipaddress.ip_network((0xFC << 120, 7))
_RESULT_FIELDS = {
    "entity_id",
    "canonical_name",
    "entity_type",
    "authority_release_id",
    "graph_release_id",
    "evidence_chunk_ids",
}
_AUDIT_NODE_FIELDS = {"cursor", "labels", "properties"}
_AUDIT_EDGE_FIELDS = {
    "cursor",
    "relationship_type",
    "from_node_id",
    "to_node_id",
    "properties",
}


class ReadOnlyNeo4jError(RuntimeError):
    """A fixed read or runtime binding failed closed."""


@dataclass(frozen=True)
class Neo4jReadBinding:
    graph_release_id: str
    driver: str
    driver_version: str
    uri_env: str
    username_env: str
    password_env: str
    database_env: str
    query_timeout_seconds: float
    max_records: int

    def __post_init__(self) -> None:
        _required_text(self.graph_release_id, "graph_release_id")
        if self.driver != NEO4J_DRIVER_NAME:
            raise ValueError("Neo4j driver name mismatch")
        if self.driver_version != NEO4J_DRIVER_VERSION:
            raise ValueError("Neo4j driver version mismatch")
        for field in ("uri_env", "username_env", "password_env", "database_env"):
            value = getattr(self, field)
            if not isinstance(value, str) or not _ENV_NAME.fullmatch(value):
                raise ValueError(f"{field} must be an exact environment variable name")
        _positive_number(self.query_timeout_seconds, "query_timeout_seconds")
        _limit(self.max_records, "max_records", maximum=1000)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be exact non-empty text")
    return value


def _positive_number(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field} must be positive")
    return float(value)


def _limit(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{field} must be between 1 and {maximum}")
    return value


def _record_mapping(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    data = getattr(record, "data", None)
    if callable(data):
        value = data()
        if isinstance(value, Mapping):
            return dict(value)
    raise ReadOnlyNeo4jError("Neo4j fixed read returned an invalid record")


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


def _canonical_record(value: Mapping[str, Any], field: str) -> bytes:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReadOnlyNeo4jError(f"{field} contains unsupported values") from exc


def _expected_node_records(package: ScopedGraphPackage) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for node in package.nodes:
        properties = {
            "graph_release_id": package.graph_release_id,
            "authority_release_id": package.authority_release_id,
            "node_id": node.node_id,
            **dict(node.properties),
        }
        if node.label == "Entity":
            properties["entity_id"] = node.node_id
        records.append({"labels": [node.label], "properties": properties})
    return records


def _expected_edge_records(package: ScopedGraphPackage) -> list[dict[str, Any]]:
    return [
        {
            "relationship_type": edge.relationship_type,
            "from_node_id": edge.from_node_id,
            "to_node_id": edge.to_node_id,
            "properties": {
                "graph_release_id": package.graph_release_id,
                "authority_release_id": package.authority_release_id,
                "edge_id": _edge_id(edge),
                "evidence_chunk_ids": list(edge.evidence_chunk_ids),
            },
        }
        for edge in package.edges
    ]


def _safe_uri(value: str) -> str:
    uri = _required_text(value, "Neo4j URI")
    parsed = urlsplit(uri)
    if (
        parsed.scheme not in _ALLOWED_URI_SCHEMES
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ReadOnlyNeo4jError("Neo4j URI is invalid")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ReadOnlyNeo4jError("Neo4j URI is invalid") from exc
    if port is None or not 1 <= port <= 65535:
        raise ReadOnlyNeo4jError("Neo4j URI is invalid")
    hostname = parsed.hostname
    if hostname is None or "%" in hostname:
        raise ReadOnlyNeo4jError("Neo4j URI must use an explicit approved IP address")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise ReadOnlyNeo4jError(
            "Neo4j URI must use an explicit approved IP address"
        ) from exc
    if address.is_loopback:
        return uri
    if isinstance(address, ipaddress.IPv4Address):
        approved_private = any(address in network for network in _PRIVATE_IPV4_NETWORKS)
    else:
        approved_private = address in _PRIVATE_IPV6_NETWORK
    if not approved_private:
        raise ReadOnlyNeo4jError("Neo4j URI address is outside the approved private scope")
    if parsed.scheme not in _VERIFIED_TLS_URI_SCHEMES:
        raise ReadOnlyNeo4jError("non-loopback Neo4j connections require verified TLS")
    return uri


def _environment_value(environment: Mapping[str, str], name: str, field: str) -> str:
    value = environment.get(name, "")
    try:
        return _required_text(value, field)
    except ValueError as exc:
        raise ReadOnlyNeo4jError(f"{field} is not configured") from exc


class ReadOnlyScopedNeo4jReader:
    """Expose sealed entity reads and an exact read-only graph audit."""

    def __init__(
        self,
        *,
        driver: Any,
        database: str,
        graph_release_id: str,
        authority_release_id: str,
        package: ScopedGraphPackage,
        query_timeout_seconds: float,
        max_records: int,
    ) -> None:
        if driver is None or not callable(getattr(driver, "session", None)):
            raise TypeError("driver must provide Neo4j sessions")
        if not isinstance(database, str) or not _SAFE_DATABASE.fullmatch(database):
            raise ValueError("database must be one exact safe name")
        self._driver = driver
        self.database = database
        self.graph_release_id = _required_text(
            graph_release_id, "graph_release_id"
        )
        self.authority_release_id = _required_text(
            authority_release_id, "authority_release_id"
        )
        if not isinstance(package, ScopedGraphPackage):
            raise TypeError("package must be a validated ScopedGraphPackage")
        if (
            package.graph_release_id != self.graph_release_id
            or package.authority_release_id != self.authority_release_id
        ):
            raise ValueError("scoped graph package release binding mismatch")
        self._package = package
        self._sealed_entities = {
            str(item["entity_id"]): {
                "canonical_name": str(item["canonical_name"]),
                "entity_type": str(item["entity_type"]),
                "evidence_chunk_ids": frozenset(
                    str(value) for value in item["evidence_chunk_ids"]
                ),
            }
            for item in package.entities
        }
        self.query_timeout_seconds = _positive_number(
            query_timeout_seconds, "query_timeout_seconds"
        )
        self.max_records = _limit(max_records, "max_records", maximum=1000)
        self._lock = threading.RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def _run(
        self,
        query_name: str,
        parameters: Mapping[str, Any],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        bounded_limit = _limit(limit, "Neo4j result limit", maximum=self.max_records)
        with self._lock:
            if self._closed:
                raise ReadOnlyNeo4jError("read-only Neo4j reader is closed")
        payload = {
            "graph_release_id": self.graph_release_id,
            "authority_release_id": self.authority_release_id,
            **dict(parameters),
            "limit": bounded_limit,
        }
        try:
            with self._driver.session(
                database=self.database,
                default_access_mode=READ_ACCESS,
            ) as session:
                result = session.run(
                    Query(
                        READ_CYPHER[query_name],
                        timeout=self.query_timeout_seconds,
                    ),
                    payload,
                )
                records = [_record_mapping(item) for item in result]
        except ReadOnlyNeo4jError:
            raise
        except Exception as exc:
            raise ReadOnlyNeo4jError("Neo4j fixed read failed") from exc
        if len(records) > bounded_limit:
            raise ReadOnlyNeo4jError("Neo4j fixed read exceeded its result limit")

        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in records:
            if set(item) != _RESULT_FIELDS:
                raise ReadOnlyNeo4jError("Neo4j fixed read returned invalid fields")
            try:
                entity_id = _required_text(item["entity_id"], "entity_id")
                canonical_name = _required_text(
                    item["canonical_name"], "canonical_name"
                )
                entity_type = _required_text(item["entity_type"], "entity_type")
            except ValueError as exc:
                raise ReadOnlyNeo4jError(
                    "Neo4j fixed read returned invalid entity data"
                ) from exc
            evidence_raw = item["evidence_chunk_ids"]
            if not isinstance(evidence_raw, list) or not evidence_raw:
                raise ReadOnlyNeo4jError("Neo4j result has no SQLite evidence ids")
            try:
                evidence = [
                    _required_text(value, "evidence_chunk_id") for value in evidence_raw
                ]
            except ValueError as exc:
                raise ReadOnlyNeo4jError(
                    "Neo4j result has invalid SQLite evidence ids"
                ) from exc
            if (
                entity_id in seen_ids
                or len(evidence) != len(set(evidence))
                or item["authority_release_id"] != self.authority_release_id
                or item["graph_release_id"] != self.graph_release_id
            ):
                raise ReadOnlyNeo4jError("Neo4j result release binding mismatch")
            expected = self._sealed_entities.get(entity_id)
            if (
                expected is None
                or canonical_name != expected["canonical_name"]
                or entity_type != expected["entity_type"]
                or frozenset(evidence) != expected["evidence_chunk_ids"]
            ):
                raise ReadOnlyNeo4jError(
                    "Neo4j entity does not match the sealed graph package"
                )
            seen_ids.add(entity_id)
            normalized.append(
                {
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "entity_type": entity_type,
                    "authority_release_id": self.authority_release_id,
                    "graph_release_id": self.graph_release_id,
                    "evidence_chunk_ids": sorted(evidence),
                }
            )
        return normalized

    def _audit_records(
        self,
        transaction: Any,
        query_name: str,
        *,
        expected_count: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        after_cursor = ""
        expected_fields = (
            _AUDIT_NODE_FIELDS if query_name == "audit_nodes" else _AUDIT_EDGE_FIELDS
        )
        while True:
            result = transaction.run(
                READ_CYPHER[query_name],
                {
                    "graph_release_id": self.graph_release_id,
                    "after_cursor": after_cursor,
                    "limit": page_size,
                },
            )
            page = [_record_mapping(item) for item in result]
            if len(page) > page_size:
                raise ReadOnlyNeo4jError("Neo4j graph audit exceeded its page limit")
            previous_cursor = after_cursor
            for item in page:
                if set(item) != expected_fields:
                    raise ReadOnlyNeo4jError("Neo4j graph audit returned invalid fields")
                try:
                    cursor = _required_text(item["cursor"], "Neo4j audit cursor")
                except ValueError as exc:
                    raise ReadOnlyNeo4jError(
                        "Neo4j graph audit returned an invalid cursor"
                    ) from exc
                if cursor <= previous_cursor:
                    raise ReadOnlyNeo4jError(
                        "Neo4j graph audit pagination is not strictly ordered"
                    )
                previous_cursor = cursor
                records.append(item)
                if len(records) > expected_count:
                    raise ReadOnlyNeo4jError("live Neo4j contains extra scoped records")
            if len(page) < page_size:
                return records
            after_cursor = previous_cursor

    @staticmethod
    def _normalize_audit_nodes(records: Sequence[Mapping[str, Any]]) -> list[bytes]:
        normalized: list[bytes] = []
        for item in records:
            labels_raw = item["labels"]
            properties_raw = item["properties"]
            if (
                not isinstance(labels_raw, list)
                or not labels_raw
                or not isinstance(properties_raw, Mapping)
                or not all(isinstance(key, str) for key in properties_raw)
            ):
                raise ReadOnlyNeo4jError("Neo4j graph audit returned an invalid node")
            try:
                labels = [_required_text(value, "Neo4j node label") for value in labels_raw]
            except ValueError as exc:
                raise ReadOnlyNeo4jError(
                    "Neo4j graph audit returned an invalid node label"
                ) from exc
            if len(labels) != len(set(labels)):
                raise ReadOnlyNeo4jError("Neo4j graph audit returned duplicate node labels")
            normalized.append(
                _canonical_record(
                    {"labels": sorted(labels), "properties": dict(properties_raw)},
                    "Neo4j audited node",
                )
            )
        return sorted(normalized)

    @staticmethod
    def _normalize_audit_edges(records: Sequence[Mapping[str, Any]]) -> list[bytes]:
        normalized: list[bytes] = []
        for item in records:
            properties_raw = item["properties"]
            if not isinstance(properties_raw, Mapping) or not all(
                isinstance(key, str) for key in properties_raw
            ):
                raise ReadOnlyNeo4jError("Neo4j graph audit returned an invalid edge")
            try:
                relationship_type = _required_text(
                    item["relationship_type"], "Neo4j relationship type"
                )
                from_node_id = _required_text(item["from_node_id"], "Neo4j edge source")
                to_node_id = _required_text(item["to_node_id"], "Neo4j edge target")
            except ValueError as exc:
                raise ReadOnlyNeo4jError(
                    "Neo4j graph audit returned invalid edge identity"
                ) from exc
            normalized.append(
                _canonical_record(
                    {
                        "relationship_type": relationship_type,
                        "from_node_id": from_node_id,
                        "to_node_id": to_node_id,
                        "properties": dict(properties_raw),
                    },
                    "Neo4j audited edge",
                )
            )
        return sorted(normalized)

    def verify_exact_package(self, *, page_size: int | None = None) -> None:
        """Reject startup unless live scoped records exactly match the sealed package."""

        with self._lock:
            if self._closed:
                raise ReadOnlyNeo4jError("read-only Neo4j reader is closed")
        bounded_page_size = _limit(
            min(self.max_records, 500) if page_size is None else page_size,
            "Neo4j audit page size",
            maximum=1000,
        )
        expected_nodes = _expected_node_records(self._package)
        expected_edges = _expected_edge_records(self._package)
        try:
            with self._driver.session(
                database=self.database,
                default_access_mode=READ_ACCESS,
            ) as session:
                with session.begin_transaction(
                    timeout=self.query_timeout_seconds
                ) as transaction:
                    actual_nodes = self._audit_records(
                        transaction,
                        "audit_nodes",
                        expected_count=len(expected_nodes),
                        page_size=bounded_page_size,
                    )
                    actual_edges = self._audit_records(
                        transaction,
                        "audit_edges",
                        expected_count=len(expected_edges),
                        page_size=bounded_page_size,
                    )
        except ReadOnlyNeo4jError:
            raise
        except Exception as exc:
            raise ReadOnlyNeo4jError("Neo4j exact graph audit failed") from exc
        if self._normalize_audit_nodes(actual_nodes) != sorted(
            _canonical_record(item, "sealed graph node") for item in expected_nodes
        ):
            raise ReadOnlyNeo4jError("live Neo4j nodes do not match the sealed package")
        if self._normalize_audit_edges(actual_edges) != sorted(
            _canonical_record(item, "sealed graph edge") for item in expected_edges
        ):
            raise ReadOnlyNeo4jError("live Neo4j edges do not match the sealed package")

    def entities_by_ids(
        self, entity_ids: Sequence[str], *, limit: int
    ) -> list[dict[str, Any]]:
        ordered = list(dict.fromkeys(_required_text(item, "entity_id") for item in entity_ids))
        if not ordered:
            return []
        if len(ordered) > self.max_records:
            raise ValueError("entity id input exceeds the fixed reader limit")
        return self._run(
            "entities_by_ids", {"entity_ids": ordered}, limit=limit
        )

    def entities_by_terms(
        self, terms: Sequence[str], *, limit: int
    ) -> list[dict[str, Any]]:
        ordered = list(
            dict.fromkeys(
                _required_text(item, "graph term").casefold() for item in terms
            )
        )
        if not ordered:
            return []
        if len(ordered) > self.max_records:
            raise ValueError("graph term input exceeds the fixed reader limit")
        return self._run("entities_by_terms", {"terms": ordered}, limit=limit)

    def entities_by_chunk_ids(
        self, chunk_ids: Sequence[str], *, limit: int
    ) -> list[dict[str, Any]]:
        ordered = list(
            dict.fromkeys(_required_text(item, "chunk_id") for item in chunk_ids)
        )
        if not ordered:
            return []
        if len(ordered) > self.max_records:
            raise ValueError("chunk id input exceeds the fixed reader limit")
        return self._run(
            "entities_by_chunk_ids", {"chunk_ids": ordered}, limit=limit
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._driver.close()
            except Exception as exc:
                raise ReadOnlyNeo4jError("read-only Neo4j close failed") from exc

    def __enter__(self) -> "ReadOnlyScopedNeo4jReader":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()


DriverFactory = Callable[..., Any]


def open_neo4j_driver(
    binding: Neo4jReadBinding,
    *,
    environment: Mapping[str, str],
    driver_factory: DriverFactory = GraphDatabase.driver,
) -> tuple[Any, str]:
    """Resolve secret references and return an exact driver plus database name."""

    if not isinstance(binding, Neo4jReadBinding):
        raise TypeError("binding must be a Neo4jReadBinding")
    if str(getattr(neo4j, "__version__", "")) != NEO4J_DRIVER_VERSION:
        raise ReadOnlyNeo4jError("Neo4j runtime version does not match the frozen release")
    uri = _safe_uri(
        _environment_value(environment, binding.uri_env, "Neo4j URI")
    )
    username = _environment_value(
        environment, binding.username_env, "Neo4j username"
    )
    password = _environment_value(
        environment, binding.password_env, "Neo4j password"
    )
    database = _environment_value(
        environment, binding.database_env, "Neo4j database"
    )
    if not _SAFE_DATABASE.fullmatch(database):
        raise ReadOnlyNeo4jError("Neo4j database is invalid")
    try:
        driver = driver_factory(
            uri,
            auth=(username, password),
            connection_timeout=min(binding.query_timeout_seconds, 30.0),
            connection_acquisition_timeout=min(binding.query_timeout_seconds, 30.0),
            max_connection_pool_size=10,
            keep_alive=True,
        )
    except Exception as exc:
        raise ReadOnlyNeo4jError("Neo4j read-only driver construction failed") from exc
    return driver, database


def open_scoped_neo4j_reader(
    binding: Neo4jReadBinding,
    *,
    authority_release_id: str,
    package: ScopedGraphPackage,
    environment: Mapping[str, str],
    driver_factory: DriverFactory = GraphDatabase.driver,
) -> ReadOnlyScopedNeo4jReader:
    """Construct a sealed reader and verify live parity before normal use."""

    if not isinstance(package, ScopedGraphPackage):
        raise TypeError("package must be a validated ScopedGraphPackage")
    if binding.graph_release_id != package.graph_release_id:
        raise ValueError("Neo4j binding does not match the scoped graph package")

    driver, database = open_neo4j_driver(
        binding,
        environment=environment,
        driver_factory=driver_factory,
    )
    try:
        reader = ReadOnlyScopedNeo4jReader(
            driver=driver,
            database=database,
            graph_release_id=binding.graph_release_id,
            authority_release_id=authority_release_id,
            package=package,
            query_timeout_seconds=binding.query_timeout_seconds,
            max_records=binding.max_records,
        )
        reader.verify_exact_package()
        return reader
    except BaseException:
        try:
            driver.close()
        except Exception:
            pass
        raise


__all__ = [
    "Neo4jReadBinding",
    "READ_CYPHER",
    "ReadOnlyNeo4jError",
    "ReadOnlyScopedNeo4jReader",
    "open_neo4j_driver",
    "open_scoped_neo4j_reader",
]
