#!/usr/bin/env python3
"""Compact claim-to-evidence contract for the four-domain cloud runtime."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "cloud-answer-claim-map-v1"
POLICY_VERSION = "cloud-claim-evidence-finalizer-v2"
CLAIM_MAP_OPEN = "<claim-map>"
CLAIM_MAP_CLOSE = "</claim-map>"
FAIL_CLOSED_ANSWER = (
    "当前证据不足以支持本次回答中的确定性断言，系统已停止输出未经核实的结论。"
    "请补充可追溯证据后重试。"
)

_TAIL = re.compile(r"<claim-map>\s*(.*?)\s*</claim-map>", re.DOTALL | re.IGNORECASE)
_SAFE_REFUSAL = re.compile(
    r"证据不足|没有直接证据|没有检索到可支持|无法核实|无法证实|无法确认|"
    r"不在本服务覆盖范围|停止输出|拒绝生成|服务不可用|大模型忙"
)
_REFUSAL_BYPASS = re.compile(
    r"(?:但|但是|不过|然而|其实|仍然|仍|结论是).{0,120}"
    r"(?:\d|必须|应当|不得|禁止|确定|就是|属于|有效|正确)"
)
_HIGH_RISK = re.compile(
    r"\d|[%％]|必须|应当|不得|禁止|安全|法规|规章|条款|执照|"
    r"资格|资质|证书|登记|许可|罚款|处罚|吊销|撤销|有效期|正确答案"
)
_OFFICIAL_REQUIREMENT = re.compile(
    r"法规|规章|条款|法律|规定|登记|许可|执照|资格|资质|证书|"
    r"罚款|处罚|吊销|撤销"
)
_PRESENTATION = re.compile(
    r"^(?:结构化数据|知识库补充|结论|回答|要点|说明|依据|来源)[:：]?$"
)
_LIST_PREFIX = re.compile(r"^(?:#{1,6}\s*|[-*+]\s+|\d+[.)、]\s*)")
_PUNCTUATION = re.compile(r"[\s，,。.;；:：!?！？、（）()\[\]【】{}“”‘’\"'《》<>]+")
_CJK = re.compile(r"[\u3400-\u9fff]")
_ALNUM = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}|\d+(?:\.\d+)?")
_RUNTIME_TRUST_FIELD = "_runtime_guard_trusted"
_MODEL_TEXT_AUTHORITIES = frozenset({
    "regulation",
    "exam_condition",
    "textbook",
    "official_api",
    "official_external",
})


def parse_claim_map(model_output: Any) -> dict[str, Any]:
    """Remove and parse the final machine-readable claim-map control tail."""
    raw = str(model_output or "")
    matches = list(_TAIL.finditer(raw))
    if len(matches) != 1:
        return {
            "answer": raw.replace(CLAIM_MAP_OPEN, "").replace(CLAIM_MAP_CLOSE, "").strip(),
            "claim_map": None,
            "error": "claim_map_missing" if not matches else "claim_map_multiple",
        }
    match = matches[0]
    answer = (raw[:match.start()] + raw[match.end():]).strip()
    if raw[match.end():].strip():
        return {"answer": answer, "claim_map": None, "error": "claim_map_not_final"}
    try:
        claim_map = json.loads(match.group(1))
    except (TypeError, ValueError):
        return {"answer": answer, "claim_map": None, "error": "claim_map_invalid_json"}
    if not isinstance(claim_map, dict) or not isinstance(claim_map.get("claims"), list):
        return {"answer": answer, "claim_map": None, "error": "claim_map_invalid_contract"}
    sanitized_claims = []
    for raw_claim in claim_map["claims"]:
        if not isinstance(raw_claim, Mapping):
            sanitized_claims.append(raw_claim)
            continue
        sanitized_claims.append({
            key: raw_claim[key]
            for key in ("claim_id", "text", "evidence", "risk")
            if key in raw_claim
        })
    return {
        "answer": answer,
        "claim_map": {"claims": sanitized_claims},
        "error": None,
    }


def _normalize_text(value: Any) -> str:
    text = _LIST_PREFIX.sub("", str(value or "").strip())
    return _PUNCTUATION.sub("", text).lower()


def _segments(answer: Any) -> list[str]:
    segments: list[str] = []
    for raw_line in str(answer or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized_line = _LIST_PREFIX.sub("", line).strip()
        if _PRESENTATION.fullmatch(normalized_line):
            continue
        if normalized_line.endswith(("：", ":")) and len(normalized_line) <= 24:
            continue
        for part in re.split(r"(?<=[。！？!?；;])\s*", normalized_line):
            part = part.strip()
            if part and _normalize_text(part):
                segments.append(part)
    return segments


def is_safe_refusal_answer(answer: Any) -> bool:
    """Accept only refusal sentences, never a refusal prefix plus a fact."""
    text = str(answer or "").strip()
    residual = _SAFE_REFUSAL.sub("", text)
    if not text or _REFUSAL_BYPASS.search(text) or _HIGH_RISK.search(residual):
        return False
    segments = _segments(text)
    return bool(segments) and all(_SAFE_REFUSAL.search(segment) for segment in segments)


def _authority(source: Mapping[str, Any]) -> str:
    explicit = str(source.get("authority") or "").strip().lower()
    if explicit:
        return explicit
    source_type = str(source.get("type") or "").strip().lower()
    if source_type == "canonical_csv":
        return "canonical_structured"
    doc_name = str(source.get("doc_name") or source.get("source_doc") or "")
    if doc_name.startswith(("政策法规_", "政策法规/", "法规_")):
        return "regulation"
    if doc_name.startswith(
        ("无人机理论书籍_", "无人机理论书籍/", "教材_", "理论书籍_")
    ):
        return "textbook"
    if doc_name.startswith(
        ("理论题库_", "理论题库/", "实操题库_", "题库_")
    ):
        return "question_bank"
    if doc_name.startswith("地面站考题考试条件/"):
        return "exam_condition"
    return "unknown"


def _catalog(
    internal_sources: Iterable[Mapping[str, Any]] | None,
    structured_sources: Iterable[Mapping[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    catalog: dict[str, dict[str, Any]] = {}
    duplicate_aliases: list[str] = []
    for index, raw_source in enumerate(internal_sources or (), start=1):
        if not isinstance(raw_source, Mapping):
            continue
        source = dict(raw_source)
        seq = source.get("seq")
        alias = str(source.get("evidence_alias") or f"S{seq or index}")
        evidence_id = str(source.get("chunk_id") or "")
        if not evidence_id:
            continue
        record = {
            **source,
            "alias": alias,
            "evidence_id": evidence_id,
            "authority": _authority(source),
            "kind": "internal",
        }
        if alias in catalog and catalog[alias]["evidence_id"] != evidence_id:
            duplicate_aliases.append(alias)
            continue
        catalog[alias] = record
    for index, raw_source in enumerate(structured_sources or (), start=1):
        if not isinstance(raw_source, Mapping):
            continue
        source = dict(raw_source)
        alias = str(source.get("evidence_alias") or f"C{index}")
        evidence_id = str(
            source.get("evidence_id")
            or f"canonical:{source.get('file') or source.get('doc_name') or index}"
        )
        record = {
            **source,
            "alias": alias,
            "evidence_id": evidence_id,
            "authority": _authority(source),
            "kind": "structured",
        }
        if alias in catalog and catalog[alias]["evidence_id"] != evidence_id:
            duplicate_aliases.append(alias)
            continue
        catalog[alias] = record
    return catalog, sorted(set(duplicate_aliases))


def evidence_aliases(
    internal_sources: Iterable[Mapping[str, Any]] | None = None,
    structured_sources: Iterable[Mapping[str, Any]] | None = None,
) -> list[str]:
    catalog, _ = _catalog(internal_sources, structured_sources)
    return list(catalog)


def build_claim_map_instruction(
    internal_sources: Iterable[Mapping[str, Any]] | None,
) -> str:
    aliases = evidence_aliases(internal_sources)
    allowed = "、".join(aliases) if aliases else "无"
    return (
        "\n\n机器可读证据约束（不得向用户解释）：正文结束后必须追加且只追加一段 "
        f"{CLAIM_MAP_OPEN} JSON {CLAIM_MAP_CLOSE}。JSON 形状固定为 "
        '{"claims":[{"text":"逐字复制正文中的一个完整事实句",'
        '"evidence":["S1"],"risk":"normal或high"}]}。'
        "正文中的每个事实句必须是单个证据片段中连续原文的逐字摘录，只允许删除原文，"
        "不得改写、拼接多个证据或推断；claim.evidence 只能引用实际包含该逐字原文的证据。"
        "每个有意义的正文句都必须被一个 claim.text 逐字覆盖；不得登记正文中不存在的句子。"
        f"evidence 只能使用本轮来源别名：{allowed}；S1 对应【来源1】，依此类推。"
        "无证据的事实句不得输出。证据不足时正文只能写‘当前证据不足，无法核实。’，"
        "并使用空 claims。"
    )


def synthesize_claim_map(answer: Any, aliases: Iterable[str]) -> dict[str, Any]:
    """Build an exact map for deterministic code paths, never for model prose."""
    text = str(answer or "").strip()
    if is_safe_refusal_answer(text):
        return {"claims": []}
    evidence = [str(alias) for alias in aliases if str(alias)]
    return {
        "claims": [
            {
                "text": segment,
                "evidence": evidence,
                "risk": "high" if _HIGH_RISK.search(segment) else "normal",
            }
            for segment in _segments(text)
        ]
    }


def merge_claim_maps(*claim_maps: Mapping[str, Any] | None) -> dict[str, Any]:
    claims = []
    for claim_map in claim_maps:
        if isinstance(claim_map, Mapping) and isinstance(claim_map.get("claims"), list):
            claims.extend(claim_map["claims"])
    return {"claims": claims}


def project_claim_map_to_answer(
    answer: Any,
    claim_map: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Drop claims for text removed by a deterministic deletion-only guard."""
    if not isinstance(claim_map, Mapping) or not isinstance(claim_map.get("claims"), list):
        return claim_map
    normalized_answer = _normalize_text(answer)
    return {
        "claims": [
            claim
            for claim in claim_map["claims"]
            if isinstance(claim, Mapping)
            and _normalize_text(claim.get("text"))
            and _normalize_text(claim.get("text")) in normalized_answer
        ]
    }


