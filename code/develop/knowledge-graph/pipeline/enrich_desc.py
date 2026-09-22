#!/usr/bin/env python3
"""批量补齐实体description - 小批次版"""
import json, os, http.client, time
from neo4j import GraphDatabase
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(BASE_DIR, 'neo4j', '.neo4j_pass')) as f: pwd = f.read().strip()
with open(os.path.join(os.path.dirname(__file__), 'config.json')) as f: cfg = json.load(f)

D = cfg['models']['doubao']
PU = urlparse(D['base_url'])
BATCH = 10
MIN_LEN = 80
os.environ['NO_PROXY'] = '*'

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", pwd))

def ask(msg):
    body = json.dumps({"model":D['name'],"messages":[{"role":"user","content":msg}],"temperature":0.3,"max_tokens":4096}).encode()
    c = http.client.HTTPSConnection(PU.hostname, timeout=60)
    c.request("POST", f"{PU.path}/chat/completions", body, headers={"Authorization":f"Bearer {D['api_key']}","Content-Type":"application/json"})
    r = json.loads(c.getresponse().read()); c.close()
    t = r['choices'][0]['message']['content'].strip()
    if t.startswith('```'): t = t.split('\n',1)[1].rsplit('```',1)[0].strip()
    return t

with driver.session() as s:
    nodes = s.run(f"MATCH (n:Entity) WHERE n.description IS NULL OR size(toString(n.description)) < {MIN_LEN} RETURN n.name AS name, n.type AS type ORDER BY n.type").data()
    print(f"需更新: {len(nodes)}", flush=True)
    
    ok = 0
    for i in range(0, len(nodes), BATCH):
        batch = nodes[i:i+BATCH]
        lst = "\n".join(f"{j+1}. {n['name']} ({n['type']})" for j,n in enumerate(batch))
        
        try:
            resp = ask(f"生成JSON数组。为以下无人机知识节点各写一段80-150字描述，格式[{{\"n\":\"名称\",\"d\":\"描述\"}}]。\n{lst}")
            items = json.loads(resp)
            for item in items:
                nm, ds = item.get('n',''), item.get('d','')
                if nm and ds and len(ds)>=20:
                    s.run("MATCH (n:Entity {name:$n}) SET n.description=$d", n=nm, d=ds)
                    ok += 1
            print(f"[{i//BATCH+1}/{-(-len(nodes)//BATCH)}] ✅ {ok}", flush=True)
        except Exception as e:
            print(f"[{i//BATCH+1}] ❌ {e}", flush=True)
        time.sleep(0.3)
    
    remain = s.run(f"MATCH (n:Entity) WHERE n.description IS NULL OR size(toString(n.description)) < {MIN_LEN} RETURN count(n) AS c").single()['c']
    print(f"✅ 完成 {len(nodes)}→{remain}, 更新{ok}", flush=True)

driver.close()
