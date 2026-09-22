#!/usr/bin/env python3
"""
Query Rewrite 模块

输入: 用户原始问题
输出: {
  rewritten: 改写后的问题,
  keywords: [关键词列表],
  entities: [{name, type, confidence}],
  intent: "regulation" | "company" | "job" | "training" | "general",
  need_kg: bool
}
"""

import csv
import json, re, os
from typing import Dict, List, Optional
from pathlib import Path

# ============ 意图关键词词典（快速匹配，不需要 LLM）============

INTENT_PATTERNS = {
    "regulation": [
        "法规", "法律", "条例", "规定", "管理办法", "标准", "资质",
        "合格证", "适航", "空域", "飞行规则", "处罚", "罚款",
        "CCAR", "行政许可", "执照要求", "飞行申请"
    ],
    "company": [
        "公司", "云技", "介绍", "业务", "课程", "价格", "费用", "多少钱",
        "报名", "培训", "地址", "电话", "联系", "招聘", "员工"
    ],
    "job": [
        "就业", "薪资", "工资", "岗位", "招聘", "工作", "找工作",
        "待遇", "前景", "人才", "市场需求"
    ],
    "training": [
        "CAAC", "考证", "实操", "考试", "题库", "通过率", "教学",
        "培训", "学习", "练习", "试题", "答案", "教练", "教员"
    ],
    "general": [
        "无人机", "多旋翼", "固定翼", "飞行", "操作", "气象",
        "原理", "系统", "技术"
    ]
}

# 已知实体白名单（公司、产品、人物、法规、组织等）
KNOWN_ENTITIES = {
    "云技科技": ("Company", 0.95),
    "湖北云技科技有限公司": ("Company", 0.98),
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
    "bge-m3": ("Model", 0.95),
    "Ollama": ("Tool", 0.95),
    "Neo4j": ("Tool", 0.90),
    "SQLite": ("Tool", 0.90),
}

DEFAULT_CANONICAL_DIR = Path(os.environ.get(
    "CSA_CANONICAL_DIR",
    "/Users/xiaoji/Documents/知识库分析/data/canonical",
))
COURSE_FALLBACK_PATTERNS = (
    "多旋翼教员考证班",
    "垂起教员考证班",
    "装调检修班",
    "精英教员就业班",
    "兴趣爱好班",
    "设备维修进阶班",
    "飞手考证班",
    "植保吊运班",
    "智慧城市班",
    "双机长专业能力进阶班",
)
COURSE_SUFFIX_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,40}(?:教员考证班|考证班|就业班|进阶班|检修班|兴趣爱好班|智慧城市班|植保吊运班|课程)")

# 长尾入口的同义词和文档锚点。只扩展检索词，不改变 chunk_id 契约。
KEYWORD_EXPANSIONS = [
    (("侧风", "横风"), ["侧风", "横风", "起飞", "着陆", "起降", "气象", "风向", "风速"]),
    (("云高", "能见度", "最低天气标准", "天气标准"), ["云高", "能见度", "云层高度", "最低天气标准", "气象", "天气标准"]),
    (("智能培训解决方案", "智能培训", "AI智学", "人工智能", "职业教育"), ["智能培训解决方案", "智能培训", "AI智学体系", "人工智能", "职业教育", "数字化升级", "公司介绍"]),
    (("客户管理", "跟进制度", "客户跟进", "执照培训项目"), ["客户管理", "跟进制度", "客户跟进", "执照培训项目", "CAAC培训", "有效客户", "咨询组", "运营组"]),
]

# ============ Query Rewrite Engine ============

