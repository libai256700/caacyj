#!/usr/bin/env python3
"""
知识图谱实体抽取管道
读取飞书文档 → DeepSeek/GPT 抽取实体和关系 → 写入 Neo4j
"""

import json
import os
import re
import sys
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("❌ 请先安装: pip install neo4j")
    sys.exit(1)

try:
    import requests
    from datetime import datetime
except ImportError:
    print("❌ 请先安装: pip install requests")
    sys.exit(1)

# ============ 配置 ============
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS_PATH = Path(__file__).parent.parent / "neo4j" / ".neo4j_pass"
if NEO4J_PASS_PATH.exists():
    NEO4J_PASS = NEO4J_PASS_PATH.read_text().strip()
else:
    NEO4J_PASS = os.environ.get("NEO4J_PASS", "")

# LLM API 配置（GPT 5.5 via 中转站）
# DeepSeek V4 Flash（国内直连，速度快成本低）
LLM_API_KEY = "sk-656d953ec2bc4334aca2df495ca859c9"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"
LLM_TIMEOUT = 120  # 秒

# 实体抽取 Prompt
EXTRACT_PROMPT = """你是一个知识图谱实体抽取专家。请从以下公司制度文档中提取实体和关系。

## 实体类型定义
- Organization: 组织/公司/部门
- Person: 角色/岗位
- Policy: 制度/规定/流程
- Product: 产品/服务/课程
- Event: 活动/培训/会议
- Document: 文档/手册

## 关系类型定义（至少使用以下7种）
- belongs_to: 属于（人→部门，制度→公司）
- contains: 包含（手册→章节）
- references: 引用（制度→手册）
- required_by: 要求（制度→岗位）
- manages: 管理（人→部门）
- regulates: 规范（制度→行为）
- provides: 提供（公司→产品）

## 输出格式
返回 JSON 格式，严格如下：
{
  "entities": [
    {
      "id": "ent_1",
      "name": "实体名称",
      "type": "Organization|Person|Policy|Product|Event|Document",
      "description": "简短描述"
    }
  ],
  "relations": [
    {
      "from_id": "ent_1",
      "to_id": "ent_2",
      "type": "关系类型",
      "description": "关系描述"
    }
  ]
}

请仔细分析文档，提取所有有意义的实体和关系，尽可能完整。
"""


