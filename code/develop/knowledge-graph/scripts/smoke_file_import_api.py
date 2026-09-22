#!/usr/bin/env python3
"""Smoke test for the file import HTTP API."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "pipeline" / "server.py"


def _decorated_routes(func: ast.FunctionDef) -> list[str]:
    routes = []
    for decorator in func.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        if not call:
            continue
        attr = call.func
        if not isinstance(attr, ast.Attribute) or attr.attr != "route":
            continue
        if call.args and isinstance(call.args[0], ast.Constant):
            routes.append(str(call.args[0].value))
    return routes


def static_smoke() -> int:
    tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    route_map = {
        route: name
        for name, func in functions.items()
        for route in _decorated_routes(func)
    }

    required_routes = {
        "/api/health": "health",
        "/api/ask": "ask",
        "/api/files": "import_file",
        "/api/import/file": "import_file",
    }
    missing = [route for route, func in required_routes.items() if route_map.get(route) != func]
    required_functions = [
        "_safe_import_path",
        "_save_uploaded_import_file",
        "import_file_to_knowledge_graph",
        "import_file",
    ]
    missing_functions = [name for name in required_functions if name not in functions]

    source = SERVER_PATH.read_text(encoding="utf-8")
    calls_real_extract = "from pipeline.extract_one import _DEFAULT_MODEL_KEY, extract" in source
    has_extract_call = "result = extract(" in source
    has_sync_contract = '"mode": "sync"' in source and '"result": result if ok else None' in source

    ok = not missing and not missing_functions and calls_real_extract and has_extract_call and has_sync_contract
    print(json.dumps({
        "ok": ok,
        "mode": "static",
        "routes": sorted(required_routes),
        "missing_routes": missing,
        "missing_functions": missing_functions,
        "calls_real_extract": calls_real_extract and has_extract_call,
        "contract": {"ok": True, "job": {"mode": "sync", "status": "imported"}},
    }, ensure_ascii=False))
    return 0 if ok else 1


def live_smoke() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from pipeline import server

    calls = []

    def fake_import(file_path, **kwargs):
        calls.append({"file_path": str(file_path), **kwargs})
        return {
            "ok": True,
            "status": "imported",
            "doc_name": kwargs.get("doc_name") or Path(file_path).stem,
            "filepath": str(file_path),
            "entities": 1,
            "relations": 0,
        }

    server.import_file_to_knowledge_graph = fake_import
    client = server.app.test_client()

    missing_path = client.post("/api/files", json={})
    if missing_path.status_code != 400 or missing_path.get_json().get("ok") is not False:
        print("missing file_path validation failed")
        return 1

    smoke_dir = ROOT / "rag_docs" / "_api_uploads"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = smoke_dir / "smoke_file_import_api.txt"
    tmp_path.write_text("smoke import content", encoding="utf-8")
    try:
        response = client.post(
            "/api/files",
            json={
                "file_path": str(tmp_path),
                "doc_name": "smoke-doc",
                "folder_hint": "default",
                "model_key": "gpt5",
            },
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    data = response.get_json()
    ok = response.status_code == 201 and data.get("ok") and calls and calls[0]["doc_name"] == "smoke-doc"
    print(json.dumps({
        "ok": bool(ok),
        "mode": "live",
        "status_code": response.status_code,
        "response": data,
        "service_calls": calls,
    }, ensure_ascii=False))
    return 0 if ok else 1


def main() -> int:
    if "--live" in sys.argv[1:]:
        return live_smoke()
    return static_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
