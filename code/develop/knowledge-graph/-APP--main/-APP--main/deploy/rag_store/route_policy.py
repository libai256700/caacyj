"""Deterministic routing policy for CSA/RAG/hybrid/external decisions."""

from __future__ import annotations


STRUCTURED_TERMS = (
)

KNOWLEDGE_TERMS = (
    "CAAC", "法规", "条例", "条款", "制度", "规定", "要求", "流程",
    "注意事项", "要点", "知识点", "空域", "低空", "无人机",
    "飞行", "起飞", "降落", "气象", "操作", "考试", "培训课程",
    "为什么", "如何", "怎么", "说明", "解释", "分析", "建议",
    "解读", "影响", "风险", "方案", "安排", "改进", "优化", "重点",
    "特点", "变化", "趋势", "新增", "新题型", "考点变化",
)

HYBRID_MARKERS = ("同时", "另外", "并且", "以及", "还要", "顺便", "结合", "；", ";", "，")

TIMELINESS_TERMS = (
    "今天", "今日", "当天", "当前", "现在", "目前",
    "最新", "最近", "最近一天", "未完成", "剩余",
    "还剩", "还有多少", "进行中", "在招", "还在招",
)

STRONG_KNOWLEDGE_TERMS = (
    "CAAC", "法规", "条例", "条款", "空域", "低空", "禁飞",
    "UOM", "民航", "资质", "执照", "制度",
)

INSTRUCTOR_KB_TERMS = (
    "培训方向", "授课方向", "主讲方向", "擅长方向", "负责哪些培训", "负责什么培训",
)

# natural_key/来源表）无任何签字或飞行经历数据，这些词零误伤。
INSTRUCTOR_QUESTIONBANK_MARKERS = (
    "题库", "试题", "考题", "题目", "考点",
    "签字", "单飞", "飞行经历", "记录本",
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
)

EXTERNAL_COMPLETION_TERMS = (
    "上门", "到校", "到场", "企业内训", "团培", "定制",
    "UTC", "utc", "FPV", "fpv", "穿越机",
)

UNKNOWN_SPECIALTY_PRICE_TERMS = (
    "utc", "上门", "到校", "到场", "企业内训", "团培", "定制", "fpv", "穿越机",
)

PRICE_TERMS = ("价格", "多少钱", "费用", "学费", "收费", "报价")

MIGRATION_TRAINING_PRICE_TERMS = (
    "培训报名价格", "培训报名费", "培训价格", "培训费用", "培训学费", "培训收费",
    "课程价格", "课程费用", "课程报价", "报名价格", "报名费用", "报名费",
)

MIGRATION_LEARNER_RECORD_FIELDS = (
    "名单", "姓名", "成绩", "联系方式", "联系电话", "电话",
)

MIGRATION_LEARNER_RECORD_DISCLOSURE_TERMS = (
    "列出", "查询", "查看", "展示", "导出", "发我", "提供名单", "提供姓名",
    "提供成绩", "提供联系方式", "名单和成绩", "名单有哪些", "姓名有哪些",
    "成绩有哪些", "成绩是多少", "联系方式是什么", "电话是多少",
)

MIGRATION_LEARNER_RECORD_GOVERNANCE_TERMS = (
    "学员信息保存", "学员名单保存", "学员姓名保存", "学员成绩保存", "学员联系方式保存",
    "如何管理", "管理措施", "信息管理", "个人信息保护",
    "数据保护", "如何保护", "保护要求", "如何评定", "评定要求", "评分要求", "考核要求",
)

MIGRATION_SCHEDULING_PERSON_TERMS = (
    "负责培训排期", "培训排期的人员", "排期负责人", "负责排期的人员",
)

MIGRATION_SCHEDULING_IDENTITY_TERMS = (
    "谁负责培训", "谁负责排期", "负责人是谁", "人员是谁", "人员有哪些",
    "哪位负责", "告诉我谁", "排期人员名单", "排期负责人姓名", "排期负责人电话",
    "排期负责人联系方式", "列出排期", "查看排期负责人", "查询排期负责人",
)

MIGRATION_SCHEDULING_GOVERNANCE_TERMS = (
    "岗位职责", "有哪些职责", "任职要求", "资格要求", "具备哪些要求", "应具备",
    "排期流程", "排期规则", "排期原则", "如何安排", "如何制定排期",
)

MIGRATION_OUT_OF_SCOPE_COMPANY_NAMES = (
    "湖北云技科技有限公司",
    "云技科技公司",
    "湖北云技科技",
    "云技科技",
)

TEXTBOOK_PRICE_KNOWLEDGE_TERMS = (
    "教材", "航拍设备", "航拍无人机", "选购", "选择", "画质", "用途", "性能",
    "分为", "分类", "哪三类", "哪些类型",
)

GRAPH_FIRST_REASONING_TERMS = (
    "适合", "匹配", "推荐", "下一步", "路径", "规划", "诊断", "短板",
    "能否", "是否匹配", "依据", "证据", "影响", "反向", "缺口", "考察",
    "涉及哪些", "覆盖哪些", "合规", "风险", "承担", "引用哪些",
)

GRAPH_FIRST_DOMAIN_TERMS = {
    "regulation": ("法规", "条款", "合规", "民航法", "CCAR", "92部", "低空", "空域"),
    "question_bank": ("题库", "试题", "知识点", "教材", "考试", "能力", "技能"),
}

