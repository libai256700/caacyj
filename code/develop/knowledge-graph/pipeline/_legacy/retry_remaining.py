#!/usr/bin/env python3
"""补跑超时的两个题库文件"""

import json, os, sys, time, requests
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
DS_TIMEOUT = 90  # 超时时间加1.5倍避免再超时
DS_MODEL = PRO_CONFIG["name"]

# ============ 待补跑文件 ============
RETRY_FILES = [
    ("无人机操作注意事项", "CAAC理论考试", "无人机飞行操作注意事项与安全规范"),
    ("旋翼无人机", "CAAC理论考试", "旋翼无人机的结构、原理与飞行特性"),
]

# ============ 提取提示词 ============
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
    
    # 截断内容
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
        # 1. 创建或更新 Document 节点
        session.run(
            "MERGE (d:Document {name: $name}) "
            "SET d.title = $name, d.source = '题库', d.category = '课件'",
            name=f"{doc_name}.txt"
        )
        
        # 2. 创建或更新每个实体
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
            
            # 4. 链接到考试节点
            session.run(
                "MATCH (exam:Entity {name: 'CAAC理论考试'}) "
                "MATCH (e:Entity {name: $ent_name}) "
                "MERGE (exam)-[:CONTAINS]->(e)",
                ent_name=name
            )
    
    driver.close()
    return created


# ============ 主流程 ============

def main():
    print("=" * 50)
    print("🔧 补跑超时题库文件")
    print("=" * 50)
    
    total_created = 0
    for filename, target_exam, desc in RETRY_FILES:
        txt_path = RAW_DIR / f"{filename}.txt"
        print(f"\n📄 {filename}.txt ({desc})")
        entities = call_deepseek_pro(txt_path.read_text(encoding="utf-8"), filename)
        
        if not entities:
            print(f"  ⏭️ 提取失败")
            continue
        
        created = import_to_neo4j(filename, entities, filename)
        print(f"  💾 入库成功: {created}/{len(entities)} 实体")
        total_created += created
        
        time.sleep(1)
    
    print(f"\n✅ 补跑完成，新增 {total_created} 实体！")
    
    # 最终验证
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        result = session.run(
            "MATCH (exam:Entity {name: 'CAAC理论考试'})-[r:CONTAINS]->(e:Entity) "
            "WHERE e.entityType = 'KnowledgePoint' "
            "RETURN count(r) as total"
        )
        total = result.single()["total"]
        print(f"📊 最终CAAC理论考试关联知识点总数: {total} 个")
        
        # 查看各文件分布
        print("\n📋 各题库文件实体数：")
        result = session.run(
            "MATCH (e:Entity {entityType: 'KnowledgePoint'}) "
            "RETURN e.source_doc as doc, count(*) as cnt "
            "ORDER BY cnt DESC"
        )
        for r in result:
            print(f"  {r['doc']}: {r['cnt']} 实体")
    
    driver.close()

if __name__ == "__main__":
    main()
