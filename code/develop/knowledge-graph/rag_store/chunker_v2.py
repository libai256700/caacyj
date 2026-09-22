#!/usr/bin/env python3
"""Structure-aware chunking for the canonical RAG text store.

The chunker keeps business evidence boundaries before falling back to a character
window. It is intentionally independent from SQLite writes so migrations can be
previewed and replayed before touching authoritative chunk ids.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ChunkProfile:
    domain: str
    mode: str
    target_chars: int
    max_chars: int
    overlap_chars: int


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_name: str
    chunk_index: int
    text: str
    domain: str
    split_rule: str


CN_NUM = "一二三四五六七八九十百千零〇两"
ARTICLE_RE = re.compile(rf"(?m)^\s*(第([{CN_NUM}]+|\d+)[条][^\n]*)")
CCAR_ARTICLE_RE = re.compile(r"(?m)^\s*(第(\d+)\.(\d+)条[^\n]*)")
STANDARD_CLAUSE_RE = re.compile(r"(?m)^\s*((\d+(?:\.\d+)*)\s+[^\n]{1,80})")
QUESTION_RE = re.compile(r"(?m)^\s*(\d{1,4})[.．]\s*[^\n]{2,}")
STRUCTURAL_HEADING_RE = re.compile(
    rf"(?m)^\s*((第[{CN_NUM}\d.]+[章节条][^\n]*)|([一二三四五六七八九十]+[、.．][^\n]{{0,80}})|(\d+(\.\d+)*\s+[^\n]{{0,80}}))"
)


def infer_profile(doc_name: str) -> ChunkProfile:
    if doc_name.startswith("理论题库_"):
        return ChunkProfile("question_bank", "question", 850, 1200, 80)
    if doc_name.startswith("政策法规_"):
        return ChunkProfile("regulation", "article", 700, 1000, 80)
    if doc_name.startswith("无人机理论书籍_"):
        return ChunkProfile("textbook", "section", 900, 1200, 120)
    if doc_name.startswith(("企业信息_", "人事制度_")):
        return ChunkProfile("company_policy", "section", 650, 900, 80)
    return ChunkProfile("general", "section", 700, 900, 80)


def chunk_document(doc_name: str, text: str, profile: ChunkProfile | None = None) -> list[Chunk]:
    profile = profile or infer_profile(doc_name)
    normalized = normalize_text(text)
    units = split_units(normalized, profile)
    if profile.mode in {"question", "article"}:
        packed = []
        for unit in units:
            packed.extend(split_long_text(unit, profile))
    else:
        packed = pack_units(units, profile)

    chunks: list[Chunk] = []
    for idx, chunk_text in enumerate(packed):
        cleaned = chunk_text.strip()
        if not cleaned:
            continue
        chunks.append(
            Chunk(
                chunk_id=build_chunk_id(doc_name, idx, cleaned, profile),
                doc_name=doc_name,
                chunk_index=len(chunks),
                text=cleaned,
                domain=profile.domain,
                split_rule=f"chunker_v2:{profile.mode}",
            )
        )
    return chunks


def build_chunk_id(doc_name: str, index: int, text: str, profile: ChunkProfile) -> str:
    doc_key = doc_key_for_id(doc_name, profile)
    if profile.mode == "article":
        article_id = article_key(text)
        if article_id:
            return f"{profile.domain}:{doc_key}:{article_id}"
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
        return f"{profile.domain}:{doc_key}:preface_{index:03d}:{digest}"
    if profile.mode == "question":
        question_id = question_key(text)
        if question_id:
            return f"{profile.domain}:{doc_key}:{question_id}:idx_{index:04d}"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{profile.domain}:{doc_key}:chunk_{index:04d}:{digest}"


def doc_key_for_id(doc_name: str, profile: ChunkProfile) -> str:
    stem = Path(doc_name).stem
    aliases = {
        "政策法规_中华人民共和国民用航空法_2025修订_2026-07-01施行": "cn_civil_aviation_law_2025",
        "政策法规_CCAR-92部": "ccar_92",
        "政策法规_《民用中小型无人驾驶航空器操控员训练机构规范》": "uas_training_org_spec",
    }
    if stem in aliases:
        return aliases[stem]
    safe_stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", stem).strip("_")
    return safe_stem or profile.domain


def article_key(text: str) -> str:
    first_lines = "\n".join(text.splitlines()[:3])
    ccar = CCAR_ARTICLE_RE.search(first_lines)
    if ccar:
        return f"art_{int(ccar.group(2)):03d}_{int(ccar.group(3)):03d}"
    match = ARTICLE_RE.search(first_lines)
    if match:
        raw = match.group(2)
        number = int(raw) if raw.isdigit() else chinese_num_to_int(raw)
        return f"art_{number:03d}" if number > 0 else ""
    clause = STANDARD_CLAUSE_RE.search(first_lines)
    if clause:
        parts = [f"{int(part):03d}" for part in clause.group(2).split(".")]
        return "clause_" + "_".join(parts)
    return ""


def question_key(text: str) -> str:
    match = QUESTION_RE.match(text.lstrip())
    if not match:
        return ""
    return f"q_{int(match.group(1)):04d}"


def chinese_num_to_int(value: str) -> int:
    value = value.strip()
    if not value:
        return 0
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in digits:
            number = digits[char]
        elif char in units:
            unit = units[char]
            section += (number or 1) * unit
            number = 0
        else:
            return 0
    total += section + number
    return total


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_units(text: str, profile: ChunkProfile) -> list[str]:
    if profile.mode == "question":
        units = split_by_question(text)
        if len(units) >= 3:
            return units
    if profile.mode == "article":
        units = split_by_regex_marker(text, ARTICLE_RE)
        if len(units) >= 3:
            return units
    units = split_by_regex_marker(text, STRUCTURAL_HEADING_RE)
    if len(units) >= 3:
        return units
    return split_paragraphs(text)


def split_by_question(text: str) -> list[str]:
    matches = list(QUESTION_RE.finditer(text))
    if len(matches) < 3:
        return []
    candidates = slices_from_matches(text, matches)
    valid_units = [unit for unit in candidates if is_question_unit(unit)]
    if len(valid_units) < 3:
        return []
    return valid_units


def is_question_unit(unit: str) -> bool:
    head = unit[:120]
    has_answer = "参考答案" in unit or re.search(r"(?m)^\s*答案[:：]", unit)
    has_choices = len(re.findall(r"(?m)^\s*[A-D][.、．]", unit)) >= 2
    return bool(QUESTION_RE.match(unit.lstrip()) and has_answer and has_choices and len(head) >= 8)


def split_by_regex_marker(text: str, regex: re.Pattern[str]) -> list[str]:
    if regex is ARTICLE_RE:
        matches = sorted([*ARTICLE_RE.finditer(text), *CCAR_ARTICLE_RE.finditer(text)], key=lambda item: item.start())
    else:
        matches = list(regex.finditer(text))
    if len(matches) < 2:
        return []
    prefix = text[: matches[0].start()].strip()
    units = slices_from_matches(text, matches)
    if prefix:
        return [prefix, *units]
    return units


def slices_from_matches(text: str, matches: Iterable[re.Match[str]]) -> list[str]:
    spans = list(matches)
    units = []
    for i, match in enumerate(spans):
        start = match.start()
        end = spans[i + 1].start() if i + 1 < len(spans) else len(text)
        unit = text[start:end].strip()
        if unit:
            units.append(unit)
    return units


def split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def pack_units(units: list[str], profile: ChunkProfile) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.extend(split_long_text("\n\n".join(current), profile))
            current = []
            current_len = 0

    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        if len(unit) > profile.max_chars:
            flush()
            chunks.extend(split_long_text(unit, profile))
            continue
        projected = current_len + len(unit) + (2 if current else 0)
        if current and projected > profile.target_chars:
            flush()
        current.append(unit)
        current_len += len(unit) + (2 if current_len else 0)
    flush()
    return [chunk for chunk in chunks if chunk.strip()]


def split_long_text(text: str, profile: ChunkProfile) -> list[str]:
    text = text.strip()
    if len(text) <= profile.max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + profile.max_chars)
        if end < len(text):
            boundary = best_boundary(text, start + profile.target_chars, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - profile.overlap_chars, start + 1)
    return chunks


def best_boundary(text: str, target: int, hard_end: int) -> int:
    target = min(target, hard_end)
    candidates = []
    for pattern in ("\n\n", "\n", "。", "；", "，", " "):
        pos = text.rfind(pattern, 0, hard_end)
        if pos >= target - 180:
            candidates.append(pos + len(pattern))
    if candidates:
        return max(candidates)
    return hard_end


def summarize_chunks(chunks: list[Chunk]) -> dict:
    lengths = [len(chunk.text) for chunk in chunks]
    return {
        "chunk_count": len(chunks),
        "min_chars": min(lengths) if lengths else 0,
        "avg_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "max_chars": max(lengths) if lengths else 0,
        "domains": sorted({chunk.domain for chunk in chunks}),
    }
