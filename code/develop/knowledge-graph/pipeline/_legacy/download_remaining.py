#!/usr/bin/env python3
"""下载剩下的3个表格"""
import requests, json, re

# 从feishu_helper.sh读取secret
helper_path = "/Users/xiaoji/.openclaw/workspace/tools/feishu_helper.sh"
with open(helper_path) as f:
    content = f.read()
app_id = re.search(r'APP_ID="(.*?)"', content).group(1)
app_secret = re.search(r'APP_SECRET="(.*?)"', content).group(1)
print(f"App: {app_id[:8]}... Secret: {app_secret[:8]}...")
r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id":"cli_a9671c9b1b78dbd9","app_secret":app_secret}, timeout=10)
r.raise_for_status()
token = r.json()["tenant_access_token"]
h = {"Authorization": f"Bearer {token}"}

base = "/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/feishu_raw"

files = [
    ("官号播放量统计", "FVpysU4XRhJyyEt6eUMcCENmn8b"),
    ("小号播放量统计", "Vi20s7247hY80Gt5fYmcrCfAn29"),
    ("运营日常工作记录表", "CT7UsMEFGhAAQotd0TncEjGcnTd"),
]

for name, t in files:
    # 查sheet列表 -> 获取sheet_id
    r2 = requests.get(f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{t}/sheets/query", headers=h, timeout=10)
    if r2.status_code != 200:
        print(f"❌ {name}: 查询失败 {r2.status_code}")
        continue
    sheets = r2.json()["data"]["sheets"]
    sheet_id = sheets[0]["sheet_id"]
    
    # 读数据
    r3 = requests.get(f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{t}/values/{sheet_id}", headers=h, timeout=15)
    if r3.status_code != 200:
        print(f"❌ {name}: 读取失败 {r3.status_code}")
        continue
    values = r3.json()["data"]["valueRange"]["values"]
    
    text = f"{name}\n"
    for v in values:
        text += " | ".join(str(c) for c in v) + "\n"
    
    path = f"{base}/{name}.txt"
    with open(path, "w") as f:
        f.write(text)
    print(f"✅ {name}: {len(values)} 行 → {path}")
