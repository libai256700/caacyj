#!/usr/bin/env python3
"""RAG知识库覆盖盲区扫描 - 用豆包分析知识库主题覆盖缺口"""
import json, os, urllib.request as ureq

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
cf = json.load(open(os.path.join(SCRIPT_DIR, 'config.json')))
ARK_KEY = cf['models']['doubao']['api_key']

API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = "doubao-seed-2-0-pro-260215"

# 加载所有实体名称（去重）
entities = json.load(open("/tmp/rag_entities.json"))
names = list(set(e['name'] for e in entities))
types = list(set(e['type'] for e in entities))

print(f"📦 {len(names)} 个唯一实体名，类型: {types}")

# 按类型抽取代表性的实体名列表，控制 token
sample_by_type = {}
for e in entities:
    sample_by_type.setdefault(e['type'], [])
    if len(sample_by_type[e['type']]) < 30:
        sample_by_type[e['type']].append(e['name'])

summary = []
for t, ns in sample_by_type.items():
    summary.append(f"{t}({len(ns)}/{sum(1 for e in entities if e['type']==t)}): {', '.join(ns)}")

entities_preview = "\n".join(summary)

prompt = f"""你是CAAC无人机培训知识体系专家。以下是知识库已有的实体名称摘要。

请分析知识库的覆盖盲区：哪些无人机培训/CAAC考试必须掌握的主题在知识库中明显缺失或薄弱？

按以下维度逐一扫描：
1. **法规类**：CAAC核心法规、运行规定、空域管理
2. **飞行原理类**：空气动力学、飞控原理、飞行性能
3. **气象类**：航空气象知识、天气对飞行的影响
4. **操作类**：飞行操作规范、应急处理、检查流程
5. **培训/考试类**：CAAC考试大纲要求的知识点
6. **硬件/系统类**：无人机各子系统
7. **行业应用类**：测绘、巡检、植保、物流等

请以 JSON 格式输出缺失主题列表：
```json
[
  {{"category":"类别","topic":"主题名","importance":"高/中","reason":"为什么重要及当前覆盖情况"}}
]
```
至少列出 15 个盲区，最多 30 个。只输出确实重要且缺失的。

=== 已有实体概览（{len(entities)} 个） ===
{entities_preview}"""

print(f"📤 发送请求 ({len(prompt)} chars)...")

body = json.dumps({
    "model": MODEL,
    "messages": [
        {"role":"system","content":"你是CAAC无人机培训知识体系专家。只输出JSON数组。"},
        {"role":"user","content": prompt}
    ],
    "max_tokens": 4096, "temperature": 0.1
}).encode()

resp = ureq.urlopen(ureq.Request(API_URL, data=body,
    headers={"Authorization":f"Bearer {ARK_KEY}","Content-Type":"application/json"}), timeout=120)
raw = json.loads(resp.read())
content = raw["choices"][0]["message"]["content"].strip()

# 提取 JSON
if "```" in content:
    content = content.split("```")[1]
    if content.startswith("json"):
        content = content[4:]
content = content.strip()

gaps = json.loads(content)
print(f"✅ 发现 {len(gaps)} 个覆盖盲区")

# 写入最终报告附录
with open("/tmp/rag_gaps.json", "w") as f:
    json.dump(gaps, f, ensure_ascii=False, indent=2)

# 附加到报告
with open("/tmp/rag_audit_report.md", "a") as f:
    f.write(f"\n# 覆盖盲区扫描\n\n> 审计模型: {MODEL}\n\n")
    f.write("## 盲区清单\n\n")
    f.write("| 类别 | 主题 | 重要性 | 原因 |\n")
    f.write("|------|------|--------|------|\n")
    for g in gaps:
        f.write(f"| {g['category']} | {g['topic']} | {g['importance']} | {g['reason']} |\n")
    f.write(f"\n共 {len(gaps)} 个覆盖盲区。\n")

print("📄 盲区结果已附加到报告")
