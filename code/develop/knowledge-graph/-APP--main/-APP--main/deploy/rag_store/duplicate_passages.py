"""教材之间近似逐字复用段落的折叠。

和 `source_authority.filter_superseded` 同一层：都是 chunk 级登记表，都在
governance 之前把不该占 prompt 席位的 chunk 拿掉。区别在于让位的理由——
`filter_superseded` 处理的是「已被现行法规取代」，本模块处理的是「同一段话被
两本教材各印了一遍」。

为什么必须在 chunk 层做：`claim_dedup` 的跨书折叠要求两侧落在同一批实体上，
而这批重复段落是两次抽取 run 各自处理的，粒度完全不同（一侧抽出「地面站核心
功能」这类整句主题，一侧抽出「地面站」「遥测部分」这类真实实体），28 对重复
chunk 里只有 2 对有同名实体。claim 层配不上，只能在 chunk 层登记。

登记表由 governance_corrections/build_duplicate_passage_registry.py 生成。

一条硬规则：**只有代表段落也在本次检索结果里时才折叠**。否则某个问题只命中了
复用那一侧，折叠会把唯一的证据也抹掉。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REGISTRY_PATH = Path(__file__).with_name("duplicate_passages.json")
_registry_cache: Optional[Dict[str, Dict[str, Any]]] = None

EXCERPT_CHARS = 160
# 章节标题会被 chunk 的正文开头重复带上一次，摘录时去掉，否则引语里全是标题。
_HEADING_RE = re.compile(r"^\s*第[一二三四五六七八九十百\d]+[章节篇]\s*[^\n]*\n+")
_SENTENCE_END = "。！？；"


def _build_index(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """duplicate chunk_id → 该 chunk 的代表段落与折叠元数据。"""
    index: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        representative = entry.get("representative")
        if not isinstance(representative, dict):
            continue
        rep_id = str(representative.get("chunk_id") or "")
        if not rep_id:
            continue
        for duplicate in entry.get("duplicates") or []:
            if not isinstance(duplicate, dict):
                continue
            dup_id = str(duplicate.get("chunk_id") or "")
            # 自己不能是自己的代表；同一 chunk 只认第一条登记。
            if not dup_id or dup_id == rep_id or dup_id in index:
                continue
            index[dup_id] = {
                "representative_chunk_id": rep_id,
                "representative": representative,
                "duplicate": duplicate,
                "containment": duplicate.get("containment_in_representative"),
            }
    return index


def load_duplicate_passages(
    path: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """读取重复段落登记表（缓存；传 path 时不走缓存，供测试用）。"""
    global _registry_cache
    if path is None and _registry_cache is not None:
        return _registry_cache
    target = path or _REGISTRY_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        entries = [item for item in data.get("entries", []) if isinstance(item, dict)]
    except (OSError, ValueError):
        entries = []
    index = _build_index(entries)
    if path is None:
        _registry_cache = index
    return index


def _excerpt(result: Dict[str, Any]) -> str:
    """一段可以直接放进引号的摘录：去标题、并行、截到句子边界。"""
    text = _HEADING_RE.sub("", str(result.get("text") or ""), count=1)
    text = re.sub(r"\s+", "", text).strip()
    if len(text) <= EXCERPT_CHARS:
        return text
    window = text[:EXCERPT_CHARS]
    cut = max(window.rfind(mark) for mark in _SENTENCE_END)
    return window[: cut + 1] if cut > EXCERPT_CHARS // 3 else window


def _source_record(result: Dict[str, Any], registered: Dict[str, Any]) -> Dict[str, Any]:
    """按 answer_policy 认的 source 形状描述一条来源。"""
    doc_name = str(result.get("doc_name") or registered.get("doc_name") or "")
    record = {
        "chunk_id": str(result.get("chunk_id") or ""),
        "doc_name": doc_name,
        "source_doc": doc_name,
        "evidence_quote": _excerpt(result),
    }
    for field in ("pdf_page_start", "pdf_page_end", "chapter_title", "section_title"):
        value = result.get(field, registered.get(field))
        if value is not None:
            record[field] = value
    return record


def fold_duplicate_passages(
    results: List[Dict[str, Any]],
    *,
    registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把登记在册的复用段落折叠到它的代表段落上。

    只在代表段落也出现在 `results` 里时折叠——否则这段是该问题唯一的证据，
    抹掉它等于凭空丢失一个知识点。

    Returns:
        (保留的检索结果, 折叠记录)
    """
    index = load_duplicate_passages() if registry is None else registry
    if not index or not results:
        return list(results or []), []

    by_chunk = {
        str(item.get("chunk_id") or ""): item
        for item in results
        if isinstance(item, dict) and item.get("chunk_id")
    }

    kept: List[Dict[str, Any]] = []
    folds: List[Dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            kept.append(result)
            continue
        chunk_id = str(result.get("chunk_id") or "")
        registered = index.get(chunk_id)
        representative = (
            by_chunk.get(str(registered["representative_chunk_id"]))
            if registered
            else None
        )
        if representative is None or representative is result:
            kept.append(result)
            continue
        folds.append(
            {
                "chunk_id": chunk_id,
                "representative_chunk_id": str(registered["representative_chunk_id"]),
                "containment": registered.get("containment"),
                "duplicate_source": _source_record(result, registered["duplicate"]),
                "representative_source": _source_record(
                    representative, registered["representative"]
                ),
            }
        )
    return kept, folds


def duplicate_groups_for_context(
    folds: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """折叠记录 → `deduplicated_sources` 组，仅保留代表段落进了上下文的。

    形状与 claim_dedup 产出的组一致，`build_textbook_deduplication_answer`
    因此能照常出「已核验辅助来源」话术，不需要另加分支。
    """
    if not folds:
        return []
    in_context = {
        str(source.get("chunk_id") or "")
        for source in sources or []
        if isinstance(source, dict) and source.get("chunk_id")
    }

    grouped: Dict[str, Dict[str, Any]] = {}
    for fold in folds:
        rep_id = str(fold.get("representative_chunk_id") or "")
        if rep_id not in in_context:
            continue
        group = grouped.setdefault(
            rep_id,
            {
                "claim_key": f"duplicate-passage:{rep_id}",
                "source": "duplicate_passage_registry",
                "representative_source": fold["representative_source"],
                "supporting_sources": [],
            },
        )
        group["supporting_sources"].append(fold["duplicate_source"])

    for group in grouped.values():
        group["suppressed_count"] = len(group["supporting_sources"])
    return [grouped[key] for key in sorted(grouped)]
