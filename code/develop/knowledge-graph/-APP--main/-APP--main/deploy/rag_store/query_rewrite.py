#!/usr/bin/env python3
"""
Query Rewrite 模块

输入: 用户原始问题
输出: {
  rewritten: 改写后的问题,
  keywords: [关键词列表],
  coverage_terms: [概览型问题必须逐项覆盖的术语],
  entities: [{name, type, confidence}],
  intent: "regulation" | "company" | "job" | "training" | "general",
  need_kg: bool
}
"""

import re
from typing import Dict, List

# ============ 意图关键词词典（快速匹配，不需要 LLM）============

INTENT_PATTERNS = {
    "regulation": [
        "法规", "法律", "条例", "规定", "管理办法", "标准", "资质",
        "合格证", "适航", "空域", "飞行规则", "处罚", "罚款",
        "CCAR", "行政许可", "执照要求", "飞行申请", "实名登记", "登记材料"
    ],
    "company": [
        "公司", "云技", "介绍", "业务", "课程", "价格", "费用", "多少钱",
        "报名", "培训", "地址", "电话", "联系", "招聘", "员工"
    ],
    "job": [
        "就业", "薪资", "工资", "岗位", "招聘", "工作", "找工作",
        "待遇", "前景", "人才", "市场需求", "就业方向", "岗位去向"
    ],
    "training": [
        "CAAC", "考证", "实操", "考试", "题库", "通过率", "教学",
        "培训", "学习", "练习", "试题", "答案", "教练", "教员",
        "中空飞行", "实名登记", "模拟训练"
    ],
    "general": [
        "无人机", "多旋翼", "固定翼", "飞行", "操作", "气象",
        "原理", "系统", "技术"
    ]
}

REGULATION_GATE_TERMS = (
    "无犯罪记录", "犯罪记录", "刑事处罚", "刑事犯罪", "故意犯罪",
    "醉驾", "酒驾", "危险驾驶", "前科", "案底", "原文", "条文",
    "无犯罪证明", "无犯罪记录证明", "无犯罪记录声明", "声明",
)

REGULATION_ELIGIBILITY_TERMS = (
    "申请条件", "申请材料", "提交材料", "报名材料", "所需材料",
    "不得申请", "不能申请", "禁止行为", "虚假材料", "实名登记",
    "登记材料", "国籍登记", "适航证", "特许飞行证",
    "登记注销", "登记信息变更", "信息更新", "补发",
    "运营合格证", "运营规范", "运行人", "运营人", "责任保险", "信息报送", "年度运营报告",
    "有效期", "更新", "续期", "运营许可",
    "持续适航", "维修管理", "维修记录", "维修放行", "飞行前准备", "缺陷", "故障", "失效",
    "通信链路", "电池储备", "维修责任人",
    "处罚", "罚款", "吊销", "撤销", "注销", "失效", "停飞",
    "停止飞行", "作弊", "代考", "欺骗", "贿赂",
    "超视距运行", "夜间飞行", "视距内运行",
    "C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序",
    "紧急迫降", "迫降地点", "终止飞行", "应急预案", "应急反应预案",
    "事故报告", "不安全事件", "严重受伤", "严重人员伤亡", "重大损失", "重大财产损失", "事故",
    "暂停报名考试资格", "停止报名考试资格", "训练机构",
    "材料", "哪些材料", "特殊条件",
)

REGULATION_LICENSE_TERMS = (
    "CAAC", "执照", "报考", "报名", "申请条件", "申请材料",
    "合格证", "92部", "CCAR", "第92", "第 92",
)

UAV_DETECTION_OVERVIEW_TERMS = (
    "目视侦察",
    "声波探测",
    "光电探测",
    "电磁频谱探测",
    "多普勒雷达探测",
)

# 已知实体白名单（公司、产品、人物、法规、组织等）
KNOWN_ENTITIES = {
    "文汉清": ("Person", 0.95),
    "王佳丽": ("Person", 0.95),
    "万志峰": ("Person", 0.95),
    "沙浩": ("Person", 0.95),
    "梅莎": ("Person", 0.90),
    "CAAC": ("Organization", 0.98),
    "中国民航局": ("Organization", 0.98),
    "CCAR-92": ("Regulation", 0.95),
    "CCAR-71": ("Regulation", 0.90),
    "民航法": ("Regulation", 0.95),
    "民用航空法": ("Regulation", 0.98),
    "民用无人驾驶航空器运行安全管理规则": ("Regulation", 0.95),
    "民用航空空中交通管理规则": ("Regulation", 0.90),
    "无人驾驶航空器": ("AircraftType", 0.90),
    "低空空域": ("KnowledgePoint", 0.90),
    "管制空域": ("KnowledgePoint", 0.90),
    "武汉": ("Location", 0.95),
    "湖北": ("Location", 0.90),
    "硚口": ("Location", 0.85),
    "智联招聘": ("Platform", 0.95),
    "猎聘": ("Platform", 0.95),
    "前程无忧": ("Platform", 0.95),
}

