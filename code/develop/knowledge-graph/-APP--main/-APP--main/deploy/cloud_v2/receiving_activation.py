#!/usr/bin/env python3
"""Materialize a hash-bound active tree from receiving-team evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


CONFIG_SCHEMA = "cloud-v2-receiving-activation-config-v1"
RECEIPT_SCHEMA = "cloud-v2-receiving-activation-receipt-v1"
FINAL_VERIFICATION_SCHEMA = "knowledge-qa-final-delivery-verification-receipt-v1"
USEARCH_RECEIPT_SCHEMA = "knowledge-qa-usearch-load-receipt-v1"
QA_RECEIPT_SCHEMA = "knowledge-qa-candidate-qa-receipt-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REQUIRED_QA_CATEGORIES = frozenset(
    {"regulation", "definition", "question_bank_exact", "theory_exam"}
)


class ActivationError(RuntimeError):
    """Raised when receiving evidence cannot authorize activation."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ActivationError(f"{field}_invalid")
    return value


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ActivationError(f"{field}_must_be_object")
    return value


def _strict_json(path: Path, field: str) -> dict[str, Any]:
    _require_regular_file(path, field)

    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ActivationError(f"{field}_duplicate_json_key")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ActivationError(f"{field}_non_finite_json")
            ),
        )
    except ActivationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ActivationError(f"{field}_invalid_json") from exc
    if not isinstance(value, dict):
        raise ActivationError(f"{field}_must_be_object")
    return value


def _require_regular_file(path: Path, field: str) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise ActivationError(f"{field}_unavailable") from exc
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise ActivationError(f"{field}_not_regular")


def _absolute_directory(value: Any, field: str, *, must_exist: bool) -> Path:
    if not isinstance(value, str) or not value:
        raise ActivationError(f"{field}_invalid")
    path = Path(value)
    if not path.is_absolute():
        raise ActivationError(f"{field}_not_absolute")
    if must_exist:
        try:
            path = path.resolve(strict=True)
        except OSError as exc:
            raise ActivationError(f"{field}_unavailable") from exc
        if not path.is_dir() or path.is_symlink():
            raise ActivationError(f"{field}_invalid_directory")
        return path
    parent = path.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise ActivationError(f"{field}_parent_invalid")
    return parent / path.name


