#!/usr/bin/env python3
"""
知识图谱在线抽取 — 先全量 DeepSeek 快速过，再择机 GPT 5.5 补抽
"""
import json, os, re, sys, time, requests
from pathlib import Path
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).parent.parent
NEO4J_PASS_PATH = BASE_DIR / "neo4j" / ".neo4j_pass"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = NEO4J_PASS_PATH.read_text().strip() if NEO4J_PASS_PATH.exists() else ""

CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

# 白名单/黑名单
WL_PATH = Path(__file__).parent / "white_list.json"
if WL_PATH.exists():
    with open(WL_PATH) as f:
        WL = json.load(f)
else:
    WL = {"white_list": [], "black_list": [], "rules": {}}

# 飞书凭证
c = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
acct = c["channels"]["feishu"]["accounts"]["default"]
APP_ID = acct["appId"]
APP_SECRET = acct["appSecret"]

TOKEN = None
H = {}

def refresh_token():
    global TOKEN, H
    r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET})
    TOKEN = r.json()["tenant_access_token"]
    H = {"Authorization": f"Bearer {TOKEN}"}

refresh_token()

# ============ Prompt ============
EXTRACT_PROMPT_TEMPLATE = """你是一个知识图谱实体抽取专家。请从以下{context}中提取实体和关系。

## 文档所在文件夹：{folder}
## 文件夹说明：{folder_hint}

## 实体类型
{entity_types}

## 关系类型（至少使用以下7种）
belongs_to | contains | references | required_by | manages | regulates | provides

## 输出格式
{{"entities":[{{"id":"ent_1","name":"名称","type":"类型","description":"描述"}}],
 "relations":[{{"from_id":"ent_1","to_id":"ent_2","type":"关系类型","description":"关系描述"}}]}}

## ⚠️ 关键规则
1. **同名实体只提取一次** — 如果同一名称出现多次，只输出一个实体节点（合并描述）
2. **实体类型必须匹配文档类型**（见上方列表）
3. **薪资数字带单位** — 如"6000-8000元"而非"6000-8000"
4. **岗位→薪资关系必须用HAS_SALARY，不能用REFERENCES** — REFERENCES用于不明确的一般引用关系
5. **公司/组织使用全称** — 如「湖北云技科技有限公司」而非「云技科技」

## ⚠️ 关系约束（严格遵守）
- **SalaryRange / SalaryItem 不能有任何外出关系** — 它们只做目标，不做源头
- **BELONGS_TO 仅用于层级归属** — 人→组织 / 实体→分类 / 学员→教员
- **LOCATED_IN 的目标必须是地点**（Location类型），不能指向非地点实体
- **MANAGES/REGULATES 的主体必须是「人」或「政策」**，不能是薪酬项/产品
- **每对实体之间只取3-5条最核心的关系**，不要过度抽取

仔细提取所有有意义的实体和关系。"""

# 文件夹→实体类型映射
FOLDER_TYPE_MAP = {
    "岗位信息报告": {"context":"招聘岗位信息", "hint":"包含职位、公司、薪资、地点、学历要求等招聘数据", "types":"Position(无人机飞手/教员/工程师) | Company(大疆/云技科技) | Location(武汉/深圳) | SalaryRange(6000-8000元) | EducationRequirement(大专/本科) | Platform(智联招聘/猎聘)"},
    "咨询客户情况": {"context":"客户信息记录", "hint":"包含客户姓名、联系方式、来源、跟进记录等", "types":"Person | Organization | Category | Phone"},
    "培训计划": {"context":"培训课程方案", "hint":"包含课程安排、培训计划、教学大纲等", "types":"Course | Event | KnowledgePoint | Person"},
    "培训学员记录": {"context":"学员学习档案", "hint":"包含学员姓名、学习进度、考试成绩等", "types":"Person | Course | Score | Progress"},
    "企业信息": {"context":"公司介绍与企业资料", "hint":"包含公司资质、产品服务、团队介绍、培训课程等", "types":"Organization | Product | Course | Certification | KnowledgePoint | Regulation"},
    "理论题库": {"context":"无人机考试理论知识", "hint":"包含CAAC无人机考试的理论知识点、法规条款、飞行原理等", "types":"KnowledgePoint | Regulation | Certification | Component | Skill"},
    "制度": {"context":"公司规章制度", "hint":"包含员工手册、薪酬体系、考勤制度、入职流程等", "types":"Policy | Department | Position | SalaryItem | Event"},
    "运营组": {"context":"运营数据与账号管理", "hint":"包含自媒体账号信息、内容数据、投放记录等", "types":"PlatformPresence | SocialAccount | SocialContent | Person"},
    "公众号内容": {"context":"公众号文章内容", "hint":"行业资讯、公司动态、政策解读等文章", "types":"Article | Event | KnowledgePoint"},
    "default": {"context":"文档", "hint":"通用文档内容", "types":"Organization | Person | Product | Event | Document"}
}

