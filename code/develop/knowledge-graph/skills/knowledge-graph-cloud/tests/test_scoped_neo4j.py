#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "deploy"))

import rag_store.scoped_graph_contract as GRAPH_CONTRACT
import pipeline.neo4j_import_candidate as NEO4J_IMPORT
from rag_store.neo4j_graph_importer import (
    IMPORT_CYPHER,
    ScopedNeo4jImporter,
)
from rag_store.runtime_neo4j_reader import (
    READ_CYPHER,
    Neo4jReadBinding,
    ReadOnlyNeo4jError,
    ReadOnlyScopedNeo4jReader,
    open_neo4j_driver,
    open_scoped_neo4j_reader,
)
from rag_store.scoped_graph_contract import (
    GRAPH_IMPORT_SCHEMA_VERSION,
    NEO4J_DRIVER_VERSION,
    ScopedGraphContractError,
    load_scoped_graph_package,
)
from pipeline.neo4j_import_candidate import (
    Neo4jImportConfig,
    Neo4jImportConfigError,
    run_candidate_import,
)
from pipeline.cloud_runtime import CloudRuntimeIntegrityError, CloudRuntimeResources


DOCUMENT_NAME = "synthetic.txt"
CHUNK_ID = "chunk:" + "a" * 40
DOCUMENT_ID = "document:" + hashlib.sha256(DOCUMENT_NAME.encode("utf-8")).hexdigest()[:40]
CHUNK_NODE_ID = "chunkref:" + CHUNK_ID.removeprefix("chunk:")
ENTITY_NAME = "无人机"
ENTITY_TYPE = "aircraft"
ENTITY_ID = "entity:" + hashlib.sha256(
    f"{ENTITY_TYPE}\x00{ENTITY_NAME}".encode("utf-8")
).hexdigest()[:40]


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _neo4j_ipv4_uri(
    scheme: str,
    *octets: int,
    include_port: bool = True,
) -> str:
    host = ".".join(str(octet) for octet in octets)
    port = ":7687" if include_port else ""
    return f"{scheme}://{host}{port}"


def _neo4j_ipv6_uri(scheme: str, prefix: str, suffix: str) -> str:
    return f"{scheme}://[{prefix}::{suffix}]:7687"


def _edge_identifier(edge) -> str:
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


class _FakeResult:
    def __init__(self, records):
        self._records = [dict(item) for item in records]

    def __iter__(self):
        return iter(self._records)


class _FakeSession:
    def __init__(self, driver, config):
        self.driver = driver
        self.config = dict(config)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return None

    def begin_transaction(self):
        self.driver.transaction_count += 1
        return _FakeTransaction(self)

    def run(self, query, parameters=None, **kwargs):
        text = getattr(query, "text", str(query))
        timeout = getattr(query, "timeout", None)
        values = dict(parameters or {})
        values.update(kwargs)
        self.driver.calls.append(
            {
                "text": text,
                "timeout": timeout,
                "parameters": values,
                "session": self.config,
            }
        )
        return _FakeResult(self.driver.respond(text, values))


class _FakeTransaction:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return None

    def run(self, query, parameters=None, **kwargs):
        return self.session.run(query, parameters, **kwargs)


