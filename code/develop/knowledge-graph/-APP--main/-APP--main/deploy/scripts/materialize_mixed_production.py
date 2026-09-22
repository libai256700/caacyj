#!/usr/bin/env python3
"""Materialize a hash-bound mixed production runtime without printing secrets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


ANSWER_ENDPOINT = "https://api.deepseek.com/chat/completions"
ANSWER_MODEL = "deepseek-chat"
GRAPH_RELEASE_ID = "graph:revision-a-r9:3a08cf106d6410c8:dd519665c574a6d9"
VECTOR_RELEASE_ID = "r9-fb70102bbfb4007b4546cf305b237d376cbd077496a4fc72a344feff583d0063"


def canonical(value):
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    path.chmod(mode)
    return sha_file(path)


def systemd_value(value):
    if not isinstance(value, str) or any(character in value for character in "\r\n\x00"):
        raise ValueError("invalid environment value")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o444)


def neo4j_environment(container):
    result = subprocess.run(
        ["docker", "inspect", container],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    document = json.loads(result.stdout)
    values = {}
    for item in document[0]["Config"]["Env"]:
        if "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    auth = values.get("NEO4J_AUTH", "")
    if "/" not in auth:
        raise RuntimeError("neo4j_auth_unavailable")
    username, password = auth.split("/", 1)
    if not username or not password:
        raise RuntimeError("neo4j_auth_unavailable")
    return {
        "KG_NEO4J_URI": "bolt://127.0.0.1:7687",
        "KG_NEO4J_USERNAME": username,
        "KG_NEO4J_PASSWORD": password,
        "KG_NEO4J_DATABASE": "neo4j",
    }


def materialize(args):
    release = args.release.resolve(strict=True) / "server-runtime"
    source = args.source.resolve(strict=True)
    active = args.active.resolve()
    config_root = args.config_root.resolve()
    secret_root = args.secret_root.resolve()
    old_config = json.loads(args.old_config.read_text(encoding="utf-8"))
    answer_secret = old_config["models"]["flash"]["api_key"]
    if not isinstance(answer_secret, str) or len(answer_secret) < 16:
        raise RuntimeError("legacy_answer_secret_invalid")
    old_server = args.old_server.read_text(encoding="utf-8")
    if ANSWER_ENDPOINT not in old_server or f'"model": "{ANSWER_MODEL}"' not in old_server:
        raise RuntimeError("legacy_answer_contract_drift")

    if active.exists():
        raise RuntimeError("active_root_already_exists")
    paths = {
        "authority_manifest": release / "data/authority/authority-manifest.json",
        "authority_db": release / "data/authority/rag_chunks.db",
        "bm25_manifest": release / "data/derived/bm25-manifest.json",
        "bm25_db": release / "data/derived/bm25.sqlite3",
        "graph_manifest": release / "data/derived/graph/graph-manifest.json",
        "graph_data": release / "data/derived/graph/scoped-graph.jsonl",
        "timeline": release / "code/deploy/rag_store/regulation_timeline.json",
        "superseded": release / "code/deploy/rag_store/superseded_passages.json",
        "vector_manifest": release / f"data/derived/vector/local-vector/candidate/{VECTOR_RELEASE_ID}/local_vector_manifest.json",
        "chunk_index": release / f"data/derived/vector/local-vector/candidate/{VECTOR_RELEASE_ID}/chunk-index/index.usearch",
        "entity_index": release / f"data/derived/vector/local-vector/candidate/{VECTOR_RELEASE_ID}/entity-index/index.usearch",
    }
    targets = {
        "authority_manifest": active / "authority/authority-manifest.json",
        "authority_db": active / "authority/rag_chunks.db",
        "bm25_manifest": active / "bm25/bm25-manifest.json",
        "bm25_db": active / "bm25/bm25.sqlite3",
        "graph_manifest": active / "graph/graph-manifest.json",
        "graph_data": active / "graph/scoped-graph.jsonl",
        "timeline": active / "governance/regulation_timeline.json",
        "superseded": active / "governance/superseded_passages.json",
        "vector_manifest": active / f"local-vector/active/{VECTOR_RELEASE_ID}/local_vector_manifest.json",
        "chunk_index": active / f"local-vector/active/{VECTOR_RELEASE_ID}/chunk-index/index.usearch",
        "entity_index": active / f"local-vector/active/{VECTOR_RELEASE_ID}/entity-index/index.usearch",
    }
    for name, src in paths.items():
        copy_file(src, targets[name])

    vector = json.loads(targets["vector_manifest"].read_text(encoding="utf-8"))
    identity = vector["identity"]
    embedding_manifest = json.loads((release / "embedding-manifest.json").read_text())
    graph_manifest = json.loads(targets["graph_manifest"].read_text())
    if graph_manifest["release_id"] != GRAPH_RELEASE_ID:
        raise RuntimeError("graph_release_drift")

    request_schema = {
        "schema_version": "kg-server-answer-request-v1",
        "disclosed_fields": ["question", "selected_evidence"],
    }
    response_schema = {
        "provider_shape": "openai-chat-completions-v1",
        "answer_pointer": "/choices/0/message/content",
    }
    request_schema_sha = write_json(config_root / "answer-request-schema.json", request_schema)
    response_schema_sha = write_json(config_root / "answer-response-schema.json", response_schema)
    limits = {
        "timeout_seconds": 60.0,
        "max_input_units": 200000,
        "max_output_units": 4096,
        "max_cost_microunits": 1,
        "max_request_bytes": 1048576,
        "max_response_bytes": 1048576,
    }
    channel_identity = {
        "api_version": "openai-chat-completions-v1",
        "base_url": ANSWER_ENDPOINT,
        "channel_id": "legacy-production-answer",
        "model": ANSWER_MODEL,
        "model_version": "production-current-20260905",
        "max_cost_microunits": limits["max_cost_microunits"],
        "max_input_units": limits["max_input_units"],
        "max_output_units": limits["max_output_units"],
        "max_request_bytes": limits["max_request_bytes"],
        "max_response_bytes": limits["max_response_bytes"],
        "local_meter_execution_contract": "trusted-local-terminating-v1",
        "provider": "deepseek-production",
        "region": "china",
        "timeout_seconds": limits["timeout_seconds"],
        "transport_control_version": "bounded-external-process-or-sealed-offline-fake-cooperative-v3",
    }
    channel_identity_sha = sha_bytes(canonical(channel_identity))
    wire_base = {
        "schema_version": "kg-provider-answer-wire-v1",
        "request_schema_sha256": request_schema_sha,
        "response_schema_sha256": response_schema_sha,
        "body_template": {
            "model": {"$ref": "identity.model"},
            "messages": [
                {"role": "system", "content": "Answer only from the evidence included in the user message and preserve the required final claim map."},
                {"role": "user", "content": {"$ref": "request.question"}},
            ],
            "max_tokens": {"$ref": "request.max_output_units"},
            "temperature": 0.1,
        },
        "answer_pointer": "/choices/0/message/content",
    }
    wire = {**wire_base, "wire_contract_sha256": sha_bytes(canonical(wire_base))}
    channel = {
        "channel_id": channel_identity["channel_id"],
        "approval_role_id": "legacy-production-answer-role",
        "provider": channel_identity["provider"],
        "endpoint": ANSWER_ENDPOINT,
        "region": channel_identity["region"],
        "model": ANSWER_MODEL,
        "model_version": channel_identity["model_version"],
        "api_version": channel_identity["api_version"],
        "identity_sha256": channel_identity_sha,
        "secret_ref": "secretref:KG_SERVER_ANSWER_API_KEY",
        "auth": {"header_name": "Authorization", "prefix": "Bearer "},
        "limits": limits,
        "meters": {
            "input_meter_id": "unicode_codepoints-v1",
            "output_meter_id": "unicode_codepoints-v1",
            "cost_meter_id": "maximum_request_exposure-v1",
        },
        "wire": wire,
    }
    server_answer = {
        "strategy": "single",
        "winner_policy": "ordered_success",
        "total_budget_seconds": 60.0,
        "total_cost_budget_microunits": 1,
        "circuit_breaker_failure_threshold": 2,
        "circuit_breaker_cooldown_seconds": 30.0,
        "channels": [channel],
    }
    policy = {
        "batch_size": 32,
        "max_input_units": 8192,
        "timeout_seconds": 120.0,
        "max_retries": 0,
        "max_requests_per_operation": 10000,
        "max_cost_microunits_per_request": 0,
        "total_cost_budget_microunits": 0,
        "max_request_bytes": 8388608,
        "max_response_bytes": 8388608,
    }
    sys_path = [str(source), str(source / "deploy")]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys_path))
    policy_sha = subprocess.run(
        [args.python, "-c", "from rag_store.runtime_query_embedding import QueryEmbeddingPolicy as P;import json,sys;print(P(**json.loads(sys.stdin.read())).sha256)"],
        input=json.dumps(policy), text=True, check=True, stdout=subprocess.PIPE, env=env,
    ).stdout.strip()
    embedding = {
        "provider": "ollama-local",
        "base_url": "http://127.0.0.1:11434",
        "model": "bge-m3:latest",
        "model_digest": embedding_manifest["model_digest"],
        "dimension": 1024,
        "identity_sha256": embedding_manifest["embedding_identity_sha256"],
        "policy": policy,
        "policy_sha256": policy_sha,
    }
    contract_sha = sha_bytes(canonical({"server_answer": server_answer, "embedding": embedding}))
    role = {
        "role_id": channel["approval_role_id"],
        "role_kind": "server_answer",
        "provider": channel["provider"],
        "endpoint": channel["endpoint"],
        "model": channel["model"],
        "identity_sha256": channel["identity_sha256"],
    }
    stop_b = {
        "schema_version": "kg-mixed-stop-b-request-v1",
        "status": "stop_b_user_approved",
        "request_id": "TASK-027-production-20260905-r2",
        "approved_by": "云技",
        "regional_policy": "china_only",
        "data_classes": ["user_query", "selected_knowledge_evidence"],
        "role": role,
    }
    stop_b_sha = write_json(config_root / "stop-b-request.json", stop_b)
    materials = {
        "schema_version": "kg-mixed-provider-contract-materials-v1",
        "stop_b_request_sha256": stop_b_sha,
        "provider_contract_sha256": contract_sha,
        "role": {
            **role,
            "wire_contract_sha256": wire["wire_contract_sha256"],
            "request_schema_sha256": request_schema_sha,
            "response_schema_sha256": response_schema_sha,
        },
    }
    materials_sha = write_json(config_root / "contract-materials.json", materials)
    egress = {
        "schema_version": "kg-mixed-provider-egress-policy-v1",
        "stop_b_request_sha256": stop_b_sha,
        "provider_contract_sha256": contract_sha,
        "allowed_endpoints": [ANSWER_ENDPOINT],
        "role": role,
    }
    egress_sha = write_json(config_root / "egress-policy.json", egress)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    receipt = {
        "schema_version": "kg-mixed-stop-b-approval-v1",
        "status": "stop_b_production_provider_approved",
        "approval_id": "TASK-027-production-user-approved",
        "approved_by": "云技",
        "approved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approval_scope": "one_https_server_answer_role",
        "stop_b_request_sha256": stop_b_sha,
        "contract_materials_sha256": materials_sha,
        "egress_policy_sha256": egress_sha,
        "provider_contract_sha256": contract_sha,
    }
    receipt_sha = write_json(config_root / "approval-receipt.json", receipt)
    mixed = {
        "schema_version": "kg-mixed-provider-runtime-config-v1",
        "network_mode": "https-answer-loopback-embedding",
        "approval_binding": {
            "receipt_path": str(config_root / "approval-receipt.json"),
            "receipt_sha256": receipt_sha,
            "stop_b_request_path": str(config_root / "stop-b-request.json"),
            "stop_b_request_sha256": stop_b_sha,
            "contract_materials_path": str(config_root / "contract-materials.json"),
            "contract_materials_sha256": materials_sha,
            "egress_policy_path": str(config_root / "egress-policy.json"),
            "egress_policy_sha256": egress_sha,
        },
        "server_answer": server_answer,
        "embedding": embedding,
    }
    mixed_sha = write_json(config_root / "mixed-provider-runtime.json", mixed)

    public_secret = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    public_identity = {
        "schema_version": "kg-public-identity-gateway-config-v1",
        "verifier": {
            "kind": "hs256-jwt-gateway-v1",
            "algorithm": "HS256",
            "issuer": "urn:knowledge-qa:legacy-loopback-gateway",
            "audience": "public-app-agent",
            "secret_ref": {"value": "secretref:KG_PUBLIC_IDENTITY_HS256_SECRET", "encoding": "base64url"},
            "token_source": {"wsgi_environ_key": "HTTP_AUTHORIZATION", "scheme": "Bearer"},
            "time_policy": {"leeway_seconds": 5, "max_lifetime_seconds": 300},
            "claim_mapping": {"subject": "sub", "roles": "roles", "authn_methods": "amr"},
            "identity_contract": {"service_account": "public-app-agent", "token_kind": "public-app-access", "network_zone": "public-app", "required_roles": ["app-user"]},
        },
    }
    public_sha = write_json(config_root / "public-identity.json", public_identity)
    runtime_config = {
        "schema_version": "kg-cloud-runtime-config-v1",
        "runtime_release_id": "knowledge-qa-20260905-r2",
        "active_root": str(active),
        "provider_runtime": {"config_sha256": mixed_sha},
        "authority": {
            "manifest_path": "authority/authority-manifest.json",
            "manifest_sha256": sha_file(targets["authority_manifest"]),
            "data_path": "authority/rag_chunks.db",
            "data_sha256": sha_file(targets["authority_db"]),
        },
        "bm25": {
            "manifest_path": "bm25/bm25-manifest.json",
            "manifest_sha256": sha_file(targets["bm25_manifest"]),
            "data_path": "bm25/bm25.sqlite3",
            "data_sha256": sha_file(targets["bm25_db"]),
        },
        "graph": {
            "manifest_path": "graph/graph-manifest.json",
            "manifest_sha256": sha_file(targets["graph_manifest"]),
            "release_id": GRAPH_RELEASE_ID,
            "driver": "neo4j",
            "driver_version": "6.2.0",
            "uri_env": "KG_NEO4J_URI",
            "username_env": "KG_NEO4J_USERNAME",
            "password_env": "KG_NEO4J_PASSWORD",
            "database_env": "KG_NEO4J_DATABASE",
            "query_timeout_seconds": 5.0,
            "max_records": 1000,
        },
        "regulation_governance": {
            "timeline_path": "governance/regulation_timeline.json",
            "timeline_sha256": sha_file(targets["timeline"]),
            "superseded_path": "governance/superseded_passages.json",
            "superseded_sha256": sha_file(targets["superseded"]),
        },
        "embedding": {"identity_sha256": embedding["identity_sha256"], "policy_sha256": policy_sha},
        "local_vector": {
            "data_root": "local-vector",
            "data_release_id": VECTOR_RELEASE_ID,
            "manifest_sha256": sha_file(targets["vector_manifest"]),
            "authority_manifest_sha256": identity["authority_manifest_sha256"],
            "chunking_identity_sha256": identity["chunking_identity_sha256"],
            "embedding_identity_sha256": identity["embedding_identity_sha256"],
            "dimension": identity["dimension"],
            "metric": identity["metric"],
            "schema_version": identity["schema_version"],
            "chunk_index_name": identity["index_names"]["chunk"],
            "entity_index_name": identity["index_names"]["entity"],
            "top_k_max": identity["top_k_max"],
            "max_vectors_per_index": identity["max_vectors_per_index"],
            "metadata_allowlist": identity["metadata_allowlist"],
            "engine": identity["engine"],
            "engine_version": identity["engine_version"],
        },
        "server_answer": {
            "strategy": server_answer["strategy"],
            "winner_policy": server_answer["winner_policy"],
            "ordered_channels": [{"channel_id": channel["channel_id"], "identity_sha256": channel["identity_sha256"]}],
            "total_budget_seconds": server_answer["total_budget_seconds"],
            "total_cost_budget_microunits": server_answer["total_cost_budget_microunits"],
            "circuit_breaker_failure_threshold": server_answer["circuit_breaker_failure_threshold"],
            "circuit_breaker_cooldown_seconds": server_answer["circuit_breaker_cooldown_seconds"],
        },
    }
    runtime_sha = write_json(config_root / "cloud-runtime.json", runtime_config)
    secret_values = {
        "KG_SERVER_ANSWER_API_KEY": answer_secret,
        "KG_PUBLIC_IDENTITY_HS256_SECRET": public_secret,
        **neo4j_environment(args.neo4j_container),
    }
    secret_root.mkdir(parents=True, exist_ok=True)
    secret_path = secret_root / "runtime.env"
    secret_path.write_text("".join(f"{key}={systemd_value(value)}\n" for key, value in secret_values.items()), encoding="utf-8")
    secret_path.chmod(0o600)
    service_values = {
        "PYTHONPATH": f"{source}:{source / 'deploy'}",
        "KG_CLOUD_RUNTIME_CONFIG": str(config_root / "cloud-runtime.json"),
        "KG_CLOUD_RUNTIME_CONFIG_SHA256": runtime_sha,
        "KG_MIXED_PROVIDER_RUNTIME_CONFIG": str(config_root / "mixed-provider-runtime.json"),
        "KG_MIXED_PROVIDER_RUNTIME_CONFIG_SHA256": mixed_sha,
        "KG_MIXED_PROVIDER_NETWORK_MODE": "https-answer-loopback-embedding",
        "KG_MIXED_STOP_B_APPROVAL_SHA256": receipt_sha,
        "KG_PUBLIC_IDENTITY_CONFIG": str(config_root / "public-identity.json"),
        "KG_PUBLIC_IDENTITY_CONFIG_SHA256": public_sha,
        "KG_PUBLIC_ALLOWED_HOSTS": "127.0.0.1:5001,127.0.0.1:15001,localhost:5001,localhost:15001",
        "KG_PUBLIC_RETRIEVAL_SOURCES": "sqlite_exact,bm25,dense,neo4j",
    }
    service_path = config_root / "service.env"
    service_path.write_text("".join(f"{key}={systemd_value(value)}\n" for key, value in service_values.items()), encoding="utf-8")
    service_path.chmod(0o600)
    for directory in sorted((item for item in active.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        directory.chmod(0o555)
    active.chmod(0o555)
    output = {
        "active_root": str(active),
        "config_root": str(config_root),
        "secret_path": str(secret_path),
        "cloud_runtime_sha256": runtime_sha,
        "mixed_provider_sha256": mixed_sha,
        "approval_receipt_sha256": receipt_sha,
        "public_identity_sha256": public_sha,
    }
    print(json.dumps(output, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--active", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--secret-root", type=Path, required=True)
    parser.add_argument("--old-config", type=Path, required=True)
    parser.add_argument("--old-server", type=Path, required=True)
    parser.add_argument("--neo4j-container", required=True)
    parser.add_argument("--python", required=True)
    materialize(parser.parse_args())


if __name__ == "__main__":
    main()
