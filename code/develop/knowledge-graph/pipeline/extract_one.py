#!/usr/bin/env python3
"""单文件抽取脚本 — 严格对齐 KG_GUIDE.md v2.4

规则来源：KG_GUIDE.md §3（实体抽取规则）、§3.5.3（Prompt策略）、§3.5.4（文件夹上下文）
执行流程：读文件(12000字符) → GPT-5.5抽取JSON → 写Neo4j(name MERGE) → 锚定 → 清理
"""
import json, sys, time, requests, os
from neo4j import GraphDatabase

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rag_store.semantic_schema import relationship_missing_evidence_reason

# ── 配置 ─────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH) as f:
    _cfg = json.load(f)

# 模型默认走 GPT-5.5（手册 §3.5.1：主抽取引擎）
# 可用模型：flash(DeepSeek), gpt5(GPT-5.5), full(Claude审计)
_DEFAULT_MODEL_KEY = "gpt5"

def _get_model_config(key):
    """获取模型配置，支持 proxies 多中转站"""
    mc = _cfg["models"].get(key, _cfg["models"]["gpt5"])
    # 处理多中转站
    proxies = mc.get("proxies", [])
    if proxies:
        return proxies[0]["base_url"], proxies[0]["api_key"], mc["name"], mc.get("timeout", 180), proxies
    return mc.get("base_url"), mc["api_key"], mc["name"], mc.get("timeout", 120), []

def _fallback_proxy(base_url, api_key, model, timeout, proxies, messages, temperature=0.1, max_tokens=8192):
    """尝试多个中转站，全部失败返回 None。用 http.client 直连绕过 Clash Verge 系统代理。"""
    import http.client, json, os
    from urllib.parse import urlparse
    os.environ['NO_PROXY'] = '*'
    errors = []
    for p in [{"base_url": base_url, "api_key": api_key}] + (proxies or [])[1:]:
        try:
            pu = urlparse(p['base_url'])
            body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens})
            if pu.scheme == 'https':
                conn = http.client.HTTPSConnection(pu.hostname, pu.port, timeout=timeout)
            else:
                conn = http.client.HTTPConnection(pu.hostname, pu.port, timeout=timeout)
            conn.request("POST", f"{pu.path}/chat/completions", body=body,
                headers={"Authorization": f"Bearer {p['api_key']}", "Content-Type": "application/json"})
            resp = conn.getresponse()
            data = resp.read().decode()
            conn.close()
            if resp.status == 200:
                return json.loads(data)
            else:
                errors.append(f"{p['base_url']}: HTTP {resp.status}")
                continue
        except Exception as e:
            errors.append(f"{p['base_url']}: {type(e).__name__}")
            continue
    print(f"⚠️ 所有中转站均失败: {'; '.join(errors)}")
    return None

NEO4J_PASS = open(os.path.join(os.path.dirname(__file__), "../neo4j/.neo4j_pass")).read().strip()

# ── 文件夹上下文映射（手册 §3.5.4） ──────────────────
FOLDER_TYPE_MAP = {
    "企业信息/介绍": "Company,KnowledgePoint,Skill,Course,Category,Policy",
    "企业信息/产品": "Category,Skill,KnowledgePoint,Course,Regulation",
    "企业信息/价格": "Course,Certification,LicenseLevel,AircraftType,WeightClass",
    "企业信息/培训": "Course,Certification,LicenseLevel,AircraftType,WeightClass,Organization,Regulation,Event",
    "企业信息/规范": "Regulation,Organization,Certification,Course,AircraftType,LicenseLevel,KnowledgePoint",
    "岗位信息报告": "Position,Company,Location,EducationRequirement,PlatformPresence",
    "咨询客户情况": "Person,Organization,Category",
    "培训学员记录": "Person,Course,Skill",
    "培训计划": "Course,Event,KnowledgePoint,Person",
    "理论题库": "KnowledgePoint,Regulation,Certification,Skill",
    "CAAC题库": "KnowledgePoint,Regulation,Certification,Skill",
    "制度": "Policy,Position,Event",
    "运营组": "PlatformPresence,SocialContent,Person",
    "企业文化": "KnowledgePoint,Company,Certification,Skill",
    "企业信息": "Organization,Course,Certification,KnowledgePoint",
    "教材/理论书籍": "Chapter,Section,KnowledgePoint,Scenario,Skill,Regulation",
    "default": "Organization,Person,Event",
}

