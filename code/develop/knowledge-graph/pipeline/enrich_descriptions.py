#!/usr/bin/env python3
"""批量补齐Entity节点description — 调用豆包API"""
import json, os, http.client, sys, time
from neo4j import GraphDatabase
from urllib.parse import urlparse

# 配置
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
with open(os.path.join(BASE_DIR, 'neo4j', '.neo4j_pass')) as f:
    NEO4J_PASS = f.read().strip()

with open(os.path.join(os.path.dirname(__file__), 'config.json')) as f:
    cfg = json.load(f)

doubao = cfg['models']['doubao']
DOUBAO_KEY = doubao['api_key']
DOUBAO_URL = doubao['base_url']  # https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL = doubao['name']    # doubao-seed-2-0-pro-260215

os.environ['NO_PROXY'] = '*'
BATCH_SIZE = 50
MIN_DESC_LEN = 80
TARGET_DESC_LEN = "80-200"

def call_doubao(prompt):
    """调用豆包API"""
    pu = urlparse(DOUBAO_URL)
    body = json.dumps({
        "model": DOUBAO_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 8192
    }).encode()
    
    conn = http.client.HTTPSConnection(pu.hostname, pu.port or 443, timeout=120)
    conn.request("POST", f"{pu.path}/chat/completions", body=body,
        headers={"Authorization": f"Bearer {DOUBAO_KEY}", "Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    
    if resp.status != 200:
        print(f"  ❌ API错误 {resp.status}: {data[:200]}")
        return None
    
    response = json.loads(data)
    content = response['choices'][0]['message']['content'].strip()
    
    # 清理代码块
    if content.startswith('```'):
        nl = content.find('\n')
        if nl > 0:
            content = content[nl+1:]
        else:
            content = content[3:]
    if content.endswith('```'):
        content = content[:-3].strip()
    
    return content

def parse_batch_response(content, batch):
    """解析豆包返回的JSON数组"""
    try:
        results = json.loads(content)
        if isinstance(results, list):
            return results
    except:
        pass
    
    # 尝试从文本中提取
    results = []
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            continue
        # 尝试匹配 "name | desc" 或 "name: desc" 格式
        for entity in batch:
            if entity['name'] in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    results.append({"name": entity['name'], "description": parts[1].strip()})
                else:
                    parts = line.split(':', 1)
                    if len(parts) == 2 and entity['name'] in parts[0]:
                        results.append({"name": entity['name'], "description": parts[1].strip()})
                break
    
    return results

def main():
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))
    
    with driver.session() as s:
        total = s.run("MATCH (n:Entity) RETURN count(n) AS c").single()['c']
        short_before = s.run(
            f"MATCH (n:Entity) WHERE n.description IS NULL OR size(toString(n.description)) < {MIN_DESC_LEN} "
            "RETURN count(n) AS c"
        ).single()['c']
        print(f"总实体: {total}, 描述不足{MIN_DESC_LEN}字: {short_before}")
        
        # 提取需要更新的节点
        nodes = s.run(f"""
            MATCH (n:Entity) 
            WHERE n.description IS NULL OR size(toString(n.description)) < {MIN_DESC_LEN}
            RETURN n.name AS name, n.type AS type, n.source_doc AS doc, n.description AS desc
            ORDER BY 
                CASE n.type 
                    WHEN 'KnowledgePoint' THEN 0
                    WHEN 'Skill' THEN 1
                    WHEN 'Regulation' THEN 2
                    WHEN 'Certification' THEN 3
                    ELSE 4
                END
        """).data()
        
        print(f"需更新: {len(nodes)} 个节点")
        
        # 分批处理
        batches = [nodes[i:i+BATCH_SIZE] for i in range(0, len(nodes), BATCH_SIZE)]
        total_updated = 0
        
        for bi, batch in enumerate(batches):
            print(f"\n批次 {bi+1}/{len(batches)} ({len(batch)}个节点)...")
            
            # 构造prompt
            entity_list = "\n".join(
                f"{i+1}. name={n['name']} | type={n['type']} | 当前描述={(n['desc'] or '无')[:60]}"
                for i, n in enumerate(batch)
            )
            
            prompt = f"""你是无人机行业知识编辑。请为以下知识图谱实体节点补全description（{TARGET_DESC_LEN}字）。

输出JSON数组，每个元素格式：{{"name":"实体名","description":"完整描述"}}

要求：
- 根据name和type撰写专业、信息丰富的描述
- 包括：定义、核心要点、关键特征
- 描述要充实（{TARGET_DESC_LEN}字），能在向量检索中提供足够的语义信息
- 参考但扩展当前的简短描述

实体列表：
{entity_list}

只输出JSON数组。"""
            
            content = call_doubao(prompt)
            if not content:
                print(f"  ❌ 批次{bi+1} API调用失败，重试...")
                time.sleep(3)
                content = call_doubao(prompt)
                if not content:
                    print(f"  ❌ 重试失败，跳过此批")
                    continue
            
            # 解析和更新
            try:
                results = json.loads(content)
            except:
                print(f"  ❌ JSON解析失败，前200字: {content[:200]}")
                continue
            
            updated = 0
            for item in results:
                name = item.get('name', '')
                desc = item.get('description', '')
                if name and desc and len(desc) >= 20:
                    try:
                        s.run(
                            "MATCH (n:Entity {name:$name}) SET n.description=$desc",
                            name=name, desc=desc
                        )
                        updated += 1
                    except Exception as e:
                        print(f"  ⚠️ 更新{name}失败: {e}")
            
            total_updated += updated
            print(f"  ✅ 更新{updated}个，累计{total_updated}/{len(nodes)}")
            
            if bi < len(batches) - 1:
                time.sleep(1)  # 避免频率限制
        
        # 验证
        short_after = s.run(
            f"MATCH (n:Entity) WHERE n.description IS NULL OR size(toString(n.description)) < {MIN_DESC_LEN} "
            "RETURN count(n) AS c"
        ).single()['c']
        print(f"\n{'='*50}")
        print(f"完成！描述不足{MIN_DESC_LEN}字: {short_before} → {short_after}")
        print(f"共更新 {total_updated} 个节点")
    
    driver.close()

if __name__ == '__main__':
    main()
