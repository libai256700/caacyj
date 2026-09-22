#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any

from rag_store.query_trace import source_name
from rag_store.anchor_rules import CAL_PRIORITY_RULES, MD92_PRIORITY_RULES, UAS_PRIORITY_RULES, first_match_chunk_ids


CAAC_PRACTICAL_SCORE_CLAIM_TERMS = (
    "起飞10分",
    "悬停20分",
    "航线飞行30分",
    "应急处置20分",
    "降落20分",
)

CAAC_PRACTICAL_SCORE_CLAIM_PATTERNS = (
    r"起飞\s*[:：]?\s*10\s*分?",
    r"悬停\s*[:：]?\s*20\s*分?",
    r"航线(?:飞行)?\s*[:：]?\s*30\s*分?",
    r"应急(?:处置)?\s*[:：]?\s*20\s*分?",
    r"降落\s*[:：]?\s*20\s*分?",
)

REGULATION_GATE_QUESTION_TERMS = (
    "无犯罪记录",
    "犯罪记录",
    "无犯罪证明",
    "无犯罪记录证明",
    "无犯罪记录声明",
    "醉驾",
    "酒驾",
    "危险驾驶",
    "前科",
    "案底",
)

REGULATION_GATE_LICENSE_TERMS = (
    "CAAC",
    "执照",
    "报考",
    "报名",
    "申请条件",
    "申请材料",
    "合格证",
    "CCAR",
    "92部",
)

REGULATION_ELIGIBILITY_TERMS = (
    "申请条件",
    "资格条件",
    "申请材料",
    "提交材料",
    "报名材料",
    "所需材料",
    "材料",
    "不得申请",
    "不能申请",
    "禁止行为",
    "虚假材料",
    "实名登记",
    "登记材料",
    "国籍登记",
    "适航证",
    "特许飞行证",
    "登记注销",
    "登记信息变更",
    "信息更新",
    "补发",
    "运营合格证",
    "运营规范",
    "运行人",
    "运营人",
    "责任保险",
    "信息报送",
    "年度运营报告",
    "有效期",
    "更新",
    "续期",
    "运营许可",
    "持续适航",
    "维修管理",
    "维修记录",
    "维修放行",
    "飞行前准备",
    "缺陷",
    "故障",
    "失效",
    "通信链路",
    "电池储备",
    "维修责任人",
    "处罚",
    "罚款",
    "吊销",
    "撤销",
    "注销",
    "失效",
    "停飞",
    "停止飞行",
    "作弊",
    "代考",
    "欺骗",
    "贿赂",
    "夜间飞行",
    "视距内运行",
    "超视距运行",
    "暂停报名考试资格",
    "停止报名考试资格",
    "训练机构",
)

NAVIGATION_LIGHT_QUERY_PATTERN = re.compile(
    r"航行灯"
    r"|(?:飞机|飞行器|航空器|翼尖|尾翼).{0,32}(?:灯光|红灯|绿灯|白灯|尾灯|红.{0,4}绿|绿.{0,4}红)"
    r"|(?:灯光|红灯|绿灯|白灯|尾灯|红.{0,4}绿|绿.{0,4}红).{0,32}(?:飞机|飞行器|航空器|翼尖|尾翼)"
)
NAVIGATION_LIGHT_OTHER_CASE_GROUPS = {
    "same": ("同向", "顺向"),
    "away": ("背向", "反向"),
    "overtake": ("追越",),
    "cross": ("交叉", "侧向", "侧面"),
    "rear": ("后方",),
}
NAVIGATION_LIGHT_CLAIM_MARKERS = (
    "灯",
    "红",
    "绿",
    "白",
    "看到",
    "看见",
    "观察",
    "可见",
    "呈现",
    "显示",
    "尾部",
    "机尾",
    "正面",
    "侧面",
    "后方",
    "对着",
    "朝向",
    "说明",
    "判断",
)
NAVIGATION_LIGHT_BOUNDARY_MARKERS = (
    "误以为",
    "不得",
    "不要由",
    "不能由",
    "不能据此",
    "不应推导",
    "不代表",
    "不等于",
    "无法确认",
    "没有直接证据",
    "未检索到",
    "不把模型推断",
)
NAVIGATION_LIGHT_EXCLUSIVE_MARKERS = (
    "只会",
    "只能",
    "必然",
    "一定",
    "永远",
    "绝不会",
    "仅可能",
)
NAVIGATION_LIGHT_EVIDENCE_NOTICE = (
    "当前知识库没有检索到足以确认该相对航向下必然可见灯光的直接证据，"
    "因此不把模型推断作为确定结论。"
)
NAVIGATION_LIGHT_STANDARD_CONFIGURATION = (
    "按照国际通用规则，左翼尖为红色、右翼尖为绿色、尾部为白色。"
)
NAVIGATION_LIGHT_SAFE_AVOIDANCE = (
    "相向接近存在碰撞风险，应及时采取避让措施并持续观察。"
)
NAVIGATION_LIGHT_SPECIFIC_ACTION_PATTERNS = {
    "directional_turn": re.compile(
        r"(?:向|往)?[左右](?:侧)?(?:转弯|转向|避让|机动|偏航|转|"
        r"(?:调整|改变|修正)(?:飞行)?航向)"
    ),
    "vertical_maneuver": re.compile(
        r"上升|爬升|下降|下沉|(?:改变|调整|降低|升高).{0,6}(?:飞行)?高度"
    ),
    "speed_change": re.compile(
        r"减速|降低(?:飞行)?速度|减小(?:飞行)?速度|放慢速度"
    ),
    "altitude_separation": re.compile(
        r"(?:保持|拉开|增加|建立|确保).{0,8}(?:安全)?高度差"
    ),
    "radio_coordination": re.compile(
        r"(?:无线电|甚高频|VHF).{0,32}(?:通报|报告|呼叫|联络|通信|协调|沟通)"
        r"|(?:通报|报告|呼叫|联络|通信|协调|沟通).{0,32}(?:无线电|甚高频|VHF)",
        re.IGNORECASE,
    ),
}
NAVIGATION_LIGHT_ACTION_EVIDENCE_ANCHOR = re.compile(
    r"航行灯|灯光|相向|对头|碰撞|避让"
)
NAVIGATION_LIGHT_SPECIFIC_SYSTEM_PATTERN = re.compile(
    r"雷达|ADS[\s-]?B|TCAS|ACAS|防撞灯|频闪灯",
    re.IGNORECASE,
)
NAVIGATION_LIGHT_VIEW_CASE_PATTERNS = {
    "rear_view": re.compile(
        r"(?:看到|看见|观察到|可见|呈现|显示).{0,18}(?:尾部|机尾|后侧)"
    ),
    "side_view": re.compile(
        r"(?:看到|看见|观察到|可见|呈现|显示).{0,24}(?:侧方|侧面|侧向)"
    ),
}
NAVIGATION_LIGHT_RISK_ESCALATION_PATTERN = re.compile(
    r"(?:碰撞|相撞|危险|风险).{0,12}(?:最高|最大|最危险|极高)"
    r"|(?:最高|最大|最危险|极高).{0,12}(?:碰撞|相撞|危险|风险)"
    r"|紧急危险信号"
    r"|(?:明确|强烈)警告信号"
    r"|无论.{0,8}(?:距离|多远).{0,16}(?:碰撞|相撞|危险|风险|避让)"
)

TEXTBOOK_DUPLICATION_QUERY_PATTERN = re.compile(
    r"重复|重合|雷同|去重|相同(?:表述|内容|说法|事实)"
)
NAVIGATION_LIGHT_UNSUPPORTED_COLOR_SEQUENCE_PATTERN = re.compile(
    r"绿左右红|左绿右红|右绿左红"
)
NAVIGATION_LIGHT_ICAO_ATTRIBUTION_PATTERN = re.compile(
    r"(?:根据|依据|按照)?\s*"
    r"(?:国际民航组织(?:[（(]\s*ICAO\s*[）)])?|ICAO)"
    r"(?:\s*及\s*各国航空法规)?(?:的)?(?:统一)?(?:规定|规则|要求)?[，,:：]?",
    re.IGNORECASE,
)
NAVIGATION_LIGHT_GENERIC_REGULATION_ATTRIBUTION_PATTERN = re.compile(
    r"(?:根据|依据|按照)?\s*各国航空法规"
    r"(?:的)?(?:统一)?(?:规定|规则|要求)?[，,:：]?"
)
NAVIGATION_LIGHT_NAMED_DOCUMENT_PATTERN = re.compile(
    r"(?:根据|依据|按照)?\s*《([^》]+)》"
    r"(?:\s*(?:相关)?(?:规定|规则|要求))?"
)
NAVIGATION_LIGHT_WING_OBSERVER_QUALIFIER_PATTERN = re.compile(
    r"[（(][^）)\n]{0,24}(?:观察者|从机头方向看)[^）)\n]{0,24}[）)]"
)


# AP-45-AA-2017-03《实名制登记管理规定》入库后，实名登记类问法出现"属性维度"分叉：
# 登记信息项由 CCAR-92 §92.205（现行）权威回答，但重量阈值/登记号格式/标志尺寸/二维码
# 这类问法各有归属（现行阈值已被 CCAR §92.201 取消"全部登记"、登记号现行为 §92.211 8位、
# 尺寸/二维码明细仅 AP-45 有）。裸"实名登记"→§92.205 的模板/注入会把这些属性问法一并
# 劫持成"登记信息项"答非所问（pool_0731 实测：问"多少克"却答信息项）。以下标记命中时，
# §92.205 信息项规则让位给检索+LLM（现行冲突项 CCAR 自然词法命中，AP-45 独有项直接检索）。
RNR_SPECIFIC_ATTRIBUTE_MARKERS = (
    "多少克", "克以上", "250克", "起飞重量",
    "几位", "多少位", "编号范围", "登记号格式", "什么格式",
    "多大", "厘米", "粘贴牌", "尺寸",
    "二维码",
)


def asks_rnr_specific_attribute(question: str) -> bool:
    q = question or ""
    return any(term in q for term in RNR_SPECIFIC_ATTRIBUTE_MARKERS)


def caac_practical_score_claim_hit_count(text: str) -> int:
    value = text or ""
    return sum(1 for pattern in CAAC_PRACTICAL_SCORE_CLAIM_PATTERNS if re.search(pattern, value))


def contains_caac_practical_score_claim(text: str) -> bool:
    return caac_practical_score_claim_hit_count(text) >= 2


def is_regulation_gate_question(question: str) -> bool:
    q = question or ""
    return any(term in q for term in REGULATION_GATE_QUESTION_TERMS) and any(
        term in q for term in REGULATION_GATE_LICENSE_TERMS
    )


def is_regulation_eligibility_question(question: str) -> bool:
    q = question or ""
    if "训练机构" in q and any(term in q for term in ("暂停报名考试资格", "停止报名考试资格")):
        return True
    if any(term in q for term in ("维修记录", "维修放行")):
        return True
    if any(term in q for term in ("运营合格证", "国籍登记", "年度运营报告", "故障", "失效", "缺陷")) and any(
        term in q for term in ("什么时候", "多久", "多久内", "几日内", "工作日", "保存多久", "保存多长时间", "提前")
    ):
        return True
    return any(term in q for term in REGULATION_ELIGIBILITY_TERMS) and any(
        term in q for term in REGULATION_GATE_LICENSE_TERMS + ("法规", "规定", "规则", "CCAR", "92部")
    )


def is_caac_practical_score_verification(question: str) -> bool:
    """Detect the known unsupported CAAC practical-score provenance claim."""
    q = question or ""
    if not contains_caac_practical_score_claim(q):
        return False
    verification_markers = (
        "来源",
        "出处",
        "官方",
        "原文",
        "文号",
        "依据",
        "对吗",
        "是否",
        "准确",
        "核实",
        "查过",
        "真假",
    )
    return any(marker in q for marker in verification_markers)


def caac_practical_score_claim_supported(ctx_result: dict) -> bool:
    context = ctx_result.get("context", "") or ""
    return caac_practical_score_claim_hit_count(context) == len(CAAC_PRACTICAL_SCORE_CLAIM_PATTERNS)