def _absolute_new_file(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ActivationError(f"{field}_invalid")
    path = Path(value)
    if not path.is_absolute():
        raise ActivationError(f"{field}_not_absolute")
    if path.exists() or path.is_symlink():
        raise ActivationError(f"{field}_already_exists")
    parent = path.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise ActivationError(f"{field}_parent_invalid")
    return parent / path.name


def _relative(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ActivationError(f"{field}_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ActivationError(f"{field}_invalid")
    return path.as_posix()


def _under(root: Path, relative: str, field: str) -> Path:
    normalized = _relative(relative, field)
    candidate = root.joinpath(*PurePosixPath(normalized).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ActivationError(f"{field}_unavailable") from exc
    if root not in resolved.parents:
        raise ActivationError(f"{field}_outside_root")
    _require_regular_file(resolved, field)
    return resolved


def _verify_sha(path: Path, expected: Any, field: str) -> str:
    expected_sha = _require_sha(expected, f"{field}_sha256")
    actual = _sha256_file(path)
    if actual != expected_sha:
        raise ActivationError(f"{field}_hash_mismatch")
    return actual


def _verify_release_sums(root: Path) -> None:
    sums_path = root / "SHA256SUMS"
    _require_regular_file(sums_path, "sha256sums")
    seen: set[str] = set()
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ActivationError("sha256sums_line_invalid")
        expected, relative = match.groups()
        relative = _relative(relative, "sha256sums_path")
        if relative in seen:
            raise ActivationError("sha256sums_duplicate_path")
        seen.add(relative)
        _verify_sha(_under(root, relative, "release_file"), expected, "release_file")
    if not seen:
        raise ActivationError("sha256sums_empty")


def _verify_final_receipt(
    receipt: Mapping[str, Any], release_root: Path, inputs: Mapping[str, Path]
) -> None:
    if receipt.get("schema_version") != FINAL_VERIFICATION_SCHEMA:
        raise ActivationError("final_verification_schema_mismatch")
    if receipt.get("status") != "passed" or receipt.get("ok") is not True:
        raise ActivationError("final_verification_not_passed")
    if receipt.get("errors") != []:
        raise ActivationError("final_verification_has_errors")
    if receipt.get("release_root") != str(release_root):
        raise ActivationError("final_verification_release_root_mismatch")
    for name, field in (
        ("suite", "suite_manifest_sha256"),
        ("source_data", "data_release_manifest_sha256"),
        ("source_runtime", "runtime_manifest_sha256"),
        ("sha256sums", "sha256sums_sha256"),
    ):
        _verify_sha(inputs[name], receipt.get(field), f"final_verification_{name}")
    _verify_sha(
        release_root / "verify_final_delivery.py",
        receipt.get("verifier_sha256"),
        "final_verification_verifier",
    )


def _verify_neo4j_receipt(
    receipt: Mapping[str, Any], graph: Mapping[str, Any], authority: Mapping[str, Any]
) -> None:
    if receipt.get("schema_version") != "cloud-scoped-neo4j-import-receipt-v1":
        raise ActivationError("neo4j_receipt_schema_mismatch")
    if receipt.get("status") != "candidate-imported":
        raise ActivationError("neo4j_candidate_not_imported")
    if receipt.get("active_switched") is not False:
        raise ActivationError("neo4j_receipt_pre_switched")
    database = _require_mapping(authority.get("database"), "authority_database")
    graph_file = _require_mapping(graph.get("graph"), "graph_file")
    expected = {
        "authority_database_sha256": database.get("sha256"),
        "authority_release_id": authority.get("release_id"),
        "graph_release_id": graph.get("release_id"),
        "graph_sha256": graph_file.get("sha256"),
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ActivationError(f"neo4j_{field}_mismatch")
    graph_counts = _require_mapping(graph.get("counts"), "graph_counts")
    counts = _require_mapping(receipt.get("counts"), "neo4j_counts")
    expected_counts = {
        "documents": graph_counts.get("document_nodes"),
        "chunks": graph_counts.get("chunk_nodes"),
        "entities": graph_counts.get("entity_nodes"),
        "has_chunk": graph_counts.get("chunk_nodes"),
        "mentions": graph_counts.get("edges") - graph_counts.get("chunk_nodes"),
    }
    if counts != expected_counts:
        raise ActivationError("neo4j_count_mismatch")


def _verify_usearch_receipt(
    receipt: Mapping[str, Any], vector: Mapping[str, Any], vector_sha: str
) -> None:
    if receipt.get("schema_version") != USEARCH_RECEIPT_SCHEMA:
        raise ActivationError("usearch_receipt_schema_mismatch")
    if receipt.get("status") != "passed" or receipt.get("read_only") is not True:
        raise ActivationError("usearch_load_not_passed")
    identity = _require_mapping(vector.get("identity"), "vector_identity")
    if receipt.get("manifest_sha256") != vector_sha:
        raise ActivationError("usearch_manifest_hash_mismatch")
    expected_identity = {
        "engine": identity.get("engine"),
        "engine_version": identity.get("engine_version"),
        "dimension": identity.get("dimension"),
        "vector_release_id": identity.get("data_release_id"),
    }
    for field, value in expected_identity.items():
        if receipt.get(field) != value:
            raise ActivationError(f"usearch_{field}_mismatch")
    indexes = _require_mapping(vector.get("indexes"), "vector_indexes")
    receipt_indexes = _require_mapping(receipt.get("indexes"), "usearch_indexes")
    if set(receipt_indexes) != {"chunk", "entity"}:
        raise ActivationError("usearch_index_set_mismatch")
    for kind in ("chunk", "entity"):
        expected = _require_mapping(indexes.get(kind), f"vector_{kind}")
        actual = _require_mapping(receipt_indexes.get(kind), f"usearch_{kind}")
        for field in ("index_sha256", "object_count"):
            if actual.get(field) != expected.get(field):
                raise ActivationError(f"usearch_{kind}_{field}_mismatch")


def _qa_metrics(
    receipt: Mapping[str, Any], suite_sha: str, data_release_id: str
) -> dict[str, Any]:
    if receipt.get("schema_version") != QA_RECEIPT_SCHEMA:
        raise ActivationError("qa_receipt_schema_mismatch")
    if receipt.get("status") != "passed" or receipt.get("false_verified_count") != 0:
        raise ActivationError("candidate_qa_not_passed")
    if receipt.get("suite_manifest_sha256") != suite_sha:
        raise ActivationError("qa_suite_hash_mismatch")
    if receipt.get("data_release_id") != data_release_id:
        raise ActivationError("qa_data_release_mismatch")
    raw_cases = receipt.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ActivationError("qa_cases_missing")
    categories: set[str] = set()
    routes: Counter[str] = Counter()
    degraded = 0
    evidence_bound = 0
    for raw in raw_cases:
        case = _require_mapping(raw, "qa_case")
        if case.get("passed") is not True or case.get("http_status") != 200:
            raise ActivationError("qa_case_failed")
        category = case.get("category")
        route = case.get("route")
        if not isinstance(category, str) or not isinstance(route, str) or not route:
            raise ActivationError("qa_case_shape_invalid")
        categories.add(category)
        routes[route] += 1
        degraded += int(case.get("degraded") is True)
        evidence_bound += int(
            isinstance(case.get("evidence_count"), int)
            and case.get("evidence_count") > 0
        )
    if not REQUIRED_QA_CATEGORIES.issubset(categories):
        raise ActivationError("qa_category_coverage_incomplete")
    negative = receipt.get("negative_cases")
    if not isinstance(negative, list) or len(negative) < 2:
        raise ActivationError("qa_negative_coverage_incomplete")
    for raw in negative:
        case = _require_mapping(raw, "qa_negative_case")
        if case.get("passed") is not True or case.get("http_status") not in {400, 403, 404}:
            raise ActivationError("qa_negative_case_failed")
    return {
        "request_count": len(raw_cases),
        "route_counts": dict(sorted(routes.items())),
        "degraded_count": degraded,
        "evidence_bound_count": evidence_bound,
        "false_verified_count": 0,
    }


def _runtime_file_set(root: Path) -> tuple[str, int]:
    records: list[dict[str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ActivationError("runtime_code_symlink_forbidden")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256_file(path),
            }
        )
    if not records:
        raise ActivationError("runtime_code_empty")
    return _sha256_bytes(_canonical_json(records)), len(records)


def _active_vector_manifest(
    vector: Mapping[str, Any], authority_manifest_sha256: str
) -> dict[str, Any]:
    active = dict(vector)
    identity = dict(_require_mapping(vector.get("identity"), "vector_identity"))
    identity["authority_manifest_sha256"] = _require_sha(
        authority_manifest_sha256, "active_authority_manifest_sha256"
    )
    active["identity"] = identity
    return active


def _copy_file(source: Path, target: Path) -> str:
    _require_regular_file(source, "copy_source")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists() or target.is_symlink():
        raise ActivationError("copy_target_exists")
    with source.open("rb") as source_stream, target.open("xb") as target_stream:
        shutil.copyfileobj(source_stream, target_stream, 1024 * 1024)
        target_stream.flush()
        os.fsync(target_stream.fileno())
    if _sha256_file(source) != _sha256_file(target):
        raise ActivationError("copy_hash_mismatch")
    return _sha256_file(target)


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = _canonical_json(value)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return _sha256_bytes(raw)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, value: object, *, mode: int) -> str:
    if path.exists() or path.is_symlink():
        raise ActivationError("atomic_json_target_exists")
    temporary = path.parent / f".{path.name}.staging-{os.getpid()}-{secrets.token_hex(8)}"
    try:
        digest = _write_json(temporary, value)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
        return digest
    finally:
        if temporary.exists():
            temporary.unlink()


def _freeze_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            raise ActivationError("active_tree_symlink_forbidden")
        os.chmod(path, 0o500 if path.is_dir() else 0o400)
    os.chmod(root, 0o500)


def _load_config(path: Path) -> dict[str, Any]:
    config = _strict_json(path, "config")
    expected_fields = {
        "schema_version",
        "release_root",
        "runtime_code_root",
        "active_root",
        "receipt_path",
        "activated_at",
        "evidence",
    }
    if set(config) != expected_fields or config.get("schema_version") != CONFIG_SCHEMA:
        raise ActivationError("config_shape_or_schema_mismatch")
    return config


def materialize(config_path: str | Path) -> dict[str, Any]:
    if os.name != "posix":
        raise ActivationError("posix_runtime_required")
    if os.geteuid() != 0:
        raise ActivationError("root_execution_required")
    config_file = Path(config_path).resolve(strict=True)
    config = _load_config(config_file)
    release_root = _absolute_directory(config["release_root"], "release_root", must_exist=True)
    runtime_code_root = _absolute_directory(
        config["runtime_code_root"], "runtime_code_root", must_exist=True
    )
    active_root = _absolute_directory(config["active_root"], "active_root", must_exist=False)
    if active_root.exists() or active_root.is_symlink():
        raise ActivationError("active_root_already_exists")
    active_parent = active_root.parent.resolve(strict=True)
    if active_parent.is_symlink() or not active_parent.is_dir():
        raise ActivationError("active_parent_invalid")
    receipt_path = _absolute_new_file(config["receipt_path"], "receipt_path")
    activated_at = config.get("activated_at")
    if not isinstance(activated_at, str) or RFC3339_RE.fullmatch(activated_at) is None:
        raise ActivationError("activated_at_invalid")
    evidence_config = _require_mapping(config.get("evidence"), "evidence")
    if set(evidence_config) != {"final_verification", "neo4j_import", "usearch_load", "candidate_qa"}:
        raise ActivationError("evidence_set_mismatch")
    evidence_paths = {
        name: Path(value).resolve(strict=True) for name, value in evidence_config.items()
    }
    evidence = {
        name: _strict_json(path, f"evidence_{name}")
        for name, path in evidence_paths.items()
    }

    _verify_release_sums(release_root)
    vector_manifest_path = next(
        iter(
            sorted(
                release_root.glob(
                    "server-runtime/data/derived/vector/local-vector/candidate/*/local_vector_manifest.json"
                )
            )
        ),
        None,
    )
    if vector_manifest_path is None:
        raise ActivationError("vector_manifest_missing")
    inputs = {
        "suite": release_root / "SUITE_MANIFEST.json",
        "source_data": release_root / "server-runtime/data-release-manifest.json",
        "source_runtime": release_root / "server-runtime/runtime-code-manifest.json",
        "sha256sums": release_root / "SHA256SUMS",
        "authority": release_root / "server-runtime/data/authority/authority-manifest.json",
        "authority_database": release_root / "server-runtime/data/authority/rag_chunks.db",
        "bm25": release_root / "server-runtime/data/derived/bm25-manifest.json",
        "bm25_index": release_root / "server-runtime/data/derived/bm25.sqlite3",
        "vector": vector_manifest_path,
        "graph": release_root / "server-runtime/data/derived/graph/graph-manifest.json",
        "graph_data": release_root / "server-runtime/data/derived/graph/scoped-graph.jsonl",
        "app_host_contract": release_root / "contracts/01-DELIVERY-CONTRACT.md",
        "server_model_set": release_root / "server-runtime/server-answer-model-set-manifest.json",
        "embedding_manifest": release_root / "server-runtime/embedding-manifest.json",
        "operator_manifest": release_root / "operator-companion/OPERATOR_MANIFEST.sha256",
    }
    for name, path in inputs.items():
        _require_regular_file(path, name)
    suite = _strict_json(inputs["suite"], "suite")
    source_data = _strict_json(inputs["source_data"], "source_data")
    source_runtime = _strict_json(inputs["source_runtime"], "source_runtime")
    authority = _strict_json(inputs["authority"], "authority")
    bm25 = _strict_json(inputs["bm25"], "bm25")
    vector = _strict_json(inputs["vector"], "vector")
    graph = _strict_json(inputs["graph"], "graph")
    if suite.get("schema_version") != "knowledge-qa-suite-manifest-v1" or suite.get("status") != "stop_b_offline_handoff_ready":
        raise ActivationError("source_suite_not_handoff_ready")
    if source_data.get("schema_version") != "knowledge-qa-data-release-manifest-v1" or source_data.get("status") != "passed":
        raise ActivationError("source_data_manifest_not_passed")
    if source_runtime.get("schema_version") != "runtime-code-manifest-v1" or source_runtime.get("status") != "passed":
        raise ActivationError("source_runtime_manifest_not_passed")
    for name, manifest, schema in (
        ("authority", authority, "cloud-rag-authority-v1"),
        ("bm25", bm25, "cloud-v2-sqlite-fts5-trigram-v1"),
        ("graph", graph, "cloud-scoped-graph-v1"),
    ):
        if manifest.get("schema_version") != schema or manifest.get("status") != "candidate":
            raise ActivationError(f"{name}_candidate_manifest_invalid")
    if vector.get("manifest_schema_version") != "kg-local-vector-manifest-v2":
        raise ActivationError("vector_manifest_schema_mismatch")
    authority_database = _require_mapping(authority.get("database"), "authority_database")
    _verify_sha(inputs["authority_database"], authority_database.get("sha256"), "authority_database")
    _verify_sha(inputs["bm25_index"], _require_mapping(bm25.get("index"), "bm25_index").get("sha256"), "bm25_index")
    _verify_sha(inputs["graph_data"], _require_mapping(graph.get("graph"), "graph_file").get("sha256"), "graph_data")
    vector_sha = _sha256_file(inputs["vector"])
    vector_dir = inputs["vector"].parent
    vector_indexes = _require_mapping(vector.get("indexes"), "vector_indexes")
    index_sources: dict[str, Path] = {}
    for kind in ("chunk", "entity"):
        item = _require_mapping(vector_indexes.get(kind), f"vector_{kind}")
        index_sources[kind] = _under(vector_dir, item.get("file"), f"vector_{kind}_file")
        _verify_sha(index_sources[kind], item.get("index_sha256"), f"vector_{kind}")

    suite_sha = _sha256_file(inputs["suite"])
    _verify_final_receipt(evidence["final_verification"], release_root, inputs)
    _verify_neo4j_receipt(evidence["neo4j_import"], graph, authority)
    _verify_usearch_receipt(evidence["usearch_load"], vector, vector_sha)
    data_release_id = authority.get("release_id")
    if not isinstance(data_release_id, str) or not data_release_id:
        raise ActivationError("data_release_id_invalid")
    quality_metrics = _qa_metrics(evidence["candidate_qa"], suite_sha, data_release_id)
    runtime_file_set_sha, runtime_file_count = _runtime_file_set(runtime_code_root)
    vector_identity = _require_mapping(vector.get("identity"), "vector_identity")
    vector_release_id = vector_identity.get("data_release_id")
    graph_release_id = graph.get("release_id")
    suite_release_id = suite.get("suite_id")
    if not all(isinstance(value, str) and value for value in (vector_release_id, graph_release_id, suite_release_id)):
        raise ActivationError("release_identity_missing")

    staging = active_parent / f".{active_root.name}.staging-{os.getpid()}-{secrets.token_hex(8)}"
    staging.mkdir(mode=0o700)
    try:
        paths = {
            "suite_manifest": "manifests/suite.json",
            "data_release_manifest": "manifests/data-release.json",
            "runtime_manifest": "manifests/runtime.json",
            "authority_manifest": "authority/authority-manifest.json",
            "authority_database": "authority/rag_chunks.db",
            "bm25_manifest": "bm25/bm25-manifest.json",
            "bm25_index": "bm25/bm25.sqlite3",
            "local_vector_manifest": f"vector/{vector_release_id}/local_vector_manifest.json",
            "local_vector_chunk_index": f"vector/{vector_release_id}/chunk-index/index.usearch",
            "local_vector_entity_index": f"vector/{vector_release_id}/entity-index/index.usearch",
            "graph_manifest": "graph/graph-manifest.json",
            "graph_data": "graph/scoped-graph.jsonl",
            "quality_summary": "telemetry/quality-summary.json",
        }
        hashes: dict[str, str] = {}
        active_authority = dict(authority)
        active_authority["status"] = "active"
        hashes["authority_manifest"] = _write_json(staging / paths["authority_manifest"], active_authority)
        hashes["authority_database"] = _copy_file(inputs["authority_database"], staging / paths["authority_database"])
        active_bm25 = dict(bm25)
        active_bm25["status"] = "active"
        hashes["bm25_manifest"] = _write_json(staging / paths["bm25_manifest"], active_bm25)
        hashes["bm25_index"] = _copy_file(inputs["bm25_index"], staging / paths["bm25_index"])
        active_vector = _active_vector_manifest(vector, hashes["authority_manifest"])
        hashes["local_vector_manifest"] = _write_json(
            staging / paths["local_vector_manifest"], active_vector
        )
        hashes["local_vector_chunk_index"] = _copy_file(index_sources["chunk"], staging / paths["local_vector_chunk_index"])
        hashes["local_vector_entity_index"] = _copy_file(index_sources["entity"], staging / paths["local_vector_entity_index"])
        active_graph = dict(graph)
        active_graph["status"] = "active"
        hashes["graph_manifest"] = _write_json(staging / paths["graph_manifest"], active_graph)
        hashes["graph_data"] = _copy_file(inputs["graph_data"], staging / paths["graph_data"])
        active_runtime = {
            "schema_version": "cloud-v2-runtime-code-manifest-v1",
            "status": "active",
            "file_set_sha256": runtime_file_set_sha,
            "file_count": runtime_file_count,
            "image_digest": f"sha256:{runtime_file_set_sha}",
            "runtime_kind": "filesystem-tree",
            "source_manifest_sha256": _sha256_file(inputs["source_runtime"]),
            "activated_at": activated_at,
        }
        hashes["runtime_manifest"] = _write_json(staging / paths["runtime_manifest"], active_runtime)
        active_data = {
            "schema_version": "cloud-v2-data-release-manifest-v1",
            "status": "active",
            "release_id": data_release_id,
            "active_switch_authorized": True,
            "real_embedding_rebuild_required_after_stop_b": False,
            "authority": {
                "manifest_path": paths["authority_manifest"],
                "manifest_sha256": hashes["authority_manifest"],
                "database_path": paths["authority_database"],
                "database_sha256": hashes["authority_database"],
            },
            "derived": {
                "bm25_manifest_path": paths["bm25_manifest"],
                "bm25_manifest_sha256": hashes["bm25_manifest"],
                "bm25_index_path": paths["bm25_index"],
                "bm25_index_sha256": hashes["bm25_index"],
                "local_vector_manifest_path": paths["local_vector_manifest"],
                "local_vector_manifest_sha256": hashes["local_vector_manifest"],
                "graph_manifest_path": paths["graph_manifest"],
                "graph_manifest_sha256": hashes["graph_manifest"],
                "graph_data_path": paths["graph_data"],
                "graph_data_sha256": hashes["graph_data"],
            },
        }
        hashes["data_release_manifest"] = _write_json(staging / paths["data_release_manifest"], active_data)
        quality = {
            "schema_version": "cloud-v2-sanitized-quality-summary-v1",
            "status": "active",
            "suite_release_id": suite_release_id,
            "data_release_id": data_release_id,
            "windows": {window: dict(quality_metrics) for window in ("1h", "24h", "7d", "30d")},
        }
        hashes["quality_summary"] = _write_json(staging / paths["quality_summary"], quality)
        active_suite = {
            "schema_version": "cloud-v2-suite-manifest-v1",
            "status": "active",
            "suite_release_id": suite_release_id,
            "activated_at": activated_at,
            "phase_state": {"runtime_activation_authorized": True, "product_accepted": False},
            "identities": {
                "data_release_manifest_sha256": hashes["data_release_manifest"],
                "runtime_code_manifest_sha256": hashes["runtime_manifest"],
                "authority_manifest_sha256": hashes["authority_manifest"],
                "authority_database_sha256": hashes["authority_database"],
                "bm25_manifest_sha256": hashes["bm25_manifest"],
                "bm25_index_sha256": hashes["bm25_index"],
                "local_vector_manifest_sha256": hashes["local_vector_manifest"],
                "graph_manifest_sha256": hashes["graph_manifest"],
                "graph_data_sha256": hashes["graph_data"],
                "operator_manifest_sha256": _sha256_file(inputs["operator_manifest"]),
                "app_host_contract_sha256": _sha256_file(inputs["app_host_contract"]),
                "server_model_set_sha256": _sha256_file(inputs["server_model_set"]),
                "embedding_manifest_sha256": _sha256_file(inputs["embedding_manifest"]),
            },
            "source_delivery": {
                "suite_manifest_sha256": suite_sha,
                "data_release_manifest_sha256": _sha256_file(inputs["source_data"]),
                "runtime_manifest_sha256": _sha256_file(inputs["source_runtime"]),
            },
        }
        hashes["suite_manifest"] = _write_json(staging / paths["suite_manifest"], active_suite)
        result = {
            "schema_version": RECEIPT_SCHEMA,
            "status": "active-materialized",
            "activated_at": activated_at,
            "active_root": str(active_root),
            "suite_release_id": suite_release_id,
            "data_release_id": data_release_id,
            "local_vector_release_id": vector_release_id,
            "graph_release_id": graph_release_id,
            "runtime_code_file_set_sha256": runtime_file_set_sha,
            "operator_companion_sha256": _sha256_file(inputs["operator_manifest"]),
            "files": {
                name: {"path": paths[name], "sha256": hashes[name]}
                for name in sorted(paths)
            },
            "evidence": {
                name: {"path": str(path), "sha256": _sha256_file(path)}
                for name, path in sorted(evidence_paths.items())
            },
            "source_suite_manifest_sha256": suite_sha,
            "product_accepted": False,
        }
        activation_receipt_sha = _write_json(
            staging / "activation/receipt.json", result
        )
        _fsync_directory(staging)
        _freeze_tree(staging)
        os.replace(staging, active_root)
        _fsync_directory(active_parent)
    except Exception:
        if staging.exists():
            os.chmod(staging, 0o700)
            for path in staging.rglob("*"):
                try:
                    os.chmod(path, 0o700 if path.is_dir() else 0o600)
                except OSError:
                    pass
            shutil.rmtree(staging)
        raise

    receipt_sha = _atomic_write_json(receipt_path, result, mode=0o400)
    if receipt_sha != activation_receipt_sha:
        raise ActivationError("activation_receipt_copy_hash_mismatch")
    output = dict(result)
    output["receipt_path"] = str(receipt_path)
    output["receipt_sha256"] = receipt_sha
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = materialize(args.config)
    except (ActivationError, OSError, ValueError) as exc:
        print(_canonical_json({"ok": False, "error": str(exc)}).decode("ascii"))
        return 1
    print(_canonical_json({"ok": True, **result}).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
