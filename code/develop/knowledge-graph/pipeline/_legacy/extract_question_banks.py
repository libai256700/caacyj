#!/usr/bin/env python3
"""
题库实体抽取 v1.0 — DeepSeek Pro 专项
处理 feishu_raw/ 中未入库的8个题库文件
→ 提取知识点实体 → 导入Neo4j → 建立考试核心节点 → 链接
"""

import json, os, sys, time, re, requests
from pathlib import Path
from neo4j import GraphDatabase

# ============ 配置 ============
BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "feishu_raw"
CONFIG_PATH = Path(__file__).parent / "config.json"

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "yj123456"

# 使用 DeepSeek Pro（来自配置）
PRO_CONFIG = CONFIG["models"]["pro"]
DS_API_KEY = PRO_CONFIG["api_key"]
DS_BASE_URL = PRO_CONFIG["base_url"]
DS_TIMEOUT = PRO_CONFIG["timeout"]
DS_MODEL = PRO_CONFIG["name"]

# ============ 题库文件清单 ============
# 格式: (文件名, 考试科目, 描述)
QUESTION_BANKS = [
    ("气象", "CAAC理论考试", "民航无人机驾驶员气象知识点，含大气组成、风、云、能见度等"),
    ("综合问答", "CAAC理论考试", "无人机综合知识问答，涵盖原理、操作、法规等"),
    ("无人机飞行手册、法律法规及其他", "CAAC理论考试", "无人机飞行手册、国家法律法规、安全规范等"),
    ("系统组成及介绍", "CAAC理论考试", "无人机系统组成与各部件功能介绍"),
    ("无人机操作注意事项", "CAAC理论考试", "无人机飞行操作注意事项与安全规范"),
    ("旋翼无人机", "CAAC理论考试", "旋翼无人机的结构、原理与飞行特性"),
    ("无人机任务规划", "CAAC理论考试", "无人机任务规划方法与参数设计"),
    ("空中交通管制", "CAAC理论考试", "空中交通管制规则与无人机飞行管理"),
]

# ============ 题库专用提取提示词 ============
QUESTION_BANK_PROMPT = """你是一个专业知识图谱抽取专家。请从以下 CAAC 无人机题库中提取关键知识概念实体。

这份文档是 CAAC 无人机驾驶员执照考试题库，包含选择题和答案解析。

## 任务
从题库内容中提取**核心知识概念**实体，每个实体代表一个独立的知识点或主题。

## 实体的"度"把握
- 提取的是「知识概念/主题」，不是每道题一个实体
- 例如「气压高度」「风的形成」「GPS定位原理」是合适的实体
- 不要提取具体的题目编号、选项字母、参考答案等题目自身结构信息
- 同一主题不管出现多少次，只输出一个实体

## 输出格式（纯JSON，不要```标记，不要markdown）
{
  "entities": [
    {"name": "知识点名称", "description": "简短说明（10-30字）"},
    {"name": "另一个知识点", "description": "... ..."}
  ]
}

请仔细分析文档，提取5-30个核心知识概念。注意：宁缺毋滥，只提取真正重要的概念。"""

# ============ DeepSeek Pro 调用 ============