def build_caac_practical_score_guard_answer(question: str, ctx_result: dict) -> str | None:
    if not is_caac_practical_score_verification(question):
        return None
    if caac_practical_score_claim_supported(ctx_result):
        return None
    return (
        "不能把这条分值当成已核实事实。当前知识库没有检索到可支持"
        "“起飞10分、悬停20分、航线飞行30分、应急处置20分、降落20分”"
        "的官方原文、文号或条款。\n\n"
        "现有命中的资料只涉及实操动作、训练要求或相关法规片段，"
        "不足以证明这套评分分布。"
    )


def build_caac_practical_score_output_guard(answer: str, ctx_result: dict) -> str | None:
    """Remove the unsupported practical-score split even for non-verification asks."""
    if not contains_caac_practical_score_claim(answer):
        return None
    if caac_practical_score_claim_supported(ctx_result):
        return None
    return (
        "已删除未证实的实操分值拆分。当前知识库没有检索到可支持"
        "“起飞10分、悬停20分、航线飞行30分、应急处置20分、降落20分”"
        "的官方原文、文号或条款，因此不能把这套分项分值作为考试事实输出。\n\n"
        "当前可依据的内部资料只支持：考试包含理论考试、综合问答、实践飞行；"
        "超视距还涉及地面站预规划、重规划和应急返航。实践飞行应关注对应等级的"
        "飞行模式、悬停、水平360°慢转、水平8字、航向/位移/高度误差和速度要求。"
    )


def _navigation_light_case_groups(text: str) -> set[str]:
    value = text or ""
    groups = {
        group
        for group, terms in NAVIGATION_LIGHT_OTHER_CASE_GROUPS.items()
        if any(term in value for term in terms)
    }
    groups.update(
        group
        for group, pattern in NAVIGATION_LIGHT_VIEW_CASE_PATTERNS.items()
        if pattern.search(value)
    )
    return groups


def _navigation_light_outcomes(text: str) -> set[str]:
    value = re.sub(r"[\s*_`]+", "", text or "")
    outcomes = set()
    if re.search(r"左.{0,4}红.{0,8}右.{0,4}绿", value):
        outcomes.add("left_red_right_green")
    if re.search(r"右.{0,4}红.{0,8}左.{0,4}绿", value):
        outcomes.add("right_red_left_green")
    if "白" in value and "灯" in value:
        outcomes.add("white_light")
    if "红" in value and "灯" in value:
        outcomes.add("red_light")
    if "绿" in value and "灯" in value:
        outcomes.add("green_light")
    if "尾灯" in value or re.search(r"尾(?:部|翼)?.{0,6}灯", value):
        outcomes.add("tail_light")
    return outcomes


def _is_question_bank_option(text: str) -> bool:
    value = (text or "").strip()
    value = re.sub(r"^(?:[-*+]\s*)", "", value)
    value = value.replace("**", "")
    return bool(
        re.match(r"^(?:选项\s*[:：]|[A-CＡ-Ｃ]\s*[.、:：)）])", value)
        or (
            "选项" in value
            and any(marker in value for marker in ("A.", "A、", "A：", "Ａ."))
        )
    )


def _split_navigation_light_segments(text: str) -> list[str]:
    return [
        segment
        for line in (text or "").splitlines()
        for segment in re.split(r"(?<=[。！？!?；;])", line)
        if segment.strip()
    ]


def _is_navigation_light_other_case_claim(text: str) -> bool:
    if not _navigation_light_case_groups(text):
        return False
    if _is_question_bank_option(text):
        return False
    if any(marker in text for marker in NAVIGATION_LIGHT_BOUNDARY_MARKERS):
        return False
    return any(marker in text for marker in NAVIGATION_LIGHT_CLAIM_MARKERS)


def _navigation_light_context_supports_claim(claim: str, ctx_result: dict) -> bool:
    claim_groups = _navigation_light_case_groups(claim)
    claim_outcomes = _navigation_light_outcomes(claim)
    if not claim_groups or not claim_outcomes:
        return False

    claim_is_exclusive = any(
        marker in claim for marker in NAVIGATION_LIGHT_EXCLUSIVE_MARKERS
    )
    context = (ctx_result or {}).get("context", "") or ""
    for segment in _split_navigation_light_segments(context):
        if _is_question_bank_option(segment) or "参考答案" in segment:
            continue
        if segment.rstrip().endswith(("?", "？")):
            continue
        if not (claim_groups & _navigation_light_case_groups(segment)):
            continue
        evidence_outcomes = _navigation_light_outcomes(segment)
        if not claim_outcomes.issubset(evidence_outcomes):
            continue
        if claim_is_exclusive and not any(
            marker in segment for marker in NAVIGATION_LIGHT_EXCLUSIVE_MARKERS
        ):
            continue
        return True
    return False


def _context_directly_mentions(ctx_result: dict, *terms: str) -> bool:
    context = (ctx_result or {}).get("context", "") or ""
    return all(term in context for term in terms)


def _navigation_light_specific_action_groups(text: str) -> set[str]:
    value = text or ""
    return {
        action
        for action, pattern in NAVIGATION_LIGHT_SPECIFIC_ACTION_PATTERNS.items()
        if pattern.search(value)
    }


def _navigation_light_context_supports_actions(claim: str, ctx_result: dict) -> bool:
    claim_actions = _navigation_light_specific_action_groups(claim)
    if not claim_actions:
        return True

    context_segments = _navigation_light_evidence_segments(ctx_result)
    return all(
        any(
            NAVIGATION_LIGHT_SPECIFIC_ACTION_PATTERNS[action].search(segment)
            for segment in context_segments
        )
        for action in claim_actions
    )


def _navigation_light_evidence_segments(ctx_result: dict) -> list[str]:
    return [
        segment
        for segment in _split_navigation_light_segments(
            (ctx_result or {}).get("context", "") or ""
        )
        if NAVIGATION_LIGHT_ACTION_EVIDENCE_ANCHOR.search(segment)
    ]


def _navigation_light_requested_case(question: str) -> str:
    value = question or ""
    if any(term in value for term in ("同向", "顺向")):
        return "同向飞行"
    if any(term in value for term in ("背向", "反向", "后方")):
        return "背向飞行"
    if "追越" in value:
        return "追越"
    if any(term in value for term in ("交叉", "侧向", "侧面")):
        return "交叉或侧向飞行"
    return "该相对航向"


def _navigation_light_evidence_boundary_answer(question: str) -> str:
    requested_case = _navigation_light_requested_case(question)
    return (
        f"{NAVIGATION_LIGHT_STANDARD_CONFIGURATION}\n\n"
        f"当前知识库没有检索到足以确认{requested_case}时必然可见灯光的直接证据，"
        "因此不能给出确定的灯光组合，也不把模型推断作为确定结论。"
    )


def _navigation_light_context_supports_systems(ctx_result: dict) -> bool:
    return any(
        NAVIGATION_LIGHT_SPECIFIC_SYSTEM_PATTERN.search(segment)
        for segment in _navigation_light_evidence_segments(ctx_result)
    )


def _strip_unsupported_navigation_light_attribution(
    segment: str,
    ctx_result: dict,
) -> str:
    context = (ctx_result or {}).get("context", "") or ""
    cleaned = segment

    if not re.search(r"ICAO|国际民航组织", context, re.IGNORECASE):
        cleaned = NAVIGATION_LIGHT_ICAO_ATTRIBUTION_PATTERN.sub("", cleaned)
    if "各国航空法规" not in context:
        cleaned = NAVIGATION_LIGHT_GENERIC_REGULATION_ATTRIBUTION_PATTERN.sub(
            "",
            cleaned,
        )

    def keep_supported_document(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1).strip() in context else ""

    cleaned = NAVIGATION_LIGHT_NAMED_DOCUMENT_PATTERN.sub(
        keep_supported_document,
        cleaned,
    )
    if (
        "翼" in cleaned
        and any(color in cleaned for color in ("红", "绿"))
        and not NAVIGATION_LIGHT_WING_OBSERVER_QUALIFIER_PATTERN.search(context)
    ):
        cleaned = NAVIGATION_LIGHT_WING_OBSERVER_QUALIFIER_PATTERN.sub("", cleaned)

    cleaned = re.sub(r"^[，,：:\s]+", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned)


def sanitize_navigation_light_answer(
    question: str,
    answer: str,
    ctx_result: dict | None = None,
) -> str:
    """Keep model enrichment while removing navigation-light claims outside KG evidence."""
    if not NAVIGATION_LIGHT_QUERY_PATTERN.search(question or ""):
        return answer

    original = answer or ""
    explicit_groups = _navigation_light_case_groups(question)
    explicit_other_case = bool(explicit_groups)
    removed_requested_case = False
    removed_specific_avoidance = False
    changed = False
    cleaned_lines = []

    for line in original.splitlines():
        kept_segments = []
        for segment in re.split(r"(?<=[。！？!?；;])", line):
            if not segment.strip():
                continue

            bounded_segment = _strip_unsupported_navigation_light_attribution(
                segment,
                ctx_result or {},
            )
            if bounded_segment != segment:
                changed = True
                segment = bounded_segment
                if not segment.strip():
                    continue

            if re.search(
                r"同时.{0,18}红.{0,10}绿.{0,10}白.{0,30}(?:正对|相向)"
                r"|同时.{0,18}白.{0,10}红.{0,10}绿.{0,30}(?:正对|相向)",
                segment,
            ) and not _context_directly_mentions(
                ctx_result or {}, "红", "绿", "白", "相向"
            ):
                changed = True
                continue

            if NAVIGATION_LIGHT_UNSUPPORTED_COLOR_SEQUENCE_PATTERN.search(segment):
                evidence = "\n".join(
                    (question or "", (ctx_result or {}).get("context", "") or "")
                )
                unsupported_sequences = {
                    match.group(0)
                    for match in NAVIGATION_LIGHT_UNSUPPORTED_COLOR_SEQUENCE_PATTERN.finditer(
                        segment
                    )
                    if match.group(0) not in evidence
                }
                if unsupported_sequences:
                    changed = True
                    continue

            if (
                _navigation_light_specific_action_groups(segment)
                and not _navigation_light_context_supports_actions(
                    segment,
                    ctx_result or {},
                )
            ):
                changed = True
                removed_specific_avoidance = True
                continue

            if (
                NAVIGATION_LIGHT_SPECIFIC_SYSTEM_PATTERN.search(segment)
                and not _navigation_light_context_supports_systems(ctx_result or {})
            ):
                changed = True
                continue

            if (
                NAVIGATION_LIGHT_RISK_ESCALATION_PATTERN.search(segment)
                and not any(
                    NAVIGATION_LIGHT_RISK_ESCALATION_PATTERN.search(evidence)
                    for evidence in _navigation_light_evidence_segments(
                        ctx_result or {}
                    )
                )
            ):
                changed = True
                removed_specific_avoidance = True
                continue

            if re.search(
                r"(?:法规|规章).{0,12}要求.{0,40}(?:夜间|超视距).{0,30}(?:灯|灯光)",
                segment,
            ) and not _context_directly_mentions(ctx_result or {}, "法规", "超视距", "灯"):
                changed = True
                continue

            if _is_navigation_light_other_case_claim(segment):
                claim_groups = _navigation_light_case_groups(segment)
                directly_asked = bool(claim_groups & explicit_groups)
                directly_supported = _navigation_light_context_supports_claim(
                    segment,
                    ctx_result or {},
                )
                if not explicit_other_case or not directly_asked or not directly_supported:
                    changed = True
                    if explicit_other_case and directly_asked and not directly_supported:
                        removed_requested_case = True
                    continue

            kept_segments.append(segment)

        cleaned_line = "".join(kept_segments).rstrip()
        if cleaned_line.strip() in {"-", "*", "+"}:
            changed = True
            continue
        cleaned_lines.append(cleaned_line)

    if not changed:
        return original

    if removed_requested_case:
        return _navigation_light_evidence_boundary_answer(question)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if removed_specific_avoidance and NAVIGATION_LIGHT_SAFE_AVOIDANCE not in cleaned:
        cleaned = f"{cleaned}\n\n{NAVIGATION_LIGHT_SAFE_AVOIDANCE}".strip()

    return cleaned or NAVIGATION_LIGHT_EVIDENCE_NOTICE


