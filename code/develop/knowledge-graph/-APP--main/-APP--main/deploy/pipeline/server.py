#!/usr/bin/env python3
"""Public ordinary-QA endpoint over sealed, read-only cloud artifacts."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import sys
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge


_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "deploy"))

from pipeline.cloud_runtime import (  # noqa: E402
    CloudRuntimeDependencyError,
    CloudRuntimeResources,
)
from pipeline.provider_bootstrap import (  # noqa: E402
    ProviderBootstrapError,
    load_provider_bound_runtime_from_environment,
)
from deploy.cloud_v2.identity_policy import (  # noqa: E402
    PUBLIC_AUDIENCE,
    VerifiedIdentity,
    authorize_public_ask,
    public_tool_registry,
    verified_identity_from_wsgi_environ,
)
from rag_store.authoritative_extractive_fallback import (  # noqa: E402
    POLICY_VERSION as EXTRACTIVE_POLICY_VERSION,
    build_authoritative_extractive_fallback,
    hydrate_sqlite_authority_sources,
)
from rag_store.cloud_claim_evidence import (  # noqa: E402
    FAIL_CLOSED_ANSWER,
    evidence_aliases,
    finalize_claim_evidence,
    parse_claim_map,
    synthesize_claim_map,
)
from rag_store.runtime_query_embedding import QueryEmbeddingError  # noqa: E402
from rag_store.query_rewrite import QueryRewriter  # noqa: E402
from rag_store.question_bank_match import (  # noqa: E402
    build_exact_question_answer,
    match_original_question,
)
from rag_store.request_envelope import (  # noqa: E402
    ALLOWED_SOURCES,
    RequestEnvelopeError,
    parse_request_envelope,
)
from rag_store.route_policy import out_of_scope_internal_fact_reason  # noqa: E402
from rag_store.source_authority import (  # noqa: E402
    filter_superseded,
    source_priority_key,
)


ANSWER_CONTRACT_HEADER = "X-KG-Answer-Contract"
ANSWER_CONTRACT_VERSION = "ordinary-qa-compat-v1"
PUBLIC_ENTRYPOINT_SCHEMA_VERSION = "cloud-v2-public-entrypoint-v1"
PUBLIC_ENTRYPOINT_ID = "public-app-agent-wsgi-v1"
PUBLIC_API_PATH = "/api/ask"
RUNTIME_SOURCE_POLICY_VERSION = "cloud-v2-read-only-retrieval-v1"
SUPPORTED_RETRIEVAL_SOURCES = frozenset(
    {"sqlite_exact", "bm25", "dense", "neo4j"}
)
MAX_RETRIEVAL_RESULTS = 20
MAX_RESPONSE_SOURCES = 10
MAX_REQUEST_BODY_BYTES = 16 * 1024
EX_CONFIG = 78
DEGRADED_NOTICE = (
    "当前知识服务未形成可验证的专业参考；App 将继续由宿主模型回答，"
    "但不应把本次知识服务结果标记为已核实。"
)

RuntimeLoader = Callable[[], CloudRuntimeResources]
VerifiedIdentityLoader = Callable[[Mapping[str, Any]], VerifiedIdentity]


def _canonical_source_kind(doc_name: str) -> str:
    normalized = str(doc_name or "").replace("_", "/", 1)
    if normalized.startswith("政策法规/"):
        return "regulation"
    if normalized.startswith(("理论题库/", "实操题库/", "题库/")):
        return "question_bank"
    if normalized.startswith("无人机理论书籍/"):
        return "textbook"
    if normalized.startswith("地面站考题考试条件/"):
        return "exam_condition"
    return "unknown"


def _source_priority(
    source: Mapping[str, Any],
    regulation_timeline: Mapping[str, Mapping[str, Any]],
) -> tuple[int, int, int, int, float, str]:
    return source_priority_key(source, timeline=regulation_timeline)


def _query_bigrams(value: Any) -> set[str]:
    normalized = "".join(
        character.casefold()
        for character in str(value or "")
        if character.isalnum()
    )
    return {
        normalized[index : index + 2]
        for index in range(max(0, len(normalized) - 1))
    }


def _relevance_filtered_sources(
    sources: Sequence[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    query_bigrams = _query_bigrams(query)
    if not query_bigrams:
        return list(sources)
    scored = [
        (len(query_bigrams.intersection(_query_bigrams(source.get("text")))), source)
        for source in sources
    ]
    maximum = max((score for score, _source in scored), default=0)
    if maximum <= 0:
        return list(sources)
    minimum = max(1, (maximum * 4 + 4) // 5)
    return [source for score, source in scored if score >= minimum]


def _merge_sources(
    *groups: Sequence[Mapping[str, Any]],
    regulation_timeline: Mapping[str, Mapping[str, Any]],
    query: str = "",
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    origins: dict[str, set[str]] = {}
    for group in groups:
        for raw in group:
            if not isinstance(raw, Mapping):
                continue
            chunk_id = str(raw.get("chunk_id") or "").strip()
            text = str(raw.get("text") or "").strip()
            doc_name = str(raw.get("doc_name") or "").strip()
            if not chunk_id or not text or not doc_name:
                continue
            candidate = dict(raw)
            current = by_id.get(chunk_id)
            if current is None or _source_priority(
                candidate, regulation_timeline
            ) < _source_priority(current, regulation_timeline):
                by_id[chunk_id] = candidate
            origin = str(raw.get("source") or raw.get("type") or "authority")
            origins.setdefault(chunk_id, set()).add(origin)

    relevant = _relevance_filtered_sources(list(by_id.values()), query)
    ranked = sorted(
        relevant,
        key=lambda item: _source_priority(item, regulation_timeline),
    )[:MAX_RETRIEVAL_RESULTS]
    for position, item in enumerate(ranked, start=1):
        chunk_id = str(item["chunk_id"])
        item["seq"] = position
        item["type"] = _canonical_source_kind(str(item["doc_name"]))
        item["retrieval_origins"] = sorted(origins[chunk_id])
    return ranked


def _query_terms(question: str, rewrite: Mapping[str, Any]) -> list[str]:
    values: list[str] = [question, str(rewrite.get("rewritten") or "")]
    values.extend(str(item) for item in rewrite.get("keywords", []) if str(item))
    values.extend(
        str(item.get("name") or "")
        for item in rewrite.get("entities", [])
        if isinstance(item, Mapping)
    )
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))[:8]


def _response_sources(
    sources: Sequence[Mapping[str, Any]], accepted_ids: set[str]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in sources:
        chunk_id = str(source.get("chunk_id") or "")
        if chunk_id not in accepted_ids:
            continue
        records.append(
            {
                "chunk_id": chunk_id,
                "doc_name": str(source.get("doc_name") or ""),
                "seq": int(source.get("seq") or len(records) + 1),
                "type": _canonical_source_kind(str(source.get("doc_name") or "")),
            }
        )
        if len(records) >= MAX_RESPONSE_SOURCES:
            break
    return records


def _response(
    *,
    trace_id: str,
    question: str,
    request_contract: Mapping[str, Any],
    route: str,
    answer: str,
    degraded: bool,
    degraded_reasons: Sequence[str],
    sources: Sequence[Mapping[str, Any]] = (),
    accepted_ids: set[str] | None = None,
    graph_result: Mapping[str, Any] | None = None,
    claim_evidence: Mapping[str, Any] | None = None,
    retrieval_counts: Mapping[str, int] | None = None,
    model_invocation_count: int = 0,
) -> dict[str, Any]:
    accepted = accepted_ids or set()
    graph = graph_result or {}
    source_records = _response_sources(sources, accepted)
    available = bool(answer.strip()) and not degraded and bool(source_records)
    return {
        "query": question,
        "route": route,
        "answer": answer.strip() or DEGRADED_NOTICE,
        "hit": available,
        "matched": available,
        "knowledge_available": available,
        "request_rejected": False,
        "degraded": degraded,
        "degraded_reasons": list(dict.fromkeys(degraded_reasons)),
        "sources": source_records,
        "evidence": [
            {"evidence_id": item["chunk_id"], "source_num": item["seq"]}
            for item in source_records
        ],
        "graph_paths": [
            dict(item)
            for item in graph.get("paths", [])
            if isinstance(item, Mapping)
        ][:MAX_RESPONSE_SOURCES],
        "evidence_bindings": [
            dict(item)
            for item in graph.get("evidence_bindings", [])
            if isinstance(item, Mapping)
            and str(item.get("chunk_id") or "") in accepted
        ][:MAX_RESPONSE_SOURCES],
        "claim_evidence": dict(claim_evidence or {}),
        "answer_recovery_status": route,
        "stats": {
            "trace_id": trace_id,
            "request_envelope": dict(request_contract),
            "retrieval_counts": dict(retrieval_counts or {}),
            "model_invocation_count": int(model_invocation_count),
            "external_completion": model_invocation_count > 0,
            "runtime_source_policy_version": RUNTIME_SOURCE_POLICY_VERSION,
        },
    }


def _finalize_deterministic(
    answer: str,
    claim_map: Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return finalize_claim_evidence(
        answer,
        claim_map,
        internal_sources=sources,
        trusted_deterministic=True,
    )


def _retrieve(
    runtime: CloudRuntimeResources,
    question: str,
    allowed_sources: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, int], list[str]]:
    rewrite = QueryRewriter().rewrite(question, use_llm=False)
    terms = _query_terms(question, rewrite)
    warnings: list[str] = []

    lexical: list[dict[str, Any]] = []
    if "sqlite_exact" in allowed_sources:
        lexical = runtime.authority_store.search_chunks(terms, limit=MAX_RETRIEVAL_RESULTS)
        for item in lexical:
            item["score"] = 100.0
            item["source"] = "sqlite_exact"

    sparse: list[dict[str, Any]] = []
    if "bm25" in allowed_sources:
        sparse = runtime.bm25_index.search(
            str(rewrite.get("rewritten") or question),
            limit=MAX_RETRIEVAL_RESULTS,
        )

    dense: list[dict[str, Any]] = []
    entity_evidence: list[dict[str, Any]] = []
    query_vector: list[float] | None = None
    if allowed_sources.intersection({"dense", "neo4j"}):
        try:
            query_vector = runtime.embed_query(str(rewrite.get("rewritten") or question))
        except (CloudRuntimeDependencyError, QueryEmbeddingError):
            warnings.append("embedding_query_unavailable")
    if query_vector is not None and "dense" in allowed_sources:
        dense = runtime.vector_index.search_by_embedding(
            query_vector, limit=MAX_RETRIEVAL_RESULTS
        )
    if query_vector is not None and "neo4j" in allowed_sources:
        entity_evidence = runtime.search_entity_evidence(
            query_vector, limit=MAX_RESPONSE_SOURCES
        )

    graph: dict[str, Any] = {
        "chunk_ids": [],
        "paths": [],
        "matched_entities": [],
        "evidence_bindings": [],
        "total": 0,
    }
    graph_sources: list[dict[str, Any]] = []
    if "neo4j" in allowed_sources:
        graph = runtime.recall_scoped_graph(
            query=question,
            entities=[
                item for item in rewrite.get("entities", []) if isinstance(item, Mapping)
            ],
            keywords=[str(item) for item in rewrite.get("keywords", []) if str(item)],
            limit=MAX_RESPONSE_SOURCES,
        )
        preliminary_ids = [
            str(item.get("chunk_id") or "")
            for item in [*lexical, *sparse, *dense]
            if str(item.get("chunk_id") or "")
        ]
        if preliminary_ids:
            graph = runtime.augment_scoped_graph_from_chunks(graph, preliminary_ids)
        graph_ids = [str(item) for item in graph.get("chunk_ids", []) if str(item)]
        if graph_ids:
            graph_sources = runtime.authority_store.require_chunks(graph_ids)
            for item in graph_sources:
                item["score"] = 75.0
                item["source"] = "scoped_graph"

    merged = _merge_sources(
        lexical,
        sparse,
        dense,
        graph_sources,
        regulation_timeline=runtime.regulation_timeline,
        query=question,
    )
    counts = {
        "sqlite_exact": len(lexical),
        "bm25": len(sparse),
        "dense": len(dense),
        "entity": len(entity_evidence),
        "scoped_graph": int(graph.get("total") or 0),
        "merged": len(merged),
    }
    return merged, graph, counts, warnings


def _answer_request(
    runtime: CloudRuntimeResources,
    *,
    trace_id: str,
    question: str,
    request_contract: Mapping[str, Any],
    allowed_sources: set[str],
) -> dict[str, Any]:
    if out_of_scope_internal_fact_reason(question):
        return _response(
            trace_id=trace_id,
            question=question,
            request_contract=request_contract,
            route="out_of_scope",
            answer=DEGRADED_NOTICE,
            degraded=True,
            degraded_reasons=["out_of_scope_internal_fact"],
        )

    sources, graph, counts, warnings = _retrieve(runtime, question, allowed_sources)
    if not sources:
        return _response(
            trace_id=trace_id,
            question=question,
            request_contract=request_contract,
            route="miss",
            answer=DEGRADED_NOTICE,
            degraded=True,
            degraded_reasons=[*warnings, "no_authoritative_evidence"],
            retrieval_counts=counts,
        )

    pre_filter_question_sources = [
        item for item in sources if item.get("type") == "question_bank"
    ]
    pre_filter_exact = build_exact_question_answer(
        match_original_question(question, pre_filter_question_sources),
        pre_filter_question_sources,
    )
    sources, superseded = filter_superseded(
        question,
        sources,
        passages=runtime.superseded_passages,
        exact_question_match=pre_filter_exact is not None,
    )
    if superseded:
        counts["superseded_excluded"] = len(superseded)
        warnings.append("superseded_evidence_excluded")
    if not sources:
        return _response(
            trace_id=trace_id,
            question=question,
            request_contract=request_contract,
            route="degraded",
            answer=DEGRADED_NOTICE,
            degraded=True,
            degraded_reasons=[*warnings, "no_current_authoritative_evidence"],
            graph_result=graph,
            retrieval_counts=counts,
            model_invocation_count=0,
        )

    regulation_sources = [
        item
        for item in sources
        if _canonical_source_kind(str(item.get("doc_name") or "")) == "regulation"
    ]
    if regulation_sources:
        try:
            regulation_rows = runtime.authority_store.require_chunks(
                [str(item["chunk_id"]) for item in regulation_sources]
            )
            hydrated_regulations = hydrate_sqlite_authority_sources(
                regulation_sources, regulation_rows
            )
            regulation_extractive = build_authoritative_extractive_fallback(
                question, hydrated_regulations
            )
        except Exception:
            return _response(
                trace_id=trace_id,
                question=question,
                request_contract=request_contract,
                route="degraded",
                answer=DEGRADED_NOTICE,
                degraded=True,
                degraded_reasons=[*warnings, "regulation_authority_pipeline_error"],
                graph_result=graph,
                retrieval_counts=counts,
                model_invocation_count=0,
            )
        if regulation_extractive["recovered"]:
            finalization = _finalize_deterministic(
                str(regulation_extractive["answer"]),
                regulation_extractive["claim_map"],
                hydrated_regulations,
            )
            if finalization["allowed"]:
                return _response(
                    trace_id=trace_id,
                    question=question,
                    request_contract=request_contract,
                    route="authoritative_extractive",
                    answer=str(finalization["answer"]),
                    degraded=False,
                    degraded_reasons=warnings,
                    sources=hydrated_regulations,
                    accepted_ids=set(
                        finalization["telemetry"]["accepted_evidence_ids"]
                    ),
                    graph_result=graph,
                    claim_evidence=finalization["telemetry"],
                    retrieval_counts=counts,
                    model_invocation_count=0,
                )
            return _response(
                trace_id=trace_id,
                question=question,
                request_contract=request_contract,
                route="degraded",
                answer=DEGRADED_NOTICE,
                degraded=True,
                degraded_reasons=[*warnings, "regulation_authority_finalizer_blocked"],
                graph_result=graph,
                retrieval_counts=counts,
                model_invocation_count=0,
            )

    question_sources = [item for item in sources if item.get("type") == "question_bank"]
    exact = build_exact_question_answer(
        match_original_question(question, question_sources), question_sources
    )
    if exact is not None:
        exact_ids = set(str(item) for item in exact["evidence_ids"])
        exact_sources = [item for item in question_sources if item["chunk_id"] in exact_ids]
        finalization = _finalize_deterministic(
            str(exact["answer"]),
            synthesize_claim_map(
                exact["answer"], evidence_aliases(internal_sources=exact_sources)
            ),
            exact_sources,
        )
        if finalization["allowed"]:
            return _response(
                trace_id=trace_id,
                question=question,
                request_contract=request_contract,
                route="question_bank_exact",
                answer=str(finalization["answer"]),
                degraded=False,
                degraded_reasons=warnings,
                sources=exact_sources,
                accepted_ids=set(finalization["telemetry"]["accepted_evidence_ids"]),
                graph_result=graph,
                claim_evidence=finalization["telemetry"],
                retrieval_counts=counts,
                model_invocation_count=0,
            )

    sources = [
        item
        for item in sources
        if _canonical_source_kind(str(item.get("doc_name") or ""))
        != "question_bank"
    ]
    if not sources:
        return _response(
            trace_id=trace_id,
            question=question,
            request_contract=request_contract,
            route="degraded",
            answer=DEGRADED_NOTICE,
            degraded=True,
            degraded_reasons=[*warnings, "non_exact_question_bank_excluded"],
            graph_result=graph,
            retrieval_counts=counts,
            model_invocation_count=0,
        )

    try:
        authority_rows = runtime.authority_store.require_chunks(
            [str(item["chunk_id"]) for item in sources]
        )
        hydrated = hydrate_sqlite_authority_sources(
            sources, authority_rows
        )
        extractive = build_authoritative_extractive_fallback(question, hydrated)
    except Exception:
        hydrated = []
        extractive = {
            "answer": FAIL_CLOSED_ANSWER,
            "claim_map": {"claims": []},
            "recovered": False,
            "used_chunk_ids": [],
            "policy_version": EXTRACTIVE_POLICY_VERSION,
        }
        warnings.append("authoritative_extractive_pipeline_error")

    if extractive["recovered"]:
        finalization = _finalize_deterministic(
            str(extractive["answer"]), extractive["claim_map"], hydrated
        )
        if finalization["allowed"]:
            return _response(
                trace_id=trace_id,
                question=question,
                request_contract=request_contract,
                route="authoritative_extractive",
                answer=str(finalization["answer"]),
                degraded=False,
                degraded_reasons=warnings,
                sources=hydrated,
                accepted_ids=set(finalization["telemetry"]["accepted_evidence_ids"]),
                graph_result=graph,
                claim_evidence=finalization["telemetry"],
                retrieval_counts=counts,
                model_invocation_count=0,
            )

    try:
        outcome = runtime.coordinate_answer(
            request_id=trace_id, question=question, sources=sources
        )
        parsed = parse_claim_map(outcome.answer)
        finalization = finalize_claim_evidence(
            parsed["answer"],
            parsed["claim_map"],
            internal_sources=sources,
            parse_error=parsed["error"],
            trusted_deterministic=False,
        )
        model_calls = sum(1 for entry in outcome.ledger if entry.disclosed)
        if finalization["allowed"]:
            return _response(
                trace_id=trace_id,
                question=question,
                request_contract=request_contract,
                route="server_model",
                answer=str(finalization["answer"]),
                degraded=False,
                degraded_reasons=warnings,
                sources=sources,
                accepted_ids=set(finalization["telemetry"]["accepted_evidence_ids"]),
                graph_result=graph,
                claim_evidence=finalization["telemetry"],
                retrieval_counts=counts,
                model_invocation_count=model_calls,
            )
        warnings.append("claim_evidence_finalizer_blocked")
    except CloudRuntimeDependencyError:
        warnings.append("server_answer_coordinator_unavailable")
    except Exception:
        warnings.append("server_answer_pipeline_error")

    return _response(
        trace_id=trace_id,
        question=question,
        request_contract=request_contract,
        route="degraded",
        answer=DEGRADED_NOTICE,
        degraded=True,
        degraded_reasons=warnings or ["insufficient_authoritative_evidence"],
        sources=sources,
        graph_result=graph,
        retrieval_counts=counts,
    )


def create_app(
    runtime_loader: RuntimeLoader,
    *,
    preflight: bool = False,
    verified_identity_loader: VerifiedIdentityLoader | None = None,
) -> Flask:
    """Create the public service around an explicit runtime loader."""

    if not callable(runtime_loader):
        raise TypeError("runtime_loader must be callable")

    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BODY_BYTES
    load_runtime = runtime_loader
    load_verified_identity = (
        verified_identity_loader or verified_identity_from_wsgi_environ
    )
    runtime_lock = threading.Lock()
    runtime_holder: dict[str, CloudRuntimeResources] = {}
    if preflight:
        runtime_holder["value"] = load_runtime()
    allowed_hosts = {
        item.strip().lower()
        for item in os.getenv(
            "KG_PUBLIC_ALLOWED_HOSTS",
            "localhost:5001,127.0.0.1:5001,localhost,127.0.0.1",
        ).split(",")
        if item.strip()
    }

    def runtime() -> CloudRuntimeResources:
        with runtime_lock:
            if "value" not in runtime_holder:
                runtime_holder["value"] = load_runtime()
            return runtime_holder["value"]

    def close_runtime() -> None:
        with runtime_lock:
            cached = runtime_holder.pop("value", None)
        if cached is not None:
            cached.close()

    app.extensions["cloud_runtime_close"] = close_runtime
    app.extensions["public_entrypoint_contract"] = {
        "schema_version": PUBLIC_ENTRYPOINT_SCHEMA_VERSION,
        "entrypoint_id": PUBLIC_ENTRYPOINT_ID,
        "process_role": PUBLIC_AUDIENCE,
        "network_zone": "public-app",
        "routes": (PUBLIC_API_PATH,),
        "tool_registry": public_tool_registry(),
        "ops_agent_discoverable": False,
        "ops_routes": (),
    }
    atexit.register(close_runtime)

    @app.errorhandler(RequestEntityTooLarge)
    def request_body_too_large(_error):
        return jsonify(
            {
                "error": "request_body_too_large",
                "request_rejected": True,
                "stats": {"trace_id": str(uuid.uuid4())},
            }
        ), 413

    @app.before_request
    def guard_public_surface():
        if request.path != PUBLIC_API_PATH:
            return jsonify({"error": "not_found"}), 404
        if str(request.host or "").lower() not in allowed_hosts:
            return jsonify({"error": "forbidden_host"}), 403
        try:
            identity = load_verified_identity(request.environ)
            authorize_public_ask(identity, request.path)
        except Exception:
            return jsonify(
                {"error": "access_denied", "request_rejected": True}
            ), 403
        return None

    @app.post(PUBLIC_API_PATH)
    def ask():
        trace_id = str(uuid.uuid4())
        if request.headers.get(ANSWER_CONTRACT_HEADER, "") != ANSWER_CONTRACT_VERSION:
            return jsonify(
                {
                    "error": "answer_contract_mismatch",
                    "request_rejected": True,
                    "stats": {"trace_id": trace_id},
                }
            ), 412
        if not request.is_json:
            return jsonify(
                {
                    "error": "invalid_content_type",
                    "request_rejected": True,
                    "stats": {"trace_id": trace_id},
                }
            ), 415
        try:
            if (
                request.content_length is not None
                and request.content_length > MAX_REQUEST_BODY_BYTES
            ):
                raise RequestEntityTooLarge()
            raw_body = request.stream.read(MAX_REQUEST_BODY_BYTES + 1)
            if len(raw_body) > MAX_REQUEST_BODY_BYTES:
                raise RequestEntityTooLarge()

            def reject_duplicate_keys(pairs):
                parsed = {}
                for key, value in pairs:
                    if key in parsed:
                        raise ValueError("duplicate JSON key")
                    parsed[key] = value
                return parsed

            def reject_non_finite(_value):
                raise ValueError("non-finite JSON number")

            payload = json.loads(
                raw_body.decode("utf-8"),
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=reject_non_finite,
            )
        except RequestEntityTooLarge:
            raise
        except (BadRequest, UnicodeDecodeError, ValueError):
            return jsonify(
                {
                    "error": "invalid_json",
                    "request_rejected": True,
                    "stats": {"trace_id": trace_id},
                }
            ), 400
        try:
            envelope = parse_request_envelope(method="POST", json_body=payload)
        except RequestEnvelopeError as exc:
            return jsonify(
                {
                    "error": exc.code,
                    "request_rejected": True,
                    "stats": {"trace_id": trace_id},
                }
            ), 400

        configured = {
            item.strip().lower()
            for item in os.getenv(
                "KG_PUBLIC_RETRIEVAL_SOURCES",
                ",".join(sorted(SUPPORTED_RETRIEVAL_SOURCES)),
            ).split(",")
            if item.strip().lower() in SUPPORTED_RETRIEVAL_SOURCES
        }
        effective = {
            item
            for item in ALLOWED_SOURCES
            if item in envelope.allowed_sources and item in configured
        }
        request_contract = envelope.to_dict(include_query=False)
        request_contract["requested_sources"] = list(envelope.allowed_sources)
        request_contract["allowed_sources"] = [
            item for item in ALLOWED_SOURCES if item in effective
        ]
        request_contract["source_policy_sha256"] = hashlib.sha256(
            (",".join(sorted(effective)) + "|" + RUNTIME_SOURCE_POLICY_VERSION).encode(
                "utf-8"
            )
        ).hexdigest()
        if not effective:
            return jsonify(
                {
                    "error": "source_policy_empty",
                    "request_rejected": True,
                    "stats": {"trace_id": trace_id},
                }
            ), 403
        try:
            result = _answer_request(
                runtime(),
                trace_id=trace_id,
                question=envelope.user_query,
                request_contract=request_contract,
                allowed_sources=effective,
            )
        except Exception:
            result = _response(
                trace_id=trace_id,
                question=envelope.user_query,
                request_contract=request_contract,
                route="unavailable",
                answer=DEGRADED_NOTICE,
                degraded=True,
                degraded_reasons=["runtime_unavailable"],
            )
            return jsonify(result), 503
        return jsonify(result), 200

    return app


def create_production_app(
    runtime_loader: RuntimeLoader | None = None,
) -> Flask:
    """Bind data, approval, secrets, and provider transports before serving."""

    load_runtime = runtime_loader or load_provider_bound_runtime_from_environment
    return create_app(load_runtime, preflight=True)


def _startup_error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, ProviderBootstrapError):
        return error.to_dict()
    return {
        "schema_version": "kg-public-startup-error-v1",
        "error": "runtime_preflight_failed",
        "provider_runtime_ready": False,
    }


def _emit_startup_error(error: Exception) -> None:
    print(
        json.dumps(
            _startup_error_payload(error),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
        flush=True,
    )


def create_wsgi_app() -> Flask:
    """WSGI factory that terminates before import completes on preflight failure."""

    try:
        return create_production_app()
    except Exception as error:
        _emit_startup_error(error)
        raise SystemExit(EX_CONFIG) from None


def _bind_address() -> tuple[str, int]:
    bind_host = os.getenv("KG_PUBLIC_BIND_HOST", "127.0.0.1")
    raw_port = os.getenv("KG_PUBLIC_BIND_PORT", "5001")
    if (
        not bind_host
        or bind_host != bind_host.strip()
        or any(character in bind_host for character in "\r\n\x00")
    ):
        raise ValueError("invalid public bind host")
    try:
        bind_port = int(raw_port)
    except (TypeError, ValueError):
        raise ValueError("invalid public bind port") from None
    if not 1 <= bind_port <= 65535 or str(bind_port) != raw_port:
        raise ValueError("invalid public bind port")
    return bind_host, bind_port


def main() -> int:
    try:
        bind_host, bind_port = _bind_address()
        app = create_production_app()
    except Exception as error:
        _emit_startup_error(error)
        return EX_CONFIG
    app.run(host=bind_host, port=bind_port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
