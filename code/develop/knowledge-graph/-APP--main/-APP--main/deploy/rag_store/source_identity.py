#!/usr/bin/env python3
"""Stable document identity shared by retrieval and context selection."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping


_SPACE = re.compile(r"\s+")


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return _SPACE.sub(" ", text)


def normalize_document_name(value: Any) -> str:
    """Normalize harmless filename variations without inventing aliases."""
    text = _normalize(value).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.lower().endswith(".txt"):
        text = text[:-4]
    return text


def document_key(item: Mapping[str, Any] | None) -> str:
    """Return a document-level key, falling back to the exact chunk identity.

    ``legacy-chunk:<hash>`` contains no document identity. It is therefore only
    safe as a final fallback; callers should preserve ``source_id`` or a real
    document name whenever retrieval results carry one.
    """
    item = item or {}
    source_id = _normalize(item.get("source_id"))
    if source_id:
        return f"source:{source_id}"

    for field in ("doc_name", "source_doc"):
        document_name = normalize_document_name(item.get(field))
        if document_name:
            return f"document:{document_name}"

    chunk_id = _normalize(item.get("chunk_id"))
    return f"chunk:{chunk_id}"