# 长尾入口的同义词和文档锚点。只扩展检索词，不改变 chunk_id 契约。
KEYWORD_EXPANSIONS = [
    (("侧风", "横风"), ["侧风", "横风", "起飞", "着陆", "起降", "气象", "风向", "风速"]),
    (("云高", "能见度", "最低天气标准", "天气标准"), ["云高", "能见度", "云层高度", "最低天气标准", "气象", "天气标准"]),
    (("中空飞行",), ["中空飞行", "飞行高度", "高度范围", "概述", "空中交通管制"]),
    (("信号失联", "失联", "失控保护", "failsafe"), ["信号失联", "失联处置", "失控保护", "Failsafe", "返航", "应急处置", "操作注意事项", "无人机飞行手册"]),
    (("GPS", "北斗", "导航系统"), ["GPS", "北斗", "导航系统", "定位", "导航", "系统组成", "无人机任务规划", "无人机操作注意事项"]),
    (("旋翼无人机和固定翼无人机", "旋翼无人机与固定翼无人机", "结构上有什么主要区别", "结构差异"), ["旋翼无人机", "固定翼无人机", "固定翼", "结构差异", "旋翼系统", "飞行原理与飞行性能", "理论题库_旋翼无人机"]),
    (("实名登记", "登记材料"), ["实名登记", "登记材料", "登记信息", "无人机实名登记系统", "民用无人驾驶航空器实名制登记管理规定"]),
    (("海拔高度", "升力", "动力系统", "动力匹配"), ["海拔高度", "升力", "动力", "空气密度", "飞行原理与飞行性能", "飞行原理", "气象"]),
    (("雨中飞行", "雷暴", "阵风", "高温环境", "风速", "气象风险"), ["气象", "天气", "雷暴", "阵风", "降雨", "高温", "风速", "理论题库_气象", "无人机操作注意事项"]),
    (("逆风起飞", "顺风起飞"), ["逆风起飞", "顺风起飞", "升力", "起飞性能", "飞行原理", "飞行原理与飞行性能"]),
    (("安全飞行规范", "飞行规范", "安全飞行"), ["安全飞行", "飞行规范", "操作注意事项", "安全事项", "应急处置", "无人机飞行手册"]),
    (("BEC", "IMU", "惯性测量单元", "电池存储", "电池保养"), ["系统组成", "BEC", "IMU", "惯性测量单元", "电池", "存储", "保养", "无人机系统"]),
    (("数据链路", "通信链路", "通讯链路"), ["数据链路", "通信链路", "通讯稳定", "通信安全", "系统组成", "无人机系统", "图传链路"]),
    (("超视距飞行", "超视距运行"), ["超视距", "超视距飞行", "运行要求", "安全要求", "CCAR-92", "训练机构规范", "无人机飞行手册"]),
    (("C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序"), ["C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序", "CCAR-92部", "第92.697条"]),
    (("紧急迫降", "迫降地点", "终止飞行"), ["紧急迫降地点", "迫降地点", "终止飞行程序", "CCAR-92部", "第92.701条"]),
    (("事故报告", "严重受伤", "严重人员伤亡", "重大损失", "重大财产损失", "事故应急反应预案", "应急反应预案"), ["事故报告", "严重人员伤亡", "重大财产损失", "飞行事故应急反应预案", "CCAR-92部", "第92.687条", "第92.667条"]),
    (("安全事故", "事故后", "报告和处理", "事故报告", "上报"), ["安全事故", "事故报告", "报告流程", "上报", "应急程序", "公安机关", "无人机操作注意事项", "无人机飞行手册"]),
    (("编队飞行", "编队"), ["编队飞行", "协同飞行", "安全事项", "飞行原理", "飞行原理与飞行性能", "无人机操作注意事项"]),
    (("禁飞区", "限飞区", "误入"), ["禁飞区", "限飞区", "空中交通管制", "无人机飞行手册", "地理围栏", "UOM"]),
    (("客户管理", "跟进制度", "客户跟进", "执照培训项目"), ["客户管理", "跟进制度", "客户跟进", "执照培训项目", "CAAC培训", "有效客户", "咨询组", "运营组"]),
]

# ============ 名词短语 / 型号词抽取（规则路径的判别信号增强）============

# 块成员分两级：NOUNISH 可收尾/记名词票，LINK 只能出现在块中间或开头。
# 块必须以名词性词收尾且至少含一个名词性词，避免"需要满足"这类纯动词串。
_PHRASE_NOUNISH_FLAGS = {"n", "nz", "ng", "nt", "ns", "nr", "vn", "an", "eng"}
_PHRASE_LINK_PREFIXES = ("v", "a", "t", "s", "b", "f")
_PHRASE_STOP_TOKENS = {
    "需要", "满足", "进行", "采取", "出现", "可以", "应该", "应当",
    "什么", "哪些", "如何", "怎么", "怎样", "为什么", "多少", "代表",
    "根据", "关于", "属于", "包括", "分别", "情况", "问题", "方面",
}

_MODEL_CODE_RE = re.compile(r"[A-Za-z]+-?\d+[A-Za-z0-9]*|\d+[A-Za-z]+[A-Za-z0-9]*")
_ALNUM_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _phrase_token_kind(word: str, flag: str) -> str:
    """token 分类：nounish / link / break。"""
    if word in _PHRASE_STOP_TOKENS:
        return "break"
    if flag in _PHRASE_NOUNISH_FLAGS:
        return "nounish"
    # 字母数字串（6S2P 等）jieba 可能标 x/m/eng，只要含字母就按名词处理
    if _ALNUM_WORD_RE.fullmatch(word) and not word.isdigit():
        return "nounish"
    if flag.startswith(_PHRASE_LINK_PREFIXES):
        return "link"
    return "break"


def extract_content_phrases(query: str, max_phrases: int = 4) -> List[str]:
    """用词性标注抽取连续内容词块（如"空域保持能力""雷暴天气""失速现象"）。

    这些多词短语在 BM25 查询中等价于给其成分词各加一票权重，
    把判别性名词短语从疑问句噪声里提出来。抽取失败时静默返回空。
    """
    try:
        import jieba.posseg as pseg
        tokens = [(w.strip(), flag) for w, flag in pseg.cut(query) if w.strip()]
    except Exception:
        return []

    phrases: List[str] = []
    block: List[tuple] = []  # (word, kind)

    def flush():
        while block and block[-1][1] != "nounish":
            block.pop()
        if len(block) >= 2 and any(k == "nounish" for _, k in block):
            phrase = "".join(w for w, _ in block)
            if 3 <= len(phrase) <= 10:
                phrases.append(phrase)
        block.clear()

    for word, flag in tokens:
        kind = _phrase_token_kind(word, flag)
        if kind == "break":
            flush()
        else:
            block.append((word, kind))
    flush()

    seen = set()
    unique = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique[:max_phrases]


def extract_model_codes(query: str) -> List[str]:
    """抽取字母数字混排的型号/条款词（6S2P、CCAR-92、C2），判别力极高。"""
    return [m for m in _MODEL_CODE_RE.findall(query or "") if len(m) >= 2]


# ============ Query Rewrite Engine ============