class _FakeDriver:
    def __init__(self, entities, *, nodes=(), edges=()):
        self.entities = {str(item["entity_id"]): dict(item) for item in entities}
        self.nodes = [dict(item) for item in nodes]
        self.edges = [dict(item) for item in edges]
        self.calls = []
        self.closed = False
        self.imported_releases = set()
        self.transaction_count = 0

    def session(self, **config):
        return _FakeSession(self, config)

    def close(self):
        self.closed = True

    def respond(self, text, parameters):
        if text == IMPORT_CYPHER["release_absent"]:
            release_id = str(parameters["graph_release_id"])
            return [{"existing_count": int(release_id in self.imported_releases)}]
        if text in {
            IMPORT_CYPHER["documents"],
            IMPORT_CYPHER["chunks"],
            IMPORT_CYPHER["entities"],
            IMPORT_CYPHER["has_chunk"],
            IMPORT_CYPHER["mentions"],
        }:
            release_id = str(parameters["graph_release_id"])
            self.imported_releases.add(release_id)
            return [{"created_count": len(parameters["rows"])}]
        if text == READ_CYPHER["entities_by_ids"]:
            selected = [
                self.entities[item]
                for item in parameters["entity_ids"]
                if item in self.entities
            ]
            return selected[: int(parameters["limit"])]
        if text == READ_CYPHER["entities_by_terms"]:
            terms = [str(item).casefold() for item in parameters["terms"]]
            selected = [
                item
                for item in self.entities.values()
                if any(
                    term in str(item["canonical_name"]).casefold()
                    or str(item["canonical_name"]).casefold() in term
                    for term in terms
                )
            ]
            return selected[: int(parameters["limit"])]
        if text == READ_CYPHER["entities_by_chunk_ids"]:
            chunk_ids = set(parameters["chunk_ids"])
            selected = [
                item
                for item in self.entities.values()
                if chunk_ids.intersection(item["evidence_chunk_ids"])
            ]
            return selected[: int(parameters["limit"])]
        if text == READ_CYPHER["audit_nodes"]:
            selected = [
                item
                for item in sorted(self.nodes, key=lambda value: value["cursor"])
                if item["cursor"] > parameters["after_cursor"]
            ]
            return selected[: int(parameters["limit"])]
        if text == READ_CYPHER["audit_edges"]:
            selected = [
                item
                for item in sorted(self.edges, key=lambda value: value["cursor"])
                if item["cursor"] > parameters["after_cursor"]
            ]
            return selected[: int(parameters["limit"])]
        raise AssertionError("unexpected Cypher")


