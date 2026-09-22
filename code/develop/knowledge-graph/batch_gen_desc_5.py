from neo4j import GraphDatabase
import os, sys

# Neo4j配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
with open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass", "r") as f:
    NEO4J_PASSWORD = f.read().strip()

# 导入kg_query
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kg_query import query

def get_entities():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    entities = []
    with driver.session() as session:
        result = session.run("""
            MATCH (n:Entity) 
            WHERE size(toString(n.description)) < 80 
            RETURN n.name AS name, n.type AS type, elementId(n) AS id
            ORDER BY n.type 
            LIMIT 100
        """)
        for record in result:
            entities.append({"name": record["name"], "type": record["type"], "id": record["id"]})
    driver.close()
    return entities

def generate_description(entity_name, entity_type):
    prompt = f"""你是低空经济/无人机领域的专业编辑，请为以下实体生成一段80到150字的专业准确的描述，符合行业常识，语言通顺专业。
实体名称：{entity_name}
实体类型：{entity_type}
只输出描述内容，不要其他多余内容。"""
    resp = query(prompt)
    if resp.get("ok"):
        return resp.get("answer", "").strip()
    return ""

def update_description(entity_id, desc):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.run("""
            MATCH (n:Entity) 
            WHERE elementId(n) = $id 
            SET n.description = $d
        """, {"id": entity_id, "d": desc})
    driver.close()

def count_remaining():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("""
            MATCH (n:Entity) 
            WHERE size(toString(n.description)) < 80 
            RETURN count(n) AS cnt
        """)
        cnt = result.single()["cnt"]
    driver.close()
    return cnt

if __name__ == "__main__":
    print("开始第5批实体描述生成...")
    entities = get_entities()
    print(f"获取到{len(entities)}个需要生成描述的实体")
    
    success = 0
    for idx, entity in enumerate(entities):
        try:
            print(f"正在处理第{idx+1}/{len(entities)}个: {entity['name']}({entity['type']})")
            desc = generate_description(entity['name'], entity['type'])
            if not desc or len(desc) < 50:
                print(f"生成描述过短，跳过: {desc}")
                continue
            print(f"生成描述: {desc} (长度:{len(desc)})")
            update_description(entity['id'], desc)
            success +=1
        except Exception as e:
            print(f"处理{entity['name']}失败: {str(e)}")
            continue
    
    print(f"处理完成，成功{success}个，失败{len(entities)-success}个")
    remaining = count_remaining()
    print(f"剩余需要生成描述的实体数量: {remaining}")
