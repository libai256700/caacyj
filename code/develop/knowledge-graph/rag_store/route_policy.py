"""Deterministic routing policy for CSA/RAG/hybrid/external decisions."""

from __future__ import annotations


STRUCTURED_TERMS = (
    "价格", "多少钱", "费用", "学费", "收费",
    "学员", "学生", "教员", "培训记录", "培训进度",
    "岗位", "招聘", "职位", "薪资",
    "客户", "客资", "咨询", "意向",
)

KNOWLEDGE_TERMS = (
    "CAAC", "法规", "条例", "条款", "制度", "规定", "要求", "流程",
    "注意事项", "要点", "知识点", "空域", "低空", "无人机",
    "飞行", "起飞", "降落", "气象", "操作", "考试", "培训课程",
    "为什么", "如何", "怎么", "说明", "解释", "分析", "建议",
    "解读", "影响", "风险", "方案", "安排", "改进", "优化", "重点",
)

HYBRID_MARKERS = ("同时", "另外", "并且", "以及", "还要", "顺便", "结合", "；", ";", "，")

STRONG_KNOWLEDGE_TERMS = (
    "CAAC", "法规", "条例", "条款", "空域", "低空", "禁飞",
    "UOM", "民航", "资质", "执照", "制度", "员工手册", "薪酬体系",
    "入职流程", "考勤", "保密协议", "客户管理与跟进制度",
)

GENERATION_TERMS = (
    "生成", "设计", "拟定", "撰写", "编写", "制定", "策划", "输出",
    "面试题", "面试问题", "招聘JD", "JD", "话术", "SOP", "方案",
    "培训方案", "复盘", "报告", "脚本", "模板",
)

INTERNAL_FACT_TERMS = (
    "公司", "业务", "发展", "结构", "部门", "岗位", "岗位职责", "职责",
    "课程", "产品", "价格", "制度", "流程", "学员", "教员", "客户",
    "客资", "培训", "招聘", "职位", "助教",
)

INTERNAL_PROFILE_TERMS = (
    "组织架构", "公司架构", "公司结构", "业务发展", "业务方向", "岗位职责",
    "工作职责", "职责说明", "企业文化", "价值观", "公司介绍", "业务板块",
    "公司简介", "介绍一下", "产品介绍",
)

INTERNAL_POLICY_TERMS = (
    "人事制度", "员工手册", "薪酬体系", "入职流程", "面试流程", "考勤",
    "保密协议", "客户管理与跟进制度", "跟进制度", "管理制度", "制度要求",
)

EXTERNAL_COMPLETION_TERMS = (
    "价格", "多少钱", "费用", "学费", "收费", "报价",
    "上门", "到校", "到场", "企业内训", "团培", "定制",
    "UTC", "utc", "FPV", "fpv", "穿越机",
)

UNKNOWN_SPECIALTY_PRICE_TERMS = (
    "utc", "上门", "到校", "到场", "企业内训", "团培", "定制", "fpv", "穿越机",
)

PRICE_TERMS = ("价格", "多少钱", "费用", "学费", "收费", "报价")

GRAPH_FIRST_REASONING_TERMS = (
    "适合", "匹配", "推荐", "下一步", "路径", "规划", "诊断", "短板",
    "能否", "是否匹配", "依据", "证据", "影响", "反向", "缺口", "考察",
    "涉及哪些", "覆盖哪些", "合规", "风险", "承担", "引用哪些",
)

GRAPH_FIRST_DOMAIN_TERMS = {
    "customer": ("客户", "客资", "咨询", "意向", "跟进"),
    "student": ("学员", "学生", "训练", "考试记录", "培训进度"),
    "course": ("课程", "培训", "班型", "产品", "价格", "学费"),
    "instructor": ("教员", "讲师", "教练"),
    "job_market": ("岗位", "岗位职责", "招聘", "职位", "面试", "薪资"),
    "regulation": ("法规", "条款", "合规", "民航法", "CCAR", "92部", "低空", "空域"),
    "question_bank": ("题库", "试题", "知识点", "教材", "考试", "能力", "技能"),
    "company": ("公司", "组织架构", "公司结构", "业务发展", "制度", "产品说明"),
}

GRAPH_FIRST_MIN_DOMAINS = 2

GRAPH_FIRST_DOMAIN_COMBOS = (
    ("customer", "course"),
    ("student", "course"),
    ("student", "instructor"),
    ("job_market", "question_bank"),
    ("job_market", "course"),
    ("course", "regulation"),
    ("course", "question_bank"),
    ("course", "instructor"),
    ("company", "job_market"),
    ("company", "course"),
)