class ScopedNeo4jTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="kg-scoped-neo4j-test-")
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)
        self.manifest_path = self._write_package()
        self.package = load_scoped_graph_package(
            self.manifest_path,
            authority_chunk_documents={CHUNK_ID: DOCUMENT_NAME},
        )
        self.entity = {
            "entity_id": ENTITY_ID,
            "canonical_name": ENTITY_NAME,
            "entity_type": ENTITY_TYPE,
            "authority_release_id": "rag-authority:synthetic",
            "graph_release_id": "graph:synthetic",
            "evidence_chunk_ids": [CHUNK_ID],
        }
        self.live_nodes = []
        for index, node in enumerate(self.package.nodes):
            properties = {
                "graph_release_id": self.package.graph_release_id,
                "authority_release_id": self.package.authority_release_id,
                "node_id": node.node_id,
                **dict(node.properties),
            }
            if node.label == "Entity":
                properties["entity_id"] = node.node_id
            self.live_nodes.append(
                {
                    "cursor": f"node:{index:04d}",
                    "labels": [node.label],
                    "properties": properties,
                }
            )
        self.live_edges = [
            {
                "cursor": f"edge:{index:04d}",
                "relationship_type": edge.relationship_type,
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "properties": {
                    "graph_release_id": self.package.graph_release_id,
                    "authority_release_id": self.package.authority_release_id,
                    "edge_id": _edge_identifier(edge),
                    "evidence_chunk_ids": list(edge.evidence_chunk_ids),
                },
            }
            for index, edge in enumerate(self.package.edges)
        ]

    def _write_package(self) -> Path:
        graph_path = self.root / "scoped-graph.jsonl"
        records = [
            {
                "kind": "node",
                "label": "Document",
                "node_id": DOCUMENT_ID,
                "properties": {
                    "doc_name": DOCUMENT_NAME,
                    "authority_release_id": "rag-authority:synthetic",
                },
            },
            {
                "kind": "node",
                "label": "ChunkRef",
                "node_id": CHUNK_NODE_ID,
                "properties": {
                    "chunk_id": CHUNK_ID,
                    "authority_release_id": "rag-authority:synthetic",
                },
            },
            {
                "kind": "node",
                "label": "Entity",
                "node_id": ENTITY_ID,
                "properties": {
                    "canonical_name": ENTITY_NAME,
                    "entity_type": ENTITY_TYPE,
                    "authority_release_id": "rag-authority:synthetic",
                },
            },
            {
                "kind": "edge",
                "type": "HAS_CHUNK",
                "from": DOCUMENT_ID,
                "to": CHUNK_NODE_ID,
                "evidence_chunk_ids": [CHUNK_ID],
            },
            {
                "kind": "edge",
                "type": "MENTIONS",
                "from": CHUNK_NODE_ID,
                "to": ENTITY_ID,
                "evidence_chunk_ids": [CHUNK_ID],
            },
        ]
        graph_path.write_bytes(b"".join(_canonical_line(item) for item in records))
        manifest = {
            "schema_version": "cloud-scoped-graph-v1",
            "release_id": "graph:synthetic",
            "status": "candidate",
            "authority_release_id": "rag-authority:synthetic",
            "authority_database_sha256": "a" * 64,
            "graph": {
                "path": graph_path.name,
                "sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
            },
            "counts": {
                "document_nodes": 1,
                "chunk_nodes": 1,
                "entity_nodes": 1,
                "edges": 2,
            },
            "binding": {
                "text_edge_count": 2,
                "unresolved_sqlite_chunk_id_count": 0,
                "authoritative_text_stored_in_graph": False,
            },
            "neo4j": {
                "import_schema_version": GRAPH_IMPORT_SCHEMA_VERSION,
                "driver": "neo4j",
                "driver_version": NEO4J_DRIVER_VERSION,
                "node_labels": ["ChunkRef", "Document", "Entity"],
                "relationship_types": ["HAS_CHUNK", "MENTIONS"],
                "release_property": "graph_release_id",
                "runtime_access": "read_only",
            },
            "entities": [
                {
                    "entity_id": ENTITY_ID,
                    "canonical_name": ENTITY_NAME,
                    "entity_type": ENTITY_TYPE,
                    "evidence_chunk_ids": [CHUNK_ID],
                }
            ],
        }
        manifest_path = self.root / "graph-manifest.json"
        manifest_path.write_bytes(_canonical_line(manifest))
        return manifest_path

    @staticmethod
    def _read_binding() -> Neo4jReadBinding:
        return Neo4jReadBinding(
            graph_release_id="graph:synthetic",
            driver="neo4j",
            driver_version=NEO4J_DRIVER_VERSION,
            uri_env="KG_TEST_NEO4J_URI",
            username_env="KG_TEST_NEO4J_USERNAME",
            password_env="KG_TEST_NEO4J_PASSWORD",
            database_env="KG_TEST_NEO4J_DATABASE",
            query_timeout_seconds=1.0,
            max_records=10,
        )

    def _reader(self, driver: _FakeDriver) -> ReadOnlyScopedNeo4jReader:
        return ReadOnlyScopedNeo4jReader(
            driver=driver,
            database="kg-active",
            graph_release_id="graph:synthetic",
            authority_release_id="rag-authority:synthetic",
            package=self.package,
            query_timeout_seconds=1.5,
            max_records=10,
        )

    def test_contract_binds_jsonl_entities_and_sqlite_evidence(self) -> None:
        self.assertEqual("graph:synthetic", self.package.graph_release_id)
        self.assertEqual({CHUNK_ID}, set(self.package.chunk_ids))
        self.assertEqual({ENTITY_ID}, set(self.package.entity_ids))

        value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        value["entities"][0]["evidence_chunk_ids"] = ["chunk:missing"]
        self.manifest_path.write_bytes(_canonical_line(value))
        with self.assertRaises(ScopedGraphContractError):
            load_scoped_graph_package(
                self.manifest_path,
                authority_chunk_documents={CHUNK_ID: DOCUMENT_NAME},
            )

    def test_contract_rejects_boolean_unresolved_chunk_count(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["binding"]["unresolved_sqlite_chunk_id_count"] = False
        self.manifest_path.write_bytes(_canonical_line(manifest))

        with self.assertRaises(ScopedGraphContractError):
            load_scoped_graph_package(
                self.manifest_path,
                authority_chunk_documents={CHUNK_ID: DOCUMENT_NAME},
            )

    def test_contract_rejects_wrong_sqlite_document_owner_and_noncanonical_ids(self) -> None:
        with self.assertRaises(ScopedGraphContractError):
            load_scoped_graph_package(
                self.manifest_path,
                authority_chunk_documents={CHUNK_ID: "other.txt"},
            )

        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        graph_path = self.manifest_path.parent / manifest["graph"]["path"]
        records = [
            json.loads(line) for line in graph_path.read_text(encoding="utf-8").splitlines()
        ]
        records[0]["node_id"] = "document:" + "f" * 40
        records[3]["from"] = records[0]["node_id"]
        graph_path.write_bytes(b"".join(_canonical_line(record) for record in records))
        manifest["graph"]["sha256"] = hashlib.sha256(graph_path.read_bytes()).hexdigest()
        self.manifest_path.write_bytes(_canonical_line(manifest))
        with self.assertRaises(ScopedGraphContractError):
            load_scoped_graph_package(
                self.manifest_path,
                authority_chunk_documents={CHUNK_ID: DOCUMENT_NAME},
            )

    def test_graph_manifest_replacement_after_open_fails_closed(self) -> None:
        replacement = self.root / "graph-manifest-replacement.json"
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        replacement.write_text(
            json.dumps(manifest, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.assertNotEqual(
            self.manifest_path.read_bytes(),
            replacement.read_bytes(),
        )
        original = self.root / "graph-manifest-original.json"
        real_open = GRAPH_CONTRACT._open_regular_file

        def open_then_replace(raw, field):
            opened = real_open(raw, field)
            if field == "graph manifest":
                os.replace(self.manifest_path, original)
                os.replace(replacement, self.manifest_path)
            return opened

        try:
            with mock.patch.object(
                GRAPH_CONTRACT,
                "_open_regular_file",
                side_effect=open_then_replace,
            ):
                with self.assertRaises(ScopedGraphContractError) as caught:
                    load_scoped_graph_package(
                        self.manifest_path,
                        authority_chunk_documents={CHUNK_ID: DOCUMENT_NAME},
                    )
            self.assertIn("path binding changed", str(caught.exception))
        finally:
            if original.exists():
                os.replace(self.manifest_path, replacement)
                os.replace(original, self.manifest_path)

    def test_graph_data_replacement_after_open_fails_closed(self) -> None:
        graph_path = self.root / "scoped-graph.jsonl"
        replacement = self.root / "scoped-graph-replacement.jsonl"
        replacement.write_bytes(
            b"".join(
                (
                    json.dumps(json.loads(line), ensure_ascii=False) + "\n"
                ).encode("utf-8")
                for line in graph_path.read_text(encoding="utf-8").splitlines()
            )
        )
        self.assertNotEqual(graph_path.read_bytes(), replacement.read_bytes())
        original = self.root / "scoped-graph-original.jsonl"
        real_open = GRAPH_CONTRACT._open_regular_file

        def open_then_replace(raw, field):
            opened = real_open(raw, field)
            if field == "graph data":
                os.replace(graph_path, original)
                os.replace(replacement, graph_path)
            return opened

        try:
            with mock.patch.object(
                GRAPH_CONTRACT,
                "_open_regular_file",
                side_effect=open_then_replace,
            ):
                with self.assertRaises(ScopedGraphContractError) as caught:
                    load_scoped_graph_package(
                        self.manifest_path,
                        authority_chunk_documents={CHUNK_ID: DOCUMENT_NAME},
                    )
            self.assertIn("path binding changed", str(caught.exception))
        finally:
            if original.exists():
                os.replace(graph_path, replacement)
                os.replace(original, graph_path)

    def test_importer_executes_only_fixed_parameterized_candidate_writes(self) -> None:
        driver = _FakeDriver([self.entity])
        importer = ScopedNeo4jImporter(
            driver=driver,
            database="kg-candidate",
            batch_size=10,
            query_timeout_seconds=2.0,
        )
        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ):
            receipt = importer.import_candidate(self.package)

        self.assertEqual("candidate-imported", receipt["status"])
        self.assertEqual(5, receipt["write_query_count"])
        self.assertEqual(set(IMPORT_CYPHER.values()), {item["text"] for item in driver.calls})
        self.assertTrue(
            all(item["session"]["default_access_mode"] == "WRITE" for item in driver.calls)
        )
        serialized_queries = "\n".join(item["text"] for item in driver.calls)
        self.assertNotIn("无人机", serialized_queries)
        self.assertNotIn(CHUNK_ID, serialized_queries)

    def test_reader_uses_read_access_fixed_queries_and_parameter_payloads(self) -> None:
        driver = _FakeDriver(
            [self.entity], nodes=self.live_nodes, edges=self.live_edges
        )
        reader = ReadOnlyScopedNeo4jReader(
            driver=driver,
            database="kg-active",
            graph_release_id="graph:synthetic",
            authority_release_id="rag-authority:synthetic",
            package=self.package,
            query_timeout_seconds=1.5,
            max_records=10,
        )
        self.addCleanup(reader.close)
        injected_term = "无人机\"}) MATCH (n) DETACH DELETE n //"
        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ):
            by_id = reader.entities_by_ids([ENTITY_ID], limit=5)
            by_terms = reader.entities_by_terms([injected_term, "无人机"], limit=5)
            by_chunk = reader.entities_by_chunk_ids([CHUNK_ID], limit=5)

        self.assertEqual([ENTITY_ID], [item["entity_id"] for item in by_id])
        self.assertEqual([ENTITY_ID], [item["entity_id"] for item in by_terms])
        self.assertEqual([ENTITY_ID], [item["entity_id"] for item in by_chunk])
        self.assertEqual(
            {
                READ_CYPHER["entities_by_ids"],
                READ_CYPHER["entities_by_terms"],
                READ_CYPHER["entities_by_chunk_ids"],
            },
            {item["text"] for item in driver.calls},
        )
        self.assertTrue(
            all(item["session"]["default_access_mode"] == "READ" for item in driver.calls)
        )
        self.assertTrue(all(item["timeout"] == 1.5 for item in driver.calls))
        self.assertNotIn(injected_term, "\n".join(item["text"] for item in driver.calls))
        self.assertIn(injected_term.casefold(), driver.calls[1]["parameters"]["terms"])

    def test_uri_policy_accepts_only_loopback_or_tls_private_ip_literals(self) -> None:
        accepted = (
            "bolt://127.0.0.1:7687",
            "bolt://[::1]:7687",
            _neo4j_ipv4_uri("bolt+s", 10, 1, 2, 3),
            _neo4j_ipv4_uri("bolt+s", 172, 16, 4, 5),
            _neo4j_ipv4_uri("bolt+s", 192, 168, 1, 9),
            _neo4j_ipv6_uri("bolt+s", "fd00", "5"),
        )
        binding = self._read_binding()
        for uri in accepted:
            with self.subTest(uri=uri):
                captured = []

                def factory(value, *, auth, **_config):
                    captured.append((value, auth))
                    return _FakeDriver([])

                driver, database = open_neo4j_driver(
                    binding,
                    environment={
                        "KG_TEST_NEO4J_URI": uri,
                        "KG_TEST_NEO4J_USERNAME": "reader",
                        "KG_TEST_NEO4J_PASSWORD": "fake-secret",
                        "KG_TEST_NEO4J_DATABASE": "kg-active",
                    },
                    driver_factory=factory,
                )
                self.assertEqual("kg-active", database)
                self.assertEqual([(uri, ("reader", "fake-secret"))], captured)
                driver.close()

    def test_uri_policy_rejects_dns_public_ssc_missing_port_and_plain_private(self) -> None:
        rejected = (
            "neo4j://127.0.0.1:7687",
            _neo4j_ipv4_uri("neo4j+s", 10, 1, 2, 3),
            "neo4j://localhost:7687",
            "neo4j+s://8.8.8.8:7687",
            "neo4j+ssc://127.0.0.1:7687",
            "bolt+ssc://127.0.0.1:7687",
            "neo4j://127.0.0.1",
            _neo4j_ipv4_uri("neo4j", 10, 1, 2, 3),
            _neo4j_ipv4_uri("bolt", 172, 16, 4, 5),
            _neo4j_ipv4_uri("neo4j", 192, 168, 1, 9),
            _neo4j_ipv6_uri("bolt", "fd00", "5"),
            _neo4j_ipv4_uri("neo4j+s", 169, 254, 1, 1),
            _neo4j_ipv6_uri("neo4j+s", "fe80", "1"),
            "neo4j+s://100.64.0.1:7687",
        )
        binding = self._read_binding()
        for uri in rejected:
            with self.subTest(uri=uri), self.assertRaises(ReadOnlyNeo4jError):
                open_neo4j_driver(
                    binding,
                    environment={
                        "KG_TEST_NEO4J_URI": uri,
                        "KG_TEST_NEO4J_USERNAME": "reader",
                        "KG_TEST_NEO4J_PASSWORD": "fake-secret",
                        "KG_TEST_NEO4J_DATABASE": "kg-active",
                    },
                    driver_factory=lambda *_args, **_kwargs: self.fail(
                        "unsafe URI reached the driver factory"
                    ),
                )

    def test_timeout_contract_rejects_non_finite_numbers(self) -> None:
        values = (float("nan"), float("inf"), float("-inf"))
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Neo4jReadBinding(
                        graph_release_id="graph:synthetic",
                        driver="neo4j",
                        driver_version=NEO4J_DRIVER_VERSION,
                        uri_env="KG_TEST_NEO4J_URI",
                        username_env="KG_TEST_NEO4J_USERNAME",
                        password_env="KG_TEST_NEO4J_PASSWORD",
                        database_env="KG_TEST_NEO4J_DATABASE",
                        query_timeout_seconds=value,
                        max_records=10,
                    )
                with self.assertRaises(ValueError):
                    ScopedNeo4jImporter(
                        driver=_FakeDriver([self.entity]),
                        database="kg-candidate",
                        query_timeout_seconds=value,
                    )

    def test_startup_audit_is_paginated_in_one_read_transaction(self) -> None:
        driver = _FakeDriver(
            [self.entity], nodes=self.live_nodes, edges=self.live_edges
        )
        reader = self._reader(driver)
        self.addCleanup(reader.close)

        reader.verify_exact_package(page_size=1)

        self.assertEqual(1, driver.transaction_count)
        audit_calls = [
            item
            for item in driver.calls
            if item["text"] in {READ_CYPHER["audit_nodes"], READ_CYPHER["audit_edges"]}
        ]
        self.assertEqual(7, len(audit_calls))
        self.assertTrue(
            all(item["session"]["default_access_mode"] == "READ" for item in audit_calls)
        )
        self.assertTrue(all(item["parameters"]["limit"] == 1 for item in audit_calls))

    def test_startup_audit_rejects_missing_extra_and_tampered_records(self) -> None:
        cases = []

        missing_node = copy.deepcopy(self.live_nodes)
        missing_node.pop()
        cases.append(("missing-node", missing_node, copy.deepcopy(self.live_edges)))

        extra_node = copy.deepcopy(self.live_nodes)
        extra = copy.deepcopy(extra_node[0])
        extra["cursor"] = "node:9999"
        extra["properties"]["node_id"] = "document:extra"
        cases.append(("extra-node", extra_node + [extra], copy.deepcopy(self.live_edges)))

        tampered_node = copy.deepcopy(self.live_nodes)
        tampered_node[0]["properties"]["doc_name"] = "tampered.txt"
        cases.append(("tampered-node", tampered_node, copy.deepcopy(self.live_edges)))

        extra_label = copy.deepcopy(self.live_nodes)
        extra_label[0]["labels"].append("Injected")
        cases.append(("extra-label", extra_label, copy.deepcopy(self.live_edges)))

        missing_edge = copy.deepcopy(self.live_edges)
        missing_edge.pop()
        cases.append(("missing-edge", copy.deepcopy(self.live_nodes), missing_edge))

        extra_edge = copy.deepcopy(self.live_edges)
        injected_edge = copy.deepcopy(extra_edge[0])
        injected_edge["cursor"] = "edge:9999"
        injected_edge["properties"]["edge_id"] = "edge:" + "f" * 64
        cases.append(("extra-edge", copy.deepcopy(self.live_nodes), extra_edge + [injected_edge]))

        tampered_edge = copy.deepcopy(self.live_edges)
        tampered_edge[0]["properties"]["evidence_chunk_ids"] = ["chunk:other"]
        cases.append(("tampered-edge", copy.deepcopy(self.live_nodes), tampered_edge))

        changed_endpoint = copy.deepcopy(self.live_edges)
        changed_endpoint[0]["to_node_id"] = ENTITY_ID
        cases.append(("changed-endpoint", copy.deepcopy(self.live_nodes), changed_endpoint))

        for name, nodes, edges in cases:
            with self.subTest(case=name):
                driver = _FakeDriver([self.entity], nodes=nodes, edges=edges)
                reader = self._reader(driver)
                try:
                    with self.assertRaises(ReadOnlyNeo4jError):
                        reader.verify_exact_package(page_size=1)
                finally:
                    reader.close()

    def test_open_reader_fails_before_return_and_closes_on_live_graph_drift(self) -> None:
        binding = self._read_binding()
        fake_driver = _FakeDriver(
            [self.entity], nodes=self.live_nodes[:-1], edges=self.live_edges
        )

        with self.assertRaises(ReadOnlyNeo4jError):
            open_scoped_neo4j_reader(
                binding,
                authority_release_id="rag-authority:synthetic",
                package=self.package,
                environment={
                    "KG_TEST_NEO4J_URI": "bolt://127.0.0.1:7687",
                    "KG_TEST_NEO4J_USERNAME": "reader",
                    "KG_TEST_NEO4J_PASSWORD": "fake-secret",
                    "KG_TEST_NEO4J_DATABASE": "kg-active",
                },
                driver_factory=lambda *_args, **_kwargs: fake_driver,
            )

        self.assertTrue(fake_driver.closed)
        self.assertEqual(1, fake_driver.transaction_count)

    def test_entity_reads_reject_changed_sealed_properties_and_evidence(self) -> None:
        cases = {
            "canonical-name": {"canonical_name": "已篡改名称"},
            "entity-type": {"entity_type": "tampered-type"},
            "evidence": {"evidence_chunk_ids": ["chunk:other"]},
        }
        for name, mutation in cases.items():
            with self.subTest(case=name):
                entity = {**self.entity, **mutation}
                driver = _FakeDriver(
                    [entity], nodes=self.live_nodes, edges=self.live_edges
                )
                reader = self._reader(driver)
                try:
                    with self.assertRaises(ReadOnlyNeo4jError):
                        reader.entities_by_ids([ENTITY_ID], limit=1)
                finally:
                    reader.close()

    def test_cloud_runtime_rechecks_every_sealed_entity_field(self) -> None:
        runtime = object.__new__(CloudRuntimeResources)
        runtime._graph_entities = {
            ENTITY_ID: {
                "canonical_name": ENTITY_NAME,
                "entity_type": ENTITY_TYPE,
                "evidence_chunk_ids": frozenset({CHUNK_ID}),
            }
        }
        self.assertEqual(
            (ENTITY_ID, ENTITY_NAME, ENTITY_TYPE, [CHUNK_ID]),
            runtime._sealed_graph_entity(self.entity),
        )
        cases = (
            {**self.entity, "entity_id": "entity:outside"},
            {**self.entity, "canonical_name": "已篡改名称"},
            {**self.entity, "entity_type": "tampered-type"},
            {**self.entity, "evidence_chunk_ids": ["chunk:other"]},
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(
                CloudRuntimeIntegrityError
            ):
                runtime._sealed_graph_entity(value)

    def test_environment_factory_keeps_secrets_out_of_binding(self) -> None:
        binding = Neo4jReadBinding(
            graph_release_id="graph:synthetic",
            driver="neo4j",
            driver_version=NEO4J_DRIVER_VERSION,
            uri_env="KG_TEST_NEO4J_URI",
            username_env="KG_TEST_NEO4J_USERNAME",
            password_env="KG_TEST_NEO4J_PASSWORD",
            database_env="KG_TEST_NEO4J_DATABASE",
            query_timeout_seconds=1.0,
            max_records=10,
        )
        captured = {}
        fake_driver = _FakeDriver(
            [self.entity], nodes=self.live_nodes, edges=self.live_edges
        )

        def factory(uri, *, auth, **config):
            captured.update({"uri": uri, "auth": auth, "config": config})
            return fake_driver

        environment = {
            "KG_TEST_NEO4J_URI": "bolt://127.0.0.1:7687",
            "KG_TEST_NEO4J_USERNAME": "kg-reader",
            "KG_TEST_NEO4J_PASSWORD": "fake-neo4j-credential",
            "KG_TEST_NEO4J_DATABASE": "kg-active",
        }
        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ):
            reader = open_scoped_neo4j_reader(
                binding,
                authority_release_id="rag-authority:synthetic",
                package=self.package,
                environment=environment,
                driver_factory=factory,
            )
        self.addCleanup(reader.close)

        self.assertEqual("bolt://127.0.0.1:7687", captured["uri"])
        self.assertEqual(("kg-reader", "fake-neo4j-credential"), captured["auth"])
        self.assertNotIn("fake-neo4j-credential", repr(binding))
        self.assertNotIn("fake-neo4j-credential", repr(reader))

    def test_configured_import_cli_path_binds_authority_and_writes_safe_receipt(self) -> None:
        authority_path = self.root / "rag_chunks.db"
        connection = sqlite3.connect(authority_path)
        try:
            connection.execute(
                "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, doc_name TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE chunk_provenance (chunk_id TEXT PRIMARY KEY)"
            )
            connection.execute(
                "INSERT INTO chunks (chunk_id, doc_name) VALUES (?, ?)",
                (CHUNK_ID, DOCUMENT_NAME),
            )
            connection.execute(
                "INSERT INTO chunk_provenance (chunk_id) VALUES (?)",
                (CHUNK_ID,),
            )
            connection.commit()
        finally:
            connection.close()
        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["authority_database_sha256"] = authority_sha256
        self.manifest_path.write_bytes(_canonical_line(manifest))

        receipt_path = self.root / "candidate-import-receipt.json"
        config_path = self.root / "neo4j-import-config.json"
        config_path.write_bytes(
            _canonical_line(
                {
                    "schema_version": "kg-scoped-neo4j-import-config-v1",
                    "graph_manifest_path": str(self.manifest_path),
                    "authority_database_path": str(authority_path),
                    "receipt_output_path": str(receipt_path),
                    "driver": "neo4j",
                    "driver_version": NEO4J_DRIVER_VERSION,
                    "uri_env": "KG_TEST_NEO4J_URI",
                    "username_env": "KG_TEST_NEO4J_USERNAME",
                    "password_env": "KG_TEST_NEO4J_PASSWORD",
                    "database_env": "KG_TEST_NEO4J_DATABASE",
                    "batch_size": 10,
                    "query_timeout_seconds": 2.0,
                }
            )
        )
        environment = {
            "KG_TEST_NEO4J_URI": "bolt://127.0.0.1:7687",
            "KG_TEST_NEO4J_USERNAME": "kg-importer",
            "KG_TEST_NEO4J_PASSWORD": "fake-neo4j-credential",
            "KG_TEST_NEO4J_DATABASE": "kg-candidate",
        }
        fake_driver = _FakeDriver([self.entity])

        def factory(_uri, *, auth, **_config):
            self.assertEqual(("kg-importer", "fake-neo4j-credential"), auth)
            return fake_driver

        config = Neo4jImportConfig.load(config_path)
        with (
            mock.patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network forbidden"),
            ),
            mock.patch.object(
                NEO4J_IMPORT,
                "_require_formal_neo4j_import_bootstrap_context",
                return_value=NEO4J_IMPORT._current_neo4j_import_action_closure(),
            ),
        ):
            receipt = run_candidate_import(
                config,
                environment=environment,
                driver_factory=factory,
            )

        self.assertTrue(fake_driver.closed)
        self.assertEqual("candidate-imported", receipt["status"])
        self.assertEqual(authority_sha256, receipt["authority_database_sha256"])
        self.assertEqual(0o600, receipt_path.stat().st_mode & 0o777)
        receipt_text = receipt_path.read_text(encoding="utf-8")
        self.assertNotIn("fake-neo4j-credential", receipt_text)
        self.assertNotIn("kg-importer", receipt_text)

    def test_import_config_rejects_overflowed_finite_json_number(self) -> None:
        authority_path = self.root / "authority.db"
        authority_path.write_bytes(b"synthetic")
        receipt_path = self.root / "candidate-import-receipt.json"
        config_path = self.root / "neo4j-import-config.json"
        payload = _canonical_line(
            {
                "schema_version": "kg-scoped-neo4j-import-config-v1",
                "graph_manifest_path": str(self.manifest_path),
                "authority_database_path": str(authority_path),
                "receipt_output_path": str(receipt_path),
                "driver": "neo4j",
                "driver_version": NEO4J_DRIVER_VERSION,
                "uri_env": "KG_TEST_NEO4J_URI",
                "username_env": "KG_TEST_NEO4J_USERNAME",
                "password_env": "KG_TEST_NEO4J_PASSWORD",
                "database_env": "KG_TEST_NEO4J_DATABASE",
                "batch_size": 10,
                "query_timeout_seconds": 2.0,
            }
        ).replace(
            b'"query_timeout_seconds":2.0',
            b'"query_timeout_seconds":1e999',
        )
        config_path.write_bytes(payload)

        with self.assertRaises(Neo4jImportConfigError):
            Neo4jImportConfig.load(config_path)


if __name__ == "__main__":
    unittest.main()
