#!/usr/bin/env python3
"""Compile sealed Stop B fixtures into provider-neutral adapter payloads.

This module has no provider transport and never compiles provider-specific wire
bytes.  It only proves the deterministic bytes presented to the two local
provider-neutral adapters while real external processing remains unauthorized.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal Stop B probe CLI bootstrap context is required\n")
    raise SystemExit(2)

import argparse
import base64
import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from deploy.cloud_v2.dlp import (
    DLPError,
    _held_payload,
    _open_held_payload,
    _revalidate_held_payload,
)
from deploy.cloud_v2.offline_evidence import (
    OfflineEvidenceError,
    _require_formal_bootstrap_context,
    _require_isolated_python,
)

from deploy.cloud_v2.stop_b_request import (
    StopBRequestError,
    validate_stop_b_request,
)
from deploy.rag_store.embedding_adapter import (
    EMBEDDING_REQUEST_SCHEMA_VERSION,
    EmbeddingIdentity,
    EmbeddingInput,
    EmbeddingPolicy,
)
from deploy.rag_store.server_answer_model import (
    ServerAnswerChannel,
    ServerAnswerRequest,
)


FIXTURE_SCHEMA_VERSION = "cloud-v2-stop-b-synthetic-probes-v2"
RECEIPT_SCHEMA_VERSION = "cloud-v2-stop-b-probe-compilation-receipt-v1"
FIXTURE_RELATIVE_PATH = Path("deploy/cloud_v2/stop-b-synthetic-probes.json")
RUNNER_RELATIVE_PATH = Path("deploy/cloud_v2/stop_b_probe.py")
SEALED_FIXTURE_SHA256 = (
    "b4e61988c9293425f87db47d96bc777840f9f4e216ffbe7b4deb88413b535f61"
)
_PURPOSES = ("build", "query", "entity")


class StopBProbeError(RuntimeError):
    """A sealed fixture, compilation, or approval binding failed closed."""


_FORMAL_STOP_B_PROBE_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_EXECUTED_STOP_B_PROBE_SOURCE = _open_held_payload(
    Path(__file__),
    "Stop B probe source",
    max_bytes=2 * 1024 * 1024,
)
_FORMAL_STOP_B_PROBE_SOURCE_SHA256: str | None = None
_FORMAL_STOP_B_PROBE_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_STOP_B_PROBE_ACTION_CLOSURE: tuple[object, ...] | None = None


def _stop_b_probe_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_STOP_B_PROBE_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_stop_b_probe_action_closure() -> tuple[object, ...]:
    return (_parser, compile_stop_b_probe, _compile_stop_b_probe_impl)


def _install_formal_stop_b_probe_bootstrap_context(
    binding: Mapping[str, Any],
) -> None:
    global _FORMAL_STOP_B_PROBE_ACTION_CLOSURE
    global _FORMAL_STOP_B_PROBE_SOURCE_SHA256
    global _FORMAL_STOP_B_PROBE_SOURCE_STATE_IDENTITY

    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        raise StopBProbeError(
            "formal Stop B probe CLI bootstrap context is required"
        ) from exc
    required = {*_FORMAL_STOP_B_PROBE_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or len(str(binding["sha256"])) != 64
        or any(character not in "0123456789abcdef" for character in str(binding["sha256"]))
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _FORMAL_STOP_B_PROBE_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise StopBProbeError("formal Stop B probe CLI source binding is malformed")
    expected_state = {
        field: int(binding[field])
        for field in _FORMAL_STOP_B_PROBE_SOURCE_STATE_FIELDS
    }
    try:
        _revalidate_held_payload(_EXECUTED_STOP_B_PROBE_SOURCE)
    except DLPError as exc:
        raise StopBProbeError(
            "formal Stop B probe CLI source binding changed"
        ) from exc
    if (
        _sha256_bytes(_EXECUTED_STOP_B_PROBE_SOURCE.payload) != binding["sha256"]
        or _stop_b_probe_source_state_identity() != expected_state
    ):
        raise StopBProbeError(
            "formal Stop B probe CLI source differs from held bootstrap bytes"
        )
    _FORMAL_STOP_B_PROBE_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_STOP_B_PROBE_SOURCE_STATE_IDENTITY = expected_state
    _FORMAL_STOP_B_PROBE_ACTION_CLOSURE = _current_stop_b_probe_action_closure()


def _require_formal_stop_b_probe_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_STOP_B_PROBE_SOURCE_SHA256
    source_state = _FORMAL_STOP_B_PROBE_SOURCE_STATE_IDENTITY
    actions = _FORMAL_STOP_B_PROBE_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_FORMAL_STOP_B_PROBE_SOURCE_STATE_FIELDS)
        or any(
            type(source_state.get(field)) is not int or int(source_state[field]) < 0
            for field in _FORMAL_STOP_B_PROBE_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != 3
    ):
        raise StopBProbeError(
            "formal Stop B probe CLI bootstrap context is required"
        )
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
        _revalidate_held_payload(_EXECUTED_STOP_B_PROBE_SOURCE)
    except (OfflineEvidenceError, DLPError) as exc:
        raise StopBProbeError(
            "formal Stop B probe CLI source binding changed"
        ) from exc
    if (
        _sha256_bytes(_EXECUTED_STOP_B_PROBE_SOURCE.payload) != source_sha256
        or _stop_b_probe_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_stop_b_probe_action_closure(), actions, strict=True
            )
        )
    ):
        raise StopBProbeError(
            "formal Stop B probe CLI source or action closure changed"
        )
    return actions


@dataclass(frozen=True)
class ParsedFixture:
    server_answer: ServerAnswerRequest
    embedding_by_purpose: Mapping[str, tuple[EmbeddingInput, ...]]
    call_counts: Mapping[str, Any]


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StopBProbeError("value is not canonical JSON") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StopBProbeError("fixture contains a duplicate object key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise StopBProbeError("fixture contains a non-finite JSON number")


def _decode_json_object(raw: bytes, field: str) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise StopBProbeError(f"{field} must be bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_json_constant,
        )
    except StopBProbeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StopBProbeError(f"{field} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise StopBProbeError(f"{field} root must be an object")
    return value


def _exact_keys(value: object, expected: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise StopBProbeError(f"{field} does not match its closed schema")
    return value


def _exact_text(value: object, expected: str, field: str) -> None:
    if type(value) is not str or value != expected:
        raise StopBProbeError(f"{field} is outside the sealed contract")


def _required_text(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise StopBProbeError(f"{field} must be a non-empty normalized string")
    return value


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise StopBProbeError(f"{field} must be a positive integer")
    return value


def _exact_bool(value: object, expected: bool, field: str) -> None:
    if type(value) is not bool or value is not expected:
        raise StopBProbeError(f"{field} is outside the sealed authorization state")


def _parse_server_answer(value: object) -> ServerAnswerRequest:
    payload = _exact_keys(
        value,
        {"request_id", "question", "evidence", "input_units"},
        "payloads.server_answer",
    )
    request_id = _required_text(payload["request_id"], "server_answer.request_id")
    question = _required_text(payload["question"], "server_answer.question")
    input_units = _positive_int(
        payload["input_units"], "server_answer.input_units"
    )
    evidence_value = payload["evidence"]
    if not isinstance(evidence_value, list) or not evidence_value:
        raise StopBProbeError("server_answer.evidence must be a non-empty array")
    evidence: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, item_value in enumerate(evidence_value):
        item = _exact_keys(
            item_value,
            {"evidence_id", "text"},
            f"server_answer.evidence[{index}]",
        )
        evidence_id = _required_text(
            item["evidence_id"], f"server_answer.evidence[{index}].evidence_id"
        )
        text = _required_text(
            item["text"], f"server_answer.evidence[{index}].text"
        )
        if evidence_id in seen_ids:
            raise StopBProbeError("server_answer evidence ids must be unique")
        seen_ids.add(evidence_id)
        evidence.append({"evidence_id": evidence_id, "text": text})
    measured_units = len(question) + sum(len(item["text"]) for item in evidence)
    if input_units != measured_units:
        raise StopBProbeError("server_answer.input_units drifted from its unit contract")
    return ServerAnswerRequest(
        request_id=request_id,
        question=question,
        evidence=tuple(evidence),
        input_units=input_units,
    )


def _parse_embedding_item(value: object, field: str) -> EmbeddingInput:
    item = _exact_keys(value, {"object_id", "text", "input_units"}, field)
    object_id = _required_text(item["object_id"], f"{field}.object_id")
    text = _required_text(item["text"], f"{field}.text")
    input_units = _positive_int(item["input_units"], f"{field}.input_units")
    if input_units != len(text):
        raise StopBProbeError(f"{field}.input_units drifted from its unit contract")
    return EmbeddingInput(
        object_id=object_id,
        text=text,
        input_units=input_units,
    )


def _parse_call_contract(value: object) -> dict[str, Any]:
    contract = _exact_keys(
        value,
        {
            "server_answer_calls_per_approved_channel",
            "embedding_calls_by_purpose",
            "single_server_channel_total",
        },
        "call_contract",
    )
    server_calls = _positive_int(
        contract["server_answer_calls_per_approved_channel"],
        "call_contract.server_answer_calls_per_approved_channel",
    )
    embedding_value = _exact_keys(
        contract["embedding_calls_by_purpose"],
        set(_PURPOSES),
        "call_contract.embedding_calls_by_purpose",
    )
    embedding_calls = {
        purpose: _positive_int(
            embedding_value[purpose],
            f"call_contract.embedding_calls_by_purpose.{purpose}",
        )
        for purpose in _PURPOSES
    }
    total = _positive_int(
        contract["single_server_channel_total"],
        "call_contract.single_server_channel_total",
    )
    if server_calls != 1 or any(count != 1 for count in embedding_calls.values()):
        raise StopBProbeError("synthetic request call counts drifted")
    if total != server_calls + sum(embedding_calls.values()):
        raise StopBProbeError("synthetic total call count drifted")
    return {
        "embedding_calls_by_purpose": embedding_calls,
        "server_answer_calls_per_approved_channel": server_calls,
        "single_server_channel_total": total,
    }


def parse_fixture_bytes(fixture_bytes: bytes) -> ParsedFixture:
    if _sha256_bytes(fixture_bytes) != SEALED_FIXTURE_SHA256:
        raise StopBProbeError("fixture bytes do not match the sealed SHA-256")
    root = _exact_keys(
        _decode_json_object(fixture_bytes, "fixture"),
        {
            "schema_version",
            "status",
            "unit_contract",
            "call_contract",
            "payloads",
            "contains_real_source_or_user_data",
            "provider_calls_authorized",
            "provider_specific_wire_bytes_authorized",
        },
        "fixture",
    )
    _exact_text(root["schema_version"], FIXTURE_SCHEMA_VERSION, "schema_version")
    _exact_text(
        root["status"],
        "sealed-offline-provider-neutral-fixture",
        "status",
    )
    unit_contract = _exact_keys(
        root["unit_contract"],
        {
            "name",
            "server_answer_input_units",
            "embedding_input_units",
        },
        "unit_contract",
    )
    _exact_text(
        unit_contract["name"], "unicode-code-point-count-v1", "unit_contract.name"
    )
    _exact_text(
        unit_contract["server_answer_input_units"],
        "question-plus-evidence-text",
        "unit_contract.server_answer_input_units",
    )
    _exact_text(
        unit_contract["embedding_input_units"],
        "text",
        "unit_contract.embedding_input_units",
    )
    _exact_bool(
        root["contains_real_source_or_user_data"],
        False,
        "contains_real_source_or_user_data",
    )
    _exact_bool(
        root["provider_calls_authorized"], False, "provider_calls_authorized"
    )
    _exact_bool(
        root["provider_specific_wire_bytes_authorized"],
        False,
        "provider_specific_wire_bytes_authorized",
    )
    payloads = _exact_keys(
        root["payloads"], {"server_answer", "embedding"}, "payloads"
    )
    server_answer = _parse_server_answer(payloads["server_answer"])
    embedding_value = _exact_keys(
        payloads["embedding"], set(_PURPOSES), "payloads.embedding"
    )
    embedding_by_purpose: dict[str, tuple[EmbeddingInput, ...]] = {}
    seen_object_ids: set[str] = set()
    for purpose in _PURPOSES:
        item_values = embedding_value[purpose]
        if not isinstance(item_values, list) or not item_values:
            raise StopBProbeError(f"embedding.{purpose} must be a non-empty array")
        items = tuple(
            _parse_embedding_item(item, f"embedding.{purpose}[{index}]")
            for index, item in enumerate(item_values)
        )
        for item in items:
            if item.object_id in seen_object_ids:
                raise StopBProbeError("embedding object ids must be globally unique")
            seen_object_ids.add(item.object_id)
        embedding_by_purpose[purpose] = items
    call_counts = _parse_call_contract(root["call_contract"])
    for purpose in _PURPOSES:
        if len(embedding_by_purpose[purpose]) != call_counts[
            "embedding_calls_by_purpose"
        ][purpose]:
            raise StopBProbeError("embedding item count drifted from its call contract")
    return ParsedFixture(
        server_answer=server_answer,
        embedding_by_purpose=embedding_by_purpose,
        call_counts=call_counts,
    )


def synthetic_server_channel() -> ServerAnswerChannel:
    return ServerAnswerChannel(
        channel_id="synthetic-server-answer-channel",
        provider="offline-fake-provider",
        base_url="https://server-answer.invalid/v1/generate",
        region="synthetic-offline-region",
        model="offline-fake-answer-model",
        model_version="offline-fake-model-v1",
        api_version="offline-fake-api-v1",
        timeout_seconds=1.0,
        max_input_units=41,
        max_output_units=64,
        max_cost_microunits=0,
        max_request_bytes=16_384,
        max_response_bytes=16_384,
    )


def synthetic_embedding_identity() -> EmbeddingIdentity:
    return EmbeddingIdentity(
        provider="offline-fake-provider",
        base_url="https://embedding.invalid/v1/embed",
        region="synthetic-offline-region",
        model="offline-fake-embedding-model",
        model_version="offline-fake-model-v1",
        api_version="offline-fake-api-v1",
        dimension=8,
        normalization="l2",
        input_type="document-or-query-text-v1",
    )


def synthetic_embedding_policy() -> EmbeddingPolicy:
    return EmbeddingPolicy(
        batch_size=1,
        max_input_units=24,
        timeout_seconds=1.0,
        max_retries=0,
        max_requests_per_operation=1,
        max_cost_microunits_per_request=0,
        total_cost_budget_microunits=0,
        max_request_bytes=16_384,
        max_response_bytes=16_384,
    )


def _embedding_payload_bytes(
    purpose: str,
    items: tuple[EmbeddingInput, ...],
    identity: EmbeddingIdentity,
    policy: EmbeddingPolicy,
) -> bytes:
    normalized = [item.normalized(policy.max_input_units) for item in items]
    if len(normalized) != 1:
        raise StopBProbeError("synthetic embedding payload must compile to one call")
    return _canonical_bytes(
        {
            "schema_version": EMBEDDING_REQUEST_SCHEMA_VERSION,
            "embedding_identity_sha256": identity.sha256,
            "purpose": purpose,
            "input_type": identity.input_type,
            "items": normalized,
        }
    )


def _request_record(request_key: str, payload_bytes: bytes) -> dict[str, Any]:
    return {
        "request_key": request_key,
        "call_count": 1,
        "payload_size_bytes": len(payload_bytes),
        "payload_sha256": _sha256_bytes(payload_bytes),
        "payload_canonical_json_utf8_base64": base64.b64encode(
            payload_bytes
        ).decode("ascii"),
    }


def compile_fixture_bytes(
    fixture_bytes: bytes,
    *,
    runner_bytes: bytes,
) -> dict[str, Any]:
    if not isinstance(runner_bytes, bytes) or not runner_bytes:
        raise StopBProbeError("runner must be non-empty bytes")
    parsed = parse_fixture_bytes(fixture_bytes)
    channel = synthetic_server_channel()
    identity = synthetic_embedding_identity()
    policy = synthetic_embedding_policy()
    try:
        server_payload_bytes = _canonical_bytes(
            parsed.server_answer.payload(channel)
        )
        requests = [_request_record("server_answer", server_payload_bytes)]
        requests.extend(
            _request_record(
                f"embedding.{purpose}.0",
                _embedding_payload_bytes(
                    purpose,
                    parsed.embedding_by_purpose[purpose],
                    identity,
                    policy,
                ),
            )
            for purpose in _PURPOSES
        )
    except (TypeError, ValueError) as exc:
        raise StopBProbeError("fixture does not compile under the current adapters") from exc
    request_set_binding = {
        "call_counts": parsed.call_counts,
        "requests": [
            {
                "call_count": record["call_count"],
                "payload_sha256": record["payload_sha256"],
                "payload_size_bytes": record["payload_size_bytes"],
                "request_key": record["request_key"],
            }
            for record in requests
        ],
    }
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "offline-provider-neutral-payloads-compiled",
        "authorized": False,
        "fixture": {
            "path": FIXTURE_RELATIVE_PATH.as_posix(),
            "sha256": _sha256_bytes(fixture_bytes),
        },
        "runner": {
            "path": RUNNER_RELATIVE_PATH.as_posix(),
            "sha256": _sha256_bytes(runner_bytes),
        },
        "compilation_boundary": {
            "semantic_fixture": True,
            "provider_neutral_adapter_payload_bytes": True,
            "provider_specific_wire_bytes": False,
        },
        "adapter_contracts": {
            "server_answer_channel_identity_sha256": channel.identity_sha256,
            "embedding_identity_sha256": identity.sha256,
            "embedding_policy_sha256": policy.sha256,
        },
        "call_counts": parsed.call_counts,
        "requests": requests,
        "request_set_sha256": _sha256_bytes(
            _canonical_bytes(request_set_binding)
        ),
    }


def _compile_stop_b_probe_impl(repo_root: Path) -> dict[str, Any]:
    if not isinstance(repo_root, Path):
        raise StopBProbeError("repo_root must be a pathlib.Path")
    try:
        root = repo_root.resolve(strict=True)
    except OSError as exc:
        raise StopBProbeError("probe repository root is unavailable") from exc
    if not root.is_dir() or repo_root.is_symlink():
        raise StopBProbeError("probe repository root must be a real directory")
    fixture_path = root / FIXTURE_RELATIVE_PATH
    runner_path = root / RUNNER_RELATIVE_PATH
    try:
        with _held_payload(
            fixture_path,
            "sealed Stop B probe fixture",
            max_bytes=2 * 1024 * 1024,
        ) as fixture, _held_payload(
            runner_path,
            "sealed Stop B probe runner",
            max_bytes=2 * 1024 * 1024,
        ) as runner:
            _revalidate_held_payload(_EXECUTED_STOP_B_PROBE_SOURCE)
            if runner.payload != _EXECUTED_STOP_B_PROBE_SOURCE.payload:
                raise StopBProbeError(
                    "probe repository runner differs from executed held bytes"
                )
            result = compile_fixture_bytes(
                fixture.payload,
                runner_bytes=_EXECUTED_STOP_B_PROBE_SOURCE.payload,
            )
            _revalidate_held_payload(_EXECUTED_STOP_B_PROBE_SOURCE)
            return result
    except (DLPError, OSError) as exc:
        raise StopBProbeError("sealed probe inputs are unavailable") from exc


def compile_stop_b_probe(repo_root: Path) -> dict[str, Any]:
    actions = _require_formal_stop_b_probe_bootstrap_context()
    return actions[2](repo_root)


def require_provider_specific_wire_receipt(
    stop_b_request: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return the complete per-role offline wire receipt set.

    Approval readiness is deliberately non-authorizing: every role slot must be
    sealed, while ``provider_calls_authorized`` remains false.  The later Stop B
    approval receipt is an execution gate and is not an input to wire compilation.
    """

    if not isinstance(stop_b_request, Mapping):
        raise StopBProbeError("Stop B request must be an object")
    try:
        validated = validate_stop_b_request(stop_b_request, mode="approval_ready")
    except StopBRequestError as exc:
        raise StopBProbeError(
            f"provider-specific wire receipts are not approval-ready: {exc.code}"
        ) from exc
    state = validated["provider_specific_wire_compilation"]
    if (
        state["status"] != "compiled-offline-awaiting-stop-b-approval"
        or state["provider_calls_authorized"] is not False
        or not state["role_slots"]
    ):
        raise StopBProbeError("provider-specific wire receipts are absent")
    return state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    return parser


def _run_cli(
    argv: Sequence[str] | None = None,
    *,
    _action_closure: tuple[object, ...] | None = None,
) -> int:
    actions = (
        _current_stop_b_probe_action_closure()[:2]
        if _action_closure is None
        else _action_closure
    )
    if not isinstance(actions, tuple) or len(actions) != 2 or any(
        not callable(action) for action in actions
    ):
        raise StopBProbeError("Stop B probe CLI action closure is malformed")
    parser_action, compile_action = actions
    args = parser_action().parse_args(argv)
    print(
        json.dumps(
            compile_action(Path(args.repo_root)),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        actions = _require_formal_stop_b_probe_bootstrap_context()
    except StopBProbeError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    return _run_cli(argv, _action_closure=actions[:2])


if __name__ == "__main__":
    raise SystemExit(main())