# 全部22类（手册 §3.3）
ALL_TYPES_LIST = ["Location","Position","Company","Organization","PlatformPresence","Event","Course","Exam","Certification","KnowledgePoint","Category","Student","Teacher","Person","Policy","Regulation","SocialContent","Skill","EducationRequirement","AircraftType","LicenseLevel","WeightClass","Chapter","Section","Scenario","DesignTool","FabricationStep"]
ALL_TYPE_KEYS = set(ALL_TYPES_LIST)

# 关系白名单（手册 §3.5.3）
REL_WHITELIST = "DESCRIBES | OFFERS | AWARDS | REQUIRES | ISSUED_BY | LOCATED_AT | REGULATES | BELONGS_TO | MENTIONS | HAS_CLASS | HAS_LEVEL | REFERS_TO | REQUIRES_SKILL | HAS_PROPERTY | SUBCLASS_OF | PART_OF | DEFINED_BY"


def relation_evidence_props(rel_type, doc_name, chunk_ids, description=""):
    props = {
        "description": description,
        "source_doc": doc_name,
        "source_chunk_ids": chunk_ids,
        "evidence_contract": "source_doc_and_source_chunk_ids_to_sqlite",
    }
    reason = relationship_missing_evidence_reason(rel_type, props)
    return props, reason


