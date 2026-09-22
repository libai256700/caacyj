#!/usr/bin/env python3
"""
知识图谱审计修复 — Phase 2
- 修复45个孤立知识点（补边）
- 批量分类645个无类型节点
- 确认CAAC题库文件全部入库并关联到CAAC理论考试
"""

import json, os, sys, time, requests, re
from pathlib import Path
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = Path(__file__).parent / "config.json"

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "yj123456"

PRO_CONFIG = CONFIG["models"]["pro"]
DS_API_KEY = PRO_CONFIG["api_key"]
DS_BASE_URL = PRO_CONFIG["base_url"]
DS_TIMEOUT = 120
DS_MODEL = PRO_CONFIG["name"]

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

# ============ 工具函数 ============
def deepseek_batch(prompt, max_tokens=4096):
    payload = {
        "model": DS_MODEL,
        "messages": [
            {"role": "system", "content": "你是知识图谱专家，输出纯JSON，不要多余文字。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens
    }
    headers = {"Authorization": f"Bearer {DS_API_KEY}", "Content-Type": "application/json"}
    
    for retry in range(3):
        try:
            resp = requests.post(
                f"{DS_BASE_URL}/chat/completions",
                headers=headers, json=payload, timeout=(10, 120)
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            start = content.find('[')
            end = content.rfind(']')
            if start != -1 and end > start:
                return json.loads(content[start:end+1])
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end > start:
                return json.loads(content[start:end+1])
        except Exception as e:
            print(f"  ❌ 调用失败(重试{retry+1}): {e}")
            time.sleep(2)
    return None

def query(q, params=None):
    with driver.session(database='neo4j') as s:
        return list(s.run(q, params or {}))

def run(q, params=None):
    with driver.session(database='neo4j') as s:
        s.run(q, params or {})

# ============ DeepSeek分类器 ============
ENTITY_TYPE_MAP = {
    "Company": ["公司", "有限公司", "科技", "集团", "企业"],
    "Person": None,  # 需要AI判断
    "Regulation": ["部", "规定", "条例", "法", "AC-"],
    "Course": ["培训", "课程", "考证班", "训练", "班$"],
    "Position": ["岗位", "主任", "经理", "工程师", "专员", "教员", "飞手"],
    "Product": ["无人机", "系统", "平台", "电池", "电机", "软件"],
    "Certification": ["证书", "执照", "合格证"],
    "Document": ["制度", "报告", "手册", "方案", "计划", "价格表"],
    "Location": ["武汉", "湖北", "区县", "省", "市"],
    "Skill": ["技术", "操作", "维护", "组装", "调试"],
}

def auto_classify(name):
    """基于名称规则的快速分类"""
    if not name:
        return None
    
    # 中文人名：2-4个纯中文字，不包含公司/科技等词
    if re.match(r'^[\u4e00-\u9fa5]{2,4}$', name) and not any(kw in name for kw in ["公司","有限","科技"]):
        # 排除常见非人名
        not_names = ["培训", "课程", "证书", "执照", "备降", "应急", "操作", "飞行", "考试", "技术",
                    "维护", "维修", "检查", "系统", "空域", "气象", "法规", "通信", "规划", "计算"]
        if not any(ng in name for ng in not_names):
            if not re.match(r'^[\u4e00-\u9fa5]{3,4}$', name) or name in ["低空经济", "人工智能", "人才培养","人群管理"]:
                pass
            else:
                return "Person"
    
    for etype, keywords in ENTITY_TYPE_MAP.items():
        if keywords:
            for kw in keywords:
                if re.search(kw, name):
                    return etype
    return None

def fix_isolated_kp():
    """Step 1: 修复45个孤立知识点"""
    print("="*50)
    print("📌 Step 1: 修复孤立知识点（补PRECEDES/RELATED_TO）")
    print("="*50)
    
    with driver.session(database='neo4j') as session:
        # 获取所有孤立知识点
        isolated = list(session.run(
            "MATCH (n:Entity {entityType:'KnowledgePoint'}) WHERE NOT (n)-->() "
            "RETURN n.name as name, n.chapter as chapter, n.source_doc as source_doc "
            "ORDER BY n.chapter, n.name"
        ))
        
        if not isolated:
            print("✅ 没有孤立知识点，跳过")
            return
        
        print(f"待修复孤立知识点: {len(isolated)} 个\n")
        
        # 按章节分组，批次发送给DeepSeek分析关系
        chapters = {}
        for kp in isolated:
            chap = kp['chapter'] or '综合知识'
            if chap not in chapters:
                chapters[chap] = []
            chapters[chap].append(kp['name'])
        
        total_fixed = 0
        for chap, kp_names in chapters.items():
            print(f"\n🔍 章节 [{chap}] ({len(kp_names)}个知识点):")
            
            # 获取同章节其他已连线的知识点作为候选
            candidates = list(session.run(
                "MATCH (n:Entity {entityType:'KnowledgePoint'}) WHERE n.chapter = $chap AND (n)-->() "
                "RETURN n.name as name LIMIT 20",
                chap=chap
            ))
            candidate_names = [c['name'] for c in candidates]
            
            if not candidate_names:
                print(f"  章节无已连线知识点的候选，跳过")
                continue
            
            prompt = f"""CAAC无人机考试知识点关系分析。

待连线的孤立知识点（{chap}章节）：
{json.dumps(kp_names, ensure_ascii=False, indent=2)}

同章节已有关联的候选知识点：
{json.dumps(candidate_names, ensure_ascii=False, indent=2)}

你的任务：给每个孤立知识点推荐1-2条PRECEDES或RELATED_TO关系，连接到候选知识点中。
规则：
- PRECEDES：A是B的前置知识（B依赖A）
- RELATED_TO：A与B关联，同属一个模块
- 确保语义正确，不要乱连

输出格式（纯JSON数组）：
[
  {{"source": "知识点A", "target": "知识点B", "type": "PRECEDES", "reason": "必须理解A才能学B"}},
  ...
]"""
            
            result = deepseek_batch(prompt)
            if not result or not isinstance(result, list):
                print(f"  ❌ DeepSeek分析失败，跳过")
                continue
            
            for rel in result:
                src = rel.get('source', '')
                tgt = rel.get('target', '')
                rel_type = rel.get('type', 'RELATED_TO')
                if src and tgt and src in kp_names:
                    try:
                        run(
                            "MATCH (a:Entity {name: $src, entityType:'KnowledgePoint'}) "
                            "MATCH (b:Entity {name: $tgt, entityType:'KnowledgePoint'}) "
                            "MERGE (a)-[:$rel_type]->(b)".replace("$rel_type", rel_type),
                            {"src": src, "tgt": tgt}
                        )
                        total_fixed += 1
                        print(f"  ✅ {src} --[{rel_type}]--> {tgt}  ({rel.get('reason','')})")
                    except Exception as e:
                        pass
                time.sleep(0.3)
        
        print(f"\n📊 Total: {total_fixed} 条关系已添加")

def classify_entities_batch():
    """Step 2: DeepSeek批量分类无类型实体"""
    print("\n" + "="*50)
    print("📌 Step 2: 批量分类无类型实体")
    print("="*50)
    
    with driver.session(database='neo4j') as session:
        # 获取所有无类型实体
        untyped = list(session.run(
            "MATCH (n:Entity) WHERE n.entityType IS NULL RETURN n.name as name"
        ))
        
        if not untyped:
            print("✅ 没有无类型实体，跳过")
            return
        
        print(f"待分类实体总数: {len(untyped)}")
        
        # 先尝试规则分类
        auto_classified = 0
        ds_needed = []
        
        for u in untyped:
            name = u['name']
            etype = auto_classify(name)
            if etype:
                try:
                    session.run(
                        "MATCH (n:Entity {name: $name}) SET n.entityType = $type",
                        name=name, type=etype
                    )
                    auto_classified += 1
                except:
                    ds_needed.append(name)
            else:
                ds_needed.append(name)
        
        print(f"  规则自动分类: {auto_classified}")
        print(f"  需DeepSeek分类: {len(ds_needed)}")
        
        if not ds_needed:
            print("✅ 全部自动分类完成")
            return
        
        # DeepSeek批量分类（每批40个）
        batch_size = 40
        ds_classified = 0
        
        for i in range(0, len(ds_needed), batch_size):
            batch = ds_needed[i:i+batch_size]
            print(f"\n🔍 批次 {i//batch_size + 1}/{(len(ds_needed)-1)//batch_size + 1} ({len(batch)}个)")
            
            prompt = f"""你是一个知识图谱专家。请给以下实体列表打上entityType标签。

可选类型：Company(企业/公司), Person(人员/员工), Course(课程/培训), 
Certification(证书/执照), Regulation(法规/条例), Position(职位/岗位), 
Document(文档/报告/方案), Location(地区/城市), Product(产品/设备/系统), 
Skill(技能/技术), Category(分类/标签), Event(活动/事件), TrainingDevice(训练设备/工具)

只输出JSON数组，格式：
[{{"name": "实体名", "type": "类型"}}]

实体列表：
{json.dumps(batch, ensure_ascii=False)}"""
            
            result = deepseek_batch(prompt)
            if not result:
                print(f"  ❌ 批次调用失败")
                continue
            
            for item in result:
                name = item.get('name', '')
                etype = item.get('type', '')
                if name and etype:
                    try:
                        session.run(
                            "MATCH (n:Entity {name: $name}) SET n.entityType = $type",
                            name=name, type=etype
                        )
                        ds_classified += 1
                    except:
                        pass
            
            print(f"  已分类: {ds_classified}")
            time.sleep(1)
        
        print(f"\n📊 DeepSeek分类: {ds_classified}")
        
    # 最终统计
    with driver.session(database='neo4j') as session:
        remaining = session.run(
            "MATCH (n:Entity) WHERE n.entityType IS NULL RETURN count(n) as cnt"
        ).single()['cnt']
        print(f"\n📊 剩余未分类: {remaining}")

def verify_caac_exam_link():
    """Step 3: 验证CAAC题库文件全部入库并关联"""
    print("\n" + "="*50)
    print("📌 Step 3: 验证CAAC题库文件入库完整性")
    print("="*50)
    
    feishu_files = [
        ("综合问答.docx", "OWNJbG04rohTi3xrwsecjLyvnlh"),
        ("旋翼无人机.docx", "PtPrbhh1GozODPxm40BcsNhonMf"),
        ("系统组成及介绍.docx", "EI9HbSTsQosOKdxsDX7cfDqJnVe"),
        ("无人机任务规划.docx", "B37vbbMYYoOXpsx4AQEcqkW4nKc"),
        ("无人机教员题库.docx", "NlGsbmxi7oZ1QIxMC84cCfO4nfW"),
        ("无人机飞行手册、法律法规及其他.docx", "Q5Xebw0SVoZoVzxQx9McovZQnye"),
        ("无人机操作注意事项.docx", "T9RebmYHJoRuKpx2Utyc5cZNnkd"),
        ("气象.docx", "EJRobhoePo1MCCxjHeRcsvaFnCg"),
        ("空中交通管制.docx", "Cr6ObOTk7oVRymxTY02ceRWmnsc"),
        ("概述.docx", "DG8EbFAWaojWZcxL0FmckwPwnHd"),
        ("飞行原理与飞行性能.docx", "KCPRbyOD3oMVSGx3w6EcKXWvnbb"),
    ]
    
    with driver.session(database='neo4j') as session:
        for fname, ftoken in feishu_files:
            # 查Document节点
            doc = list(session.run(
                "MATCH (d:Document) WHERE d.file_token = $token OR d.name CONTAINS $name "
                "RETURN d.name, d.file_token LIMIT 1",
                token=ftoken, name=fname.replace('.docx','')
            ))
            
            if doc:
                d = doc[0]
                # 查该文档关联的知识点数
                kp_count = session.run(
                    "MATCH (d:Document {name: $dname})-[r:CONTAINS]->(kp) RETURN count(kp) as cnt",
                    dname=d['d.name']
                ).single()['cnt']
                
                # 查关联到CAAC理论考试
                exam_link = session.run(
                    "MATCH (d:Document {name: $dname})-[r1]->(e:Entity {name:'CAAC理论考试'}) "
                    "RETURN count(r1) as cnt",
                    dname=d['d.name']
                ).single()['cnt']
                
                status = "✅" if kp_count > 0 else "⚠️"
                exam_status = "✅" if exam_link > 0 else "⚠️ 未直接关联"
                print(f"  {status} {fname}")
                print(f"     入库: {d['d.name']} | 关联知识点: {kp_count} | 理论考试: {exam_status}")
            else:
                print(f"  ❌ {fname} - 未入库！")
        
        # 文档与CAAC理论考试的深层关联统计
        print(f"\n📊 所有题库文档关联到CAAC理论考试的总路径：")
        total_kp_in_exam = session.run(
            "MATCH (e:Entity {name:'CAAC理论考试'})-[r:CONTAINS]->(kp) RETURN count(kp) as cnt"
        ).single()['cnt']
        print(f"  CAAC理论考试直接关联知识点: {total_kp_in_exam}")

def main():
    print("🔥 CAAC知识图谱深度审计 — Phase 2")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Step 1
    fix_isolated_kp()
    
    # Step 2 
    classify_entities_batch()
    
    # Step 3
    verify_caac_exam_link()
    
    # 最终统计
    print("\n" + "="*60)
    print("📊 最终统计")
    print("="*60)
    with driver.session(database='neo4j') as session:
        total = session.run("MATCH (n:Entity) RETURN count(n) as cnt").single()['cnt']
        with_type = session.run("MATCH (n:Entity) WHERE n.entityType IS NOT NULL RETURN count(n) as cnt").single()['cnt']
        kp = session.run("MATCH (n:Entity {entityType:'KnowledgePoint'}) RETURN count(n) as cnt").single()['cnt']
        kp_with_out = session.run(
            "MATCH (n:Entity {entityType:'KnowledgePoint'}) WHERE (n)-->() RETURN count(n) as cnt"
        ).single()['cnt']
        kp_isolated = session.run(
            "MATCH (n:Entity {entityType:'KnowledgePoint'}) WHERE NOT (n)-->() RETURN count(n) as cnt"
        ).single()['cnt']
        total_rels = session.run("MATCH ()-[r]->() RETURN count(r) as cnt").single()['cnt']
        
        print(f"  总Entity节点: {total}")
        print(f"  已分类(有entityType): {with_type} ({round(with_type/total*100,2)}%)")
        print(f"  未分类(无entityType): {total - with_type}")
        print(f"  总知识点: {kp}")
        print(f"  知识点有出边: {kp_with_out}")
        print(f"  知识点无出边(孤立): {kp_isolated}")
        print(f"  总关系: {total_rels}")
    
    driver.close()
    print("\n✅ Phase 2 审计修复完成！")

if __name__ == "__main__":
    main()
