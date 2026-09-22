#!/usr/bin/env python3
"""
飞书云文档全量扫描器
扫描关键文件夹（制度、咨询组、企业文化等），发现新文件自动下载到 feishu_raw/
"""

import json, hashlib, sys
from pathlib import Path
import urllib.request, urllib.error
import zipfile, xml.etree.ElementTree as ET

# ============ 配置 ============
import subprocess
# 从 feishu_helper.sh 读取凭证（单源管理，避免脚本间复制粘贴）
_helper_path = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "feishu_helper.sh"
def _read_secret() -> tuple:
    with open(_helper_path) as f:
        content = f.read()
    import re
    app_id = re.search(r'APP_ID="(.*?)"', content).group(1)
    app_secret = re.search(r'APP_SECRET="(.*?)"', content).group(1)
    return app_id, app_secret

APP_ID, APP_SECRET = _read_secret()
BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "feishu_raw"
META_DIR = RAW_DIR / "_meta"

# 要跳过的子文件夹名（运营数据、公众号文章等不入知识库）
SKIP_FOLDERS = {"公众号内容"}

# 要扫描的飞书文件夹（名称 → token）
FOLDERS = {
    # 一级文件夹
    "咨询组": {"token": "ENHXfWstPlzHKbdmoL2cUR7hnag", "recursive": True},
    "运营组": {"token": "N8kDfuMkXlHi2FdEjoTcT7Lanfc", "recursive": True},
    "培训组": {"token": "KuRHfkauGlL0rndL5wOcz3kJnCf", "recursive": True},
    
    # 二级文件夹（直接扫整个人事行政根目录，新增子文件夹自动捕获）
    "人事行政": {"token": "Y18ffYVp9ldkqUdaq6TcKPJjnrh", "recursive": True},
    
    # 就业资源
    "岗位信息报告": {"token": "FhmNfRifQlpsZldRXKMcwvKlnCg", "recursive": True},
}

def get_token() -> str:
    """获取飞书 tenant_access_token"""
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=data, headers={"Content-Type": "application/json"}
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    token = resp.get("tenant_access_token", "")
    if not token:
        print(f"❌ 获取 token 失败: {resp.get('msg','')}")
        sys.exit(1)
    return token

def list_folder(token: str, folder_token: str) -> list:
    """列出文件夹内容"""
    url = f"https://open.feishu.cn/open-apis/drive/v1/files?folder_token={folder_token}&page_size=50"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    res = json.loads(urllib.request.urlopen(req).read())
    return res.get("data", {}).get("files", [])