def build_prompt(doc_name, folder_path, text):
    """根据文件夹路径构建带上下文提示词"""
    # 从folder_path中找出匹配的文件夹名
    folder_info = FOLDER_TYPE_MAP.get("default")
    if folder_path:
        for key in FOLDER_TYPE_MAP:
            if key in folder_path:
                folder_info = FOLDER_TYPE_MAP[key]
                break
    
    prompt = EXTRACT_PROMPT_TEMPLATE.format(
        context=folder_info["context"],
        folder=folder_path or "未知",
        folder_hint=folder_info["hint"],
        entity_types=folder_info["types"]
    )
    return prompt + f"\n\n## 文档：{doc_name}\n\n{text[:8000]}"

def call_flash(text, doc_name, source=""):
    """DeepSeek Flash: 高速提取JSON，重试3次"""
    cfg = CONFIG["models"]["flash"]
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    prompt = build_prompt(doc_name, source, text)
    payload = {
        "model": cfg["name"],
        "messages": [{"role":"system","content":"只输出JSON，不要markdown代码块"}, {"role":"user","content":prompt}],
        "temperature": 0.1, "max_tokens": 8192
    }
    start = time.time()
    for attempt in range(3):
        try:
            r = requests.post(f"{cfg['base_url']}/chat/completions", headers=headers, json=payload,
                            timeout=cfg["timeout"])
            r.raise_for_status()
            c = r.json()["choices"][0]["message"]["content"]
            elapsed = time.time() - start
            result = try_parse_json(c)
            if result:
                print(f"  ✅ Flash: {len(result.get('entities',[]))}实体 {len(result.get('relations',[]))}关系 ({elapsed:.1f}s)")
                return result
        except Exception as e:
            if attempt < 2:
                print(f"  ⚠️ Flash重试{attempt+1}: {e}")
                time.sleep(3)
            else:
                print(f"  ❌ Flash失败(3次): {e}")
    # Flash → Pro 思考分析
    print(f"  🧠 Flash失败，转 Pro 语义分析...")
    return call_pro(text, doc_name, source)


def call_pro(text, doc_name, source=""):
    """Flash Pro模式：复杂语义分析，出规则不出数据"""
    cfg = CONFIG["models"]["pro"]
    pro_prompt = f"""分析以下文档内容，只输出JSON。
文档：{doc_name}
来源：{source or "未知"}
内容预览：{text[:3000]}

判断：1)文档类型 2)应提取的实体类型 3)关系规则
输出格式：{{"doc_type":"","entity_types":[],"relation_rules":{{}}}}"""
    try:
        r = requests.post(f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json={"model":cfg["name"],"messages":[{"role":"user","content":pro_prompt}],"temperature":0.1,"max_tokens":2048},
            timeout=cfg["timeout"])
        r.raise_for_status()
        result = try_parse_json(r.json()["choices"][0]["message"]["content"])
        if result:
            print(f"  🧠 Pro分析: {result.get('doc_type','?')}")
            return result
    except Exception as e:
        print(f"  ❌ Pro失败: {e}")
    # GPT-5.5终兜
    print(f"  🚨 Pro也失败，转 GPT-5.5...")
    return call_llm(text, doc_name, "full", source)

