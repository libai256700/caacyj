#!/usr/bin/env python3
"""Append-only query trace logging for /api/ask diagnostics."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


class QueryTraceLogger:
    """Small JSONL logger for retrieval diagnostics.

    The trace intentionally stores routing and retrieval metadata, not provider
    credentials or full prompts. Disable with RAG_TRACE_ENABLED=0.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.enabled = os.environ.get("RAG_TRACE_ENABLED", "1").lower() not in {"0", "false", "no"}
        self._lock = threading.RLock()

    def record(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        item = dict(payload)
        item.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        if "query" in item and isinstance(item["query"], str):
            item["query"] = item["query"][:500]
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


def source_name(source: dict[str, Any]) -> str:
    return str(
        source.get("doc_name")
        or source.get("doc")
        or source.get("source_doc")
        or source.get("file")
        or ""
    )
