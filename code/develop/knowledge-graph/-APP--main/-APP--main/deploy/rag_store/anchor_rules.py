"""法规锚点规则唯一事实源（2026-07-12 审计闭环）。

bm25_index（累加式：全部命中规则的 chunk 依序插入检索首位）与
answer_policy.regulation_priority_source_ids（首匹配式：命中即条款优先注入）
此前各自手工维护一份内容相近的规则表，已三次同步修改，漂移只是时间问题。
本模块是两处共用的唯一事实源；两处的消费语义差异（累加 vs 首匹配）保留原设计。

规则语义：exclude 任一命中 → 不触发；否则 anchors 任一命中 且 triggers 任一命中 → 触发。
改锚纪律：加规则前先查语料真值（sqlite LIKE 数 chunk 分布）+ 扫全量题库触发影响面。
"""
from __future__ import annotations

UAS_PREFIX = "regulation:uas_flight_management_interim_regulation"

# 《无人驾驶航空器飞行管理暂行条例》条款锚点。
# 罚则/禁止行为类问法的多法规路由（2026-07-12）：裸"处罚/罚款"历史规则默认罚则都在
# CCAR-92，条例入库后该假设过时——条例专属主题（监护人/产品质量/重大设计更改/农用/
# 拍摄）的问法按语料真值直接锚到条例条文，其余仍走 answer_policy 的 CCAR 默认规则。
UAS_PRIORITY_RULES = [
    {
        "anchors": ("无人驾驶航空器飞行管理暂行条例", "飞行管理暂行条例", "无人机飞行管理暂行条例"),
        "triggers": ("施行", "实施", "生效", "什么时候", "哪天", "日期", "公布", "哪一号令", "第几号"),
        "chunk_ids": [f"{UAS_PREFIX}:art_063"],
    },
    {
        "anchors": ("无人驾驶航空器管制空域", "无人机管制空域", "管制空域"),
        "triggers": ("包括", "哪些区域", "范围", "划设", "怎么划"),
        # 裸"管制空域"是通用航空术语：点名民航法的问法应由民航法规则接管
        "exclude": ("民航法", "民用航空法"),
        "chunk_ids": [f"{UAS_PREFIX}:art_019", f"{UAS_PREFIX}:art_020"],
    },
    {
        # 未实名登记罚则真值在第47条（200元以下/情节严重2000-2万元）；
        # 必须先于 answer_policy 裸"实名登记"锚（92.205 登记信息项）命中
        "anchors": ("实名登记",),
        "triggers": ("处罚", "罚款", "罚则", "法律责任", "后果", "怎么处理", "如何处理"),
        "chunk_ids": [f"{UAS_PREFIX}:art_047"],
    },
    {
        # 未经批准在管制空域飞行罚款真值在第51条第2款（500元以下/情节严重1000-1万）
        "anchors": ("未经批准在管制空域", "未经批准操控", "擅自在管制空域"),
        "triggers": ("处罚", "罚款", "罚则", "后果"),
        "chunk_ids": [f"{UAS_PREFIX}:art_051"],
    },
    {
        # 无/限制民事行为能力人违规操控，监护人罚款真值在第50条（500-5000元）
        "anchors": ("监护人", "无民事行为能力", "限制民事行为能力"),
        "triggers": ("罚款", "处罚", "罚则", "后果"),
        "chunk_ids": [f"{UAS_PREFIX}:art_050"],
    },
    {
        # 违反产品质量/标准化管理的处罚部门真值在第54条（县级以上市场监督管理部门）
        "anchors": ("产品质量", "标准化管理"),
        "triggers": ("处罚", "罚款", "哪个部门", "什么部门", "由谁"),
        "chunk_ids": [f"{UAS_PREFIX}:art_054"],
    },
    {
        # 重大设计更改未重新申请适航许可的罚则真值在第46条（货值1-5倍罚款）
        "anchors": ("重大设计更改",),
        "triggers": ("处罚", "罚款", "后果", "面临什么"),
        "chunk_ids": [f"{UAS_PREFIX}:art_046"],
    },
    {
        # 常规农用无人驾驶航空器作业飞行（≤150千克）免运营合格证真值在第11条
        "anchors": ("农用无人驾驶航空器", "农用无人机"),
        "triggers": ("运营合格证",),
        "chunk_ids": [f"{UAS_PREFIX}:art_011"],
    },
    {
        # 农用无人驾驶航空器定义在第62条第(八)项，埋于长chunk后段词法难命中（07-12审计）
        "anchors": ("农用无人驾驶航空器", "农用无人机"),
        "triggers": ("定义", "是指", "含义", "什么是"),
        "chunk_ids": [f"{UAS_PREFIX}:art_062"],
    },
    {
        # 违法拍摄军事设施/军工设施/涉密场所的禁止行为在第34条
        "anchors": ("拍摄",),
        "triggers": ("禁止", "违法", "哪些场所", "涉密"),
        "chunk_ids": [f"{UAS_PREFIX}:art_034"],
    },
    {
        # 口语"商用/接活/挣钱"在语料里没有词法落点——法规写的是"经营性活动/运营
        # 合格证"，于是这类问法整片跑到题库上：2026-07-26 微信实测"中型多旋翼超视距
        # 可以商用吗"召回 6 条里 5 条是题库，模型只好凭记忆编，答出"中型=空机重量
        # >4千克"（错：第62条中型是最大起飞重量不超过150千克，4千克是轻型的空机重量线）。
        # 语料真值：条例第11条=除微型外单位须取运营合格证、经营性还须为营利法人；
        # 92.603=运营许可适用范围与免除清单（只免微型和常规农用）；92.645=颁发条件。
        "anchors": ("商用", "商业运营", "商业飞行", "商业用途", "商业化", "经营性", "营利", "接活", "挣钱", "盈利"),
        "triggers": (
            "无人机", "无人驾驶航空器", "多旋翼", "固定翼", "超视距", "视距内",
            "航拍", "测绘", "植保", "巡检", "作业", "运营", "资质", "条件",
        ),
        "chunk_ids": [
            f"{UAS_PREFIX}:art_011",
            "regulation:ccar_92:art_092_603",
            "regulation:ccar_92:art_092_645",
        ],
    },
    {
        # 分级定义真值在第62条第(二)-(六)项，埋在长 chunk 中段词法难命中。
        # 中型=最大起飞重量不超过150千克（不含微/轻/小），不是任何"空机重量"区间。
        "anchors": (
            "微型无人", "轻型无人", "小型无人", "中型无人", "大型无人",
            "中型多旋翼", "小型多旋翼", "中型固定翼", "无人机分类", "无人机分级",
            "无人驾驶航空器分类",
        ),
        "triggers": (
            "定义", "是指", "什么是", "含义", "怎么分", "分类", "分级",
            "多少千克", "多少公斤", "多重", "重量", "空机重量", "最大起飞重量",
            "算不算", "属于", "区别", "标准是",
        ),
        "chunk_ids": [f"{UAS_PREFIX}:art_062"],
    },
]