def call_llm(text, doc_name, level, source=""):
    """调用指定级别的 LLM 抽取"""
    cfg = CONFIG["models"][level]
    # 处理proxies数组配置（full模型用）
    if "proxies" in cfg:
        proxy = cfg["proxies"][0]
        api_key = proxy["api_key"]
        base_url = proxy["base_url"]
        timeout = proxy.get("timeout", cfg.get("timeout", 120))
    else:
        api_key = cfg["api_key"]
        base_url = cfg["base_url"]
        timeout = cfg["timeout"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    prompt = build_prompt(doc_name, source, text)
    payload = {
        "model": cfg["name"],
        "messages": [{"role":"system","content":"只输出JSON，不要markdown代码块"}, {"role":"user","content":prompt}],
        "temperature": 0.1, "max_tokens": 8192
    }
    start = time.time()
    try:
        r = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        c = r.json()["choices"][0]["message"]["content"]
        elapsed = time.time() - start
        result = try_parse_json(c)
        if result:
            print(f"  ✅ [{level.upper()}] {len(result.get('entities',[]))}实体 {len(result.get('relations',[]))}关系 ({elapsed:.1f}s)")
            return result
        print(f"  ❌ [{level.upper()}] JSON解析失败")
        return {"entities":[], "relations":[]}
    except Exception as e:
        print(f"  ❌ [{level.upper()}] 失败: {e}")
        return {"entities":[], "relations":[]}

def try_parse_json(text):
    import json, re
    # 策略1: 直接解析
    text = text.strip()
    try:
        return json.loads(text) if text.startswith('{') else None
    except: pass
    # 策略2: 查找 {} 包裹的内容
    m = re.search(r'\{[^{}]*"entities"[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group())
            if result.get('entities'): return result
        except: pass
    # 策略3: 从第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        candidate = text[start:end+1]
        try:
            return json.loads(candidate)
        except:
            # 尝试修复常见问题
            try:
                candidate = re.sub(r',\s*}', '}', candidate)
                candidate = re.sub(r',\s*\]', ']', candidate)
                return json.loads(candidate)
            except: pass
    return None

# ============ 飞书文件读取 ============
CONTENT_CACHE = {}

def read_doc_content(doc_token):
    """读 docx 内容"""
    if doc_token in CONTENT_CACHE:
        return CONTENT_CACHE[doc_token]
    for _ in range(2):
        try:
            r = requests.get(f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/raw_content", headers=H, timeout=30)
            if r.status_code == 401: refresh_token()
            if r.status_code == 200:
                c = r.json().get("data",{}).get("content","")
                if len(c) > 50: CONTENT_CACHE[doc_token] = c; return c
            return ""
        except: return ""

def read_docx_via_download(doc_token):
    """下载 docx 提取文字"""
    if doc_token in CONTENT_CACHE:
        return CONTENT_CACHE[doc_token]
    for _ in range(2):
        try:
            r = requests.get(f"https://open.feishu.cn/open-apis/drive/v1/files/{doc_token}/download", headers=H, timeout=30)
            if r.status_code == 401: refresh_token()
            if r.status_code == 200:
                tmp = f"/tmp/_kg_{doc_token}.docx"
                open(tmp, "wb").write(r.content)
                import zipfile, xml.etree.ElementTree as ET
                z = zipfile.ZipFile(tmp)
                texts = []
                for name in z.namelist():
                    if name.startswith("word/document"):
                        tree = ET.fromstring(z.read(name))
                        for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                            t = "".join(t.text or "" for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
                            if t.strip(): texts.append(t.strip())
                os.remove(tmp)
                c = "\n".join(texts)
                if len(c) > 50: CONTENT_CACHE[doc_token] = c; return c
            return ""
        except:
            try: os.remove(tmp)
            except: pass
            return ""

def read_pptx_content(doc_token):
    if doc_token in CONTENT_CACHE:
        return CONTENT_CACHE[doc_token]
    for _ in range(2):
        try:
            r = requests.get(f"https://open.feishu.cn/open-apis/drive/v1/files/{doc_token}/download", headers=H, timeout=60)
            if r.status_code == 401: refresh_token()
            if r.status_code == 200:
                tmp = f"/tmp/_kg_{doc_token}.pptx"
                open(tmp, "wb").write(r.content)
                from pptx import Presentation
                prs = Presentation(tmp)
                texts = []
                for slide in prs.slides:
                    for shape in slide.shapes:
                        if shape.has_text_frame:
                            for para in shape.text_frame.paragraphs:
                                if para.text.strip(): texts.append(para.text.strip())
                os.remove(tmp)
                c = "\n".join(texts)
                if len(c) > 50: CONTENT_CACHE[doc_token] = c; return c
            return ""
        except:
            try: os.remove(tmp)
            except: pass
            return ""

def read_sheet_content(sheet_token):
    if sheet_token in CONTENT_CACHE:
        return CONTENT_CACHE[sheet_token]
    for _ in range(2):
        try:
            r = requests.get(f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{sheet_token}/values/Sheet1", headers=H, timeout=30)
            if r.status_code == 401: refresh_token()
            if r.status_code == 200:
                data = r.json().get("data",{})
                values = data.get("valueRange",{}).get("values", data.get("values", []))
                lines = [" | ".join(str(c) for c in row if c) for row in values[:50]]
                c = "\n".join(lines)
                if len(c) > 50: CONTENT_CACHE[sheet_token] = c; return c
            return ""
        except: return ""

# ============ 验证模块 ============
sys.path.insert(0, str(Path(__file__).parent))
from post_extract_validation import validate_entities_and_relations, print_validation_report


def validate_result(entities, relations, doc_name):
    """验证抽取结果，拦截语义错误"""
    validated_entities, validated_relations, warnings = validate_entities_and_relations(
        entities, relations, doc_name
    )
    print_validation_report(warnings, doc_name)
    return validated_entities, validated_relations


# ============ 去重 ============
def dedup_entities(entities):
    """文档内同名实体去重：同名合并，保留类型，合并描述"""
    seen = {}  # name -> entity
    deduped = []
    for e in entities:
        name = e.get("name","").strip()
        if not name:
            continue
        if name in seen:
            # 已有同名实体：合并描述，统一类型
            existing = seen[name]
            desc1 = existing.get("description","")
            desc2 = e.get("description","")
            if desc2 and desc2 not in desc1:
                existing["description"] = f"{desc1}；{desc2}" if desc1 else desc2
            # 已有类型优先，新类型只在旧类型为空时补充
            old_t = existing.get("type","")
            new_t = e.get("type","")
            if not old_t and new_t:
                existing["type"] = new_t
        else:
            seen[name] = dict(e)
            deduped.append(seen[name])
    removed = len(entities) - len(deduped)
    if removed:
        print(f"  🔄 去重: 移除 {removed} 个重复实体 ({len(deduped)} 个唯一)")
    return deduped


def type_consistency_check(entities):
    """检查已有知识图谱中同名实体的类型，新类型优先与旧类型保持一致"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        for e in entities:
            name = e.get("name","").strip()
            if not name:
                continue
            result = session.run(
                "MATCH (e:Entity {name:$n}) RETURN e.type as old_type LIMIT 1",
                n=name
            )
            row = result.single()
            if row and row["old_type"]:
                old_type = row["old_type"]
                new_type = e.get("type","")
                if new_type and new_type != old_type:
                    # 类型不一致 → 以旧类型为准
                    e["_type_overridden"] = f"{new_type}→{old_type}"
                    e["type"] = old_type
    driver.close()
    overridden = [e for e in entities if e.get("_type_overridden")]
    if overridden:
        print(f"  🔄 类型修正: {len(overridden)} 个实体类型与知识图谱不一致，已自动对齐")
        for e in overridden:
            print(f"    - {e['name']}: {e['_type_overridden']}")
            del e["_type_overridden"]
    return entities


# ============ Neo4j 写入 ============
def write_neo4j(doc_name, entities, relations, doc_url=""):
    if not entities:
        print("  ℹ️ 无实体，跳过")
        return
    # 写入前去重
    entities = dedup_entities(entities)
    if not entities:
        print("  ⏭️ 去重后无实体，跳过")
        return
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        session.run("MERGE (d:Document {name:$n}) SET d.doc_url=$u, d.imported_at=datetime()", n=doc_name, u=doc_url)
        name_map = {}  # name->id
        id_map = {}    # orig_id -> actual_id
        for i, e in enumerate(entities):
            orig_id = e.get("id", "") or f"auto_{i}"
            eid = f"{doc_name[:6]}_{i+1}"
            name = e.get("name",""); t = e.get("type","Unknown"); d = e.get("description","")
            # 🔧 修复(2026-05-21): 按name MERGE而非id，防止同名实体创建多个节点
            result = session.run("MERGE (e:Entity {name:$n}) ON CREATE SET e.id=$eid SET e.type=$t, e.description=$d, e.source_doc=$s, e.doc_url=$u, e.source_chunk=$ch, e.imported_at=datetime() RETURN e.id AS actual_id",
                       n=name, eid=eid, t=t, d=d, s=doc_name, u=doc_url, ch=e.get("source_chunk",""))
            actual_eid = result.single()[0]  # 返回已有id（合并）或新id（新建）
            session.run("MATCH (d:Document {name:$dn}) MATCH (e:Entity {id:$eid}) MERGE (d)-[:CONTAINS]->(e)", dn=doc_name, eid=actual_eid)
            name_map[name] = actual_eid
            name_map[orig_id] = actual_eid  # Also map by original LLM ID
            id_map[orig_id] = actual_eid
        for rel in relations:
            from_key = rel.get("from_id","")
            to_key = rel.get("to_id","")
            fid = name_map.get(from_key, from_key)
            tid = name_map.get(to_key, to_key)
            rt = re.sub(r'[^a-zA-Z_]', '_', rel.get("type","RELATED_TO")).upper()
            try:
                session.run(f"MATCH (a:Entity {{id:$fid}}) MATCH (b:Entity {{id:$tid}}) MERGE (a)-[r:{rt}]->(b) SET r.description=$d",
                          fid=fid, tid=tid, d=rel.get("description",""))
            except Exception as e_rel:
                pass  # 关系创建失败可能是实体不存在，静默跳过
        # 🔧 离散关系修复（2026-05-21）：找不到目标实体的关系，挂到来源文档
        for rel in relations:
            from_key = rel.get("from_id","")
            to_key = rel.get("to_id","")
            fid = name_map.get(from_key, from_key)
            tid = name_map.get(to_key, to_key)
            # 检查from/to实体是否存在
            has_from = session.run("MATCH (e:Entity {id:$id}) RETURN count(e)", id=fid).single()[0] > 0
            has_to = session.run("MATCH (e:Entity {id:$id}) RETURN count(e)", id=tid).single()[0] > 0
            if has_from and not has_to:
                rt = re.sub(r'[^a-zA-Z_]', '_', rel.get("type","RELATED_TO")).upper()
                try:
                    session.run(f"MATCH (a:Entity {{id:$fid}}) MATCH (d:Document {{name:$dn}}) MERGE (a)-[r:MENTIONS]->(d) SET r.description=$d, r.original_type=$ot",
                              fid=fid, dn=doc_name, d=rel.get("description",""), ot=rt)
                except: pass
            elif has_to and not has_from:
                rt = re.sub(r'[^a-zA-Z_]', '_', rel.get("type","RELATED_TO")).upper()
                try:
                    session.run(f"MATCH (d:Document {{name:$dn}}) MATCH (b:Entity {{id:$tid}}) MERGE (d)-[r:MENTIONS]->(b) SET r.description=$d, r.original_type=$ot",
                              dn=doc_name, tid=tid, d=rel.get("description",""), ot=rt)
                except: pass
        # 🔧 文档关联（2026-05-21新增）：岗位报告类文档自动互相关联
        if doc_name.startswith('每日岗位信息报告') or doc_name.startswith('无人机岗位招聘日报') or doc_name.startswith('低空经济岗位周度分析报告'):
            session.run("""
                MATCH (d1:Document {name:$dn})
                MATCH (d2:Document)
                WHERE d2.name <> $dn
                  AND (d2.name CONTAINS '岗位信息' OR d2.name CONTAINS '低空经济' OR d2.name CONTAINS '无人机岗位')
                  AND (d2.deprecated IS NULL OR d2.deprecated <> true)
                MERGE (d1)-[:RELATED_TO]->(d2)
            """, dn=doc_name)
        # 🔧 五分类骨架（2026-05-21新增）：实体自动归属到对应Category
        category = None
        if any(kw in doc_name for kw in ['岗位信息','岗位招聘','低空经济','无人机岗位']):
            category = '就业资源'
        elif any(kw in doc_name for kw in ['员工手册','制度','薪酬','入职','账号']):
            category = '公司制度'
        elif any(kw in doc_name for kw in ['培训计划','培训方案','长江委']):
            category = '培训体系'
        elif doc_name.endswith('.docx') and any(kw in doc_name for kw in ['旋翼','无人机','概述','气象','系统组成','综合问答','空中','飞行原理']):
            category = '无人机理论知识'
        elif any(kw in doc_name for kw in ['客户','咨询']):
            category = '咨询客户'
        elif any(kw in doc_name for kw in ['学员']):
            category = '学员管理'
        if category:
            session.run("MERGE (c:Entity {name:$cn}) SET c.type='Category'", cn=category)
            for eid_val in name_map.values():
                session.run("MATCH (e:Entity {id:$eid}) MATCH (c:Entity {name:$cn}) WHERE e.type IS NOT NULL AND e.type <> 'Category' AND e.type <> 'FolderRef' AND e.type <> 'DocRef' MERGE (e)-[:BELONGS_TO]->(c)", eid=eid_val, cn=category)
    driver.close()
    print(f"  ✅ 入库: {len(entities)}实体 {len(relations)}关系")

# ============ 主流程 ============
def process_file(doc_token, doc_name, doc_type, folder_path, doc_url=""):
    print(f"\n📄 {doc_name}")
    print(f"   {folder_path}")
    
    # 读内容
    if doc_type == "docx":
        content = read_doc_content(doc_token) or read_docx_via_download(doc_token)
    elif doc_type in ("file",):
        ext = doc_name.split(".")[-1].lower() if "." in doc_name else ""
        if ext in ("pptx","ppt"):
            content = read_pptx_content(doc_token)
        elif ext in ("xlsx","xls"):
            content = read_sheet_content(doc_token)
        else:
            content = ""
    elif doc_type == "sheet":
        content = read_sheet_content(doc_token)
    else:
        content = ""
    
    if not content or len(content) < 50:
        print("   ⏭️ 无有效内容")
        return
    
    print(f"   内容: {len(content):,} 字符")
    
    # DeepSeek 抽取
    result = call_flash(content, doc_name, folder_path)
    entities = result.get("entities", [])
    relations = result.get("relations", [])
    
    if not entities:
        # 🔧 修复(2026-05-21): Flash失败+Pro分析返回无实体→显式调用GPT-5.5兜底
        print("   ⏭️ Flash+Pro无实体，转GPT-5.5最终兜底...")
        result = call_llm(content, doc_name, "full", folder_path)
        entities = result.get("entities", [])
        relations = result.get("relations", [])
    
    if not entities:
        print("   ⏭️ 抽取为空")
        return
    
    # 自动标签（根据文件夹路径匹配）
    tags = CONFIG.get("folder_tags", {})
    for ft_token, tag_info in tags.items():
        tag_name = tag_info.get("name", "")
        if tag_name and tag_name in folder_path:
            for e in entities:
                e["category"] = tag_info.get("category", "")
            break
    
    # 提取原文片段
    for e in entities:
        name = e.get("name","")
        idx = content.find(name)
        if idx >= 0:
            s = max(0, idx-100); en = min(len(content), idx+len(name)+100)
            e["source_chunk"] = content[s:en].strip()[:300]
    
    # 语义验证（拦截 SalaryRange 等错误关系）
    entities, relations = validate_result(entities, relations, doc_name)
    if not entities:
        print("   ⏭️ 验证后无可用实体，跳过入库")
        return
    
    # 类型一致性检查（与已有知识图谱对齐）
    entities = type_consistency_check(entities)
    
    # 入库
    write_neo4j(doc_name, entities, relations, doc_url)
    return len(entities), len(relations)


def incremental_scan():
    """增量抽取：扫描飞书全部文件夹，只处理图谱中不存在的文件（2026-05-21新增）"""
    print("="*60)
    print("🔍 增量抽取：只处理图谱中缺失的文件")
    print("="*60)
    
    # 加载黑名单
    blacklist_tokens = set()
    bl = WL.get("black_list", [])
    for item in bl:
        if item.get("type") == "folder":
            blacklist_tokens.add(item["token"])
            print(f"⛔ 黑名单: {item.get('note','')} ({item['token']})")
    
    # 从Neo4j获取已有文档名
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        existing = set()
        for r in session.run("MATCH (d:Document) RETURN d.name AS n"):
            existing.add(r[0])
    driver.close()
    print(f"📊 图谱中已有 {len(existing)} 个文档\n")
    
    total_e, total_r, total_f = 0, 0, 0
    new_files = []
    skipped = 0
    
    def scan_incremental(ft, path_parts):
        nonlocal total_e, total_r, total_f, skipped
        if ft in blacklist_tokens:
            print(f"⛔ 跳过黑名单: {'/'.join(path_parts)}")
            return
        url = f"https://open.feishu.cn/open-apis/drive/v1/files?page_size=50&folder_token={ft}"
        try:
            r = requests.get(url, headers=H, timeout=30)
        except:
            refresh_token()
            r = requests.get(url, headers=H, timeout=30)
        items = r.json().get("data",{}).get("files",[])
        for f in items:
            t = f["type"]; name = f["name"]; token = f["token"]
            if t == "folder":
                scan_incremental(token, path_parts + [name])
                continue
            if t not in ("docx","sheet") and not (t=="file" and name.split(".")[-1].lower() in ("pptx","ppt","xlsx","xls")):
                continue
            if t == "shortcut":
                continue
            if name in existing:
                skipped += 1
                continue
            fp = "/".join(path_parts + [name])
            print(f"\n🆕 {fp}")
            try:
                result = process_file(token, name, t, fp,
                    f"https://zcn5jf36q4fv.feishu.cn/drive/folder/{ft}")
                if result:
                    total_e += result[0]; total_r += result[1]; total_f += 1
                    existing.add(name)
                else:
                    print(f"  ⚠️ 处理失败")
            except Exception as e:
                print(f"  ❌ {e}")
    
    scan_incremental("X9pZftImzlgO1HdIo7Xct1CXn5b", ["云技资料库"])
    print(f"\n{'='*60}")
    print(f"📊 增量抽取完成: {total_f} 新文件 | {total_e} 实体 | {total_r} 关系 | ⏭️ 跳过: {skipped}")

def scan_and_process():
    print("="*60)
    print("🔍 全量抽取：云技资料库 → Neo4j（DeepSeek 快速模式）")
    print("="*60)
    
    # 加载黑名单
    blacklist_tokens = set()
    bl = WL.get("black_list", [])
    for item in bl:
        if item.get("type") == "folder":
            blacklist_tokens.add(item["token"])
            print(f"⛔ 黑名单文件夹: {item.get('note','')} ({item['token']})")
    
    total_e, total_r, total_f = 0, 0, 0
    processed = []
    failed = []
    
    def scan(ft, path_parts):
        nonlocal total_e, total_r, total_f
        
        # 黑名单跳过（包括云技资料库内的子文件夹）
        if ft in blacklist_tokens:
            path_str = "/".join(path_parts)
            print(f"⛔ 跳过黑名单文件夹: {path_str}")
            return
        
        url = f"https://open.feishu.cn/open-apis/drive/v1/files?page_size=50&folder_token={ft}"
        try:
            r = requests.get(url, headers=H, timeout=30)
        except:
            print("⚠️ 扫描超时，重试...")
            refresh_token()
            r = requests.get(url, headers=H, timeout=30)
        items = r.json().get("data",{}).get("files",[])
        
        for f in items:
            t = f["type"]; name = f["name"]; token = f["token"]
            fp = "/".join(path_parts + [name])
            
            if t == "folder":
                scan(token, path_parts + [name])
                continue
            
            # 只处理文本类文件
            ext = name.split(".")[-1].lower() if "." in name else ""
            if t == "docx":
                print(f"\n📝 {fp}")
            elif t == "sheet":
                print(f"\n📊 {fp}")
            elif t == "file" and ext in ("pptx","ppt","xlsx","xls"):
                print(f"\n📄 {fp}")
            elif t == "shortcut":
                continue
            else:
                continue
            
            try:
                res = process_file(token, name, t, fp,
                    f"https://zcn5jf36q4fv.feishu.cn/drive/folder/{ft}")
                if res:
                    total_e += res[0]; total_r += res[1]; total_f += 1
                    processed.append(name)
                else:
                    failed.append(name)
                # 写入进度
                with open("/tmp/kg_progress.txt", "w") as pf:
                    pf.write(f"已处理: {total_f} 文件 | {total_e} 实体 | {total_r} 关系\n最近: {name}")
            except Exception as e:
                print(f"  ❌ 处理失败: {e}")
                failed.append(name)
    
    scan("X9pZftImzlgO1HdIo7Xct1CXn5b", ["云技资料库"])
    
    print("\n" + "="*60)
    print(f"📊 抽取完成: {total_f} 个文件")
    print(f"   ✅ 成功: {len(processed)} 个")
    print(f"   ⏭️ 跳过/失败: {len(failed)} 个")
    print(f"   📥 共 {total_e} 实体, {total_r} 关系")
    if processed:
        print(f"\n   已处理: {', '.join(processed[:8])}...")
    print("="*60)

if __name__ == "__main__":
    # 支持命令行参数: python3 online_extract.py <file_path> <doc_name> [doc_url]
    if len(sys.argv) >= 3 and sys.argv[1] not in ("--only-new", "-n"):
        file_path = sys.argv[1]
        doc_name = sys.argv[2]
        doc_url = sys.argv[3] if len(sys.argv) > 3 else ""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[:8000]
        folder_path = str(Path(file_path).parent)
        result = call_flash(content, doc_name, folder_path)
        entities = result.get("entities", [])
        relations = result.get("relations", [])
        if not entities:
            # GPT-5.5兜底
            result = call_llm(content, doc_name, "full", folder_path)
            entities = result.get("entities", [])
            relations = result.get("relations", [])
        if entities:
            entities, relations = validate_result(entities, relations, doc_name)
            if entities:
                entities = type_consistency_check(entities)
                write_neo4j(doc_name, entities, relations, doc_url)
            else:
                print(f"  ⚠️ 验证后无可用实体")
        else:
            print(f"  ⚠️ 未提取到实体")
    elif len(sys.argv) >= 2 and sys.argv[1] in ("--only-new", "-n"):
        # 🔧 2026-05-21 新增：增量模式，只处理图谱中没有的文件
        incremental_scan()
    else:
        scan_and_process()
