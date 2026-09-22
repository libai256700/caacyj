#!/usr/bin/env python3
"""修复未标注的知识点，重新跑标签"""

import json, os, sys, time, requests
from pathlib import Path
from neo4j import GraphDatabase

# ============ 配置 ============
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = Path(__file__).parent / "config.json"

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "yj123456"

# DeepSeek Pro 配置
PRO_CONFIG = CONFIG["models"]["pro"]
DS_API_KEY = PRO_CONFIG["api_key"]
DS_BASE_URL = PRO_CONFIG["base_url"]
DS_TIMEOUT = 60
DS_MODEL = PRO_CONFIG["name"]

# 章节分类定义
CHAPTERS = [
    "气象", "法律法规", "无人机系统组成", "飞行原理", "操作规范",
    "空中交通管制", "任务规划", "旋翼无人机特性", "综合知识"
]

# ============ 标注提示词 ============
LABEL_PROMPT = """你是CAAC无人机驾驶员考试考点标注专家。请给以下知识点打两个标签。

## 知识点信息
名称：{name}
描述：{description}
来源文档：{source_doc}

## 标签规范
1. 难度：只能选「易/中/难」
   - 易：基础常识题，属于送分题，学员必须掌握
   - 中：常考核心题，需要理解记忆
   - 难：拔高题，容易丢分，需要深入理解
2. 所属章节：从以下列表选最匹配的一个：
   {chapters}

## 输出格式（纯JSON，不要任何其他内容，不要```标记）
{{
  "difficulty": "难度",
  "chapter": "所属章节"
}}
"""

# ============ DeepSeek Pro 调用 ============
def call_deepseek_label(name: str, desc: str, source_doc: str) -> dict:
    prompt = LABEL_PROMPT.format(
        name=name,
        description=desc if desc else "无",
        source_doc=source_doc if source_doc else "无",
        chapters="\n   ".join([f"- {c}" for c in CHAPTERS])
    )
    
    payload = {
        "model": DS_MODEL,
        "messages": [
            {"role": "system", "content": "你是专业的考试考点标注专家，只输出纯JSON，不要任何其他内容，不要解释，不要多余文字。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 256
    }
    
    headers = {
        "Authorization": f"Bearer {DS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    for retry in range(3):
        try:
            resp = requests.post(
                f"{DS_BASE_URL}/chat/completions",
                headers=headers, json=payload, timeout=(10, DS_TIMEOUT)
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            
            # 强清洗JSON
            content = content.strip()
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx > start_idx:
                content = content[start_idx:end_idx+1]
                # 去掉多余的逗号
                content = content.replace(',\n}', '\n}').replace(',\r\n}', '\r\n}')
                result = json.loads(content)
                # 校验字段
                if "difficulty" in result and "chapter" in result:
                    if result["difficulty"] in ["易", "中", "难"] and result["chapter"] in CHAPTERS:
                        return result
            time.sleep(1)
        except Exception as e:
            print(f"    重试 {retry+1}/3 失败: {e}")
            time.sleep(2)
    return None

# ============ 主流程 ============
def main():
    print("=" * 50)
    print("🔧 修复未标注知识点")
    print("=" * 50)
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    with driver.session(database="neo4j") as session:
        # 获取所有未标注的知识点
        result = session.run(
            "MATCH (e:Entity {entityType: 'KnowledgePoint'}) "
            "WHERE e.difficulty IS NULL OR e.chapter IS NULL "
            "RETURN e.name as name, e.description as desc, e.source_doc as source_doc "
            "ORDER BY e.source_doc"
        )
        kps = list(result)
        total = len(kps)
        if total == 0:
            print("✅ 全部知识点已标注完成！")
            return
        
        print(f"待修复知识点: {total} 个\n")
        
        success = 0
        failed = 0
        
        for idx, kp in enumerate(kps, 1):
            name = kp["name"]
            desc = kp["desc"]
            source = kp["source_doc"]
            
            print(f"[{idx}/{total}] {name}")
            print(f"  来源: {source}")
            
            labels = call_deepseek_label(name, desc, source)
            if not labels:
                failed +=1
                print(f"  ❌ 标注失败，跳过")
                continue
            
            # 写入Neo4j
            try:
                session.run(
                    "MATCH (e:Entity {name: $name}) "
                    "SET e.difficulty = $diff, "
                    "    e.chapter = $chapter",
                    name=name,
                    diff=labels["difficulty"],
                    chapter=labels["chapter"]
                )
                success +=1
                print(f"  ✅ 标注成功 | {labels['difficulty']} | {labels['chapter']}")
            except Exception as e:
                failed +=1
                print(f"  ❌ 写入失败: {e}")
            
            time.sleep(0.5)
            print()
    
    driver.close()
    
    print("=" * 50)
    print("📊 修复完成")
    print("=" * 50)
    print(f"待修复: {total}")
    print(f"成功: {success}")
    print(f"失败: {failed}")
    print("=" * 50)
    
    if failed == 0:
        print("✅ 全部标注完成！可以启动关系构建任务了！")
    else:
        print(f"⚠️  还有 {failed} 个失败，可手动标注")

if __name__ == "__main__":
    main()