CAL_PREFIX = "regulation:cn_civil_aviation_law_2025"

# 《中华人民共和国民用航空法》(2025修订) 主题锚点（2026-07-13）。
# 这批问法不点名"民航法"（bm25_index 的 CIVIL_LAW_ARTICLE_BOOST_RULES 要求点名，
# 管不到），且罚则/登记主题被 CCAR-92 词法垄断——按语料真值直锚民航法条文。
# 触发词均已扫全量题库影响面：值勤时间/境外租赁/必须携带/安全检查/未取得航空人员执照
# 在 2051 题里只命中各自的民航法题，"未取得操控员执照"(CCAR题)不含"航空人员"不误伤。
CAL_PRIORITY_RULES = [
    {
        # 机组违反飞行/值勤/休息时间规定：企业每次飞行1-10万罚款真值在第243条
        "anchors": ("值勤时间",),
        "triggers": ("罚款", "处罚", "罚则", "违反"),
        "chunk_ids": [f"{CAL_PREFIX}:art_243"],
    },
    {
        # 境外租赁航空器国籍登记条件（承租人合规+自配机组+先注销原国籍）在第14条
        "anchors": ("境外租赁",),
        "triggers": ("国籍登记", "登记"),
        "chunk_ids": [f"{CAL_PREFIX}:art_014"],
    },
    {
        # 飞行时必须携带的文件清单（国籍登记证书/适航证书/执照/记录簿等）在第78条
        "anchors": ("必须携带", "应当携带"),
        "triggers": ("文件", "证书"),
        "chunk_ids": [f"{CAL_PREFIX}:art_078"],
    },
    {
        # 机场/公共航空运输企业不依法开展安全检查的罚则在第247条
        "anchors": ("安全检查",),
        "triggers": ("罚款", "处罚", "机场", "开包"),
        "chunk_ids": [f"{CAL_PREFIX}:art_247"],
    },
    {
        # 未取得航空人员执照从事民航活动：个人1-5万/所属单位10-50万罚款在第237条
        "anchors": ("未取得航空人员执照", "未取得相关航空人员执照"),
        "triggers": ("罚款", "处罚", "单位"),
        "chunk_ids": [f"{CAL_PREFIX}:art_237"],
    },
]


MD92_PREFIX = "regulation:uas_operator_license_exam_management_2024"

# 《操控员执照考试管理办法》(MD-92-FS-02) 主题锚点（2026-07-25）。
# "理论考试考什么/大纲覆盖哪些模块"类问法文档级已命中 MD-92，但知识范围清单段
# （2.2 节（1）-（9）条）常被元数据头 chunk 挤出摘录窗，答案只能说"未列出清单"
# （test100 reg_08/reg_14 实锤）。影响面已扫：全量 2056 题仅 3 题触发且期望源
# 均含 MD-92，只升不降。
MD92_PRIORITY_RULES = [
    {
        "anchors": ("理论考试", "考试大纲"),
        "triggers": ("大纲", "知识模块", "知识范围", "考试科目", "考察", "考哪些", "哪些内容", "考什么", "涵盖"),
        "chunk_ids": [f"{MD92_PREFIX}:clause_002_003_002"],
    },
]


def rule_matches(question: str, rule: dict) -> bool:
    q = question or ""
    if any(term in q for term in rule.get("exclude", ())):
        return False
    return any(term in q for term in rule["anchors"]) and any(
        term in q for term in rule["triggers"]
    )


def accumulate_chunk_ids(question: str, rules: list[dict]) -> list[str]:
    """bm25 语义：全部命中规则的 chunk_ids 依序累加去重。"""
    chunk_ids: list[str] = []
    for rule in rules:
        if rule_matches(question, rule):
            chunk_ids.extend(rule["chunk_ids"])
    seen: set[str] = set()
    return [cid for cid in chunk_ids if not (cid in seen or seen.add(cid))]


def first_match_chunk_ids(question: str, rules: list[dict]) -> list[str] | None:
    """answer_policy 语义：首个命中规则的 chunk_ids，无命中返回 None。"""
    for rule in rules:
        if rule_matches(question, rule):
            return list(rule["chunk_ids"])
    return None