def is_fact_dependent_generation(question: str) -> bool:
    """Generated deliverables still need RAG when they depend on internal facts."""
    q = question or ""
    return any(term in q for term in GENERATION_TERMS) and any(term in q for term in INTERNAL_FACT_TERMS)


def is_internal_profile_question(question: str) -> bool:
    """Internal company/role profile asks are not satisfied by job-count CSV stats."""
    q = question or ""
    return any(term in q for term in INTERNAL_PROFILE_TERMS)


def is_internal_policy_question(question: str) -> bool:
    """HR/customer-management policy asks must use internal knowledge documents."""
    q = question or ""
    return any(term in q for term in INTERNAL_POLICY_TERMS)


def requires_internal_kb(question: str) -> bool:
    """Questions whose answer should come from internal docs, not CSV aggregates."""
    return (
        is_fact_dependent_generation(question)
        or is_internal_profile_question(question)
        or is_internal_policy_question(question)
    )


def graph_first_domains(question: str) -> list[str]:
    """Business domains mentioned by a question, for graph-first routing."""
    q = question or ""
    domains = []
    for domain, terms in GRAPH_FIRST_DOMAIN_TERMS.items():
        if any(term in q for term in terms):
            domains.append(domain)
    return domains


def is_graph_first_question(question: str) -> bool:
    """Questions that need entity relation paths before ordinary text synthesis."""
    q = question or ""
    if not q:
        return False
    domains = graph_first_domains(q)
    domain_set = set(domains)
    has_multi_domain = len(domain_set) >= GRAPH_FIRST_MIN_DOMAINS
    has_business_combo = any(left in domain_set and right in domain_set for left, right in GRAPH_FIRST_DOMAIN_COMBOS)
    has_reasoning = any(term in q for term in GRAPH_FIRST_REASONING_TERMS)
    if not (has_multi_domain and has_business_combo and has_reasoning):
        return False

    # Writing deliverables can remain hybrid RAG unless the prompt asks for
    # matching, diagnosis, recommendation, path planning, or a gap analysis.
    if any(term in q for term in GENERATION_TERMS) and not any(
        term in q for term in ("推荐", "匹配", "诊断", "路径", "规划", "适合", "能否", "缺口")
    ):
        return False
    return True


def is_hybrid_question(question: str, csa_result: dict | None) -> bool:
    """Detect questions where a CSA hit covers only part of the ask."""
    if not csa_result:
        return False
    q = question or ""
    has_structured = any(term in q for term in STRUCTURED_TERMS)
    has_knowledge = any(term in q for term in KNOWLEDGE_TERMS)
    has_compound_joiner = any(term in q for term in HYBRID_MARKERS)
    topic = csa_result.get("stats", {}).get("topic")

    explicit_knowledge = any(term in q for term in STRONG_KNOWLEDGE_TERMS)
    if topic in {"prices", "students", "jobs", "customers", "training_progress"}:
        if requires_internal_kb(q):
            return True
        return has_structured and has_knowledge and (has_compound_joiner or explicit_knowledge)
    return has_structured and has_knowledge


def classify_route(question: str, csa_result: dict | None) -> str:
    """Route class before retrieval has run: csa, hybrid, graph_first, rag, or rag_external_candidate."""
    if is_graph_first_question(question):
        return "graph_first"
    if csa_result and not is_hybrid_question(question, csa_result):
        return "csa"
    if csa_result:
        return "hybrid"
    if needs_external_candidate(question, [], csa_result):
        return "rag_external_candidate"
    return "rag"


def needs_external_candidate(question: str, internal_sources: list[dict] | None, csa_result: dict | None) -> bool:
    """External customer asks must not stop at an empty or generic internal KB result."""
    q = question or ""
    if not any(term in q for term in EXTERNAL_COMPLETION_TERMS):
        return False
    if csa_result and csa_result.get("route") == "csa":
        return False
    if not internal_sources:
        return any(term in q for term in PRICE_TERMS) and any(
            term in q.lower() for term in UNKNOWN_SPECIALTY_PRICE_TERMS
        )

    source_text = " ".join(
        str(src.get("doc_name") or src.get("source_doc") or src.get("file") or "")
        for src in internal_sources
    )
    price_question = any(term in q for term in PRICE_TERMS)
    specific_external_service = any(term in q.lower() for term in UNKNOWN_SPECIALTY_PRICE_TERMS)
    has_internal_price_source = "价格表" in source_text or "价格" in source_text
    if price_question and specific_external_service:
        return True
    return bool(price_question and not has_internal_price_source)