class QueryRewriter:
    """查询改写 + 实体抽取 + 意图路由"""
    
    def __init__(self, model_provider: str = "deepseek", api_key: str = None):
        self.model_provider = model_provider
        self._api_key = api_key
        self._canonical_dir = DEFAULT_CANONICAL_DIR
        self._course_entities = self._load_course_entities()
        self._load_config()
    
    def _load_config(self):
        """从 config.json 读取 API key"""
        if not self._api_key:
            config_path = Path(__file__).parent.parent / "pipeline" / "config.json"
            if config_path.exists():
                cfg = json.loads(config_path.read_text())
                if "models" in cfg and "flash" in cfg["models"]:
                    self._api_key = cfg["models"]["flash"].get("api_key", "")
    
    def rewrite(self, query: str, use_llm: bool = True) -> Dict:
        """
        主入口：改写问题并提取所有元信息
        
        Args:
            query: 用户原始问题
            use_llm: 是否用 LLM 做深度改写（False 时只做规则匹配）
        """
        # Step 1: 规则匹配（快速，零成本）
        entities = self._extract_entities_rule(query)
        intent = self._classify_intent_rule(query)
        keywords = self._extract_keywords(query, entities)
        
        # Step 2: LLM 深度改写（可选，精度更高）
        if use_llm and self._api_key:
            try:
                result = self._llm_rewrite(query, entities, intent, keywords)
                return result
            except Exception as e:
                print(f"[QueryRewrite] LLM 失败: {e}，回退到规则模式")
        
        return {
            "original": query,
            "rewritten": query,  # 规则模式下不重写
            "keywords": keywords,
            "entities": entities,
            "intent": intent,
            "need_kg": intent in ("regulation", "company", "training", "general"),
        }
    
    def _load_course_entities(self) -> List[tuple[str, str, float]]:
        entities: List[tuple[str, str, float]] = []
        seen = set()
        path = self._canonical_dir / "courses.csv"
        if path.exists():
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        name = (row.get("course_name") or row.get("name") or "").strip()
                        if name and name not in seen:
                            seen.add(name)
                            entities.append((name, "Course", 0.96))
            except Exception as e:
                print(f"[QueryRewrite] 读取 canonical courses 失败: {e}")
        for name in COURSE_FALLBACK_PATTERNS:
            if name not in seen:
                seen.add(name)
                entities.append((name, "Course", 0.94))
        return entities

    def _extract_entities_rule(self, query: str) -> List[Dict]:
        """规则匹配：从白名单和 canonical 课程名中提取已知实体"""
        found = []
        for name, (etype, conf) in KNOWN_ENTITIES.items():
            if name in query:
                found.append({"name": name, "type": etype, "confidence": conf})
        for name, etype, conf in self._course_entities:
            if name in query:
                found.append({"name": name, "type": etype, "confidence": conf})
        for match in COURSE_SUFFIX_RE.finditer(query):
            name = match.group(0).strip()
            if len(name) >= 3:
                found.append({"name": name, "type": "Course", "confidence": 0.88})
        
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
        scores = {}
        for intent, patterns in INTENT_PATTERNS.items():
            score = sum(1 for p in patterns if p in query)
            scores[intent] = score
        
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"
    
    def _extract_keywords(self, query: str, entities: List[Dict], max_kw: int = 12) -> List[str]:
        """提取关键词：去停用词 + 保留实体名 + 长词优先"""
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
        if any(term in query for term in ("价格", "费用", "多少钱", "收费")):
            keywords.extend(["价格表", "价格", "费用", "收费", "课程"])
        for triggers, expansions in KEYWORD_EXPANSIONS:
            if any(term in query for term in triggers):
                keywords.extend(expansions)
        
        for w in words:
            if w in entity_names:
                keywords.append(w)
            elif len(w) >= 2 and w not in stopwords:
                keywords.append(w)
        
        # 去重，保留顺序
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)
        
        return unique[:max_kw]
    
    def _llm_rewrite(self, query: str, entities: List[Dict], intent: str, keywords: List[str]) -> Dict:
        """用 LLM 深度改写问题，抽取结构化信息"""
        e_str = ", ".join([f"{e['name']}({e['type']})" for e in entities]) or "无"
        kw_str = ", ".join(keywords) or "无"
        
        prompt = f"""你是查询改写助手。请分析以下用户问题，提取结构化信息。

用户问题：{query}

已知实体（规则匹配结果）：{e_str}
已知关键词（规则匹配结果）：{kw_str}
已知意图：{intent}

请输出 JSON：
{{
    "rewritten": "改写后的问题（补全指代、扩展同义词、提取核心意图）",
    "entities": [{{"name": "实体名", "type": "Person/Company/Regulation/Organization/Location/Product/Concept", "confidence": 0.95}}],
    "keywords": ["关键词1", "关键词2"],
    "intent": "regulation/company/job/training/general",
    "need_kg": true/false
}}

要求：
- rewritten: 把口语化问题改写成便于检索的标准查询语句
- entities: 从问题中抽取的实体，补充规则遗漏的
- keywords: 最重要的检索关键词（5-8个）
- need_kg: regulation/company/general 类问题通常需要图谱，简单寒暄不需要

只输出 JSON，不要其他内容。"""
        
        body = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是查询改写助手。只输出合法 JSON，不要 markdown 代码块。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }).encode()
        
        import urllib.request as ureq
        r = ureq.urlopen(ureq.Request(
            "https://api.deepseek.com/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json"
            }
        ), timeout=20)
        
        resp = json.loads(r.read())
        content = resp["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        # 合并规则匹配和 LLM 结果
        result["original"] = query
        result.setdefault("intent", intent)
        result.setdefault("need_kg", intent in ("regulation", "company", "training", "general"))
        
        return result


# ============ 测试 ============
if __name__ == "__main__":
    rw = QueryRewriter()
    
    queries = [
        "无人机测绘需要什么资质？",
        "云技科技有哪些培训课程？",
        "CAAC考证多少钱？",
        "武汉今天天气怎么样？",
        "CCAR-92关于罚款的规定是什么？",
    ]
    
    for q in queries:
        result = rw.rewrite(q, use_llm=False)
        print(f"\nQ: {q}")
        print(f"  intent: {result['intent']} | need_kg: {result['need_kg']}")
        print(f"  entities: {[e['name'] for e in result['entities']]}")
        print(f"  keywords: {result['keywords']}")