def call_deepseek_pro(text: str, doc_name: str) -> dict:
    """调用 DeepSeek Pro 提取实体"""
    
    # 截断内容（Pro上下文窗口有限）
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars]
    
    prompt = QUESTION_BANK_PROMPT + f"\n\n## 文档名称：{doc_name}\n\n## 文档内容\n{text}"
    
    payload = {
        "model": DS_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个知识图谱构建专家。只输出纯JSON，不要markdown格式，不要```代码块标记，不要任何其他文字。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 4096
    }
    
    headers = {
        "Authorization": f"Bearer {DS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"  → 调用 DeepSeek Pro({DS_MODEL})...", end=" ", flush=True)
        t0 = time.time()
        resp = requests.post(
            f"{DS_BASE_URL}/chat/completions",
            headers=headers, json=payload, timeout=(15, DS_TIMEOUT)
        )
        resp.raise_for_status()
        elapsed = time.time() - t0
        
        content = resp.json()["choices"][0]["message"]["content"]
        
        # 提取JSON
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        if start_idx != -1 and end_idx > start_idx:
            result = json.loads(content[start_idx:end_idx+1])
            ents = result.get("entities", [])
            print(f"✅ {len(ents)}实体 ({elapsed:.1f}s)")
            return ents
        else:
            print(f"⚠️ 未找到JSON ({elapsed:.1f}s)")
            return []
            
    except Exception as e:
        print(f"❌ {e}")
        return []


# ============ Neo4j 操作 ============

def import_to_neo4j(doc_name: str, entities: list, source_file: str):
    """将提取的实体导入Neo4j，并链接到文档"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    created = 0
    
    with driver.session(database="neo4j") as session:
        # 1. 创建或更新 Document 节点（题库文件）
        session.run(
            "MERGE (d:Document {name: $name}) "
            "SET d.title = $name, d.source = '题库', d.category = '课件'",
            name=f"{doc_name}.txt"
        )
        
        # 2. 创建或更新每个实体，链接到文档
        for ent in entities:
            name = ent.get("name", "").strip()
            desc = ent.get("description", "").strip()
            if not name:
                continue
            
            result = session.run(
                "MERGE (e:Entity {name: $name}) "
                "SET e.description = $desc, "
                "    e.source_doc = $source_file, "
                "    e.source = $doc_name, "
                "    e.entityType = 'KnowledgePoint' "
                "RETURN e.name",
                name=name, desc=desc,
                source_file=f"{doc_name}.txt",
                doc_name=doc_name
            )
            if result.single():
                created += 1
            
            # 3. 链接 Document → Entity
            session.run(
                "MATCH (d:Document {name: $doc_file}) "
                "MATCH (e:Entity {name: $ent_name}) "
                "MERGE (d)-[:CONTAINS]->(e)",
                doc_file=f"{doc_name}.txt",
                ent_name=name
            )
    
    driver.close()
    return created


def ensure_exam_nodes():
    """确保3个考试核心节点存在"""
    exam_nodes = [
        {
            "name": "CAAC理论考试",
            "description": "中国民用航空局组织的无人机驾驶员理论考试，涵盖飞行原理、气象、法规等科目"
        },
        {
            "name": "CAAC无人机执照考试",
            "description": "CAAC无人机驾驶员执照资格认证考试，含理论和实操"
        },
        {
            "name": "CAAC实操考试",
            "description": "CAAC无人机驾驶员实际操作考试，含悬停、八字飞行、电子桩等"
        }
    ]
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        for node in exam_nodes:
            result = session.run(
                "MERGE (e:Entity {name: $name}) "
                "SET e.description = $desc, "
                "    e.entityType = 'Exam', "
                "    e.category = '考试' "
                "RETURN e.name",
                name=node["name"], desc=node["description"]
            )
            print(f"  ✅ 考试节点: {result.single()['e.name']}")
    
    driver.close()


def link_entities_to_exam(doc_name: str, target_exam: str):
    """将文档关联的实体链接到考试节点"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    with driver.session(database="neo4j") as session:
        # 找到当前文档下的所有实体，链接到考试节点
        result = session.run(
            "MATCH (d:Document {name: $doc})-[r:CONTAINS]->(e:Entity) "
            "MATCH (exam:Entity {name: $exam}) "
            "MERGE (exam)-[:CONTAINS]->(e) "
            "RETURN count(e) as linked",
            doc=f"{doc_name}.txt", exam=target_exam
        )
        linked = result.single()["linked"]
        print(f"  🔗 {doc_name} → {target_exam}: {linked} 实体已链接")
    
    driver.close()


# ============ 主流程 ============

def process_remaining_banks():
    """处理未入库的题库文件"""
    results = {}
    
    print("=" * 60)
    print("📚 题库实体提取 — DeepSeek Pro 专项")
    print("=" * 60)
    
    for filename, target_exam, desc in QUESTION_BANKS:
        txt_path = RAW_DIR / f"{filename}.txt"
        
        if not txt_path.exists():
            print(f"⚠️ 文件不存在，跳过: {txt_path}")
            continue
        
        print(f"\n📄 {filename}.txt ({desc})")
        print(f"   ({target_exam})")
        
        # 1. 用 DeepSeek Pro 提取实体
        entities = call_deepseek_pro(txt_path.read_text(encoding="utf-8"), filename)
        
        if not entities:
            print(f"  ⏭️ 无实体提取，跳过")
            results[filename] = {"entities": 0, "created": 0}
            continue
        
        # 2. 导入 Neo4j
        created = import_to_neo4j(filename, entities, filename)
        print(f"  💾 Neo4j入库: {created}/{len(entities)} 实体")
        
        # 3. 链接到考试节点
        link_entities_to_exam(filename, target_exam)
        
        results[filename] = {"entities": len(entities), "created": created}
        
        # API调用间短暂休息，避免限流
        time.sleep(1)
    
    return results


def verify_results():
    """验证最终成果"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    print("\n" + "=" * 60)
    print("🔍 验证结果")
    print("=" * 60)
    
    with driver.session(database="neo4j") as session:
        # 考试节点检查
        for name in ["CAAC理论考试", "CAAC无人机执照考试", "CAAC实操考试"]:
            result = session.run(
                "MATCH (e:Entity {name: $name}) RETURN e.name, e.entityType, e.description LIMIT 1",
                name=name
            )
            for r in result:
                print(f"  ✅ {r['e.name']} ({r['e.entityType']})")
        
        # 统计
        result = session.run(
            "MATCH (exam:Entity {name: 'CAAC理论考试'})-[r:CONTAINS]->(e:Entity) "
            "RETURN count(r) as total"
        )
        total = result.single()["total"]
        print(f"\n  📊 CAAC理论考试 → 连接实体: {total} 个")
        
        result = session.run(
            "MATCH (e:Entity) WHERE e.source_doc ENDS WITH '.txt' AND e.entityType = 'KnowledgePoint' "
            "RETURN count(e) as total"
        )
        total_kp = result.single()["total"]
        print(f"  📊 KnowledgePoint实体总计: {total_kp} 个")
        
        # 各题库文件实体数
        result = session.run(
            "MATCH (e:Entity) WHERE e.entityType = 'KnowledgePoint' "
            "RETURN e.source_doc as doc, count(*) as cnt "
            "ORDER BY cnt DESC"
        )
        print(f"\n  📋 各题库文件实体数:")
        for r in result:
            print(f"     {r['doc']}: {r['cnt']} 实体")
    
    driver.close()


# ============ 入口 ============
if __name__ == "__main__":
    print(f"使用模型: {DS_MODEL}")
    print(f"模型来源: {DS_BASE_URL}")
    print()
    
    # 1. 确保考试核心节点
    print("📌 Step 1: 确保考试核心节点")
    ensure_exam_nodes()
    
    # 2. 处理未入库题库
    print("\n📌 Step 2: 提取题库实体")
    results = process_remaining_banks()
    
    # 3. 验证
    print("\n📌 Step 3: 验证结果")
    verify_results()
    
    # 4. 汇总
    print("\n" + "=" * 60)
    print("📊 汇总")
    print("=" * 60)
    total_ents = sum(r["entities"] for r in results.values())
    total_created = sum(r["created"] for r in results.values())
    processed = len(results)
    print(f"  处理题库文件: {processed}/8")
    print(f"  提取实体总计: {total_ents}")
    print(f"  入库成功: {total_created}")
    print("=" * 60)
    print("✅ 完成！")