def governance_response_fields(ctx_result: dict | None = None) -> dict[str, Any]:
    """Normalize backward-compatible governance fields for API responses."""
    ctx_result = ctx_result or {}
    conflict_ids = sorted(
        {
            str(conflict_id)
            for conflict_id in ctx_result.get("conflict_ids", [])
            if conflict_id
        }
    )
    deduplicated_sources = ctx_result.get("deduplicated_sources") or []
    if not isinstance(deduplicated_sources, list):
        deduplicated_sources = []
    return {
        "review_required": bool(conflict_ids),
        "conflict_ids": conflict_ids,
        "deduplicated_sources": deduplicated_sources,
    }


def _normalized_comparison_text(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).lower()


def _textbook_source_label(source: dict[str, Any]) -> str:
    raw_name = source_name(source)
    title = re.sub(r"\.txt$", "", raw_name)
    title = re.sub(r"^(?:无人机理论书籍|理论书籍)_", "", title)
    title = title.replace("_", "·")
    label = f"《{title}》" if title else "未命名教材"
    page_start = source.get("pdf_page_start")
    page_end = source.get("pdf_page_end")
    if page_start is not None:
        page = str(page_start)
        if page_end is not None and page_end != page_start:
            page += f"-{page_end}"
        label += f"（PDF第{page}页）"
    return label


def _is_textbook_source(source: dict[str, Any]) -> bool:
    doc_name = source_name(source)
    chunk_id = str(source.get("chunk_id") or "")
    content_type = str(source.get("content_type") or "")
    return bool(
        doc_name.startswith("无人机理论书籍_")
        or chunk_id.startswith("textbook:")
        or "textbook" in content_type.lower()
    )


def build_textbook_deduplication_answer(
    question: str,
    ctx_result: dict | None,
) -> str | None:
    """Answer explicit overlap checks from governed cross-book evidence."""
    if not TEXTBOOK_DUPLICATION_QUERY_PATTERN.search(question or ""):
        return None

    requested_titles = re.findall(r"《([^》]{2,})》", question or "")
    quoted_statements = re.findall(r"[“\"]([^”\"]{8,})[”\"]", question or "")
    matches: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for group in governance_response_fields(ctx_result)["deduplicated_sources"]:
        if not isinstance(group, dict):
            continue
        representative = group.get("representative_source") or {}
        supporting = [
            source
            for source in (group.get("supporting_sources") or [])
            if isinstance(source, dict)
        ]
        if not representative or not supporting:
            continue

        all_sources = [representative, *supporting]
        if not all(_is_textbook_source(source) for source in all_sources):
            continue
        if len({source_name(source) for source in all_sources}) < 2:
            continue
        normalized_docs = [
            _normalized_comparison_text(source_name(source))
            for source in all_sources
        ]
        if requested_titles and not all(
            any(
                _normalized_comparison_text(title) in doc
                for doc in normalized_docs
            )
            for title in requested_titles
        ):
            continue

        if quoted_statements:
            normalized_quotes = [
                _normalized_comparison_text(source.get("evidence_quote"))
                for source in all_sources
            ]
            if not any(
                any(
                    _normalized_comparison_text(statement) in quote
                    for quote in normalized_quotes
                )
                for statement in quoted_statements
            ):
                continue
        matches.append((representative, supporting))

    if not matches:
        return None

    lines = ["是。知识库已确认存在跨教材的相同事实表述："]
    for representative, supporting in matches[:5]:
        quote = str(representative.get("evidence_quote") or "").strip("。；; ")
        source_labels = "、".join(
            _textbook_source_label(source)
            for source in [representative, *supporting]
        )
        detail = f"- {source_labels}"
        if quote:
            detail += f"均有表述：“{quote}”。"
        else:
            detail += "记录了同一事实。"
        lines.append(detail)
    lines.append(
        "系统仅在回答层保留一条代表事实，并把其他教材登记为已核验辅助来源；"
        "原始文本、页码和来源记录均未删除。"
    )
    return "\n".join(lines)


def deduplicate_response_sources(sources: list[dict] | None) -> list[dict]:
    """Expose each SQLite-backed chunk once without changing prompt evidence."""
    result = []
    seen_chunk_ids = set()
    for source in sources or []:
        if not isinstance(source, dict):
            result.append(source)
            continue
        chunk_id = str(source.get("chunk_id") or "")
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        result.append(source)
    return result


def build_conflict_review_answer(ctx_result: dict) -> str | None:
    """Return a non-adjudicating answer for unresolved governed claims."""
    conflict_ids = governance_response_fields(ctx_result)["conflict_ids"]
    if not conflict_ids:
        return None
    return (
        "本次检索命中了尚未裁决的知识冲突，系统不会自动选择其中任一版本，"
        "也不会用外部搜索或模型推断替代人工决定。相关冲突已进入人工审核。\n\n"
        f"冲突编号：{'、'.join(conflict_ids)}"
    )


def build_regulation_gate_answer(question: str, ctx_result: dict) -> str | None:
    """Use grounded clause synthesis for CAAC license crime/background questions."""
    if not is_regulation_gate_question(question):
        return None
    source_map = {
        (src.get("chunk_id") or ""): src
        for src in (ctx_result or {}).get("sources", [])
    }
    art_9255 = source_map.get("regulation:ccar_92:art_092_055")
    art_9257 = source_map.get("regulation:ccar_92:art_092_057")
    if not art_9255 and not art_9257:
        return None

    q = question or ""
    source_9255 = f"【来源{art_9255.get('seq')}】" if art_9255 else ""
    source_9257 = f"【来源{art_9257.get('seq')}】" if art_9257 else ""
    asks_clause = any(term in q for term in ("原文", "条文", "具体原文", "第92.55条"))
    asks_statement_vs_proof = any(term in q for term in ("一回事", "一样吗", "区别", "声明", "证明"))
    asks_drink_drive = any(term in q for term in ("醉驾", "酒驾", "危险驾驶"))

    if asks_clause and art_9255:
        lines = [
            "CCAR-92部第92.55条(c)款写的是："
            "“近5年内无因危害国家安全、公共安全或者侵犯公民人身权利、"
            "扰乱公共秩序的故意犯罪受到刑事处罚的记录。”"
            f"{source_9255}"
        ]
        if art_9257:
            lines.append(
                "同时，第92.57条(b)(3)要求提交的是近5年内无上述故意犯罪刑事处罚记录的声明，"
                f"不是法规明文要求的通用无犯罪记录证明{source_9257}"
            )
        return "\n\n".join(lines)

    lines = []
    if art_9255:
        lines.append(
            "1. 报考条件：第92.55条(c)要求申请人近5年内没有因危害国家安全、公共安全、"
            "侵犯公民人身权利或者扰乱公共秩序的故意犯罪而受到刑事处罚的记录"
            f"{source_9255}。"
        )
    if asks_drink_drive and art_9255:
        lines.append(
            "2. 关于酒驾/醉驾：从条文含义看，若醉驾已经构成危险驾驶罪，且在近5年内因此受到刑事处罚，"
            f"通常会落入上述限制{source_9255}；单纯酒驾行政处罚不等于该条款所说的刑事处罚。"
        )
    if art_9257:
        statement_line = (
            "3. 材料要求：第92.57条(b)(3)要求提交的是近5年内无上述故意犯罪刑事处罚记录的声明，"
            f"不是法规明文要求提交公安机关出具的通用“无犯罪记录证明”{source_9257}。"
        )
        if asks_statement_vs_proof:
            statement_line = (
                "3. 声明和证明不是一回事：第92.57条(b)(3)写的是申请人提交相关声明，"
                f"法规文本没有写必须提交公安机关出具的通用“无犯罪记录证明”{source_9257}。"
            )
        lines.append(statement_line)
    if not lines:
        return None
    lines.append("4. 结论：这类问题应直接按 CCAR-92 部第92.55条和第92.57条理解，不需要再跳到外部网页找依据。")
    return "\n\n".join(lines)


