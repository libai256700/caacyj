#!/usr/bin/env python3
"""下载飞书表格到txt"""
import requests, json, csv, io
from pathlib import Path

# 从feishu_helper.sh读取secret
helper = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "feishu_helper.sh"
content = helper.read_text()
import re
app_id = re.search(r'APP_ID="(.*?)"', content).group(1)
app_secret = "EDm0vzQklgoUP8yXiZkQRfkrI4ZpwJMl"

# 获取token
r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": app_id, "app_secret": app_secret}, timeout=10)
r.raise_for_status()
token = r.json()["tenant_access_token"]
h = {"Authorization": f"Bearer {token}"}

# 客资表
sheet_token = "GMjVsoXo5hJVVztnfqBc6tpznIT"
r2 = requests.get(f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{sheet_token}/values/Sheet1", headers=h, timeout=15)
if r2.status_code != 200:
    print(f"❌ 下载失败: {r2.text[:200]}")
    exit(1)

data = r2.json()
rows = data.get("data", {}).get("valueRange", {}).get("values", [])
print(f"✅ 客资表: {len(rows)} 行")

# 转为CSV格式文本
output = "客资登记表\n"
for row in rows:
    output += " | ".join(str(cell) for cell in row) + "\n"

out_path = Path(__file__).parent.parent / "feishu_raw" / "客资表.txt"
out_path.write_text(output, encoding="utf-8")
print(f"✅ 已保存: {out_path}")
print(f"预览:")
for line in output.split("\n")[:5]:
    print(f"  {line}")