def synthesize_uncovered_guard_claims(
    answer: Any,
    aliases: Iterable[str],
    claim_map: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Create trusted claims only for text introduced by a deterministic guard."""
    existing_claims = (
        claim_map.get("claims", [])
        if isinstance(claim_map, Mapping) and isinstance(claim_map.get("claims"), list)
        else []
    )
    existing_texts = [
        str(claim.get("text") or "")
        for claim in existing_claims
        if isinstance(claim, Mapping)
    ]
    evidence = [str(alias) for alias in aliases if str(alias)]
    claims = []
    for segment in _segments(answer):
        if _segment_covered(segment, existing_texts):
            continue
        claims.append({
            "text": segment,
            "evidence": evidence,
            "risk": "high" if _HIGH_RISK.search(segment) else "normal",
            _RUNTIME_TRUST_FIELD: True,
        })
    return {"claims": claims}


def _related(claim_text: str, evidence: Mapping[str, Any]) -> bool:
    if evidence.get("kind") == "structured":
        return True
    evidence_text = str(evidence.get("text") or "")
    claim_normalized = _normalize_text(claim_text)
    evidence_normalized = _normalize_text(evidence_text)
    if not claim_normalized or not evidence_normalized:
        return False
    if claim_normalized in evidence_normalized or evidence_normalized in claim_normalized:
        return True

    claim_tokens = {token.lower() for token in _ALNUM.findall(claim_text)}
    evidence_tokens = {token.lower() for token in _ALNUM.findall(evidence_text)}
    if claim_tokens and not claim_tokens.issubset(evidence_tokens):
        return False
    claim_cjk = "".join(char for char in claim_normalized if _CJK.fullmatch(char))
    evidence_cjk = "".join(char for char in evidence_normalized if _CJK.fullmatch(char))
    bigrams = {claim_cjk[index:index + 2] for index in range(max(0, len(claim_cjk) - 1))}
    if not bigrams:
        return bool(claim_tokens.intersection(evidence_tokens))
    matched = sum(1 for token in bigrams if token in evidence_cjk)
    return matched >= 2 and matched / len(bigrams) >= 0.12


def _authoritative_text_entails_claim(
    claim_text: str,
    evidence: Mapping[str, Any],
) -> bool:
    """Require model prose to be a deletion-only authoritative extract."""
    if evidence.get("kind") != "internal":
        return False
    if evidence.get("authority") not in _MODEL_TEXT_AUTHORITIES:
        return False
    claim_normalized = _normalize_text(claim_text)
    evidence_normalized = _normalize_text(evidence.get("text"))
    return bool(
        claim_normalized
        and evidence_normalized
        and claim_normalized in evidence_normalized
    )


def _segment_covered(segment: str, claim_texts: Iterable[str]) -> bool:
    normalized_segment = _normalize_text(segment)
    if not normalized_segment:
        return True
    covered = [False] * len(normalized_segment)
    for raw_claim_text in claim_texts:
        claim_text = _normalize_text(raw_claim_text)
        if not claim_text:
            continue
        if normalized_segment in claim_text:
            return True
        start = 0
        while True:
            index = normalized_segment.find(claim_text, start)
            if index < 0:
                break
            for position in range(index, index + len(claim_text)):
                covered[position] = True
            start = index + 1
    return all(covered)


def finalize_claim_evidence(
    answer: Any,
    claim_map: Mapping[str, Any] | None,
    *,
    internal_sources: Iterable[Mapping[str, Any]] | None = None,
    structured_sources: Iterable[Mapping[str, Any]] | None = None,
    parse_error: str | None = None,
    trusted_deterministic: bool = False,
    allow_runtime_guard_claims: bool = False,
) -> dict[str, Any]:
    """Validate coverage, evidence allowlisting, relevance, and authority."""
    answer_text = str(answer or "").strip()
    catalog, duplicate_aliases = _catalog(internal_sources, structured_sources)
    reasons: list[str] = []
    if parse_error:
        reasons.append(parse_error)
    if not answer_text:
        reasons.append("answer_required")
    if duplicate_aliases:
        reasons.extend(f"ambiguous_evidence_alias:{alias}" for alias in duplicate_aliases)
    if not isinstance(claim_map, Mapping) or not isinstance(claim_map.get("claims"), list):
        reasons.append("claim_map_invalid_contract")
        raw_claims: list[Any] = []
    else:
        raw_claims = claim_map["claims"]

    evaluated_claims: list[dict[str, Any]] = []
    covered_claim_texts: list[str] = []
    accepted_ids: set[str] = set()
    unsupported_high_risk = 0
    for index, raw_claim in enumerate(raw_claims, start=1):
        claim_reasons: list[str] = []
        if not isinstance(raw_claim, Mapping):
            evaluated_claims.append({
                "claim_id": f"claim:{index}",
                "text": "",
                "risk": "high",
                "accepted_evidence_ids": [],
                "reasons": ["claim_not_object"],
                "supported": False,
            })
            unsupported_high_risk += 1
            continue
        claim_text = str(raw_claim.get("text") or "").strip()
        normalized_claim = _normalize_text(claim_text)
        if not normalized_claim:
            claim_reasons.append("claim_text_required")
        elif normalized_claim not in _normalize_text(answer_text):
            claim_reasons.append("claim_text_not_in_answer")
        else:
            covered_claim_texts.append(claim_text)

        declared_risk = str(raw_claim.get("risk") or "normal").strip().lower()
        risk = "high" if declared_risk == "high" or _HIGH_RISK.search(claim_text) else "normal"
        raw_aliases = raw_claim.get("evidence")
        if not isinstance(raw_aliases, list) or not raw_aliases:
            aliases: list[str] = []
            claim_reasons.append("evidence_required")
        else:
            aliases = [str(alias) for alias in raw_aliases]

        candidate_evidence: list[dict[str, Any]] = []
        for alias in aliases:
            evidence = catalog.get(alias)
            if evidence is None:
                claim_reasons.append(f"unknown_evidence_alias:{alias}")
                continue
            candidate_evidence.append(evidence)

        runtime_guard_trusted = bool(
            allow_runtime_guard_claims
            and raw_claim.get(_RUNTIME_TRUST_FIELD) is True
        )
        related_evidence = []
        unrelated_evidence = []
        non_entailing_evidence = []
        for evidence in candidate_evidence:
            if trusted_deterministic or runtime_guard_trusted:
                related_evidence.append(evidence)
            elif not _related(claim_text, evidence):
                unrelated_evidence.append(evidence)
            elif not _authoritative_text_entails_claim(
                claim_text,
                evidence,
            ):
                non_entailing_evidence.append(evidence)
            else:
                related_evidence.append(evidence)
        if unrelated_evidence:
            claim_reasons.append("unrelated_evidence")
        if non_entailing_evidence:
            claim_reasons.append(
                "high_risk_evidence_not_entailing"
                if risk == "high"
                else "evidence_not_entailing"
            )
        if _OFFICIAL_REQUIREMENT.search(claim_text) and not any(
            evidence.get("authority") in {"regulation", "official_api", "official_external"}
            for evidence in related_evidence
        ):
            claim_reasons.append("official_evidence_required")

        supported = not claim_reasons
        claim_accepted_ids = [evidence["evidence_id"] for evidence in related_evidence]
        if supported:
            accepted_ids.update(claim_accepted_ids)
        elif risk == "high":
            unsupported_high_risk += 1
        evaluated_claims.append({
            "claim_id": str(raw_claim.get("claim_id") or f"claim:{index}"),
            "text": claim_text,
            "risk": risk,
            "evidence_aliases": aliases,
            "accepted_evidence_ids": claim_accepted_ids,
            "reasons": list(dict.fromkeys(claim_reasons)),
            "supported": supported,
        })

    safe_refusal = is_safe_refusal_answer(answer_text)
    if not (safe_refusal and not raw_claims):
        for segment in _segments(answer_text):
            if not _segment_covered(segment, covered_claim_texts):
                reasons.append("answer_sentence_unmapped")
                break

    if not raw_claims and answer_text and not safe_refusal:
        reasons.append("positive_answer_requires_claims")
    unsupported_claims = sum(1 for claim in evaluated_claims if not claim["supported"])
    supported_claims = len(evaluated_claims) - unsupported_claims
    blocked = bool(reasons or unsupported_claims)
    outcome = "blocked" if blocked else "passed"
    telemetry = {
        "finalizer_invoked": True,
        "outcome": outcome,
        "claim_count": len(evaluated_claims),
        "supported_claims": supported_claims,
        "unsupported_claims": unsupported_claims,
        "unsupported_high_risk_claims": unsupported_high_risk,
        "claim_support_rate": (
            round(supported_claims / len(evaluated_claims), 4)
            if evaluated_claims
            else 1.0 if not blocked else 0.0
        ),
        "accepted_evidence_ids": sorted(accepted_ids),
        "policy_version": POLICY_VERSION,
    }
    return {
        "allowed": not blocked,
        "outcome": outcome,
        "answer": FAIL_CLOSED_ANSWER if blocked else answer_text,
        "claims": evaluated_claims,
        "reasons": list(dict.fromkeys(reasons)),
        "telemetry": telemetry,
    }
