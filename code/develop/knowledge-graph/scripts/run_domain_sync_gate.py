#!/usr/bin/env python3
"""Run the full domain sync gate as one repeatable command.

Pipeline:
1. Refresh ingest_manifest.json.
2. Run sync readiness.
3. Build domain sync packages.
4. Replay packages into isolated local replay directories.
5. Import replay Cypher into isolated Neo4j and run the 15-question eval.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from neo4j import GraphDatabase, Query

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ACCEPTANCE = BASE_DIR / "eval" / "domain_sync_acceptance_questions.json"
DEFAULT_PACKAGE_DIR = BASE_DIR / "sync_packages"
DEFAULT_REPLAY_DIR = BASE_DIR / "remote_replay"
DEFAULT_SUMMARY = DEFAULT_REPLAY_DIR / "domain_sync_gate_report.json"
DEFAULT_NEO4J_COMPOSE = DEFAULT_REPLAY_DIR / "docker-compose.neo4j.yml"
DEFAULT_REPLAY_HARNESS = DEFAULT_REPLAY_DIR / "replay_retrieval_harness.py"
DEFAULT_NEO4J_URI = "bolt://localhost:7688"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings"
DEFAULT_EMBED_MODEL = "bge-m3"
DOMAINS = ("regulation", "question_bank", "textbook")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def batched(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def command_name(argv: list[str]) -> str:
    return " ".join(argv)


def run_command(argv: list[str], log_dir: Path, step: str, check: bool = True) -> dict[str, Any]:
    started = utc_now()
    proc = subprocess.run(argv, cwd=BASE_DIR, text=True, capture_output=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_step = step.replace("/", "_")
    (log_dir / f"{safe_step}.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (log_dir / f"{safe_step}.stderr.log").write_text(proc.stderr, encoding="utf-8")
    result = {
        "step": step,
        "command": command_name(argv),
        "started_at": started,
        "finished_at": utc_now(),
        "returncode": proc.returncode,
        "stdout_log": str(log_dir / f"{safe_step}.stdout.log"),
        "stderr_log": str(log_dir / f"{safe_step}.stderr.log"),
    }
    try:
        result["json"] = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result["stdout_preview"] = proc.stdout[-2000:]
    if check and proc.returncode != 0:
        raise StepFailed(result)
    return result


class StepFailed(RuntimeError):
    def __init__(self, result: dict[str, Any]):
        super().__init__(f"{result['step']} failed with exit code {result['returncode']}")
        self.result = result


def domain_flags(domains: list[str]) -> list[str]:
    flags: list[str] = []
    for domain in domains:
        flags.extend(["--domain", domain])
    return flags


def compose_command(compose_file: Path, extra: list[str]) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), *extra]


def ensure_neo4j_compose(replay_dir: Path) -> Path:
    compose_file = replay_dir / "docker-compose.neo4j.yml"
    if compose_file.exists():
        return compose_file
    if not DEFAULT_NEO4J_COMPOSE.exists():
        raise FileNotFoundError(f"missing Neo4j compose template: {DEFAULT_NEO4J_COMPOSE}")
    replay_dir.mkdir(parents=True, exist_ok=True)
    text = DEFAULT_NEO4J_COMPOSE.read_text(encoding="utf-8")
    # Keep temporary gate runs independent from the default remote_replay container.
    lines = [line for line in text.splitlines() if not line.strip().startswith("container_name:")]
    compose_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return compose_file


def ensure_replay_harness(replay_dir: Path) -> Path:
    harness_path = replay_dir / "replay_retrieval_harness.py"
    if harness_path.exists():
        return harness_path
    if not DEFAULT_REPLAY_HARNESS.exists():
        raise FileNotFoundError(f"missing replay harness template: {DEFAULT_REPLAY_HARNESS}")
    replay_dir.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(DEFAULT_REPLAY_HARNESS.read_text(encoding="utf-8"), encoding="utf-8")
    return harness_path


def wait_for_neo4j(uri: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        driver = GraphDatabase.driver(uri, auth=None, connection_timeout=2)
        try:
            driver.verify_connectivity()
            return
        except Exception as exc:  # pragma: no cover - depends on Docker startup timing.
            last_error = exc
            time.sleep(2)
        finally:
            driver.close()
    raise RuntimeError(f"isolated Neo4j did not become ready at {uri}: {last_error}")


def iter_cypher_statements(path: Path) -> list[str]:
    statements = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.endswith(";"):
            line = line[:-1].strip()
        if line:
            statements.append(line)
    return statements


def isolated_neo4j_import(
    package_dir: Path,
    replay_dir: Path,
    domains: list[str],
    uri: str,
    start_container: bool,
    log_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    compose_file = ensure_neo4j_compose(replay_dir)
    if start_container:
        run_command(compose_command(compose_file, ["up", "-d"]), log_dir, "isolated_neo4j_start")
    wait_for_neo4j(uri, timeout_seconds)

    driver = GraphDatabase.driver(uri, auth=None, connection_timeout=5)
    domain_reports = []
    try:
        with driver.session() as session:
            session.run(Query("MATCH (n) DETACH DELETE n", timeout=30)).consume()
            for domain in domains:
                cypher_path = replay_dir / domain / "neo4j_import.cypher"
                statements = iter_cypher_statements(cypher_path)
                nodes = read_jsonl(package_dir / domain / "graph_nodes.jsonl")
                relationships = read_jsonl(package_dir / domain / "graph_relationships.jsonl")
                for chunk in batched(nodes, 1000):
                    session.run(
                        Query(
                            """
                            UNWIND $rows AS row
                            MERGE (n:ReplayNode {replay_key: row.key})
                            SET n += row.properties,
                                n.replay_key = row.key,
                                n.replay_labels = row.labels
                            """,
                            timeout=30,
                        ),
                        rows=chunk,
                    ).consume()
                for chunk in batched(relationships, 1000):
                    session.run(
                        Query(
                            """
                            UNWIND $rows AS row
                            MATCH (a:ReplayNode {replay_key: row.start_key})
                            MATCH (b:ReplayNode {replay_key: row.end_key})
                            MERGE (a)-[r:REPLAY_REL {
                                start_key: row.start_key,
                                end_key: row.end_key,
                                rel_type: row.type
                            }]->(b)
                            SET r += row.properties,
                                r.rel_type = row.type
                            """,
                            timeout=60,
                        ),
                        rows=chunk,
                    ).consume()
                domain_reports.append(
                    {
                        "domain": domain,
                        "mode": "batch_jsonl_import",
                        "cypher": str(cypher_path),
                        "nodes_file": str(package_dir / domain / "graph_nodes.jsonl"),
                        "relationships_file": str(package_dir / domain / "graph_relationships.jsonl"),
                        "statements": len(statements),
                        "nodes": len(nodes),
                        "relationships": len(relationships),
                    }
                )
            counts = session.run(
                Query(
                    """
                    MATCH (n:ReplayNode)
                    OPTIONAL MATCH ()-[r]->()
                    RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS relationships
                    """,
                    timeout=30,
                )
            ).single()
            per_domain = session.run(
                Query(
                    """
                    MATCH (n:ReplayNode)
                    RETURN coalesce(n.domain, "unknown") AS domain, count(n) AS nodes
                    ORDER BY domain
                    """,
                    timeout=30,
                )
            ).data()
    finally:
        driver.close()

    nodes = int(counts["nodes"] if counts else 0)
    relationships = int(counts["relationships"] if counts else 0)
    return {
        "ready": nodes > 0,
        "neo4j_uri": uri,
        "domains": domain_reports,
        "nodes": nodes,
        "relationships": relationships,
        "per_domain_nodes": per_domain,
    }


def load_harness(replay_dir: Path) -> Any:
    harness_path = ensure_replay_harness(replay_dir)
    spec = importlib.util.spec_from_file_location("replay_retrieval_harness", harness_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load replay harness from {harness_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_acceptance_eval(args: argparse.Namespace, domains: list[str]) -> dict[str, Any]:
    acceptance = read_json(Path(args.acceptance_file).expanduser())
    records = [record for record in acceptance.get("records", []) if record.get("domain") in domains]
    harness = load_harness(Path(args.replay_dir).expanduser())
    results = []
    for record in records:
        query_args = SimpleNamespace(
            domain=record["domain"],
            query=record["query"],
            base_dir=str(Path(args.replay_dir).expanduser()),
            neo4j_uri=args.neo4j_uri,
            ollama_url=args.ollama_url,
            embedding_model=args.embedding_model,
            bm25_limit=args.bm25_limit,
            dense_limit=args.dense_limit,
            kg_limit=args.kg_limit,
            limit=args.eval_limit,
            excerpt_chars=args.excerpt_chars,
        )
        result = harness.run(query_args)
        sources = result.get("sources") or []
        missing = result.get("missing_sqlite_chunk_ids") or []
        top_source = sources[0] if sources else {}
        top_text = top_source.get("text") or ""
        top_excerpt = top_source.get("excerpt") or ""
        top_haystack = f"{top_source.get('doc_name') or ''}\n{top_text}\n{top_excerpt}"
        failure_reasons = []
        if len(sources) < args.min_source_count:
            failure_reasons.append(f"source_count_lt_{args.min_source_count}")
        if missing:
            failure_reasons.append("missing_sqlite_chunk_ids")
        if result.get("degraded") and not args.allow_degraded_eval:
            failure_reasons.append("degraded")
        if any(source.get("text_source") != "replay_sqlite" for source in sources):
            failure_reasons.append("non_sqlite_source")

        expected_doc = record.get("expected_top_doc_contains")
        expected_doc_any = record.get("expected_top_doc_any") or []
        top_doc_name = str(top_source.get("doc_name") or "")
        if expected_doc and expected_doc not in top_doc_name:
            failure_reasons.append("top_doc_mismatch")
        if expected_doc_any and not any(doc in top_doc_name for doc in expected_doc_any):
            failure_reasons.append("top_doc_mismatch")

        expected_chunks = record.get("expected_top_chunk_ids") or []
        if expected_chunks and top_source.get("chunk_id") not in expected_chunks:
            failure_reasons.append("top_chunk_mismatch")

        expected_all = record.get("expected_top_text_all") or []
        missing_all = [term for term in expected_all if term not in top_haystack]
        if missing_all:
            failure_reasons.append("top_text_missing_all:" + ",".join(missing_all))

        expected_any = record.get("expected_top_text_any") or []
        if expected_any and not any(term in top_haystack for term in expected_any):
            failure_reasons.append("top_text_missing_any")

        passed = not failure_reasons
        results.append(
            {
                "id": record.get("id"),
                "domain": record["domain"],
                "query": record["query"],
                "passed": passed,
                "failure_reasons": failure_reasons,
                "expectation": {
                    "expected_top_doc_contains": expected_doc,
                    "expected_top_doc_any": expected_doc_any,
                    "expected_top_chunk_ids": expected_chunks,
                    "expected_top_text_all": expected_all,
                    "expected_top_text_any": expected_any,
                },
                "source_count": len(sources),
                "top_chunk_id": top_source.get("chunk_id"),
                "top_doc_name": top_source.get("doc_name"),
                "top_retrievers": top_source.get("retrievers"),
                "top_text_source": top_source.get("text_source"),
                "degraded": bool(result.get("degraded")),
                "degraded_reasons": result.get("degraded_reasons") or [],
                "retriever_counts": result.get("retriever_counts") or {},
                "missing_sqlite_chunk_ids": missing,
            }
        )
    by_domain: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_domain.setdefault(item["domain"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        if item["passed"]:
            bucket["passed"] += 1
    return {
        "ready": all(item["passed"] for item in results)
        and len(results) == (args.expected_eval_count or len(records)),
        "expected_count": args.expected_eval_count or len(records),
        "actual_count": len(results),
        "by_domain": by_domain,
        "records": results,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", action="append", choices=DOMAINS, help="Run only selected sync domain(s).")
    parser.add_argument("--manifest", default=str(BASE_DIR / "ingest_manifest.json"))
    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR))
    parser.add_argument("--replay-dir", default=str(DEFAULT_REPLAY_DIR))
    parser.add_argument("--acceptance-file", default=str(DEFAULT_ACCEPTANCE))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--dense-mode", choices=("full", "sample", "skip"), default="full")
    parser.add_argument("--dense-sample", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-chunk-coverage", type=float, default=0.70)
    parser.add_argument("--neo4j-uri", default=DEFAULT_NEO4J_URI)
    parser.add_argument("--neo4j-timeout", type=int, default=90)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--bm25-limit", type=int, default=20)
    parser.add_argument("--dense-limit", type=int, default=20)
    parser.add_argument("--kg-limit", type=int, default=20)
    parser.add_argument("--eval-limit", type=int, default=8)
    parser.add_argument("--excerpt-chars", type=int, default=420)
    parser.add_argument("--min-source-count", type=int, default=1)
    parser.add_argument("--expected-eval-count", type=int)
    parser.add_argument("--allow-degraded-eval", action="store_true")
    parser.add_argument("--skip-manifest-refresh", action="store_true")
    parser.add_argument("--skip-readiness", action="store_true")
    parser.add_argument("--skip-package-build", action="store_true")
    parser.add_argument("--skip-replay", action="store_true")
    parser.add_argument("--skip-neo4j-import", action="store_true")
    parser.add_argument("--skip-neo4j-start", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    domains = args.domain or list(DOMAINS)
    replay_dir = Path(args.replay_dir).expanduser()
    summary_path = Path(args.summary).expanduser()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = replay_dir / "gate_logs" / run_id
    report: dict[str, Any] = {
        "schema_version": "domain-sync-gate-report-v1",
        "run_id": run_id,
        "started_at": utc_now(),
        "base_dir": str(BASE_DIR),
        "domains": domains,
        "log_dir": str(log_dir),
        "ready": False,
        "steps": {},
    }

    try:
        if not args.skip_manifest_refresh:
            report["steps"]["manifest"] = run_command(
                [sys.executable, "scripts/build_ingest_manifest.py"],
                log_dir,
                "build_ingest_manifest",
            )
        if not args.skip_readiness:
            report["steps"]["readiness"] = run_command(
                [
                    sys.executable,
                    "scripts/check_sync_readiness.py",
                    "--manifest",
                    str(Path(args.manifest).expanduser()),
                    "--min-chunk-coverage",
                    str(args.min_chunk_coverage),
                    *domain_flags(domains),
                ],
                log_dir,
                "check_sync_readiness",
            )
        if not args.skip_package_build:
            report["steps"]["package"] = run_command(
                [
                    sys.executable,
                    "scripts/build_domain_sync_package.py",
                    "--manifest",
                    str(Path(args.manifest).expanduser()),
                    "--output-dir",
                    str(Path(args.package_dir).expanduser()),
                    *domain_flags(domains),
                ],
                log_dir,
                "build_domain_sync_package",
            )
        if not args.skip_replay:
            replay_cmd = [
                sys.executable,
                "scripts/replay_domain_sync_package.py",
                "--package-dir",
                str(Path(args.package_dir).expanduser()),
                "--output-dir",
                str(replay_dir),
                "--dense-mode",
                args.dense_mode,
                "--dense-sample",
                str(args.dense_sample),
                *domain_flags(domains),
            ]
            if args.force:
                replay_cmd.append("--force")
            report["steps"]["replay"] = run_command(replay_cmd, log_dir, "replay_domain_sync_package")
        if not args.skip_neo4j_import:
            report["steps"]["isolated_neo4j_import"] = isolated_neo4j_import(
                Path(args.package_dir).expanduser(),
                replay_dir,
                domains,
                args.neo4j_uri,
                not args.skip_neo4j_start,
                log_dir,
                args.neo4j_timeout,
            )
            if not report["steps"]["isolated_neo4j_import"]["ready"]:
                raise RuntimeError("isolated Neo4j import produced no ReplayNode records")
        if not args.skip_eval:
            report["steps"]["acceptance_eval"] = run_acceptance_eval(args, domains)
            if not report["steps"]["acceptance_eval"]["ready"]:
                raise RuntimeError("domain sync acceptance eval failed")
        report["ready"] = True
        return_code = 0
    except StepFailed as exc:
        report["failed_step"] = exc.result["step"]
        report["steps"][exc.result["step"]] = exc.result
        report["error"] = str(exc)
        return_code = exc.result["returncode"] or 1
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return_code = 1
    finally:
        report["finished_at"] = utc_now()
        write_json(summary_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
