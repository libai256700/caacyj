#!/usr/bin/env python3

from __future__ import annotations

import base64
import contextlib
import hashlib
import inspect
import io
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path, PurePosixPath
from typing import Mapping
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "deploy"))

import pipeline.production_embedding_candidate as CANDIDATE
import pipeline.production_embedding_bootstrap as BOOTSTRAP
from deploy.cloud_v2.authority_builder import (
    AUTHORITY_SCHEMA_SQL as BUILDER_AUTHORITY_SCHEMA_SQL,
)
from pipeline.production_embedding_candidate import (
    ProductionEmbeddingCandidateConfig,
    ProductionEmbeddingCandidateConfigError,
    ProductionEmbeddingCandidateError,
    build_production_embedding_candidate,
    local_data_release_id,
    materialize_production_vector_build_contract,
    validate_production_embedding_candidate,
)
# Semantic unit tests exercise the private implementations. The public names
# remain reserved for exact-release bootstrap and bypass tests below.
PUBLIC_MATERIALIZE = materialize_production_vector_build_contract
PUBLIC_VALIDATE = validate_production_embedding_candidate
PUBLIC_BUILD = build_production_embedding_candidate
materialize_production_vector_build_contract = (
    CANDIDATE._materialize_production_vector_build_contract_impl
)
validate_production_embedding_candidate = (
    CANDIDATE._validate_production_embedding_candidate_impl
)
build_production_embedding_candidate = (
    CANDIDATE._build_production_embedding_candidate_impl
)

from pipeline.provider_bootstrap import (
    ProviderApprovalError,
    ProviderBootstrapError,
    ProviderRuntimeConfig,
)
from rag_store.embedding_adapter import EmbeddingIdentity, EmbeddingPolicy
from rag_store.provider_http_transport import (
    ProviderHTTPTransport as RealProviderHTTPTransport,
)
from rag_store.runtime_sqlite_reader import (
    AUTHORITY_SCHEMA_SQL as RUNTIME_AUTHORITY_SCHEMA_SQL,
    ReadOnlyAuthorityReader,
    ReadOnlySQLiteError,
    SQLiteSemanticValidationError,
)
from rag_store.scoped_graph_contract import (
    GRAPH_IMPORT_SCHEMA_VERSION,
    NEO4J_DRIVER_VERSION,
)
from rag_store.server_answer_model import ServerAnswerChannel


SCHEMA_PATH = (
    REPO_ROOT / "deploy/pipeline/production_embedding_config.schema.json"
)
R9_SOURCE_SCOPE = {
    "allowlist_sha256": (
        "a5efe7537d9ab9de1624bf40e5cb944f95c35fb0252c04927f73886c1bb5d64f"
    ),
    "approved_redacted_source_count": 7,
    "candidate_id": "revision-a-r9",
    "schema_version": "cloud-v2-source-scope-v1",
    "source_count": 35,
    "source_dlp_receipt_sha256": (
        "ee460cfd8d35a6ace33d87c6f2f313e68e1ef6b5c5ceaa8b29fcb70950219123"
    ),
    "source_manifest_sha256": (
        "9e0f9018c9a72f2a99c19a7c6b2362cb49154233b770c8f7c41af0b48a3aa8fe"
    ),
    "stop_a_receipt_sha256": (
        "4515475c1e89b85aea91eb912d238d0eb63776f82b75468ac4aecd8206c4ab6c"
    ),
    "unchanged_source_count": 28,
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def record_set_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value) + b"\n").hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class FakeEmbeddingExecutor:
    """Pickleable executor that forbids socket access in the child process."""

    def __init__(
        self,
        *,
        dimension: int,
        model: str,
        model_version: str,
        identity_sha256: str,
        secret: str,
        call_log: Path,
        partial_purpose: str | None = None,
    ) -> None:
        self.dimension = dimension
        self.model = model
        self.model_version = model_version
        self.identity_sha256 = identity_sha256
        self.secret = secret
        self.call_log = call_log
        self.partial_purpose = partial_purpose

    def __call__(self, **request):
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network forbidden in fake executor"),
        ):
            body = json.loads(request["body"])
            if body["model"] != self.model:
                raise AssertionError("model binding mismatch")
            if body["model_version"] != self.model_version:
                raise AssertionError("model version binding mismatch")
            if body["embedding_identity_sha256"] != self.identity_sha256:
                raise AssertionError("identity binding mismatch")
            if request["headers"]["Authorization"] != f"Bearer {self.secret}":
                raise AssertionError("secret header mismatch")
            if self.secret.encode("ascii") in request["body"]:
                raise AssertionError("secret entered request body")
            purpose = body["purpose"]
            with self.call_log.open("a", encoding="ascii") as handle:
                handle.write(purpose + "\n")
            vectors = []
            for index, _item in enumerate(body["inputs"]):
                values = [0.0] * self.dimension
                values[index % self.dimension] = 1.0
                vectors.append({"embedding": values})
            if purpose == self.partial_purpose:
                vectors = vectors[:-1]
            return (
                200,
                {"Content-Type": "application/json"},
                canonical_bytes({"data": vectors}),
            )


class RuntimeDistributionClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="kg-production-runtime-closure-test-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.installation_root = self.root / "runtime-venv"
        self.library_root = self.installation_root / "lib/python3.14/site-packages"
        self.server_runtime = self.root / "server-runtime"
        self.library_root.mkdir(parents=True)
        self.server_runtime.mkdir()

    @staticmethod
    def _record_hash(payload: bytes) -> str:
        encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
        return "sha256=" + encoded.rstrip(b"=").decode("ascii")

    def _target(self, relative: str) -> Path:
        return Path(
            os.path.abspath(
                self.library_root.joinpath(*PurePosixPath(relative).parts)
            )
        )

    def _write_requirements(self, *requirements: str) -> None:
        (self.server_runtime / "requirements.lock").write_text(
            "".join(requirement + "\n" for requirement in requirements),
            encoding="ascii",
        )

    def _write_distribution(
        self,
        name: str,
        version: str,
        files: Mapping[str, bytes] | None = None,
    ) -> Path:
        dist_info = f"{name}-{version}.dist-info"
        metadata_relative = f"{dist_info}/METADATA"
        record_relative = f"{dist_info}/RECORD"
        owned = {
            metadata_relative: f"Name: {name}\nVersion: {version}\n".encode("utf-8"),
            **dict(files or {}),
        }
        rows = []
        for relative, payload in sorted(owned.items()):
            target = self._target(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                self.assertEqual(payload, target.read_bytes())
            else:
                target.write_bytes(payload)
            rows.append(f"{relative},{self._record_hash(payload)},{len(payload)}\n")
        rows.append(f"{record_relative},,\n")
        record_path = self._target(record_relative)
        record_path.write_text("".join(rows), encoding="utf-8", newline="")
        return record_path

    def _identity(self) -> dict[str, object]:
        return BOOTSTRAP._requirements_identity(
            self.server_runtime,
            (self.library_root,),
            self.installation_root,
        )

    def _use_case_root(self, label: str) -> None:
        self.installation_root = self.root / label / "runtime-venv"
        self.library_root = self.installation_root / "lib/python3.14/site-packages"
        self.server_runtime = self.root / label / "server-runtime"
        self.library_root.mkdir(parents=True)
        self.server_runtime.mkdir()

    def test_record_owned_closure_accepts_hashed_files_and_venv_script(self):
        self._write_requirements("demo==1.0")
        self._write_distribution(
            "demo",
            "1.0",
            {
                "demo/__init__.py": b"VALUE = 1\n",
                "../../../bin/demo": b"#!/usr/bin/env python3\n",
            },
        )

        identity = self._identity()

        self.assertEqual(1, len(identity["distributions"]))
        self.assertEqual(3, identity["site_packages"][0]["file_count"])
        self.assertEqual(4, identity["owned_file_count"])

    def test_record_owned_closure_rejects_unowned_runtime_content(self):
        cases = {
            "top_level_python": ("unowned_importable.py", b"VALUE = 1\n"),
            "package_python": ("unowned/module.py", b"VALUE = 1\n"),
            "native_library": ("unowned_native.so", b"native"),
            "bytecode": ("unowned.pyc", b"\x00\x00\x00\x00"),
            "metadata": ("orphan.egg-info/PKG-INFO", b"Name: orphan\n"),
        }
        for label, (relative, payload) in cases.items():
            with self.subTest(label=label):
                self._use_case_root(label)
                self._write_requirements("demo==1.0")
                self._write_distribution(
                    "demo", "1.0", {"demo/__init__.py": b"VALUE = 1\n"}
                )
                target = self._target(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                with self.assertRaisesRegex(
                    BOOTSTRAP.ProductionEmbeddingBootstrapError,
                    "unowned runtime",
                ):
                    self._identity()

    def test_record_owned_closure_rejects_path_escape_and_duplicate_owner(self):
        self._write_requirements("alpha==1.0", "bravo==1.0")
        alpha_record = self._write_distribution(
            "alpha", "1.0", {"shared.py": b"VALUE = 1\n"}
        )
        self._write_distribution(
            "bravo", "1.0", {"shared.py": b"VALUE = 1\n"}
        )
        with self.assertRaisesRegex(
            BOOTSTRAP.ProductionEmbeddingBootstrapError,
            "ownership is duplicated",
        ):
            self._identity()

        shutil.rmtree(self.library_root / "bravo-1.0.dist-info")
        self._write_requirements("alpha==1.0")
        alpha_record.write_text(
            alpha_record.read_text(encoding="utf-8")
            + "../../../../outside.py,sha256=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA,1\n",
            encoding="utf-8",
            newline="",
        )
        with self.assertRaisesRegex(
            BOOTSTRAP.ProductionEmbeddingBootstrapError,
            "escapes the installation root",
        ):
            self._identity()

    def test_record_owned_closure_rejects_hash_and_size_drift(self):
        for field in ("hash", "size"):
            with self.subTest(field=field):
                self._use_case_root(field)
                self._write_requirements("demo==1.0")
                record = self._write_distribution(
                    "demo", "1.0", {"demo.py": b"VALUE = 1\n"}
                )
                value = record.read_text(encoding="utf-8")
                if field == "hash":
                    value = value.replace(
                        self._record_hash(b"VALUE = 1\n"),
                        "sha256=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    )
                else:
                    value = value.replace(",10\n", ",11\n")
                record.write_text(value, encoding="utf-8", newline="")
                with self.assertRaisesRegex(
                    BOOTSTRAP.ProductionEmbeddingBootstrapError,
                    f"{field} drifted",
                ):
                    self._identity()


class ProductionEmbeddingCandidateTests(unittest.TestCase):
    def test_held_loader_sets_bound_metadata_without_package_search_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_path = Path(temporary).resolve() / "package/__init__.py"
            source = BOOTSTRAP._HeldSource(
                module="held_fixture.package",
                path=source_path,
                payload=(
                    b"observed_file = __file__\n"
                    b"observed_package = __package__\n"
                    b"observed_path = list(__path__)\n"
                ),
                sha256=hashlib.sha256(b"fixture").hexdigest(),
                is_package=True,
            )
            finder = BOOTSTRAP._HeldSourceFinder({source.module: source})
            spec = finder.find_spec(source.module)
            self.assertIsNotNone(spec)
            module = types.ModuleType(source.module)
            module.__spec__ = spec
            spec.loader.exec_module(module)

            self.assertEqual(str(source_path), module.__file__)
            self.assertEqual(source.module, module.__package__)
            self.assertIs(spec.loader, module.__loader__)
            self.assertEqual(str(source_path), module.__spec__.origin)
            self.assertEqual([], module.__path__)
            self.assertEqual([], module.__spec__.submodule_search_locations)

    def setUp(self) -> None:
        incoming_environment = dict(os.environ)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="kg-production-embedding-candidate-test-"
        )
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)
        self.base_suite_root = self.root / "base-suite"
        self.suite_root = self.base_suite_root / "server-runtime"
        self.suite_root.mkdir(parents=True)
        self.secret = "test-only-embedding-secret-6428"
        self.identity = EmbeddingIdentity(
            provider="provider-neutral-fixture",
            base_url="https://embedding.invalid/v1/embed",
            region="synthetic-region",
            model="embedding-model",
            model_version="embedding-model-v1",
            api_version="api-v1",
            dimension=4,
            normalization="l2",
            input_type="document-or-query-text-v1",
        )
        self.policy = EmbeddingPolicy(
            batch_size=16,
            max_input_units=4096,
            timeout_seconds=2.0,
            max_retries=0,
            max_requests_per_operation=10,
            max_cost_microunits_per_request=5,
            total_cost_budget_microunits=50,
            max_request_bytes=65536,
            max_response_bytes=65536,
        )
        self.environment = {
            "KG_PROVIDER_NETWORK_MODE": "https",
            "KG_EMBEDDING_KEY": self.secret,
        }
        for name in (
            "KG_TEST_PRODUCTION_EMBEDDING_WHEELHOUSE",
            "KG_TEST_PRODUCTION_EMBEDDING_INSTALLER_PYTHON",
            "KG_TEST_PRODUCTION_EMBEDDING_INSTALLER_SHA256",
            "KG_TEST_PRODUCTION_EMBEDDING_SCRATCH_ROOT",
            "TMPDIR",
            "TMP",
            "TEMP",
            "HOME",
        ):
            if name in incoming_environment:
                self.environment[name] = incoming_environment[name]
        (
            self.authority_manifest_path,
            self.authority_database_path,
            self.authority_release_id,
            self.authority_database_sha256,
            self.authority_manifest_sha256,
            self.chunking_identity_sha256,
        ) = self._write_authority()
        (
            self.graph_manifest_path,
            self.graph_data_path,
            self.graph_manifest_sha256,
        ) = self._write_graph()
        self.bm25_manifest_path, self.bm25_index_path = self._write_bm25()
        self.provider_config = self._provider_config()
        self.base_contract_path = self._write_base_production_vector_build_contract()
        self.base_suite_manifest_path = self._write_base_suite_manifest()
        self.base_suite_manifest_sha256 = sha256_file(
            self.base_suite_manifest_path
        )
        self.environment[
            "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
        ] = self.base_suite_manifest_sha256
        self.config_path = self._write_candidate_config()
        self.config = ProductionEmbeddingCandidateConfig.load(self.config_path)
        environment_patch = mock.patch.dict(os.environ, self.environment, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        self.environment = os.environ
        approval_patch = mock.patch.object(
            CANDIDATE,
            "validate_production_approval",
            side_effect=self._approved_runtime,
        )
        approval_patch.start()
        self.addCleanup(approval_patch.stop)
        transport_patch = mock.patch.object(
            CANDIDATE,
            "ProviderHTTPTransport",
            side_effect=self._fake_transport,
        )
        transport_patch.start()
        self.addCleanup(transport_patch.stop)
        materialized = materialize_production_vector_build_contract(
            config=self.config,
            output_path=self.root / "production-vector-build-contract.json",
        )
        self.production_vector_build_contract_path = materialized.contract_path
        self.production_vector_build_contract_sha256 = materialized.contract_sha256
        self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = (
            self.production_vector_build_contract_sha256
        )

    def _bootstrap_path(self) -> Path:
        return (
            self.suite_root
            / "code/deploy/pipeline/production_embedding_bootstrap.py"
        )

    def _run_bootstrap(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
        executable: str | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                executable or sys.executable,
                "-I",
                "-S",
                "-B",
                str(self._bootstrap_path()),
                *arguments,
            ],
            cwd=cwd or self.root,
            env=environment or dict(self.environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def _capture_runtime_lock(
        self,
        name: str = "runtime-lock.json",
        *,
        executable: str | None = None,
    ) -> Path:
        path = self.root / name
        result = self._run_bootstrap(
            "capture-runtime",
            "--output",
            str(path),
            executable=executable,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual("capture-runtime", payload["command"])
        self.assertEqual(sha256_file(path), payload["runtime_lock_sha256"])
        self.environment["KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256"] = payload[
            "runtime_lock_sha256"
        ]
        lock = json.loads(path.read_bytes())
        quick = lock["identity"]["quick"]
        self.assertNotIn("initial_sys_path", quick)
        expected_worker = list(quick["bootstrap_sys_path"])
        for key in ("purelib", "platlib"):
            library_path = quick["library_paths"][key]
            if library_path not in expected_worker:
                expected_worker.append(library_path)
        self.assertEqual(expected_worker, quick["worker_sys_path"])
        return path

    def test_runtime_tree_rejects_import_reachable_directory_symlink(self):
        runtime_root = self.root / "runtime-tree"
        import_root = runtime_root / "lib/python/site-packages"
        external_package = self.root / "mutable-external-package"
        import_root.mkdir(parents=True)
        external_package.mkdir()
        (external_package / "__init__.py").write_text("VALUE = 1\n", encoding="ascii")
        (import_root / "unsafe_package").symlink_to(
            external_package,
            target_is_directory=True,
        )

        with self.assertRaisesRegex(
            BOOTSTRAP.ProductionEmbeddingBootstrapError,
            "directory symlink",
        ):
            BOOTSTRAP._tree_records(
                runtime_root,
                import_roots=(import_root,),
            )

    def _write_json(self, path: Path, value: object) -> None:
        path.write_bytes(canonical_bytes(value) + b"\n")

    @staticmethod
    def _documents():
        documents = [
            ("alpha.txt", "alpha", "textbook", "a" * 40, "1" * 64),
            ("bravo.txt", "bravo", "regulation", "b" * 40, "2" * 64),
        ]
        for index in range(2, R9_SOURCE_SCOPE["source_count"]):
            documents.append(
                (
                    f"source-{index:02d}.txt",
                    f"source text {index:02d}",
                    "textbook",
                    f"{index:040x}",
                    f"{index + 1:064x}",
                )
            )
        return tuple(documents)

    def _write_authority(self):
        authority_root = self.suite_root / "data/authority"
        authority_root.mkdir(parents=True)
        database_path = authority_root / "rag_chunks.db"
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(RUNTIME_AUTHORITY_SCHEMA_SQL)
            connection.execute("PRAGMA user_version=1")
            documents = self._documents()
            sources = []
            recorded_at = "2026-09-03T00:00:00Z"
            for index, (name, text, content_type, suffix, source_hash) in enumerate(
                documents
            ):
                chunk_id = "chunk:" + suffix
                connection.execute(
                    """INSERT INTO document_sources (
                           document_source_id, doc_name, source_path, source_sha256,
                           source_page_count, authority, extractor_version,
                           import_run_id, metadata_json, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"docsrc:{index}",
                        name,
                        "kb://knowledge_base/" + name,
                        source_hash,
                        1,
                        "rag_chunks.db",
                        "cloud-v2-source-extractor-v1",
                        "import-fixture",
                        "{}",
                        recorded_at,
                        recorded_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO documents VALUES (?, ?, ?, ?)",
                    (name, "kb://knowledge_base/" + name, 1, recorded_at),
                )
                connection.execute(
                    """INSERT INTO chunks (
                           chunk_id, text, doc_name, chunk_index, created_at
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (chunk_id, text, name, 0, recorded_at),
                )
                connection.execute(
                    """INSERT INTO chunk_provenance (
                           chunk_id, document_source_id, source_sha256,
                           import_run_id, pdf_page_start, pdf_page_end,
                           content_type, confidence, review_status,
                           evidence_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk_id,
                        f"docsrc:{index}",
                        source_hash,
                        "import-fixture",
                        1,
                        1,
                        content_type,
                        1.0,
                        "approved-source-extracted",
                        json.dumps(
                            {
                                "extractor": "cloud-v2-source-extractor-v1",
                                "source_text_sha256": hashlib.sha256(
                                    text.encode("utf-8") + b"\x00"
                                ).hexdigest(),
                                "unit_ordinal": 0,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        recorded_at,
                    ),
                )
                sources.append(
                    {
                        "relative_path": name,
                        "source_sha256": source_hash,
                        "extracted_text_sha256": hashlib.sha256(
                            text.encode("utf-8") + b"\x00"
                        ).hexdigest(),
                        "chunk_count": 1,
                        "page_count": 1,
                    }
                )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        os.chmod(database_path, 0o600)
        database_sha256 = sha256_file(database_path)
        release_id = f"rag-authority:fixture:{database_sha256[:16]}"
        chunking_identity_sha256 = canonical_sha256(
            {
                "chunking_policy": "cloud-v2-paragraph-1200-v1",
                "extractor_version": "cloud-v2-source-extractor-v1",
            }
        )
        manifest = {
            "schema_version": "cloud-rag-authority-v1",
            "release_id": release_id,
            "status": "candidate",
            "authority": {"owner": "rag_chunks.db", "join_key": "chunk_id"},
            "source_scope": dict(R9_SOURCE_SCOPE),
            "database": {
                "path": database_path.name,
                "sha256": database_sha256,
                "mode": "0600",
                "sqlite_user_version": 1,
                "integrity_check": "ok",
                "foreign_key_violation_count": 0,
            },
            "build": {
                "extractor_version": "cloud-v2-source-extractor-v1",
                "chunking_policy": "cloud-v2-paragraph-1200-v1",
                "import_run_id": "import-fixture",
                "network_calls": 0,
                "old_authority_reused": False,
                "ocr_runtime": None,
            },
            "counts": {
                "documents": len(documents),
                "chunks": len(documents),
                "provenance": len(documents),
            },
            "sources": sources,
        }
        manifest_path = authority_root / "authority-manifest.json"
        self._write_json(manifest_path, manifest)
        return (
            manifest_path,
            database_path,
            release_id,
            database_sha256,
            sha256_file(manifest_path),
            chunking_identity_sha256,
        )

    def _write_graph(self):
        graph_root = self.suite_root / "data/derived/graph"
        graph_root.mkdir(parents=True)
        graph_path = graph_root / "scoped-graph.jsonl"
        documents = self._documents()
        document_ids = {
            name: "document:"
            + hashlib.sha256(name.encode("utf-8")).hexdigest()[:40]
            for name, _text, _content_type, _suffix, _source_hash in documents
        }
        chunkref_ids = {
            suffix: "chunkref:" + suffix
            for _name, _text, _content_type, suffix, _source_hash in documents
        }
        alpha_entity_id = "entity:" + hashlib.sha256(
            "concept\0alpha entity".encode("utf-8")
        ).hexdigest()[:40]
        bravo_entity_id = "entity:" + hashlib.sha256(
            "regulation\0bravo entity".encode("utf-8")
        ).hexdigest()[:40]
        records = []
        for name, _text, _content_type, suffix, _source_hash in documents:
            records.extend(
                [
                    {
                        "kind": "node",
                        "label": "Document",
                        "node_id": document_ids[name],
                        "properties": {
                            "doc_name": name,
                            "authority_release_id": self.authority_release_id,
                        },
                    },
                    {
                        "kind": "node",
                        "label": "ChunkRef",
                        "node_id": chunkref_ids[suffix],
                        "properties": {
                            "chunk_id": "chunk:" + suffix,
                            "authority_release_id": self.authority_release_id,
                        },
                    },
                ]
            )
        records.extend(
            [
                {
                    "kind": "node",
                    "label": "Entity",
                    "node_id": alpha_entity_id,
                    "properties": {
                        "canonical_name": "alpha entity",
                        "entity_type": "concept",
                        "authority_release_id": self.authority_release_id,
                    },
                },
                {
                    "kind": "node",
                    "label": "Entity",
                    "node_id": bravo_entity_id,
                    "properties": {
                        "canonical_name": "bravo entity",
                        "entity_type": "regulation",
                        "authority_release_id": self.authority_release_id,
                    },
                },
            ]
        )
        for name, _text, _content_type, suffix, _source_hash in documents:
            records.append(
                {
                    "kind": "edge",
                    "type": "HAS_CHUNK",
                    "from": document_ids[name],
                    "to": chunkref_ids[suffix],
                    "evidence_chunk_ids": ["chunk:" + suffix],
                }
            )
        chunk_a = "chunk:" + documents[0][3]
        chunk_b = "chunk:" + documents[1][3]
        records.extend(
            [
            {
                "kind": "edge",
                "type": "MENTIONS",
                "from": chunkref_ids[documents[0][3]],
                "to": alpha_entity_id,
                "evidence_chunk_ids": [chunk_a],
            },
            {
                "kind": "edge",
                "type": "MENTIONS",
                "from": chunkref_ids[documents[1][3]],
                "to": bravo_entity_id,
                "evidence_chunk_ids": [chunk_b],
            },
            ]
        )
        graph_path.write_bytes(
            b"".join(canonical_bytes(item) + b"\n" for item in records)
        )
        graph_sha256 = sha256_file(graph_path)
        manifest = {
            "schema_version": "cloud-scoped-graph-v1",
            "release_id": "graph:fixture",
            "status": "candidate",
            "authority_release_id": self.authority_release_id,
            "authority_database_sha256": self.authority_database_sha256,
            "graph": {"path": graph_path.name, "sha256": graph_sha256},
            "counts": {
                "document_nodes": len(documents),
                "chunk_nodes": len(documents),
                "entity_nodes": 2,
                "edges": len(documents) + 2,
            },
            "binding": {
                "text_edge_count": len(documents) + 2,
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
                    "entity_id": alpha_entity_id,
                    "canonical_name": "alpha entity",
                    "entity_type": "concept",
                    "evidence_chunk_ids": [chunk_a],
                },
                {
                    "entity_id": bravo_entity_id,
                    "canonical_name": "bravo entity",
                    "entity_type": "regulation",
                    "evidence_chunk_ids": [chunk_b],
                },
            ],
        }
        manifest_path = graph_root / "graph-manifest.json"
        self._write_json(manifest_path, manifest)
        return manifest_path, graph_path, sha256_file(manifest_path)

    def _write_bm25(self) -> tuple[Path, Path]:
        derived_root = self.suite_root / "data/derived"
        database_path = derived_root / "bm25.sqlite3"
        rows = [
            ("chunk:" + suffix, name, text)
            for name, text, _content_type, suffix, _source_hash in self._documents()
        ]
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE chunks_fts USING "
                "fts5(text, chunk_id UNINDEXED, doc_name UNINDEXED, tokenize='trigram')"
            )
            connection.executemany(
                "INSERT INTO chunks_fts(text, chunk_id, doc_name) VALUES (?, ?, ?)",
                [(text, chunk_id, doc_name) for chunk_id, doc_name, text in rows],
            )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        os.chmod(database_path, 0o600)
        fingerprint = hashlib.sha256()
        text_byte_count = 0
        text_codepoint_count = 0
        for chunk_id, doc_name, text in sorted(rows):
            fingerprint.update(
                json.dumps(
                    [chunk_id, doc_name, 0, text],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            fingerprint.update(b"\n")
            text_byte_count += len(text.encode("utf-8"))
            text_codepoint_count += len(text)
        manifest = {
            "schema_version": "cloud-v2-sqlite-fts5-trigram-v1",
            "status": "candidate",
            "authority_release_id": self.authority_release_id,
            "authority_database_sha256": self.authority_database_sha256,
            "source": {
                "chunk_count": len(rows),
                "document_count": len(rows),
                "text_byte_count": text_byte_count,
                "text_codepoint_count": text_codepoint_count,
                "schema_version": "chunks-v1",
                "fingerprint_algorithm": "sha256-jsonl-chunk-content-v1",
                "fingerprint": fingerprint.hexdigest(),
            },
            "index": {
                "path": database_path.name,
                "sha256": sha256_file(database_path),
            },
            "indexed_chunk_count": len(rows),
            "tokenizer": "trigram",
            "minimum_effective_query_codepoints": 3,
            "short_query_fallback": "authority-sqlite-substring-v1",
            "sqlite_backfill_required": True,
        }
        manifest_path = derived_root / "bm25-manifest.json"
        self._write_json(manifest_path, manifest)
        return manifest_path, database_path

    def _write_base_production_vector_build_contract(self) -> Path:
        allowlist_source = REPO_ROOT / "deploy/cloud_v2/builder-file-allowlist.json"
        allowlist = json.loads(allowlist_source.read_text(encoding="utf-8"))
        shutil.copyfile(
            allowlist_source,
            self.suite_root / "builder-file-allowlist.json",
        )
        shutil.copyfile(
            REPO_ROOT / "deploy/cloud_v2/requirements.lock",
            self.suite_root / "requirements.lock",
        )
        builder_records = []
        for relative in allowlist["files"]:
            source = REPO_ROOT / relative
            target = self.suite_root / "code" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            builder_records.append(
                {"path": relative, "sha256": sha256_file(target)}
            )
        data_records = [
            {
                "path": "authority/authority-manifest.json",
                "role": "authority-manifest",
                "sha256": sha256_file(self.authority_manifest_path),
            },
            {
                "path": "authority/rag_chunks.db",
                "role": "authority-sqlite",
                "sha256": sha256_file(self.authority_database_path),
            },
            {
                "path": "derived/bm25-manifest.json",
                "role": "bm25-manifest",
                "sha256": sha256_file(self.bm25_manifest_path),
            },
            {
                "path": "derived/bm25.sqlite3",
                "role": "bm25-index",
                "sha256": sha256_file(self.bm25_index_path),
            },
            {
                "path": "derived/graph/graph-manifest.json",
                "role": "graph-manifest",
                "sha256": sha256_file(self.graph_manifest_path),
            },
            {
                "path": "derived/graph/scoped-graph.jsonl",
                "role": "graph-data",
                "sha256": sha256_file(self.graph_data_path),
            },
        ]
        data_records.sort(key=lambda record: record["path"])
        builder_hashes = {
            record["path"]: record["sha256"] for record in builder_records
        }
        contract = {
            "schema_version": "cloud-v2-production-vector-build-contract-v1",
            "status": "unconfigured-pending-stop-b-production-provider-approval",
            "provider_neutral": True,
            "builder": {
                "working_directory": "not-required-isolated-bootstrap",
                "module": "pipeline.production_embedding_candidate",
                "bootstrap_path": (
                    "code/deploy/pipeline/production_embedding_bootstrap.py"
                ),
                "bootstrap_sha256": builder_hashes[
                    "deploy/pipeline/production_embedding_bootstrap.py"
                ],
                "source_path": "code/deploy/pipeline/production_embedding_candidate.py",
                "source_sha256": builder_hashes[
                    "deploy/pipeline/production_embedding_candidate.py"
                ],
                "runtime_capture_command": CANDIDATE._expected_builder_command(
                    "capture-runtime"
                ),
                "runtime_verify_command": [
                    "<absolute-python-executable>",
                    "-I",
                    "-S",
                    "-B",
                    "<exact-release-bootstrap-path>",
                    "--runtime-lock",
                    "<absolute-runtime-lock-path>",
                    "verify-runtime",
                ],
                "materialize_command": CANDIDATE._expected_builder_command(
                    "materialize"
                ),
                "validate_command": CANDIDATE._expected_builder_command("validate"),
                "build_command": CANDIDATE._expected_builder_command("build"),
                "file_allowlist_path": "builder-file-allowlist.json",
                "file_allowlist_sha256": sha256_file(
                    self.suite_root / "builder-file-allowlist.json"
                ),
                "file_set_sha256": record_set_sha256(builder_records),
                "files": builder_records,
            },
            "schemas": {
                name: {"path": "code/" + relative, "sha256": builder_hashes[relative]}
                for name, relative in {
                    "candidate_config_schema": (
                        "deploy/pipeline/production_embedding_config.schema.json"
                    ),
                    "provider_runtime_schema": (
                        "deploy/pipeline/provider_runtime_config.schema.json"
                    ),
                    "production_embedding_runtime_lock_schema": (
                        "deploy/pipeline/production_embedding_runtime_lock.schema.json"
                    ),
                    "stop_b_request_schema": (
                        "deploy/cloud_v2/stop-b-external-processing-request.schema.json"
                    ),
                }.items()
            },
            "sealed_inputs": {
                "file_set_sha256": record_set_sha256(data_records),
                "files": data_records,
                "authority_manifest_sha256": sha256_file(
                    self.authority_manifest_path
                ),
                "authority_database_sha256": sha256_file(
                    self.authority_database_path
                ),
                "bm25_manifest_sha256": sha256_file(self.bm25_manifest_path),
                "bm25_index_sha256": sha256_file(self.bm25_index_path),
                "graph_manifest_sha256": sha256_file(self.graph_manifest_path),
                "graph_data_sha256": sha256_file(self.graph_data_path),
            },
            "production_embedding_identity": {
                "provider": None,
                "endpoint": None,
                "region": None,
                "model": None,
                "model_version": None,
                "dimension": None,
                "normalization": None,
            },
            "output_contract": {
                "mode": "candidate-only",
                "chunk_and_entity_indexes_required": True,
                "production_vector_packaged": False,
                "fake_fixture_packaged": False,
                "active_write_authorized": False,
                "release_switch_authorized": False,
            },
            "approval_contract": {
                "stop_b_production_provider_approved_required": True,
                "real_provider_calls_authorized": False,
                "production_build_authorized": False,
            },
        }
        path = self.suite_root / "production-vector-build-contract.json"
        self._write_json(path, contract)
        return path

    def _write_base_suite_manifest(self) -> Path:
        components = [
            {
                "path": path.relative_to(self.base_suite_root).as_posix(),
                "sha256": sha256_file(path),
            }
            for path in sorted(
                self.base_suite_root.rglob("*"),
                key=lambda item: item.relative_to(self.base_suite_root).as_posix(),
            )
            if path.is_file()
            and path.relative_to(self.base_suite_root).as_posix()
            not in {"SUITE_MANIFEST.json", "SHA256SUMS"}
        ]
        component_set_sha256 = record_set_sha256(components)
        contract = json.loads(self.base_contract_path.read_text(encoding="utf-8"))
        sealed = contract["sealed_inputs"]
        manifest = {
            "schema_version": "cloud-v2-suite-manifest-v1",
            "suite_release_id": (
                "knowledge-qa-suite:r9-offline:" + component_set_sha256[:16]
            ),
            "status": "offline-provider-candidate",
            "created_at": "2026-09-03T00:00:00Z",
            "base_commit": "f09f090d5c7ee6b3b029d66894a9d9c13022f0d3",
            "components": components,
            "component_set_sha256": component_set_sha256,
            "identities": {
                "authority_manifest_sha256": sealed[
                    "authority_manifest_sha256"
                ],
                "authority_database_sha256": sealed[
                    "authority_database_sha256"
                ],
                "bm25_manifest_sha256": sealed["bm25_manifest_sha256"],
                "bm25_index_sha256": sealed["bm25_index_sha256"],
                "graph_candidate_manifest_sha256": sealed[
                    "graph_manifest_sha256"
                ],
                "graph_data_sha256": sealed["graph_data_sha256"],
                "builder_file_allowlist_sha256": contract["builder"][
                    "file_allowlist_sha256"
                ],
                "builder_code_file_set_sha256": contract["builder"][
                    "file_set_sha256"
                ],
                "production_vector_build_contract_sha256": sha256_file(
                    self.base_contract_path
                ),
            },
            "evidence": {},
            "phase_state": {
                "stop_a": "approved",
                "stop_b": "pending",
                "stop_c": "pending",
                "stop_d": "pending",
                "real_provider_calls": 0,
                "commit_push_upload_deploy_authorized": False,
                "runtime_activation_authorized": False,
                "product_accepted": False,
            },
        }
        path = self.base_suite_root / "SUITE_MANIFEST.json"
        self._write_json(path, manifest)
        return path

    def _reseal_base_suite(self, *, update_anchor: bool = True) -> None:
        self._write_base_suite_manifest()
        current_sha256 = sha256_file(self.base_suite_manifest_path)
        self.base_suite_manifest_sha256 = current_sha256
        if update_anchor:
            self.environment[
                "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
            ] = current_sha256
        if self.config_path.exists():
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
            value["base_suite"]["manifest"]["sha256"] = current_sha256
            value["base_suite"]["pending_contract"]["sha256"] = sha256_file(
                self.base_contract_path
            )
            self._write_json(self.config_path, value)

    def _rematerialize_production_vector_contract(self) -> None:
        temporary_path = self.root / "rematerialized-production-vector-contract.json"
        materialized = materialize_production_vector_build_contract(
            config=self.config,
            output_path=temporary_path,
        )
        os.replace(temporary_path, self.production_vector_build_contract_path)
        self.production_vector_build_contract_sha256 = materialized.contract_sha256
        self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = (
            materialized.contract_sha256
        )

    def _reseal_unvalidated_configured_contract_for_attack(self) -> None:
        identity, _policy, _bindings = CANDIDATE._binding_contract(
            self.config.provider_config,
            self.config.vector_contract,
        )
        approved_production = self._approved_local_vector_production()
        binding = CANDIDATE._load_base_suite_binding(
            self.config,
            self.environment["KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"],
        )
        contract = CANDIDATE._configured_contract(
            binding,
            self.config,
            identity,
            approved_production,
        )
        self._write_json(self.production_vector_build_contract_path, contract)
        self.production_vector_build_contract_sha256 = sha256_file(
            self.production_vector_build_contract_path
        )
        self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = (
            self.production_vector_build_contract_sha256
        )

    def _reanchor_configured_contract_for_invalid_base_attack(self) -> None:
        identity, _policy, _bindings = CANDIDATE._binding_contract(
            self.config.provider_config,
            self.config.vector_contract,
        )
        approved_production = self._approved_local_vector_production()
        contract = json.loads(
            self.production_vector_build_contract_path.read_text(encoding="utf-8")
        )
        contract["candidate_config_sha256"] = self.config.sha256
        contract["provider_binding"] = CANDIDATE._provider_binding(self.config)
        contract["production_embedding_identity"] = (
            CANDIDATE._production_embedding_identity(identity)
        )
        contract["local_vector_contract"] = {
            "configured": CANDIDATE._local_vector_build_contract(
                self.config,
                identity,
            ),
            "approved_production": approved_production,
        }
        self._write_json(self.production_vector_build_contract_path, contract)
        self.production_vector_build_contract_sha256 = sha256_file(
            self.production_vector_build_contract_path
        )
        self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = (
            self.production_vector_build_contract_sha256
        )

    def _reseal_production_vector_contract_data(
        self,
        *,
        update_base_anchor: bool = True,
        rematerialize: bool = True,
    ) -> None:
        contract = json.loads(
            self.base_contract_path.read_text(encoding="utf-8")
        )
        data_paths = {
            "authority/authority-manifest.json": self.authority_manifest_path,
            "authority/rag_chunks.db": self.authority_database_path,
            "derived/bm25-manifest.json": self.bm25_manifest_path,
            "derived/bm25.sqlite3": self.bm25_index_path,
            "derived/graph/graph-manifest.json": self.graph_manifest_path,
            "derived/graph/scoped-graph.jsonl": self.graph_data_path,
        }
        records = contract["sealed_inputs"]["files"]
        for record in records:
            record["sha256"] = sha256_file(data_paths[record["path"]])
        contract["sealed_inputs"]["file_set_sha256"] = record_set_sha256(records)
        record_hashes = {record["path"]: record["sha256"] for record in records}
        for field, relative in {
            "authority_manifest_sha256": "authority/authority-manifest.json",
            "authority_database_sha256": "authority/rag_chunks.db",
            "bm25_manifest_sha256": "derived/bm25-manifest.json",
            "bm25_index_sha256": "derived/bm25.sqlite3",
            "graph_manifest_sha256": "derived/graph/graph-manifest.json",
            "graph_data_sha256": "derived/graph/scoped-graph.jsonl",
        }.items():
            contract["sealed_inputs"][field] = record_hashes[relative]
        self._write_json(self.base_contract_path, contract)
        self._reseal_base_suite(update_anchor=update_base_anchor)
        if self.config_path.exists():
            self.config = ProductionEmbeddingCandidateConfig.load(self.config_path)
            if rematerialize and hasattr(
                self, "production_vector_build_contract_path"
            ):
                self._rematerialize_production_vector_contract()

    def _provider_config(self) -> ProviderRuntimeConfig:
        answer = ServerAnswerChannel(
            channel_id="answer-1",
            provider="answer-provider-fixture",
            base_url="https://answer.invalid/v1/generate",
            region="synthetic-region",
            model="answer-model",
            model_version="answer-model-v1",
            api_version="api-v1",
            timeout_seconds=2.0,
            max_input_units=4096,
            max_output_units=512,
            max_cost_microunits=10,
            max_request_bytes=65536,
            max_response_bytes=65536,
        )
        meters = {
            "input_meter_id": "unicode_codepoints-v1",
            "output_meter_id": "unicode_codepoints-v1",
            "cost_meter_id": "maximum_request_exposure-v1",
        }
        auth = {"header_name": "Authorization", "prefix": "Bearer "}
        answer_wire = {
            "schema_version": "kg-provider-answer-wire-v1",
            "request_schema_sha256": "1" * 64,
            "response_schema_sha256": "2" * 64,
            "body_template": {
                "model": {"$ref": "identity.model"},
                "question": {"$ref": "request.question"},
            },
            "answer_pointer": "/result/text",
        }
        answer_wire["wire_contract_sha256"] = canonical_sha256(answer_wire)
        embedding_wire = {
            "schema_version": "kg-provider-embedding-wire-v1",
            "request_schema_sha256": "3" * 64,
            "response_schema_sha256": "4" * 64,
            "body_template": {
                "model": {"$ref": "identity.model"},
                "model_version": {"$ref": "identity.model_version"},
                "dimension": {"$ref": "identity.dimension"},
                "normalization": {"$ref": "identity.normalization"},
                "embedding_identity_sha256": {
                    "$ref": "request.embedding_identity_sha256"
                },
                "purpose": {"$ref": "request.purpose"},
                "inputs": {"$ref": "request.items"},
            },
            "vectors_pointer": "/data",
            "values_pointer": "/embedding",
            "match_by": "input_order",
            "id_pointer": None,
        }
        embedding_wire["wire_contract_sha256"] = canonical_sha256(
            embedding_wire
        )
        value = {
            "schema_version": "kg-provider-runtime-config-v1",
            "network_mode": "https",
            "approval_binding": {
                "receipt_path": str(self.root / "approval.json"),
                "receipt_sha256": "5" * 64,
                "stop_b_request_path": str(self.root / "stop-b-request.json"),
                "stop_b_request_sha256": "6" * 64,
                "contract_materials_path": str(
                    self.root / "contract-materials.json"
                ),
                "contract_materials_sha256": "7" * 64,
                "egress_policy_path": str(self.root / "egress.json"),
                "egress_policy_sha256": "8" * 64,
            },
            "server_answer": {
                "strategy": "single",
                "winner_policy": "ordered_success",
                "total_budget_seconds": 2.0,
                "total_cost_budget_microunits": 10,
                "circuit_breaker_failure_threshold": 2,
                "circuit_breaker_cooldown_seconds": 30.0,
                "channels": [
                    {
                        "channel_id": answer.channel_id,
                        "approval_role_id": "server_answer:answer-1",
                        "provider": answer.provider,
                        "endpoint": answer.base_url,
                        "region": answer.region,
                        "model": answer.model,
                        "model_version": answer.model_version,
                        "api_version": answer.api_version,
                        "identity_sha256": answer.identity_sha256,
                        "secret_ref": "secretref:KG_ANSWER_KEY",
                        "auth": auth,
                        "limits": {
                            "timeout_seconds": answer.timeout_seconds,
                            "max_input_units": answer.max_input_units,
                            "max_output_units": answer.max_output_units,
                            "max_cost_microunits": answer.max_cost_microunits,
                            "max_request_bytes": answer.max_request_bytes,
                            "max_response_bytes": answer.max_response_bytes,
                        },
                        "meters": meters,
                        "wire": answer_wire,
                    }
                ],
            },
            "embedding": {
                "approval_role_id": "embedding",
                "identity": {
                    "provider": self.identity.provider,
                    "endpoint": self.identity.base_url,
                    "region": self.identity.region,
                    "model": self.identity.model,
                    "model_version": self.identity.model_version,
                    "api_version": self.identity.api_version,
                    "dimension": self.identity.dimension,
                    "normalization": self.identity.normalization,
                    "input_type": self.identity.input_type,
                },
                "identity_sha256": self.identity.sha256,
                "policy": {
                    "batch_size": self.policy.batch_size,
                    "max_input_units": self.policy.max_input_units,
                    "timeout_seconds": self.policy.timeout_seconds,
                    "max_retries": self.policy.max_retries,
                    "max_requests_per_operation": (
                        self.policy.max_requests_per_operation
                    ),
                    "max_cost_microunits_per_request": (
                        self.policy.max_cost_microunits_per_request
                    ),
                    "total_cost_budget_microunits": (
                        self.policy.total_cost_budget_microunits
                    ),
                    "max_request_bytes": self.policy.max_request_bytes,
                    "max_response_bytes": self.policy.max_response_bytes,
                },
                "policy_sha256": self.policy.sha256,
                "secret_ref": "secretref:KG_EMBEDDING_KEY",
                "auth": auth,
                "meters": meters,
                "wire": embedding_wire,
            },
        }
        path = self.root / "provider.json"
        self._write_json(path, value)
        return ProviderRuntimeConfig.load(path)

    def _candidate_config_value(self) -> dict[str, object]:
        return {
            "schema_version": "kg-production-embedding-candidate-config-v2",
            "provider_config": {
                "path": str(self.provider_config.path),
                "sha256": self.provider_config.sha256,
            },
            "base_suite": {
                "manifest": {
                    "path": str(self.base_suite_manifest_path),
                    "sha256": sha256_file(self.base_suite_manifest_path),
                },
                "pending_contract": {
                    "path": str(self.base_contract_path),
                    "sha256": sha256_file(self.base_contract_path),
                },
            },
            "authority": {
                "path": str(self.authority_manifest_path),
                "sha256": self.authority_manifest_sha256,
            },
            "graph": {
                "path": str(self.graph_manifest_path),
                "sha256": self.graph_manifest_sha256,
            },
            "local_vector": {
                "approved_data_parent": str(self.root),
                "data_root": str(self.root / "vector-data"),
                "data_release_id": local_data_release_id(
                    self.authority_database_sha256,
                    self.identity.sha256,
                ),
                "authority_manifest_sha256": self.authority_manifest_sha256,
                "chunking_identity_sha256": self.chunking_identity_sha256,
                "embedding_identity_sha256": self.identity.sha256,
                "dimension": self.identity.dimension,
                "metric": "cosine",
                "schema_version": "kg-local-vector-schema-v1",
                "chunk_index_name": "chunk-index",
                "entity_index_name": "entity-index",
                "top_k_max": 20,
                "max_vectors_per_index": 100,
                "metadata_allowlist": {
                    "chunk": ["authority_release_id", "content_type"],
                    "entity": ["authority_release_id", "entity_type"],
                },
                "engine": "usearch",
                "engine_version": "2.26.2",
                "dtype": "f32",
            },
        }

    def _write_candidate_config(self) -> Path:
        path = self.root / "production-embedding.json"
        self._write_json(path, self._candidate_config_value())
        return path

    def _candidate_with_authority_manifest(
        self,
        manifest: object,
        *,
        rematerialize: bool = True,
    ):
        self._write_json(self.authority_manifest_path, manifest)
        manifest_sha256 = sha256_file(self.authority_manifest_path)
        value = self._candidate_config_value()
        value["authority"]["sha256"] = manifest_sha256
        value["local_vector"]["authority_manifest_sha256"] = manifest_sha256
        self._write_json(self.config_path, value)
        self._reseal_production_vector_contract_data(
            rematerialize=rematerialize,
        )
        return self.config

    def _reseal_complete_data_chain(self) -> ProductionEmbeddingCandidateConfig:
        trusted_base_anchor = self.environment[
            "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
        ]
        replacement_text = "alpha replacement with a completely resealed data chain"
        replacement_text_sha256 = hashlib.sha256(
            replacement_text.encode("utf-8") + b"\x00"
        ).hexdigest()
        connection = sqlite3.connect(self.authority_database_path)
        try:
            connection.execute(
                "UPDATE chunks SET text=? WHERE chunk_id=?",
                (replacement_text, "chunk:" + "a" * 40),
            )
            connection.execute(
                "UPDATE chunk_provenance SET evidence_json=? WHERE chunk_id=?",
                (
                    json.dumps(
                        {
                            "extractor": "cloud-v2-source-extractor-v1",
                            "source_text_sha256": replacement_text_sha256,
                            "unit_ordinal": 0,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "chunk:" + "a" * 40,
                ),
            )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        authority_database_sha256 = sha256_file(self.authority_database_path)
        authority_release_id = (
            f"rag-authority:fixture:{authority_database_sha256[:16]}"
        )
        authority = json.loads(
            self.authority_manifest_path.read_text(encoding="utf-8")
        )
        authority["release_id"] = authority_release_id
        authority["database"]["sha256"] = authority_database_sha256
        for source in authority["sources"]:
            if source["relative_path"] == "alpha.txt":
                source["extracted_text_sha256"] = replacement_text_sha256
                break
        else:
            self.fail("authority fixture omitted alpha.txt")
        self._write_json(self.authority_manifest_path, authority)

        connection = sqlite3.connect(self.bm25_index_path)
        try:
            connection.execute(
                "UPDATE chunks_fts SET text=? WHERE chunk_id=?",
                (replacement_text, "chunk:" + "a" * 40),
            )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        semantics = CANDIDATE.inspect_authority_bm25_semantics(
            self.authority_database_path,
            self.bm25_index_path,
        )
        bm25 = json.loads(self.bm25_manifest_path.read_text(encoding="utf-8"))
        bm25["authority_release_id"] = authority_release_id
        bm25["authority_database_sha256"] = authority_database_sha256
        bm25["source"] = dict(semantics.source)
        bm25["index"]["sha256"] = semantics.bm25_database_sha256
        bm25["indexed_chunk_count"] = semantics.indexed_chunk_count
        self._write_json(self.bm25_manifest_path, bm25)

        graph_records = []
        for line in self.graph_data_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            properties = record.get("properties")
            if isinstance(properties, dict) and "authority_release_id" in properties:
                properties["authority_release_id"] = authority_release_id
            graph_records.append(record)
        self.graph_data_path.write_bytes(
            b"".join(canonical_bytes(record) + b"\n" for record in graph_records)
        )
        graph_sha256 = sha256_file(self.graph_data_path)
        graph = json.loads(self.graph_manifest_path.read_text(encoding="utf-8"))
        graph["authority_release_id"] = authority_release_id
        graph["authority_database_sha256"] = authority_database_sha256
        graph["graph"]["sha256"] = graph_sha256
        graph["release_id"] = (
            "graph:" + authority_release_id.split(":", 1)[-1] + ":" + graph_sha256[:16]
        )
        self._write_json(self.graph_manifest_path, graph)

        authority_manifest_sha256 = sha256_file(self.authority_manifest_path)
        graph_manifest_sha256 = sha256_file(self.graph_manifest_path)
        config = self._candidate_config_value()
        config["authority"]["sha256"] = authority_manifest_sha256
        config["graph"]["sha256"] = graph_manifest_sha256
        config["local_vector"]["authority_manifest_sha256"] = (
            authority_manifest_sha256
        )
        config["local_vector"]["data_release_id"] = local_data_release_id(
            authority_database_sha256,
            self.identity.sha256,
        )
        self._write_json(self.config_path, config)
        self._reseal_production_vector_contract_data(
            update_base_anchor=False,
            rematerialize=False,
        )
        attacker_environment = dict(self.environment)
        attacker_environment[
            "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
        ] = sha256_file(self.base_suite_manifest_path)
        self.production_vector_build_contract_path.unlink()
        with mock.patch.dict(os.environ, attacker_environment, clear=True):
            materialized = materialize_production_vector_build_contract(
                config=self.config,
                output_path=self.production_vector_build_contract_path,
            )
        self.production_vector_build_contract_sha256 = materialized.contract_sha256
        self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = (
            materialized.contract_sha256
        )
        self.environment[
            "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
        ] = trusted_base_anchor
        return self.config

    def _replacement_authority_database(self) -> Path:
        replacement = self.root / "rag_chunks-replacement.db"
        replacement.write_bytes(self.authority_database_path.read_bytes())
        connection = sqlite3.connect(replacement)
        try:
            connection.execute(
                "UPDATE chunks SET text=? WHERE chunk_id=?",
                ("replacement-only text", "chunk:" + "a" * 40),
            )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        os.chmod(replacement, 0o600)
        self.assertNotEqual(
            self.authority_database_sha256,
            sha256_file(replacement),
        )
        return replacement

    def _approved_local_vector_production(self) -> dict[str, object]:
        vector = self.config.vector_contract.identity_manifest()
        embedding = self.config.provider_config.embedding
        self.assertIsNotNone(embedding)
        return {
            "target_platform": {
                "os_name": "fixture-os",
                "os_version": "fixture-version",
                "architecture": "fixture-architecture",
                "cpu_model": "fixture-cpu",
                "cpu_features": ["fixture-feature"],
                "filesystem": "fixture-filesystem",
            },
            "engine": {
                "name": vector["engine"],
                "version": vector["engine_version"],
                "package_sha256": "9" * 64,
                "python_version": "3.14.6",
                "index_build_threads": vector["index_build_threads"],
            },
            "data_layout": {
                "data_root": str(self.config.vector_contract.data_root),
                "candidate_root": str(
                    self.config.vector_contract.data_root / "candidate"
                ),
                "active_root": str(self.config.vector_contract.data_root / "active"),
                "owner": "fixture-owner",
                "group": "fixture-group",
                "directory_mode": "0700",
                "file_mode": "0600",
            },
            "indexes": dict(vector["index_names"]),
            "vector_identity": {
                "embedding_identity_sha256": vector[
                    "embedding_identity_sha256"
                ],
                "dimension": vector["dimension"],
                "dtype": vector["dtype"],
                "normalization": embedding.identity["normalization"],
                "metric": vector["metric"],
                "engine_metric": vector["engine_metric"],
                "schema_version": vector["schema_version"],
                "authority_manifest_sha256": vector[
                    "authority_manifest_sha256"
                ],
                "chunking_identity_sha256": vector[
                    "chunking_identity_sha256"
                ],
                "metadata_allowlist": dict(vector["metadata_allowlist"]),
                "top_k_max": vector["top_k_max"],
                "max_vectors_per_index": vector["max_vectors_per_index"],
            },
            "capacity": {
                "chunk_capacity": 2000,
                "entity_capacity": 100,
                "memory_budget_bytes": 1048576,
                "disk_budget_bytes": 2097152,
            },
            "static_encryption": {
                "algorithm": "fixture-encryption",
                "key_reference": "secretref:KG_VECTOR_ENCRYPTION_KEY",
            },
            "backup": {
                "backup_root": str(self.root / "vector-backups"),
                "retention_seconds": 86400,
                "rpo_seconds": 3600,
                "rto_seconds": 3600,
                "restore_test_evidence_sha256": "a" * 64,
            },
            "exact_delete": {
                "target_kinds": [
                    "candidate_root",
                    "active_root",
                    "backup_root",
                ],
                "procedure_id": "fixture-exact-delete-v1",
                "verification_method": "fixture-hash-and-absence-check",
                "verification_schema_sha256": "b" * 64,
            },
            "runtime_read_only": True,
            "network_listener": False,
            "rebuild_from_real_embedding_required": True,
        }

    def _approved(self, _config) -> dict[str, object]:
        return self._approved_local_vector_production()

    def _approved_runtime(
        self,
        _config,
        _environment=None,
    ) -> dict[str, object]:
        return self._approved_local_vector_production()

    def _executor(self, *, partial_purpose: str | None = None):
        return FakeEmbeddingExecutor(
            dimension=self.identity.dimension,
            model=self.identity.model,
            model_version=self.identity.model_version,
            identity_sha256=self.identity.sha256,
            secret=self.secret,
            call_log=self.root / "calls.log",
            partial_purpose=partial_purpose,
        )

    def _fake_transport(self, **kwargs):
        return RealProviderHTTPTransport(executor=self._executor(), **kwargs)

    def _build(self, **changes):
        environment = changes.pop("environment", None)
        approval_validator = changes.pop("approval_validator", None)
        executor = changes.pop("executor", None)
        values = {
            "config": self.config,
            "production_vector_build_contract_path": (
                self.production_vector_build_contract_path
            ),
        }
        values.update(changes)
        with contextlib.ExitStack() as stack:
            if environment is not None:
                stack.enter_context(mock.patch.dict(os.environ, environment, clear=True))
            if approval_validator is not None:
                stack.enter_context(
                    mock.patch.object(
                        CANDIDATE,
                        "validate_production_approval",
                        side_effect=lambda config, _environment: approval_validator(config),
                    )
                )
            if executor is not None:
                stack.enter_context(
                    mock.patch.object(
                        CANDIDATE,
                        "ProviderHTTPTransport",
                        side_effect=lambda **kwargs: RealProviderHTTPTransport(
                            executor=executor,
                            **kwargs,
                        ),
                    )
                )
            return build_production_embedding_candidate(**values)

    def _validate(self, **changes):
        environment = changes.pop("environment", None)
        approval_validator = changes.pop("approval_validator", None)
        values = {
            "config": self.config,
            "production_vector_build_contract_path": (
                self.production_vector_build_contract_path
            ),
        }
        values.update(changes)
        with contextlib.ExitStack() as stack:
            if environment is not None:
                stack.enter_context(mock.patch.dict(os.environ, environment, clear=True))
            if approval_validator is not None:
                stack.enter_context(
                    mock.patch.object(
                        CANDIDATE,
                        "validate_production_approval",
                        side_effect=lambda config, _environment: approval_validator(config),
                    )
                )
            return validate_production_embedding_candidate(**values)

    def test_sealed_sources_validate_then_build_candidate_only(self):
        validation = self._validate()
        self.assertEqual(R9_SOURCE_SCOPE["source_count"], validation.chunk_count)
        self.assertEqual(2, validation.entity_count)
        self.assertEqual(self.authority_database_sha256, validation.authority_database_sha256)
        self.assertEqual(self.graph_manifest_sha256, validation.graph_manifest_sha256)
        self.assertEqual(
            self.production_vector_build_contract_sha256,
            validation.production_vector_build_contract_sha256,
        )
        self.assertEqual(0, validation.network_calls)
        self.assertFalse((self.root / "calls.log").exists())
        self.assertFalse(self.config.vector_contract.candidate_release_dir.exists())

        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network forbidden in parent"),
        ):
            receipt = self._build()
        self.assertTrue(receipt.candidate_only)
        self.assertEqual(
            self.production_vector_build_contract_sha256,
            receipt.production_vector_build_contract_sha256,
        )
        self.assertEqual(
            R9_SOURCE_SCOPE["source_count"], receipt.local_vector.chunk_count
        )
        self.assertEqual(2, receipt.local_vector.entity_count)
        serialized = receipt.as_dict()
        self.assertEqual(3, len(serialized["chunk_ledger"]))
        self.assertEqual(1, len(serialized["entity_ledger"]))
        ledger_text = json.dumps(serialized, sort_keys=True)
        self.assertNotIn(self.secret, ledger_text)
        self.assertNotIn("alpha entity", ledger_text)
        self.assertNotIn("bravo entity", ledger_text)
        self.assertEqual(
            ["build", "build", "build", "entity"],
            (self.root / "calls.log").read_text(encoding="ascii").splitlines(),
        )
        release_dir = self.config.vector_contract.candidate_release_dir
        self.assertTrue((release_dir / "chunk-index/index.usearch").is_file())
        self.assertTrue((release_dir / "entity-index/index.usearch").is_file())
        self.assertFalse(self.config.vector_contract.active_release_dir.exists())
        self.assertFalse(self.config.vector_contract.active_state_path.exists())
        manifest_text = (release_dir / "local_vector_manifest.json").read_text(
            encoding="utf-8"
        )
        for source_text in (
            '"text":',
            "alpha entity",
            "bravo entity",
        ):
            self.assertNotIn(source_text, manifest_text)

    def test_materializer_is_deterministic_and_preserves_pending_base(self):
        pending = json.loads(self.base_contract_path.read_text(encoding="utf-8"))
        configured = json.loads(
            self.production_vector_build_contract_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            "unconfigured-pending-stop-b-production-provider-approval",
            pending["status"],
        )
        self.assertFalse(
            pending["approval_contract"]["real_provider_calls_authorized"]
        )
        self.assertEqual(
            "configured-stop-b-production-provider-approved",
            configured["status"],
        )
        self.assertEqual(
            self.base_suite_manifest_sha256,
            configured["base_suite"]["manifest"]["sha256"],
        )
        self.assertEqual(
            sha256_file(self.base_contract_path),
            configured["base_suite"]["pending_contract"]["sha256"],
        )
        self.assertEqual(35, len(configured["source_scope"]["files"]))
        self.assertEqual(
            self.identity.api_version,
            configured["production_embedding_identity"]["api_version"],
        )
        self.assertEqual(
            self.identity.input_type,
            configured["production_embedding_identity"]["input_type"],
        )
        self.assertEqual(
            self.identity.sha256,
            configured["production_embedding_identity"]["identity_sha256"],
        )
        self.assertEqual(
            self.config.sha256,
            configured["candidate_config_sha256"],
        )
        configured_vector = configured["local_vector_contract"]["configured"]
        self.assertEqual(
            str(self.config.vector_contract.candidate_release_dir),
            configured_vector["candidate_release_dir"],
        )
        self.assertEqual(
            self.config.vector_contract.identity_manifest()["top_k_max"],
            configured_vector["identity"]["top_k_max"],
        )
        self.assertEqual(
            self._approved_local_vector_production(),
            configured["local_vector_contract"]["approved_production"],
        )
        self.assertEqual(pending["builder"], configured["builder"])
        self.assertEqual(pending["sealed_inputs"], configured["sealed_inputs"])
        second = materialize_production_vector_build_contract(
            config=self.config,
            output_path=self.root / "production-vector-build-contract-second.json",
        )
        self.assertEqual(
            self.production_vector_build_contract_path.read_bytes(),
            second.contract_path.read_bytes(),
        )
        self.assertNotIn(
            "offline-phase1-fake",
            second.contract_path.read_text(encoding="utf-8"),
        )
        self.assertNotIn(".usearch", second.contract_path.read_text(encoding="utf-8"))
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            materialize_production_vector_build_contract(
                config=self.config,
                output_path=self.suite_root / "configured-contract-v2.json",
            )
        self.assertEqual(
            "production_vector_build_contract_must_be_suite_external",
            caught.exception.code,
        )

    def test_materializer_holds_parent_fd_across_parent_path_swap(self):
        output_parent = self.root / "contract-output"
        output_parent.mkdir()
        moved_parent = self.root / "contract-output-held"
        output_path = output_parent / "configured.json"
        read_contract = CANDIDATE._read_contract_from_parent

        def swap_parent(target):
            output_parent.rename(moved_parent)
            output_parent.mkdir()
            return read_contract(target)

        with (
            mock.patch.object(
                CANDIDATE,
                "_read_contract_from_parent",
                side_effect=swap_parent,
            ),
            self.assertRaises(ProductionEmbeddingCandidateError) as caught,
        ):
            materialize_production_vector_build_contract(
                config=self.config,
                output_path=output_path,
            )
        self.assertEqual(
            "production_vector_contract_output_write_failed",
            caught.exception.code,
        )
        self.assertFalse((moved_parent / output_path.name).exists())
        self.assertFalse(output_path.exists())

    def test_public_production_apis_have_no_test_injection_parameters(self):
        self.assertEqual(
            {"config", "output_path"},
            set(inspect.signature(PUBLIC_MATERIALIZE).parameters),
        )
        expected = {"config", "production_vector_build_contract_path"}
        self.assertEqual(
            expected,
            set(inspect.signature(PUBLIC_VALIDATE).parameters),
        )
        self.assertEqual(
            expected,
            set(inspect.signature(PUBLIC_BUILD).parameters),
        )
        self.assertNotIn("EmbeddingCandidateRecord", CANDIDATE.__all__)

    def test_public_apis_reject_direct_and_forged_context_before_side_effects(self):
        output_path = self.root / "forged-public-output.json"
        fake_contexts = (None, True, {"formal": True}, object())
        for fake_context in fake_contexts:
            with (
                self.subTest(context=type(fake_context).__name__),
                mock.patch.object(
                    CANDIDATE, "_ACTIVE_BOOTSTRAP_CONTEXT", fake_context
                ),
                mock.patch.object(
                    CANDIDATE,
                    "_materialize_production_vector_build_contract_impl",
                ) as materialize_impl,
                mock.patch.object(
                    CANDIDATE,
                    "_validate_production_embedding_candidate_impl",
                ) as validate_impl,
                mock.patch.object(
                    CANDIDATE,
                    "_build_production_embedding_candidate_impl",
                ) as build_impl,
            ):
                with self.assertRaises(ProductionEmbeddingCandidateError) as error:
                    PUBLIC_MATERIALIZE(config=object(), output_path=output_path)
                self.assertEqual("exact_release_bootstrap_required", error.exception.code)
                with self.assertRaises(ProductionEmbeddingCandidateError):
                    PUBLIC_VALIDATE(
                        config=object(),
                        production_vector_build_contract_path=object(),
                    )
                with self.assertRaises(ProductionEmbeddingCandidateError):
                    PUBLIC_BUILD(
                        config=object(),
                        production_vector_build_contract_path=object(),
                    )
                materialize_impl.assert_not_called()
                validate_impl.assert_not_called()
                build_impl.assert_not_called()
                self.assertFalse(output_path.exists())
                self.assertFalse((self.root / "calls.log").exists())

        stdout = io.StringIO()
        with (
            mock.patch.object(
                ProductionEmbeddingCandidateConfig,
                "load",
                side_effect=AssertionError("config read before bootstrap"),
            ),
            contextlib.redirect_stdout(stdout),
            self.assertRaises(ProductionEmbeddingCandidateError),
        ):
            CANDIDATE._run_cli(["--help"])
        self.assertEqual("", stdout.getvalue())


    def test_production_vector_contract_is_required_and_externally_anchored(self):
        without_anchor = dict(self.environment)
        without_anchor.pop("KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256")
        with self.assertRaises(ProductionEmbeddingCandidateError) as missing_anchor:
            self._validate(environment=without_anchor)
        self.assertEqual(
            "production_vector_build_contract_hash_missing",
            missing_anchor.exception.code,
        )

        without_base_anchor = dict(self.environment)
        without_base_anchor.pop(
            "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
        )
        with self.assertRaises(ProductionEmbeddingCandidateError) as missing_base:
            self._validate(environment=without_base_anchor)
        self.assertEqual(
            "production_vector_base_suite_hash_missing",
            missing_base.exception.code,
        )

        missing_path = self.suite_root / "missing-contract.json"
        with self.assertRaises(ProductionEmbeddingCandidateError) as missing_contract:
            self._validate(production_vector_build_contract_path=missing_path)
        self.assertEqual(
            "production_vector_build_contract_unavailable",
            missing_contract.exception.code,
        )

        with self.production_vector_build_contract_path.open("ab") as handle:
            handle.write(b"drift")
        with self.assertRaises(ProductionEmbeddingCandidateError) as drift:
            self._validate()
        self.assertEqual(
            "production_vector_build_contract_hash_mismatch",
            drift.exception.code,
        )

    def test_anchor_failures_do_not_open_sqlite_or_graph(self):
        probes = (
            "_load_trusted_candidate_inputs",
            "inspect_authority_bm25_semantics",
            "load_scoped_graph_package",
        )
        for label, environment in (
            (
                "configured-contract-anchor-missing",
                {
                    key: value
                    for key, value in self.environment.items()
                    if key != "KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"
                },
            ),
            (
                "configured-contract-anchor-drift",
                {
                    **self.environment,
                    "KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256": "0" * 64,
                },
            ),
            (
                "base-suite-anchor-missing",
                {
                    key: value
                    for key, value in self.environment.items()
                    if key
                    != "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
                },
            ),
            (
                "base-suite-anchor-drift",
                {
                    **self.environment,
                    "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256": "0" * 64,
                },
            ),
        ):
            with self.subTest(label=label):
                patches = [
                    mock.patch.object(
                        CANDIDATE,
                        name,
                        side_effect=AssertionError(f"{name} must not be called"),
                    )
                    for name in probes
                ]
                with contextlib.ExitStack() as stack:
                    mocks = [stack.enter_context(patch) for patch in patches]
                    with self.assertRaises(ProductionEmbeddingCandidateError):
                        self._validate(environment=environment)
                self.assertTrue(all(item.call_count == 0 for item in mocks))

    def test_config_and_local_vector_drift_fails_before_reload_approval_or_data(self):
        value = json.loads(self.config_path.read_text(encoding="utf-8"))
        value["local_vector"].update(
            {
                "data_root": str(self.root / "changed-vector-data"),
                "metric": "dot",
                "top_k_max": 999,
                "chunk_index_name": "changed-chunks",
            }
        )
        self._write_json(self.config_path, value)
        changed = ProductionEmbeddingCandidateConfig.load(self.config_path)
        probes = (
            "_reload_bound_config",
            "_validate_approval",
            "_load_trusted_candidate_inputs",
            "inspect_authority_bm25_semantics",
            "load_scoped_graph_package",
        )
        patches = [
            mock.patch.object(
                CANDIDATE,
                name,
                side_effect=AssertionError(f"{name} must not be called"),
            )
            for name in probes
        ]
        with contextlib.ExitStack() as stack:
            mocks = [stack.enter_context(patch) for patch in patches]
            with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                self._validate(config=changed)
        self.assertEqual(
            "production_vector_build_contract_config_mismatch",
            caught.exception.code,
        )
        self.assertTrue(all(item.call_count == 0 for item in mocks))

    def test_reanchored_local_vector_drift_fails_against_stop_b_approval(self):
        approved_production = self._approved_local_vector_production()
        value = json.loads(self.config_path.read_text(encoding="utf-8"))
        value["local_vector"].update(
            {
                "data_root": str(self.root / "changed-vector-data"),
                "metric": "dot",
                "top_k_max": 999,
                "chunk_index_name": "changed-chunks",
            }
        )
        self._write_json(self.config_path, value)
        self.config = ProductionEmbeddingCandidateConfig.load(self.config_path)
        changed_contract = json.loads(
            self.production_vector_build_contract_path.read_text(encoding="utf-8")
        )
        changed_contract["candidate_config_sha256"] = self.config.sha256
        changed_contract["local_vector_contract"]["configured"] = (
            CANDIDATE._local_vector_build_contract(self.config, self.identity)
        )
        self._write_json(self.production_vector_build_contract_path, changed_contract)
        self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = sha256_file(
            self.production_vector_build_contract_path
        )

        with self.assertRaises(ProviderApprovalError) as caught:
            self._validate(
                approval_validator=lambda _config: approved_production,
            )
        self.assertEqual(
            "production_vector_approval_binding_mismatch",
            caught.exception.code,
        )
        self.assertFalse((self.root / "calls.log").exists())

    def test_loaded_candidate_config_hash_drift_is_a_config_error(self):
        self.config_path.write_bytes(self.config_path.read_bytes() + b" ")
        probes = (
            "_validate_approval",
            "_load_trusted_candidate_inputs",
            "inspect_authority_bm25_semantics",
            "load_scoped_graph_package",
        )
        patches = [
            mock.patch.object(
                CANDIDATE,
                name,
                side_effect=AssertionError(f"{name} must not be called"),
            )
            for name in probes
        ]
        with contextlib.ExitStack() as stack:
            mocks = [stack.enter_context(patch) for patch in patches]
            with self.assertRaises(ProductionEmbeddingCandidateConfigError) as caught:
                self._validate()
        self.assertEqual("candidate_config_hash_mismatch", caught.exception.code)
        self.assertTrue(all(item.call_count == 0 for item in mocks))

    def test_contract_path_replacement_during_descriptor_read_fails_closed(self):
        contract_path = self.production_vector_build_contract_path
        original_path = self.root / "production-vector-contract-original.json"
        replacement_path = self.root / "production-vector-contract-replacement.json"
        shutil.copyfile(contract_path, replacement_path)
        real_pread = os.pread
        replaced = False

        def read_then_replace(descriptor, size, offset):
            nonlocal replaced
            payload = real_pread(descriptor, size, offset)
            descriptor_stat = os.fstat(descriptor)
            contract_stat = os.stat(contract_path, follow_symlinks=False)
            if (
                not replaced
                and descriptor_stat.st_dev == contract_stat.st_dev
                and descriptor_stat.st_ino == contract_stat.st_ino
            ):
                replaced = True
                os.replace(contract_path, original_path)
                os.replace(replacement_path, contract_path)
            return payload

        try:
            with mock.patch("rag_store.runtime_sqlite_reader.os.pread", read_then_replace):
                with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                    self._validate()
            self.assertTrue(replaced)
            self.assertEqual(
                "production_vector_build_contract_unavailable",
                caught.exception.code,
            )
            self.assertFalse((self.root / "calls.log").exists())
        finally:
            if original_path.exists():
                if contract_path.exists():
                    os.replace(contract_path, replacement_path)
                os.replace(original_path, contract_path)

    def test_bm25_manifest_swap_during_semantic_validation_fails_closed(self):
        valid_payload = self.bm25_manifest_path.read_bytes()
        invalid = json.loads(valid_payload)
        invalid["tokenizer"] = "not-trigram"
        self._write_json(self.bm25_manifest_path, invalid)
        invalid_payload = self.bm25_manifest_path.read_bytes()
        self._reseal_production_vector_contract_data(rematerialize=False)
        self._reanchor_configured_contract_for_invalid_base_attack()
        validate_semantics = CANDIDATE._validate_contract_data_semantics

        def swap_during_semantics(**kwargs):
            self.bm25_manifest_path.write_bytes(valid_payload)
            try:
                return validate_semantics(**kwargs)
            finally:
                self.bm25_manifest_path.write_bytes(invalid_payload)

        with mock.patch.object(
            CANDIDATE,
            "_validate_contract_data_semantics",
            side_effect=swap_during_semantics,
        ):
            with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                self._validate()
        self.assertEqual("bm25_manifest_invalid", caught.exception.code)
        self.assertEqual(invalid_payload, self.bm25_manifest_path.read_bytes())
        self.assertFalse((self.root / "calls.log").exists())

    def test_complete_data_reseal_with_new_contract_anchor_still_fails_base_anchor(self):
        original_base_anchor = self.environment[
            "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
        ]
        current = self._reseal_complete_data_chain()
        self.assertNotEqual(
            original_base_anchor,
            sha256_file(self.base_suite_manifest_path),
        )
        self.assertEqual(
            self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"],
            sha256_file(self.production_vector_build_contract_path),
        )
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            self._validate(config=current)
        self.assertEqual(
            "production_vector_base_suite_hash_mismatch",
            caught.exception.code,
        )
        self.assertFalse((self.root / "calls.log").exists())

    def test_production_vector_contract_rejects_resealed_identity_and_aliases(self):
        original = json.loads(
            self.production_vector_build_contract_path.read_text(encoding="utf-8")
        )
        mutations = {
            "identity": lambda value: value["production_embedding_identity"].update(
                {"model": "substituted-model"}
            ),
            "identity-api-version": lambda value: value[
                "production_embedding_identity"
            ].update({"api_version": "substituted-api"}),
            "identity-input-type": lambda value: value[
                "production_embedding_identity"
            ].update({"input_type": "substituted-input"}),
            "identity-sha256": lambda value: value[
                "production_embedding_identity"
            ].update({"identity_sha256": "0" * 64}),
            "data-alias": lambda value: value["sealed_inputs"]["files"][0].update(
                {"path": "./authority/authority-manifest.json"}
            ),
            "manifest-omission": lambda value: value["sealed_inputs"].pop(
                "bm25_manifest_sha256"
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                contract = json.loads(json.dumps(original))
                mutate(contract)
                self._write_json(self.production_vector_build_contract_path, contract)
                environment = dict(self.environment)
                environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = sha256_file(
                    self.production_vector_build_contract_path
                )
                with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                    self._validate(environment=environment)
                self.assertIn(
                    caught.exception.code,
                    {
                        "production_vector_build_contract_config_mismatch",
                        "production_vector_build_contract_binding_mismatch",
                        "production_vector_build_contract_invalid",
                    },
                )

    def test_production_contract_rejects_path_aliases_and_hardlinks(self):
        original = json.loads(
            self.production_vector_build_contract_path.read_text(encoding="utf-8")
        )

        def builder_alias(value, replacement):
            value["builder"]["files"][0]["path"] = replacement
            value["builder"]["file_set_sha256"] = record_set_sha256(
                value["builder"]["files"]
            )

        mutations = {
            "leading-dot": lambda value: builder_alias(
                value, "./deploy/cloud_v2/__init__.py"
            ),
            "intermediate-dot": lambda value: builder_alias(
                value, "deploy/./cloud_v2/__init__.py"
            ),
            "trailing-slash": lambda value: value["sealed_inputs"]["files"][
                0
            ].update({"path": "authority/authority-manifest.json/"}),
            "case-alias": lambda value: builder_alias(
                value, "Deploy/cloud_v2/__init__.py"
            ),
            "nfd-alias": lambda value: value["source_scope"]["files"][0].update(
                {"relative_path": "cafe\u0301.txt"}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = json.loads(json.dumps(original))
                mutate(changed)
                self._write_json(self.production_vector_build_contract_path, changed)
                environment = {
                    **self.environment,
                    "KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256": sha256_file(
                        self.production_vector_build_contract_path
                    ),
                }
                with self.assertRaises(ProductionEmbeddingCandidateError):
                    self._validate(environment=environment)

        self._write_json(self.production_vector_build_contract_path, original)
        alias = self.root / "production-vector-build-contract-hardlink.json"
        os.link(self.production_vector_build_contract_path, alias)
        try:
            with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                self._validate(production_vector_build_contract_path=alias)
            self.assertEqual(
                "production_vector_build_contract_unavailable",
                caught.exception.code,
            )
        finally:
            alias.unlink()

    def test_materializer_rejects_builder_file_omission_after_reseal(self):
        omitted = "deploy/cloud_v2/source_scope.py"
        allowlist_path = self.suite_root / "builder-file-allowlist.json"
        allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
        allowlist["files"].remove(omitted)
        self._write_json(allowlist_path, allowlist)
        pending = json.loads(self.base_contract_path.read_text(encoding="utf-8"))
        pending["builder"]["files"] = [
            record
            for record in pending["builder"]["files"]
            if record["path"] != omitted
        ]
        pending["builder"]["file_allowlist_sha256"] = sha256_file(
            allowlist_path
        )
        pending["builder"]["file_set_sha256"] = record_set_sha256(
            pending["builder"]["files"]
        )
        self._write_json(self.base_contract_path, pending)
        self._reseal_base_suite(update_anchor=True)
        current = ProductionEmbeddingCandidateConfig.load(self.config_path)
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            materialize_production_vector_build_contract(
                config=current,
                output_path=self.root / "omitted-builder-contract.json",
            )
        self.assertEqual(
            "production_vector_build_contract_invalid",
            caught.exception.code,
        )

    def test_production_vector_contract_rejects_integer_boolean_aliases(self):
        original = json.loads(
            self.production_vector_build_contract_path.read_text(encoding="utf-8")
        )
        mutations = {
            "false-as-zero": lambda value: value["output_contract"].update(
                {"active_write_authorized": 0}
            ),
            "true-as-one": lambda value: value["approval_contract"].update(
                {"production_build_authorized": 1}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                contract = json.loads(json.dumps(original))
                mutate(contract)
                self._write_json(self.production_vector_build_contract_path, contract)
                environment = dict(self.environment)
                environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = (
                    sha256_file(self.production_vector_build_contract_path)
                )
                with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                    self._validate(environment=environment)
                self.assertEqual(
                    "production_vector_build_contract_unapproved",
                    caught.exception.code,
                )

    def test_dimension_one_contract_rejects_json_true_alias(self):
        self.identity = EmbeddingIdentity(
            provider=self.identity.provider,
            base_url=self.identity.base_url,
            region=self.identity.region,
            model=self.identity.model,
            model_version=self.identity.model_version,
            api_version=self.identity.api_version,
            dimension=1,
            normalization=self.identity.normalization,
            input_type=self.identity.input_type,
        )
        provider = json.loads(self.provider_config.path.read_text(encoding="utf-8"))
        provider["embedding"]["identity"]["dimension"] = 1
        provider["embedding"]["identity_sha256"] = self.identity.sha256
        self._write_json(self.provider_config.path, provider)
        self.provider_config = ProviderRuntimeConfig.load(self.provider_config.path)
        self._write_json(self.config_path, self._candidate_config_value())
        self.config = ProductionEmbeddingCandidateConfig.load(self.config_path)
        self._rematerialize_production_vector_contract()

        contract = json.loads(
            self.production_vector_build_contract_path.read_text(encoding="utf-8")
        )
        contract["production_embedding_identity"]["dimension"] = True
        self._write_json(self.production_vector_build_contract_path, contract)
        self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = sha256_file(
            self.production_vector_build_contract_path
        )
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            self._validate()
        self.assertEqual(
            "production_vector_build_contract_config_mismatch",
            caught.exception.code,
        )

    def test_validate_and_build_both_consume_production_vector_contract(self):
        with mock.patch.object(
            CANDIDATE,
            "_validate_production_vector_build_contract",
            side_effect=ProductionEmbeddingCandidateError(
                "production_vector_build_contract_not_consumed"
            ),
        ) as validator:
            with self.assertRaises(ProductionEmbeddingCandidateError) as validate_error:
                self._validate()
            self.assertEqual(
                "production_vector_build_contract_not_consumed",
                validate_error.exception.code,
            )
            with self.assertRaises(ProductionEmbeddingCandidateError) as build_error:
                self._build()
            self.assertEqual(
                "production_vector_build_contract_not_consumed",
                build_error.exception.code,
            )
        self.assertEqual(2, validator.call_count)

    def test_partial_entity_response_writes_no_candidate(self):
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            self._build(executor=self._executor(partial_purpose="entity"))
        self.assertEqual("entity_embedding_failed", caught.exception.code)
        self.assertFalse(self.config.vector_contract.candidate_release_dir.exists())
        self.assertFalse(self.config.vector_contract.active_release_dir.exists())
        self.assertNotIn(self.secret, repr(caught.exception))
        ledgers = caught.exception.ledger_dict()
        self.assertEqual(3, len(ledgers["chunk_ledger"]))
        self.assertEqual(1, len(ledgers["entity_ledger"]))
        serialized = json.dumps(ledgers, sort_keys=True)
        self.assertNotIn(self.secret, serialized)
        self.assertNotIn("alpha entity", serialized)
        self.assertNotIn("bravo entity", serialized)

    def test_build_cli_emits_sanitized_failure_ledgers(self):
        output = io.StringIO()
        partial = self._executor(partial_purpose="entity")
        with (
            mock.patch.object(
                CANDIDATE,
                "ProviderHTTPTransport",
                side_effect=lambda **kwargs: RealProviderHTTPTransport(
                    executor=partial,
                    **kwargs,
                ),
            ),
            contextlib.redirect_stdout(output),
        ):
            rc = CANDIDATE._run_cli_impl(
                [
                    "build",
                    "--config",
                    str(self.config_path),
                    "--contract",
                    str(self.production_vector_build_contract_path),
                ]
            )
        self.assertEqual(1, rc)
        value = json.loads(output.getvalue())
        self.assertFalse(value["ok"])
        self.assertEqual(3, len(value["chunk_ledger"]))
        self.assertEqual(1, len(value["entity_ledger"]))
        self.assertNotIn(self.secret, output.getvalue())
        self.assertNotIn("alpha entity", output.getvalue())
        self.assertNotIn("bravo entity", output.getvalue())

    def test_network_and_approval_fail_before_disclosure(self):
        network_disabled = dict(self.environment)
        network_disabled.pop("KG_PROVIDER_NETWORK_MODE")
        with self.assertRaises(ProviderBootstrapError) as network_error:
            self._build(environment=network_disabled)
        self.assertEqual("provider_network_disabled", network_error.exception.code)
        self.assertFalse((self.root / "calls.log").exists())

        def reject(_config):
            raise ProviderApprovalError("provider_approval_missing")

        with self.assertRaises(ProviderApprovalError):
            self._build(approval_validator=reject)
        self.assertFalse((self.root / "calls.log").exists())

    def test_default_approval_validator_receives_explicit_environment(self):
        observed = {}
        approved_production = self._approved_local_vector_production()

        def validate(config, environment=None):
            observed["config"] = config
            observed["environment"] = environment

        with (
            mock.patch.object(CANDIDATE, "validate_production_approval", validate),
            mock.patch.object(
                CANDIDATE,
                "_load_approved_local_vector_production",
                return_value=approved_production,
            ) as load_approved,
            mock.patch.object(CANDIDATE, "LocalVectorStoreAdapter"),
        ):
            validation = validate_production_embedding_candidate(
                config=self.config,
                production_vector_build_contract_path=(
                    self.production_vector_build_contract_path
                ),
            )
        self.assertEqual(R9_SOURCE_SCOPE["source_count"], validation.chunk_count)
        self.assertEqual(self.provider_config, observed["config"])
        self.assertIs(os.environ, observed["environment"])
        load_approved.assert_called_once_with(self.provider_config)

    def test_approved_capacity_binds_actual_counts_and_f32_bytes(self):
        minimum_bytes = (
            (R9_SOURCE_SCOPE["source_count"] + 2) * self.identity.dimension * 4
        )
        cases = {
            "chunk_count": (
                {"chunk_capacity": R9_SOURCE_SCOPE["source_count"] - 1},
                "production_vector_capacity_exceeded",
            ),
            "entity_count": (
                {"entity_capacity": 1},
                "production_vector_capacity_exceeded",
            ),
            "memory_bytes": (
                {"memory_budget_bytes": minimum_bytes - 1},
                "production_vector_memory_budget_exceeded",
            ),
            "disk_bytes": (
                {"disk_budget_bytes": minimum_bytes - 1},
                "production_vector_disk_budget_exceeded",
            ),
            "typed_capacity": (
                {"chunk_capacity": True},
                "production_vector_capacity_invalid",
            ),
        }
        for label, (mutation, expected_code) in cases.items():
            with self.subTest(label=label):
                approved = self._approved_local_vector_production()
                approved["capacity"].update(mutation)
                identity, _policy, _bindings = CANDIDATE._binding_contract(
                    self.config.provider_config,
                    self.config.vector_contract,
                )
                binding = CANDIDATE._load_base_suite_binding(
                    self.config,
                    self.environment[
                        "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
                    ],
                )
                configured = CANDIDATE._configured_contract(
                    binding,
                    self.config,
                    identity,
                    approved,
                )
                self._write_json(
                    self.production_vector_build_contract_path,
                    configured,
                )
                self.environment["KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"] = (
                    sha256_file(self.production_vector_build_contract_path)
                )
                with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                    self._validate(
                        approval_validator=lambda _config: approved,
                    )
                self.assertEqual(expected_code, caught.exception.code)
                self.assertFalse((self.root / "calls.log").exists())

    def test_strict_loader_rejects_extra_duplicate_and_hash_drift(self):
        value = self._candidate_config_value()
        value["unexpected"] = True
        extra = self.root / "extra.json"
        self._write_json(extra, value)
        with self.assertRaises(ProductionEmbeddingCandidateConfigError):
            ProductionEmbeddingCandidateConfig.load(extra)

        duplicate = self.root / "duplicate.json"
        duplicate.write_text(
            '{"schema_version":"kg-production-embedding-candidate-config-v2",'
            '"schema_version":"kg-production-embedding-candidate-config-v2"}\n',
            encoding="utf-8",
        )
        with self.assertRaises(ProductionEmbeddingCandidateConfigError):
            ProductionEmbeddingCandidateConfig.load(duplicate)

        provider = json.loads(self.provider_config.path.read_text(encoding="utf-8"))
        provider["embedding"]["identity"]["model"] = "mutated-model"
        self._write_json(self.provider_config.path, provider)
        with self.assertRaises(ProductionEmbeddingCandidateConfigError):
            validate_production_embedding_candidate(
                config=self.config,
                production_vector_build_contract_path=(
                    self.production_vector_build_contract_path
                ),
            )
        self.assertFalse((self.root / "calls.log").exists())

    def test_authority_scope_must_equal_frozen_revision_a_r9(self):
        authority = json.loads(
            self.authority_manifest_path.read_text(encoding="utf-8")
        )
        mutations = {
            "arbitrary_mapping": {"schema_version": "fixture-scope-v1"},
            "source_count": {**R9_SOURCE_SCOPE, "source_count": 34},
            "source_count_float": {**R9_SOURCE_SCOPE, "source_count": 35.0},
            "unchanged_count": {
                **R9_SOURCE_SCOPE,
                "unchanged_source_count": 27,
            },
            "redacted_count": {
                **R9_SOURCE_SCOPE,
                "approved_redacted_source_count": 8,
            },
            "source_manifest_hash": {
                **R9_SOURCE_SCOPE,
                "source_manifest_sha256": "0" * 64,
            },
            "allowlist_hash": {
                **R9_SOURCE_SCOPE,
                "allowlist_sha256": "0" * 64,
            },
            "source_dlp_hash": {
                **R9_SOURCE_SCOPE,
                "source_dlp_receipt_sha256": "0" * 64,
            },
            "stop_a_hash": {
                **R9_SOURCE_SCOPE,
                "stop_a_receipt_sha256": "0" * 64,
            },
            "extra_field": {**R9_SOURCE_SCOPE, "unexpected": True},
        }
        for label, source_scope in mutations.items():
            with self.subTest(label=label):
                changed = {**authority, "source_scope": source_scope}
                current = self._candidate_with_authority_manifest(
                    changed,
                    rematerialize=False,
                )
                self._reanchor_configured_contract_for_invalid_base_attack()
                with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                    validate_production_embedding_candidate(
                        config=current,
                        production_vector_build_contract_path=(
                            self.production_vector_build_contract_path
                        ),
                    )
                self.assertEqual("authority_manifest_invalid", caught.exception.code)
        with self.subTest(label="authority_source_count"):
            truncated = json.loads(json.dumps(authority))
            truncated["sources"] = truncated["sources"][:-1]
            truncated["counts"] = {
                "documents": 34,
                "chunks": 34,
                "provenance": 34,
            }
            current = self._candidate_with_authority_manifest(
                truncated,
                rematerialize=False,
            )
            self._reanchor_configured_contract_for_invalid_base_attack()
            with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                validate_production_embedding_candidate(
                    config=current,
                    production_vector_build_contract_path=(
                        self.production_vector_build_contract_path
                    ),
                )
            self.assertEqual("authority_manifest_invalid", caught.exception.code)
        self.assertFalse((self.root / "calls.log").exists())

    def test_sqlite_reader_rejects_path_replacement_after_descriptor_open(self):
        replacement = self._replacement_authority_database()
        original = self.root / "rag_chunks-original.db"
        reader = ReadOnlyAuthorityReader(self.authority_database_path)
        self.assertEqual(self.authority_database_sha256, reader.database_sha256)
        os.replace(self.authority_database_path, original)
        os.replace(replacement, self.authority_database_path)
        try:
            with self.assertRaises(ReadOnlySQLiteError):
                reader.embedding_chunk_rows()
        finally:
            reader.close()
            os.replace(self.authority_database_path, replacement)
            os.replace(original, self.authority_database_path)

    def test_authority_replace_execute_restore_attack_fails_closed(self):
        replacement = self._replacement_authority_database()
        original = self.root / "rag_chunks-original.db"
        authority_path = self.authority_database_path
        real_reader = CANDIDATE.ReadOnlyAuthorityReader

        class ReplaceThenRestoreReader:
            def __init__(inner, database_path):
                os.replace(authority_path, original)
                os.replace(replacement, authority_path)
                try:
                    inner.delegate = real_reader(database_path)
                except Exception:
                    os.replace(authority_path, replacement)
                    os.replace(original, authority_path)
                    raise

            def __getattr__(inner, name):
                return getattr(inner.delegate, name)

            def close(inner):
                try:
                    inner.delegate.close()
                finally:
                    os.replace(authority_path, replacement)
                    os.replace(original, authority_path)

        with mock.patch.object(
            CANDIDATE,
            "ReadOnlyAuthorityReader",
            ReplaceThenRestoreReader,
        ):
            with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                validate_production_embedding_candidate(
                    config=self.config,
                    production_vector_build_contract_path=(
                        self.production_vector_build_contract_path
                    ),
                )
        self.assertEqual("authority_database_hash_mismatch", caught.exception.code)
        self.assertEqual(self.authority_database_sha256, sha256_file(authority_path))
        self.assertFalse((self.root / "calls.log").exists())

    def test_authority_database_and_graph_tamper_fail_before_disclosure(self):
        with self.authority_database_path.open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaises(ProductionEmbeddingCandidateError) as authority_error:
            validate_production_embedding_candidate(
                config=self.config,
                production_vector_build_contract_path=(
                    self.production_vector_build_contract_path
                ),
            )
        self.assertEqual(
            "production_vector_build_contract_data_mismatch",
            authority_error.exception.code,
        )
        self.assertFalse((self.root / "calls.log").exists())

    def test_graph_data_hash_tamper_fails_before_disclosure(self):
        with self.graph_data_path.open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            validate_production_embedding_candidate(
                config=self.config,
                production_vector_build_contract_path=(
                    self.production_vector_build_contract_path
                ),
            )
        self.assertEqual(
            "production_vector_build_contract_data_mismatch",
            caught.exception.code,
        )
        self.assertFalse((self.root / "calls.log").exists())

    def test_graph_change_after_validation_fails_before_disclosure(self):
        load_package = CANDIDATE.load_scoped_graph_package

        def load_then_change(*args, **kwargs):
            package = load_package(*args, **kwargs)
            with self.graph_data_path.open("ab") as handle:
                handle.write(b"changed-after-validation")
            return package

        with mock.patch.object(
            CANDIDATE,
            "load_scoped_graph_package",
            side_effect=load_then_change,
        ):
            with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                validate_production_embedding_candidate(
                    config=self.config,
                    production_vector_build_contract_path=(
                        self.production_vector_build_contract_path
                    ),
                )
        self.assertEqual("source_inputs_changed", caught.exception.code)
        self.assertFalse((self.root / "calls.log").exists())

    def test_missing_sqlite_provenance_is_not_caller_patchable(self):
        connection = sqlite3.connect(self.authority_database_path)
        try:
            connection.execute(
                "DELETE FROM chunk_provenance WHERE chunk_id=?",
                ("chunk:" + "b" * 40,),
            )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        new_database_sha256 = sha256_file(self.authority_database_path)
        authority = json.loads(
            self.authority_manifest_path.read_text(encoding="utf-8")
        )
        authority["database"]["sha256"] = new_database_sha256
        authority["release_id"] = (
            f"rag-authority:fixture:{new_database_sha256[:16]}"
        )
        self._write_json(self.authority_manifest_path, authority)
        new_authority_sha256 = sha256_file(self.authority_manifest_path)
        bm25 = json.loads(self.bm25_manifest_path.read_text(encoding="utf-8"))
        bm25["authority_release_id"] = authority["release_id"]
        bm25["authority_database_sha256"] = new_database_sha256
        self._write_json(self.bm25_manifest_path, bm25)
        config = self._candidate_config_value()
        config["authority"]["sha256"] = new_authority_sha256
        config["local_vector"]["authority_manifest_sha256"] = (
            new_authority_sha256
        )
        config["local_vector"]["data_release_id"] = local_data_release_id(
            new_database_sha256,
            self.identity.sha256,
        )
        self._write_json(self.config_path, config)
        self.config = ProductionEmbeddingCandidateConfig.load(self.config_path)
        self._reseal_production_vector_contract_data(rematerialize=False)
        self._reanchor_configured_contract_for_invalid_base_attack()
        current = self.config
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            validate_production_embedding_candidate(
                config=current,
                production_vector_build_contract_path=(
                    self.production_vector_build_contract_path
                ),
            )
        self.assertEqual("authority_coverage_mismatch", caught.exception.code)
        self.assertFalse((self.root / "calls.log").exists())

    def test_sqlite_provenance_must_be_source_bound_and_approved(self):
        mutations = {
            "cross-document": (
                "UPDATE chunk_provenance SET document_source_id='docsrc:1' "
                "WHERE chunk_id=?",
                (),
            ),
            "source-hash": (
                "UPDATE chunk_provenance SET source_sha256=? WHERE chunk_id=?",
                ("2" * 64,),
            ),
            "import-run": (
                "UPDATE chunk_provenance SET import_run_id='other-run' "
                "WHERE chunk_id=?",
                (),
            ),
            "review-status": (
                "UPDATE chunk_provenance SET review_status='pending' "
                "WHERE chunk_id=?",
                (),
            ),
            "evidence": (
                "UPDATE chunk_provenance SET evidence_json='{}' WHERE chunk_id=?",
                (),
            ),
            "evidence-source-hash": (
                "UPDATE chunk_provenance SET evidence_json=? WHERE chunk_id=?",
                (
                    json.dumps(
                        {
                            "extractor": "cloud-v2-source-extractor-v1",
                            "source_text_sha256": "0" * 64,
                            "unit_ordinal": 0,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            ),
        }
        alpha_chunk = "chunk:" + "a" * 40
        expected_source_text_sha256 = {
            name: hashlib.sha256(text.encode("utf-8") + b"\x00").hexdigest()
            for name, text, _content_type, _suffix, _source_hash in self._documents()
        }
        for name, (statement, parameters) in mutations.items():
            with self.subTest(name=name):
                database_path = self.root / f"authority-{name}.db"
                shutil.copyfile(self.authority_database_path, database_path)
                connection = sqlite3.connect(database_path)
                try:
                    connection.execute(statement, (*parameters, alpha_chunk))
                    connection.commit()
                    connection.execute("VACUUM")
                finally:
                    connection.close()
                with self.assertRaises(SQLiteSemanticValidationError) as caught:
                    CANDIDATE.inspect_authority_bm25_semantics(
                        database_path,
                        self.bm25_index_path,
                        expected_source_text_sha256=expected_source_text_sha256,
                    )
                self.assertEqual("authority_provenance_mismatch", caught.exception.code)

    def test_actual_per_document_chunk_counts_must_match_manifest(self):
        extra_chunk_id = "chunk:" + "e" * 40
        connection = sqlite3.connect(self.authority_database_path)
        try:
            connection.execute(
                """INSERT INTO chunks (
                       chunk_id, text, doc_name, chunk_index, created_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    extra_chunk_id,
                    "extra alpha",
                    "alpha.txt",
                    1,
                    "2026-09-03T00:00:00Z",
                ),
            )
            connection.execute(
                """INSERT INTO chunk_provenance (
                       chunk_id, document_source_id, source_sha256,
                       import_run_id, pdf_page_start, pdf_page_end,
                       content_type, confidence, review_status,
                       evidence_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    extra_chunk_id,
                    "docsrc:0",
                    "1" * 64,
                    "import-fixture",
                    1,
                    1,
                    "textbook",
                    1.0,
                    "approved-source-extracted",
                    json.dumps(
                        {
                            "extractor": "cloud-v2-source-extractor-v1",
                            "source_text_sha256": hashlib.sha256(
                                b"alpha\x00"
                            ).hexdigest(),
                            "unit_ordinal": 1,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "2026-09-03T00:00:00Z",
                ),
            )
            connection.execute(
                "UPDATE documents SET chunk_count=2 WHERE doc_name='bravo.txt'"
            )
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        database_sha256 = sha256_file(self.authority_database_path)
        manifest = json.loads(
            self.authority_manifest_path.read_text(encoding="utf-8")
        )
        manifest["database"]["sha256"] = database_sha256
        manifest["release_id"] = f"rag-authority:fixture:{database_sha256[:16]}"
        manifest["counts"]["chunks"] += 1
        manifest["counts"]["provenance"] += 1
        for source in manifest["sources"]:
            if source["relative_path"] == "bravo.txt":
                source["chunk_count"] = 2
        bm25 = json.loads(self.bm25_manifest_path.read_text(encoding="utf-8"))
        bm25["authority_release_id"] = manifest["release_id"]
        bm25["authority_database_sha256"] = database_sha256
        self._write_json(self.bm25_manifest_path, bm25)
        current = self._candidate_with_authority_manifest(
            manifest,
            rematerialize=False,
        )
        value = self._candidate_config_value()
        current_value = json.loads(self.config_path.read_text(encoding="utf-8"))
        value["authority"] = current_value["authority"]
        value["local_vector"]["authority_manifest_sha256"] = current_value[
            "local_vector"
        ]["authority_manifest_sha256"]
        value["local_vector"]["data_release_id"] = local_data_release_id(
            database_sha256,
            self.identity.sha256,
        )
        self._write_json(self.config_path, value)
        self.config = ProductionEmbeddingCandidateConfig.load(self.config_path)
        self._reanchor_configured_contract_for_invalid_base_attack()
        current = self.config

        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            validate_production_embedding_candidate(
                config=current,
                production_vector_build_contract_path=(
                    self.production_vector_build_contract_path
                ),
            )
        self.assertEqual("authority_coverage_mismatch", caught.exception.code)

    def test_authority_manifest_rejects_schema_drift_and_boolean_zeroes(self):
        original = json.loads(
            self.authority_manifest_path.read_text(encoding="utf-8")
        )
        mutations = (
            ("sqlite-user-version", ("database", "sqlite_user_version"), 2),
            ("foreign-key-bool", ("database", "foreign_key_violation_count"), False),
            ("network-bool", ("build", "network_calls"), False),
        )
        for name, path, value in mutations:
            with self.subTest(name=name):
                manifest = json.loads(json.dumps(original))
                manifest[path[0]][path[1]] = value
                current = self._candidate_with_authority_manifest(
                    manifest,
                    rematerialize=False,
                )
                self._reseal_unvalidated_configured_contract_for_attack()
                with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
                    validate_production_embedding_candidate(
                        config=current,
                        production_vector_build_contract_path=(
                            self.production_vector_build_contract_path
                        ),
                    )
                self.assertEqual("authority_manifest_invalid", caught.exception.code)

    def test_runtime_authority_schema_matches_candidate_builder(self):
        self.assertEqual(BUILDER_AUTHORITY_SCHEMA_SQL, RUNTIME_AUTHORITY_SCHEMA_SQL)

    def test_preexisting_candidate_fails_closed_without_active_switch(self):
        candidate = self.config.vector_contract.candidate_release_dir
        candidate.mkdir(parents=True)
        marker = candidate / "existing.txt"
        marker.write_text("preserve", encoding="ascii")
        with self.assertRaises(ProductionEmbeddingCandidateError) as caught:
            validate_production_embedding_candidate(
                config=self.config,
                production_vector_build_contract_path=(
                    self.production_vector_build_contract_path
                ),
            )
        self.assertEqual("candidate_already_exists", caught.exception.code)
        self.assertEqual("preserve", marker.read_text(encoding="ascii"))
        self.assertFalse(self.config.vector_contract.active_release_dir.exists())

    def test_materialize_cli_writes_suite_external_configured_contract(self):
        output_path = self.root / "cli-production-vector-build-contract-v2.json"
        observed = {}

        def approved(config, environment=None):
            observed["config"] = config
            observed["environment"] = environment
            return self._approved(config)

        stdout = io.StringIO()
        with (
            mock.patch.object(CANDIDATE, "validate_production_approval", approved),
            mock.patch.dict(os.environ, self.environment, clear=True),
            contextlib.redirect_stdout(stdout),
        ):
            rc = CANDIDATE._run_cli_impl(
                [
                    "materialize",
                    "--config",
                    str(self.config_path),
                    "--output",
                    str(output_path),
                ]
            )
        self.assertEqual(0, rc)
        output = json.loads(stdout.getvalue())
        self.assertEqual("materialize", output["command"])
        self.assertTrue(output["ok"])
        self.assertTrue(output["candidate_only"])
        self.assertEqual(0, output["network_calls"])
        self.assertEqual(35, output["source_count"])
        self.assertEqual(sha256_file(output_path), output["contract_sha256"])
        self.assertEqual(
            self.base_suite_manifest_sha256,
            output["base_suite_manifest_sha256"],
        )
        self.assertEqual(self.provider_config, observed["config"])
        self.assertIs(os.environ, observed["environment"])

    def test_validate_and_build_cli_contracts_are_deterministic(self):
        observed = {}

        def approved(config, environment=None):
            observed["config"] = config
            observed["environment"] = environment
            return self._approved(config)

        validate_stdout = io.StringIO()
        with (
            mock.patch.object(CANDIDATE, "validate_production_approval", approved),
            mock.patch.dict(os.environ, self.environment, clear=True),
            contextlib.redirect_stdout(validate_stdout),
        ):
            rc = CANDIDATE._run_cli_impl(
                [
                    "validate",
                    "--config",
                    str(self.config_path),
                    "--contract",
                    str(self.production_vector_build_contract_path),
                ]
            )
        self.assertEqual(0, rc)
        output = json.loads(validate_stdout.getvalue())
        self.assertTrue(output["ok"])
        self.assertEqual("validate", output["command"])
        self.assertTrue(output["candidate_only"])
        self.assertEqual(0, output["network_calls"])
        self.assertFalse(self.config.vector_contract.candidate_release_dir.exists())
        self.assertEqual(self.provider_config, observed["config"])
        self.assertIs(os.environ, observed["environment"])

        receipt = self._build()
        build_stdout = io.StringIO()
        with (
            mock.patch.object(
                CANDIDATE,
                "_build_production_embedding_candidate_impl",
                return_value=receipt,
            ),
            contextlib.redirect_stdout(build_stdout),
        ):
            rc = CANDIDATE._run_cli_impl(
                [
                    "build",
                    "--config",
                    str(self.config_path),
                    "--contract",
                    str(self.production_vector_build_contract_path),
                ]
            )
        self.assertEqual(0, rc)
        build_output = json.loads(build_stdout.getvalue())
        self.assertTrue(build_output["ok"])
        self.assertEqual("build", build_output["command"])
        self.assertTrue(build_output["candidate_only"])
        self.assertEqual(
            receipt.local_vector.manifest_sha256,
            build_output["local_vector_manifest_sha256"],
        )

    def test_empty_copied_no_pip_venv_capture_verify_smoke(self):
        fixture_names = (
            "KG_TEST_PRODUCTION_EMBEDDING_WHEELHOUSE",
            "KG_TEST_PRODUCTION_EMBEDDING_INSTALLER_PYTHON",
            "KG_TEST_PRODUCTION_EMBEDDING_INSTALLER_SHA256",
        )
        provided_fixture_names = tuple(
            name for name in fixture_names if name in self.environment
        )
        if provided_fixture_names and len(provided_fixture_names) != len(
            fixture_names
        ):
            self.fail(
                "the three KG_TEST_PRODUCTION_EMBEDDING_* fixture variables "
                "must be set together"
            )
        if not provided_fixture_names:
            self.skipTest(
                "set the three KG_TEST_PRODUCTION_EMBEDDING_* variables for the offline smoke"
            )
        wheelhouse_value = self.environment[fixture_names[0]]
        installer_value = self.environment[fixture_names[1]]
        installer_sha256 = self.environment[fixture_names[2]]
        wheelhouse = Path(str(wheelhouse_value))
        installer = Path(str(installer_value))
        self.assertTrue(wheelhouse.is_absolute())
        self.assertFalse(wheelhouse.is_symlink())
        self.assertEqual(wheelhouse, wheelhouse.resolve(strict=True))
        self.assertTrue(wheelhouse.is_dir())
        self.assertTrue(installer.is_absolute())
        self.assertFalse(installer.is_symlink())
        self.assertEqual(installer, installer.resolve(strict=True))
        self.assertEqual(str(installer_sha256), sha256_file(installer))

        scratch_root_value = self.environment.get(
            "KG_TEST_PRODUCTION_EMBEDDING_SCRATCH_ROOT"
        )
        working_root = self.root
        if scratch_root_value is not None:
            scratch_root = Path(str(scratch_root_value))
            self.assertTrue(scratch_root.is_absolute())
            self.assertFalse(scratch_root.is_symlink())
            self.assertEqual(scratch_root, scratch_root.resolve(strict=True))
            self.assertTrue(scratch_root.is_dir())
            working_root = scratch_root
        target = working_root / "empty-copied-runtime-venv"
        self.assertEqual(working_root, target.parent)
        self.assertFalse(target.exists())
        create = subprocess.run(
            [
                sys._base_executable,
                "-B",
                "-m",
                "venv",
                "--copies",
                "--without-pip",
                str(target),
            ],
            cwd=working_root,
            env=dict(self.environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, create.returncode, create.stdout)
        target_python = target / "bin/python"
        self.assertTrue(target_python.is_file())
        self.assertFalse(target_python.is_symlink())

        install = subprocess.run(
            [
                str(installer),
                "-B",
                "-m",
                "pip",
                "--python",
                str(target_python),
                "install",
                "--no-deps",
                "--only-binary=:all:",
                "--no-index",
                "--no-compile",
                "--no-cache-dir",
                "--find-links",
                str(wheelhouse),
                "-r",
                str(REPO_ROOT / "deploy/cloud_v2/requirements.lock"),
            ],
            cwd=working_root,
            env=dict(self.environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, install.returncode, install.stdout)
        site_packages = target / "lib/python3.14/site-packages"
        self.assertFalse(list(site_packages.glob("pip-*.dist-info")))
        self.assertFalse(list(site_packages.glob("setuptools-*.dist-info")))
        self.assertFalse(list(site_packages.glob("wheel-*.dist-info")))
        self.assertFalse(list(site_packages.rglob("__pycache__")))

        runtime_lock = self._capture_runtime_lock(
            "empty-copied-runtime-lock.json",
            executable=str(target_python),
        )
        verified = self._run_bootstrap(
            "--runtime-lock",
            str(runtime_lock),
            "verify-runtime",
            executable=str(target_python),
        )
        self.assertEqual(0, verified.returncode, verified.stdout)
        result = json.loads(verified.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual("spawn", result["multiprocessing_spawn_preflight"]["start_method"])

    def test_exact_release_bootstrap_ignores_shadow_origins_and_direct_module_rejects(self):
        runtime_lock = self._capture_runtime_lock()
        shadow = self.root / "shadow"
        shadow_pipeline = shadow / "pipeline"
        shadow_pipeline.mkdir(parents=True)
        marker = self.root / "attacker-origin-executed"
        marker_program = (
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        )
        (shadow / "sitecustomize.py").write_text(marker_program, encoding="utf-8")
        (shadow / "attacker.pth").write_text(
            f"import pathlib; pathlib.Path({str(marker)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        (shadow_pipeline / "__init__.py").write_text("", encoding="ascii")
        (shadow_pipeline / "production_embedding_candidate.py").write_text(
            marker_program,
            encoding="utf-8",
        )
        environment = dict(self.environment)
        environment["PYTHONPATH"] = str(shadow)
        environment["PYTHONUSERBASE"] = str(shadow)
        verified = self._run_bootstrap(
            "--runtime-lock",
            str(runtime_lock),
            "verify-runtime",
            environment=environment,
            cwd=shadow,
        )
        self.assertEqual(0, verified.returncode, verified.stdout)
        verification = json.loads(verified.stdout)
        self.assertEqual(
            sha256_file(
                self.suite_root
                / "code/deploy/pipeline/production_embedding_candidate.py"
            ),
            verification["candidate_sha256"],
        )
        lock = json.loads(runtime_lock.read_bytes())
        self.assertEqual(
            {
                "held_import_finder": True,
                "runtime_lock_sha256": sha256_file(runtime_lock),
                "start_method": "spawn",
                "worker_sys_path_sha256": canonical_sha256(
                    lock["identity"]["quick"]["worker_sys_path"]
                ),
            },
            verification["multiprocessing_spawn_preflight"],
        )
        self.assertFalse(marker.exists())
        help_result = self._run_bootstrap(
            "--runtime-lock",
            str(runtime_lock),
            "materialize",
            "--help",
            environment=environment,
            cwd=shadow,
        )
        self.assertEqual(0, help_result.returncode, help_result.stdout)

        formal_contract = self.root / "bootstrap-materialized-contract.json"
        materialized = self._run_bootstrap(
            "--runtime-lock",
            str(runtime_lock),
            "materialize",
            "--config",
            str(self.config_path),
            "--output",
            str(formal_contract),
            environment=environment,
            cwd=shadow,
        )
        self.assertEqual(1, materialized.returncode, materialized.stdout)
        self.assertEqual(
            "production_embedding_candidate_failed",
            json.loads(materialized.stdout)["error"],
        )
        self.assertFalse(formal_contract.exists())
        self.assertFalse((self.root / "calls.log").exists())

        code_root = self.suite_root / "code"
        direct_environment = dict(self.environment)
        direct_environment["PYTHONPATH"] = os.pathsep.join(
            [str(code_root / "deploy"), str(code_root)]
        )
        direct = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "pipeline.production_embedding_candidate",
                "validate",
            ],
            cwd=code_root,
            env=direct_environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, direct.returncode, direct.stdout)
        self.assertEqual(
            "exact_release_bootstrap_required", json.loads(direct.stdout)["error"]
        )

    def test_runtime_lock_and_python_executable_drift_fail_closed(self):
        runtime_lock = self._capture_runtime_lock()
        original = runtime_lock.read_bytes()
        drifted = json.loads(original)
        drifted["identity"]["quick"]["flags"]["isolated"] = 0
        drifted["identity_sha256"] = canonical_sha256(drifted["identity"])
        runtime_lock.write_bytes(canonical_bytes(drifted) + b"\n")
        drifted_environment = dict(self.environment)
        drifted_environment["KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256"] = sha256_file(
            runtime_lock
        )
        runtime_result = self._run_bootstrap(
            "--runtime-lock",
            str(runtime_lock),
            "verify-runtime",
            environment=drifted_environment,
        )
        self.assertEqual(1, runtime_result.returncode, runtime_result.stdout)
        self.assertEqual(
            "production_embedding_bootstrap_failed",
            json.loads(runtime_result.stdout)["error"],
        )

        runtime_lock.write_bytes(original)
        executable_result = self._run_bootstrap(
            "--runtime-lock",
            str(runtime_lock),
            "verify-runtime",
            environment=dict(self.environment),
            executable=str(Path(sys._base_executable).resolve()),
        )
        self.assertEqual(1, executable_result.returncode, executable_result.stdout)
        self.assertEqual(
            "production_embedding_bootstrap_failed",
            json.loads(executable_result.stdout)["error"],
        )

        internal_runtime_lock = self.suite_root / "suite-internal-runtime-lock.json"
        internal_runtime_lock.write_bytes(original)
        internal_environment = dict(self.environment)
        internal_environment["KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256"] = sha256_file(
            internal_runtime_lock
        )
        internal_result = self._run_bootstrap(
            "--runtime-lock",
            str(internal_runtime_lock),
            "verify-runtime",
            environment=internal_environment,
        )
        self.assertEqual(1, internal_result.returncode, internal_result.stdout)
        self.assertEqual(
            "production_embedding_bootstrap_failed",
            json.loads(internal_result.stdout)["error"],
        )

    def test_exact_release_path_swap_and_held_byte_races_never_execute_attacker(self):
        runtime_lock = self._capture_runtime_lock()
        code_root = self.suite_root / "code"
        parked_root = self.root / "parked-code"
        attacker_root = self.root / "attacker-code"
        shutil.copytree(code_root, attacker_root)
        marker = self.root / "attacker-held-byte-executed"
        attacker_candidate = (
            attacker_root / "deploy/pipeline/production_embedding_candidate.py"
        )
        attacker_candidate.write_bytes(
            attacker_candidate.read_bytes()
            + f"\nPath({str(marker)!r}).write_text('executed')\n".encode("utf-8")
        )
        command = [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(self._bootstrap_path()),
            "--runtime-lock",
            str(runtime_lock),
            "verify-runtime",
        ]
        process = subprocess.Popen(
            command,
            cwd=self.root,
            env=dict(self.environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        code_root.rename(parked_root)
        attacker_root.rename(code_root)
        try:
            output, _ = process.communicate(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            displaced = self.root / "displaced-attacker-code"
            code_root.rename(displaced)
            parked_root.rename(code_root)
        self.assertEqual(1, process.returncode, output)
        self.assertEqual(
            "production_embedding_bootstrap_failed", json.loads(output)["error"]
        )
        self.assertFalse(marker.exists())

        candidate = code_root / "deploy/pipeline/production_embedding_candidate.py"
        original = candidate.read_bytes()
        attacker = original + f"\nPath({str(marker)!r}).write_text('executed')\n".encode(
            "utf-8"
        )
        attacks: list[int] = []
        process_two = subprocess.Popen(
            command,
            cwd=self.root,
            env=dict(self.environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        def race_candidate() -> None:
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and process_two.poll() is None:
                candidate.write_bytes(attacker)
                attacks.append(1)
                candidate.write_bytes(original)

        attacker_thread = threading.Thread(target=race_candidate)
        attacker_thread.start()
        try:
            output_two, _ = process_two.communicate(timeout=30)
        finally:
            attacker_thread.join(timeout=5)
            candidate.write_bytes(original)
            if process_two.poll() is None:
                process_two.kill()
                process_two.communicate()
        self.assertTrue(attacks)
        self.assertFalse(marker.exists())
        self.assertIn(process_two.returncode, {0, 1}, output_two)
        parsed = json.loads(output_two)
        if process_two.returncode == 0:
            self.assertEqual(sha256_file(candidate), parsed["candidate_sha256"])
        else:
            self.assertEqual("production_embedding_bootstrap_failed", parsed["error"])

    def test_cli_failure_is_sanitized(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = CANDIDATE._run_cli_impl(
                [
                    "validate",
                    "--config",
                    str(self.root / "missing.json"),
                    "--contract",
                    str(self.production_vector_build_contract_path),
                ]
            )
        self.assertEqual(1, rc)
        value = json.loads(output.getvalue())
        self.assertEqual(
            {
                "command": "validate",
                "error": "production_embedding_candidate_failed",
                "ok": False,
            },
            value,
        )
        self.assertNotIn(self.secret, output.getvalue())

    def test_json_schema_matches_loader_contract(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {
                "schema_version",
                "provider_config",
                "base_suite",
                "authority",
                "graph",
                "local_vector",
            },
            set(schema["required"]),
        )
        base_suite = schema["$defs"]["baseSuite"]
        self.assertFalse(base_suite["additionalProperties"])
        self.assertEqual(
            {"manifest", "pending_contract"},
            set(base_suite["required"]),
        )
        local = schema["$defs"]["localVector"]
        self.assertFalse(local["additionalProperties"])
        self.assertEqual(
            ["authority_release_id", "content_type"],
            local["properties"]["metadata_allowlist"]["properties"]["chunk"][
                "const"
            ],
        )
        self.assertEqual(
            ["authority_release_id", "entity_type"],
            local["properties"]["metadata_allowlist"]["properties"]["entity"][
                "const"
            ],
        )
        runtime_schema = json.loads(
            (
                REPO_ROOT
                / "deploy/pipeline/production_embedding_runtime_lock.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            "kg-production-embedding-runtime-lock-v2",
            runtime_schema["properties"]["schema_version"]["const"],
        )
        deploy_guide = (REPO_ROOT / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertIn("test ! -e /srv/knowledge-qa/venv", deploy_guide)
        self.assertIn("venv --copies --without-pip", deploy_guide)
        self.assertIn("KG_BOOTSTRAP_INSTALLER_PYTHON_SHA256", deploy_guide)
        self.assertIn("--python /srv/knowledge-qa/venv/bin/python install", deploy_guide)
        self.assertIn("--no-deps --only-binary=:all: --no-index", deploy_guide)
        self.assertNotIn("venv/bin/python -m pip install --upgrade pip", deploy_guide)

    def test_loader_rejects_local_vector_schema_version_drift(self):
        value = self._candidate_config_value()
        value["local_vector"]["schema_version"] = "kg-local-vector-schema-NOT-V1"
        self._write_json(self.config_path, value)

        with self.assertRaises(ProductionEmbeddingCandidateConfigError) as caught:
            ProductionEmbeddingCandidateConfig.load(self.config_path)
        self.assertEqual("vector_contract_invalid", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
