#!/usr/bin/env python3
"""Plan-only Phase 1 release, rollback, and exact cleanup contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Mapping


RELEASE_CONTRACT_VERSION = "cloud-v2-release-plan-v1"


class ReleaseContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PhaseApprovalRequired(PermissionError):
    pass


def _sha(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ReleaseContractError(f"invalid_{field}")
    return value


def _relative_path(value: str, field: str) -> str:
    if not value or value.startswith("/") or "\\" in value or "//" in value:
        raise ReleaseContractError(f"invalid_{field}")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseContractError(f"invalid_{field}")
    if any(character in value for character in "*?[]{}"):
        raise ReleaseContractError(f"glob_forbidden_in_{field}")
    return path.as_posix()


@dataclass(frozen=True)
class SuiteIdentity:
    suite_release_id: str
    code_identity_sha256: str
    authority_sha256: str
    bm25_sha256: str
    app_host_contract_sha256: str
    server_model_set_sha256: str
    embedding_manifest_sha256: str
    local_vector_manifest_sha256: str
    graph_manifest_sha256: str
    operator_companion_sha256: str

    def __post_init__(self) -> None:
        if not self.suite_release_id or any(char.isspace() for char in self.suite_release_id):
            raise ReleaseContractError("invalid_suite_release_id")
        for field, value in asdict(self).items():
            if field != "suite_release_id":
                _sha(value, field)


@dataclass(frozen=True)
class ReleasePlan:
    operation: str
    candidate: SuiteIdentity
    current_release_id: str
    rollback_release_id: str
    exact_targets: Mapping[str, str]
    exact_cleanup_targets: tuple[str, ...]
    execution_authorized: bool = False
    required_stop: str = "D"
    schema_version: str = RELEASE_CONTRACT_VERSION

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "candidate": asdict(self.candidate),
            "current_release_id": self.current_release_id,
            "rollback_release_id": self.rollback_release_id,
            "exact_targets": dict(sorted(self.exact_targets.items())),
            "exact_cleanup_targets": list(self.exact_cleanup_targets),
            "execution_authorized": self.execution_authorized,
            "required_stop": self.required_stop,
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.manifest(),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


class ReleaseController:
    def plan(
        self,
        *,
        candidate: SuiteIdentity,
        current_release_id: str,
        rollback_release_id: str,
        exact_targets: Mapping[str, str],
        exact_cleanup_targets: tuple[str, ...] = (),
    ) -> ReleasePlan:
        if not current_release_id or not rollback_release_id:
            raise ReleaseContractError("release_pair_required")
        if current_release_id == candidate.suite_release_id:
            raise ReleaseContractError("candidate_already_active")
        if rollback_release_id == candidate.suite_release_id:
            raise ReleaseContractError("rollback_must_precede_candidate")
        required_targets = {
            "code",
            "authority",
            "bm25",
            "chunk_vector",
            "entity_vector",
            "graph",
            "app_host_contract",
            "server_model_set",
            "embedding",
            "operator_companion",
        }
        if set(exact_targets) != required_targets:
            raise ReleaseContractError("exact_target_set_mismatch")
        normalized_targets = {
            key: _relative_path(value, f"target_{key}") for key, value in exact_targets.items()
        }
        cleanup = tuple(
            _relative_path(value, "cleanup_target") for value in exact_cleanup_targets
        )
        if len(cleanup) != len(set(cleanup)):
            raise ReleaseContractError("duplicate_cleanup_target")
        return ReleasePlan(
            operation="atomic-suite-switch",
            candidate=candidate,
            current_release_id=current_release_id,
            rollback_release_id=rollback_release_id,
            exact_targets=normalized_targets,
            exact_cleanup_targets=cleanup,
        )

    def execute(self, plan: ReleasePlan) -> None:
        del plan
        raise PhaseApprovalRequired("Phase 1 controller is plan-only; Stop D approval is required")
