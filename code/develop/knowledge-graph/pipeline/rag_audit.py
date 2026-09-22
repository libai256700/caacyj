#!/usr/bin/env python3
"""RAG审计 v2 - 小批次增量续跑"""
import json, os, re, time, urllib.request as ureq

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SCRIPT_DIR, 'config.json')) as cf:
    ARK_KEY = json.load(cf)['models']['doubao']['api_key']

API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = "doubao-seed-2-0-pro-260215"
BATCH_SIZE = 25
PROGRESS_FILE = "/tmp/rag_audit_progress.json"
RESULTS_FILE = "/tmp/rag_audit_results.jsonl"

# 加载实体
entities = json.load(open("/tmp/rag_entities.json"))
print(f"📦 {len(entities)} 个实体")

# 加载已完成的
done_ids = set()
results = []
if os.path.exists(PROGRESS_FILE):
    done_ids = set(json.load(open(PROGRESS_FILE)))
    if os.path.exists(RESULTS_FILE):
        results = [json.loads(l) for l in open(RESULTS_FILE) if l.strip()]
    print(f"📌 续跑: 已完成 {len(done_ids)} 个, 已发现 {len([r for r in results if 'error' not in r.get('problem','')])} 个问题")

# 过滤未完成的
remaining = [e for i, e in enumerate(entities) if str(i) not in done_ids]
print(f"🔄 剩余: {len(remaining)} 个")

# 分批发请求
for bi in range(0, len(remaining), BATCH_SIZE):
    batch = remaining[bi:bi+BATCH_SIZE]
    idxs = [entities.index(e) for e in batch]
    
    entities_text = "\n".join(
        f"{j+1}. [{e['type']}] {e['name']}\n   描述: {(e.get('description') or '（空）')[:200]}"
        for j, e in enumerate(batch)
    )

    prompt = f"""你是无人机知识审计专家。逐条检查以下实体描述质量，输出 JSON 数组（无其他内容）。

检查维度：
- 事实错误：描述与无人机常识/法规不符
- 描述过简：<10字或空洞
- 分类错误：type与内容不匹配
- 矛盾：与常识或其他实体冲突

格式：[{{"idx":序号,"problem":"类型","detail":"问题","suggestion":"建议"}}]
没问题输出 []

实体（{len(batch)}个）：
{entities_text}"""

    print(f"  [{bi//BATCH_SIZE+1}] {len(batch)}个...", end=" ", flush=True)
    
    try:
        body = json.dumps({
            "model": MODEL,
            "messages": [
                {"role":"system","content":"你是无人机知识审计专家。只输出JSON数组。"},
                {"role":"user","content": prompt}
            ],
            "max_tokens": 4096, "temperature": 0.1
        }).encode()
        
        resp = ureq.urlopen(ureq.Request(API_URL, data=body, 
            headers={"Authorization":f"Bearer {ARK_KEY}","Content-Type":"application/json"}), timeout=300)
        raw = json.loads(resp.read())
        content = raw["choices"][0]["message"]["content"].strip()
        
        # 提取 JSON
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        issues = json.loads(content)
        cnt = len(issues)
        
        # 映射 idx 回真实实体名
        for iss in issues:
            idx = int(iss.get("idx", 1)) - 1
            if idx < len(batch):
                results.append({
                    "name": batch[idx]["name"],
                    "type": batch[idx]["type"],
                    "problem": iss.get("problem",""),
                    "detail": iss.get("detail",""),
                    "suggestion": iss.get("suggestion",""),
                    "batch": f"kp_{idxs[idx]}"
                })
        
        print(f"✅ {cnt}个问题")
        time.sleep(1)
        
    except Exception as e:
        print(f"❌ {str(e)[:80]}")
    
    # 增量保存
    for idx in idxs:
        done_ids.add(str(idx))
    json.dump(list(done_ids), open(PROGRESS_FILE, "w"))
    with open(RESULTS_FILE, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ===== 生成报告 =====
print(f"\n📊 审计完成: {len(results)} 个问题 / {len(entities)} 实体")

by_problem = {}
for r in results:
    p = r["problem"]
    by_problem[p] = by_problem.get(p, 0) + 1

report = f"""# RAG 知识库全量审计报告

> 时间: {time.strftime('%Y-%m-%d %H:%M')} | 模型: {MODEL}
> 实体总数: {len(entities)} | 问题: {len(results)} | 问题率: {len(results)/len(entities)*100:.1f}%

## 问题分布

| 类型 | 数量 |
|------|------|
"""
for p, c in sorted(by_problem.items(), key=lambda x: -x[1]):
    report += f"| {p} | {c} |\n"

report += "\n## 问题明细\n\n"
for i, r in enumerate(results):
    report += f"### {i+1}. [{r['problem']}] {r['name']} ({r['type']})\n"
    report += f"- **问题**: {r['detail']}\n- **建议**: {r['suggestion']}\n\n---\n\n"

with open("/tmp/rag_audit_report.md", "w") as f:
    f.write(report)

print(f"📄 报告: /tmp/rag_audit_report.md")
print(f"问题率: {len(results)/len(entities)*100:.1f}%")
for p, c in sorted(by_problem.items(), key=lambda x: -x[1]):
    print(f"  {p}: {c}")