def build_regulation_eligibility_answer(question: str, ctx_result: dict, rag_store: Any) -> str | None:
    if not is_regulation_eligibility_question(question):
        return None
    ctx_result = ctx_result or {}
    # A deterministic template must obey the same quarantine decision as the
    # prompt path. It cannot pick a version while any conflict remains visible,
    # even when that conflict was isolated from the final prose.
    if (
        ctx_result.get("review_required")
        or ctx_result.get("conflict_ids")
        or ctx_result.get("isolated_conflict_ids")
    ):
        return None
    # 07-13: 原句词法保底命中强题库原题（≥40 分近逐字，如酒精药物一年题 206 分/
    # 实名登记250克题 157 分）时整个模板族让位——模板绕过 LLM，会把题库原题答成
    # CCAR 通用条款（张冠李戴）。规章类问法的原句赢家通常就是政策法规 chunk 本身，
    # 此豁免不触发、模板照常。
    _lex_doc = (ctx_result.get("raw_lexical_guarantee") or {}).get("doc_name") or ""
    if _lex_doc and not _lex_doc.startswith("政策法规_"):
        return None
    q = question or ""
    blocked_ids = {
        str(chunk_id)
        for field in (
            "excluded_exercise_chunk_ids",
            "quarantined_conflict_chunk_ids",
        )
        for chunk_id in ctx_result.get(field) or []
        if chunk_id
    }
    blocked_ids.update(
        str(source.get("chunk_id") or "")
        for source in ctx_result.get("superseded_sources") or []
        if isinstance(source, dict) and source.get("chunk_id")
    )
    blocked_ids.update(
        str(source.get("chunk_id") or "")
        for source in ctx_result.get("sources") or []
        if isinstance(source, dict)
        and source.get("chunk_id")
        and str(source.get("content_type") or "").lower() == "exercise"
    )
    source_map = {
        (src.get("chunk_id") or ""): src
        for src in ctx_result.get("sources", [])
        if (src.get("chunk_id") or "") not in blocked_ids
    }
    available_ids = set(source_map.keys())
    fallback_ids = [
        "regulation:ccar_92:art_092_055",
        "regulation:ccar_92:art_092_057",
        "regulation:ccar_92:art_092_099",
        "regulation:ccar_92:art_092_101",
        "regulation:ccar_92:art_092_205",
        "regulation:ccar_92:art_092_207",
        "regulation:ccar_92:art_092_209",
        "regulation:ccar_92:art_092_215",
        "regulation:ccar_92:art_092_217",
        "regulation:ccar_92:art_092_223",
        "regulation:ccar_92:art_092_453",
        "regulation:ccar_92:art_092_455",
        "regulation:ccar_92:art_092_467",
        "regulation:ccar_92:art_092_471",
        "regulation:ccar_92:art_092_067",
        "regulation:ccar_92:art_092_095",
        "regulation:ccar_92:art_092_1005",
        "regulation:ccar_92:art_092_1007",
        "regulation:ccar_92:art_092_1009",
        "regulation:ccar_92:art_092_1013",
        "regulation:ccar_92:art_092_1015",
        "regulation:ccar_92:art_092_665",
        "regulation:ccar_92:art_092_603",
        "regulation:ccar_92:art_092_645",
        "regulation:ccar_92:art_092_647",
        "regulation:ccar_92:art_092_651",
        "regulation:ccar_92:art_092_655",
        "regulation:ccar_92:art_092_659",
        "regulation:ccar_92:art_092_663",
        "regulation:ccar_92:art_092_669",
        "regulation:ccar_92:art_092_671",
        "regulation:ccar_92:art_092_673",
        "regulation:ccar_92:art_092_311",
        "regulation:ccar_92:art_092_619",
        "regulation:ccar_92:art_092_621",
        "regulation:ccar_92:art_092_623",
        "regulation:ccar_92:art_092_707",
        "regulation:ccar_92:art_092_709",
        "regulation:ccar_92:art_092_631",
        "regulation:ccar_92:art_092_633",
        "regulation:uas_training_org_spec:clause_014_002_001",
        "regulation:uas_training_org_spec:clause_014_002_002",
        "regulation:uas_training_org_spec:clause_014_002_003",
    ]
    try:
        fetched = rag_store.get_chunks_batch(fallback_ids)
    except Exception:
        fetched = []
    fetched_ids = {
        str(item.get("chunk_id") or "")
        for item in fetched
        if item.get("chunk_id") and str(item.get("chunk_id")) not in blocked_ids
    }
    if fetched_ids:
        try:
            schema_state = rag_store.governance_schema_state()
            if schema_state == "ready":
                governance = rag_store.get_chunk_governance(sorted(fetched_ids))
                if (
                    set(governance.get("by_chunk") or {}) != fetched_ids
                    or set(governance.get("unresolved_conflicts") or {}) != fetched_ids
                ):
                    fetched_ids = set()
                else:
                    provenance = governance.get("provenance") or {}
                    unresolved = governance.get("unresolved_conflicts") or {}
                    fetched_ids = {
                        chunk_id
                        for chunk_id in fetched_ids
                        if str((provenance.get(chunk_id) or {}).get("content_type") or "").lower()
                        != "exercise"
                        and not unresolved.get(chunk_id)
                    }
            elif schema_state != "legacy":
                fetched_ids = set()
        except Exception:
            # Template fallback is optional. A governance read failure must
            # disable it rather than silently restoring a quarantined clause.
            fetched_ids = set()
    available_ids.update(fetched_ids)
    def cite(chunk_id: str) -> str:
        src = source_map.get(chunk_id)
        if src:
            return f"【来源{src.get('seq')}】"
        fallback_labels = {
            "regulation:ccar_92:art_092_055": "（CCAR-92部第92.55条）",
            "regulation:ccar_92:art_092_057": "（CCAR-92部第92.57条）",
            "regulation:ccar_92:art_092_099": "（CCAR-92部第92.99条）",
            "regulation:ccar_92:art_092_101": "（CCAR-92部第92.101条）",
            "regulation:ccar_92:art_092_205": "（CCAR-92部第92.205条）",
            "regulation:ccar_92:art_092_207": "（CCAR-92部第92.207条）",
            "regulation:ccar_92:art_092_209": "（CCAR-92部第92.209条）",
            "regulation:ccar_92:art_092_215": "（CCAR-92部第92.215条）",
            "regulation:ccar_92:art_092_217": "（CCAR-92部第92.217条）",
            "regulation:ccar_92:art_092_223": "（CCAR-92部第92.223条）",
            "regulation:ccar_92:art_092_453": "（CCAR-92部第92.453条）",
            "regulation:ccar_92:art_092_455": "（CCAR-92部第92.455条）",
            "regulation:ccar_92:art_092_467": "（CCAR-92部第92.467条）",
            "regulation:ccar_92:art_092_471": "（CCAR-92部第92.471条）",
            "regulation:ccar_92:art_092_067": "（CCAR-92部第92.67条）",
            "regulation:ccar_92:art_092_095": "（CCAR-92部第92.95条）",
            "regulation:ccar_92:art_092_1005": "（CCAR-92部第92.1005条）",
            "regulation:ccar_92:art_092_1007": "（CCAR-92部第92.1007条）",
            "regulation:ccar_92:art_092_1009": "（CCAR-92部第92.1009条）",
            "regulation:ccar_92:art_092_1013": "（CCAR-92部第92.1013条）",
            "regulation:ccar_92:art_092_1015": "（CCAR-92部第92.1015条）",
            "regulation:ccar_92:art_092_665": "（CCAR-92部第92.665条）",
            "regulation:ccar_92:art_092_603": "（CCAR-92部第92.603条）",
            "regulation:ccar_92:art_092_645": "（CCAR-92部第92.645条）",
            "regulation:ccar_92:art_092_647": "（CCAR-92部第92.647条）",
            "regulation:ccar_92:art_092_651": "（CCAR-92部第92.651条）",
            "regulation:ccar_92:art_092_655": "（CCAR-92部第92.655条）",
            "regulation:ccar_92:art_092_659": "（CCAR-92部第92.659条）",
            "regulation:ccar_92:art_092_663": "（CCAR-92部第92.663条）",
            "regulation:ccar_92:art_092_669": "（CCAR-92部第92.669条）",
            "regulation:ccar_92:art_092_671": "（CCAR-92部第92.671条）",
            "regulation:ccar_92:art_092_673": "（CCAR-92部第92.673条）",
            "regulation:ccar_92:art_092_311": "（CCAR-92部第92.311条）",
            "regulation:ccar_92:art_092_619": "（CCAR-92部第92.619条）",
            "regulation:ccar_92:art_092_621": "（CCAR-92部第92.621条）",
            "regulation:ccar_92:art_092_623": "（CCAR-92部第92.623条）",
            "regulation:ccar_92:art_092_667": "（CCAR-92部第92.667条）",
            "regulation:ccar_92:art_092_679": "（CCAR-92部第92.679条）",
            "regulation:ccar_92:art_092_687": "（CCAR-92部第92.687条）",
            "regulation:ccar_92:art_092_695": "（CCAR-92部第92.695条）",
            "regulation:ccar_92:art_092_697": "（CCAR-92部第92.697条）",
            "regulation:ccar_92:art_092_701": "（CCAR-92部第92.701条）",
            "regulation:ccar_92:art_092_707": "（CCAR-92部第92.707条）",
            "regulation:ccar_92:art_092_709": "（CCAR-92部第92.709条）",
            "regulation:ccar_92:art_092_631": "（CCAR-92部第92.631条）",
            "regulation:ccar_92:art_092_633": "（CCAR-92部第92.633条）",
            "regulation:uas_training_org_spec:clause_014_002_001": "（训练机构规范14.2.1）",
            "regulation:uas_training_org_spec:clause_014_002_002": "（训练机构规范14.2.2）",
            "regulation:uas_training_org_spec:clause_014_002_003": "（训练机构规范14.2.3）",
        }
        return fallback_labels.get(chunk_id, "")

    if "训练机构" in q and any(term in q for term in ("暂停报名考试资格", "停止报名考试资格")):
        s1 = cite("regulation:uas_training_org_spec:clause_014_002_001")
        s2 = cite("regulation:uas_training_org_spec:clause_014_002_002")
        s3 = cite("regulation:uas_training_org_spec:clause_014_002_003")
        if not any(cid in available_ids for cid in (
            "regulation:uas_training_org_spec:clause_014_002_001",
            "regulation:uas_training_org_spec:clause_014_002_002",
            "regulation:uas_training_org_spec:clause_014_002_003",
        )):
            return None
        return "\n\n".join([
            f"1. 暂停报名考试资格：违反 14.1 a)、b) 的训练机构，会被暂停报名考试资格{s1}。",
            f"2. 停止报名考试资格 6 个月：违反 14.1 c)、d)、e)、f) 的训练机构，会被停止报名考试资格 6 个月{s2}。",
            f"3. 停止报名考试资格 1 年：违反 14.1 g)、h)、I) 的训练机构，会被停止报名考试资格 1 年{s3}。",
            "4. 结论：这类问题应直接按《民用中小型无人驾驶航空器操控员训练机构规范》14.1 和 14.2 理解。"
        ])

    if any(term in q for term in ("作弊", "代考")):
        s99 = cite("regulation:ccar_92:art_092_099")
        s1015 = cite("regulation:ccar_92:art_092_1015")
        if not any(cid in available_ids for cid in (
            "regulation:ccar_92:art_092_099",
            "regulation:ccar_92:art_092_1015",
        )):
            return None
        return "\n\n".join([
            f"1. 第92.99条列明了考试中的禁止行为，包括作弊、代考、接受帮助、使用未经批准材料等{s99}。",
            f"2. 第92.1015条规定，执照或者等级申请人考试中有隐瞒有关情况、提供虚假材料等禁止行为的，局方予以警告，并自行为被发现之日起1年内不得申请相关执照、等级以及考试；执照或者等级持有人考试中有欺骗等禁止行为，或者以欺骗、贿赂等不正当手段取得执照或者等级的，局方予以警告，同时撤销相应执照或者等级，责令立即停止飞行运行并交回执照，且自撤销之日起3年内不得再次申请{s1015}。",
        ])

    if any(term in q for term in ("无证操控", "未取得执照", "没执照")):
        s1005 = cite("regulation:ccar_92:art_092_1005")
        if "regulation:ccar_92:art_092_1005" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.1005条规定，未按规定取得民用无人驾驶航空器操控员执照操控飞行的，由局方处5000元以上5万元以下的罚款{s1005}。",
            f"2. 情节严重的，处1万元以上10万元以下的罚款{s1005}。",
        ])

    if any(term in q for term in ("没取得运营合格证", "未取得运营合格证", "没有运营合格证")):
        s1005 = cite("regulation:ccar_92:art_092_1005")
        if "regulation:ccar_92:art_092_1005" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.1005条规定，运行人未取得相应运营合格证和运营规范，或者违反运营合格证或者运营规范要求实施本规则规定运行的，由局方责令改正，处5万元以上50万元以下的罚款{s1005}。",
            f"2. 情节严重的，责令停业整顿直至吊销其运营合格证{s1005}。",
        ])

    if any(term in q for term in ("运营合格证", "运营规范")) and any(term in q for term in ("没取得", "未取得", "没有")) and any(term in q for term in ("处罚", "罚款", "后果")):
        s1005 = cite("regulation:ccar_92:art_092_1005")
        if "regulation:ccar_92:art_092_1005" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.1005条规定，运行人未取得相应运营合格证和运营规范，或者违反运营合格证或者运营规范要求实施本规则规定运行的，由局方责令改正，处5万元以上50万元以下的罚款{s1005}。",
            f"2. 情节严重的，责令停业整顿直至吊销其运营合格证{s1005}。",
        ])

    if any(term in q for term in ("责任保险", "投保")) and any(term in q for term in ("后果", "处罚", "罚款")):
        s1011 = cite("regulation:ccar_92:art_092_1011")
        if "regulation:ccar_92:art_092_1011" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.1011条规定，违反第92.669条未依法投保责任保险的，由局方责令改正，处2000元以上2万元以下的罚款{s1011}。",
            f"2. 情节严重的，责令从事飞行活动的单位停业整顿直至吊销其运营合格证{s1011}。",
        ])

    if any(term in q for term in ("动态信息", "年度运营报告")) and any(term in q for term in ("处罚", "罚款", "后果")):
        s1011 = cite("regulation:ccar_92:art_092_1011")
        s671 = cite("regulation:ccar_92:art_092_671")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_1011", "regulation:ccar_92:art_092_671")):
            return None
        return "\n\n".join([
            f"1. 第92.671条规定，运营人应报送动态信息，并在每年3月31日前报送上一年度年度运营报告{s671}。",
            f"2. 第92.1011条规定，未通过综合管理平台报送相关动态信息或者未按要求报送年度运营报告的，由局方责令改正，处1万元以上3万元以下的罚款{s1011}。",
        ])

    if any(term in q for term in ("严重失信", "失信记录", "信用记录")):
        s1019 = cite("regulation:ccar_92:art_092_1019")
        if "regulation:ccar_92:art_092_1019" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.1019条规定，拒绝接受或者拒不配合局方监督检查、拒不执行改正要求、在执照/适航许可/运营合格证或运营规范申请修改中欺骗伪造或者故意提交虚假材料、操控员执照考试作弊、因故意行为导致相关许可或证件被撤销等，依法作为严重失信行为记入民航行业信用记录{s1019}。",
            "2. 结论：这类问题应优先按 CCAR-92 的严重失信条款回答，不要先混入训练机构规范或一般题库说明。",
        ])

    if any(term in q for term in ("处罚", "罚款", "违法", "违规")) and not first_match_chunk_ids(
        q, UAS_PRIORITY_RULES + CAL_PRIORITY_RULES
    ):
        # 07-12: 罚则主题命中暂行条例锚（监护人/产品质量/重大设计更改等）时不套本 CCAR
        # 固定模板——模板会绕过 LLM 与条款优先注入，把条例罚则答成 CCAR 数额（2035 实锤）；
        # 07-13: 民航法锚同口径豁免（词法保底豁免已上提到函数入口）
        s1005 = cite("regulation:ccar_92:art_092_1005")
        s1007 = cite("regulation:ccar_92:art_092_1007")
        s1009 = cite("regulation:ccar_92:art_092_1009")
        s1013 = cite("regulation:ccar_92:art_092_1013")
        parts = []
        if s1005:
            parts.append(f"1. 证照和运营类处罚：第92.1005条规定，无证操控可处5000元以上5万元以下罚款；情节严重的可处1万元以上10万元以下罚款。超出执照载明范围飞行的，可处2000元以上2万元以下罚款，并暂扣执照6个月至12个月；情节严重的，吊销操控员执照，2年内不受理其申请{s1005}。")
        if s1009:
            parts.append(f"2. 运行规定类处罚：第92.1009条对未接受空中交通服务、未按规定安装使用电子围栏、未遵守视距内运行规则等行为，规定责令停止违法行为、限期整改；情节严重的，对执照持有人可警告或者罚款1000元以下，对运行人可警告或者罚款3万元以下{s1009}。")
        if s1007:
            parts.append(f"3. 欺骗取证类处罚：第92.1007条规定，申请材料中隐瞒情况或者提供虚假信息的，不予受理或者不予许可并警告；以欺骗、贿赂等不正当手段取得许可的，予以撤销，并可处警告或者1万元以下罚款，情节严重的处1万元以上3万元以下罚款，3年内不得再次申请{s1007}。")
        if any(term in q for term in ("酒精", "药物", "饮酒", "醉酒")) and s1013:
            parts.append(f"4. 酒精药物类处罚：第92.1013条规定，相关人员违反酒精或药物限制时，可被责令立即停止担任飞行机组成员，并处罚款、暂扣或者吊销证照{s1013}。")
        if parts:
            return "\n\n".join(parts)

    if any(term in q for term in ("运营合格证", "运营规范")) and any(term in q for term in ("撤销", "注销", "吊销")):
        s665 = cite("regulation:ccar_92:art_092_665")
        if "regulation:ccar_92:art_092_665" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.665条规定，合格证持有人不再具备安全生产条件的，局方撤销其运营合格证和相应运营规范{s665}。",
            f"2. 还包括以下注销情形：有效期届满未延续、持有人依法终止、自愿放弃并交回、证件已被吊销或者撤销，以及法律法规规定的其他应注销行政许可情形{s665}。",
        ])

    if "运营合格证" in q and any(term in q for term in ("有效期届满未更新", "有效期届满未延续", "逾期未更新", "没更新会怎样")):
        s663 = cite("regulation:ccar_92:art_092_663")
        s665 = cite("regulation:ccar_92:art_092_665")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_663", "regulation:ccar_92:art_092_665")):
            return None
        return "\n\n".join([
            f"1. 第92.663条规定，合格证持有人应当在有效期届满30个工作日前提出更新申请；未按期申请或者不满足更新条件、标准和程序的，不得更新运营合格证{s663}。",
            f"2. 第92.665条(b)(1)进一步规定，运营合格证有效期届满未延续的，局方依法办理运营合格证和相应运营规范的注销手续{s665}。",
        ])

    if "运营合格证" in q and any(term in q for term in ("自愿放弃", "放弃运营合格证")):
        s665 = cite("regulation:ccar_92:art_092_665")
        if "regulation:ccar_92:art_092_665" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.665条(b)(3)规定，合格证持有人自愿放弃运营合格证和相应运营规范，并将其交回局方的，局方依法办理注销手续{s665}。",
            "2. 结论：这里不是继续保留证件效力，而是交回证件后进入注销流程。"
        ])

    if "运营合格证" in q and any(term in q for term in ("有效期", "更新", "续期")):
        s655 = cite("regulation:ccar_92:art_092_655")
        s663 = cite("regulation:ccar_92:art_092_663")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_655", "regulation:ccar_92:art_092_663")):
            return None
        return "\n\n".join([
            f"1. 第92.655条规定，除另有规定外，运营合格证自颁发或者更新之日起有效期为 24 个日历月{s655}。",
            f"2. 第92.663条规定，合格证持有人应在有效期届满 30 个工作日前提出更新申请；未按期申请或者不满足更新条件、标准和程序的，不得更新{s663}。",
        ])

    if "运营合格证" in q and any(term in q for term in ("适用范围", "哪些情况", "什么情况", "哪些单位", "哪些运行人", "什么情况下")) and any(term in q for term in ("需要", "应当", "要", "取得")):
        s603 = cite("regulation:ccar_92:art_092_603")
        if "regulation:ccar_92:art_092_603" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.603条(a)规定，除同条(b)款另有规定外，使用民用无人驾驶航空器从事飞行活动的单位，应当经局方运营安全评估，取得运营合格证和相应运营规范后，方可实施运行{s603}。",
            f"2. 第92.603条(b)同时明确两类例外：使用微型民用无人驾驶航空器从事飞行活动的单位，以及常规农用无人驾驶航空器作业飞行活动，无需取得运营合格证{s603}。",
            "3. 结论：除上述两类例外外，使用民用无人驾驶航空器从事飞行活动的单位，原则上都要先取得运营合格证和相应运营规范。"
        ])

    if any(term in q for term in ("外国运行人", "国外运营合格证", "外国运营合格证")) and any(term in q for term in ("国内运行", "在国内运行", "中国境内运行", "能不能直接用", "是否可以认可")):
        s637 = cite("regulation:ccar_92:art_092_637")
        if "regulation:ccar_92:art_092_637" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.637条(a)规定，外国民用无人驾驶航空器在中国境内运行时，应当遵守本章相应的运行规则{s637}。",
            f"2. 第92.637条(b)进一步规定，满足本章规定的运行要求同等安全水平时，经申请，局方可以认可外国运行人的运营合格证或者其他等效证件{s637}。",
            "3. 结论：不是当然可以直接拿国外证件运行，而是要先满足同等安全水平并经申请获得局方认可。"
        ])

    if any(term in q for term in ("开放类", "特定类")) and any(term in q for term in ("运营许可", "运营合格证", "运营规范", "边界", "区别")):
        s601 = cite("regulation:ccar_92:art_092_601")
        s603 = cite("regulation:ccar_92:art_092_603")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_601", "regulation:ccar_92:art_092_603")):
            return None
        return "\n\n".join([
            f"1. 第92.601条(a)规定，开放类运行包括使用微型民用无人驾驶航空器实施运行、使用轻型民用无人驾驶航空器在适飞空域内运行，以及常规农用无人驾驶航空器作业飞行活动；这类运行适用一般运行要求{s601}。",
            f"2. 第92.601条(b)规定，经运营安全评估确定为特定类运行的，应当符合并遵守一般运行要求和相应运营规范的要求{s601}。",
            f"3. 第92.603条进一步把运营许可边界说清楚：除微型运行和常规农用作业两类例外外，从事飞行活动的单位原则上都应先取得运营合格证和相应运营规范{s603}。",
            "4. 结论：开放类中的微型运行和常规农用作业是许可例外；特定类运行则不是例外，需要纳入运营合格证和运营规范框架。"
        ])

    if any(term in q for term in ("开放类", "哪些运行属于开放类")) and any(term in q for term in ("不需要额外运营规范", "无需额外运营规范", "哪些运行")):
        s601 = cite("regulation:ccar_92:art_092_601")
        s603 = cite("regulation:ccar_92:art_092_603")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_601", "regulation:ccar_92:art_092_603")):
            return None
        return "\n\n".join([
            f"1. 第92.601条(a)列明了开放类运行的典型范围：使用微型民用无人驾驶航空器实施运行、使用轻型民用无人驾驶航空器在适飞空域内运行、常规农用无人驾驶航空器作业飞行活动{s601}。",
            f"2. 其中第92.603条(b)明确的许可例外只有两类：使用微型民用无人驾驶航空器从事飞行活动，以及常规农用无人驾驶航空器作业飞行活动，无需取得运营合格证{s603}。",
            f"3. 相比之下，第92.601条(b)的特定类运行应遵守相应运营规范要求{s601}。",
            "4. 结论：问到“无需额外运营规范”的边界时，应优先落在开放类中的许可例外场景，而不能把特定类一起并入。"
        ])

    if "微型无人机" in q and "运营合格证" in q and any(term in q for term in ("需不需要", "需要吗", "要不要", "是否需要")):
        s603 = cite("regulation:ccar_92:art_092_603")
        if "regulation:ccar_92:art_092_603" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.603条(b)明确规定，使用微型民用无人驾驶航空器从事飞行活动的单位，无需取得运营合格证{s603}。",
            f"2. 同条(a)的运营合格证要求，适用于除(b)款例外之外的其他单位{s603}。",
            "3. 结论：微型无人机本身对应的这类运行，不需要取得运营合格证。"
        ])

    if "运营合格证" in q and "运营规范" in q and any(term in q for term in ("分别", "区别", "是什么")):
        s603 = cite("regulation:ccar_92:art_092_603")
        if "regulation:ccar_92:art_092_603" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.603条规定，符合条件的单位经运营安全评估后，应取得运营合格证和相应运营规范，方可实施运行{s603}。",
            f"2. 同条还明确，运营规范是运营合格证的附件，合格证持有人不得违反运营合格证和相应运营规范的要求实施运行{s603}。",
        ])

    if "运营合格证" in q and any(term in q for term in ("受理后多久", "多久作出决定", "审查多久", "多久决定", "多少工作日作出决定")):
        s647 = cite("regulation:ccar_92:art_092_647")
        if "regulation:ccar_92:art_092_647" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.647条(c)规定，局方应当自受理申请之日起 20 个工作日内，作出是否颁发运营合格证和相应运营规范的决定{s647}。",
            f"2. 但如果对申请人的运行风险或者风险缓解措施有效性存在争议，需要检验、检测、鉴定或者组织专家评审的，相应时间不计入前述 20 个工作日{s647}。",
        ])

    if "运营合格证" in q and any(term in q for term in ("送达", "颁发后多久", "决定后多久", "多久送达", "作出决定之日起")):
        s651 = cite("regulation:ccar_92:art_092_651")
        if "regulation:ccar_92:art_092_651" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.651条(a)规定，局方作出颁发运营合格证和相应运营规范决定后，应当自作出决定之日起 10 个工作日内向申请人颁发、送达运营合格证和相应运营规范{s651}。",
            f"2. 第92.651条(b)还规定，不予颁发的，应以书面形式通知申请人，说明理由并告知其依法申请行政复议或者提起行政诉讼的权利{s651}。",
        ])

    if "运营规范" in q and any(term in q for term in ("载明", "哪些内容", "什么内容", "包含什么")):
        s653 = cite("regulation:ccar_92:art_092_653")
        if "regulation:ccar_92:art_092_653" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.653条(b)规定，运营规范是运营合格证的附件，内容包括局方规定的合格证持有人应当遵守的、与行使合格证权利相关的批准、条件和限制等规范{s653}。",
            f"2. 结论：运营规范核心不是单独一张说明性文件，而是围绕合格证权利范围所附着的批准事项、运行条件和限制要求{s653}。",
        ])

    if "运营合格证" in q and any(term in q for term in ("材料", "申请", "提交")):
        s647 = cite("regulation:ccar_92:art_092_647")
        if "regulation:ccar_92:art_092_647" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.647条规定，申请运营合格证和相应运营规范时，应提交申请书及下列材料：符合局方要求内容的手册、民用无人驾驶航空器及运行设备设施的购买/租赁合同或协议副本、与管理人员和操控员签署的劳动合同、说明计划运行性质和范围的文件以及运行风险评估报告和测试验证文件、申请人符合适用条款的符合性声明{s647}。",
            f"2. 申请从事经营活动的，还应提交营业执照、法定代表人身份证明、外商投资相关合规性声明（如适用）、拟申请的经营种类及相关说明材料{s647}。",
        ])

    if "运营合格证" in q and any(term in q for term in ("材料", "提交")) and any(term in q for term in ("受理后多久", "多久决定", "作出决定", "多久送达", "决定后多久", "送达")):
        s647 = cite("regulation:ccar_92:art_092_647")
        s651 = cite("regulation:ccar_92:art_092_651")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_647", "regulation:ccar_92:art_092_651")):
            return None
        return "\n\n".join([
            f"1. 第92.647条规定，申请运营合格证和相应运营规范时，应提交申请书、手册、航空器和设备设施合同或协议副本、人员劳动合同、运行性质和范围说明文件、运行风险评估报告及测试验证文件、符合性声明；从事经营活动的还需补充营业执照等经营相关材料{s647}。",
            f"2. 对审查时限，第92.647条(c)规定，局方应当自受理申请之日起20个工作日内，作出是否颁发运营合格证和相应运营规范的决定；检验、检测、鉴定或者专家评审时间不计入{s647}。",
            f"3. 对送达时限，第92.651条(a)规定，局方作出颁发决定后，应当自作出决定之日起10个工作日内向申请人颁发、送达运营合格证和相应运营规范{s651}。",
        ])

    if any(term in q for term in ("吊销", "撤销", "失效", "注销")) and any(term in q for term in ("执照", "等级")):
        s67 = cite("regulation:ccar_92:art_092_067")
        s95 = cite("regulation:ccar_92:art_092_095")
        s1015 = cite("regulation:ccar_92:art_092_1015")
        parts = []
        if s67:
            parts.append(f"1. 第92.67条规定，执照有效期满未更新、持有人死亡或丧失行为能力、自愿放弃、执照依法被撤销撤回或吊销等情形，局方应依法办理执照注销{s67}。")
        if s95:
            parts.append(f"2. 第92.95条规定，因执照持有人的操作造成民用无人驾驶航空器事故的，局方可以暂停或者撤销其执照或者相应等级{s95}。")
        if s1015:
            parts.append(f"3. 第92.1015条规定，持证人考试中有欺骗等禁止行为，或者以欺骗、贿赂等不正当手段取得执照或者等级的，局方会撤销相应执照或者等级，并责令其立即停止飞行运行、交回执照，且3年内不得再次申请{s1015}。")
        if parts:
            return "\n\n".join(parts)

    if any(term in q for term in ("运行人", "运营人")) and any(term in q for term in ("基本运行责任", "运行责任")):
        s673 = cite("regulation:ccar_92:art_092_673")
        if "regulation:ccar_92:art_092_673" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.673条规定，运行人应对运行负责，确保落实所有运行安全工作，并遵守局方针对其运行的相关要求{s673}。",
            f"2. 还包括：对第三方安全关键服务负责；确保实施运行相关人员熟悉适用的法律、法规、规章和程序；并按局方要求报告不安全事件{s673}。",
        ])

    if any(term in q for term in ("责任保险", "投保", "保险")) and any(term in q for term in ("运行人", "运营人", "无人机")):
        s669 = cite("regulation:ccar_92:art_092_669")
        if "regulation:ccar_92:art_092_669" not in available_ids:
            return None
        return f"第92.669条规定：运营人应当按规定投保责任保险{s669}。"

    if any(term in q for term in ("报送", "年度运营报告", "平台")) and any(term in q for term in ("运行人", "运营人", "无人机")):
        s671 = cite("regulation:ccar_92:art_092_671")
        if "regulation:ccar_92:art_092_671" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.671条规定，运营人应及时向综合管理平台报送经营活动性质、运营区域、航线信息、起降架次、运营时间、作业量等动态信息{s671}。",
            f"2. 还应在每年 3 月 31 日前报送上一年度的年度运营报告，至少包括企业简介、经营情况说明、股东情况、董事监事高管及专业技术人员情况{s671}。",
        ])

    if "年度运营报告" in q and any(term in q for term in ("哪些运行人", "哪些主体", "谁需要", "什么人需要")):
        s603 = cite("regulation:ccar_92:art_092_603")
        s671 = cite("regulation:ccar_92:art_092_671")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_603", "regulation:ccar_92:art_092_671")):
            return None
        return "\n\n".join([
            f"1. 第92.671条规定，运营人应当通过综合管理平台报送动态信息，并在每年 3 月 31 日前报送上一年度年度运营报告{s671}。",
            f"2. 结合第92.603条，原则上需要取得运营合格证并按本章实施运行的单位，属于这里所说的运营人；而使用微型民用无人驾驶航空器从事飞行活动的单位、常规农用无人驾驶航空器作业飞行活动，无需取得运营合格证{s603}。",
            "3. 结论：需要履行年度运营报告义务的，是适用第92章运营许可规则的运营人，不包括第92.603条(b)明确排除的两类情形。"
        ])

    if "年度运营报告" in q and any(term in q for term in ("哪些运行人", "哪些主体", "谁需要")) and any(term in q for term in ("处罚", "罚款", "没报")):
        s603 = cite("regulation:ccar_92:art_092_603")
        s671 = cite("regulation:ccar_92:art_092_671")
        s1011 = cite("regulation:ccar_92:art_092_1011")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_603", "regulation:ccar_92:art_092_671", "regulation:ccar_92:art_092_1011")):
            return None
        return "\n\n".join([
            f"1. 第92.671条规定，运营人应通过综合管理平台报送动态信息，并在每年3月31日前报送上一年度年度运营报告{s671}。",
            f"2. 结合第92.603条，这里的运营人原则上是适用第92章运营许可规则、需要取得运营合格证并按本章实施运行的单位；微型运行和常规农用作业两类例外不在其中{s603}。",
            f"3. 第92.1011条规定，未通过综合管理平台报送相关动态信息或者未按要求报送年度运营报告的，由局方责令改正，处1万元以上3万元以下的罚款{s1011}。",
        ])

    if any(term in q for term in ("持续适航", "维修管理")) and any(term in q for term in ("运行人", "维修", "体系")):
        s619 = cite("regulation:ccar_92:art_092_619")
        s707 = cite("regulation:ccar_92:art_092_707")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_619", "regulation:ccar_92:art_092_707")):
            return None
        return "\n\n".join([
            f"1. 第92.619条规定，运行人应对持续保持民用无人驾驶航空器系统的适航状态负责，并确保适航证件持续有效、航空器处于适航状态、遥控站及指挥控制链路处于安全工作状态{s619}。",
            f"2. 第92.707条规定，为落实持续适航要求，运行人应指定具备维修资质和经验的责任人，并建立维修计划管理、资源保障和质量管理制度等维修管理体系{s707}。",
        ])

    if any(term in q for term in ("故障", "失效", "缺陷")) and any(term in q for term in ("报告", "怎么办", "发现")):
        s621 = cite("regulation:ccar_92:art_092_621")
        s311 = cite("regulation:ccar_92:art_092_311")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_621", "regulation:ccar_92:art_092_311")):
            return None
        return "\n\n".join([
            f"1. 第92.621条规定，在实施维修过程中，如发现可能普遍影响安全飞行的故障、失效或者缺陷，运行人应及时向制造厂家报告，并自愿向局方报告{s621}。",
            f"2. 第92.311条还规定，设计/生产相关持证人确认故障、失效或缺陷存在后，应按规定格式向局方提交报告；其中相关报告义务可涉及 48 小时内提交{s311}。",
        ])

    if any(term in q for term in ("飞行前准备", "通信链路", "电池储备")):
        s623 = cite("regulation:ccar_92:art_092_623")
        if "regulation:ccar_92:art_092_623" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.623条规定，飞行前应确认适航要求、了解任务区域气象条件、确认运行场地满足使用说明书或飞行手册要求、检查各组件情况、燃油或者电池储备、通信链路信号是否满足运行要求，并确认运行控制系统是否正常接入{s623}。",
            f"2. 还应制定紧急情况处置预案，了解任务区域人员和地形位置，并确保直接参与飞行操控的人员了解飞行条件、职责和潜在风险{s623}。",
        ])
    if any(term in q for term in ("C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序")):
        s679 = cite("regulation:ccar_92:art_092_679")
        s697 = cite("regulation:ccar_92:art_092_697")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_679", "regulation:ccar_92:art_092_697")):
            return None
        return "\n\n".join([
            f"1. 第92.679条规定，C2链路应符合与运行相适合的通信业务处理时间、连续性、可用性和完好性要求；运行人应使用符合局方要求的服务水平协议对直接控制的 C2 链路或通信服务提供方的服务进行管理{s679}。",
            f"2. 第92.697条规定，运行人应制定 C2 链路的建立、保障和终止程序，以及非正常和紧急程序；并确保在 C2 链路故障时，民用无人驾驶航空器具备按照预设程序和可预期飞行轨迹飞行的能力{s697}。",
        ])
    if any(term in q for term in ("紧急迫降", "迫降地点", "终止飞行")):
        s701 = cite("regulation:ccar_92:art_092_701")
        if "regulation:ccar_92:art_092_701" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.701条规定，在特殊运行要求下，民用无人驾驶航空器操控员应当按照局方要求计划或者选择紧急迫降地点，并制定终止飞行相应程序{s701}。",
            "2. 结论：这类问题优先按 CCAR-92 的特殊运行要求条款回答，不应先落到任务规划题库的泛化描述。",
        ])
    if any(term in q for term in ("事故报告", "严重受伤", "重大损失")):
        s687 = cite("regulation:ccar_92:art_092_687")
        if "regulation:ccar_92:art_092_687" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.687条规定，机长应当以可用的、最迅速的方法，向最近的民航及有关部门报告导致人员严重受伤或者死亡、地面财产重大损失的任何航空器事故{s687}。",
            f"2. 同条还规定，机长或者由运行人指定的人员应尽早向运行人报告民用无人驾驶航空器所有已知或者怀疑的缺陷{s687}。",
        ])
    if any(term in q for term in ("应急反应预案", "飞行事故应急反应预案")):
        s667 = cite("regulation:ccar_92:art_092_667")
        if "regulation:ccar_92:art_092_667" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.667条规定，从事载客、载人类经营性通用航空活动的，应按照民航局有关规定和相应运营规范要求，制定服务标准、锂电池等危险品运输管理手册、飞行事故应急反应预案和伤亡人员家属援助计划{s667}。",
            "2. 结论：这里问的是经营活动运行人的法定义务，不是一般培训或题库中的经验性应急建议。",
        ])

    if any(term in q for term in ("维修记录", "维修放行")):
        s619 = cite("regulation:ccar_92:art_092_619")
        s709 = cite("regulation:ccar_92:art_092_709")
        if not any(cid in available_ids for cid in ("regulation:ccar_92:art_092_619", "regulation:ccar_92:art_092_709")):
            return None
        return "\n\n".join([
            f"1. 第92.619条规定，运行人应妥善保存维修记录和维修放行证明，直至被下一次维修工作全部覆盖{s619}。",
            f"2. 也就是说，这里不是按固定几年或者几个月计算，而是以下一次对应维修工作已经完整覆盖前一次记录为止{s619}。",
            f"3. 第92.709条还要求运行人建立记录保存系统，并对每架民用无人驾驶航空器建立飞行记录本，及时准确录入信息{s709}。",
        ])

    if any(term in q for term in ("立即停止飞行", "停止飞行", "不能飞")):
        s633 = cite("regulation:ccar_92:art_092_633")
        if "regulation:ccar_92:art_092_633" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.633条规定，超视距运行时，如果飞行操控危害到空域其他使用者、地面上人身财产安全，或者不能按照飞行计划继续飞行，应当立即停止飞行活动{s633}。",
            "2. 结论：这类问题优先按 CCAR-92 的运行限制条款回答，不应先落到题库泛化说明。"
        ])

    if any(term in q for term in ("申请条件", "资格条件")) and any(term in q for term in ("申请材料", "提交材料", "报名材料", "所需材料", "材料")) and any(term in q for term in ("区别", "不同", "有什么区别")):
        s55 = cite("regulation:ccar_92:art_092_055")
        s57 = cite("regulation:ccar_92:art_092_057")
        if not any(cid in available_ids for cid in (
            "regulation:ccar_92:art_092_055",
            "regulation:ccar_92:art_092_057",
        )):
            return None
        return "\n\n".join([
            f"1. 申请条件看第92.55条，要求申请人具备完全民事行为能力、无相关疾病病史、无吸毒行为记录、近5年内无特定故意犯罪刑事处罚记录，并完成相应训练和考试{s55}。",
            f"2. 申请材料看第92.57条，要求提交身份证明、身体情况说明、犯罪记录声明、理论考试合格成绩单、授权教员资质证明、训练飞行活动合法证明、飞行经历记录信息、实践考试合格证明{s57}。",
            "3. 结论：申请条件回答的是“你是否具备申请资格”，申请材料回答的是“申请时要交什么文件”，两者不是一回事。"
        ])

    if any(term in q for term in ("申请材料", "提交材料", "报名材料", "所需材料", "材料")) and not any(term in q for term in ("虚假材料", "作弊", "代考", "运营合格证")):
        s = cite("regulation:ccar_92:art_092_057")
        if "regulation:ccar_92:art_092_057" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.57条规定，申请人提交执照或者等级申请时，至少应提交：身份证明、身体情况说明、近5年内特定故意犯罪刑事处罚记录声明、理论考试合格成绩单、授权教员资质证明、训练飞行活动的合法证明、飞行经历记录信息、实践考试合格证明{s}。",
            "2. 结论：这里说的是执照/等级申请材料，不是空域申请材料，也不是培训机构自定义报名材料。"
        ])

    if any(term in q for term in ("不得申请", "不能申请", "禁止行为", "虚假材料")):
        s55 = cite("regulation:ccar_92:art_092_055")
        s99 = cite("regulation:ccar_92:art_092_099")
        s101 = cite("regulation:ccar_92:art_092_101")
        parts = []
        if s55:
            parts.append(f"1. 申请条件层面：第92.55条要求申请人具备完全民事行为能力、无相关疾病病史、无吸毒行为记录、近5年内无特定故意犯罪刑事处罚记录，并完成相应训练和考试{s55}。")
        if s99:
            parts.append(f"2. 考试行为层面：第92.99条列明了考试中的禁止行为，例如作弊、代考、接受帮助、使用未经批准材料等{s99}。")
        if s101:
            parts.append(f"3. 材料真实性层面：第92.101条禁止在执照、等级申请书和相关记录中作虚假陈述、填写虚假内容或伪造篡改证件{s101}。")
        if not parts:
            return None
        parts.append("4. 结论：这类问题要区分“本身不具备申请条件”与“考试/材料阶段存在禁止行为”两类限制。")
        return "\n\n".join(parts)

    if "实名登记" in q and "国籍登记" in q and any(term in q for term in ("区别", "不同", "有什么区别")):
        s205 = cite("regulation:ccar_92:art_092_205")
        s215 = cite("regulation:ccar_92:art_092_215")
        s217 = cite("regulation:ccar_92:art_092_217")
        if not any(cid in available_ids for cid in (
            "regulation:ccar_92:art_092_205",
            "regulation:ccar_92:art_092_215",
            "regulation:ccar_92:art_092_217",
        )):
            return None
        return "\n\n".join([
            f"1. 实名登记看第92.205条，核心是登记所有人合法身份信息、联系信息、航空器信息和使用用途，属于境内运行前的基础登记{s205}。",
            f"2. 国籍登记看第92.215条、第92.217条，核心是确认哪些主体可以申请中华人民共和国国籍登记，以及申请时提交合法身份文件、所有权证明、实名登记号和境外国籍证明等材料{s215}{s217}。",
            "3. 结论：实名登记侧重“谁在用这架无人机、这架机是什么用途”，国籍登记侧重“这架无人机属于哪个国家登记体系以及是否具备相应登记资格”。"
        ])

    if any(term in q for term in ("实名登记", "登记材料")) and not asks_rnr_specific_attribute(q):
        s = cite("regulation:ccar_92:art_092_205")
        if "regulation:ccar_92:art_092_205" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.205条规定，实名登记信息至少包括：所有人合法身份信息、所有人联系信息、民用无人驾驶航空器信息、民用无人驾驶航空器使用用途{s}。",
            "2. 结论：这类问题应直接按实名登记信息项回答，不要混入执照申请材料或培训报名材料。"
        ])
    if "实名登记" in q and any(term in q for term in ("注销", "注销登记")):
        s = cite("regulation:ccar_92:art_092_207")
        if "regulation:ccar_92:art_092_207" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.207条规定，实名登记后遇有以下情形之一应申请注销：所有权或者占有权发生变更；民用无人驾驶航空器退出使用、报废或者失事；所有权依法转移境外并已办理出口适航证{s}。",
            "2. 结论：这类问题要按注销触发情形回答，不要泛化成重新登记流程。"
        ])
    if "实名登记" in q and any(term in q for term in ("变更", "更新")):
        s = cite("regulation:ccar_92:art_092_209")
        if "regulation:ccar_92:art_092_209" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.209条规定，应更新的信息包括：微型、轻型、小型航空器的空域保持和可靠性监视能力、速度、高度等出厂性能参数变化；中型、大型航空器重大设计更改；所有人或者占有人的联系方式或其他信息变更；民用无人驾驶航空器用途变更{s}。",
            "2. 结论：这类问题应回答哪些信息项需要更新，而不是再回到首次实名登记材料。"
        ])
    if "国籍登记" in q and any(term in q for term in ("条件", "要求", "谁可以", "哪些人可以", "哪些主体可以", "申请人")):
        s = cite("regulation:ccar_92:art_092_215")
        if "regulation:ccar_92:art_092_215" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.215条规定，可以申请中华人民共和国民用航空器国籍登记的申请人包括：国家机构、依中国法律设立的企业法人、在中国境内有住所或者主要营业场所的中国公民、依中国法律设立的事业法人，以及民航局准予登记的其他情况{s}。",
            "2. 结论：这里回答的是申请主体条件，不是申请文件清单。"
        ])
    if "国籍登记" in q and any(term in q for term in ("材料", "申请", "提交")):
        s = cite("regulation:ccar_92:art_092_217")
        if "regulation:ccar_92:art_092_217" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.217条规定，申请中华人民共和国民用无人驾驶航空器国籍登记时，应填写国籍登记申请书，并提交：证明申请人合法身份的文件、所有权或者占有该航空器的证明文件、民用无人驾驶航空器的实名登记号，以及未在境外登记国籍或者已注销境外国籍的证明{s}。",
            "2. 结论：这里看的是国籍登记申请文件，不是实名登记信息项。"
        ])
    if "国籍登记" in q and any(term in q for term in ("遗失", "污损", "补发", "更换", "证书")):
        s = cite("regulation:ccar_92:art_092_223")
        if "regulation:ccar_92:art_092_223" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.223条(c)规定，国籍登记证书遗失或者污损的，应向民航局申请补发或者更换，并提交有关说明材料{s}。",
            f"2. 民航局自收到申请之日起 5 个工作日内审查；符合规定的，即补发或者更换国籍登记证书{s}。",
        ])
    if "适航证" in q and "特许飞行证" in q and any(term in q for term in ("区别", "不同")):
        s453 = cite("regulation:ccar_92:art_092_453")
        if "regulation:ccar_92:art_092_453" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.453条规定，适航证件包括标准适航证、特殊适航证、特许飞行证和出口适航证{s453}。",
            f"2. 其中，标准/特殊适航证适用于已按本章取得相应适航批准的民用无人驾驶航空器系统；特许飞行证适用于尚未取得有效适航证或者可能不符合有关适航要求，但在一定限制条件下能够安全开展相关飞行活动的系统{s453}。",
            "3. 结论：两者核心区别在于适用状态不同，特许飞行证是受限条件下的例外飞行批准，不等同于一般适航状态证明。"
        ])
    if "适航证" in q and any(term in q for term in ("申请", "提交", "材料")):
        s455 = cite("regulation:ccar_92:art_092_455")
        if "regulation:ccar_92:art_092_455" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.455条规定，按本规则 C 章完成实名登记的民用无人驾驶航空器系统，其所有人或者占有人可以申请适航证{s455}。",
            f"2. 申请时应提交申请书，并提交证明该航空器系统适航性的相关文件{s455}。",
            "3. 结论：这里看的是适航性证明文件，不是执照报考材料。"
        ])
    if "特许飞行证" in q and any(term in q for term in ("情况", "条件", "申请")):
        s453 = cite("regulation:ccar_92:art_092_453")
        s467 = cite("regulation:ccar_92:art_092_467")
        s471 = cite("regulation:ccar_92:art_092_471")
        if not any(cid in available_ids for cid in (
            "regulation:ccar_92:art_092_453",
            "regulation:ccar_92:art_092_467",
            "regulation:ccar_92:art_092_471",
        )):
            return None
        return "\n\n".join([
            f"1. 第92.453条规定，特许飞行证适用于尚未取得有效适航证或者可能不符合有关适航要求，但在一定限制条件下能够安全开展相关飞行活动的民用无人驾驶航空器系统{s453}。",
            f"2. 第92.467条规定，完成实名登记的系统，其所有人或者占有人可以申请特许飞行证；申请时应提交申请书，并提交表明该航空器系统技术与批准状态的报告和建议的使用限制{s467}。",
            f"3. 第92.471条规定，局方收到申请后会进行审查、提出确保飞行安全的限制条件、开展适航检查，并颁发明确用途和必要限制的特许飞行证{s471}。",
        ])

    if any(term in q for term in ("夜间飞行", "视距内运行")):
        s = cite("regulation:ccar_92:art_092_631")
        if "regulation:ccar_92:art_092_631" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.631条规定，夜间运行属于视距内运行的一部分飞行阶段，操控员或者观测员应当与航空器保持直接且无设备辅助的目视接触；还应开启防碰撞灯光，并保持最低安全间隔{s}。",
            "2. 结论：夜间飞行这里优先看视距内运行条款，不应先跳到题库泛化答案。"
        ])
    if any(term in q for term in ("视距内等级", "超视距等级")) and any(term in q for term in ("区别", "不同", "有什么区别")):
        s55 = cite("regulation:ccar_92:art_092_055")
        s57 = cite("regulation:ccar_92:art_092_057")
        s633 = cite("regulation:ccar_92:art_092_633")
        if not any(cid in available_ids for cid in (
            "regulation:ccar_92:art_092_055",
            "regulation:ccar_92:art_092_057",
            "regulation:ccar_92:art_092_633",
        )):
            return None
        return "\n\n".join([
            f"1. 第92.55条把视距内等级、超视距等级都放在执照和等级申请条件框架下，但超视距等级对应的是更高运行权限{s55}。",
            f"2. 第92.633条对应超视距运行要求，强调让航、交通态势信息服务、必要时立即停止飞行等要求，说明超视距等级对应的运行场景和风险控制要求更高{s633}。",
            f"3. 第92.57条则要求申请执照或者等级时提交相应申请材料；如果是增设超视距等级，仍需按该条提交相应申请文件并完成对应训练考试{s57}。",
            "4. 结论：视距内等级主要覆盖目视范围内运行，超视距等级覆盖视距外运行，权限更高、运行约束更严、训练考试要求也更高。"
        ])
    if any(term in q for term in ("超视距飞行", "超视距运行")):
        s = cite("regulation:ccar_92:art_092_633")
        if "regulation:ccar_92:art_092_633" not in available_ids:
            return None
        return "\n\n".join([
            f"1. 第92.633条规定，超视距运行时应当让航于有人驾驶航空器；当运行危害其他空域使用者、地面人身财产安全，或者不能按飞行计划继续飞行时，应立即停止飞行活动{s}。",
            "2. 对于自动模式运行，操控员仍应能够随时超控；并应具备相应超视距等级。",
        ])
    return None