GRAPH_FIRST_MIN_DOMAINS = 2

GRAPH_FIRST_DOMAIN_COMBOS = (
)

GROUND_STATION_TREND_TERMS = (
    "特点", "变化", "趋势", "新增", "新题", "新题型", "考点变化", "出题特点",
)

TIME_SENSITIVE_CSA_TOPICS = {
}


def is_fact_dependent_generation(question: str) -> bool:
    """Generated deliverables still need RAG when they depend on internal facts."""
    q = question or ""
    return any(term in q for term in GENERATION_TERMS) and any(term in q for term in INTERNAL_FACT_TERMS)


def out_of_scope_internal_fact_reason(question: str) -> str | None:
    """Reject internal-data classes deliberately excluded from the snapshot."""
    q = question or ""
    if any(company_name in q for company_name in MIGRATION_OUT_OF_SCOPE_COMPANY_NAMES):
        return "company_identity"
    training_price = any(term in q for term in MIGRATION_TRAINING_PRICE_TERMS) or (
        any(term in q for term in PRICE_TERMS)
        and any(term in q for term in ("培训", "报名", "课程", "上门", "到校", "团培", "内训", "定制"))
    )
    if training_price:
        return "training_price"
    learner_record = "学员" in q and any(term in q for term in MIGRATION_LEARNER_RECORD_FIELDS)
    learner_disclosure = any(term in q for term in MIGRATION_LEARNER_RECORD_DISCLOSURE_TERMS)
    learner_governance = any(term in q for term in MIGRATION_LEARNER_RECORD_GOVERNANCE_TERMS)
    if learner_record and (learner_disclosure or not learner_governance):
        return "learner_records"
    scheduling_person = any(term in q for term in MIGRATION_SCHEDULING_PERSON_TERMS)
    scheduling_identity = "排期" in q and any(term in q for term in MIGRATION_SCHEDULING_IDENTITY_TERMS)
    scheduling_governance = any(term in q for term in MIGRATION_SCHEDULING_GOVERNANCE_TERMS)
    if scheduling_identity or (scheduling_person and not scheduling_governance):
        return "training_schedule_personnel"
    return None


def is_internal_profile_question(question: str) -> bool:
    """Internal company/role profile asks are not satisfied by job-count CSV stats."""
    q = question or ""
    return any(term in q for term in INTERNAL_PROFILE_TERMS)


def is_internal_policy_question(question: str) -> bool:
    """制度类问题必须走内部知识文档。"""
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

    if topic == "ground_station_exam" and any(term in q for term in GROUND_STATION_TREND_TERMS):
        return True

    explicit_knowledge = any(term in q for term in STRONG_KNOWLEDGE_TERMS)
    instructor_knowledge = False
    return has_structured and has_knowledge


# CSA 主题词劫持知识/制度类问题的通用护栏（2026-07-11 全量评测发现三个新模式，
# 知识库/制度内容。词集按 topic 收窄，避免误伤合法结构化问法
CSA_KNOWLEDGE_HIJACK_RULES = (
    # 地面站考试案例统计 vs 无线电物理知识（"地面站中无线电波长越长，绕射能力越？"）
    ("ground_station_exam", ("无线电", "波长", "频率", "绕射", "穿透")),
)


def is_misrouted_csa_knowledge_question(question: str, csa_result: dict | None) -> bool:
    """CSA 命中结构化主题，但问题在问知识/制度内容 → 应走知识库而非结构化表。"""
    if not csa_result:
        return False
    topic = csa_result.get("stats", {}).get("topic")
    q = question or ""
    for rule_topic, markers in CSA_KNOWLEDGE_HIJACK_RULES:
        if topic == rule_topic and any(term in q for term in markers):
            return True
    return False


def is_time_sensitive_structured_question(question: str, csa_result: dict | None) -> bool:
    """Prefer CSA when the user is clearly asking for current structured state."""
    if not csa_result:
        return False
    q = question or ""
    topic = csa_result.get("stats", {}).get("topic")
    if topic not in TIME_SENSITIVE_CSA_TOPICS:
        return False
    return any(term in q for term in TIMELINESS_TERMS)


def classify_route(question: str, csa_result: dict | None) -> str:
    """Route class before retrieval has run: csa, hybrid, graph_first, rag, or rag_external_candidate."""
    if is_time_sensitive_structured_question(question, csa_result):
        return "csa"
    if is_graph_first_question(question):
        return "graph_first"
    if is_misrouted_csa_knowledge_question(question, csa_result):
        return "rag"
    if csa_result and not is_hybrid_question(question, csa_result):
        return "csa"
    if csa_result:
        return "hybrid"
    if needs_external_candidate(question, [], csa_result):
        return "rag_external_candidate"
    return "rag"


def needs_external_candidate(question: str, internal_sources: list[dict] | None, csa_result: dict | None) -> bool:
    """外部问法不应停在空泛的内部检索结果上。"""
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
    has_textbook_source = "无人机理论书籍" in source_text or "教材" in source_text
    if (
        price_question
        and has_textbook_source
        and any(term in q for term in TEXTBOOK_PRICE_KNOWLEDGE_TERMS)
        and not specific_external_service
    ):
        return False
    has_internal_price_source = False
    if price_question and specific_external_service:
        return True
    return bool(price_question and not has_internal_price_source)
