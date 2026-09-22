#!/usr/bin/env python3
"""题库原题匹配与题库栏目清洗

背景（2026-07-26 李腾达提出）：`question_bank_hit` 只表示"检索命中了题库文档"，
不代表"用户问的就是那道原题"。旧逻辑把这两件事混为一谈，于是像
"中型多旋翼超视距可以商用吗"这种非原题提问，也被强制套上「题库关联」栏目，
逼模型写出题号/题干/选项/正确答案——来源里根本没有，只能写成"来源未提供"
或挂一道不相干的近似题（实测挂了 113 题训练时长），属于纯噪声甚至误导。

新规则：**没匹配到完全相同的原题，就不输出任何题库关联内容。**

本模块提供四件事：
1. `parse_question_bank_entries` — 把题库 chunk 原文解析成题号/题干/选项/答案
2. `match_original_question` — 判断用户问题是否就是某道原题（完全相同口径）
3. `build_exact_question_answer` — 对完全相同且证据已绑定的题目生成确定性答案
4. `strip_question_bank_sections` — 非原题命中时，删除答案里的题库关联栏目
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# 完全相同原题的判定阈值。
# - 归一化后完全相等 → 1.0
# - 一方完整包含另一方（用户贴了带选项的整题 / 题干带编号）→ 短/长 长度比
# - 其余情况用 difflib 比值兜住标点、错字级别的抄写差异
# 阈值故意定得高：宁可判成"不是原题"少输出一个栏目，也不要挂错题号误导学员。
EXACT_MATCH_MIN_RATIO = 0.95
CONTAINMENT_MIN_RATIO = 0.90
MIN_STEM_CHARS = 6
EXACT_QUESTION_POLICY_VERSION = "question-bank-exact-answer-v1"

# Character similarity is not semantic equivalence. A single negation can flip
# the answer while still scoring above the fuzzy exact-match threshold.
_NEGATION_CUES = (
    "不属于",
    "不包括",
    "不包含",
    "不正确",
    "不准确",
    "不符合",
    "不能",
    "不得",
    "禁止",
    "不允许",
    "不可以",
    "不应",
    "不宜",
    "不是",
    "错误的是",
    "有误的是",
)

_NEIGHBOR_LABEL = re.compile(r"^\s*\[(?:命中片段|相邻片段)[^\]]*\]\s*$")
_SOURCE_HEADER = re.compile(r"^\s*【来源\d+】")
_QUESTION_START = re.compile(r"^\s*(\d{1,4})\s*[.、．]\s*(.*)$")
_OPTION_LINE = re.compile(r"^\s*([A-Ha-h])\s*[.、．:：]\s*(.*)$")
_ANSWER_LINE = re.compile(r"^\s*(?:参考答案|正确答案|标准答案|答案)\s*[:：]\s*(.+?)\s*$")
_EXPLAIN_LINE = re.compile(r"^\s*(?:解析|解答|讲解|分析)\s*[:：]?\s*$")
_INLINE_OPTIONS = re.compile(r"[\s(（]?A\s*[.、．:：]\s*\S")
_LEADING_NO = re.compile(r"^\s*\d{1,4}\s*[.、．]\s*")
_BLANK_SLOT = re.compile(r"[（(]\s*[)）]|_{2,}|＿{2,}|[·•]{2,}")
# 题库里混着分值和题型标注（"…有几根引出线[1分]"），它们不是题干的一部分，
# 逐字比对前必须剔除，否则原题会被判成"不是原题"（2026-07-26 162 题实测）。
_ANNOTATION = re.compile(
    r"[\[【（(]\s*(?:\d+(?:\.\d+)?\s*分|单选(?:题)?|多选(?:题)?|判断(?:题)?|填空(?:题)?|简答(?:题)?)\s*[\]】）)]"
)
_DROP_CHARS = re.compile(
    r"[\s　。，、；：？！,.;:?!\-—_…·\"'“”‘’()（）\[\]【】{}《》<>/\\|~`@#$%^&*+=]"
)


def normalize_question_text(text: Any) -> str:
    """题面归一化：全角转半角、去空白标点、去填空占位符。"""
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = _ANNOTATION.sub("", normalized)
    normalized = _BLANK_SLOT.sub("", normalized)
    normalized = _DROP_CHARS.sub("", normalized)
    normalized = normalized.lower().replace("其它", "其他")
    # 口述题会把选择题未写出的答项维度补进题干，例如原题止于“应该判断为”，
    # 用户会问成“应该判断为与谁飞行”。这仍是同一道原题，不应退化成普通生成。
    normalized = re.sub(r"((?:应该|应当|应)?判断为)(?:与谁)?(?:如何|怎样)?飞行$", r"\1", normalized)
    normalized = re.sub(r"^如(?=观察|发现|看到)", "如果", normalized)
    return normalized


def _clean_lines(text: str) -> List[str]:
    lines = []
    for line in str(text or "").splitlines():
        if _NEIGHBOR_LABEL.match(line):
            continue
        lines.append(_SOURCE_HEADER.sub("", line))
    return lines


def parse_question_bank_entries(text: str) -> List[Dict[str, Any]]:
    """把题库 chunk 原文解析成结构化题目。

    题库入库格式（理论题库）：
        113.题干……
        A.选项一
        B.选项二
        参考答案：C
        解析：……

    解析正文里也会出现 "1." 这种编号行，因此只有"后面跟得上选项行或答案行"
    的编号行才算新题的开始。
    """
    lines = _clean_lines(text)
    starts = []
    for index, line in enumerate(lines):
        if not _QUESTION_START.match(line):
            continue
        # 前瞻：真题干后面一定跟着选项或参考答案，解析里的编号行不会。
        for probe in lines[index + 1 : index + 14]:
            if _QUESTION_START.match(probe):
                break
            if _OPTION_LINE.match(probe) or _ANSWER_LINE.match(probe):
                starts.append(index)
                break

    entries: List[Dict[str, Any]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        head = _QUESTION_START.match(lines[start])
        number, first = head.group(1), head.group(2)
        stem_parts = [first] if first.strip() else []
        options: List[str] = []
        answer = ""
        in_explanation = False
        for line in lines[start + 1 : end]:
            if _EXPLAIN_LINE.match(line):
                in_explanation = True
                continue
            answer_hit = _ANSWER_LINE.match(line)
            if answer_hit and not answer:
                answer = answer_hit.group(1).strip()
                continue
            option_hit = _OPTION_LINE.match(line)
            if option_hit and not in_explanation:
                options.append(f"{option_hit.group(1).upper()}.{option_hit.group(2).strip()}")
                continue
            if in_explanation or answer or options:
                continue
            if line.strip():
                stem_parts.append(line.strip())
        stem = " ".join(part.strip() for part in stem_parts if part.strip()).strip()
        if not stem:
            continue
        entries.append(
            {
                "number": number,
                "stem": stem,
                "options": options,
                "answer": answer,
            }
        )
    return entries


def extract_query_stem(query: str) -> str:
    """从用户问题里剥出题干：去掉粘贴进来的选项、参考答案和题号。"""
    kept: List[str] = []
    for line in str(query or "").splitlines():
        if _OPTION_LINE.match(line) or _ANSWER_LINE.match(line) or _EXPLAIN_LINE.match(line):
            break
        kept.append(line.strip())
    stem = " ".join(part for part in kept if part).strip()
    # 选项也可能和题干挤在同一行："……（ ）A.xx B.yy C.zz"
    inline = _INLINE_OPTIONS.search(stem)
    if inline and re.search(r"B\s*[.、．:：]\s*\S", stem[inline.start() :]):
        stem = stem[: inline.start()].strip()
    return _LEADING_NO.sub("", stem).strip()


def question_similarity(left: str, right: str) -> float:
    """归一化题面的相似度；1.0 表示逐字相同。"""
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return min(len(left), len(right)) / max(len(left), len(right))
    return difflib.SequenceMatcher(None, left, right).ratio()


def _negation_signature(text: str) -> frozenset[str]:
    """返回题干中会改变选择方向的否定标记。"""
    return frozenset(cue for cue in _NEGATION_CUES if cue in text)


def match_original_question(
    query: str,
    candidates: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """用户问题是否就是题库里的某道原题。

    Args:
        query: 用户原始问题
        candidates: 检索命中的题库 chunk（需含 `text`，可含 `chunk_id`/`doc_name`）

    Returns:
        命中时返回题号/题干/选项/答案/来源和相似度；不是原题时返回 None。
    """
    normalized_query = normalize_question_text(extract_query_stem(query))
    if len(normalized_query) < MIN_STEM_CHARS:
        return None

    best: Optional[Dict[str, Any]] = None
    for candidate in candidates or []:
        text = candidate.get("text") or candidate.get("expanded_text") or ""
        if not text:
            continue
        for entry in parse_question_bank_entries(text):
            normalized_stem = normalize_question_text(entry["stem"])
            if len(normalized_stem) < MIN_STEM_CHARS:
                continue
            if _negation_signature(normalized_query) != _negation_signature(
                normalized_stem
            ):
                continue
            similarity = question_similarity(normalized_query, normalized_stem)
            contained = (
                normalized_query in normalized_stem or normalized_stem in normalized_query
            )
            threshold = CONTAINMENT_MIN_RATIO if contained else EXACT_MATCH_MIN_RATIO
            if similarity < threshold:
                continue
            if best and similarity <= best["similarity"]:
                continue
            best = {
                "chunk_id": candidate.get("chunk_id", ""),
                "doc_name": candidate.get("doc_name", ""),
                "number": entry["number"],
                "stem": entry["stem"],
                "options": entry["options"],
                "answer": entry["answer"],
                "similarity": round(similarity, 4),
                "match_type": "identical" if similarity >= 1.0 else "normalized",
            }
    return best


def build_exact_question_answer(
    matched_question: Mapping[str, Any] | None,
    trusted_sources: Sequence[Mapping[str, Any]] | None,
) -> Optional[Dict[str, Any]]:
    """Build a deterministic answer only for an identical, source-bound question."""

    if not isinstance(matched_question, Mapping):
        return None
    try:
        similarity = float(matched_question.get("similarity"))
    except (TypeError, ValueError):
        return None
    if matched_question.get("match_type") != "identical" or similarity != 1.0:
        return None
    if matched_question.get("superseded_note"):
        return None

    chunk_id = str(matched_question.get("chunk_id") or "").strip()
    trusted_by_id = {
        str(source.get("chunk_id") or source.get("source_id") or "").strip(): source
        for source in trusted_sources or ()
        if isinstance(source, Mapping)
    }
    trusted_source = trusted_by_id.get(chunk_id)
    if trusted_source is None:
        return None
    trusted_doc_name = str(trusted_source.get("doc_name") or "")
    if not (
        chunk_id.startswith("question_bank:")
        or (
            chunk_id.startswith("chunk:")
            and trusted_doc_name.startswith("理论题库/")
        )
    ):
        return None

    option_map: Dict[str, str] = {}
    for raw_option in matched_question.get("options") or ():
        hit = _OPTION_LINE.fullmatch(str(raw_option or "").strip())
        if not hit or not hit.group(2).strip():
            continue
        label = hit.group(1).upper()
        option_map[label] = f"{label}.{hit.group(2).strip()}"

    raw_answer = unicodedata.normalize(
        "NFKC", str(matched_question.get("answer") or "")
    ).strip()
    if not raw_answer:
        return None
    compact_labels = re.sub(r"[\s,，、/|;；]+", "", raw_answer).upper()
    if re.fullmatch(r"[A-H]+", compact_labels):
        labels = list(dict.fromkeys(compact_labels))
        if any(label not in option_map for label in labels):
            return None
        rendered_answer = "、".join(option_map[label] for label in labels)
    else:
        rendered_answer = raw_answer

    answer = f"正确答案：{rendered_answer}"
    return {
        "answer": answer,
        "evidence_ids": [chunk_id],
        "mode": "question_bank_exact",
        "policy_version": EXACT_QUESTION_POLICY_VERSION,
        "question_number": str(matched_question.get("number") or ""),
        "similarity": similarity,
    }


def format_matched_question(match: Dict[str, Any]) -> str:
    """把命中的原题格式化成可直接引用的证据块（避免模型自己编题号）。"""
    if not match:
        return ""
    lines = [
        f"题号：{match.get('number') or '来源未提供'}",
        f"题干：{match.get('stem') or '来源未提供'}",
    ]
    options = match.get("options") or []
    lines.append("选项：" + ("；".join(options) if options else "来源未提供"))
    lines.append(f"正确答案：{match.get('answer') or '来源未提供'}")
    source = match.get("doc_name") or match.get("chunk_id")
    if source:
        lines.append(f"出处：{source}")
    return "\n".join(lines)


# ============ 输出侧清洗 ============

_QB_SECTION_TITLE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*{1,2}\s*)?"
    r"(?:题库关联|题库对应|关联题库|相关题目|关联题目|近似题目?|相似题目?|类似题目?"
    r"|原题(?:还原|回顾|对照|链接)?|对应原题|题库参考)"
    r"\s*(?:\*{1,2})?\s*[:：]?"
)
_MD_HEADING = re.compile(r"^\s*(#{1,6})\s+\S")
_BOLD_ONLY = re.compile(r"^\s*\*{2}[^*]+\*{2}\s*[:：]?\s*$")
_LABEL_LINE = re.compile(r"^\s*(?:\*{2})?[一-龥A-Za-z][一-龥A-Za-z0-9（）()·、]{1,14}(?:\*{2})?\s*[:：]")
_HR_LINE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_BRACKET_TITLE = re.compile(r"^\s*【[^】]{1,20}】\s*$")
_NO_EXACT_MATCH_NOTE = re.compile(
    r"^.{0,40}(?:未匹配到|没有匹配到|未找到|没有找到)(?:完全)?相同(?:的)?原题.{0,60}$"
)
_ORPHAN_FIELD = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*{2})?(?:题号|题干|选项|正确答案|参考答案)(?:\*{2})?\s*[:：]"
)
EMPTY_AFTER_STRIP_NOTICE = (
    "本轮检索命中的题库内容与你问的不是同一道题，按规则已不再输出题库关联内容。"
    "如果你要的是某道原题的标准答案，请把完整题干和选项发过来。"
)


def _heading_level(line: str) -> int:
    hit = _MD_HEADING.match(line)
    return len(hit.group(1)) if hit else 0


def _is_boundary(line: str, *, level: int) -> bool:
    """判断某行是否结束当前题库栏目。

    栏目由 markdown 标题起头时，只有同级/更高级标题、分隔线才算结束——中间的
    `**题号：**`、`**选项：**`、`**补充：**` 都是这个栏目的子标签，不能提前收尾
    （否则选项行会被漏在外面，2026-07-26 实测漏了 A/B/C 三行）。
    """
    if _ORPHAN_FIELD.match(line) or _QB_SECTION_TITLE.match(line):
        return False
    heading = _heading_level(line)
    if heading:
        return heading <= level if level else True
    if _HR_LINE.match(line) or _BRACKET_TITLE.match(line):
        return True
    if level:
        return False
    return bool(_BOLD_ONLY.match(line) or _LABEL_LINE.match(line))


def strip_question_bank_sections(answer: str) -> str:
    """删除答案里的题库关联栏目。

    只在"没有匹配到完全相同原题"时调用：此时任何题号/题干/选项/正确答案都不是
    用户这道题的，属于误导性内容，必须整段删除而不是留个"来源未提供"占位。
    """
    original = str(answer or "")
    if not original.strip():
        return original

    lines = original.splitlines()
    kept: List[str] = []
    skipping = False
    skip_level = 0
    for line in lines:
        if skipping:
            if not _is_boundary(line, level=skip_level):
                continue
            skipping = False
            # 收尾的分隔线属于被删栏目的边框，留着会让上一行变成 setext 标题。
            if _HR_LINE.match(line):
                continue
        if _QB_SECTION_TITLE.match(line):
            skipping = True
            skip_level = _heading_level(line)
            # 顺带把栏目上方的分隔线收走，避免留下孤立的 ---
            while kept and (_HR_LINE.match(kept[-1]) or not kept[-1].strip()):
                kept.pop()
            continue
        if _NO_EXACT_MATCH_NOTE.match(line) or _ORPHAN_FIELD.match(line):
            continue
        kept.append(line)

    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"(?m)^\s*(?:-{3,}|\*{3,})\s*$\n(?=\s*(?:-{3,}|\*{3,})\s*$)", "", cleaned)
    cleaned = re.sub(r"(?:^|\n)\s*(?:-{3,}|\*{3,})\s*$", "", cleaned).strip()
    # 整段都是题库栏目时不能交白卷，也不能把不相干的原题还回去。
    if not cleaned:
        return EMPTY_AFTER_STRIP_NOTICE
    return cleaned


def answer_has_question_bank_section(answer: str) -> bool:
    """答案里是否还残留题库关联栏目（供门禁校验用）。"""
    for line in str(answer or "").splitlines():
        if _QB_SECTION_TITLE.match(line) or _ORPHAN_FIELD.match(line):
            return True
    return False
