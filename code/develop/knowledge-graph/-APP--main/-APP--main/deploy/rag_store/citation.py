#!/usr/bin/env python3
"""答案引用判据（遥测用）。

旧实现只匹配字面“来源”二字，导致大量逐条引用法规条款的答案（如
“（CCAR-92部第92.655条）”）被误判为“无引用”，质量看板“无引用”数字虚高。

本模块覆盖问答系统实际产出的引用格式。诚实兜底类答案（“知识库未涉及……分析
推断……”）本就不含这些标记，仍正确计为无引用——修完后“无引用”成为知识库真空
缺口的有效信号，而非噪声。
"""

from __future__ import annotations

import re

_CITATION_MARKERS = re.compile(
    r"来源"                                         # 沿用旧口径的“来源”字样，确保存量“有引用”零回归
    r"|第\s*\d+(?:\.\d+)?\s*条"                     # 条款号：第92.655条 / 第26条
    r"|(?:CCAR|MD)[-\s]?\d+"                        # 法规编号：CCAR-92 / MD-92
    r"|【证据链】"                                   # 图谱证据链标记
    r"|《[^》]{2,}》"                                # 书名号引用来源
    r"|\[[a-z]{2,6}_[0-9a-f]{6,}\]"                 # 规范实体ID：[ins_2678e1accf50]
)


def answer_has_citation(answer: str | None, response_sources) -> bool:
    """答案是否既有召回来源、又在正文中携带可溯源引用标记。

    与旧口径一致地要求 ``response_sources`` 非空（无召回来源谈不上引用），
    再在正文中匹配任一已知引用格式。

    注意：这是**遥测口径**，必须在展示清洗之前对原始模型答案计算。展示层会把
    `【来源N】`去掉（见下方 render_answer_citations），如果在清洗后再算，
    看板上的"无引用"会集体虚高。
    """
    return bool(response_sources) and bool(_CITATION_MARKERS.search(answer or ""))


# ============ 展示层：用户看到的引用形态 ============
# 2026-07-26 李腾达：普通用户问答里不许出现 `【来源1】` 这种临时编号——用户看不到
# 那张来源列表，编号既不可核验也不专业；也不要用"根据知识库已有信息""根据提供的
# 上下文"开场，那是系统内部话术。只有用户明确追问来源/依据/出处时才列来源，
# 而且要写成《文档名》，不是编号。

_SOURCE_MARKER = re.compile(r"[【\[]\s*来源\s*(\d{1,2})\s*[】\]]")
_SOURCE_DISCLOSURE_ASK = re.compile(
    r"来源|出处|依据(?:是什么|哪|什么)|引用|原文|文号|条款号|哪(?:份|个)(?:文件|文档|资料|法规)"
    r"|怎么知道|从哪(?:里|儿)?(?:查|来|得)|查(?:的|了)什么|知识库(?:里|中)?(?:有没有|查|命中)"
    r"|核验|核实|可信吗|真的吗|trace|provenance"
)
_KB_META_PREAMBLE = re.compile(
    r"^\s*(?:根据|基于|依据)?\s*(?:提供的|现有的?|已有的?|当前的?|本轮)?\s*"
    r"(?:知识库(?:已有)?(?:信息|内容|资料)?|检索(?:到的)?(?:上下文|内容|资料|结果)?|上下文|资料)\s*"
    r"[，,：:]\s*"
)
_DOC_CATEGORY_PREFIX = re.compile(
    r"^(?:政策法规|理论题库|实操题库|无人机理论书籍)_"
)


def asks_for_source_disclosure(question: str | None) -> bool:
    """用户是不是在追问来源/依据（后台核验口径）。"""
    return bool(_SOURCE_DISCLOSURE_ASK.search(str(question or "")))


def display_source_name(doc_name: str | None) -> str:
    """把内部文档名转成用户可读的引用名：`政策法规_CCAR-92部.txt` → `《CCAR-92部》`。"""
    name = str(doc_name or "").strip()
    if not name:
        return ""
    name = re.sub(r"\.(?:txt|md|pdf|docx?|csv)$", "", name, flags=re.IGNORECASE)
    name = _DOC_CATEGORY_PREFIX.sub("", name).strip()
    if not name:
        return ""
    if name.startswith("《") and name.endswith("》"):
        return name
    return f"《{name}》"


def answer_has_source_marker(answer: str | None) -> bool:
    """答案里是否还残留 `【来源N】` 这类临时编号。"""
    return bool(_SOURCE_MARKER.search(str(answer or "")))


def render_answer_citations(
    answer: str | None,
    sources: Iterable[Dict[str, Any]] | None = None,
    *,
    disclose: bool = False,
) -> str:
    """把答案里的 `【来源N】` 处理成用户可见的形态。

    disclose=True（用户在追问来源）→ 换成《文档名》；
    disclose=False（普通问答）    → 直接删除，并去掉"根据知识库已有信息："这类开场白。
    """
    text = str(answer or "")
    if not text:
        return text

    names: Dict[str, str] = {}
    for index, source in enumerate(sources or []):
        seq = source.get("seq") if isinstance(source, dict) else None
        key = str(seq if isinstance(seq, int) else index + 1)
        display = display_source_name(
            (source or {}).get("doc_name") or (source or {}).get("title")
        )
        if display:
            names.setdefault(key, display)

    def _replace(match: re.Match) -> str:
        if not disclose:
            return ""
        return names.get(match.group(1), "")

    text = _SOURCE_MARKER.sub(_replace, text)
    if disclose:
        # 句子里本来就点了文档名时，替换会写成《X》《X》
        text = re.sub(r"(《[^》]+》)(?:\s*\1)+", r"\1", text)
    else:
        text = _KB_META_PREAMBLE.sub("", text, count=1)
    # 删掉编号后可能留下空括号、连续标点和行首孤立标点
    text = re.sub(r"[（(]\s*[)）]", "", text)
    text = re.sub(r"(?m)^[ \t]*[，,、。；;：:]\s*", "", text)
    text = re.sub(r"[，,、]{2,}", "，", text)
    text = re.sub(r"\s+([。，、；：！？])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
