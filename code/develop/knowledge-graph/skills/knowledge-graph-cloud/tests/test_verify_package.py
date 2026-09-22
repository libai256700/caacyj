#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import unittest
from shutil import copy2, copytree
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from verify_package import (
    DELIVERY_SCAN_PREFIXES,
    DELIVERY_SCAN_TOP_LEVEL,
    DELIVERY_SKILL_DIRS,
    EXPECTED_BUILDER_FILES,
    EXPECTED_RUNTIME_FILES,
    FIXED_EVAL_ARTIFACTS,
    IGNORED_NAMES,
    INDEPENDENT_SKILL_BOUNDARY_DOCS,
    canonical_relative_path,
    expected_delivery_files,
    expected_knowledge_files,
    load_hash_manifest,
    scan_forbidden_text,
    verify_eval_artifacts,
    verify_independent_skill_boundary,
    verify_knowledge_qa_boundary,
    verify_manifest,
    verify_runtime_package_boundary,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class PackageVerifierTests(unittest.TestCase):
    @staticmethod
    def _copy_runtime_boundary_fixture(root: Path) -> None:
        copytree(
            REPO_ROOT / "deploy",
            root / "deploy",
            ignore=lambda _directory, names: [
                name for name in names if name in {"__pycache__", ".DS_Store"}
            ],
        )

    def test_knowledge_qa_keeps_live_tools_as_independent_skills(self):
        self.assertEqual([], verify_knowledge_qa_boundary(REPO_ROOT))

    def test_reverse_coupling_from_independent_skill_docs_is_rejected(self):
        stale_text = (
            "由 live_tool_for_query 将 live_context 传给 "
            "knowledge-graph-cloud 的 build_app_prompt()。\n"
        )

        for stale_relative in INDEPENDENT_SKILL_BOUNDARY_DOCS:
            with self.subTest(relative=stale_relative), TemporaryDirectory() as raw_tmp:
                root = Path(raw_tmp)
                for relative in INDEPENDENT_SKILL_BOUNDARY_DOCS:
                    destination = root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    copy2(REPO_ROOT / relative, destination)
                with (root / stale_relative).open("a", encoding="utf-8") as handle:
                    handle.write(stale_text)

                errors = verify_independent_skill_boundary(root)
                for marker in (
                    "knowledge-graph-cloud",
                    "build_app_prompt",
                    "live_tool_for_query",
                    "live_context",
                ):
                    self.assertIn(
                        f"independent_skill_doc_coupling:{stale_relative}:{marker}",
                        errors,
                    )

    def test_delivery_manifest_covers_all_portable_skills(self):
        expected = expected_delivery_files(REPO_ROOT)

        self.assertIn("APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md", expected)
        self.assertIn("KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md", expected)
        self.assertIn("STOP_B_EXTERNAL_PROCESSING_REQUEST.json", expected)
        self.assertIn("CLOUD_MIGRATION_DECISIONS.json", expected)
        self.assertIn(".gitattributes", expected)
        self.assertIn("skills/knowledge-graph-cloud/SKILL.md", expected)
        self.assertIn("skills/evaluation-report/SKILL.md", expected)
        self.assertIn("skills/career-planning-coach/SKILL.md", expected)
        self.assertIn("skills/career-planning-coach/server/app.mjs", expected)
        self.assertIn("skills/weather/SKILL.md", expected)
        self.assertIn("skills/weather/scripts/qweather.py", expected)
        self.assertIn("skills/search/SKILL.md", expected)
        self.assertIn("skills/search/scripts/dual_search.py", expected)
        self.assertIn("scripts/ollama_local_embedding_probe.py", expected)
        self.assertIn("scripts/build_ollama_vector_candidate.py", expected)
        self.assertIn("scripts/verify_ollama_vector_candidate.py", expected)
        self.assertNotIn("skills/knowledge-graph/SKILL.md", expected)
        self.assertNotIn("deploy/cloud_v2/offline_evidence.py.orig", expected)
        self.assertNotIn(
            "deploy/cloud_v2/tests/test_offline_evidence.py.orig",
            expected,
        )

    def test_delivery_manifest_covers_entire_operator_companion(self):
        expected = expected_delivery_files(REPO_ROOT)
        operator_root = REPO_ROOT / "operator-companion"
        discovered = {
            path.relative_to(REPO_ROOT).as_posix()
            for path in operator_root.rglob("*")
            if path.is_file()
            and path.suffix != ".pyc"
            and not any(part in IGNORED_NAMES for part in path.parts)
        }
        covered = {
            relative
            for relative in expected
            if relative.startswith("operator-companion/")
        }

        self.assertEqual(discovered, covered)
        for relative in (
            "operator-companion/lib/ops_contract.py",
            "operator-companion/hybrid-audit-cloud/SKILL.md",
            "operator-companion/quality-dashboard-cloud/SKILL.md",
            "operator-companion/maintenance-controller-cloud/SKILL.md",
            "operator-companion/ops-agent-config/ops-agent-config.schema.json",
            "operator-companion/tests/test_ops_isolation.py",
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, expected)

    def test_delivery_manifest_rejects_missing_extra_and_wrong_hash(self):
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            (root / "missing.txt").write_text("missing\n", encoding="utf-8")
            (root / "extra.txt").write_text("extra\n", encoding="utf-8")
            (root / "CODE_MANIFEST.sha256").write_text(
                f"{'0' * 64}  tracked.txt\n"
                f"{'0' * 64}  extra.txt\n",
                encoding="utf-8",
            )

            errors = verify_manifest(
                root,
                "CODE_MANIFEST.sha256",
                expected={"tracked.txt", "missing.txt"},
            )

            self.assertIn(
                "manifest_missing_entry:CODE_MANIFEST.sha256:missing.txt",
                errors,
            )
            self.assertIn(
                "manifest_extra_entry:CODE_MANIFEST.sha256:extra.txt",
                errors,
            )
            self.assertIn(
                "manifest_hash_mismatch:CODE_MANIFEST.sha256:tracked.txt",
                errors,
            )

    def test_operator_companion_symlink_is_rejected(self):
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            (root / "deploy").mkdir()
            (root / "operator-companion").mkdir()
            (root / "scripts").mkdir()
            for skill_name in DELIVERY_SKILL_DIRS:
                (root / "skills" / skill_name).mkdir(parents=True)
            (root / "payload.txt").write_text("payload\n", encoding="utf-8")
            (root / "operator-companion" / "payload-link").symlink_to(
                root / "payload.txt"
            )

            with self.assertRaisesRegex(ValueError, "delivery symlink forbidden"):
                expected_delivery_files(root)

    def test_knowledge_manifest_exactly_covers_all_source_files(self):
        expected = expected_knowledge_files(REPO_ROOT)
        records, errors = load_hash_manifest(REPO_ROOT / "MANIFEST.sha256")

        self.assertEqual([], errors)
        self.assertEqual(expected, set(records))
        self.assertEqual(35, len(expected))

    def test_delivery_surfaces_receive_secret_and_host_path_scans(self):
        for relative in (
            "skills/weather/SKILL.md",
            "skills/search/scripts/dual_search.py",
            "skills/career-planning-coach/server/app.mjs",
            "operator-companion/lib/ops_contract.py",
            "scripts/build_ollama_vector_candidate.py",
            "CLOUD_MIGRATION_DECISIONS.json",
            "KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md",
            "STOP_B_EXTERNAL_PROCESSING_REQUEST.json",
        ):
            with self.subTest(relative=relative):
                self.assertTrue(
                    relative.startswith(DELIVERY_SCAN_PREFIXES)
                    or relative in DELIVERY_SCAN_TOP_LEVEL
                )
                host_path = "path='" + "/" + "Users/name/private'"
                self.assertTrue(scan_forbidden_text(relative, host_path))

    def test_manifest_paths_must_be_canonical_and_relative(self):
        self.assertEqual("deploy/pipeline/server.py", canonical_relative_path("deploy/pipeline/server.py"))
        for invalid in ("/tmp/server.py", "../server.py", "deploy//server.py", "deploy\\server.py"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    canonical_relative_path(invalid)

    def test_host_paths_and_literal_credentials_are_rejected(self):
        host_path = "path = '/" + "Users/name/data'"
        self.assertTrue(scan_forbidden_text("deploy/a.py", host_path))
        key_field = '"api_' + 'key"'
        literal_config = key_field + ': "not-a-secretref"'
        self.assertTrue(scan_forbidden_text("deploy/a.json", literal_config))
        self.assertEqual([], scan_forbidden_text("deploy/a.json", '"api_key": "secretref:KG_KEY"'))

    def test_runtime_package_boundary_is_dependency_closed(self):
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            self._copy_runtime_boundary_fixture(root)
            self.assertEqual([], verify_runtime_package_boundary(root))

    def test_runtime_and_builder_allowlists_match_independent_fixed_closures(self):
        runtime = json.loads(
            (REPO_ROOT / "deploy/cloud_v2/runtime-file-allowlist.json").read_text(
                encoding="utf-8"
            )
        )
        builder = json.loads(
            (REPO_ROOT / "deploy/cloud_v2/builder-file-allowlist.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(EXPECTED_RUNTIME_FILES), runtime["files"])
        self.assertEqual(list(EXPECTED_BUILDER_FILES), builder["files"])
        self.assertIn("deploy/rag_store/source_authority.py", builder["files"])

    def test_runtime_boundary_rejects_self_authorized_allowlist_extras(self):
        for allowlist_name in ("runtime-file-allowlist.json", "builder-file-allowlist.json"):
            with self.subTest(allowlist=allowlist_name), TemporaryDirectory() as raw_tmp:
                root = Path(raw_tmp)
                self._copy_runtime_boundary_fixture(root)
                extra = root / "deploy/rag_store/self_authorized_extra.py"
                extra.write_text("pass\n", encoding="utf-8")
                allowlist_path = root / "deploy/cloud_v2" / allowlist_name
                value = json.loads(allowlist_path.read_text(encoding="utf-8"))
                value["files"].append("deploy/rag_store/self_authorized_extra.py")
                value["files"].sort()
                allowlist_path.write_text(json.dumps(value) + "\n", encoding="utf-8")

                self.assertIn(
                    "runtime_boundary_allowlist_not_exact:deploy/cloud_v2/"
                    + allowlist_name,
                    verify_runtime_package_boundary(root),
                )

    def test_delivery_tree_rejects_generated_python_cache_nodes(self):
        for relative in (
            "deploy/pipeline/__pycache__/server.cpython-314.pyc",
            "operator-companion/client.pyc",
            "skills/knowledge-graph-cloud/tests/__pycache__/test_app.pyc",
        ):
            with self.subTest(relative=relative), TemporaryDirectory() as raw_tmp:
                root = Path(raw_tmp)
                (root / "deploy").mkdir()
                (root / "operator-companion").mkdir()
                (root / "scripts").mkdir()
                for skill_name in DELIVERY_SKILL_DIRS:
                    (root / "skills" / skill_name).mkdir(parents=True)
                cache = root / relative
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(b"generated bytecode")

                with self.assertRaisesRegex(ValueError, "generated Python cache forbidden"):
                    expected_delivery_files(root)

    def test_runtime_package_boundary_rejects_allowlist_and_lock_omissions(self):
        cases = (
            "runtime-import",
            "runtime-resource",
            "builder-entrypoint",
            "builder-resource",
            "wsgi-server-dependency",
            "wsgi-eager-entrypoint",
        )
        for case in cases:
            with self.subTest(case=case), TemporaryDirectory() as raw_tmp:
                root = Path(raw_tmp)
                self._copy_runtime_boundary_fixture(root)
                if case == "runtime-import":
                    path = root / "deploy/cloud_v2/runtime-file-allowlist.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["files"].remove("deploy/rag_store/provider_http_transport.py")
                    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
                    expected = (
                        "runtime_boundary_local_dependency_missing:"
                        "deploy/rag_store/provider_http_transport.py"
                    )
                elif case == "runtime-resource":
                    path = root / "deploy/cloud_v2/runtime-file-allowlist.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["files"].remove(
                        "deploy/pipeline/neo4j_import_config.schema.json"
                    )
                    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
                    expected = (
                        "runtime_boundary_required_file_missing:"
                        "deploy/pipeline/neo4j_import_config.schema.json"
                    )
                elif case == "builder-entrypoint":
                    path = root / "deploy/cloud_v2/builder-file-allowlist.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["files"].remove(
                        "deploy/pipeline/production_embedding_candidate.py"
                    )
                    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
                    expected = (
                        "builder_boundary_required_file_missing:"
                        "deploy/pipeline/production_embedding_candidate.py"
                    )
                elif case == "builder-resource":
                    path = root / "deploy/cloud_v2/builder-file-allowlist.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["files"].remove(
                        "deploy/pipeline/production_embedding_config.schema.json"
                    )
                    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
                    expected = (
                        "builder_boundary_required_file_missing:"
                        "deploy/pipeline/production_embedding_config.schema.json"
                    )
                elif case == "wsgi-server-dependency":
                    path = root / "deploy/cloud_v2/requirements.lock"
                    path.write_text(
                        "\n".join(
                            line
                            for line in path.read_text(encoding="ascii").splitlines()
                            if line != "waitress==3.0.2"
                        )
                        + "\n",
                        encoding="ascii",
                    )
                    expected = "runtime_boundary_requirement_missing:waitress==3.0.2"
                else:
                    path = root / "deploy/pipeline/wsgi.py"
                    text = path.read_text(encoding="utf-8")
                    replaced = text.replace(
                        "app = create_authenticated_wsgi_app(create_wsgi_app)\n",
                        "def get_app():\n"
                        "    return create_authenticated_wsgi_app(create_wsgi_app)\n",
                    )
                    self.assertNotEqual(text, replaced)
                    path.write_text(replaced, encoding="utf-8")
                    expected = "runtime_boundary_wsgi_application_not_eager"

                self.assertIn(expected, verify_runtime_package_boundary(root))

    def test_runtime_package_boundary_rejects_wsgi_bypass_shapes(self):
        assignment = "app = create_authenticated_wsgi_app(create_wsgi_app)\n"
        cases = {
            "unreachable": (
                "try:\n    " + assignment,
                "try:\n    raise RuntimeError('unreachable')\n    " + assignment,
            ),
            "except-only": (
                "try:\n    " + assignment + "except Exception as error:\n",
                "try:\n    raise RuntimeError('startup')\n"
                "except Exception as error:\n    "
                + assignment,
            ),
            "overwritten": (assignment, assignment + "app = None\n"),
        }
        for case, (needle, replacement) in cases.items():
            with self.subTest(case=case), TemporaryDirectory() as raw_tmp:
                root = Path(raw_tmp)
                self._copy_runtime_boundary_fixture(root)
                path = root / "deploy/pipeline/wsgi.py"
                source = path.read_text(encoding="utf-8")
                mutated = source.replace(needle, replacement, 1)
                self.assertNotEqual(source, mutated)
                path.write_text(mutated, encoding="utf-8")

                self.assertIn(
                    "runtime_boundary_wsgi_application_not_eager",
                    verify_runtime_package_boundary(root),
                )

    def test_runtime_package_boundary_rejects_symlinked_allowlist_ancestor(self):
        with TemporaryDirectory() as raw_tmp:
            temporary = Path(raw_tmp)
            root = temporary / "root"
            root.mkdir()
            self._copy_runtime_boundary_fixture(root)
            pipeline = root / "deploy/pipeline"
            outside = temporary / "outside-pipeline"
            pipeline.rename(outside)
            pipeline.symlink_to(outside, target_is_directory=True)

            self.assertIn(
                "runtime_boundary_allowlist_target_missing:"
                "deploy/cloud_v2/runtime-file-allowlist.json:"
                "deploy/pipeline/wsgi.py",
                verify_runtime_package_boundary(root),
            )

    def test_runtime_package_boundary_rejects_wsgi_trust_name_rebinding(self):
        for name in (
            "EX_CONFIG",
            "create_authenticated_wsgi_app",
            "create_wsgi_app",
        ):
            with self.subTest(name=name), TemporaryDirectory() as raw_tmp:
                root = Path(raw_tmp)
                self._copy_runtime_boundary_fixture(root)
                path = root / "deploy/pipeline/wsgi.py"
                source = path.read_text(encoding="utf-8")
                mutated = source.replace(
                    "\n\ntry:\n",
                    f"\n\n{name} = lambda *args: object()\n\ntry:\n",
                    1,
                )
                self.assertNotEqual(source, mutated)
                path.write_text(mutated, encoding="utf-8")

                self.assertIn(
                    "runtime_boundary_wsgi_application_not_eager",
                    verify_runtime_package_boundary(root),
                )

    def test_eval_directory_allows_only_fixed_pending_gold_artifacts(self):
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            (root / "eval").mkdir()
            for relative in FIXED_EVAL_ARTIFACTS:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                copy2(REPO_ROOT / relative, destination)

            self.assertEqual([], verify_eval_artifacts(root))

            (root / "eval" / "results.json").write_text("{}\n", encoding="utf-8")
            self.assertIn(
                "unexpected_eval_artifact:eval/results.json",
                verify_eval_artifacts(root),
            )

    def test_reviewed_gold_cannot_be_checked_into_the_portable_package(self):
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            (root / "eval").mkdir()
            for relative in FIXED_EVAL_ARTIFACTS:
                copy2(REPO_ROOT / relative, root / relative)
            gold_path = root / "eval" / "cloud80_gold_standard_v1.json"
            gold = json.loads(gold_path.read_text(encoding="utf-8"))
            gold["review_policy"]["status"] = "reviewed-pending-signature"
            gold_path.write_text(
                json.dumps(gold, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            errors = verify_eval_artifacts(root)
            self.assertIn(
                "checked_in_gold_must_be_80_case_pending_template",
                errors,
            )
            self.assertIn(
                "fixed_eval_artifact_hash_mismatch:eval/cloud80_gold_standard_v1.json",
                errors,
            )

            gold["review_policy"] = []
            gold_path.write_text(json.dumps(gold) + "\n", encoding="utf-8")
            self.assertIn(
                "checked_in_gold_must_be_80_case_pending_template",
                verify_eval_artifacts(root),
            )


if __name__ == "__main__":
    unittest.main()
