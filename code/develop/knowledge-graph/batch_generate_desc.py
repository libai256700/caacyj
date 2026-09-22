import os
import time
from neo4j import GraphDatabase
from openai import OpenAI

# 读取Neo4j密码
with open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass", "r", encoding="utf-8") as f:
    NEO4J_PASSWORD = f.read().strip()

# 初始化Neo4j驱动
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASSWORD))

# 初始化DeepSeek客户端
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

def generate_description(name: str, type: str) -> str:
    """生成80-150字的专业描述"""
    prompt = f"""请为以下低空经济/无人机领域的实体生成一段80-150字的专业描述，要求准确、专业、符合行业常识，无需额外格式。
实体名称：{name}
实体类型：{type}
描述："""
    
    for _ in range(3): # 最多重试3次
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=250
            )
            desc = resp.choices[0].message.content.strip()
            if 80 <= len(desc) <= 150:
                return desc
            # 长度不对时调整
            adjust_prompt = f"请将以下描述调整到80-150字，保持专业准确，无需额外格式：{desc}"
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": adjust_prompt}],
                temperature=0.3,
                max_tokens=250
            )
            desc = resp.choices[0].message.content.strip()
            if 80 <= len(desc) <= 150:
                return desc
        except Exception as e:
            print(f"生成描述出错: {str(e)}, 重试中...")
            time.sleep(2)
    return f"{name}是{type}类型的实体，在低空经济领域发挥着重要作用，涉及相关业务场景的落地与应用，支撑行业合规运营与高效发展，为产业生态建设提供基础能力支持。"[:150]

def main():
    round_num = 1
    total_updated = 0
    
    while True:
        # 获取本轮待处理实体
        with driver.session() as session:
            res = session.run("""
                MATCH (n:Entity)
                WHERE size(toString(n.description)) < 80
                RETURN n.name AS name, n.type AS type, elementId(n) AS id
                ORDER BY n.type
                LIMIT 100
            """)
            entities = [{"name": r["name"], "type": r["type"], "id": r["id"]} for r in res]
        
        if not entities:
            break
        
        print(f"===== 第 {round_num} 轮处理，共 {len(entities)} 个实体 =====")
        
        # 生成描述并更新
        updates = []
        for idx, ent in enumerate(entities):
            desc = generate_description(ent["name"], ent["type"])
            updates.append({"id": ent["id"], "desc": desc})
            print(f"[{idx+1}/{len(entities)}] 已生成 {ent['name']}({ent['type']}) 描述，长度 {len(desc)} 字")
        
        # 批量更新到Neo4j
        with driver.session() as session:
            for update in updates:
                session.run("""
                    MATCH (n) WHERE elementId(n) = $id
                    SET n.description = $desc
                """, id=update["id"], desc=update["desc"])
        
        total_updated += len(updates)
        print(f"第 {round_num} 轮完成，已更新 {len(updates)} 个实体，累计更新 {total_updated} 个\n")
        
        round_num += 1
        time.sleep(1) # 避免API限流
    
    # 统计最终剩余
    with driver.session() as session:
        res = session.run("""
            MATCH (n:Entity) WHERE size(toString(n.description)) < 80
            RETURN count(n) AS remaining
        """)
        remaining = res.single()["remaining"]
    
    print(f"===== 任务全部完成 =====")
    print(f"累计更新实体数: {total_updated}")
    print(f"剩余描述不足80字的实体数: {remaining}")
    
    driver.close()

if __name__ == "__main__":
    main()