def read_docx_content(token: str, doc_token: str) -> str:
    """读取飞书 docx 文档内容"""
    for endpoint, method in [
        (f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/raw_content", "docx API"),
    ]:
        try:
            req = urllib.request.Request(endpoint, headers={"Authorization": "Bearer " + token})
            res = json.loads(urllib.request.urlopen(req).read())
            return res.get("data", {}).get("content", "")
        except:
            pass
    return ""

def read_file_content(token: str, file_token: str) -> str:
    """下载并解析飞书上传文件（docx）的文本"""
    try:
        url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/download"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        resp = urllib.request.urlopen(req)
        data = resp.read()
        
        # Try to extract text from docx
        texts = []
        try:
            with zipfile.ZipFile(io:=__import__('io').BytesIO(data)) as z:
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
                    if t.text: texts.append(t.text)
                # Try tables too
                for tbl in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl"):
                    rows = tbl.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr")
                    for row in rows:
                        cells = row.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc")
                        row_text = " | ".join(
                            "".join(t.text or "" for t in cell.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
                            for cell in cells
                        )
                        texts.append(row_text)
        except:
            pass
        
        return "\n".join(texts) if texts else f"(二进制文件, {len(data)} bytes)"
    except Exception as e:
        return f"(读取失败: {e})"

def save_file(name: str, content: str):
    """保存文件到 feishu_raw/ 并更新 meta"""
    # 替换文件名中的路径分隔符
    safe_name = name.replace("/", "_").replace("\\", "_")
    file_path = RAW_DIR / f"{safe_name}.txt"
    file_path.write_text(content)
    
    meta = {}
    meta_path = META_DIR / f"{safe_name}.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    
    meta["file_hash"] = hashlib.sha256(content.encode()).hexdigest()
    meta["last_imported"] = __import__('time').strftime("%Y-%m-%dT%H:%M:%S")
    meta["file_size"] = len(content)
    meta["doc_name"] = name
    META_DIR.mkdir(exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

def read_sheet_content(token: str, sheet_token: str) -> str:
    """读取飞书 Sheet (spreadsheet) 内容"""
    import json as _json
    import urllib.request as _ur
    
    try:
        # 获取 sheet 列表
        url = f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{sheet_token}/sheets/query"
        req = _ur.Request(url, headers={"Authorization": "Bearer " + token})
        res = _json.loads(_ur.urlopen(req).read())
        sheets = res.get("data", {}).get("sheets", [])
        
        all_text = []
        for s in sheets:
            sid = s["sheet_id"]
            title = s.get("title", "Sheet")
            all_text.append(f"=== Sheet: {title} ===")
            
            # 读取内容
            url2 = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{sheet_token}/values/{sid}"
            req2 = _ur.Request(url2, headers={"Authorization": "Bearer " + token})
            res2 = _json.loads(_ur.urlopen(req2).read())
            values = res2.get("data", {}).get("valueRange", {}).get("values", [])
            
            for row in values:
                row_text = " | ".join(str(c or "") for c in row)
                if row_text.strip():
                    all_text.append(row_text)
        
        return "\n".join(all_text) if all_text else ""
    except Exception as e:
        return f"(读取Sheet失败: {e})"


def normalize_name(name: str) -> str:
    """规范化文件名（去扩展名、特殊字符）"""
    for ext in [".docx", ".doc", ".pptx", ".xlsx", ".xls"]:
        name = name.replace(ext, "")
    return name.strip()

def scan_folder(token, config, folder_path=""):
    """递归扫描一个文件夹"""
    folder_token = config["token"]
    recursive = config.get("recursive", False)
    
    try:
        files = list_folder(token, folder_token)
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        return []
    
    new_files = []
    for f in files:
        ftype = f["type"]
        fname = f["name"]
        ftoken = f["token"]
        
        if ftype == "folder" and recursive:
            if fname in SKIP_FOLDERS:
                print(f"  ⏭️  [跳过子文件夹] {fname}")
                continue
            sub = scan_folder(token, {"token": ftoken, "recursive": True}, f"{folder_path}/{fname}")
            new_files.extend(sub)
            continue
        
        if ftype not in ("doc", "docx", "file", "sheet"):
            continue
        
        # Determine local name
        local_name = normalize_name(fname)
        if folder_path:
            # Avoid overly long names from path prefix
            pass
        
        # Check if already exists with same content
        local_path = RAW_DIR / f"{local_name}.txt"
        meta_path = META_DIR / f"{local_name}.json"
        
        skip = False
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            # If it was imported recently, skip
            if meta.get("file_hash"):
                skip = True  # Will be checked by sync.py hash comparison
        
        if not skip or not local_path.exists():
            # Read content
            if ftype in ("doc", "docx"):
                content = read_docx_content(token, ftoken)
            elif ftype == "sheet":
                content = read_sheet_content(token, ftoken)
            else:
                content = read_file_content(token, ftoken)
            
            if content and len(content) > 10:
                save_file(local_name, content)
                new_files.append(local_name)
                print(f"  ✅ [新增] {local_name} ({len(content)} chars)")
            else:
                print(f"  ⏭️  [跳过] {fname} (空内容或二进制)")
    
    return new_files

def main():
    print("=" * 50)
    print("📂 飞书云文档全量扫描器")
    print("=" * 50)
    
    os = __import__('os')
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(META_DIR, exist_ok=True)
    
    token = get_token()
    print("✅ Token 获取成功\n")
    
    all_new = []
    for folder_name, config in FOLDERS.items():
        print(f"📁 扫描: {folder_name}")
        new = scan_folder(token, config, f"/{folder_name}")
        all_new.extend(new)
        print()
    
    if all_new:
        print(f"\n📊 本次扫描新增 {len(all_new)} 个文件:")
        for n in all_new:
            print(f"  📄 {n}")
    else:
        print("\n✅ 无新增文件")

    # 提示用户手动清理或后续由 pipeline 自动清理
    txt_count = len(list(RAW_DIR.glob('*.txt'))) if RAW_DIR.exists() else 0
    print(f"\n📊 feishu_raw/ 当前共 {txt_count} 个文件（如需清理请运行: rm -rf {RAW_DIR}）")
    print("下次运行 sync.py 将处理新增/变更文件")

if __name__ == "__main__":
    main()