class QueryRewriter:
    """只读规则改写、实体抽取与意图路由。"""

    def rewrite(self, query: str, use_llm: bool = False) -> Dict:
        """
        主入口：改写问题并提取所有元信息
        
        Args:
            query: 用户原始问题
            use_llm: 是否用 LLM 做深度改写（False 时只做规则匹配）
        """
        if use_llm is not False:
            raise ValueError("cloud query rewrite is rule-only")

        # Step 1: 规则匹配（快速，零成本）
        entities = self._extract_entities_rule(query)
        intent = self._classify_intent_rule(query)
        keywords = self._extract_keywords(query, entities)
        coverage_terms = (
            list(UAV_DETECTION_OVERVIEW_TERMS)
            if self._looks_like_uav_detection_overview(query)
            else []
        )
        
        rewritten = query
        if self._looks_like_regulation_gate_question(query):
            rewritten = self._rewrite_regulation_gate_query(query)
        elif self._looks_like_regulation_eligibility_question(query):
            rewritten = self._rewrite_regulation_eligibility_query(query)
        elif self._looks_like_uav_detection_overview(query):
            rewritten = f"{query} {' '.join(UAV_DETECTION_OVERVIEW_TERMS)}"
        elif self._looks_like_gps_interference_comparison(query):
            rewritten = (
                f"{query} GPS压制式干扰 GPS欺骗干扰 "
                "转发式欺骗干扰 生产式欺骗干扰"
            )
        
        return {
            "original": query,
            "rewritten": rewritten,
            "keywords": keywords,
            "coverage_terms": coverage_terms,
            "entities": entities,
            "intent": intent,
            "need_kg": intent in ("regulation", "company", "training", "general"),
        }

    @staticmethod
    def _looks_like_uav_detection_overview(query: str) -> bool:
        q = query or ""
        return (
            "无人机" in q
            and any(term in q for term in ("防控", "反制"))
            and any(
                term in q
                for term in ("探测技术", "侦测技术", "探测手段", "侦测手段")
            )
            and any(term in q for term in ("主要", "哪些", "包括"))
        )

    @staticmethod
    def _looks_like_gps_interference_comparison(query: str) -> bool:
        q = query or ""
        return (
            "GPS" in q.upper()
            and "压制" in q
            and "欺骗" in q
            and any(term in q for term in ("区别", "不同", "差异", "对比"))
        )
    
    def _extract_entities_rule(self, query: str) -> List[Dict]:
        """规则匹配：从白名单中提取已知实体"""
        found = []
        for name, (etype, conf) in KNOWN_ENTITIES.items():
            if name in query:
                found.append({"name": name, "type": etype, "confidence": conf})
        if self._looks_like_regulation_gate_question(query) and not any(e["name"] == "CCAR-92" for e in found):
            found.append({"name": "CCAR-92", "type": "Regulation", "confidence": 0.94})

        # 去重 + 按信心降序
        seen = set()
        unique = []
        for e in sorted(found, key=lambda x: -x["confidence"]):
            if e["name"] not in seen:
                seen.add(e["name"])
                unique.append(e)
        return unique
    
    def _classify_intent_rule(self, query: str) -> str:
        """规则匹配：判断查询意图"""
        if self._looks_like_regulation_gate_question(query):
            return "regulation"
        if self._looks_like_regulation_eligibility_question(query):
            return "regulation"

        scores = {}
        for intent, patterns in INTENT_PATTERNS.items():
            score = sum(1 for p in patterns if p in query)
            scores[intent] = score
        
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"
    
    def _extract_keywords(self, query: str, entities: List[Dict], max_kw: int = 12) -> List[str]:
        """提取关键词：去停用词 + 保留实体名 + 长词优先"""
        is_regulation_gate = self._looks_like_regulation_gate_question(query)
        is_regulation_eligibility = self._looks_like_regulation_eligibility_question(query)
        is_uav_detection_overview = self._looks_like_uav_detection_overview(query)
        is_gps_interference_comparison = self._looks_like_gps_interference_comparison(
            query
        )
        stopwords = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
            "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
            "怎么", "什么", "为什么", "哪里", "哪个", "多少", "怎样", "如何", "可以",
            "吗", "呢", "吧", "啊", "能", "还是", "还有", "这个", "那个", "吗"
        }
        punctuations = set("，。！？、；：""''（）【】《》…·")
        
        words = []
        current = ""
        for ch in query:
            if ch in punctuations or ch.isspace():
                if current:
                    words.append(current)
                    current = ""
            else:
                current += ch
        if current:
            words.append(current)
        
        keywords = []
        entity_names = {e["name"] for e in entities}
        keywords.extend(e["name"] for e in entities)
        for patterns in INTENT_PATTERNS.values():
            for pattern in patterns:
                if len(pattern) >= 2 and pattern in query:
                    keywords.append(pattern)
        if is_uav_detection_overview:
            keywords.extend(["无人机探测技术", *UAV_DETECTION_OVERVIEW_TERMS])
        if is_gps_interference_comparison:
            keywords.extend(
                [
                    "GPS压制式干扰",
                    "GPS欺骗干扰",
                    "转发式欺骗干扰",
                    "生产式欺骗干扰",
                ]
            )
        for triggers, expansions in KEYWORD_EXPANSIONS:
            if any(term in query for term in triggers):
                if is_gps_interference_comparison and triggers == (
                    "GPS",
                    "北斗",
                    "导航系统",
                ):
                    continue
                    continue
                keywords.extend(expansions)
        if is_regulation_gate:
            keywords.extend([
                "CCAR-92",
                "CCAR-92部",
                "民用无人驾驶航空器运行安全管理规则",
                "政策法规_CCAR-92部.txt",
                "执照和等级的申请条件",
                "无犯罪记录",
                "犯罪记录",
                "刑事处罚",
                "第92.55条",
                "第92.57条",
                "无犯罪记录声明",
            ])
            if self._looks_like_clause_lookup(query):
                keywords.extend(["原文", "条文", "第92.55条"])
        
        for w in words:
            if w in entity_names:
                keywords.append(w)
            elif len(w) >= 2 and w not in stopwords:
                keywords.append(w)
        
        if is_regulation_gate:
            seen = set()
            unique = []
            for kw in keywords:
                if kw not in seen:
                    seen.add(kw)
                    unique.append(kw)
            forced = [
                "CCAR-92",
                "CCAR-92部",
                "民用无人驾驶航空器运行安全管理规则",
                "政策法规_CCAR-92部.txt",
                "执照和等级的申请条件",
                "无犯罪记录",
                "犯罪记录",
                "刑事处罚",
                "第92.55条",
                "第92.57条",
                "无犯罪记录声明",
            ]
            if self._looks_like_clause_lookup(query):
                forced.extend(["原文", "条文"])
            ordered = [kw for kw in forced if kw in unique]
            ordered.extend(kw for kw in unique if kw not in ordered)
            return ordered[:max_kw]

        if is_regulation_eligibility:
            q = query or ""
            keywords.extend([
                "CCAR-92",
                "CCAR-92部",
                "民用无人驾驶航空器运行安全管理规则",
                "政策法规_CCAR-92部.txt",
            ])
            if any(term in q for term in ("申请条件", "资格条件")):
                keywords.extend(["第92.55条", "执照和等级的申请条件"])
            if any(term in q for term in ("视距内", "超视距", "教员")):
                keywords.extend(["视距内", "超视距等级", "教员等级"])
            if any(term in q for term in ("申请材料", "提交材料", "报名材料", "所需材料", "材料")):
                keywords.extend([
                    "第92.57条",
                    "执照和等级的申请材料",
                    "身份证明",
                    "身体情况说明",
                    "飞行经历记录信息",
                ])
            if any(term in q for term in ("不得申请", "不能申请", "禁止行为", "虚假材料")):
                keywords.extend([
                    "第92.99条",
                    "第92.101条",
                    "考试中禁止的行为",
                    "禁止提供虚假材料",
                ])
            if any(term in q for term in ("处罚", "罚款", "违法", "违规")):
                keywords.extend([
                    "第92.1005条",
                    "第92.1007条",
                    "第92.1009条",
                    "第92.1013条",
                    "第92.1015条",
                    "违反证照管理的处罚",
                    "违反运行规定的处罚",
                ])
            if any(term in q for term in ("吊销", "撤销", "失效", "注销")):
                keywords.extend([
                    "第92.67条",
                    "第92.95条",
                    "第92.665条",
                    "第92.1015条",
                    "执照的变更 放弃和注销",
                    "撤销和注销",
                ])
            if any(term in q for term in ("作弊", "代考")):
                keywords.extend([
                    "第92.99条",
                    "第92.1015条",
                    "考试中禁止的行为",
                    "考试作弊行为的处罚",
                ])
            if any(term in q for term in ("立即停止飞行", "停止飞行", "不能飞")):
                keywords.extend([
                    "第92.633条",
                    "超视距运行",
                    "立即停止飞行活动",
                    "第92.625条",
                    "飞行区域限制",
                ])
            if any(term in q for term in ("实名登记", "登记材料")):
                keywords.extend([
                    "第92.205条",
                    "实名登记要求",
                    "所有人合法身份的信息",
                    "联系信息",
                    "使用用途",
                ])
            if "实名登记" in q and any(term in q for term in ("注销", "注销登记")):
                keywords.extend([
                    "第92.207条",
                    "实名登记注销",
                    "所有权或者占有权发生变更",
                    "退出使用 报废 失事",
                ])
            if "实名登记" in q and any(term in q for term in ("变更", "更新")):
                keywords.extend([
                    "第92.209条",
                    "实名登记信息更新",
                    "联系方式变更",
                    "用途变更",
                ])
            if "国籍登记" in q:
                keywords.extend([
                    "第92.215条",
                    "第92.217条",
                    "第92.223条",
                    "国籍登记要求",
                    "国籍登记申请",
                    "国籍登记证书",
                ])
            if "适航证" in q:
                keywords.extend([
                    "第92.453条",
                    "第92.455条",
                    "适航证件",
                    "适航证的申请书和申请文件",
                ])
            if "特许飞行证" in q:
                keywords.extend([
                    "第92.453条",
                    "第92.467条",
                    "第92.471条",
                    "特许飞行证的申请书和申请文件",
                    "特许飞行证的适航检查和颁发",
                ])
            if any(term in q for term in ("运营合格证", "运营规范", "运行人", "运营人", "责任保险", "信息报送", "年度运营报告")):
                keywords.extend([
                    "第92.603条",
                    "第92.645条",
                    "第92.647条",
                    "第92.655条",
                    "第92.663条",
                    "第92.665条",
                    "第92.669条",
                    "第92.671条",
                    "第92.673条",
                    "运营许可适用范围",
                    "运营合格证",
                    "运营规范",
                ])
            if any(term in q for term in ("持续适航", "维修管理", "维修记录", "维修放行", "飞行前准备", "缺陷", "故障", "失效", "通信链路", "电池储备", "维修责任人")):
                keywords.extend([
                    "第92.619条",
                    "第92.621条",
                    "第92.623条",
                    "第92.707条",
                    "第92.709条",
                    "持续适航要求",
                    "维修管理体系",
                    "报告和自愿报告",
                    "飞行前准备",
                ])
            if any(term in q for term in ("C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序")):
                keywords.extend([
                    "第92.679条",
                    "第92.697条",
                    "指挥和控制链路",
                    "C2链路运行管理",
                    "预设程序",
                    "可预期的飞行轨迹",
                ])
            if any(term in q for term in ("紧急迫降", "迫降地点", "终止飞行")):
                keywords.extend([
                    "第92.701条",
                    "特殊运行要求",
                    "紧急迫降地点",
                    "终止飞行程序",
                ])
            if any(term in q for term in ("事故报告", "严重受伤", "严重人员伤亡", "重大损失", "重大财产损失")):
                keywords.extend([
                    "第92.687条",
                    "机长的职责和权限",
                    "最迅速的方法",
                    "民航及有关部门",
                    "航空器事故",
                ])
            if any(term in q for term in ("应急反应预案", "飞行事故应急反应预案")):
                keywords.extend([
                    "第92.667条",
                    "一般规定",
                    "飞行事故应急反应预案",
                    "伤亡人员家属援助计划",
                ])
            if any(term in q for term in ("夜间飞行", "视距内运行")):
                keywords.extend([
                    "第92.631条",
                    "视距内运行",
                    "夜间运行",
                    "直接且无设备辅助的目视接触",
                ])
            if any(term in q for term in ("超视距飞行", "超视距运行")):
                keywords.extend(["第92.633条", "超视距运行", "交通态势信息服务"])
            if "训练机构" in q and any(term in q for term in ("暂停报名考试资格", "停止报名考试资格")):
                keywords.extend([
                    "政策法规_《民用中小型无人驾驶航空器操控员训练机构规范》.txt",
                    "14.1 失信行为",
                    "14.2 失信行为管理",
                    "暂停报名考试资格",
                    "停止报名考试资格",
                ])
            seen = set()
            unique = []
            for kw in keywords:
                if kw not in seen:
                    seen.add(kw)
                    unique.append(kw)
            forced = [
                "CCAR-92",
                "CCAR-92部",
                "民用无人驾驶航空器运行安全管理规则",
                "政策法规_CCAR-92部.txt",
            ]
            if any(term in q for term in ("申请条件", "视距内", "超视距", "教员", "资格条件")):
                forced.extend(["第92.55条", "执照和等级的申请条件", "超视距等级", "教员等级"])
            if any(term in q for term in ("申请材料", "提交材料", "报名材料", "所需材料")):
                forced.extend(["第92.57条", "执照和等级的申请材料", "身份证明", "身体情况说明", "飞行经历记录信息"])
            if any(term in q for term in ("不得申请", "不能申请", "禁止行为", "虚假材料")):
                forced.extend(["第92.99条", "第92.101条", "考试中禁止的行为", "禁止提供虚假材料"])
            if any(term in q for term in ("处罚", "罚款", "违法", "违规")):
                forced.extend(["第92.1005条", "第92.1007条", "第92.1009条", "第92.1013条", "第92.1015条", "违反证照管理的处罚", "违反运行规定的处罚"])
            if any(term in q for term in ("吊销", "撤销", "失效", "注销")):
                forced.extend(["第92.67条", "第92.95条", "第92.665条", "第92.1015条", "执照的变更 放弃和注销", "撤销和注销"])
            if any(term in q for term in ("作弊", "代考")):
                forced.extend(["第92.99条", "第92.1015条", "考试中禁止的行为", "考试作弊行为的处罚"])
            if any(term in q for term in ("立即停止飞行", "停止飞行", "不能飞")):
                forced.extend(["第92.633条", "超视距运行", "立即停止飞行活动", "第92.625条", "飞行区域限制"])
            if any(term in q for term in ("实名登记", "登记材料")):
                forced.extend(["第92.205条", "实名登记要求", "所有人合法身份的信息", "联系信息", "使用用途"])
            if "实名登记" in q and any(term in q for term in ("注销", "注销登记")):
                forced.extend(["第92.207条", "实名登记注销", "所有权或者占有权发生变更", "退出使用 报废 失事"])
            if "实名登记" in q and any(term in q for term in ("变更", "更新")):
                forced.extend(["第92.209条", "实名登记信息更新", "联系方式变更", "用途变更"])
            if "国籍登记" in q:
                forced.extend(["第92.215条", "第92.217条", "第92.223条", "国籍登记要求", "国籍登记申请", "国籍登记证书"])
            if "适航证" in q:
                forced.extend(["第92.453条", "第92.455条", "适航证件", "适航证的申请书和申请文件"])
            if "特许飞行证" in q:
                forced.extend(["第92.453条", "第92.467条", "第92.471条", "特许飞行证的申请书和申请文件", "特许飞行证的适航检查和颁发"])
            if any(term in q for term in ("运营合格证", "运营规范", "运行人", "运营人", "责任保险", "信息报送", "年度运营报告")):
                forced.extend(["第92.603条", "第92.645条", "第92.647条", "第92.655条", "第92.663条", "第92.665条", "第92.669条", "第92.671条", "第92.673条", "运营许可适用范围", "运营合格证", "运营规范"])
            if any(term in q for term in ("持续适航", "维修管理", "维修记录", "维修放行", "飞行前准备", "缺陷", "故障", "失效", "通信链路", "电池储备", "维修责任人")):
                forced.extend(["第92.619条", "第92.621条", "第92.623条", "第92.707条", "第92.709条", "持续适航要求", "维修管理体系", "报告和自愿报告", "飞行前准备"])
            if any(term in q for term in ("C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序")):
                forced.extend(["第92.679条", "第92.697条", "指挥和控制链路", "C2链路运行管理", "预设程序", "可预期的飞行轨迹"])
            if any(term in q for term in ("紧急迫降", "迫降地点", "终止飞行")):
                forced.extend(["第92.701条", "特殊运行要求", "紧急迫降地点", "终止飞行程序"])
            if any(term in q for term in ("事故报告", "严重受伤", "严重人员伤亡", "重大损失", "重大财产损失")):
                forced.extend(["第92.687条", "机长的职责和权限", "最迅速的方法", "民航及有关部门", "航空器事故"])
            if any(term in q for term in ("应急反应预案", "飞行事故应急反应预案")):
                forced.extend(["第92.667条", "一般规定", "飞行事故应急反应预案", "伤亡人员家属援助计划"])
            if any(term in q for term in ("夜间飞行", "视距内运行")):
                forced.extend(["第92.631条", "视距内运行", "夜间运行", "直接且无设备辅助的目视接触"])
            if any(term in q for term in ("超视距", "超视距运行")):
                forced.extend(["第92.633条", "超视距运行", "交通态势信息服务"])
            if "训练机构" in q and any(term in q for term in ("暂停报名考试资格", "停止报名考试资格")):
                forced.extend([
                    "政策法规_《民用中小型无人驾驶航空器操控员训练机构规范》.txt",
                    "14.1 失信行为",
                    "14.2 失信行为管理",
                    "暂停报名考试资格",
                    "停止报名考试资格",
                ])
            ordered = [kw for kw in forced if kw in unique]
            ordered.extend(kw for kw in unique if kw not in ordered)
            return ordered[:max_kw]

        # 普通路径：补充判别性名词短语和型号词（gate/eligibility 路径在上面已 return，
        # 不受影响）。短语在 BM25 端会被再分词，等价于给判别词加权。
        phrases = extract_content_phrases(query)
        codes = extract_model_codes(query)
        keywords.extend(codes)
        keywords.extend(phrases)

        # 去重，保留顺序
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)
        # 给新增短语留余量，避免挤掉原有扩展词造成行为回退
        return unique[:max_kw + len(codes) + len(phrases)]

    def _looks_like_regulation_gate_question(self, query: str) -> bool:
        q = query or ""
        if not q:
            return False
        has_gate_term = any(term in q for term in REGULATION_GATE_TERMS)
        has_license_term = any(term in q for term in REGULATION_LICENSE_TERMS)
        return has_gate_term and has_license_term

    def _looks_like_regulation_eligibility_question(self, query: str) -> bool:
        q = query or ""
        if not q:
            return False
        if "训练机构" in q and any(term in q for term in ("暂停报名考试资格", "停止报名考试资格")):
            return True
        if any(term in q for term in ("维修记录", "维修放行")):
            return True
        if any(term in q for term in ("运营合格证", "国籍登记", "年度运营报告", "故障", "失效", "缺陷")) and any(
            term in q for term in ("什么时候", "多久", "多久内", "几日内", "工作日", "保存多久", "保存多长时间", "提前")
        ):
            return True
        if "考试" in q and any(term in q for term in ("作弊", "代考", "欺骗", "贿赂")):
            return True
        if "实名登记" in q:
            return True
        if "国籍登记" in q:
            return True
        if "适航证" in q:
            return True
        if "特许飞行证" in q:
            return True
        if any(term in q for term in ("C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序", "紧急迫降", "迫降地点", "终止飞行", "事故报告", "严重人员伤亡", "重大财产损失", "应急反应预案", "飞行事故应急反应预案")):
            return True
        if any(term in q for term in ("处罚", "罚款", "吊销", "撤销", "注销", "失效")) and any(
            term in q for term in ("执照", "运营合格证", "运营规范", "飞行")
        ):
            return True
        has_eligibility_term = any(term in q for term in REGULATION_ELIGIBILITY_TERMS)
        has_license_or_reg_term = any(term in q for term in REGULATION_LICENSE_TERMS) or any(
            term in q for term in ("法规", "规定", "规则", "CCAR-92", "民航")
        )
        return has_eligibility_term and has_license_or_reg_term

    def _looks_like_clause_lookup(self, query: str) -> bool:
        q = query or ""
        if "原文" in q or "条文" in q:
            return True
        return bool(re.search(r"第?\s*\d{1,3}(?:\.\d+)?\s*条", q))

    def _rewrite_regulation_gate_query(self, query: str) -> str:
        q = query or ""
        if self._looks_like_clause_lookup(q):
            return "CCAR-92部 第92.55条 犯罪记录 原文 民用无人驾驶航空器运行安全管理规则"
        return "CCAR-92部 第92.55条 第92.57条 执照和等级的申请条件 犯罪记录 无犯罪记录声明 民用无人驾驶航空器运行安全管理规则"

    def _rewrite_regulation_eligibility_query(self, query: str) -> str:
        q = query or ""
        if any(term in q for term in ("申请条件", "资格条件")) and any(term in q for term in ("申请材料", "提交材料", "报名材料", "所需材料", "材料")) and any(term in q for term in ("区别", "不同", "有什么区别")):
            return "CCAR-92部 第92.55条 第92.57条 执照和等级的申请条件 执照和等级的申请材料 区别"
        if "训练机构" in q and any(term in q for term in ("暂停报名考试资格", "停止报名考试资格")):
            return "训练机构规范 14.1 14.2 失信行为 暂停报名考试资格 停止报名考试资格"
        if any(term in q for term in ("申请条件", "资格条件")) and any(term in q for term in ("视距内", "超视距", "教员")):
            return "CCAR-92部 第92.55条 执照和等级的申请条件 视距内 超视距等级 教员等级"
        if any(term in q for term in ("申请材料", "提交材料", "报名材料", "所需材料", "哪些材料")):
            return "CCAR-92部 第92.57条 执照和等级的申请材料 身份证明 身体情况说明 飞行经历记录信息"
        if any(term in q for term in ("不得申请", "不能申请", "禁止行为", "虚假材料")):
            return "CCAR-92部 第92.55条 第92.99条 第92.101条 执照申请条件 考试中禁止的行为 禁止提供虚假材料"
        if any(term in q for term in ("作弊", "代考")):
            return "CCAR-92部 第92.99条 第92.1015条 考试中禁止的行为 考试作弊行为的处罚 代考 撤销执照"
        if any(term in q for term in ("运营合格证", "运营规范")) and any(term in q for term in ("撤销", "注销", "吊销")):
            return "CCAR-92部 第92.665条 运营合格证 运营规范 撤销 注销 安全生产条件 有效期届满未延续"
        if "运营合格证" in q and any(term in q for term in ("有效期届满未更新", "有效期届满未延续", "逾期未更新", "没更新会怎样")):
            return "CCAR-92部 第92.663条 第92.665条 运营合格证 有效期届满未延续 不得更新 注销"
        if "运营合格证" in q and any(term in q for term in ("自愿放弃", "放弃运营合格证")):
            return "CCAR-92部 第92.665条 运营合格证 自愿放弃 交回局方 注销"
        if "运营合格证" in q and any(term in q for term in ("适用范围", "哪些情况", "什么情况", "哪些单位", "哪些运行人", "什么情况下")) and any(term in q for term in ("需要", "应当", "要", "取得")):
            return "CCAR-92部 第92.603条 运营许可适用范围 微型民用无人驾驶航空器 常规农用无人驾驶航空器作业飞行活动 无需取得运营合格证"
        if any(term in q for term in ("外国运行人", "国外运营合格证", "外国运营合格证")) and any(term in q for term in ("国内运行", "在国内运行", "中国境内运行", "能不能直接用", "是否可以认可")):
            return "CCAR-92部 第92.637条 外国民用无人驾驶航空器和运行人在中国境内运行 同等安全水平 经申请 认可外国运行人的运营合格证 或者其他等效证件"
        if any(term in q for term in ("开放类", "特定类")) and any(term in q for term in ("运营许可", "运营合格证", "运营规范", "边界", "区别")):
            return "CCAR-92部 第92.601条 第92.603条 开放类 特定类 运营许可 运营合格证 运营规范 微型 轻型 适飞空域 常规农用"
        if any(term in q for term in ("开放类", "哪些运行属于开放类")) and any(term in q for term in ("不需要额外运营规范", "无需额外运营规范", "哪些运行")):
            return "CCAR-92部 第92.601条 第92.603条 开放类 微型民用无人驾驶航空器 轻型民用无人驾驶航空器 适飞空域 常规农用 无需取得运营合格证"
        if "微型无人机" in q and "运营合格证" in q and any(term in q for term in ("需不需要", "需要吗", "要不要", "是否需要")):
            return "CCAR-92部 第92.603条 微型民用无人驾驶航空器 无需取得运营合格证 运营许可适用范围"
        if "运营合格证" in q and any(term in q for term in ("材料", "提交")) and any(term in q for term in ("受理后多久", "多久决定", "作出决定", "多久送达", "决定后多久", "送达")):
            return "CCAR-92部 第92.647条 第92.651条 运营合格证 申请材料 受理申请之日起20个工作日内 作出决定 作出决定之日起10个工作日内 送达"
        if "运营合格证" in q and any(term in q for term in ("受理后多久", "多久作出决定", "审查多久", "多久决定", "多少工作日作出决定")):
            return "CCAR-92部 第92.647条 运营合格证 受理申请之日起20个工作日内 作出是否颁发决定"
        if "运营合格证" in q and any(term in q for term in ("送达", "颁发后多久", "决定后多久", "多久送达", "作出决定之日起")):
            return "CCAR-92部 第92.651条 运营合格证 作出决定之日起10个工作日内 颁发 送达"
        if "运营规范" in q and any(term in q for term in ("载明", "哪些内容", "什么内容", "包含什么")):
            return "CCAR-92部 第92.653条 运营规范 运营合格证的附件 批准 条件 限制"
        if "运营合格证" in q and any(term in q for term in ("更新", "续期")) and any(term in q for term in ("什么时候", "多久", "工作日", "提前")):
            return "CCAR-92部 第92.655条 第92.663条 运营合格证 有效期24个日历月 更新 提前30个工作日申请"
        if any(term in q for term in ("无证操控", "未取得执照", "没执照")):
            return "CCAR-92部 第92.1005条 违反证照管理的处罚 无证操控 5000元以上5万元以下罚款"
        if any(term in q for term in ("没取得运营合格证", "未取得运营合格证", "没有运营合格证")):
            return "CCAR-92部 第92.1005条 运营合格证 运营规范 未取得运营合格证 5万元以上50万元以下罚款 停业整顿"
        if any(term in q for term in ("责任保险", "投保")) and any(term in q for term in ("后果", "处罚", "罚款")):
            return "CCAR-92部 第92.669条 第92.1011条 责任保险 未依法投保 2000元以上2万元以下罚款 停业整顿"
        if any(term in q for term in ("动态信息", "年度运营报告")) and any(term in q for term in ("处罚", "罚款", "后果")):
            return "CCAR-92部 第92.671条 第92.1011条 动态信息 年度运营报告 未报送 1万元以上3万元以下罚款"
        if any(term in q for term in ("严重失信", "失信记录", "信用记录")):
            return "CCAR-92部 第92.1019条 严重失信行为 民航行业信用记录 拒绝监督检查 虚假材料 考试作弊"
        if "运营合格证" in q and any(term in q for term in ("有效期", "更新", "续期")):
            return "CCAR-92部 第92.655条 第92.663条 运营合格证 有效期24个日历月 更新 提前30个工作日申请"
        if "运营合格证" in q and "运营规范" in q and any(term in q for term in ("分别", "区别", "是什么")):
            return "CCAR-92部 第92.603条 第92.653条 运营合格证 运营规范 附件 批准 条件 限制"
        if "运营合格证" in q and any(term in q for term in ("材料", "申请", "提交")):
            return "CCAR-92部 第92.647条 运营合格证 运营规范 申请材料 手册 购买合同 劳动合同 风险评估报告"
        if any(term in q for term in ("吊销", "撤销", "失效", "注销")) and any(term in q for term in ("执照", "等级")):
            return "CCAR-92部 第92.67条 第92.95条 第92.665条 第92.1015条 执照注销 撤销 吊销 运营合格证"
        if any(term in q for term in ("处罚", "罚款", "违法", "违规")):
            return "CCAR-92部 第92.1005条 第92.1007条 第92.1009条 第92.1013条 第92.1015条 处罚 罚款 吊销 撤销"
        if any(term in q for term in ("立即停止飞行", "停止飞行", "不能飞")):
            return "CCAR-92部 第92.625条 第92.633条 飞行区域限制 超视距运行 立即停止飞行活动"
        if "实名登记" in q and "国籍登记" in q and any(term in q for term in ("区别", "不同", "有什么区别")):
            return "CCAR-92部 第92.205条 第92.215条 第92.217条 实名登记 国籍登记 区别 登记信息 申请主体 申请材料"
        if any(term in q for term in ("实名登记", "登记材料")):
            return "CCAR-92部 第92.205条 实名登记要求 所有人合法身份的信息 联系信息 无人驾驶航空器的信息 使用用途"
        if "实名登记" in q and any(term in q for term in ("注销", "注销登记")):
            return "CCAR-92部 第92.207条 实名登记注销 所有权或者占有权发生变更 退出使用 报废 失事"
        if "实名登记" in q and any(term in q for term in ("变更", "更新")):
            return "CCAR-92部 第92.209条 实名登记信息更新 联系方式变更 用途变更 出厂性能参数"
        if "国籍登记" in q and any(term in q for term in ("条件", "要求", "谁可以", "哪些人可以", "哪些主体可以", "申请人")):
            return "CCAR-92部 第92.215条 国籍登记要求 国家机构 企业法人 中国公民 事业法人"
        if "国籍登记" in q and any(term in q for term in ("材料", "申请", "提交")):
            return "CCAR-92部 第92.217条 国籍登记申请 合法身份文件 所有权证明 实名登记号 境外国籍证明"
        if "国籍登记" in q and any(term in q for term in ("遗失", "污损", "补发", "更换", "证书")):
            return "CCAR-92部 第92.223条 国籍登记证书 遗失 污损 补发 更换 说明材料"
        if any(term in q for term in ("报送", "年度运营报告")) and any(term in q for term in ("什么时候", "多久", "几月几日", "截止")):
            return "CCAR-92部 第92.671条 年度运营报告 每年3月31日前 综合管理平台"
        if "年度运营报告" in q and any(term in q for term in ("哪些运行人", "哪些主体", "谁需要", "什么人需要")):
            return "CCAR-92部 第92.671条 第92.603条 年度运营报告 运营人 微型民用无人驾驶航空器 常规农用无人驾驶航空器作业飞行活动"
        if "年度运营报告" in q and any(term in q for term in ("哪些运行人", "哪些主体", "谁需要")) and any(term in q for term in ("处罚", "罚款", "没报")):
            return "CCAR-92部 第92.671条 第92.603条 第92.1011条 年度运营报告 运营人 综合管理平台 未按要求报送 1万元以上3万元以下罚款"
        if "适航证" in q and any(term in q for term in ("材料", "申请", "提交")):
            return "CCAR-92部 第92.453条 第92.455条 适航证件 适航证的申请书和申请文件 完成实名登记 适航性相关文件"
        if "特许飞行证" in q and any(term in q for term in ("情况", "条件", "申请", "材料")):
            return "CCAR-92部 第92.453条 第92.467条 第92.471条 特许飞行证 一定限制条件下安全飞行 申请书 技术与批准状态报告 使用限制"
        if "适航证" in q and "特许飞行证" in q and any(term in q for term in ("区别", "不同", "有什么区别")):
            return "CCAR-92部 第92.453条 适航证件 标准适航证 特殊适航证 特许飞行证 适用情形 区别"
        if any(term in q for term in ("视距内等级", "超视距等级")) and any(term in q for term in ("区别", "不同", "有什么区别")):
            return "CCAR-92部 第92.55条 第92.57条 第92.633条 视距内等级 超视距等级 区别 超视距运行"
        if any(term in q for term in ("运行人", "运营人")) and any(term in q for term in ("基本运行责任", "运行责任")):
            return "CCAR-92部 第92.673条 运行人基本运行责任 对运行负责 第三方安全关键服务 不安全事件报告"
        if any(term in q for term in ("责任保险", "投保")) and any(term in q for term in ("运行人", "运营人", "无人机")):
            return "CCAR-92部 第92.669条 责任保险 运营人 应当按规定投保"
        if any(term in q for term in ("报送", "年度运营报告", "平台")) and any(term in q for term in ("运行人", "运营人", "无人机")):
            return "CCAR-92部 第92.671条 信息报送和评价 综合管理平台 动态信息 年度运营报告"
        if any(term in q for term in ("持续适航", "维修管理")) and any(term in q for term in ("运行人", "维修", "体系")):
            return "CCAR-92部 第92.619条 第92.707条 持续适航要求 维修管理体系 维修责任人"
        if any(term in q for term in ("故障", "失效", "缺陷")) and any(term in q for term in ("报告", "怎么办", "发现")):
            return "CCAR-92部 第92.621条 第92.311条 报告和自愿报告 故障 失效 缺陷 48小时报告"
        if any(term in q for term in ("维修记录", "维修放行")) and any(term in q for term in ("多久", "保存多久", "保存多长时间")):
            return "CCAR-92部 第92.619条 第92.709条 维修记录 维修放行证明 直至被下一次维修工作全部覆盖 记录保存系统"
        if any(term in q for term in ("飞行前准备", "通信链路", "电池储备")):
            return "CCAR-92部 第92.623条 飞行前准备 通信链路信号 电池储备 紧急处置预案"
        if any(term in q for term in ("C2链路", "链路故障", "链路中断", "非正常程序", "紧急程序")):
            return "CCAR-92部 第92.679条 第92.697条 指挥和控制链路 C2链路运行管理 非正常程序 紧急程序 预设程序 可预期的飞行轨迹"
        if any(term in q for term in ("紧急迫降", "迫降地点", "终止飞行")):
            return "CCAR-92部 第92.701条 特殊运行要求 紧急迫降地点 终止飞行程序"
        if any(term in q for term in ("事故报告", "严重受伤", "严重人员伤亡", "重大损失", "重大财产损失")):
            return "CCAR-92部 第92.687条 机长的职责和权限 最迅速的方法 民航及有关部门 航空器事故"
        if any(term in q for term in ("应急反应预案", "飞行事故应急反应预案")):
            return "CCAR-92部 第92.667条 一般规定 飞行事故应急反应预案 伤亡人员家属援助计划"
        if any(term in q for term in ("维修记录", "维修放行")):
            return "CCAR-92部 第92.619条 第92.709条 维修记录 维修放行证明 记录保存系统"
        if any(term in q for term in ("夜间飞行", "视距内运行", "特殊条件")):
            return "CCAR-92部 第92.631条 视距内运行 夜间运行 直接且无设备辅助的目视接触"
        if any(term in q for term in ("超视距", "超视距运行")):
            return "CCAR-92部 第92.55条 第92.633条 超视距运行 超视距等级 交通态势信息服务"
        if any(term in q for term in ("视距内", "超视距", "教员", "申请条件", "资格条件")):
            return "CCAR-92部 第92.55条 执照和等级的申请条件 视距内 超视距 教员等级"
        return query
    
# ============ 测试 ============