def regulation_priority_source_ids(question: str) -> list[str]:
    q = question or ""
    # 暂行条例规则表与 bm25 共用唯一事实源（anchor_rules，2026-07-12 审计闭环）；
    # 本函数保持首匹配语义，且必须先于下方 CCAR 历史宽锚（裸"实名登记"/裸"处罚"等）命中
    uas_hit = first_match_chunk_ids(q, UAS_PRIORITY_RULES)
    if uas_hit:
        return uas_hit
    # 民航法主题锚（值勤时间/境外租赁/携带文件/安全检查/未取得航空人员执照，2026-07-13）：
    # 这批问法不点名"民航法"、罚则被 CCAR-92 词法垄断，按语料真值直锚民航法条文
    cal_hit = first_match_chunk_ids(q, CAL_PRIORITY_RULES)
    if cal_hit:
        return cal_hit
    # 考试办法知识范围锚（理论考试考什么/大纲模块，2026-07-25）：清单段常被
    # 元数据头 chunk 挤出摘录窗，条款优先注入保证清单入场
    md92_hit = first_match_chunk_ids(q, MD92_PRIORITY_RULES)
    if md92_hit:
        return md92_hit
    if any(term in q for term in ("外国运行人", "国外运营合格证", "外国运营合格证")) and any(term in q for term in ("国内运行", "在国内运行", "中国境内运行", "能不能直接用", "是否可以认可")):
        return ["regulation:ccar_92:art_092_637"]
    if any(term in q for term in ("开放类", "特定类")) and any(term in q for term in ("运营许可", "运营合格证", "运营规范", "边界", "区别")):
        return ["regulation:ccar_92:art_092_601", "regulation:ccar_92:art_092_603"]
    if any(term in q for term in ("开放类", "哪些运行属于开放类")) and any(term in q for term in ("不需要额外运营规范", "无需额外运营规范", "哪些运行")):
        return ["regulation:ccar_92:art_092_601", "regulation:ccar_92:art_092_603"]
    if "运营合格证" in q and any(term in q for term in ("有效期届满未更新", "有效期届满未延续", "逾期未更新", "没更新会怎样")):
        return ["regulation:ccar_92:art_092_663", "regulation:ccar_92:art_092_665"]
    if "运营合格证" in q and any(term in q for term in ("自愿放弃", "放弃运营合格证")):
        return ["regulation:ccar_92:art_092_665"]
    if "运营合格证" in q and any(term in q for term in ("材料", "提交")) and any(term in q for term in ("受理后多久", "多久决定", "作出决定", "多久送达", "决定后多久", "送达")):
        return ["regulation:ccar_92:art_092_647", "regulation:ccar_92:art_092_651"]
    if "运营合格证" in q and any(term in q for term in ("受理后多久", "多久作出决定", "审查多久", "多久决定", "多少工作日作出决定")):
        return ["regulation:ccar_92:art_092_647"]
    if "运营合格证" in q and any(term in q for term in ("送达", "颁发后多久", "决定后多久", "多久送达", "作出决定之日起")):
        return ["regulation:ccar_92:art_092_651"]
    if "运营规范" in q and any(term in q for term in ("载明", "哪些内容", "什么内容", "包含什么")):
        return ["regulation:ccar_92:art_092_653"]
    if "运营合格证" in q and any(term in q for term in ("适用范围", "哪些情况", "什么情况", "哪些单位", "哪些运行人", "什么情况下")) and any(term in q for term in ("需要", "应当", "要", "取得")):
        return ["regulation:ccar_92:art_092_603"]
    if "微型无人机" in q and "运营合格证" in q and any(term in q for term in ("需不需要", "需要吗", "要不要", "是否需要")):
        return ["regulation:ccar_92:art_092_603"]
    if any(term in q for term in ("申请条件", "资格条件")) and any(term in q for term in ("申请材料", "提交材料", "报名材料", "所需材料", "材料")) and any(term in q for term in ("区别", "不同", "有什么区别")):
        return ["regulation:ccar_92:art_092_055", "regulation:ccar_92:art_092_057"]
    if "运营合格证" in q and any(term in q for term in ("材料", "申请", "提交")):
        return ["regulation:ccar_92:art_092_647"]
    if "运营合格证" in q and any(term in q for term in ("有效期", "更新", "续期")):
        return ["regulation:ccar_92:art_092_655", "regulation:ccar_92:art_092_663"]
    if "运营合格证" in q and "运营规范" in q and any(term in q for term in ("分别", "区别", "是什么")):
        return ["regulation:ccar_92:art_092_603"]
    if "年度运营报告" in q and any(term in q for term in ("哪些运行人", "哪些主体", "谁需要", "什么人需要")):
        return ["regulation:ccar_92:art_092_671", "regulation:ccar_92:art_092_603"]
    if "年度运营报告" in q and any(term in q for term in ("哪些运行人", "哪些主体", "谁需要")) and any(term in q for term in ("处罚", "罚款", "没报")):
        return ["regulation:ccar_92:art_092_671", "regulation:ccar_92:art_092_603", "regulation:ccar_92:art_092_1011"]
    if any(term in q for term in ("运行人", "运营人")) and any(term in q for term in ("基本运行责任", "运行责任")):
        return ["regulation:ccar_92:art_092_673"]
    if any(term in q for term in ("责任保险", "投保", "保险")) and any(term in q for term in ("运行人", "运营人", "无人机")):
        return ["regulation:ccar_92:art_092_669"]
    if any(term in q for term in ("报送", "年度运营报告", "平台")) and any(term in q for term in ("运行人", "运营人", "无人机")):
        return ["regulation:ccar_92:art_092_671"]
    if any(term in q for term in ("无证操控", "未取得执照", "没执照")):
        return ["regulation:ccar_92:art_092_1005"]
    if any(term in q for term in ("没取得运营合格证", "未取得运营合格证", "没有运营合格证")):
        return ["regulation:ccar_92:art_092_1005"]
    if any(term in q for term in ("责任保险", "投保")) and any(term in q for term in ("后果", "处罚", "罚款")):
        return ["regulation:ccar_92:art_092_1011", "regulation:ccar_92:art_092_669"]
    if any(term in q for term in ("动态信息", "年度运营报告")) and any(term in q for term in ("处罚", "罚款", "后果")):
        return ["regulation:ccar_92:art_092_1011", "regulation:ccar_92:art_092_671"]
    if any(term in q for term in ("严重失信", "失信记录", "信用记录")):
        return ["regulation:ccar_92:art_092_1019"]
    if any(term in q for term in ("持续适航", "维修管理")) and any(term in q for term in ("运行人", "维修", "体系")):
        return ["regulation:ccar_92:art_092_619", "regulation:ccar_92:art_092_707"]
    if any(term in q for term in ("故障", "失效", "缺陷")) and any(term in q for term in ("报告", "怎么办", "发现")):
        return ["regulation:ccar_92:art_092_621", "regulation:ccar_92:art_092_311"]
    if "实名登记" in q and "国籍登记" in q and any(term in q for term in ("区别", "不同", "有什么区别")):
        return ["regulation:ccar_92:art_092_205", "regulation:ccar_92:art_092_215", "regulation:ccar_92:art_092_217"]
    if any(term in q for term in ("实名登记", "登记材料")) and not asks_rnr_specific_attribute(q):
        return ["regulation:ccar_92:art_092_205"]
    if "实名登记" in q and any(term in q for term in ("注销", "注销登记")):
        return ["regulation:ccar_92:art_092_207"]
    if "实名登记" in q and any(term in q for term in ("变更", "更新")):
        return ["regulation:ccar_92:art_092_209"]
    if "国籍登记" in q and any(term in q for term in ("条件", "要求", "谁可以", "哪些人可以", "哪些主体可以", "申请人")):
        return ["regulation:ccar_92:art_092_215"]
    if "国籍登记" in q and any(term in q for term in ("材料", "申请", "提交")):
        return ["regulation:ccar_92:art_092_217"]
    if "国籍登记" in q and any(term in q for term in ("遗失", "污损", "补发", "更换", "证书")):
        return ["regulation:ccar_92:art_092_223"]
    if "适航证" in q and "特许飞行证" in q and any(term in q for term in ("区别", "不同", "是什么")):
        return ["regulation:ccar_92:art_092_453"]
    if any(term in q for term in ("视距内等级", "超视距等级")) and any(term in q for term in ("区别", "不同", "有什么区别")):
        return ["regulation:ccar_92:art_092_055", "regulation:ccar_92:art_092_633", "regulation:ccar_92:art_092_057"]
    if "适航证" in q and any(term in q for term in ("材料", "申请", "提交")):
        return ["regulation:ccar_92:art_092_455"]
    if "特许飞行证" in q and any(term in q for term in ("情况", "条件", "申请", "材料")):
        return ["regulation:ccar_92:art_092_453", "regulation:ccar_92:art_092_467", "regulation:ccar_92:art_092_471"]
    if any(term in q for term in ("飞行前准备", "通信链路", "电池储备")):
        return ["regulation:ccar_92:art_092_623"]
    if any(term in q for term in ("C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序")):
        return ["regulation:ccar_92:art_092_679", "regulation:ccar_92:art_092_697"]
    if any(term in q for term in ("紧急迫降", "迫降地点", "终止飞行")):
        return ["regulation:ccar_92:art_092_701"]
    if any(term in q for term in ("事故报告", "严重受伤", "重大损失")):
        return ["regulation:ccar_92:art_092_687"]
    if any(term in q for term in ("应急反应预案", "飞行事故应急反应预案")):
        return ["regulation:ccar_92:art_092_667"]
    if any(term in q for term in ("维修记录", "维修放行")):
        return ["regulation:ccar_92:art_092_619", "regulation:ccar_92:art_092_709"]
    if any(term in q for term in ("作弊", "代考")):
        return ["regulation:ccar_92:art_092_099", "regulation:ccar_92:art_092_1015"]
    if any(term in q for term in ("处罚", "罚款", "违法", "违规")):
        # 裸"处罚/罚款"词曾无差别前置 CCAR-92 罚则（2026-07-11 全量评测实锤两类误伤）：
        company_policy = False
        other_regulation = any(term in q for term in ("暂行条例", "民用航空法", "民航法", "训练机构规范"))
        if not company_policy and not other_regulation:
            return [
                "regulation:ccar_92:art_092_1005",
                "regulation:ccar_92:art_092_1007",
                "regulation:ccar_92:art_092_1009",
                "regulation:ccar_92:art_092_1013",
                "regulation:ccar_92:art_092_1015",
            ]
    if any(term in q for term in ("吊销", "撤销", "失效", "注销")) and any(term in q for term in ("执照", "等级")):
        return [
            "regulation:ccar_92:art_092_067",
            "regulation:ccar_92:art_092_095",
            "regulation:ccar_92:art_092_1015",
        ]
    if any(term in q for term in ("运营合格证", "运营规范")) and any(term in q for term in ("撤销", "注销", "吊销")):
        return ["regulation:ccar_92:art_092_665"]
    if any(term in q for term in ("立即停止飞行", "停止飞行", "不能飞")):
        return ["regulation:ccar_92:art_092_633"]
    return []

def merge_hybrid_answer(csa_result: dict, rag_answer: str) -> str:
    csa_answer = (csa_result or {}).get("answer", "").strip()
    rag_answer = (rag_answer or "").strip()
    csa_topic = ((csa_result or {}).get("stats") or {}).get("topic")
    csa_data = (csa_result or {}).get("data") or {}
    zero_structured_hit = False
    if csa_topic in {"students", "instructors"}:
        zero_structured_hit = int(csa_data.get("count", 0) or 0) == 0
    elif csa_topic == "training_progress":
        zero_structured_hit = int(csa_data.get("record_count", 0) or 0) == 0
    if csa_answer and zero_structured_hit and csa_topic in {"students", "instructors", "training_progress"}:
        return csa_answer
    if csa_answer and rag_answer and csa_topic in {"students", "instructors", "training_progress"}:
        suppress_markers = (
            "无法确认",
            "未直接列出",
            "未提供",
            "未涉及",
            "建议您直接联系",
        )
        if any(marker in rag_answer for marker in suppress_markers):
            return csa_answer
    if csa_answer and rag_answer:
        return f"结构化数据：\n{csa_answer}\n\n知识库补充：\n{rag_answer}"
    return csa_answer or rag_answer
