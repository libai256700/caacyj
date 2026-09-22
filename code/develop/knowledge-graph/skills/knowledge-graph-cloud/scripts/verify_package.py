#!/usr/bin/env python3
"""Verify the portable cloud runtime, skill, evaluator, and sealed hashes."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath


DELIVERY_DOCS = (
    "README.md",
    "DEPLOY.md",
    "USAGE.md",
    "APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md",
    "KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md",
    "STOP_B_EXTERNAL_PROCESSING_REQUEST.json",
)
DELIVERY_GOVERNANCE_ARTIFACTS = (
    ".gitattributes",
    "CLOUD_MIGRATION_DECISIONS.json",
)
DELIVERY_SKILL_DIRS = (
    "knowledge-graph-cloud",
    "evaluation-report",
    "career-planning-coach",
    "weather",
    "search",
)
DELIVERY_TREE_DIRS = (
    "deploy",
    "operator-companion",
    "scripts",
)
DELIVERY_SCAN_PREFIXES = tuple(f"{name}/" for name in DELIVERY_TREE_DIRS) + tuple(
    f"skills/{name}/" for name in DELIVERY_SKILL_DIRS
)
DELIVERY_SCAN_TOP_LEVEL = frozenset(
    (
        *DELIVERY_GOVERNANCE_ARTIFACTS,
        "KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md",
        "STOP_B_EXTERNAL_PROCESSING_REQUEST.json",
    )
)
EXCLUDED_DELIVERY_PATHS = frozenset(
    {
        "deploy/pipeline/config.json",
        "deploy/cloud_v2/offline_evidence.py.orig",
        "deploy/cloud_v2/tests/test_offline_evidence.py.orig",
    }
)
IGNORED_NAMES = frozenset({"__pycache__", "node_modules", ".DS_Store"})
FORBIDDEN_PYTHON_CACHE_DIRECTORIES = frozenset({"__pycache__"})
FORBIDDEN_PYTHON_CACHE_SUFFIXES = frozenset({".pyc"})
FORBIDDEN_TEXT = {
    "/" + "Users/": "host_absolute_path",
    "." + "openclaw": "openclaw_host_coupling",
    "-----BEGIN " + "PRIVATE KEY-----": "private_key_material",
    "-----BEGIN RSA " + "PRIVATE KEY-----": "private_key_material",
}
TOKEN_PATTERN = re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE)
API_KEY_LITERAL = re.compile(r'"api_key"\s*:\s*"(?!secretref:)([^"$<{][^"]{7,})"')
FIXTURE_RELATIVE_PATH = "eval/online_subset_20260803.json"
FIXTURE_SHA256 = "7f9cc4c2470f6aa5dcfef6d928429e6b08fb73453d592e3a188d913128e85e2d"
GOLD_RELATIVE_PATH = "eval/cloud80_gold_standard_v1.json"
GOLD_SHA256 = "e660d0de7b3f32068b9bcc5cf33f29d46669a5e1d1ff640d740b297cdd1ea508"
GOLD_SCHEMA_RELATIVE_PATH = "eval/cloud80_gold_standard_v1.schema.json"
GOLD_SCHEMA_SHA256 = "be36c702f4fd6c87637442c7dcf27bd89650bde1e1b74688b3f0bae482caee18"
FIXED_EVAL_ARTIFACTS = {
    FIXTURE_RELATIVE_PATH: FIXTURE_SHA256,
    GOLD_RELATIVE_PATH: GOLD_SHA256,
    GOLD_SCHEMA_RELATIVE_PATH: GOLD_SCHEMA_SHA256,
}
KNOWLEDGE_QA_BOUNDARY_DOCS = (
    "README.md",
    "USAGE.md",
    "skills/knowledge-graph-cloud/SKILL.md",
)
KNOWLEDGE_QA_FORBIDDEN_COUPLING = (
    "live_tool_for_query",
    "live_context",
    "QWEATHER_KEY",
    "BAIDU_QIANFAN_SEARCH_TOKEN",
    "SERPER_API_KEY",
)
INDEPENDENT_SKILL_BOUNDARY_DOCS = (
    "skills/weather/SKILL.md",
    "skills/search/SKILL.md",
)
INDEPENDENT_SKILL_FORBIDDEN_COUPLING = (
    "knowledge-graph-cloud",
    "build_app_prompt",
    "live_tool_for_query",
    "live_context",
)
RUNTIME_ALLOWLIST_RELATIVE_PATH = "deploy/cloud_v2/runtime-file-allowlist.json"
BUILDER_ALLOWLIST_RELATIVE_PATH = "deploy/cloud_v2/builder-file-allowlist.json"
RUNTIME_REQUIREMENTS_RELATIVE_PATH = "deploy/cloud_v2/requirements.lock"
RUNTIME_ENTRYPOINTS = (
    "deploy/pipeline/wsgi.py",
    "deploy/pipeline/neo4j_import_candidate.py",
    "deploy/pipeline/production_embedding_bootstrap.py",
    "deploy/pipeline/production_embedding_candidate.py",
)
BUILDER_ENTRYPOINTS = (
    "deploy/pipeline/production_embedding_bootstrap.py",
    "deploy/pipeline/production_embedding_candidate.py",
)
EXPECTED_RUNTIME_FILES = (
    "deploy/cloud_v2/__init__.py",
    "deploy/cloud_v2/identity_policy.py",
    "deploy/cloud_v2/source_scope.py",
    "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
    "deploy/cloud_v2/stop_b_request.py",
    "deploy/pipeline/cloud_runtime.py",
    "deploy/pipeline/cloud_runtime_config.schema.json",
    "deploy/pipeline/neo4j_import_candidate.py",
    "deploy/pipeline/neo4j_import_config.schema.json",
    "deploy/pipeline/production_embedding_bootstrap.py",
    "deploy/pipeline/production_embedding_candidate.py",
    "deploy/pipeline/production_embedding_config.schema.json",
    "deploy/pipeline/production_embedding_runtime_lock.schema.json",
    "deploy/pipeline/provider_bootstrap.py",
    "deploy/pipeline/provider_runtime_config.schema.json",
    "deploy/pipeline/public_identity_config.schema.json",
    "deploy/pipeline/public_identity_middleware.py",
    "deploy/pipeline/server.py",
    "deploy/pipeline/wsgi.py",
    "deploy/rag_store/authoritative_extractive_fallback.py",
    "deploy/rag_store/cloud_claim_evidence.py",
    "deploy/rag_store/embedding_adapter.py",
    "deploy/rag_store/local_vector_store.py",
    "deploy/rag_store/neo4j_graph_importer.py",
    "deploy/rag_store/provider_http_transport.py",
    "deploy/rag_store/provider_meters.py",
    "deploy/rag_store/provider_wire.py",
    "deploy/rag_store/query_rewrite.py",
    "deploy/rag_store/question_bank_match.py",
    "deploy/rag_store/regulation_timeline.json",
    "deploy/rag_store/request_envelope.py",
    "deploy/rag_store/route_policy.py",
    "deploy/rag_store/runtime_neo4j_reader.py",
    "deploy/rag_store/runtime_query_embedding.py",
    "deploy/rag_store/runtime_sqlite_reader.py",
    "deploy/rag_store/runtime_vector_reader.py",
    "deploy/rag_store/scoped_graph_contract.py",
    "deploy/rag_store/server_answer_coordinator.py",
    "deploy/rag_store/server_answer_model.py",
    "deploy/rag_store/source_authority.py",
    "deploy/rag_store/superseded_passages.json",
)
EXPECTED_BUILDER_FILES = (
    "deploy/cloud_v2/__init__.py",
    "deploy/cloud_v2/source_scope.py",
    "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
    "deploy/cloud_v2/stop_b_request.py",
    "deploy/pipeline/production_embedding_bootstrap.py",
    "deploy/pipeline/production_embedding_candidate.py",
    "deploy/pipeline/production_embedding_config.schema.json",
    "deploy/pipeline/production_embedding_runtime_lock.schema.json",
    "deploy/pipeline/provider_bootstrap.py",
    "deploy/pipeline/provider_runtime_config.schema.json",
    "deploy/rag_store/embedding_adapter.py",
    "deploy/rag_store/local_vector_store.py",
    "deploy/rag_store/provider_http_transport.py",
    "deploy/rag_store/provider_meters.py",
    "deploy/rag_store/provider_wire.py",
    "deploy/rag_store/runtime_query_embedding.py",
    "deploy/rag_store/runtime_sqlite_reader.py",
    "deploy/rag_store/scoped_graph_contract.py",
    "deploy/rag_store/server_answer_model.py",
    "deploy/rag_store/source_authority.py",
)
RUNTIME_REQUIRED_RESOURCES = (
    "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
    "deploy/pipeline/cloud_runtime_config.schema.json",
    "deploy/pipeline/neo4j_import_config.schema.json",
    "deploy/pipeline/production_embedding_config.schema.json",
    "deploy/pipeline/production_embedding_runtime_lock.schema.json",
    "deploy/pipeline/provider_runtime_config.schema.json",
    "deploy/pipeline/public_identity_config.schema.json",
    "deploy/rag_store/regulation_timeline.json",
    "deploy/rag_store/superseded_passages.json",
)
BUILDER_REQUIRED_RESOURCES = (
    "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
    "deploy/pipeline/production_embedding_config.schema.json",
    "deploy/pipeline/production_embedding_runtime_lock.schema.json",
    "deploy/pipeline/provider_runtime_config.schema.json",
)
RUNTIME_REQUIRED_DISTRIBUTIONS = {
    "flask": "3.1.3",
    "neo4j": "6.2.0",
    "numpy": "2.5.2",
    "usearch": "2.26.2",
    "waitress": "3.0.2",
    "werkzeug": "3.1.8",
}
_LOCAL_MODULE_ROOTS = (
    ("deploy/pipeline", "pipeline"),
    ("deploy/rag_store", "rag_store"),
    ("deploy/cloud_v2", "deploy.cloud_v2"),
)
_LOCAL_MODULE_PREFIXES = tuple(module_root for _path, module_root in _LOCAL_MODULE_ROOTS)


def canonical_relative_path(value: str) -> str:
    if not value or "\\" in value or value.startswith("/") or "//" in value:
        raise ValueError("path must be canonical relative POSIX")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path traversal or dot component")
    return path.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_generated_python_cache(relative: str) -> bool:
    path = PurePosixPath(relative)
    return bool(
        any(part in FORBIDDEN_PYTHON_CACHE_DIRECTORIES for part in path.parts)
        or path.suffix in FORBIDDEN_PYTHON_CACHE_SUFFIXES
    )


def expected_delivery_files(root: Path) -> set[str]:
    expected = set(DELIVERY_DOCS) | set(DELIVERY_GOVERNANCE_ARTIFACTS)
    targets = tuple(root / name for name in DELIVERY_TREE_DIRS) + tuple(
        root / "skills" / name for name in DELIVERY_SKILL_DIRS
    )
    for target in targets:
        if not target.is_dir() or target.is_symlink():
            raise ValueError(f"delivery directory missing or symlinked: {target}")
        for path in target.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if _is_generated_python_cache(relative):
                raise ValueError(f"generated Python cache forbidden: {relative}")
            if any(part in IGNORED_NAMES for part in path.parts):
                continue
            if path.is_symlink():
                raise ValueError(f"delivery symlink forbidden: {path}")
            if not path.is_file():
                continue
            if relative in EXCLUDED_DELIVERY_PATHS:
                continue
            expected.add(relative)
    expected.update(FIXED_EVAL_ARTIFACTS)
    return expected


def expected_knowledge_files(root: Path) -> set[str]:
    knowledge_root = root / "knowledge_base"
    if not knowledge_root.is_dir() or knowledge_root.is_symlink():
        raise ValueError(f"knowledge directory missing or symlinked: {knowledge_root}")
    expected: set[str] = set()
    for path in knowledge_root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if _is_generated_python_cache(relative):
            raise ValueError(f"generated Python cache forbidden: {relative}")
        if any(part in IGNORED_NAMES for part in path.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"knowledge symlink forbidden: {path}")
        if path.is_file():
            expected.add(path.relative_to(root).as_posix())
    return expected


def load_hash_manifest(path: Path) -> tuple[dict[str, str], list[str]]:
    records: dict[str, str] = {}
    errors: list[str] = []
    if not path.is_file() or path.is_symlink():
        return {}, [f"manifest_missing_or_symlink:{path.name}"]
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw_line)
        if not match:
            errors.append(f"manifest_invalid_line:{path.name}:{line_number}")
            continue
        digest, raw_relative = match.groups()
        try:
            relative = canonical_relative_path(raw_relative)
        except ValueError:
            errors.append(f"manifest_invalid_path:{path.name}:{line_number}")
            continue
        if relative in records:
            errors.append(f"manifest_duplicate_path:{path.name}:{relative}")
            continue
        records[relative] = digest
    return records, errors


def verify_manifest(
    root: Path,
    manifest_name: str,
    *,
    expected: set[str] | None = None,
) -> list[str]:
    records, errors = load_hash_manifest(root / manifest_name)
    if expected is not None:
        for relative in sorted(expected - set(records)):
            errors.append(f"manifest_missing_entry:{manifest_name}:{relative}")
        for relative in sorted(set(records) - expected):
            errors.append(f"manifest_extra_entry:{manifest_name}:{relative}")
    for relative, expected_digest in sorted(records.items()):
        path = root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root.resolve())
        except (FileNotFoundError, ValueError):
            errors.append(f"manifest_target_invalid:{manifest_name}:{relative}")
            continue
        if path.is_symlink() or not path.is_file():
            errors.append(f"manifest_target_not_regular:{manifest_name}:{relative}")
            continue
        actual_digest = sha256_file(path)
        if actual_digest != expected_digest:
            errors.append(f"manifest_hash_mismatch:{manifest_name}:{relative}")
    return errors


def scan_forbidden_text(relative: str, text: str) -> list[str]:
    errors = [
        f"forbidden_text:{code}:{relative}"
        for marker, code in FORBIDDEN_TEXT.items()
        if marker in text
    ]
    if TOKEN_PATTERN.search(text):
        errors.append(f"forbidden_text:credential_token:{relative}")
    if API_KEY_LITERAL.search(text):
        errors.append(f"forbidden_text:literal_credential:{relative}")
    return errors


def _load_file_allowlist(
    root: Path,
    relative: str,
    *,
    expected_schema: str,
    expected_files: tuple[str, ...],
) -> tuple[tuple[str, ...], list[str]]:
    path = root / relative
    errors: list[str] = []
    try:
        path_resolved = path.resolve(strict=True)
    except OSError:
        path_resolved = None
    if path_resolved != path or not path.is_file():
        return (), [f"runtime_boundary_allowlist_missing:{relative}"]

    duplicate = False

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        nonlocal duplicate
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                duplicate = True
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda _constant: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, UnicodeDecodeError, ValueError):
        return (), [f"runtime_boundary_allowlist_invalid_json:{relative}"]
    if (
        duplicate
        or not isinstance(value, dict)
        or set(value) != {"schema_version", "files"}
        or value.get("schema_version") != expected_schema
        or not isinstance(value.get("files"), list)
        or not value["files"]
    ):
        return (), [f"runtime_boundary_allowlist_invalid_schema:{relative}"]

    files: list[str] = []
    for raw in value["files"]:
        if not isinstance(raw, str):
            errors.append(f"runtime_boundary_allowlist_invalid_path:{relative}")
            continue
        try:
            item = canonical_relative_path(raw)
        except ValueError:
            errors.append(f"runtime_boundary_allowlist_invalid_path:{relative}")
            continue
        files.append(item)
        target = root / item
        try:
            target_resolved = target.resolve(strict=True)
        except OSError:
            target_resolved = None
        if target_resolved != target or not target.is_file():
            errors.append(f"runtime_boundary_allowlist_target_missing:{relative}:{item}")
    if files != sorted(set(files)):
        errors.append(f"runtime_boundary_allowlist_not_unique_sorted:{relative}")
    if tuple(files) != expected_files:
        errors.append(f"runtime_boundary_allowlist_not_exact:{relative}")
    return tuple(files), errors


def _local_module_index(root: Path) -> tuple[dict[str, Path], dict[Path, str], list[str]]:
    by_name: dict[str, Path] = {}
    preferred_name: dict[Path, str] = {}
    errors: list[str] = []
    for relative_root, module_root in _LOCAL_MODULE_ROOTS:
        source_root = root / relative_root
        if source_root.is_symlink() or not source_root.is_dir():
            errors.append(f"runtime_boundary_module_root_missing:{relative_root}")
            continue
        for path in sorted(source_root.rglob("*.py")):
            relative_parts = list(path.relative_to(source_root).with_suffix("").parts)
            if path.name == "__init__.py":
                relative_parts.pop()
            suffix = ".".join(relative_parts)
            module_name = module_root + (f".{suffix}" if suffix else "")
            if path.is_symlink() or not path.is_file() or module_name in by_name:
                errors.append(f"runtime_boundary_module_invalid:{path.relative_to(root)}")
                continue
            by_name[module_name] = path
            preferred_name[path] = module_name
            if module_root in {"pipeline", "rag_store"}:
                by_name[f"deploy.{module_name}"] = path
    return by_name, preferred_name, errors


def _resolve_import_name(
    node: ast.ImportFrom,
    *,
    current_module: str,
    is_package: bool,
) -> str:
    if not node.level:
        return node.module or ""
    package = current_module if is_package else current_module.rpartition(".")[0]
    parts = package.split(".") if package else []
    if node.level > 1:
        parts = parts[: -(node.level - 1)]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _local_import_closure(
    root: Path,
    entrypoints: tuple[str, ...],
) -> tuple[set[str], list[str]]:
    by_name, preferred_name, errors = _local_module_index(root)
    stack: list[Path] = []
    for relative in entrypoints:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"runtime_boundary_entrypoint_missing:{relative}")
        else:
            stack.append(path)

    seen: set[Path] = set()
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        module_name = preferred_name.get(path)
        if module_name is None:
            errors.append(
                f"runtime_boundary_entrypoint_outside_module_roots:{path.relative_to(root)}"
            )
            continue

        parts = module_name.split(".")
        for index in range(1, len(parts)):
            package_path = by_name.get(".".join(parts[:index]))
            if package_path is not None and package_path.name == "__init__.py":
                stack.append(package_path)

        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (OSError, SyntaxError):
            errors.append(f"runtime_boundary_python_unreadable:{path.relative_to(root)}")
            continue
        for node in ast.walk(tree):
            imported: tuple[str, ...]
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported = (
                    _resolve_import_name(
                        node,
                        current_module=module_name,
                        is_package=path.name == "__init__.py",
                    ),
                )
            else:
                continue
            for name in imported:
                target = by_name.get(name)
                if target is not None:
                    stack.append(target)
                elif any(name.startswith(f"{prefix}.") for prefix in _LOCAL_MODULE_PREFIXES):
                    errors.append(
                        "runtime_boundary_local_import_unresolved:"
                        f"{path.relative_to(root)}:{name}"
                    )
                for index in range(1, len(name.split("."))):
                    package_path = by_name.get(".".join(name.split(".")[:index]))
                    if package_path is not None and package_path.name == "__init__.py":
                        stack.append(package_path)

    return {path.relative_to(root).as_posix() for path in seen}, errors


def _runtime_requirement_pins(root: Path) -> tuple[dict[str, str], list[str]]:
    relative = RUNTIME_REQUIREMENTS_RELATIVE_PATH
    path = root / relative
    if path.is_symlink() or not path.is_file():
        return {}, [f"runtime_boundary_requirements_missing:{relative}"]
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}, [f"runtime_boundary_requirements_invalid:{relative}"]
    pins: dict[str, str] = {}
    errors: list[str] = []
    for line_number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", line)
        if match is None:
            errors.append(f"runtime_boundary_requirement_invalid:{line_number}")
            continue
        raw_name, version = match.groups()
        name = re.sub(r"[-_.]+", "-", raw_name).lower()
        if name in pins:
            errors.append(f"runtime_boundary_requirement_duplicate:{name}")
        pins[name] = version
    return pins, errors


def _has_eager_wsgi_application(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError):
        return False
    identity_factory_imported = any(
        isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module == "pipeline.public_identity_middleware"
        and any(
            alias.name == "create_authenticated_wsgi_app" and alias.asname is None
            for alias in node.names
        )
        for node in tree.body
    )
    server_factories_imported = any(
        isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module == "pipeline.server"
        and {alias.name for alias in node.names if alias.asname is None}.issuperset(
            {"EX_CONFIG", "create_wsgi_app"}
        )
        for node in tree.body
    )
    if not identity_factory_imported or not server_factories_imported:
        return False

    protected_rebindings = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id
        in {"EX_CONFIG", "create_authenticated_wsgi_app", "create_wsgi_app"}
        and isinstance(node.ctx, (ast.Store, ast.Del))
    }
    if protected_rebindings:
        return False

    app_bindings = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "app"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if len(app_bindings) != 1:
        return False

    for statement in tree.body:
        if (
            not isinstance(statement, ast.Try)
            or len(statement.body) != 1
            or len(statement.handlers) != 1
            or statement.orelse
            or statement.finalbody
        ):
            continue
        assignment = statement.body[0]
        handler = statement.handlers[0]
        if (
            not isinstance(assignment, ast.Assign)
            or len(assignment.targets) != 1
            or not isinstance(assignment.targets[0], ast.Name)
            or assignment.targets[0].id != "app"
            or not isinstance(assignment.value, ast.Call)
            or not isinstance(assignment.value.func, ast.Name)
            or assignment.value.func.id != "create_authenticated_wsgi_app"
            or len(assignment.value.args) != 1
            or not isinstance(assignment.value.args[0], ast.Name)
            or assignment.value.args[0].id != "create_wsgi_app"
            or assignment.value.keywords
            or not isinstance(handler.type, ast.Name)
            or handler.type.id != "Exception"
            or not handler.body
        ):
            continue
        terminal = handler.body[-1]
        if (
            isinstance(terminal, ast.Raise)
            and isinstance(terminal.exc, ast.Call)
            and isinstance(terminal.exc.func, ast.Name)
            and terminal.exc.func.id == "SystemExit"
            and len(terminal.exc.args) == 1
            and isinstance(terminal.exc.args[0], ast.Name)
            and terminal.exc.args[0].id == "EX_CONFIG"
            and not terminal.exc.keywords
        ):
            return True
    return False


def verify_runtime_package_boundary(root: Path) -> list[str]:
    """Verify the deployable server package closure independently of DLP receipts."""

    root = root.resolve()
    runtime_files, runtime_errors = _load_file_allowlist(
        root,
        RUNTIME_ALLOWLIST_RELATIVE_PATH,
        expected_schema="cloud-v2-runtime-file-allowlist-v1",
        expected_files=EXPECTED_RUNTIME_FILES,
    )
    builder_files, builder_errors = _load_file_allowlist(
        root,
        BUILDER_ALLOWLIST_RELATIVE_PATH,
        expected_schema="cloud-v2-builder-file-allowlist-v1",
        expected_files=EXPECTED_BUILDER_FILES,
    )
    errors = [*runtime_errors, *builder_errors]
    runtime_set = set(runtime_files)
    builder_set = set(builder_files)
    for relative in (*RUNTIME_ENTRYPOINTS, *RUNTIME_REQUIRED_RESOURCES):
        if relative not in runtime_set:
            errors.append(f"runtime_boundary_required_file_missing:{relative}")
    for relative in (*BUILDER_ENTRYPOINTS, *BUILDER_REQUIRED_RESOURCES):
        if relative not in builder_set:
            errors.append(f"builder_boundary_required_file_missing:{relative}")
    for relative in sorted(builder_set - runtime_set):
        errors.append(f"builder_boundary_not_packaged_in_runtime:{relative}")

    closure, closure_errors = _local_import_closure(root, RUNTIME_ENTRYPOINTS)
    errors.extend(closure_errors)
    for relative in sorted(closure - runtime_set):
        errors.append(f"runtime_boundary_local_dependency_missing:{relative}")

    pins, pin_errors = _runtime_requirement_pins(root)
    errors.extend(pin_errors)
    for name, version in sorted(RUNTIME_REQUIRED_DISTRIBUTIONS.items()):
        if pins.get(name) != version:
            errors.append(f"runtime_boundary_requirement_missing:{name}=={version}")

    if not _has_eager_wsgi_application(root / "deploy/pipeline/wsgi.py"):
        errors.append("runtime_boundary_wsgi_application_not_eager")
    return sorted(set(errors))


def verify_eval_artifacts(root: Path) -> list[str]:
    errors: list[str] = []
    eval_root = root / "eval"
    if not eval_root.is_dir() or eval_root.is_symlink():
        return ["eval_directory_missing_or_symlink"]

    discovered = {
        path.relative_to(root).as_posix()
        for path in eval_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    for relative in sorted(discovered - set(FIXED_EVAL_ARTIFACTS)):
        errors.append(f"unexpected_eval_artifact:{relative}")
    for relative, expected_digest in sorted(FIXED_EVAL_ARTIFACTS.items()):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"fixed_eval_artifact_missing_or_symlink:{relative}")
            continue
        if sha256_file(path) != expected_digest:
            errors.append(f"fixed_eval_artifact_hash_mismatch:{relative}")

    gold_path = root / GOLD_RELATIVE_PATH
    if gold_path.is_file() and not gold_path.is_symlink():
        try:
            gold = json.loads(gold_path.read_bytes())
            cases = gold.get("cases") if isinstance(gold, dict) else None
            review_policy = (
                gold.get("review_policy")
                if isinstance(gold, dict)
                and isinstance(gold.get("review_policy"), dict)
                else {}
            )
            pending = bool(
                isinstance(cases, list)
                and len(cases) == 80
                and review_policy.get("status") == "pending"
                and all(
                    isinstance(case, dict)
                    and case.get("review_status") == "pending"
                    and case.get("reviewer_type") is None
                    and case.get("reviewed_by") is None
                    and case.get("reviewed_at") is None
                    and case.get("answer_contract") is None
                    for case in cases
                )
            )
        except (UnicodeDecodeError, ValueError):
            pending = False
        if not pending:
            errors.append("checked_in_gold_must_be_80_case_pending_template")
    return errors


def verify_independent_skill_boundary(root: Path) -> list[str]:
    """Keep live-tool outputs under App-host orchestration."""

    errors: list[str] = []
    for relative in INDEPENDENT_SKILL_BOUNDARY_DOCS:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(f"independent_skill_doc_unreadable:{relative}")
            continue
        for marker in INDEPENDENT_SKILL_FORBIDDEN_COUPLING:
            if marker in text:
                errors.append(f"independent_skill_doc_coupling:{relative}:{marker}")
    return errors


def verify_knowledge_qa_boundary(root: Path) -> list[str]:
    """Keep independent live tools out of the knowledge QA skill contract."""

    errors: list[str] = []
    helper_relative = "skills/knowledge-graph-cloud/scripts/app_answer.py"
    helper_path = root / helper_relative
    try:
        helper_text = helper_path.read_text(encoding="utf-8")
        tree = ast.parse(helper_text, filename=helper_relative)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return ["knowledge_qa_boundary_helper_unreadable"]

    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    if "live_tool_for_query" in function_names:
        errors.append("knowledge_qa_boundary_embeds_live_tool_router")
    prompt_function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "build_app_prompt"
        ),
        None,
    )
    if prompt_function is None:
        errors.append("knowledge_qa_boundary_prompt_missing")
    else:
        argument_names = {
            argument.arg
            for argument in (
                list(prompt_function.args.posonlyargs)
                + list(prompt_function.args.args)
                + list(prompt_function.args.kwonlyargs)
            )
        }
        if "live_context" in argument_names:
            errors.append("knowledge_qa_boundary_accepts_live_context")

    for relative in KNOWLEDGE_QA_BOUNDARY_DOCS:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(f"knowledge_qa_boundary_doc_unreadable:{relative}")
            continue
        for marker in KNOWLEDGE_QA_FORBIDDEN_COUPLING:
            if marker in text:
                errors.append(f"knowledge_qa_boundary_doc_coupling:{relative}:{marker}")

    verify_script = root / "skills/knowledge-graph-cloud/scripts/verify.sh"
    try:
        verify_text = verify_script.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        errors.append("knowledge_qa_boundary_verify_unreadable")
    else:
        for relative in ("skills/weather/tests", "skills/search/tests"):
            if relative in verify_text:
                errors.append(f"knowledge_qa_boundary_accepts_independent_skill:{relative}")
    errors.extend(verify_independent_skill_boundary(root))
    return errors


def verify_package(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    try:
        expected = expected_delivery_files(root)
        expected_knowledge = expected_knowledge_files(root)
    except ValueError as exc:
        return [f"delivery_tree_invalid:{exc}"]
    errors.extend(verify_manifest(root, "CODE_MANIFEST.sha256", expected=expected))
    errors.extend(
        verify_manifest(root, "MANIFEST.sha256", expected=expected_knowledge)
    )

    errors.extend(verify_eval_artifacts(root))
    errors.extend(verify_knowledge_qa_boundary(root))
    errors.extend(verify_runtime_package_boundary(root))

    for relative in sorted(expected):
        path = root / relative
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if path.suffix == ".py":
            try:
                ast.parse(raw, filename=relative)
            except SyntaxError as exc:
                errors.append(f"python_syntax_error:{relative}:{exc.lineno}")
        if path.suffix == ".json":
            try:
                json.loads(raw)
            except (UnicodeDecodeError, ValueError):
                errors.append(f"json_invalid:{relative}")
        if (
            relative.startswith(DELIVERY_SCAN_PREFIXES)
            or relative in DELIVERY_SCAN_TOP_LEVEL
        ):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            errors.extend(scan_forbidden_text(relative, text))
    return sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    errors = verify_package(args.root)
    result = {
        "schema_version": "kg-cloud-package-verification-v1",
        "ok": not errors,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
