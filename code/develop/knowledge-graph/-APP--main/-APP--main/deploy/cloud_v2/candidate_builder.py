#!/usr/bin/env python3
"""Build BM25, fake embeddings, local vectors, and graph from clean authority."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal candidate builder CLI bootstrap context is required\n")
    raise SystemExit(2)

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

from deploy.rag_store.embedding_adapter import (
    EmbeddingAdapter,
    EmbeddingInput,
    EmbeddingPolicy,
)
from deploy.rag_store.local_vector_store import (
    LocalVectorContract,
    LocalVectorStoreAdapter,
    VectorRecord,
)

from .authority_builder import (
    AuthorityBuildError,
    _open_held_builder_source,
    _require_formal_bootstrap_context as _require_authority_formal_bootstrap_context,
    _require_isolated_python as _require_authority_isolated_python,
    _revalidate_held_builder_source,
    _write_json_impl as write_json,
)
from .fake_providers import (
    FAKE_PROVIDER_POLICY_VERSION,
    FakeEmbeddingTransport,
    fake_embedding_identity,
)
from .graph_builder import build_graph
from .source_scope import sha256_file


DERIVED_SCHEMA_VERSION = "cloud-v2-derived-candidate-v1"
BM25_SCHEMA_VERSION = "cloud-v2-sqlite-fts5-trigram-v1"
LOCAL_DATA_RELEASE_ID_SCHEMA_VERSION = "cloud-v2-local-data-release-id-v2"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CandidateBuildError(RuntimeError):
    """A derived candidate failed a binding, completeness, or output gate."""


def _require_formal_bootstrap_context() -> None:
    try:
        _require_authority_formal_bootstrap_context()
    except AuthorityBuildError as exc:
        raise CandidateBuildError(
            "formal candidate builder CLI bootstrap context is required"
        ) from exc


def _require_isolated_python() -> None:
    try:
        _require_authority_isolated_python()
    except AuthorityBuildError as exc:
        raise CandidateBuildError(
            "formal candidate builder requires Python -I -S -B"
        ) from exc


_FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_EXECUTED_CANDIDATE_BUILDER_SOURCE = _open_held_builder_source(
    Path(__file__),
    "candidate builder source",
    max_bytes=4 * 1024 * 1024,
)
_FORMAL_CANDIDATE_BUILDER_SOURCE_SHA256: str | None = None
_FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_CANDIDATE_BUILDER_ACTION_CLOSURE: tuple[object, ...] | None = None


def _candidate_builder_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_CANDIDATE_BUILDER_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_candidate_builder_action_closure() -> tuple[object, ...]:
    return (
        main,
        _main_impl,
        build_derived_candidate,
        _build_derived_candidate_impl,
        _parser,
        _load_authority,
        _authority_rows,
        _canonical_source_fingerprint,
        _build_bm25,
        _fake_embedding_adapter,
        _ledger_summary,
        local_data_release_id,
        write_json,
        sha256_file,
        build_graph,
        fake_embedding_identity,
        EmbeddingAdapter,
        EmbeddingAdapter.__dict__["embed_build"],
        LocalVectorContract,
        LocalVectorStoreAdapter,
        LocalVectorStoreAdapter.__dict__["build_candidate"],
        VectorRecord,
        FakeEmbeddingTransport,
    )


def _install_formal_candidate_builder_bootstrap_context(
    binding: Mapping[str, Any],
) -> None:
    global _FORMAL_CANDIDATE_BUILDER_ACTION_CLOSURE
    global _FORMAL_CANDIDATE_BUILDER_SOURCE_SHA256
    global _FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_IDENTITY

    _require_formal_bootstrap_context()
    _require_isolated_python()
    required = {*_FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", str(binding["sha256"]))
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise CandidateBuildError(
            "formal candidate builder CLI source binding is malformed"
        )
    expected_state = {
        field: int(binding[field])
        for field in _FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_FIELDS
    }
    try:
        _revalidate_held_builder_source(
            _EXECUTED_CANDIDATE_BUILDER_SOURCE,
            field="candidate builder source",
        )
    except AuthorityBuildError as exc:
        raise CandidateBuildError(
            "formal candidate builder CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_CANDIDATE_BUILDER_SOURCE.payload).hexdigest()
        != binding["sha256"]
        or _candidate_builder_source_state_identity() != expected_state
    ):
        raise CandidateBuildError(
            "formal candidate builder CLI source differs from held bootstrap bytes"
        )
    _FORMAL_CANDIDATE_BUILDER_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_IDENTITY = expected_state
    _FORMAL_CANDIDATE_BUILDER_ACTION_CLOSURE = (
        _current_candidate_builder_action_closure()
    )


def _require_formal_candidate_builder_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_CANDIDATE_BUILDER_SOURCE_SHA256
    source_state = _FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_IDENTITY
    actions = _FORMAL_CANDIDATE_BUILDER_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_FIELDS)
        or any(
            type(source_state.get(field)) is not int or int(source_state[field]) < 0
            for field in _FORMAL_CANDIDATE_BUILDER_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != 23
    ):
        raise CandidateBuildError(
            "formal candidate builder CLI bootstrap context is required"
        )
    _require_formal_bootstrap_context()
    _require_isolated_python()
    try:
        _revalidate_held_builder_source(
            _EXECUTED_CANDIDATE_BUILDER_SOURCE,
            field="candidate builder source",
        )
    except AuthorityBuildError as exc:
        raise CandidateBuildError(
            "formal candidate builder CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_CANDIDATE_BUILDER_SOURCE.payload).hexdigest()
        != source_sha256
        or _candidate_builder_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_candidate_builder_action_closure(),
                actions,
                strict=True,
            )
        )
    ):
        raise CandidateBuildError(
            "formal candidate builder CLI source or action closure changed"
        )
    return actions


def local_data_release_id(
    authority_database_sha256: str, embedding_identity_sha256: str
) -> str:
    """Bind a local vector release path to both authority and vector space."""

    identities = {
        "authority_database_sha256": authority_database_sha256,
        "embedding_identity_sha256": embedding_identity_sha256,
    }
    if any(
        not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value)
        for value in identities.values()
    ):
        raise CandidateBuildError("local data release identities must be SHA-256 values")
    payload = {
        "schema_version": LOCAL_DATA_RELEASE_ID_SCHEMA_VERSION,
        **identities,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return "r9-" + digest


def _load_authority(root: Path) -> tuple[dict[str, Any], Path]:
    manifest_path = root / "authority-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateBuildError("authority manifest cannot be loaded") from exc
    database = manifest.get("database") if isinstance(manifest, dict) else None
    if manifest.get("status") != "candidate" or not isinstance(database, dict):
        raise CandidateBuildError("authority input is not a clean candidate")
    relative = database.get("path")
    if not isinstance(relative, str) or Path(relative).name != relative:
        raise CandidateBuildError("authority database path is not exact")
    database_path = root / relative
    if not database_path.is_file() or database_path.is_symlink():
        raise CandidateBuildError("authority database is unavailable")
    if sha256_file(database_path) != database.get("sha256"):
        raise CandidateBuildError("authority database hash mismatch")
    return manifest, database_path


def _authority_rows(database_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise CandidateBuildError("authority integrity gate failed")
        rows = [
            dict(row)
            for row in connection.execute(
                """SELECT c.chunk_id, c.text, c.doc_name, c.chunk_index, p.content_type
                   FROM chunks c JOIN chunk_provenance p ON p.chunk_id=c.chunk_id
                   ORDER BY c.doc_name, c.chunk_index"""
            )
        ]
        sources = {
            str(row["chunk_id"]): str(row["source_sha256"])
            for row in connection.execute(
                "SELECT chunk_id, source_sha256 FROM chunk_provenance ORDER BY chunk_id"
            )
        }
    finally:
        connection.close()
    if not rows or len(rows) != len(sources):
        raise CandidateBuildError("authority chunks and provenance are incomplete")
    return rows, sources


def _canonical_source_fingerprint(rows: list[dict[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    text_byte_count = 0
    text_codepoint_count = 0
    document_names: set[str] = set()
    for row in sorted(rows, key=lambda item: str(item["chunk_id"])):
        text = str(row["text"])
        document_names.add(str(row["doc_name"]))
        text_byte_count += len(text.encode("utf-8"))
        text_codepoint_count += len(text)
        canonical_row = json.dumps(
            [row["chunk_id"], row["doc_name"], row["chunk_index"], text],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest.update(canonical_row.encode("utf-8"))
        digest.update(b"\n")
    return {
        "chunk_count": len(rows),
        "document_count": len(document_names),
        "text_byte_count": text_byte_count,
        "text_codepoint_count": text_codepoint_count,
        "schema_version": "chunks-v1",
        "fingerprint_algorithm": "sha256-jsonl-chunk-content-v1",
        "fingerprint": digest.hexdigest(),
    }


def _build_bm25(rows: list[dict[str, Any]], output_root: Path, authority: dict[str, Any]) -> dict[str, Any]:
    database_path = output_root / "bm25.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA page_size=4096")
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE chunks_fts USING fts5(text, chunk_id UNINDEXED, doc_name UNINDEXED, tokenize='trigram')"
            )
        except sqlite3.OperationalError as exc:
            raise CandidateBuildError("SQLite FTS5 trigram tokenizer is unavailable") from exc
        connection.executemany(
            "INSERT INTO chunks_fts (text, chunk_id, doc_name) VALUES (?, ?, ?)",
            [(row["text"], row["chunk_id"], row["doc_name"]) for row in rows],
        )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        if count != len(rows):
            raise CandidateBuildError("BM25 row count differs from SQLite authority")
        smoke = connection.execute(
            "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 1",
            ("无人机",),
        ).fetchone()
        if smoke is None:
            raise CandidateBuildError("BM25 representative retrieval returned no result")
        connection.execute("VACUUM")
    finally:
        connection.close()
    os.chmod(database_path, 0o600)
    manifest = {
        "schema_version": BM25_SCHEMA_VERSION,
        "status": "candidate",
        "authority_release_id": authority["release_id"],
        "authority_database_sha256": authority["database"]["sha256"],
        "source": _canonical_source_fingerprint(rows),
        "index": {"path": database_path.name, "sha256": sha256_file(database_path)},
        "indexed_chunk_count": len(rows),
        "tokenizer": "trigram",
        "minimum_effective_query_codepoints": 3,
        "short_query_fallback": "authority-sqlite-substring-v1",
        "sqlite_backfill_required": True,
    }
    write_json(output_root / "bm25-manifest.json", manifest)
    manifest["manifest_sha256"] = sha256_file(output_root / "bm25-manifest.json")
    return manifest


def _fake_embedding_adapter() -> tuple[EmbeddingAdapter, FakeEmbeddingTransport]:
    identity = fake_embedding_identity()
    transport = FakeEmbeddingTransport()
    policy = EmbeddingPolicy(
        batch_size=64,
        max_input_units=4096,
        timeout_seconds=2.0,
        max_retries=0,
        max_requests_per_operation=10000,
        max_cost_microunits_per_request=0,
        total_cost_budget_microunits=0,
    )
    return EmbeddingAdapter(identity, policy=policy, transport=transport), transport


def _ledger_summary(result: Any) -> dict[str, Any]:
    return {
        "purpose": result.purpose,
        "identity_sha256": result.identity_sha256,
        "vector_count": len(result.vectors),
        "calls": [
            {
                "batch_index": entry.batch_index,
                "attempt": entry.attempt,
                "status": entry.status,
                "request_sha256": entry.request_sha256,
                "response_sha256": entry.response_sha256,
                "accounted_cost_microunits": entry.accounted_cost_microunits,
            }
            for entry in result.ledger
        ],
    }


def _build_derived_candidate_impl(
    authority_root: str | Path,
    candidate_root: str | Path,
) -> dict[str, Any]:
    authority_root = Path(authority_root).resolve(strict=True)
    output_root = Path(candidate_root).resolve()
    if not any(part in {"candidate", "candidates"} for part in output_root.parts):
        raise CandidateBuildError("derived output must be inside an explicit candidate root")
    if output_root.exists():
        raise CandidateBuildError("derived candidate output already exists")
    output_root.mkdir(parents=True, mode=0o700)
    authority, database_path = _load_authority(authority_root)
    rows, provenance = _authority_rows(database_path)
    bm25 = _build_bm25(rows, output_root, authority)
    graph = build_graph(authority_root, output_root / "graph")

    embedding, transport = _fake_embedding_adapter()
    chunk_inputs = [
        EmbeddingInput(str(row["chunk_id"]), str(row["text"]), len(str(row["text"])))
        for row in rows
    ]
    entity_inputs = [
        EmbeddingInput(
            str(entity["entity_id"]),
            str(entity["canonical_name"]),
            len(str(entity["canonical_name"])),
        )
        for entity in graph["entities"]
    ]
    chunk_result = embedding.embed_build(chunk_inputs)
    entity_result = embedding.embed_entity(entity_inputs)
    if chunk_result.identity_sha256 != entity_result.identity_sha256:
        raise CandidateBuildError("chunk and entity embedding identities differ")
    chunk_vectors = chunk_result.by_id()
    entity_vectors = entity_result.by_id()
    if set(chunk_vectors) != set(provenance):
        raise CandidateBuildError("chunk embeddings do not exactly cover SQLite authority")
    graph_entity_ids = {str(entity["entity_id"]) for entity in graph["entities"]}
    if set(entity_vectors) != graph_entity_ids:
        raise CandidateBuildError("entity embeddings do not exactly cover the scoped graph")

    data_release_id = local_data_release_id(
        str(authority["database"]["sha256"]), embedding.identity.sha256
    )
    authority_manifest_sha256 = sha256_file(authority_root / "authority-manifest.json")
    chunking_identity_sha256 = hashlib.sha256(
        json.dumps(
            {
                "chunking_policy": authority["build"]["chunking_policy"],
                "extractor_version": authority["build"]["extractor_version"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    vector_contract = LocalVectorContract(
        approved_data_parent=output_root,
        data_root=(output_root / "local-vector").resolve(),
        data_release_id=data_release_id,
        authority_manifest_sha256=authority_manifest_sha256,
        chunking_identity_sha256=chunking_identity_sha256,
        embedding_identity_sha256=embedding.identity.sha256,
        dimension=embedding.identity.dimension,
        metric="cosine",
        schema_version="kg-local-vector-schema-v1",
        chunk_index_name="chunk-index",
        entity_index_name="entity-index",
        top_k_max=50,
        max_vectors_per_index=max(100000, len(rows) + len(graph_entity_ids)),
        metadata_allowlist={
            "chunk": ("authority_release_id", "content_type"),
            "entity": ("authority_release_id", "entity_type"),
        },
    )
    vector_adapter = LocalVectorStoreAdapter(vector_contract)
    entity_by_id = {str(entity["entity_id"]): entity for entity in graph["entities"]}
    vector_receipt = vector_adapter.build_candidate(
        chunk_records=[
            VectorRecord(
                object_id=str(row["chunk_id"]),
                vector=chunk_vectors[str(row["chunk_id"])],
                metadata={
                    "authority_release_id": authority["release_id"],
                    "content_type": str(row["content_type"]),
                },
            )
            for row in rows
        ],
        entity_records=[
            VectorRecord(
                object_id=entity_id,
                vector=entity_vectors[entity_id],
                metadata={
                    "authority_release_id": authority["release_id"],
                    "entity_type": str(entity_by_id[entity_id]["entity_type"]),
                },
            )
            for entity_id in sorted(graph_entity_ids)
        ],
        expected_ids={
            "chunk": [str(row["chunk_id"]) for row in rows],
            "entity": sorted(graph_entity_ids),
        },
    )
    fake_embedding_manifest = {
        "schema_version": "cloud-v2-fake-embedding-manifest-v1",
        "status": "offline-test-only",
        "policy_version": FAKE_PROVIDER_POLICY_VERSION,
        "identity": embedding.identity.manifest(),
        "identity_sha256": embedding.identity.sha256,
        "policy": embedding.policy.manifest(),
        "policy_sha256": embedding.policy.sha256,
        "network_implementation": False,
        "real_data_externalized": False,
        "transport_call_count": transport.call_count,
        "chunk_ledger": _ledger_summary(chunk_result),
        "entity_ledger": _ledger_summary(entity_result),
    }
    write_json(output_root / "fake-embedding-manifest.json", fake_embedding_manifest)
    fake_embedding_manifest_sha256 = sha256_file(
        output_root / "fake-embedding-manifest.json"
    )
    derived_manifest = {
        "schema_version": DERIVED_SCHEMA_VERSION,
        "status": "candidate",
        "authority_release_id": authority["release_id"],
        "authority_database_sha256": authority["database"]["sha256"],
        "bm25_manifest_sha256": bm25["manifest_sha256"],
        "graph_manifest_sha256": graph["manifest_sha256"],
        "embedding_identity_sha256": embedding.identity.sha256,
        "embedding_policy_sha256": embedding.policy.sha256,
        "fake_embedding_manifest_sha256": fake_embedding_manifest_sha256,
        "local_vector": {
            "data_release_id": data_release_id,
            "manifest_sha256": vector_receipt.manifest_sha256,
            "authority_manifest_sha256": authority_manifest_sha256,
            "chunking_identity_sha256": chunking_identity_sha256,
            "chunk_count": vector_receipt.chunk_count,
            "entity_count": vector_receipt.entity_count,
            "engine": "usearch",
            "engine_version": "2.26.2",
        },
        "gates": {
            "sqlite_chunk_backfill_missing": 0,
            "graph_entity_backfill_missing": 0,
            "unknown_vector_id_count": 0,
            "cross_release_id_count": 0,
            "network_call_count": 0,
        },
    }
    write_json(output_root / "derived-candidate-manifest.json", derived_manifest)
    derived_manifest["manifest_sha256"] = sha256_file(
        output_root / "derived-candidate-manifest.json"
    )
    return derived_manifest


def build_derived_candidate(
    authority_root: str | Path,
    candidate_root: str | Path,
) -> dict[str, Any]:
    actions = _require_formal_candidate_builder_bootstrap_context()
    return actions[3](authority_root, candidate_root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    return parser


def _main_impl(
    argv: Sequence[str] | None = None,
    *,
    _action_closure: tuple[object, ...] | None = None,
) -> int:
    actions = (
        (_parser, _build_derived_candidate_impl)
        if _action_closure is None
        else _action_closure
    )
    if (
        not isinstance(actions, tuple)
        or len(actions) != 2
        or any(not callable(action) for action in actions)
    ):
        raise CandidateBuildError("candidate builder CLI action closure is malformed")
    parser_action, build_action = actions
    args = parser_action().parse_args(argv)
    result = build_action(args.authority_root, args.candidate_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        actions = _require_formal_candidate_builder_bootstrap_context()
    except CandidateBuildError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return actions[1](
        argv,
        _action_closure=(actions[4], actions[3]),
    )


if __name__ == "__main__":
    raise SystemExit(main())