def call_llm(document_text: str, doc_name: str) -> dict:
    """调用 LLM 进行实体抽取"""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = EXTRACT_PROMPT + f"\n\n## 文档名称：{doc_name}\n\n## 文档内容\n{document_text}"
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个知识图谱构建专家。只输出 JSON，不要其他文字。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 4096
    }
    
    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=LLM_TIMEOUT
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        reasoning = resp.json()["choices"][0]["message"].get("reasoning_content", "")
        
        # 先找 content 里的 JSON，没有的话找 reasoning_content 里的
        full_text = content or reasoning
        json_match = re.search(r'\{.*\}', full_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result
        elif content:
            print(f"⚠️ LLM 输出没有 JSON: {content[:200]}")
            return {"entities": [], "relations": []}
        else:
            print(f"⚠️ LLM 返回空（可能还在 reasoning 中），尝试从 reasoning 提取...")
            json_match = re.search(r'\{.*\}', reasoning, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            print(f"⚠️ reasoning 中也没找到 JSON")
            return {"entities": [], "relations": []}
            
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        return {"entities": [], "relations": []}


def write_to_neo4j(entities: list, relations: list, doc_name: str):
    """将抽取的实体和关系写入 Neo4j"""
    if not entities:
        print("⚠️ 没有实体需要写入")
        return
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    with driver.session(database="neo4j") as session:
        # 1. 创建源文档节点
        session.run(
            "MERGE (d:Document {name: $name}) "
            "SET d.source = 'feishu', d.imported_at = datetime()",
            name=doc_name
        )
        
        # 2. 创建实体节点
        for ent in entities:
            props = {
                "name": ent.get("name", ""),
                "type": ent.get("type", "Unknown"),
                "description": ent.get("description", ""),
                "imported_at": str(datetime.now())
            }
            # 添加额外属性
            for k, v in ent.get("properties", {}).items():
                props[k] = str(v)[:500] if v else ""
            
            session.run(
                "MERGE (e:Entity {id: $id}) "
                "SET e.name = $name, "
                "    e.type = $type, "
                "    e.description = $description, "
                f"   e += $props "
                "SET e.imported_at = datetime()",
                id=ent.get("id", ""),
                name=ent.get("name", ""),
                type=ent.get("type", "Unknown"),
                description=ent.get("description", ""),
                props={k: v for k, v in props.items() if k not in ("name", "type", "description")}
            )
            
            # 3. 关联文档→实体
            session.run(
                "MATCH (d:Document {name: $doc_name}) "
                "MATCH (e:Entity {id: $ent_id}) "
                "MERGE (d)-[:CONTAINS]->(e)",
                doc_name=doc_name,
                ent_id=ent.get("id", "")
            )
        
        # 4. 创建实体间关系
        for rel in relations:
            session.run(
                "MATCH (a:Entity {id: $from_id}) "
                "MATCH (b:Entity {id: $to_id}) "
                f"MERGE (a)-[r:{rel.get('type', 'RELATED_TO')} {{description: $desc}}]->(b)",
                from_id=rel.get("from_id", ""),
                to_id=rel.get("to_id", ""),
                desc=rel.get("description", "")
            )
    
    driver.close()
    print(f"✅ 写入完成: {len(entities)} 个实体, {len(relations)} 个关系 → Neo4j")


def process_document(file_path: str, doc_name: str = None):
    """处理单个文档"""
    if doc_name is None:
        doc_name = Path(file_path).stem
    
    print(f"\n{'='*50}")
    print(f"📄 处理: {doc_name}")
    print(f"{'='*50}")
    
    # 读文件
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    print(f"   文档大小: {len(content)} 字符")
    
    # 调用 LLM 抽实体
    print(f"   正在调用 LLM 抽取实体...")
    result = call_llm(content, doc_name)
    
    entities = result.get("entities", [])
    relations = result.get("relations", [])
    
    print(f"   抽取结果: {len(entities)} 实体, {len(relations)} 关系")
    
    # 写入 Neo4j
    write_to_neo4j(entities, relations, doc_name)
    
    return entities, relations


def main():
    """主函数"""
    raw_dir = Path(__file__).parent.parent / "feishu_raw"
    
    if not raw_dir.exists():
        print(f"❌ 文档目录不存在: {raw_dir}")
        return
    
    files = sorted(raw_dir.glob("*.txt"))
    if not files:
        print("❌ 没有找到文档文件")
        return
    
    print(f"找到 {len(files)} 份文档")
    
    all_entities = []
    all_relations = []
    
    for file_path in files:
        entities, relations = process_document(str(file_path))
        all_entities.extend(entities)
        all_relations.extend(relations)
        
        # 保存中间结果
        result_file = raw_dir / f"{file_path.stem}_result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump({"entities": entities, "relations": relations}, f, ensure_ascii=False, indent=2)
        print(f"   中间结果已保存: {result_file.name}")
    
    # 汇总
    print(f"\n{'='*50}")
    print(f"📊 汇总: {len(all_entities)} 实体, {len(all_relations)} 关系")
    print(f"{'='*50}")
    
    # 保存汇总结果
    summary = {
        "total_entities": len(all_entities),
        "total_relations": len(all_relations),
        "entities_by_type": {},
        "relations_by_type": {}
    }
    for e in all_entities:
        t = e.get("type", "Unknown")
        summary["entities_by_type"][t] = summary["entities_by_type"].get(t, 0) + 1
    for r in all_relations:
        t = r.get("type", "Unknown")
        summary["relations_by_type"][t] = summary["relations_by_type"].get(t, 0) + 1
    
    summary_file = raw_dir / "_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"📊 汇总: {json.dumps(summary, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