def extract(doc_name, filepath, folder_hint="", types="", doc_url="", model_key=_DEFAULT_MODEL_KEY):
    """核心抽取函数 — 严格按手册规则"""
    
    # ── 读取文件（动态截断：按文件大小自动适配，上限50000字符，手册§3.5.3） ────
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()[:12000]
    
    # ── 确定类型白名单（手册§3.5.4 文件夹注入，兜底用全22类） ────
    if not types:
        types = FOLDER_TYPE_MAP.get(folder_hint, FOLDER_TYPE_MAP.get("default", ",".join(ALL_TYPES_LIST)))
    
    print(f"📄 {doc_name} ({len(text)}字符)")
    print(f"📌 类型白名单: {types}")
    print(f"📌 模型: {model_key}")
    
    # ── 构建 Prompt（手册§3.5.3 抽取Prompt） ────
    system_msg = "只输出JSON，不要markdown代码块"
    
    prompt = f"""从以下文档提取实体和关系，只输出JSON。

文档：{doc_name}
来源：{folder_hint}

## 实体类型
实体类型只能从以下选择（从类型白名单中选），不能使用 "Other"、"null" 或列表外的类型：
{types}

## 关系类型
关系类型只能从以下选择：
{REL_WHITELIST}

## 输出格式
{{"entities":[{{"id":"ent_1","name":"实体名称","type":"实体类型","properties":{{"description":"实体描述","example":"示例型号（如有）"}}}}],
 "relations":[{{"from_id":"ent_1","to_id":"ent_2","type":"关系类型","properties":{{"description":"关系描述"}}}}]}}

## 提取规则

### 命名与去重（手册§3.2）
- 同名实体只提取一次（合并 properties 中的描述）
- 同名实体必须用同一个 name，不要生成两个不同 id
- 公司/组织使用全称（如「湖北云技科技有限公司」而非「云技科技」）
- 薪资数字带单位（如"6000-8000元"）

### 关系约束（手册§4）
- 核心关系规则：
  · SUBCLASS_OF — 子类关系（A类空域→管制空域、微型无人机→无人机质量分类），替代泛化的 BELONGS_TO
  · PART_OF — 组成部分关系（空中交通管制服务→空中交通服务、机场起落航线→机场飞行空域）
  · DEFINED_BY — 法规依据关系（空域分类→中华人民共和国民用航空法），替代方向混乱的 REGULATES
  · BELONGS_TO — 仅用于无法明确归类的层级归属，优先用 SUBCLASS_OF 和 PART_OF 替代
  · REFERS_TO — 知识点引用法规
  · REQUIRES_SKILL — 知识点需要对应技能
  · HAS_PROPERTY — 实体具有某个属性
  · （INCLUDES 和 USES 已移除 — 质量门禁未通过，禁止生成）
  · REGULATES — 法规约束对象，方向为 Regulation→其他类型
- 每对实体之间只取 2-3 条最核心的关系
- 避免使用语义模糊的 MENTIONS、DESCRIBES 关系

### ⚠️ 关系准确性硬约束
- **每条关系必须被文档内容直接支持** — 不能基于外部知识或常识推断
- **禁止关联属于不同知识领域且文档未同时提及的实体** — 例如：空域分类类的实体不能关联到电池/电机类实体，除非文档同时提到了这两个概念
- **文档中各实体间的关联要忠于原文结构**，不要自己给不相干的实体建立联系。例：如果文档只讲空域分类，就不该把空域实体关联到电池/电机/动力系统等文档未提及的概念上。
- **只能关联本次文档中新提取的实体**，不要将本次文档中的实体关联到已有的旧实体上，除非旧实体也出现在本次文档文本中
- **所有被关联的两个实体必须都出现在当前文档的文本中**

### ⛔ 禁止行为（手册§3.1）
- **禁止提取文档中未出现的实体** — 只提取文档字面上提到的内容
- **禁止根据上下文脑补实体的课	程/价格/工资等属性** — 文档没写的就是没有
- **禁止将表头/字段名作为实体**（如"核查内容"被当成学生姓名）
- **禁止使用 "Other" 或空类型**
- 如果文档是表格数据：只提取表格中的具体值，不提取表格标题或列名

### 📋 理论题库文档特殊规则
如果文档是理论题库类文档，请额外遵守：
- **具体产品型号不作为独立实体**：赛斯纳、悟、S800、侦察兵、捕食者、精灵、6S2P 等机型名称，必须作为父知识点的 `example` 属性存储，不建独立节点
- **别名合并**：罗马数字和阿拉伯数字统一（Ⅰ类=1类，Ⅱ类=2类），法规名称去重（带"中国民用航空局《》"前缀和不带的合并为一条）
- **排除过细实体**：电池细分类型（6S2P电池组/6S2P动力电池）、模糊概念（无人机优势）、角色（飞行员）不作为独立实体
- **法规类实体必标为 Regulation 类型**，不能标为 KnowledgePoint 或 Entity
- **只保留核心知识点**，排除纯粹的组件名、产品名、具体参数值

### 📋 培训方案文档特殊规则（手册§5.1.2）
如果文档是培训方案/培训计划类文档，请遵守：
- 实体类型偏好：TrainingPlan > Course > KnowledgePoint > Event > Person > Organization
- **禁止将公司制度类实体（Policy/SalaryItem/SalaryRange/Department）关联到培训方案**
- **禁止将运营类实体（Platform/PlatformPresence/SocialAccount）关联到培训方案**
- **禁止通过MERGE将已有制度/运营实体关联到培训方案文档**

### ⚠️ 规范/制度/价格表类文档
如果文档有多行数据（如价格表行、制度条款），请逐行检查每行内容，确保不遗漏重要实体。
- 价格表类文档：每行课程必须包含 price/duration/content 等属性

文档内容：
{text}
"""
    
    # ── 调用模型（手册§3.5.1 GPT-5.5 主抽取） ──
    base_url, api_key, model, timeout, proxies = _get_model_config(model_key)
    print("🚀 请求模型...", flush=True)
    
    t0 = time.time()
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt}
    ]
    result_json = _fallback_proxy(base_url, api_key, model, timeout, proxies, messages)
    
    if result_json is None:
        # 全部失败 → 按手册§3.5.1降级链：停下来问老文
        print("❌ 所有中转站失败，按手册§3.5.1需老文确认后降级")
        print("💡 手动执行: python3 extract_one.py <文件路径> <文档名> <分类> doubao")
        return
    
    elapsed = time.time() - t0
    content = result_json["choices"][0]["message"]["content"].strip()
    
    # 清理 markdown 代码块包裹
    if content.startswith("```"):
        # 尝试找到第一个换行后的内容
        first_nl = content.find("\n")
        if first_nl >= 0:
            content = content[first_nl+1:]
        else:
            content = content[3:]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()
    
    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        print(f"原始响应前200字: {content[:200]}")
        return
    
    entities = result.get("entities", [])
    relations = result.get("relations", [])
    print(f"⚡ {elapsed:.1f}s → {len(entities)}实体 {len(relations)}关系")
    
    if not entities:
        print("⚠️ 无实体，跳过入库")
        return
    
    print(f"📊 模型: {model}")
    
    # ── 写Neo4j（手册§3.5.6 name MERGE） ────
    d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))
    name_map = {}
    new_ids = set()
    doc_chunk_ids = []
    with d.session() as s:
        # 1. 确保Document节点
        s.run("MERGE (d:Document {name: $n}) SET d.name=$n, d.url=$u, d.imported_at=datetime()",
              n=doc_name, u=doc_url)
        doc_chunk_ids = [
            row["chunk_id"]
            for row in s.run(
                """
                MATCH (n)
                WHERE n.source_doc = $doc AND n.source_chunk_ids IS NOT NULL
                UNWIND n.source_chunk_ids AS chunk_id
                RETURN DISTINCT chunk_id LIMIT 20
                """,
                doc=doc_name,
            )
        ]
        
        # 2. 写入实体（name MERGE，手册§3.5.6）
        for e in entities:
            eid = e.get("id", f"e_{entities.index(e)}")
            ename = e["name"]
            etype = e.get("type", "Unknown")
            # 支持 properties.description 和直接 description 两种格式
            props = e.get("properties", {})
            edesc = props.get("description", "") if isinstance(props, dict) else ""
            if not edesc:
                edesc = e.get("description", "")
            # 抽取 example 属性（产品型号示例）
            eexample = props.get("example", "") if isinstance(props, dict) else ""
            
            # 类型校验：不在白名单中则跳过
            if etype not in ALL_TYPE_KEYS:
                print(f"  ⚠️ 类型不在白名单中: {ename} -> {etype}，跳过")
                continue
            
            # 类型标签：只有 Entity 类型名才用 Entity，否则用具体类型名 + Entity 双标签
            type_label = "Entity"
            if etype not in ("", "Unknown", "Entity"):
                type_label = etype
            
            # 动态Cypher：用具体类型标签 + 通用Entity标签
            cypher = (
                f"MERGE (e:{type_label}:Entity {{name: $n}}) "
                f"ON CREATE SET e.id=$id, e.type=$t, e.description=$d, e.example=$ex, e.source_doc=$doc, e._created_by=$doc "
                f"ON MATCH SET e.id=COALESCE(e.id,$id), e.description=CASE WHEN (e.description IS NULL OR e.description = '') AND $d <> '' THEN $d ELSE e.description END, "
                f"           e.example=COALESCE(e.example,$ex), e.source_doc=COALESCE(e.source_doc,$doc) "
                f"RETURN e.id AS actual_id, e._created_by AS creator"
            )
            result = s.run(cypher, n=ename, id=eid, t=etype, d=edesc, ex=eexample, doc=doc_name)
            row = result.single()
            actual_id = row["actual_id"]
            creator = row.get("creator", "")
            name_map[eid] = actual_id
            
            # 仅当实体是由本文档首次创建时，才建立CONTAINS边
            if creator == doc_name:
                s.run("MATCH (d:Document {name:$dn}) MATCH (e:Entity {id:$ei}) MERGE (d)-[:CONTAINS]->(e)",
                      dn=doc_name, ei=actual_id)
                new_ids.add(actual_id)
        
        # 3. 写入关系（仅两个端点都是本次新建的实体才创建，防止跨文档错误关联）
        rc = 0
        for r in relations:
            fid = name_map.get(r["from_id"])
            tid = name_map.get(r["to_id"])
            if fid and tid:
                # 调试：打印被过滤的关系
                if fid not in new_ids or tid not in new_ids:
                    print(f"  🚫 跳过跨文档关系: {r.get('from_id')}({fid}) -[{r['type']}]-> {r.get('to_id')}({tid})")
                    continue
                rel_type = r["type"].upper().strip()
                # 关系类型校验
                if rel_type not in [x.strip() for x in REL_WHITELIST.split("|")]:
                    print(f"  ⚠️ 关系类型不在白名单中: {r.get('from_id')} -[{rel_type}]-> {r.get('to_id')}，跳过")
                    continue
                props = r.get("properties", {})
                rdesc = props.get("description", "") if isinstance(props, dict) else ""
                if not rdesc:
                    rdesc = r.get("description", "")
                rel_props, evidence_reason = relation_evidence_props(rel_type, doc_name, doc_chunk_ids, rdesc)
                if evidence_reason:
                    print(
                        f"  🚫 跳过缺证据关键关系: {r.get('from_id')} -[{rel_type}]-> {r.get('to_id')} ({evidence_reason})"
                    )
                    continue
                try:
                    s.run(f"MATCH (a:Entity {{id:$f}}) MATCH (b:Entity {{id:$t}}) "
                          f"MERGE (a)-[rel:`{rel_type}`]->(b) SET rel += $props",
                          f=fid, t=tid, props=rel_props)
                    rc += 1
                except Exception as ex:
                    print(f"  ⚠️ 关系写入失败: {ex}")
    d.close()
    print(f"✅ 入库: {len(entities)}实体 {rc}关系")
    
    # ── 统计 ──
    d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))
    with d.session() as s:
        nb = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        # 检查CONTAINS污染（手册§5.1.2验证方式）
        polluted = s.run(
            "MATCH (d:Document)-[r:CONTAINS]->(e:Entity) "
            "WHERE e._created_by <> d.name "
            "RETURN count(r) AS c").single()["c"]
    d.close()
    print(f"📊 总计: {nb} 节点, {rels} 关系 (CONTAINS污染: {polluted})")
    
    # ── 锚定到主图谱（防孤岛） ──
    ANCHOR_ENTITIES = ['湖北云技科技有限公司', '云技科技', '文汉清', '王佳丽']
    anchored = False
    try:
        d2 = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))
        with d2.session() as s:
            for anchor_name in ANCHOR_ENTITIES:
                core = s.run("MATCH (e:Entity {name:$name}) RETURN e.id AS id", name=anchor_name).single()
                if core:
                    s.run("MATCH (d:Document {name:$doc}) MATCH (e:Entity {id:$eid}) MERGE (d)-[:CONTAINS]->(e)",
                          doc=doc_name, eid=core["id"])
                    print(f"  🔗 锚定到主图谱: {anchor_name}")
                    anchored = True
                    break
        d2.close()
        if not anchored:
            print(f"  ⚠️ 锚定失败：图谱中未找到已知锚定实体")
    except Exception as e:
        print(f"  ⚠️ 锚定异常: {e}")
    
    # ── 自动清理违规关系（手册§5.1.1） ──
    print("🧹 清理违规关系...")
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "cleanup_relations.py")], capture_output=True)
    
    print(f"✅ 抽取完成: {doc_name}")
    print(f"📋 共抽取 {len(entities)} 个实体, {rc} 个关系")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python3 extract_one.py <文件路径> <文档名> <文件夹分类> [类型白名单] [模型]")
        print("  文件夹分类: 如 理论题库, 企业信息/规范, 岗位信息报告, 制度, default")
        print("  类型白名单: 可选，不传则按文件夹自动匹配（手册§3.5.4）")
        print("  模型: 可选，默认 gpt5, 可选 flash(DeepSeek) / doubao / full(Claude审计)")
        print("示例:")
        print("  python3 extract_one.py ../概述.txt 概述 理论题库")
        print("  python3 extract_one.py ../概述.txt 概述 理论题库 KnowledgePoint,Regulation flash")
        sys.exit(1)
    model_key = sys.argv[5] if len(sys.argv) > 5 else _DEFAULT_MODEL_KEY
    extract(sys.argv[2], sys.argv[1], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "", model_key=model_key)
