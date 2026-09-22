from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFIER = _load_script(
    "verify_ollama_vector_candidate_test_target",
    "scripts/verify_ollama_vector_candidate.py",
)
BUILDER = _load_script(
    "build_ollama_vector_candidate_test_target",
    "scripts/build_ollama_vector_candidate.py",
)


class OllamaLocalCandidateToolTests(unittest.TestCase):
    def test_candidate_manifest_writer_completes_short_writes(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.json"
            real_write = BUILDER.os.write

            def short_write(descriptor, payload):
                return real_write(descriptor, payload[:3])

            with mock.patch.object(BUILDER.os, "write", side_effect=short_write):
                BUILDER._write_json(path, {"ok": True, "value": "candidate"})

            self.assertEqual(
                {"ok": True, "value": "candidate"},
                json.loads(path.read_text(encoding="utf-8")),
            )

    def test_authority_database_hash_is_bound_before_local_model_probe(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "rag_chunks.db"
            database.write_bytes(b"wrong authority bytes")
            (root / "ollama-local-vector-candidate-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "kg-ollama-local-vector-candidate-v1",
                        "status": "local-development-candidate-only",
                        "promotion_authorized": False,
                        "authority": {"database_sha256": "0" * 64},
                        "local_vector": {},
                        "embedding": {"identity": {}},
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                VERIFIER, "inspect_ollama_model"
            ) as model_probe, self.assertRaisesRegex(
                VERIFIER.OllamaCandidateVerificationError,
                "authority_database_hash_mismatch",
            ):
                VERIFIER.verify_candidate(
                    candidate_root=root,
                    authority_database=database,
                    query="无人机安全飞行",
                    base_url="http://127.0.0.1:11434",
                    model="bge-m3:latest",
                )
            model_probe.assert_not_called()

    def test_candidate_release_path_cannot_escape_candidate_root(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "rag_chunks.db"
            database.write_bytes(b"authority")
            (root / "ollama-local-vector-candidate-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "kg-ollama-local-vector-candidate-v1",
                        "status": "local-development-candidate-only",
                        "promotion_authorized": False,
                        "authority": {
                            "database_sha256": VERIFIER._sha256_file(database)
                        },
                        "local_vector": {"data_release_id": "../../outside"},
                        "embedding": {"identity": {}},
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                VERIFIER, "inspect_ollama_model"
            ) as model_probe, self.assertRaisesRegex(
                VERIFIER.OllamaCandidateVerificationError,
                "data_release_id_invalid",
            ):
                VERIFIER.verify_candidate(
                    candidate_root=root,
                    authority_database=database,
                    query="无人机安全飞行",
                    base_url="http://127.0.0.1:11434",
                    model="bge-m3:latest",
                )
            model_probe.assert_not_called()

    def test_authority_database_rejects_symlink_even_with_matching_hash(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "rag_chunks.db"
            database.write_bytes(b"authority")
            alias = root / "authority-alias.db"
            alias.symlink_to(database)

            with self.assertRaisesRegex(
                VERIFIER.OllamaCandidateVerificationError,
                "authority_database_invalid",
            ):
                VERIFIER._validated_authority_database(
                    alias, VERIFIER._sha256_file(database)
                )


if __name__ == "__main__":
    unittest.main()
