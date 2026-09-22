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


DELIVERY_DOCS = ("README.md", "DEPLOY.md", "USAGE.md")
EXCLUDED_DELIVERY_PATHS = frozenset({"deploy/pipeline/config.json"})
IGNORED_NAMES = frozenset({"__pycache__", ".DS_Store"})
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


def expected_delivery_files(root: Path) -> set[str]:
    expected = set(DELIVERY_DOCS)
    targets = (root / "deploy", root / "skills" / "knowledge-graph-cloud")
    for target in targets:
        if not target.is_dir() or target.is_symlink():
            raise ValueError(f"delivery directory missing or symlinked: {target}")
        for path in target.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"delivery symlink forbidden: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if any(part in IGNORED_NAMES for part in path.parts) or path.suffix == ".pyc":
                continue
            if relative in EXCLUDED_DELIVERY_PATHS:
                continue
            expected.add(relative)
    expected.update(FIXED_EVAL_ARTIFACTS)
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
        errors.append(f"forbidden_text:literal_api_key:{relative}")
    return errors


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


def verify_package(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    try:
        expected = expected_delivery_files(root)
    except ValueError as exc:
        return [f"delivery_tree_invalid:{exc}"]
    errors.extend(verify_manifest(root, "CODE_MANIFEST.sha256", expected=expected))
    errors.extend(verify_manifest(root, "MANIFEST.sha256"))

    errors.extend(verify_eval_artifacts(root))

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
        if relative.startswith(("deploy/", "skills/knowledge-graph-cloud/")):
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
