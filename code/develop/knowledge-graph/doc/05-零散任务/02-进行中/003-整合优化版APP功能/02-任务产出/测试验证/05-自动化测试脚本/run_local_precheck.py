#!/usr/bin/env python3
"""Read-only local code precheck; never starts services or opens databases."""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[7]
SOURCE = ROOT / "-APP--main" / "-APP--main"
COMPILE_TARGETS = (
    "rag_store/request_envelope.py",
    "rag_store/retrieval_planner.py",
    "pipeline/answer_policy.py",
    "pipeline/server.py",
    "kg_query.py",
    "tests/test_ask_optimization.py",
)
REQUIRED_ROUTES = (
    "/api/ask",
    "/api/import/file",
    "/api/cypher",
    "/api/entity",
    "/api/edge",
    "/api/node",
    "/api/edge-3d",
)
REQUIRED_STATIC = (
    "3d.html",
    "three.min.js",
    "d3.v7.min.js",
    "vis-network.min.js",
    "3d-force-graph.min.js",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    subprocess.run(
        [sys.executable, "-m", "py_compile", *COMPILE_TARGETS],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=True,
    )

    server_path = ROOT / "pipeline" / "server.py"
    server = server_path.read_text(encoding="utf-8")
    ast.parse(server)
    require('@app.route("/api/ask", methods=["GET", "POST"])' in server, "GET/POST ask route missing")
    for route in REQUIRED_ROUTES:
        require(route in server, f"required route missing: {route}")
    require('app.run(host="0.0.0.0", port=5001' in server, "Windows/local startup contract missing")

    static_dir = ROOT / "pipeline" / "static"
    for name in REQUIRED_STATIC:
        require((static_dir / name).is_file(), f"required static asset missing: {name}")
    for name in ("index.html", "search.html"):
        require(
            sha256(static_dir / name) == sha256(SOURCE / "deploy" / "pipeline" / "static" / name),
            f"shared page hash mismatch: {name}",
        )
    require(not any(ROOT.rglob("uni_modules")), "uni_modules directory found; manual review required")

    task = ROOT / "doc" / "05-零散任务" / "02-进行中" / "003-整合优化版APP功能"
    for relative in (
        "00-任务计划.md",
        "01-验收标准.md",
        "02-任务产出/优化功能对比报告.md",
        "02-任务产出/整合实施记录.md",
        "02-任务产出/独立验收报告.md",
    ):
        require((task / relative).is_file(), f"formal artifact missing: {relative}")

    print("LOCAL_PRECHECK_OK: syntax, 10 unit tests, routes, static assets, hashes and artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

