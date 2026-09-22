#!/usr/bin/env python3
"""
每日招聘岗位爬虫 - 无人机/CAAC岗位采集
按配置爬取招聘平台和关键词，输出报告并上传到飞书云空间
输出报告并上传到飞书云空间

依赖: agent-browser CLI (通过 subprocess 调用), Python 标准库
"""

import subprocess
import json
import re
import os
import shutil
import sys
import time
import datetime
import hashlib
import html as html_lib
import statistics
import tempfile
import unicodedata
import urllib.parse

os.umask(0o077)

# ============================================================
# 配置区
# ============================================================

CONFIG_PATH = os.path.expanduser(
    os.environ.get(
        "RECRUITMENT_CRAWLER_CONFIG",
        "~/.openclaw/workspace/projects/recruitment-crawler/config.json",
    )
)

DEFAULT_CONFIG = {
    "agent_browser": "~/.npm-global/bin/agent-browser",
    "agent_browser_fallbacks": [
        "~/.npm-packages/bin/agent-browser",
        "~/.local/bin/agent-browser",
    ],
    "report_dir": "~/.openclaw/workspace/reports",
    "snapshot_dir": "~/.openclaw/workspace/reports/job_crawler_snapshots",
    "folder_token": "",
    "chat_id": "",
    "lark_cli": "lark-cli",
    "keywords": ["无人机飞手", "CAAC", "低空经济", "eVTOL", "无人机教员"],
    "platforms": ["猎聘", "前程无忧", "国聘", "智联招聘"],
    # 智联城市码：空串=全国搜索；"736"=武汉站（与其他平台全国口径不一致，历史遗留）
    "zhaopin_city_code": "",
    "duplicate_retention_days": 30,
    "snapshot_retention_days": 30,
    "repeated_detail_limit": 80,
    "volume_drop_ratio": 0.5,
    "pagination_pause_seconds": 1.5,
    "max_pages_per_query": {
        "猎聘": 5,
        "前程无忧": 5,
        "国聘": 3,
        "智联招聘": 5,
    },
    "result_caps": {
        "猎聘": 40,
        "前程无忧": 20,
        "国聘": 20,
        "智联招聘": 20,
    },
    "quality_thresholds": {
        "min_url_match_rate": 0.75,
        "min_actionable_url_rate": 0.75,
        "max_missing_company_rate": 0.45,
        "max_missing_salary_rate": 0.55,
        "max_missing_location_rate": 0.35,
        "max_missing_url_rate": 0.25,
        "max_invalid_location_rate": 0.0,
        "max_invalid_salary_rate": 0.0,
        "platforms": {
            "智联招聘": {
                "max_missing_company_rate": 0.15,
                "critical_missing_company_rate": 0.25,
            },
        },
    },
    "staff": [],
}


def deep_merge(base, override):
    """递归合并配置，保持缺省字段向后兼容。"""
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def expand_path(value):
    return os.path.expanduser(os.path.expandvars(value))


def ensure_private_directory(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def load_config():
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("配置顶层必须是对象")
            config = deep_merge(DEFAULT_CONFIG, loaded)
            print(f"  [CONFIG] 使用配置: {CONFIG_PATH}")
        except Exception as e:
            raise RuntimeError(
                f"配置读取失败，已拒绝回退默认值: {CONFIG_PATH} ({type(e).__name__})"
            ) from e
    else:
        print(f"  [CONFIG] 未找到配置，使用内置默认值: {CONFIG_PATH}")
    return config


CONFIG = load_config()

# agent-browser 路径
AGENT_BROWSER = expand_path(CONFIG["agent_browser"])

# 启动时校验 agent-browser 存在性
if not os.path.isfile(AGENT_BROWSER):
    print(f"⚠️ agent-browser 未找到: {AGENT_BROWSER}", file=sys.stderr)
    # 尝试常见备用路径
    fallback_paths = [expand_path(p) for p in CONFIG.get("agent_browser_fallbacks", [])]
    for fp in fallback_paths:
        if os.path.isfile(fp):
            print(f"  → 使用备用路径: {fp}")
            AGENT_BROWSER = fp
            break
    else:
        path_candidate = shutil.which("agent-browser")
        if path_candidate:
            print(f"  → 使用 PATH 中的 agent-browser: {path_candidate}")
            AGENT_BROWSER = path_candidate
        else:
            print(f"  ❌ 无可用的 agent-browser，爬虫将无法运行", file=sys.stderr)

# 报告目录
REPORT_DIR = expand_path(CONFIG["report_dir"])
ensure_private_directory(REPORT_DIR)
SNAPSHOT_DIR = expand_path(CONFIG.get("snapshot_dir", os.path.join(REPORT_DIR, "job_crawler_snapshots")))
ensure_private_directory(SNAPSHOT_DIR)

# 飞书云空间文件夹 token（目标上传目录）
FOLDER_TOKEN = CONFIG["folder_token"]

# 飞书人事行政群 chat_id
CHAT_ID = CONFIG["chat_id"]

# 员工权限列表
STAFF_CONFIG = CONFIG.get("staff", [])
ALL_STAFF = [
    tuple(str(value).strip() for value in item[:3])
    for item in STAFF_CONFIG
    if isinstance(item, (list, tuple)) and len(item) >= 3
]
STAFF_NAME_MAP = {
    str(item[1]).strip(): str(item[3]).strip()
    for item in STAFF_CONFIG
    if isinstance(item, (list, tuple)) and len(item) >= 4
}
STAFF_MEMBER_TYPES = {"email", "openid", "unionid", "userid"}
STAFF_PERMISSIONS = {"view", "edit", "full_access"}

LARK_CLI = CONFIG["lark_cli"]

# 关键词
KEYWORDS = CONFIG["keywords"]
ENABLED_PLATFORMS = set(CONFIG.get("platforms") or [])
QUALITY_THRESHOLDS = CONFIG.get("quality_thresholds", {})
RESULT_CAPS = CONFIG.get("result_caps", {"猎聘": 40, "智联招聘": 20})
MAX_FAILED_COMBINATION_RATE = float(CONFIG.get("max_failed_combination_rate", 0.20))
REPEATED_DETAIL_LIMIT = int(CONFIG.get("repeated_detail_limit", 80) or 0)
VOLUME_DROP_RATIO = float(CONFIG.get("volume_drop_ratio", 0.50))
PAGINATION_PAUSE_SECONDS = float(CONFIG.get("pagination_pause_seconds", 1.5) or 0)
QUALITY_EVENTS = []
# 回放模式下禁止写新快照，避免离线分析污染快照目录
SNAPSHOT_DISABLED = False


def configured_platform_names():
    return [name for name, _ in PLATFORM_CRAWLERS]


def validate_runtime_config(require_feishu=True):
    missing = []
    invalid = []
    if not KEYWORDS:
        missing.append("keywords")
    if not PLATFORM_CRAWLERS:
        missing.append("platforms")
    if require_feishu:
        if not FOLDER_TOKEN:
            missing.append("folder_token")
        if not CHAT_ID:
            missing.append("chat_id")
        if not isinstance(STAFF_CONFIG, list) or not STAFF_CONFIG:
            missing.append("staff")
        else:
            valid_staff = []
            for index, item in enumerate(STAFF_CONFIG):
                if not isinstance(item, (list, tuple)) or len(item) != 4:
                    invalid.append(f"staff[{index}] 必须是四元组")
                    continue
                member_type, member_id, perm, display_name = item
                values = (member_type, member_id, perm, display_name)
                if not all(isinstance(value, str) and value.strip() for value in values):
                    invalid.append(f"staff[{index}] 各字段必须是非空字符串")
                    continue
                if member_type.strip() not in STAFF_MEMBER_TYPES:
                    invalid.append(f"staff[{index}] member_type 不受支持")
                    continue
                if perm.strip() not in STAFF_PERMISSIONS:
                    invalid.append(f"staff[{index}] perm 不受支持")
                    continue
                valid_staff.append(item)
            if valid_staff and not any(
                str(item[0]).strip() == "openid" and str(item[2]).strip() == "full_access"
                for item in valid_staff
            ):
                invalid.append("staff 至少需要一名 openid 类型的 full_access 成员")
        if not isinstance(LARK_CLI, str) or not LARK_CLI.strip():
            invalid.append("lark_cli 必须是非空字符串")
        elif not shutil.which(expand_path(LARK_CLI.strip())):
            invalid.append("lark_cli 不可执行或不在 PATH 中")
    if missing:
        raise ValueError(f"配置缺少必要字段: {', '.join(missing)} (config: {CONFIG_PATH})")
    if invalid:
        raise ValueError(f"staff 配置无效: {'; '.join(invalid)} (config: {CONFIG_PATH})")


def record_quality_event(platform, keyword, metric, value, threshold=None, detail=""):
    event = {
        "platform": platform,
        "keyword": keyword,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "detail": detail,
    }
    QUALITY_EVENTS.append(event)


def save_html_snapshot(platform, keyword, html, reason, dedupe_days=3):
    if not html or SNAPSHOT_DISABLED:
        return ""
    safe_platform = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", platform)[:30]
    safe_keyword = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", keyword)[:30]
    # 同一 平台/关键词/症状 近 dedupe_days 天已有快照则不再重复保存，防告警疲劳期快照堆积
    if dedupe_days:
        cutoff = (datetime.date.today() - datetime.timedelta(days=dedupe_days)).isoformat()
        try:
            for existing in os.listdir(SNAPSHOT_DIR):
                p = existing.split("_")
                if len(p) >= 4 and p[0] >= cutoff and p[1] == safe_platform and p[2] == safe_keyword and reason in existing:
                    print(f"  [SNAPSHOT] {dedupe_days}天内已有同症状快照({existing})，跳过保存")
                    return ""
        except OSError:
            pass
    digest = hashlib.sha1(html.encode("utf-8", errors="ignore")).hexdigest()[:10]
    filename = f"{datetime.date.today().isoformat()}_{safe_platform}_{safe_keyword}_{reason}_{digest}.html"
    path = os.path.join(SNAPSHOT_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  [SNAPSHOT] 已保存页面快照: {path}")
        return path
    except Exception as e:
        print(f"  [WARN] 保存页面快照失败: {e}")
        return ""

def purge_old_snapshots():
    """按 snapshot_retention_days 清理过期快照（文件名以 YYYY-MM-DD_ 开头）。"""
    retention = int(CONFIG.get("snapshot_retention_days", 30) or 0)
    if retention <= 0:
        return
    cutoff = (datetime.date.today() - datetime.timedelta(days=retention)).isoformat()
    removed = 0
    try:
        for name in os.listdir(SNAPSHOT_DIR):
            if not name.endswith(".html"):
                continue
            date_part = name.split("_", 1)[0]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part) and date_part < cutoff:
                try:
                    os.remove(os.path.join(SNAPSHOT_DIR, name))
                    removed += 1
                except OSError:
                    pass
    except OSError:
        return
    if removed:
        print(f"  [SNAPSHOT] 已清理 {removed} 个超过{retention}天的过期快照")


# ============================================================
# 标题/公司归一化工具
# ============================================================

# "驾驶员"必须与无人机语境共现才算相关（否则货车/叉车/网约车驾驶员全部混入）
_DRIVER_CONTEXT = ("无人机", "飞行", "航空", "植保", "测绘", "巡检", "机长", "航拍")
# eVTOL/低空经济检索回来的行业岗位，标题常不含字面关键词，用行业词表兜住
_INDUSTRY_TERMS = {
    "evtol": ("evtol", "垂直起降", "飞行汽车", "飞行器", "航空器", "旋翼", "复合翼", "适航", "低空", "飞控"),
    "低空经济": ("低空", "evtol", "垂直起降", "飞行器", "航空器", "适航", "飞行汽车", "飞控"),
}
_CORE_RELEVANCE_TERMS = ("无人机", "飞手", "caac", "evtol", "无人驾驶航空器")
_INDUSTRY_RELEVANCE_TERMS = (
    "低空", "垂直起降", "飞行汽车", "飞行器", "航空器", "旋翼", "复合翼", "适航", "飞控",
)
_WEAK_RELEVANCE_TERMS = ("航空",)
RELEVANCE_ORDER = {"core": 0, "industry": 1, "weak": 2, "irrelevant": 3}


def classify_relevance(title, keyword=""):
    """返回 core/industry/weak/irrelevant 及命中理由。"""
    if not title:
        return "irrelevant", "empty_title"
    lower = title.lower()
    if any(term in lower for term in _CORE_RELEVANCE_TERMS):
        return "core", "core_title_term"
    if "驾驶员" in lower and any(ctx in lower for ctx in _DRIVER_CONTEXT):
        return "core", "aviation_driver_context"
    if any(term in lower for term in _INDUSTRY_RELEVANCE_TERMS):
        return "industry", "low_altitude_industry_term"
    for term in _INDUSTRY_TERMS.get((keyword or "").lower(), ()):
        if term in lower:
            return "industry", "query_industry_term"
    if any(term in lower for term in _WEAK_RELEVANCE_TERMS):
        return "weak", "broad_aviation_term"
    return "irrelevant", "no_relevance_evidence"


def is_relevant_job_title(title, keyword=""):
    """核心岗直接入选；普通产业/弱相关岗仅供宽口径行业检索。"""
    tier, _ = classify_relevance(title, keyword)
    if tier in {"industry", "weak"}:
        return (keyword or "").lower() in {"evtol", "低空经济"}
    return tier == "core"


def classify_job_relevance(job):
    keywords = job.get("keywords") or [job.get("keyword", "")]
    candidates = [classify_relevance(job.get("title", ""), keyword) for keyword in keywords]
    return min(candidates, key=lambda item: RELEVANCE_ORDER[item[0]])


def normalize_title(title):
    """归一化岗位标题：删除招聘修饰，保留固定翼/多旋翼等语义括注。"""
    t = title or ''
    promotion_terms = (
        '急聘', '诚聘', '高薪', '双休', '五险', '公积金', '包住', '包吃',
        '住宿', '食宿', '朝九晚五', '不加班', '社保', '带薪',
    )

    def normalize_bracket(match):
        content = (match.group(1) or "").strip()
        return "" if any(term in content for term in promotion_terms) else content

    for pattern in (r'（(.*?)）', r'\((.*?)\)', r'【(.*?)】', r'\[(.*?)\]'):
        t = re.sub(pattern, normalize_bracket, t)

    modifiers = [
        '急聘', '诚聘', '高薪', '双休', '五险一金', '包住', '包吃',
        '提供住宿', '提供食宿', '朝九晚五', '不加班',
        '社保', '五险', '公积金', '带薪',
    ]
    for m in modifiers:
        t = re.sub(m, '', t)
    # 去掉多余空格和标点
    t = re.sub(r'[\s+|\-\/·•★☆▲▼]', '', t).strip().lower()[:40]
    return t


def clean_company_name(company):
    """归一化公司名：去掉公司后缀"""
    c = company or ''
    suffixes = ['股份有限公司', '有限责任公司', '有限公司', '股份公司', '集团', '股份', '有限']
    for s in suffixes:
        c = c.replace(s, '')
    return re.sub(r'[\s|｜·•]', '', c).strip().lower()[:25]


def canonical_platforms(job):
    platforms = job.get("platforms")
    if isinstance(platforms, list) and platforms:
        return [p for p in platforms if p]
    platform = job.get("platform", "")
    if "/" in platform:
        return [p for p in platform.split("/") if p]
    return [platform] if platform else []


PUBLISH_HOST_SUFFIXES = {
    "猎聘": ("liepin.com",),
    "前程无忧": ("51job.com",),
    "国聘": ("iguopin.com",),
    "智联招聘": ("zhaopin.com",),
}


def clean_external_text(value):
    """规整外部页面字段：换行折叠为空格，移除其他 Unicode 控制字符。"""
    cleaned = []
    for char in str(value or ""):
        if char in "\r\n\t":
            cleaned.append(" ")
        elif not unicodedata.category(char).startswith("C"):
            cleaned.append(char)
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def escape_markdown_text(value):
    """转义不可信字段，避免岗位内容注入标题、链接或图片。"""
    text = clean_external_text(value).replace("\\", "\\\\")
    for marker in "`*_{}[]()<>#!|":
        text = text.replace(marker, f"\\{marker}")
    return text


def allowed_publish_url(value, platforms):
    """只允许当前岗位来源平台的 HTTP(S) 链接进入对外报告。"""
    raw = str(value or "").strip()
    if not raw or clean_external_text(raw) != raw or re.search(r'[\s<>"\\]', raw):
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 80, 443}
    ):
        return ""
    allowed_suffixes = {
        suffix
        for platform in platforms
        for suffix in PUBLISH_HOST_SUFFIXES.get(platform, ())
    }
    hostname = parsed.hostname.lower().rstrip(".")
    if not any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed_suffixes):
        return ""
    safe_path = parsed.path.replace("(", "%28").replace(")", "%29")
    safe_query = parsed.query.replace("(", "%28").replace(")", "%29")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, safe_path, safe_query, ""))


def extract_stable_job_id(url):
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    host = re.sub(r"^www\.", "", parsed.netloc.lower())
    path = parsed.path
    candidates = [
        r'/jobdetail/([^/?#]+)',
        r'/job/([^/?#]+)',
        r'/a/([^/?#]+)',
        r'/([^/?#]+)\.html',
    ]
    for pattern in candidates:
        m = re.search(pattern, path)
        if m:
            return f"{host}:{m.group(1)}"
    return ""


def normalize_location_city(location):
    """地点归一到城市级："武汉-洪山区"→"武汉"。跨平台地点粒度不一致时保证同岗同键。"""
    loc = re.sub(r"[\s|｜•]", "", location or "").replace("·", "-").lower()[:20]
    return re.split(r"[-–—]", loc)[0]


def make_job_signature(job, prefer_url=True):
    """生成岗位签名：优先稳定岗位链接（host:id，不含平台集合——平台集合随合并关系
    日间波动会把同岗误判新增），其次公司+标题+城市级地点。"""
    url_id = extract_stable_job_id(job.get("url", ""))
    norm_t = normalize_title(job.get("title", ""))
    norm_c = clean_company_name(job.get("company", ""))
    raw_location = str(job.get("location") or "").strip()
    raw_salary = str(job.get("salary") or "").strip()
    city = normalize_location_city(raw_location) if is_valid_location(raw_location) else ""
    salary = re.sub(r"\s+", "", raw_salary).lower() if is_valid_salary(raw_salary) else ""
    if prefer_url and url_id:
        return f"url|{url_id}"
    if norm_c and norm_t and city:
        return f"text|{norm_c}|{norm_t}|{city}"
    if norm_t and (city or salary):
        platforms = "+".join(sorted(set(canonical_platforms(job)))) or "未知平台"
        return f"nc|{platforms}|{norm_t}|{city}|{salary}"
    if url_id:
        return f"url|{url_id}"
    return ""


# ============================================================
# Agent-Browser 封装
# ============================================================

def run_browser(args, timeout=30, session_name="zhaopin"):
    """运行 agent-browser 命令，返回 (stdout, stderr, returncode)"""
    # 使用 session_name 持久化登录态，避免每次触发 EdgeOne 验证
    if session_name:
        cmd = [AGENT_BROWSER, "--session-name", session_name] + args
    else:
        cmd = [AGENT_BROWSER] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "ERROR: Timeout expired", -1
    except FileNotFoundError:
        return "", f"ERROR: agent-browser not found at {AGENT_BROWSER}", -1


def browser_open(url, timeout=15):
    """打开页面并等待加载（有头模式，可见浏览器窗口）"""
    stdout, stderr, rc = run_browser(["open", url, "--headed"], timeout=timeout)
    if rc != 0:
        print(f"  [WARN] open failed: {stderr[:200]}", file=sys.stderr)
        return False
    # 等待页面稳定（不用 networkidle 避免某些页面永不完成）
    run_browser(["wait", "3000"], timeout=8)
    return True


def browser_get_text(timeout=10):
    """获取页面body文本"""
    stdout, stderr, rc = run_browser(["get", "text", "body", "--json"], timeout=timeout)
    if rc != 0:
        return ""
    try:
        data = json.loads(stdout)
        if data.get("success") and data.get("data"):
            # data["data"] 是一个 dict: {"origin": "...", "text": "..."}
            inner = data["data"]
            if isinstance(inner, dict):
                return inner.get("text", "")
            return str(inner)
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def browser_get_html(timeout=10):
    """获取页面body HTML"""
    stdout, stderr, rc = run_browser(["get", "html", "body", "--json"], timeout=timeout)
    if rc != 0:
        return ""
    try:
        data = json.loads(stdout)
        if data.get("success") and data.get("data"):
            inner = data["data"]
            if isinstance(inner, dict):
                return inner.get("html", "")
            return str(inner)
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def browser_get_links(timeout=10):
    """从页面 HTML 中提取所有链接"""
    html = browser_get_html(timeout=timeout)
    if not html:
        return {}
    # 提取 <a href="...">text</a>
    links = {}
    for m in re.finditer(r'<a[^>]*?href=["\'](https?://[^"\']+)["\'][^>]*>\s*([^<]{2,80}?)\s*</a>', html, re.IGNORECASE):
        url = m.group(1)
        text = m.group(2).strip()
        # 去重：短文本优先
        if text and len(text) > 1:
            normalized = re.sub(r'\s+', '', text)[:30]
            if normalized not in links or len(text) < len(links[normalized][1]):
                links[normalized] = (url, text)
    # 再提取纯 href 但可能没文本的链接
    for m in re.finditer(r'<a[^>]*?href=["\'](https?://[^"\']+)["\'][^>]*?>\s*</a>', html, re.IGNORECASE):
        url = m.group(1)
        # 用 URL 的一部分当 key
        key = url.split("/")[-1][:30]
        if key not in links:
            links[key] = (url, "")
    return links


def match_job_url(jobs, page_links):
    """将解析出的岗位与页面链接进行匹配"""
    for job in jobs:
        if job.get("url"):
            continue  # 已有链接则不覆盖
        title = job.get("title", "")
        if not title:
            continue
        # 标准化标题用于匹配
        title_norm = re.sub(r'\s+', '', title)[:30]
        # 精确匹配
        if title_norm in page_links:
            job["url"] = page_links[title_norm][0]
            continue
        # 子串匹配：标题包含在链接文本中
        for norm_key, (url, link_text) in page_links.items():
            if len(title_norm) > 4 and title_norm in norm_key:
                job["url"] = url
                break
            # 链接文本包含标题关键词
            if len(link_text) > 3 and any(kw in link_text for kw in title_norm.split(" ") if len(kw) > 2):
                job["url"] = url
                break
    return jobs


def extract_job_urls_from_html(html, platform):
    """从HTML中提取各平台的岗位详情链接"""
    if not html:
        return []

    patterns = {
        "猎聘": r'href=["\'](https?://(?:www\.)?liepin\.com/(?:job|a)/[^"\']+)["\']',
        "前程无忧": r'href=["\'](https?://jobs\.51job\.com/[^"\']+/\d+\.html[^"\']*?)["\']',
        "国聘": r'href=["\'](https?://(?:www\.)?iguopin\.com/(?!job(?:\s|$|\?))(?!app)[^"\']+)["\']',
    }

    pattern = patterns.get(platform)
    if not pattern:
        return []

    urls = re.findall(pattern, html, re.IGNORECASE)
    # 去重
    seen = set()
    unique = []
    for u in urls:
        clean = u.split("#")[0]
        # 51job 搜索页侧栏会插入首页推荐岗位链接（s=pchome_*），与搜索结果无关，
        # 按位置匹配时会把错误链接挂到岗位上，必须剔除
        if "pchome" in clean:
            continue
        if clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return unique


def attach_job_urls(jobs, html, platform, search_url="", keyword=""):
    """为岗位列表匹配对应的URL（按位置匹配）"""
    if not jobs or not html:
        return jobs

    # 从HTML提取该平台的所有岗位链接
    urls = extract_job_urls_from_html(html, platform)
    if not urls:
        # 无URL时，用搜索页链接作为兜底
        if search_url:
            for job in jobs:
                if not job.get("url"):
                    job["url"] = search_url
            print(f"  [URL] {platform}: 无岗位链接，使用搜索页URL兜底")
            record_quality_event(platform, keyword, "url_match_rate", 0, QUALITY_THRESHOLDS.get("min_url_match_rate"), "无岗位详情链接，已使用搜索页兜底")
            save_html_snapshot(platform, keyword, html, "no_job_url")
        return jobs

    # 位置匹配只在"岗位数==链接数"时可信：解析器过滤过卡片或页面混入杂链时
    # 两个序列不再一一对应，按位置硬挂必然错位（历史上国聘 3岗配8链接打✅就是实证）
    pending = [job for job in jobs if not job.get("url")]
    if pending and len(urls) == len(jobs):
        for i, job in enumerate(jobs):
            if not job.get("url"):
                job["url"] = urls[i]
        print(f"  [URL] {platform}: 位置匹配 {len(jobs)}/{len(jobs)} 个（岗位数与链接数一致）✅")
    elif pending:
        for job in pending:
            if search_url:
                job["url"] = search_url
        record_quality_event(
            platform,
            keyword,
            "url_position_mismatch",
            f"{len(jobs)}岗/{len(urls)}链",
            None,
            "岗位数与链接数不一致，放弃位置匹配改用搜索页兜底（防错位挂链）",
        )
        save_html_snapshot(platform, keyword, html, "url_position_mismatch")
        print(f"  [URL] {platform}: 岗位{len(jobs)}个 vs 链接{len(urls)}个不一致，已用搜索页兜底 ⚠️")
    return jobs


def browser_close():
    """关闭浏览器页面"""
    run_browser(["close"], timeout=5)


class CrawlFetchError(RuntimeError):
    """页面未被可信获取，不能按正常空结果处理。"""


class CrawlBlockedError(CrawlFetchError):
    """页面被安全验证或反爬拦截。"""


class PublishError(RuntimeError):
    """日报未完成端到端发布。"""


class HistoryStoreError(RuntimeError):
    """发布历史无法可信读写。"""


class SignatureStoreError(RuntimeError):
    """岗位签名主库和备份均无法可信使用。"""


BROWSER_SECURITY_MARKERS = (
    "验证连接安全性",
    "Security Verification",
    "Checking your browser",
    "Just a moment",
    "请完成安全验证",
    "请完成验证",
)

BROWSER_TRANSPORT_ERROR_MARKERS = (
    "This site can't be reached",
    "无法访问此网站",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_",
    "ERR_TIMED_OUT",
    "ERR_INTERNET_DISCONNECTED",
)


def detect_security_marker(content, markers=None):
    """返回命中的安全验证标记；空字符串表示未命中。"""
    active_markers = BROWSER_SECURITY_MARKERS if markers is None else tuple(markers)
    content_folded = (content or "").casefold()
    marker = next((marker for marker in active_markers if marker.casefold() in content_folded), "")
    if marker:
        return marker
    # CDN/厂商名本身可能出现在正常页面资源中，只有与挑战语义共现才判拦截。
    if "cloudflare" in content_folded and any(
        phrase in content_folded for phrase in ("attention required", "ray id", "checking your browser")
    ):
        return "Cloudflare challenge"
    if "edgeone" in content_folded and any(
        phrase in content_folded for phrase in ("security verification", "安全验证", "连接安全性")
    ):
        return "EdgeOne challenge"
    return ""


def detect_transport_error_marker(content):
    """返回浏览器内置网络错误页标记；空字符串表示未命中。"""
    content_folded = (content or "").casefold()
    return next(
        (marker for marker in BROWSER_TRANSPORT_ERROR_MARKERS if marker.casefold() in content_folded),
        "",
    )


def _validate_browser_content(content, url, security_detect=None):
    marker = detect_security_marker(content, security_detect)
    if marker:
        raise CrawlBlockedError(f"页面被安全验证拦截({marker}): {url}")
    transport_marker = detect_transport_error_marker(content)
    if transport_marker:
        raise CrawlFetchError(f"浏览器网络错误页({transport_marker}): {url}")


def read_open_browser_page(url, wait_ms=5000, security_detect=None):
    """Read and validate the page currently open in the shared browser session."""
    run_browser(["wait", "2000"], timeout=5)
    text = browser_get_text(timeout=8)
    _validate_browser_content(text, url, security_detect)

    if wait_ms:
        run_browser(["wait", str(wait_ms)], timeout=10)
    text = browser_get_text(timeout=10)
    _validate_browser_content(text, url, security_detect)
    links = browser_get_links(timeout=8)
    html = browser_get_html(timeout=8)
    _validate_browser_content(html, url, security_detect)
    if not (text or "").strip() and not (html or "").strip():
        raise CrawlFetchError(f"页面正文和HTML均为空: {url}")
    return text, links, html


def safe_browser_task(url, wait_ms=5000, timeout=30, security_detect=None, close_browser=True):
    """
    安全打开页面并获取文本、链接和HTML。
    security_detect: 自定义反爬页面文本片段；None 使用默认标记，空列表表示不检测。
    成功返回 (text, links_dict, html)；页面打开、反爬或空响应均抛 CrawlFetchError。
    """
    try:
        if not browser_open(url, timeout=timeout):
            raise CrawlFetchError(f"页面打开失败: {url}")

        return read_open_browser_page(url, wait_ms=wait_ms, security_detect=security_detect)
    except CrawlFetchError:
        raise
    except Exception as e:
        raise CrawlFetchError(f"浏览器任务异常({type(e).__name__}): {url}: {e}") from e
    finally:
        if close_browser:
            try:
                browser_close()
            except Exception:
                pass


# ============================================================
# 各平台搜索配置与解析器
# ============================================================

def parse_liepin(text, keyword):
    """
    解析猎聘搜索结果。
    从实际测试看，格式为：
      Line i  : 职位名称
      Line i+1: 【
      Line i+2: 地点
      Line i+3: 】
      Line i+4: 薪资
      Line i+5: 经验
      Line i+6: 学历
      Line i+7: 公司名
      ...
    """
    jobs = []
    if not text:
        return jobs

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if is_relevant_job_title(line, keyword) and len(line) < 50 and len(line) > 2:
            title = line.strip()
            location = ""
            salary = ""
            company = ""

            # 向前扫描最多 10 行
            for j in range(1, min(11, len(lines) - i)):
                nxt = lines[i + j].strip()
                if not nxt:
                    continue

                # 处理多行括号 【  】
                if nxt == "【":
                    # 下一行是地点
                    if i + j + 1 < len(lines):
                        loc_line = lines[i + j + 1].strip()
                        if loc_line and "】" not in loc_line:
                            location = loc_line
                    continue

                if not salary:
                    sal_m = re.search(r'(\d[\d\.]*\s*[-~至]\s*\d[\d\.]*\s*[kK万]|\d[\d\.]*\s*[kK]|\d{4,6}[-~]\d{4,6})', nxt)
                    if sal_m:
                        salary = sal_m.group(1)
                        continue

                if not company and ("公司" in nxt or "科技" in nxt or "有限" in nxt or "集团" in nxt or "企业" in nxt):
                    if len(nxt) > 3 and len(nxt) < 40:
                        company = nxt[:40]
                        continue

            # 只要有薪资、地点或公司之一就记录
            if salary or location or company:
                jobs.append({
                    "platform": "猎聘",
                    "title": title,
                    "company": company,
                    "salary": salary,
                    "location": location,
                    "url": "",
                    "keyword": keyword,
                })
            elif len(title) > 2:
                # 至少匹配上关键词
                jobs.append({
                    "platform": "猎聘",
                    "title": title,
                    "company": "",
                    "salary": "",
                    "location": "",
                    "url": "",
                    "keyword": keyword,
                })
        i += 1

    return jobs


def parse_51job(text, keyword):
    """
    解析前程无忧搜索结果。
    实际格式：
      职位名称
      薪资
      地点
      ... (tags)
      公司名
      公司信息
    """
    jobs = []
    if not text:
        return jobs

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if is_relevant_job_title(line, keyword) and len(line) < 60:
            title = line.strip()
            location = ""
            salary = ""
            company = ""

            look_ahead = []
            for j in range(1, min(12, len(lines) - i)):
                nxt = lines[i + j].strip()
                if not nxt:
                    continue
                look_ahead.append(nxt)

            for la in look_ahead:
                # 薪资: 5-8千, 6-10万/年, 6千-1.2万, 4-6千·13薪
                sal_m = re.search(
                    r'(\d[\d\.]*\s*[-~至]\s*\d[\d\.]*\s*(千|万|k|K)(/\w+)?'
                    r'|\d[\d\.]*\s*千\s*[-~至]\s*\d[\d\.]*\s*万'
                    r'|\d[\d\.]*\s*[kK]'
                    r'|面议)',
                    la
                )
                if sal_m and not salary:
                    salary = sal_m.group(0).strip()
                    continue
                # 地点
                cities = r'(武汉|北京|上海|广州|深圳|成都|杭州|南京|西安|重庆|长沙|郑州|合肥|苏州|东莞|天津|宁波|青岛|厦门|大连|雄安|三亚|信阳|随州|昌江)'
                loc_m = re.search(cities, la)
                if loc_m and not location:
                    location = loc_m.group(1)
                    # 检查是否有详细的地区
                    detail_m = re.search(rf'{loc_m.group(1)}[·\-]([^\s]{{2,6}})', la)
                    if detail_m:
                        location = f"{loc_m.group(1)}-{detail_m.group(1)}"
                    continue
                # 公司名（不含薪资模式）
                if not company and ("公司" in la or "科技" in la or "有限" in la or "集团" in la):
                    company = la[:40]
                    continue

            if salary or location:
                jobs.append({
                    "platform": "前程无忧",
                    "title": title,
                    "company": company,
                    "salary": salary,
                    "location": location,
                    "url": "",
                    "keyword": keyword,
                })
            elif any(k.lower() in title.lower() for k in KEYWORDS):
                jobs.append({
                    "platform": "前程无忧",
                    "title": title,
                    "company": "",
                    "salary": "",
                    "location": "",
                    "url": "",
                    "keyword": keyword,
                })
        i += 1

    return jobs


def parse_iguopin(text, keyword):
    """
    解析国聘搜索结果。
    实际格式（"CAAC"关键词）：
      职位名称
      「地点」
      薪资 性质 经验 学历
      职位类别
      公司名
      公司信息
    """
    jobs = []
    if not text:
        return jobs

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if is_relevant_job_title(line, keyword) and len(line) < 60:
            title = line.strip()
            location = ""
            salary = ""
            company = ""

            look_ahead = []
            for j in range(1, min(10, len(lines) - i)):
                nxt = lines[i + j].strip()
                if not nxt:
                    continue
                look_ahead.append(nxt)

            for la in look_ahead:
                # 地点 【xxx】
                loc_m = re.match(r'「(.+?)」', la)
                if loc_m and not location:
                    location = loc_m.group(1)
                    continue
                # 薪资: 8~16K, 5~10K, 面议
                sal_m = re.search(r'(\d[\d\.]*\s*[~]\s*\d[\d\.]*\s*[kK]|\d[\d\.]*[kK]|面议)', la)
                if sal_m and not salary:
                    salary = sal_m.group(1).strip()
                    continue
                # 公司
                if not company and ("公司" in la or "科技" in la or "有限" in la or "集团" in la):
                    if "人力资源" not in la and len(la) < 40:
                        company = la[:40]
                        continue

            if location or salary:
                jobs.append({
                    "platform": "国聘",
                    "title": title,
                    "company": company,
                    "salary": salary,
                    "location": location,
                    "url": "",
                    "keyword": keyword,
                })
            elif any(k.lower() in title.lower() for k in KEYWORDS):
                jobs.append({
                    "platform": "国聘",
                    "title": title,
                    "company": "",
                    "salary": "",
                    "location": "",
                    "url": "",
                    "keyword": keyword,
                })
        i += 1

    return jobs


def parse_iguopin_html(html, keyword):
    """
    国聘（iguopin）卡片式解析（2026-07-15 快照确认的 DOM）：
      <div class="job-card">
        <div class="job-name">标题</div>
        <div class="job-district">「成都-郫都区」</div>
        <span class="job-salary">8~16K·13薪</span>
        <a class="substring company-name" title="公司名" href="/company?id=138..." ...>公司名</a>

    国聘是 React SPA，岗位详情走 JS 路由、DOM 里没有岗位详情 <a href>，页面上仅有的
    iguopin.com 链接是导航/客服/文档等装饰位（历史上被 attach_job_urls 的宽正则抓成
    恒定 8 条杂链，逐日误报 url_position_mismatch）。改为逐卡解析后，url 取该卡内真实存在
    的公司页链接 https://www.iguopin.com/company?id=<id>——注意 extract_stable_job_id
    只认 /jobdetail、/job/、/a/、*.html，不会把 /company?id= 当岗位ID，故去重自动回退
    文本签名（公司+标题+城市），同公司不同岗位不会误并。卡片容器缺失时返回空，交由
    crawl_iguopin 降级文本解析兜底。
    """
    jobs = []
    if not html:
        return jobs

    # 空结果页识别：真实无结果 ≠ 解析失败，不记质量事件不存快照
    if any(marker in html for marker in ("没有找到符合您条件的职位", "没有找到相关职位")):
        print(f"  [INFO] 平台真实无结果（空结果页文案确认）")
        return jobs

    # 右边界锚 [\s"] 只切 class="job-card" 精确结束处，杜绝未来 job-card* 变体类名误切、
    # 让 DEBUG 计数恒等真实卡数
    cards = re.split(r'class="job-card[\s"]', html)[1:]
    if not cards:
        return jobs  # 无卡片容器：交由调用方降级文本解析

    seen = set()
    titles_found = 0  # 抽出标题的卡数（区分"真DOM解析失败"与"平台真没这类岗"）
    for card in cards:
        tm = re.search(r'class="job-name"[^>]*>\s*([^<]{2,200}?)\s*<', card)
        if not tm:
            continue
        title = html_lib.unescape(re.sub(r"\s+", " ", tm.group(1))).strip()
        if not title:
            continue
        titles_found += 1
        if not is_relevant_job_title(title, keyword):
            continue
        # 公司锚点属性无序提取：先框住 company-name 的 <a>…</a>，再从其属性里取 href/title，
        # 不绑定 class 与 href 的先后顺序（防站点调属性序导致丢名丢链→签名翻抖）
        cm = re.search(r'<a\b([^>]*\bcompany-name\b[^>]*)>\s*([^<]{2,80}?)\s*</a>', card)
        cm_attrs = cm.group(1) if cm else ""
        cm_href = re.search(r'href="(/company\?id=\d+)"', cm_attrs)
        company = html_lib.unescape(cm.group(2)).strip() if cm else ""
        if not company and cm_attrs:
            tm_c = re.search(r'title="([^"]{2,80})"', cm_attrs)  # 兜底：anchor 的 title 属性
            company = html_lib.unescape(tm_c.group(1)).strip() if tm_c else ""
        if not company:
            dpm = re.search(r'class="department-name"[^>]*>\s*([^<]{2,80}?)\s*<', card)
            company = html_lib.unescape(dpm.group(1)).strip() if dpm else ""
        # 卡内去重：同公司+同标题的重复卡（跨关键词/跨平台合并留给 deduplicate_jobs）
        key = (company, title)
        if key in seen:
            continue
        seen.add(key)
        dm = re.search(r'class="job-district"[^>]*>\s*「?([^<」]{1,40}?)」?\s*<', card)
        sm = re.search(r'class="job-salary"[^>]*>\s*([^<]{1,30}?)\s*<', card)
        jobs.append({
            "platform": "国聘",
            "title": title,
            "company": company,
            "salary": sm.group(1).strip() if sm else "",
            "location": (html_lib.unescape(dm.group(1)).strip().replace("·", "-") if dm else ""),
            "url": ("https://www.iguopin.com" + cm_href.group(1)) if cm_href else "",
            "keyword": keyword,
        })
    print(f"  [DEBUG] 国聘卡片解析 {len(cards)} 张卡（抽出标题 {titles_found}）→ {len(jobs)} 个相关岗位")
    if not jobs:
        if titles_found == 0:
            # 卡片容器在、却一个标题都抽不出 = 真 DOM 结构变更/解析失败 → 修复触发（看门狗照常升级）
            record_quality_event("国聘", keyword, "parsed_jobs", 0, None,
                                 "卡片容器存在但未抽出任何岗位标题（疑似 DOM 结构变更，需修复）")
            save_html_snapshot("国聘", keyword, html, "no_parsed_jobs")
        else:
            # 有标题但无一匹配我们的关键词 = 平台真没这类岗，非解析故障、无代码可修 →
            # 信息型事件（看门狗 NON_ESCALATING_METRICS 不催修复，仅日报可见+存快照备查）
            record_quality_event("国聘", keyword, "no_relevant_jobs", titles_found, None,
                                 f"卡片 {titles_found} 个但无一匹配关键词（平台无该类岗，非解析故障）")
            save_html_snapshot("国聘", keyword, html, "no_relevant_jobs")
    return jobs


def parse_liepin_html(html, keyword):
    """
    从猎聘搜索页 HTML 的岗位卡片解析。
    卡片结构（2026-07 快照确认）：
      <div class="... job-card-pc-container">
        <a data-nick="job-detail-job-info" href="https://www.liepin.com/a/xxx.shtml?...">
          <div title="...">标题</div> <span>【</span><span>地点</span><span>】</span> <span>薪资</span>
        </a>
        <div data-nick="job-detail-company-info"><span class="... ellipsis-1">公司名</span>...</div>
    CSS 类名带构建哈希（_40108xxx）会漂移，只依赖 data-nick 锚点和文本结构。
    """
    jobs = []
    if not html or "job-card-pc-container" not in html:
        return jobs

    cards = html.split("job-card-pc-container")[1:]
    titles_found = 0
    relevant_titles = 0
    for card in cards:
        url = ""
        m = re.search(
            r'data-nick="job-detail-job-info"[^>]*href=["\'](https?://(?:www\.)?liepin\.com/(?:job|a)/[^"\'?#]+)',
            card,
        )
        if m:
            url = m.group(1)

        anchor_m = re.search(r'data-nick="job-detail-job-info"[^>]*>(.*?)</a>', card, re.DOTALL)
        if not anchor_m:
            continue
        anchor_html = anchor_m.group(1)
        inner = re.sub(r"<[^>]+>", " ", anchor_html)
        inner = html_lib.unescape(re.sub(r"\s+", " ", inner)).strip()
        if not inner:
            continue

        location_candidates = [value.strip() for value in re.findall(r"【\s*(.+?)\s*】", inner)]
        location = next((value for value in location_candidates if is_valid_location(value)), "")

        sal_m = re.search(r"(\d[\d.]*\s*-\s*\d[\d.]*\s*[kK万](?:·\d+薪)?|\d[\d.]*[kK万]以上|面议)", inner)
        salary = sal_m.group(1).strip() if sal_m else ""

        title_attr = re.search(
            r'<(?:div|span)[^>]*\btitle=["\']([^"\']{2,60})["\']',
            anchor_html,
            re.IGNORECASE,
        )
        title = html_lib.unescape(title_attr.group(1)).strip() if title_attr else inner.split("【")[0].strip()
        if not title and sal_m:
            title = inner[: sal_m.start()].strip()
        if not title or len(title) > 60:
            continue
        titles_found += 1
        if not is_relevant_job_title(title, keyword):
            continue
        relevant_titles += 1

        company = ""
        cpos = card.find('data-nick="job-detail-company-info"')
        if cpos >= 0:
            cm = re.search(
                r'<span[^>]*class="[^"]*ellipsis-1[^"]*"[^>]*>\s*([^<]{2,40}?)\s*</span>',
                card[cpos:cpos + 1500],
            )
            if cm:
                company = cm.group(1).strip()

        jobs.append({
            "platform": "猎聘",
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "url": url,
            "keyword": keyword,
        })

    record_card_parse_outcome(
        "猎聘", keyword, html, len(cards), titles_found, relevant_titles, len(jobs)
    )
    return jobs


def parse_51job_html(html, keyword):
    """
    从前程无忧搜索页 HTML 的岗位卡片解析。
    卡片结构（2026-07 快照确认）：
      <div class="joblist-item">
        <div sensorsdata="{jobId, jobTitle, jobSalary, jobArea, ...}" ...>
        ... <span title="公司名" class="cname text-cut">公司名</span>
    sensorsdata 是 HTML 转义的埋点 JSON，字段完整可靠。
    详情页 URL 由 jobId 构造：jobs.51job.com/all/<jobId>.html（已验证可访问）。
    """
    jobs = []
    if not html or "joblist-item" not in html:
        return jobs

    # 词边界式切分：兼容 class="joblist-item" 与 class="xxx joblist-item"，
    # 但不误切 joblist-item-job 之类的派生类名
    cards = re.split(r'class="[^"]*\bjoblist-item[" ]', html)[1:]
    titles_found = 0
    relevant_titles = 0
    for chunk in cards:
        m = re.search(r'sensorsdata="([^"]+)"', chunk)
        if not m:
            continue
        try:
            data = json.loads(html_lib.unescape(m.group(1)))
        except (json.JSONDecodeError, ValueError):
            continue

        title = str(data.get("jobTitle") or "").strip()
        if not title or len(title) > 60:
            continue
        titles_found += 1
        if not is_relevant_job_title(title, keyword):
            continue
        relevant_titles += 1

        job_id = str(data.get("jobId") or "").strip()
        url = f"https://jobs.51job.com/all/{job_id}.html" if job_id.isdigit() else ""
        salary = str(data.get("jobSalary") or "").strip()
        location = str(data.get("jobArea") or "").strip().replace("·", "-")

        cm = re.search(r'<span[^>]*class="cname[^"]*"[^>]*>\s*([^<]{2,50}?)\s*</span>', chunk)
        company = cm.group(1).strip() if cm else ""

        jobs.append({
            "platform": "前程无忧",
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "url": url,
            "keyword": keyword,
        })

    record_card_parse_outcome(
        "前程无忧", keyword, html, len(cards), titles_found, relevant_titles, len(jobs)
    )
    return jobs


def parse_zhaopin_html(html, keyword):
    """
    智联招聘解析：优先卡片解析（2026-07-13 探针确认的 DOM）：
      <div class="joblist-box__item ...">
        <a href="...zhaopin.com/jobdetail/xxx.htm..." class="jobinfo__name">标题</a>
        <p class="jobinfo__salary">5000-10000元</p>
        <img class="jobinfo__other-info-location-image"> <span>成都·双流·新兴</span>
        <a title="公司名" ... class="companyinfo__name [companyinfo__name-short]">公司名</a>
    卡片结构缺失时降级为旧全局收集+就近匹配。
    """
    jobs = []
    if not html:
        return jobs

    # 空结果页识别：真实无结果 ≠ 解析失败，不记质量事件不存快照
    if any(marker in html for marker in ("您搜索的职位找不到", "没有找到相关职位")):
        print(f"  [INFO] 平台真实无结果（空结果页文案确认）")
        return jobs

    cards = re.split(r'class="[^"]*\bjoblist-box__item[" ]', html)[1:]
    if cards:
        seen_ids = set()
        titles_found = 0
        relevant_titles = 0
        for card in cards:
            um = re.search(r'href=["\'](https?://(?:www\.)?zhaopin\.com/jobdetail/[^"\']+)["\']', card)
            tm = re.search(r'class="jobinfo__name"[^>]*>\s*([^<]{2,60}?)\s*</a>', card)
            if not tm:
                continue
            title = html_lib.unescape(tm.group(1)).strip()
            if not title:
                continue
            titles_found += 1
            if not is_relevant_job_title(title, keyword):
                continue
            relevant_titles += 1
            if not um:
                continue
            url = um.group(1).split("?")[0]
            job_id = extract_stable_job_id(url)
            if job_id and job_id in seen_ids:
                continue
            if job_id:
                seen_ids.add(job_id)
            sm = re.search(r'class="jobinfo__salary"[^>]*>\s*([^<]{2,30}?)\s*<', card)
            lm = re.search(r'jobinfo__other-info-location-image[^>]*>\s*<span>\s*([^<]{2,40}?)\s*</span>', card)
            cm = re.search(
                r'class="(?:[^"]*\s)?companyinfo__name(?:\s[^"]*)?"[^>]*>\s*([^<]{2,50}?)\s*<',
                card,
            )
            jobs.append({
                "platform": "智联招聘",
                "title": title,
                "company": html_lib.unescape(cm.group(1)).strip() if cm else "",
                "salary": sm.group(1).strip() if sm else "",
                "location": (lm.group(1).strip().replace("·", "-") if lm else ""),
                "url": url,
                "keyword": keyword,
            })
        print(f"  [DEBUG] 卡片解析 {len(cards)} 张卡 → {len(jobs)} 个相关岗位")
        record_card_parse_outcome(
            "智联招聘", keyword, html, len(cards), titles_found, relevant_titles, len(jobs)
        )
        return jobs

    # ---- 旧版 DOM 兜底：按相邻岗位链接的局部片段解析，禁止跨卡片猜薪资/公司 ----
    link_matches = list(re.finditer(
        r'<a[^>]*?href=["\'](https?://(?:www\.)?zhaopin\.com/jobdetail/[^"\']+)["\'][^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL,
    ))
    titles_found = 0
    relevant_titles = 0
    seen_urls = set()
    for index, match in enumerate(link_matches):
        inner = html_lib.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', match.group(2)))).strip()
        title = inner if 2 < len(inner) < 60 else ""
        if not title:
            continue
        titles_found += 1
        if not is_relevant_job_title(title, keyword):
            continue
        relevant_titles += 1
        url = match.group(1).split("?")[0]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        next_start = link_matches[index + 1].start() if index + 1 < len(link_matches) else len(html)
        window_start = match.start()
        window_end = next_start
        window_html = html[window_start:window_end]

        salary_match = re.search(
            r'class=["\'][^"\']*salary[^"\']*["\'][^>]*>\s*([^<]{2,40}?)\s*<',
            window_html, re.IGNORECASE,
        )
        company_match = re.search(
            r'<a[^>]*href=["\'](?:https?://)?(?:www\.)?zhaopin\.com/companydetail/[^"\']+["\'][^>]*>'
            r'\s*([^<]{2,50}?)\s*</a>',
            window_html, re.IGNORECASE,
        )
        location_match = re.search(
            r'(?:location|address)[^>]*>\s*([^<]{2,40}?)\s*<',
            window_html, re.IGNORECASE,
        )
        jobs.append({
            "platform": "智联招聘",
            "title": title,
            "company": html_lib.unescape(company_match.group(1)).strip() if company_match else "",
            "salary": html_lib.unescape(salary_match.group(1)).strip() if salary_match else "",
            "location": (
                html_lib.unescape(location_match.group(1)).strip().replace("·", "-")
                if location_match else ""
            ),
            "url": url,
            "keyword": keyword,
        })
    record_card_parse_outcome(
        "智联招聘", keyword, html, len(link_matches), titles_found, relevant_titles, len(jobs)
    )
    return jobs


def record_card_parse_outcome(
    platform, keyword, html, card_count, title_count, relevant_count, job_count
):
    """统一卡片解析分流：零相关是信息，零标题/相关标题无法成岗才是故障。"""
    if job_count:
        return
    if title_count > 0 and relevant_count == 0:
        record_quality_event(
            platform, keyword, "no_relevant_jobs", title_count, None,
            f"卡片 {card_count} 个、抽出标题 {title_count} 个，但无相关岗位",
        )
        save_html_snapshot(platform, keyword, html, "no_relevant_jobs")
    else:
        record_quality_event(
            platform, keyword, "parsed_jobs", 0, None,
            f"卡片/链接 {card_count} 个、标题 {title_count} 个、相关标题 {relevant_count} 个，未形成岗位",
        )
        save_html_snapshot(platform, keyword, html, "no_parsed_jobs")


EMPTY_RESULT_MARKERS = {
    "猎聘": ("没有找到符合条件的职位", "未找到符合条件的职位", "暂无相关职位", "暂无职位"),
    "前程无忧": ("没有找到相关职位", "没有找到符合条件的职位", "暂无搜索结果", "暂无相关职位"),
    "国聘": ("没有找到符合您条件的职位",),
    "智联招聘": ("您搜索的职位找不到", "没有找到相关职位"),
}


def has_explicit_empty_result(platform, text="", html=""):
    """只有命中平台明确空结果文案，才把无岗位视为可信真零。"""
    content = f"{text or ''}\n{html or ''}"
    return any(marker in content for marker in EMPTY_RESULT_MARKERS.get(platform, ()))


def count_result_cards(platform, html):
    patterns = {
        "猎聘": r"job-card-pc-container",
        "前程无忧": r'class="[^"]*\bjoblist-item[" ]',
        "国聘": r'class="job-card[\s"]',
        "智联招聘": r'class="[^"]*\bjoblist-box__item[" ]',
    }
    pattern = patterns.get(platform)
    return len(re.findall(pattern, html or "")) if pattern else 0


def max_pages_for_platform(platform):
    """Return the bounded per-query page limit from config."""
    configured = CONFIG.get("max_pages_per_query", 1)
    if isinstance(configured, dict):
        configured = configured.get(platform, 1)
    try:
        return max(1, min(int(configured), 20))
    except (TypeError, ValueError):
        return 1


def update_url_query(url, **updates):
    """Update query parameters without dropping existing search filters."""
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    replacement = {str(key): str(value) for key, value in updates.items()}
    kept = [(key, value) for key, value in query if key not in replacement]
    kept.extend(replacement.items())
    return urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urllib.parse.urlencode(kept),
        parsed.fragment,
    ))


def extract_result_page_keys(platform, html):
    """Extract stable raw-card keys before relevance filtering for page-loop guards."""
    html = html or ""
    keys = []
    if platform == "猎聘":
        keys = re.findall(
            r'href=["\'](https?://(?:www\.)?liepin\.com/(?:job|a)/[^"\'?#]+)',
            html,
            re.IGNORECASE,
        )
    elif platform == "前程无忧":
        decoded = html_lib.unescape(html)
        keys = [f"job:{job_id}" for job_id in re.findall(r'"jobId"\s*:\s*"?([^",}]+)', decoded)]
    elif platform == "智联招聘":
        keys = re.findall(
            r'href=["\'](https?://(?:www\.)?zhaopin\.com/jobdetail/[^"\'?#]+)',
            html,
            re.IGNORECASE,
        )
    elif platform == "国聘":
        cards = re.split(r'<div[^>]*class=["\'][^"\']*\bjob-card\b[^"\']*["\'][^>]*>', html)[1:]
        for card in cards:
            title_match = re.search(r'class=["\'][^"\']*\bjob-name\b[^"\']*["\'][^>]*>(.*?)</div>', card, re.DOTALL)
            location_match = re.search(r'class=["\'][^"\']*\bjob-district\b[^"\']*["\'][^>]*>(.*?)</div>', card, re.DOTALL)
            company_match = re.search(r'href=["\']/?company\?id=([^"\'&]+)', card)
            title = html_lib.unescape(re.sub(r'<[^>]+>', ' ', title_match.group(1))).strip() if title_match else ""
            location = html_lib.unescape(re.sub(r'<[^>]+>', ' ', location_match.group(1))).strip() if location_match else ""
            company_id = company_match.group(1) if company_match else ""
            if title or location or company_id:
                keys.append(f"{company_id}|{title}|{location}")
    return tuple(dict.fromkeys(str(key).split("#", 1)[0] for key in keys if key))


def pagination_state(platform, html):
    """Return platform-specific next-page state; never infer enabled from label text alone."""
    html = html or ""
    state = {"known": False, "has_next": False, "next_url": "", "total_pages": 0}
    if platform == "国聘":
        next_tag = re.search(
            r'<li[^>]*class=["\'][^"\']*\bant-pagination-next\b[^"\']*["\'][^>]*>',
            html,
            re.IGNORECASE,
        )
        page_numbers = [int(value) for value in re.findall(r'ant-pagination-item-(\d+)', html)]
        state["total_pages"] = max(page_numbers, default=0)
        if next_tag:
            tag = next_tag.group(0).lower()
            state["known"] = True
            state["has_next"] = bool(
                re.search(r'aria-disabled=["\']false["\']', tag)
                and "ant-pagination-disabled" not in tag
                and not re.search(r'\sdisabled(?:=|\s|>)', tag)
            )
        return state

    if platform == "智联招聘":
        state["known"] = bool(re.search(
            r'<[^>]*class=["\'][^"\']*\bsoupager__[^"\']*["\']', html, re.IGNORECASE
        ))
        for anchor in re.finditer(r'<a\b([^>]*)>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
            attrs, body = anchor.groups()
            class_match = re.search(r'class=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
            href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            label = html_lib.unescape(re.sub(r'<[^>]+>', ' ', body)).strip()
            classes = class_match.group(1) if class_match else ""
            if "soupager__btn" in classes and label == "下一页" and href_match:
                state["has_next"] = True
                state["next_url"] = html_lib.unescape(href_match.group(1))
                break
        page_numbers = [int(value) for value in re.findall(r'/p(\d+)["\']\s+class=["\'][^"\']*soupager__index', html)]
        state["total_pages"] = max(page_numbers, default=0)
        return state

    # Liepin/51job occasionally expose a real anchor. Follow it when present,
    # otherwise leave state unknown and let the platform-specific cap policy decide.
    for anchor in re.finditer(r'<a\b([^>]*)>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        attrs, body = anchor.groups()
        href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        rel_match = re.search(r'rel=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        label = html_lib.unescape(re.sub(r'<[^>]+>', ' ', body)).strip()
        if href_match and (label == "下一页" or (rel_match and "next" in rel_match.group(1).lower())):
            state.update({
                "known": True,
                "has_next": True,
                "next_url": html_lib.unescape(href_match.group(1)),
            })
            break
    return state


def detect_result_truncation(platform, html, card_count=None):
    """Use enabled platform controls first, then a cap hint only when state is unknown."""
    html = html or ""
    card_count = count_result_cards(platform, html) if card_count is None else card_count
    page_state = pagination_state(platform, html)
    cap = int(RESULT_CAPS.get(platform, 0) or 0)
    truncated = card_count > 0 and (
        page_state["has_next"]
        or (not page_state["known"] and cap > 0 and card_count >= cap)
    )
    if not truncated:
        return None
    if page_state["has_next"]:
        detail = f"当前页 {card_count} 张卡且存在下一页"
    else:
        detail = f"当前页 {card_count} 张卡达到配置上限 {cap}"
    return {
        "card_count": card_count,
        "total_pages": page_state["total_pages"],
        "has_next": page_state["has_next"],
        "detail": detail,
    }


def record_result_truncation(platform, keyword, html):
    result = detect_result_truncation(platform, html)
    if result:
        record_quality_event(
            platform,
            keyword,
            "possible_truncation",
            result["card_count"],
            RESULT_CAPS.get(platform),
            result["detail"] + "；本日报为当前可见结果，不代表市场全量",
        )


def record_pagination_limit(platform, keyword, pages_fetched, jobs_collected, reason):
    record_quality_event(
        platform,
        keyword,
        "possible_truncation",
        jobs_collected,
        max_pages_for_platform(platform),
        f"已抓取 {pages_fetched} 页；{reason}；本日报不代表市场全量",
    )


def page_job_key(job):
    stable_id = extract_stable_job_id(job.get("url", ""))
    if stable_id:
        return f"id|{stable_id}"
    return "text|" + "|".join(
        str(job.get(field) or "").strip().casefold()
        for field in ("platform", "title", "company", "location", "salary")
    )


def extend_unique_page_jobs(target, page_jobs, seen_job_keys):
    added = 0
    for job in page_jobs:
        key = page_job_key(job)
        if key in seen_job_keys:
            continue
        seen_job_keys.add(key)
        target.append(job)
        added += 1
    return added


# ============================================================
# 爬取平台流程
# ============================================================

def crawl_liepin(keyword):
    """爬取猎聘：优先 HTML 卡片解析，页面结构缺失时回退文本解析"""
    base_url = f"https://www.liepin.com/zhaopin/?key={urllib.parse.quote(keyword)}"
    max_pages = max_pages_for_platform("猎聘")
    jobs = []
    seen_job_keys = set()
    seen_page_tokens = set()

    for page in range(1, max_pages + 1):
        url = update_url_query(base_url, currentPage=page - 1, pageSize=40)
        print(f"\n  📍 猎聘 第{page}页 → {url}")
        text, links, html = safe_browser_task(url, wait_ms=5000, timeout=30)
        if has_explicit_empty_result("猎聘", text, html):
            if page == 1:
                print("  → 暂无结果（空结果页文案确认）")
                return []
            print(f"  → 第{page}页为空，分页完成")
            break

        if html and "job-card-pc-container" in html:
            raw_keys = extract_result_page_keys("猎聘", html)
            page_token = tuple(sorted(raw_keys))
            if page_token and page_token in seen_page_tokens:
                record_pagination_limit("猎聘", keyword, page - 1, len(jobs), "站点返回重复页，已停止")
                break
            if page_token:
                seen_page_tokens.add(page_token)

            event_start = len(QUALITY_EVENTS)
            page_jobs = parse_liepin_html(html, keyword)
            if not page_jobs and any(
                event.get("metric") == "parsed_jobs" for event in QUALITY_EVENTS[event_start:]
            ):
                raise CrawlFetchError(f"猎聘第{page}页结果容器存在但未解析出岗位标题")
            added = extend_unique_page_jobs(jobs, page_jobs, seen_job_keys)
            print(
                f"  → 第{page}页解析 {len(page_jobs)} 个相关岗位，新增 {added} 个，"
                f"累计 {len(jobs)} 个"
            )

            card_count = count_result_cards("猎聘", html)
            page_state = pagination_state("猎聘", html)
            cap = int(RESULT_CAPS.get("猎聘", 40) or 40)
            has_more = page_state["has_next"] or (not page_state["known"] and card_count >= cap)
            if not has_more:
                break
            if page >= max_pages:
                record_pagination_limit("猎聘", keyword, page, len(jobs), "达到配置分页上限")
                break
            if PAGINATION_PAUSE_SECONDS:
                time.sleep(PAGINATION_PAUSE_SECONDS)
            continue

        if page == 1 and text:
            page_jobs = parse_liepin(text, keyword)
            page_jobs = attach_job_urls(page_jobs, html or "", "猎聘", search_url=url, keyword=keyword)
            if page_jobs:
                record_quality_event(
                    "猎聘", keyword, "card_parse_fallback", len(page_jobs), None,
                    "未找到岗位卡片结构，已回退文本解析",
                )
                save_html_snapshot("猎聘", keyword, html or "", "card_parse_fallback")
                print(f"  → 文本回退解析到 {len(page_jobs)} 个岗位")
                return page_jobs
        raise CrawlFetchError(f"猎聘第{page}页非空，但未识别结果容器、明确空页文案或有效岗位")

    return jobs


def crawl_51job(keyword):
    """爬取前程无忧：优先 HTML 卡片解析（sensorsdata），页面结构缺失时回退文本解析"""
    url = f"https://we.51job.com/pc/search?keyword={urllib.parse.quote(keyword)}&searchType=2"
    max_pages = max_pages_for_platform("前程无忧")
    jobs = []
    seen_job_keys = set()
    seen_page_tokens = set()

    for page in range(1, max_pages + 1):
        print(f"\n  📍 前程无忧 第{page}页 → {url}")
        text, links, html = safe_browser_task(url, wait_ms=5000, timeout=30)
        if has_explicit_empty_result("前程无忧", text, html):
            if page == 1:
                print("  → 暂无结果（空结果页文案确认）")
                return []
            print(f"  → 第{page}页为空，分页完成")
            break

        if html and "joblist-item" in html:
            raw_keys = extract_result_page_keys("前程无忧", html)
            page_token = tuple(sorted(raw_keys))
            if page_token and page_token in seen_page_tokens:
                record_pagination_limit("前程无忧", keyword, page - 1, len(jobs), "站点返回重复页，已停止")
                break
            if page_token:
                seen_page_tokens.add(page_token)

            event_start = len(QUALITY_EVENTS)
            page_jobs = parse_51job_html(html, keyword)
            if not page_jobs and any(
                event.get("metric") == "parsed_jobs" for event in QUALITY_EVENTS[event_start:]
            ):
                raise CrawlFetchError(f"前程无忧第{page}页结果容器存在但未解析出岗位标题")
            added = extend_unique_page_jobs(jobs, page_jobs, seen_job_keys)
            print(
                f"  → 第{page}页解析 {len(page_jobs)} 个相关岗位，新增 {added} 个，"
                f"累计 {len(jobs)} 个"
            )

            page_state = pagination_state("前程无忧", html)
            if page_state["has_next"] and page_state["next_url"]:
                if page >= max_pages:
                    record_pagination_limit("前程无忧", keyword, page, len(jobs), "达到配置分页上限")
                    break
                next_url = urllib.parse.urljoin(url, page_state["next_url"])
                if next_url == url:
                    record_pagination_limit("前程无忧", keyword, page, len(jobs), "下一页链接未变化")
                    break
                url = next_url
                if PAGINATION_PAUSE_SECONDS:
                    time.sleep(PAGINATION_PAUSE_SECONDS)
                continue

            # 当前站点的 pageNum 查询参数会被前端重置为 1。只有真实下一页链接
            # 才能继续；命中固定首屏上限时如实披露，不猜测无效 URL。
            record_result_truncation("前程无忧", keyword, html)
            break

        if page == 1 and text:
            page_jobs = parse_51job(text, keyword)
            page_jobs = attach_job_urls(page_jobs, html or "", "前程无忧", search_url=url, keyword=keyword)
            if page_jobs:
                record_quality_event(
                    "前程无忧", keyword, "card_parse_fallback", len(page_jobs), None,
                    "未找到岗位卡片结构，已回退文本解析",
                )
                save_html_snapshot("前程无忧", keyword, html or "", "card_parse_fallback")
                print(f"  → 文本回退解析到 {len(page_jobs)} 个岗位")
                return page_jobs
        raise CrawlFetchError(f"前程无忧第{page}页非空，但未识别结果容器、明确空页文案或有效岗位")

    return jobs


def crawl_iguopin(keyword):
    """爬取国聘"""
    url = f"https://www.iguopin.com/job?keyword={urllib.parse.quote(keyword)}"
    max_pages = max_pages_for_platform("国聘")
    jobs = []
    seen_job_keys = set()
    seen_page_tokens = set()
    print(f"\n  📍 国聘 第1页 → {url}")

    try:
        text, links, html = safe_browser_task(
            url, wait_ms=6000, timeout=30, close_browser=False
        )
        for page in range(1, max_pages + 1):
            if has_explicit_empty_result("国聘", text, html):
                if page == 1:
                    print("  → 暂无结果（空结果页文案确认）")
                    return []
                print(f"  → 第{page}页为空，分页完成")
                break

            raw_keys = extract_result_page_keys("国聘", html or "")
            page_token = tuple(sorted(raw_keys))
            if page_token and page_token in seen_page_tokens:
                record_pagination_limit("国聘", keyword, page - 1, len(jobs), "站点返回重复页，已停止")
                break
            if page_token:
                seen_page_tokens.add(page_token)

            event_start = len(QUALITY_EVENTS)
            page_jobs = parse_iguopin_html(html or "", keyword)
            if not page_jobs and text and 'class="job-card' not in (html or ""):
                # 仅当卡片容器整体缺失（疑似旧版 DOM）才降级文本解析。
                page_jobs = parse_iguopin(text, keyword)
            if not page_jobs and any(
                event.get("metric") == "parsed_jobs" for event in QUALITY_EVENTS[event_start:]
            ):
                raise CrawlFetchError(f"国聘第{page}页结果容器存在但未解析出岗位标题")
            for job in page_jobs:
                if not job.get("url"):
                    job["url"] = url
            added = extend_unique_page_jobs(jobs, page_jobs, seen_job_keys)
            print(
                f"  → 第{page}页解析 {len(page_jobs)} 个相关岗位，新增 {added} 个，"
                f"累计 {len(jobs)} 个"
            )

            no_relevant = any(
                event.get("metric") == "no_relevant_jobs" for event in QUALITY_EVENTS[event_start:]
            )
            if not (page_jobs or no_relevant):
                raise CrawlFetchError(f"国聘第{page}页非空，但未识别有效岗位")

            page_state = pagination_state("国聘", html or "")
            if not page_state["has_next"]:
                break
            if page >= max_pages:
                record_pagination_limit("国聘", keyword, page, len(jobs), "达到配置分页上限")
                break

            selector = (
                'li.ant-pagination-next[aria-disabled="false"]'
                ':not(.ant-pagination-disabled) button:not([disabled])'
            )
            stdout, stderr, rc = run_browser(["click", selector], timeout=10)
            if rc != 0:
                raise CrawlFetchError(f"国聘第{page + 1}页点击失败: {stderr[:160]}")
            if PAGINATION_PAUSE_SECONDS:
                time.sleep(PAGINATION_PAUSE_SECONDS)
            text, links, html = read_open_browser_page(url, wait_ms=3000)
            print(f"  📍 国聘 第{page + 1}页（站内分页）")

        return jobs
    finally:
        try:
            browser_close()
        except Exception:
            pass


def fetch_zhaopin_page(url, page):
    """Fetch one Zhaopin page with the existing bounded retry policy."""
    retry_delays = [10, 20, 40]
    last_error = CrawlFetchError("尚未获取页面")
    for attempt in range(3):
        if attempt > 0:
            print(f"  🔄 第{attempt+1}次重试（等待{retry_delays[attempt-1]}秒后）...")
            time.sleep(retry_delays[attempt-1])
        try:
            text, links, html = safe_browser_task(url, wait_ms=5000, timeout=20)
            if has_explicit_empty_result("智联招聘", text, html):
                return text, links, html
            if html and len(html) > 10000:
                return text, links, html
            if html:
                print(f"  ⚠️ HTML太短 ({len(html)}字)，可能未完全加载")
                raise CrawlFetchError(f"第{attempt+1}次HTML过短({len(html)}字)")
            else:
                print(f"  ⚠️ 第{attempt+1}次: 获取HTML失败")
                raise CrawlFetchError(f"第{attempt+1}次HTML为空")
        except CrawlFetchError as e:
            print(f"  ⚠️ 第{attempt+1}次异常: {e}", file=sys.stderr)
            last_error = e

    print("  ❌ 重试3次后仍失败")
    error_type = CrawlBlockedError if isinstance(last_error, CrawlBlockedError) else CrawlFetchError
    raise error_type(f"智联招聘第{page}页抓取重试耗尽: {last_error}") from last_error


def crawl_zhaopin(keyword):
    """爬取智联招聘，跟随页面提供的规范化下一页链接。"""
    # 城市码来自 config：空串沿用站点入口；显式城市码使用对应城市站。
    city_code = str(CONFIG.get("zhaopin_city_code", "") or "").strip()
    city_seg = f"jl{city_code}/" if city_code else ""
    url = f"https://www.zhaopin.com/sou/{city_seg}?kw={urllib.parse.quote(keyword)}"
    max_pages = max_pages_for_platform("智联招聘")
    jobs = []
    seen_job_keys = set()
    seen_page_tokens = set()

    for page in range(1, max_pages + 1):
        print(f"\n  📍 智联招聘 第{page}页 → {url}")
        text, links, html = fetch_zhaopin_page(url, page)
        if has_explicit_empty_result("智联招聘", text, html):
            if page == 1:
                print("  → 暂无结果（空结果页文案确认）")
                return []
            print(f"  → 第{page}页为空，分页完成")
            break

        raw_keys = extract_result_page_keys("智联招聘", html)
        page_token = tuple(sorted(raw_keys))
        if page_token and page_token in seen_page_tokens:
            record_pagination_limit("智联招聘", keyword, page - 1, len(jobs), "站点返回重复页，已停止")
            break
        if page_token:
            seen_page_tokens.add(page_token)

        event_start = len(QUALITY_EVENTS)
        page_jobs = parse_zhaopin_html(html, keyword)
        if not page_jobs and any(
            event.get("metric") == "parsed_jobs" for event in QUALITY_EVENTS[event_start:]
        ):
            raise CrawlFetchError(f"智联招聘第{page}页结果页存在但未可信解析出岗位")
        added = extend_unique_page_jobs(jobs, page_jobs, seen_job_keys)
        print(
            f"  → 第{page}页解析 {len(page_jobs)} 个相关岗位，新增 {added} 个，"
            f"累计 {len(jobs)} 个"
        )

        page_state = pagination_state("智联招聘", html)
        if not page_state["has_next"]:
            if not page_state["known"]:
                record_result_truncation("智联招聘", keyword, html)
            break
        if page >= max_pages:
            record_pagination_limit("智联招聘", keyword, page, len(jobs), "达到配置分页上限")
            break
        next_url = urllib.parse.urljoin(url, page_state["next_url"])
        if not next_url or next_url == url:
            record_pagination_limit("智联招聘", keyword, page, len(jobs), "下一页链接缺失或未变化")
            break
        url = next_url
        if PAGINATION_PAUSE_SECONDS:
            time.sleep(PAGINATION_PAUSE_SECONDS)

    return jobs

# 平台爬取映射
PLATFORM_CRAWLERS = [
    ("猎聘", crawl_liepin),
    ("前程无忧", crawl_51job),
    ("国聘", crawl_iguopin),
    ("智联招聘", crawl_zhaopin),
]
if ENABLED_PLATFORMS:
    PLATFORM_CRAWLERS = [(name, crawler) for name, crawler in PLATFORM_CRAWLERS if name in ENABLED_PLATFORMS]


# ============================================================
# 去重
# ============================================================

INVALID_FIELD_OBSERVATIONS = "_invalid_field_observations"


def normalize_invalid_field_observations(value):
    normalized = {"location": [], "salary": []}
    if not isinstance(value, dict):
        return normalized
    for field in normalized:
        seen = set()
        observations = value.get(field, [])
        if not isinstance(observations, list):
            continue
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            raw_value = str(observation.get("value") or "").strip()
            platforms = tuple(sorted({str(item) for item in observation.get("platforms", []) if item}))
            if not raw_value:
                continue
            key = (raw_value, platforms)
            if key in seen:
                continue
            seen.add(key)
            normalized[field].append({"value": raw_value, "platforms": list(platforms)})
    return normalized


def merge_invalid_field_observations(jobs):
    merged = {"location": [], "salary": []}
    for job in jobs:
        observations = normalize_invalid_field_observations(job.get(INVALID_FIELD_OBSERVATIONS))
        for field in merged:
            merged[field].extend(observations[field])
    return normalize_invalid_field_observations(merged)


def sanitize_job_semantic_fields(job):
    """Clear invalid business fields while retaining platform-scoped audit evidence."""
    sanitized = dict(job)
    observations = normalize_invalid_field_observations(job.get(INVALID_FIELD_OBSERVATIONS))
    platforms = sorted(set(canonical_platforms(job)))
    for field, validator in (("location", is_valid_location), ("salary", is_valid_salary)):
        value = str(job.get(field) or "").strip()
        if value and not validator(value):
            observations[field].append({"value": value, "platforms": platforms})
            sanitized[field] = ""
    observations = normalize_invalid_field_observations(observations)
    if any(observations.values()):
        sanitized[INVALID_FIELD_OBSERVATIONS] = observations
    else:
        sanitized.pop(INVALID_FIELD_OBSERVATIONS, None)
    return sanitized


def _merge_job_group(group):
    """合并一组同岗记录：每个字段取组内首个非空值（url 优先带稳定ID的详情链）。"""
    group = [sanitize_job_semantic_fields(job) for job in group]
    main = dict(group[0])
    for field in ("title", "company", "salary", "location"):
        if not main.get(field):
            for j in group[1:]:
                if j.get(field):
                    main[field] = j[field]
                    break
    if not extract_stable_job_id(main.get("url", "")):
        for j in group[1:]:
            if extract_stable_job_id(j.get("url", "")):
                main["url"] = j["url"]
                break
        else:
            if not main.get("url"):
                for j in group[1:]:
                    if j.get("url"):
                        main["url"] = j["url"]
                        break
    platforms = set()
    keywords = set()
    urls = []
    for j in group:
        platforms.update(canonical_platforms(j))
        if j.get("keyword"):
            keywords.add(j.get("keyword"))
        if j.get("url"):
            urls.append(j.get("url"))
    main["platforms"] = sorted(p for p in platforms if p)
    main["keywords"] = sorted(keywords)
    main["urls"] = list(dict.fromkeys(urls))
    observations = merge_invalid_field_observations(group)
    if any(observations.values()):
        main[INVALID_FIELD_OBSERVATIONS] = observations
    else:
        main.pop(INVALID_FIELD_OBSERVATIONS, None)
    if len(platforms) > 1:
        main["platform"] = "/".join(sorted(platforms))
        main["cross_platform"] = True
    else:
        main["cross_platform"] = False
    return main


def deduplicate_jobs(jobs):
    """
    智能去重：同日内跨关键词、跨平台合并，两轮分组
    1. 稳定岗位ID预合并：同 host:id 必是同一岗位（同平台跨关键词）
    2. 文本合并：公司+归一化标题+城市；公司缺失时不做纯"标题+城市"合并
       （两家不同公司的同名岗会被误并），改用 平台+标题+城市+薪资 收窄键
    3. 字段取组内非空，合并来源平台列表
    """
    # 清洗必须早于URL/文本签名，避免字段噪声进入去重键和跨日状态。
    jobs = [sanitize_job_semantic_fields(job) for job in jobs]

    # 第一轮：稳定ID分组
    id_groups = {}
    no_id = []
    for job in jobs:
        url_id = extract_stable_job_id(job.get("url", ""))
        if url_id:
            id_groups.setdefault(url_id, []).append(job)
        else:
            no_id.append(job)
    stage1 = [_merge_job_group(g) for g in id_groups.values()] + no_id

    # 第二轮：文本分组（跨平台合并）
    groups = {}
    for job in stage1:
        key = make_job_signature(job, prefer_url=False)
        if not key:
            key = f"raw|{id(job)}"
        groups.setdefault(key, []).append(job)

    merged = [_merge_job_group(g) for g in groups.values()]

    dropped = len(jobs) - len(merged)
    print(f"  [去重] 原始 {len(jobs)} 个, 跨平台合并后 {len(merged)} 个 (合并了 {dropped} 个重复)")
    return merged


# ============================================================
# 跨日重复检测
# ============================================================

# 历史岗位签名文件（用于跨日重复检测）
JOB_SIGNATURE_FILE = os.path.join(REPORT_DIR, "job_signatures.json")
# 重复岗位保留天数（config: duplicate_retention_days）
DUP_RETENTION_DAYS = int(CONFIG.get("duplicate_retention_days", 30) or 30)



def _migrate_signature_key(sig):
    """旧签名格式迁移（2026-07-13 签名稳定化）：
    - url|<平台集合>|<host:id>  →  url|<host:id>
    - text|...|<地点-区县>      →  text|...|<城市>（末段地点去区县）
    """
    if sig.startswith("url|"):
        parts = sig.split("|")
        value = parts[2] if len(parts) == 3 else "|".join(parts[1:])
        value = re.sub(r"^www\.", "", value)
        return f"url|{value}"
    if sig.startswith("text|"):
        parts = sig.split("|")
        last = parts[-1].replace("·", "-")
        city = re.split(r"[-–—]", last)[0]
        if city:
            return "|".join(parts[:-1] + [city])
    return sig


def _parse_iso_date(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} 缺失")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"{field} 不是 ISO 日期: {value}") from e


def _reconstruct_seen_dates(first_seen, last_seen, times):
    """从旧 times 迁移出不重复日期，并把历史虚增次数封顶到自然日跨度。"""
    first = _parse_iso_date(first_seen, "first_seen")
    last = _parse_iso_date(last_seen, "last_seen")
    if first > last:
        raise ValueError("first_seen 晚于 last_seen")
    span = (last - first).days + 1
    count = min(max(int(times or 1), 1), span)
    if count == 1:
        return [last.isoformat()]
    dates = {first.isoformat(), last.isoformat()}
    cursor = last - datetime.timedelta(days=1)
    while len(dates) < count and cursor > first:
        dates.add(cursor.isoformat())
        cursor -= datetime.timedelta(days=1)
    return sorted(dates)


def _normalize_signature_info(info):
    if not isinstance(info, dict):
        raise ValueError("签名记录不是对象")
    first_seen = str(info.get("first_seen") or "")
    last_seen = str(info.get("last_seen") or "")
    first = _parse_iso_date(first_seen, "first_seen")
    last = _parse_iso_date(last_seen, "last_seen")
    if first > last:
        raise ValueError("first_seen 晚于 last_seen")

    raw_seen_dates = info.get("seen_dates")
    if raw_seen_dates is None:
        seen_dates = _reconstruct_seen_dates(first_seen, last_seen, info.get("times", 1))
    else:
        if not isinstance(raw_seen_dates, list):
            raise ValueError("seen_dates 不是数组")
        seen_dates = sorted({_parse_iso_date(str(value), "seen_dates").isoformat() for value in raw_seen_dates})
        seen_dates = sorted(set(seen_dates) | {first_seen, last_seen})

    last_salary = str(info.get("last_salary") or "").strip()
    last_location = str(info.get("last_location") or "").strip()
    if last_salary and not is_valid_salary(last_salary):
        last_salary = ""
    if last_location and not is_valid_location(last_location):
        last_location = ""

    normalized = dict(info)
    normalized.update({
        "first_seen": first_seen,
        "last_seen": last_seen,
        "seen_dates": seen_dates,
        "times": len(seen_dates),
        "last_salary": last_salary,
        "last_location": last_location,
    })
    return normalized


def _read_signature_store(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("顶层不是对象")
    _parse_iso_date(str(data.get("updated") or ""), "updated")
    raw = data.get("signatures")
    if not isinstance(raw, dict):
        raise ValueError("signatures 不是对象")
    if data.get("total") != len(raw):
        raise ValueError(f"total={data.get('total')} 与实际 {len(raw)} 不一致")
    normalized = {}
    for sig, info in raw.items():
        if not isinstance(sig, str) or not sig:
            raise ValueError("存在空签名键")
        normalized[sig] = _normalize_signature_info(info)
    return data, normalized


def _merge_signature_info(existing, incoming):
    existing = _normalize_signature_info(existing)
    incoming = _normalize_signature_info(incoming)
    existing_last = existing["last_seen"]
    incoming_last = incoming["last_seen"]
    latest, older = (incoming, existing) if incoming_last >= existing_last else (existing, incoming)
    seen_dates = sorted(set(existing["seen_dates"]) | set(incoming["seen_dates"]))
    return {
        "first_seen": min(existing["first_seen"], incoming["first_seen"]),
        "last_seen": max(existing_last, incoming_last),
        "seen_dates": seen_dates,
        "times": len(seen_dates),
        "last_salary": latest.get("last_salary") or older.get("last_salary", ""),
        "last_location": latest.get("last_location") or older.get("last_location", ""),
    }


def load_previous_signatures(path=JOB_SIGNATURE_FILE):
    """严格加载签名库；主库损坏仅回退已验证备份，主备均坏则停止发布。"""
    backup_path = path + ".bak"
    if not os.path.exists(path) and not os.path.exists(backup_path):
        return {}

    errors = []
    raw = None
    source_path = ""
    for candidate in (path, backup_path):
        if not os.path.exists(candidate):
            continue
        try:
            _, raw = _read_signature_store(candidate)
            source_path = candidate
            break
        except Exception as e:
            errors.append(f"{os.path.basename(candidate)}: {e}")
    if raw is None:
        raise SignatureStoreError("；".join(errors) or "签名主库和备份均不可用")
    if source_path == backup_path:
        detail = "；".join(errors)[:160]
        print(f"  [SIG] 主库损坏，已回退验证通过的备份: {detail}")
        record_quality_event(
            "签名库", "", "signature_backup_recovered", os.path.basename(backup_path), None,
            "主库损坏，本次使用已验证备份；保存时会重建主库",
        )

    migrated = {}
    changed = 0
    for sig, info in raw.items():
        new_sig = _migrate_signature_key(sig)
        if new_sig != sig:
            changed += 1
        if new_sig in migrated:
            migrated[new_sig] = _merge_signature_info(migrated[new_sig], info)
        else:
            migrated[new_sig] = dict(info)
    if changed:
        print(f"  [SIG] 旧签名格式迁移: {changed} 条键已更新（url去平台/www、地点归一城市）")
    return migrated


def save_signatures(signatures, today_str, path=JOB_SIGNATURE_FILE):
    """带验证备份、原子写和写后回读地保存签名库。"""
    today = _parse_iso_date(today_str, "today_str")
    cutoff = today - datetime.timedelta(days=DUP_RETENTION_DAYS)
    cutoff_str = cutoff.isoformat()
    cleaned = {}
    for sig, info in signatures.items():
        normalized = _normalize_signature_info(info)
        if normalized.get("last_seen", "") >= cutoff_str:
            cleaned[sig] = normalized
    data = {
        "updated": today_str,
        "retention_days": DUP_RETENTION_DAYS,
        "signatures": cleaned,
        "total": len(cleaned),
    }
    backup_path = path + ".bak"
    if os.path.exists(path):
        try:
            _read_signature_store(path)
        except Exception:
            # 主库已坏时保留原字节作为取证，且绝不覆盖已验证的 .bak。
            if not os.path.exists(backup_path):
                raise SignatureStoreError("签名主库损坏且无有效备份，拒绝覆盖")
            _read_signature_store(backup_path)
            corrupt_path = f"{path}.corrupt.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy2(path, corrupt_path)
            os.chmod(corrupt_path, 0o600)
        else:
            shutil.copy2(path, backup_path)
            os.chmod(backup_path, 0o600)
    try:
        atomic_write_json(path, data)
        written, normalized_written = _read_signature_store(path)
        if written.get("total") != len(cleaned) or set(normalized_written) != set(cleaned):
            raise ValueError("写后回读内容不一致")
    except Exception as e:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, path)
            os.chmod(path, 0o600)
        raise SignatureStoreError(f"签名库写入或回读校验失败: {e}") from e
    print(f"  [SIG] 已保存 {len(cleaned)} 条岗位签名 (保留{DUP_RETENTION_DAYS}天)")


def categorize_jobs(jobs, today_str, previous_signatures=None):
    """
    跨日检测：将岗位分为三类
    - new_jobs: 首次出现
    - updated_jobs: 之前出现过但薪资/地点变了
    - repeated_jobs: 持续在招的（信息无变化）

    返回: (new_jobs, updated_jobs, repeated_jobs, updated_signatures)
    """
    sigs = load_previous_signatures() if previous_signatures is None else previous_signatures
    new_sigs = {}
    for sig, info in sigs.items():
        normalized = _normalize_signature_info(info)
        normalized["seen_dates"] = list(normalized["seen_dates"])
        new_sigs[sig] = normalized

    new_jobs = []
    updated_jobs = []
    repeated_jobs = []

    for job in jobs:
        sig = make_job_signature(job)

        if not sig or sig in {"|", "text|"}:
            # 签名为空的岗位恒判新增，且不写库（空串键会互相覆盖污染签名库）
            job["_category"] = "new"
            new_jobs.append(job)
            continue

        if sig in new_sigs:
            info = new_sigs[sig]
            first_seen = info.get("first_seen", today_str)
            old_salary = info.get("last_salary", "")
            old_location = info.get("last_location", "")
            cur_salary = job.get("salary", "")
            cur_location = job.get("location", "")

            seen_dates = set(info.get("seen_dates", []))
            seen_dates.add(today_str)
            times = len(seen_dates)
            salary_changed = bool(cur_salary) and bool(old_salary) and cur_salary.strip() != old_salary.strip()
            location_changed = bool(cur_location) and bool(old_location) and cur_location.strip() != old_location.strip()
            salary_enriched = bool(cur_salary) and not bool(old_salary)
            location_enriched = bool(cur_location) and not bool(old_location)

            if salary_changed or location_changed or salary_enriched or location_enriched:
                change_parts = []
                if salary_changed:
                    change_parts.append(f"薪资: {old_salary} -> {cur_salary}")
                elif salary_enriched:
                    change_parts.append(f"薪资补全: {cur_salary}")
                if location_changed:
                    change_parts.append(f"地点: {old_location} -> {cur_location}")
                elif location_enriched:
                    change_parts.append(f"地点补全: {cur_location}")
                job["_category"] = "updated"
                job["_update_info"] = ", ".join(change_parts)
                updated_jobs.append(job)
            else:
                job["_category"] = "repeated"
                job["_repeat_info"] = f"首次出现: {first_seen}, 累计{times}天"
                repeated_jobs.append(job)
            if cur_salary:
                info["last_salary"] = cur_salary
            if cur_location:
                info["last_location"] = cur_location
            info["last_seen"] = today_str
            info["seen_dates"] = sorted(seen_dates)
            info["times"] = times
        else:
            job["_category"] = "new"
            new_jobs.append(job)
            new_sigs[sig] = {
                "first_seen": today_str, "last_seen": today_str, "times": 1,
                "seen_dates": [today_str],
                "last_salary": job.get("salary", ""), "last_location": job.get("location", ""),
            }

    print(f"  [分类] 新增 {len(new_jobs)}, 更新 {len(updated_jobs)}, 持续在招 {len(repeated_jobs)}")
    return new_jobs, updated_jobs, repeated_jobs, new_sigs



def validate_crawl_results(raw_counts, max_failed_rate=None):
    """拒绝不可信零结果、整个平台失守或失败组合比例过高的降级日报。"""
    has_failure = any(count == -1 for count in raw_counts.values())
    has_jobs = any(count > 0 for count in raw_counts.values())
    if raw_counts and has_failure and not has_jobs:
        raise CrawlFetchError(
            f"{len(raw_counts)} 组平台×关键词中存在抓取失败且无任何正数结果，"
            f"疑似 agent-browser 运行时不可用、网络中断、被反爬拦截或页面不可识别；"
            f"拒绝以 0 岗位成功日报收尾"
        )
    if not has_failure:
        return

    failed = sum(1 for count in raw_counts.values() if count == -1)
    max_failed_rate = MAX_FAILED_COMBINATION_RATE if max_failed_rate is None else max_failed_rate
    failure_rate = failed / len(raw_counts)
    if failure_rate >= max_failed_rate:
        raise CrawlFetchError(
            f"抓取失败组合 {failed}/{len(raw_counts)} ({failure_rate:.0%}) "
            f"达到门禁 {max_failed_rate:.0%}，拒绝发布不完整日报"
        )

    for platform in configured_platform_names():
        values = [
            raw_counts.get(f"{platform}|{keyword}")
            for keyword in KEYWORDS
            if f"{platform}|{keyword}" in raw_counts
        ]
        if len(values) == len(KEYWORDS) and values and all(value == -1 for value in values):
            raise CrawlFetchError(f"{platform} 的全部 {len(KEYWORDS)} 个关键词均抓取失败，拒绝发布")


def crawl_all(platform_crawlers=None, keywords=None, pause_seconds=1.5):
    """爬取所有平台所有关键词，返回 (去重后岗位, 平台×关键词原始计数)"""
    all_jobs = []
    raw_counts = {}
    active_crawlers = PLATFORM_CRAWLERS if platform_crawlers is None else platform_crawlers
    active_keywords = KEYWORDS if keywords is None else keywords

    for keyword in active_keywords:
        print(f"\n{'='*60}")
        print(f"  关键词: 「{keyword}」")
        print(f"{'='*60}")

        for name, crawler in active_crawlers:
            try:
                print(f"\n  --- {name} ---")
                jobs = crawler(keyword)
                all_jobs.extend(jobs)
                raw_counts[f"{name}|{keyword}"] = len(jobs)
            except CrawlFetchError as e:
                print(f"  [ERROR] {name}: {e}", file=sys.stderr)
                raw_counts[f"{name}|{keyword}"] = -1  # -1 表示该组合抛异常
                record_quality_event(
                    name,
                    keyword,
                    "crawl_failed",
                    type(e).__name__,
                    None,
                    str(e)[:200],
                )
            # 平台间暂停，防止被封
            if pause_seconds:
                time.sleep(pause_seconds)

    unique_jobs = deduplicate_jobs(all_jobs)
    print(f"\n\n{'*'*60}")
    print(f"  爬取完毕: 原始 {len(all_jobs)} 个, 去重后 {len(unique_jobs)} 个")
    print(f"{'*'*60}")
    return unique_jobs, raw_counts


HISTORY_FILE = os.path.join(REPORT_DIR, "job_crawler_history.jsonl")
PUBLISH_RECEIPT_FILE = os.path.join(REPORT_DIR, "job_crawler_publish_state.json")


def atomic_write_json(path, data):
    """以 0600 权限原子写 JSON，避免状态半写。"""
    tmp_path = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def load_publish_receipt(path=PUBLISH_RECEIPT_FILE):
    """加载最新发布收据；损坏时 fail closed，避免重复投递。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            receipt = json.load(f)
    except Exception as e:
        raise PublishError(f"发布收据损坏，拒绝继续以免重复投递: {e}") from e
    if not isinstance(receipt, dict):
        raise PublishError("发布收据顶层不是对象，拒绝继续以免重复投递")
    return receipt


def write_publish_receipt(receipt, path=PUBLISH_RECEIPT_FILE):
    atomic_write_json(path, receipt)


def read_history_entries(path=HISTORY_FILE):
    """严格读取 JSONL 历史；任何损坏行都拒绝静默覆盖。"""
    if not os.path.exists(path):
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                entry = json.loads(line)
                if not isinstance(entry, dict) or not entry.get("date"):
                    raise ValueError(f"第{line_no}行缺少 date")
                entries.append(entry)
    except Exception as e:
        raise HistoryStoreError(f"发布历史损坏: {e}") from e
    return entries


def published_history_entry(today_str, path=HISTORY_FILE):
    """返回今日成功历史；兼容旧记录以非空 docx_url 作为成功证据。"""
    matches = [entry for entry in read_history_entries(path) if entry.get("date") == today_str]
    for entry in reversed(matches):
        if entry.get("status") == "published":
            return entry
        if not entry.get("status") and entry.get("docx_url"):
            return entry
    return None


def publication_guard(today_str, force=False, receipt_path=PUBLISH_RECEIPT_FILE, history_path=HISTORY_FILE):
    """返回 proceed/skip/block，阻止同日重复群消息。"""
    if force:
        return "proceed", {}
    receipt = load_publish_receipt(receipt_path)
    if receipt.get("date") == today_str:
        status = receipt.get("status")
        if status == "published" and receipt.get("message_id"):
            return "skip", receipt
        # message_id 是外部副作用已发生的硬证据。即使进程在收尾前被
        # SIGKILL/断电，也必须阻断自动重发；终态却缺回执同样失败关闭。
        if receipt.get("message_id") or status in {
            "published", "delivered", "delivered_degraded"
        }:
            return "block", receipt
    history_entry = published_history_entry(today_str, history_path)
    if history_entry:
        return "skip", history_entry
    return "proceed", receipt


def append_history(today_str, raw_counts, report, receipt, path=HISTORY_FILE):
    """原子 upsert 当日成功历史；写失败必须使发布状态降级。"""
    entry = {
        "date": today_str,
        "status": "published",
        "total": report.get("total", 0),
        "new": report.get("total_new", 0),
        "updated": report.get("total_updated", 0),
        "repeated": report.get("total_repeated", 0),
        "raw_counts": raw_counts,
        "warnings": [
            {"platform": w.get("platform", ""), "keyword": w.get("keyword", ""),
             "metric": w.get("metric", ""), "value": w.get("value", "")}
            for w in report.get("quality", {}).get("warnings", [])
        ],
        "info": [
            {"platform": event.get("platform", ""), "keyword": event.get("keyword", ""),
             "metric": event.get("metric", ""), "value": event.get("value", "")}
            for event in report.get("quality", {}).get("info", [])
        ],
        "docx_url": receipt.get("docx_url", ""),
        "docx_id": receipt.get("docx_id", ""),
        "message_id": receipt.get("message_id", ""),
        "permissions": receipt.get("permissions", {}),
        "run_id": receipt.get("run_id", ""),
    }
    try:
        entries = [existing for existing in read_history_entries(path) if existing.get("date") != today_str]
        entries.append(entry)
        tmp_path = f"{path}.tmp.{os.getpid()}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                for existing in entries:
                    f.write(json.dumps(existing, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
        print(f"  [HISTORY] 已记录当日成功历史: {path}")
    except Exception as e:
        if isinstance(e, HistoryStoreError):
            raise
        raise HistoryStoreError(f"写入发布历史失败: {e}") from e


# 信息型指标：平台真实无此类岗、无代码可修，不触发 Runbook 修复线
# （须与 job_crawler_watchdog.py 的 NON_ESCALATING_METRICS 保持一致）
INFORMATIONAL_METRICS = {"no_relevant_jobs", "possible_truncation"}


def annotate_warning_streaks(warnings, today_str):
    """给告警标注连续天数（读历史JSONL往前连续追溯），≥3天显式标注达修复触发线。"""
    if not warnings or not os.path.exists(HISTORY_FILE):
        return warnings
    history = {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                d = e.get("date", "")
                if d and d < today_str:
                    history[d] = {
                        (w.get("platform", ""), w.get("keyword", ""), w.get("metric", ""))
                        for w in e.get("warnings", [])
                    }
    except OSError:
        return warnings
    if not history:
        return warnings
    for w in warnings:
        key = (w.get("platform", ""), w.get("keyword", ""), w.get("metric", ""))
        streak = 1
        try:
            day = datetime.date.fromisoformat(today_str)
        except ValueError:
            break
        while True:
            day = day - datetime.timedelta(days=1)
            keys = history.get(day.isoformat())
            if keys is None or key not in keys:
                break
            streak += 1
        if streak >= 3:
            if w.get("metric") in INFORMATIONAL_METRICS:
                w["detail"] = (w.get("detail", "") + f"（已连续{streak}天；信息型指标，不触发修复）").strip()
            else:
                w["detail"] = (w.get("detail", "") + f"（⚠️已连续{streak}天，达Runbook修复触发线，请召唤修复会话）").strip()
        elif streak > 1:
            w["detail"] = (w.get("detail", "") + f"（已连续{streak}天）").strip()
    return warnings


def is_valid_location(value):
    value = str(value or "").strip()
    if not value:
        return False
    if len(value) > 40 or re.search(r"(接受|小白|经验|学历|招聘|五险|双休|薪资|面议|食宿|住宿)", value):
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9\-·/（）()]+", value))


def is_valid_salary(value):
    value = str(value or "").strip()
    if not value:
        return False
    if value == "面议":
        return True
    return bool(re.search(r"\d", value) and re.search(r"(?:[kK]|千|万|元|薪)", value))


def invalid_field_observations_for(job, field, platform):
    observations = normalize_invalid_field_observations(
        job.get(INVALID_FIELD_OBSERVATIONS)
    ).get(field, [])
    return [
        observation for observation in observations
        if not observation.get("platforms") or platform in observation.get("platforms", [])
    ]


def add_quality_samples(target, observations):
    for observation in observations:
        value = str(observation.get("value") or "")[:40]
        if value and value not in target and len(target) < 3:
            target.append(value)


def is_actionable_job_url(url):
    url = str(url or "")
    if extract_stable_job_id(url):
        return True
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower().endswith("iguopin.com") and parsed.path == "/company" and bool(
        urllib.parse.parse_qs(parsed.query).get("id")
    )


def quality_threshold_for(platform, key, default):
    platform_values = QUALITY_THRESHOLDS.get("platforms", {}).get(platform, {})
    return platform_values.get(key, QUALITY_THRESHOLDS.get(key, default))


def detect_volume_drops(raw_counts, history_entries, today_str=""):
    """用最近14条成功历史的中位数识别平台×关键词突降。"""
    events = []
    history_entries = [
        entry for entry in history_entries
        if not today_str or entry.get("date") != today_str
    ][-14:]
    for key, current in raw_counts.items():
        if current < 0:
            continue
        samples = []
        for entry in history_entries:
            value = (entry.get("raw_counts") or {}).get(key)
            if isinstance(value, int) and value >= 0:
                samples.append(value)
        if len(samples) < 3:
            continue
        baseline = statistics.median(samples)
        if baseline >= 5 and current < baseline * VOLUME_DROP_RATIO:
            platform, keyword = key.split("|", 1)
            events.append({
                "platform": platform,
                "keyword": keyword,
                "metric": "volume_drop",
                "value": current,
                "threshold": round(baseline * VOLUME_DROP_RATIO, 2),
                "detail": f"当前 {current}，最近{len(samples)}次中位数 {baseline:g}，下降超过 {1 - VOLUME_DROP_RATIO:.0%}",
            })
    return events


def analyze_quality(jobs, raw_counts=None, today_str="", history_entries=None):
    """汇总字段语义、可行动链接、覆盖事件和滚动突降。"""
    platform_names = configured_platform_names()

    def new_stats():
        return {
            "total": 0,
            "missing_company": 0,
            "missing_salary": 0,
            "missing_location": 0,
            "missing_url": 0,
            "invalid_location": 0,
            "invalid_salary": 0,
            "search_fallback_url": 0,
            "actionable_url": 0,
            "invalid_location_samples": [],
            "invalid_salary_samples": [],
        }

    by_platform = {name: new_stats() for name in platform_names}
    for job in jobs:
        platforms = canonical_platforms(job) or ["未知"]
        for platform in platforms:
            stats = by_platform.setdefault(platform, new_stats())
            stats["total"] += 1
            if not job.get("company"):
                stats["missing_company"] += 1
            salary_observations = invalid_field_observations_for(job, "salary", platform)
            if salary_observations:
                stats["invalid_salary"] += 1
                add_quality_samples(stats["invalid_salary_samples"], salary_observations)
            elif not job.get("salary"):
                stats["missing_salary"] += 1
            elif not is_valid_salary(job.get("salary")):
                stats["invalid_salary"] += 1
                if len(stats["invalid_salary_samples"]) < 3:
                    stats["invalid_salary_samples"].append(str(job.get("salary"))[:40])
            location_observations = invalid_field_observations_for(job, "location", platform)
            if location_observations:
                stats["invalid_location"] += 1
                add_quality_samples(stats["invalid_location_samples"], location_observations)
            elif not job.get("location"):
                stats["missing_location"] += 1
            elif not is_valid_location(job.get("location")):
                stats["invalid_location"] += 1
                if len(stats["invalid_location_samples"]) < 3:
                    stats["invalid_location_samples"].append(str(job.get("location"))[:40])
            if not job.get("url"):
                stats["missing_url"] += 1
            elif is_actionable_job_url(job.get("url")):
                stats["actionable_url"] += 1
            else:
                stats["search_fallback_url"] += 1

    events = list(QUALITY_EVENTS)
    if raw_counts:
        if history_entries is None:
            history_entries = read_history_entries(HISTORY_FILE)
        events.extend(detect_volume_drops(raw_counts, history_entries, today_str=today_str))
    info = [event for event in events if event.get("metric") in INFORMATIONAL_METRICS]
    warnings = [event for event in events if event.get("metric") not in INFORMATIONAL_METRICS]

    for platform, stats in by_platform.items():
        total = stats["total"]
        if not total:
            warnings.append({
                "platform": platform,
                "keyword": "",
                "metric": "platform_total",
                "value": 0,
                "threshold": None,
                "detail": "平台无采集结果",
            })
            continue
        rates = {
            "missing_company_rate": stats["missing_company"] / total,
            "missing_salary_rate": stats["missing_salary"] / total,
            "missing_location_rate": stats["missing_location"] / total,
            "missing_url_rate": stats["missing_url"] / total,
            "invalid_location_rate": stats["invalid_location"] / total,
            "invalid_salary_rate": stats["invalid_salary"] / total,
            "search_fallback_url_rate": stats["search_fallback_url"] / total,
            "actionable_url_rate": stats["actionable_url"] / total,
        }
        stats.update({k: round(v, 4) for k, v in rates.items()})
        threshold_specs = (
            ("missing_company_rate", "max_missing_company_rate", 1, "公司缺失率过高"),
            ("missing_salary_rate", "max_missing_salary_rate", 1, "薪资缺失率过高"),
            ("missing_location_rate", "max_missing_location_rate", 1, "地点缺失率过高"),
            ("missing_url_rate", "max_missing_url_rate", 1, "链接缺失率过高"),
            ("invalid_location_rate", "max_invalid_location_rate", 0, "地点字段存在语义异常"),
            ("invalid_salary_rate", "max_invalid_salary_rate", 0, "薪资字段存在语义异常"),
        )
        for metric, threshold_key, default, detail in threshold_specs:
            threshold = quality_threshold_for(platform, threshold_key, default)
            if rates[metric] > threshold:
                critical_threshold = quality_threshold_for(
                    platform, f"critical_{metric}", 2
                )
                warnings.append({
                    "platform": platform,
                    "keyword": "",
                    "metric": metric,
                    "value": round(rates[metric], 4),
                    "threshold": threshold,
                    "severity": "critical" if rates[metric] >= critical_threshold else "warning",
                    "detail": detail,
                })
        min_actionable = quality_threshold_for(platform, "min_actionable_url_rate", 0.75)
        if rates["actionable_url_rate"] < min_actionable:
            warnings.append({
                "platform": platform,
                "keyword": "",
                "metric": "actionable_url_rate",
                "value": round(rates["actionable_url_rate"], 4),
                "threshold": min_actionable,
                "detail": "可直接打开岗位/公司页面的链接比例过低；搜索页兜底不计为可行动链接",
            })

    print("  [QUALITY] 数据质量摘要")
    for platform, stats in by_platform.items():
        total = stats["total"]
        if total:
            print(
                f"    {platform}: total={total}, "
                f"company_missing={stats['missing_company']}/{total}, "
                f"salary_missing={stats['missing_salary']}/{total}, "
                f"location_missing={stats['missing_location']}/{total}, "
                f"url_actionable={stats['actionable_url']}/{total}"
            )
        else:
            print(f"    {platform}: total=0")
    if warnings:
        print(f"  [QUALITY] 发现 {len(warnings)} 个质量提醒")
    if info:
        print(f"  [QUALITY] 记录 {len(info)} 条覆盖说明")
    return {"platforms": by_platform, "warnings": warnings, "info": info}


# ============================================================
# 报告生成与保存
# ============================================================

def build_report(new_jobs, updated_jobs, repeated_jobs, today_str, quality=None):
    """构建标准 JSON 报告，含分类信息"""
    def public_job(job):
        cleaned = dict(job)
        cleaned.pop(INVALID_FIELD_OBSERVATIONS, None)
        for field in (
            "title", "company", "salary", "location", "keyword",
            "_update_info", "_repeat_info",
        ):
            if field in cleaned:
                cleaned[field] = clean_external_text(cleaned[field])
        if isinstance(cleaned.get("keywords"), list):
            cleaned["keywords"] = [
                clean_external_text(keyword)
                for keyword in cleaned["keywords"]
                if clean_external_text(keyword)
            ]
        platforms = canonical_platforms(cleaned)
        cleaned["url"] = allowed_publish_url(cleaned.get("url", ""), platforms)
        if isinstance(cleaned.get("urls"), list):
            cleaned["urls"] = list(dict.fromkeys(
                safe_url
                for raw_url in cleaned["urls"]
                if (safe_url := allowed_publish_url(raw_url, platforms))
            ))
        tier, reason = classify_job_relevance(cleaned)
        cleaned["relevance_tier"] = tier
        cleaned["relevance_reason"] = reason
        return cleaned

    new_jobs = [public_job(job) for job in new_jobs]
    updated_jobs = [public_job(job) for job in updated_jobs]
    repeated_jobs = [public_job(job) for job in repeated_jobs]
    all_jobs = new_jobs + updated_jobs + repeated_jobs
    platform_names = configured_platform_names()
    platform_jobs = {name: [] for name in platform_names}
    relevance_counts = {"core": 0, "industry": 0, "weak": 0, "irrelevant": 0}
    for job in all_jobs:
        relevance_counts[job["relevance_tier"]] += 1
        for p in canonical_platforms(job):
            if p in platform_jobs:
                platform_jobs[p].append(job)

    report = {
        "date": today_str,
        "total": len(all_jobs),
        "total_new": len(new_jobs),
        "total_updated": len(updated_jobs),
        "total_repeated": len(repeated_jobs),
        "platforms": platform_jobs,
        "new_jobs": new_jobs,
        "updated_jobs": updated_jobs,
        "repeated_jobs": repeated_jobs,
        "jobs": all_jobs,
        "relevance": relevance_counts,
        "quality": quality or {"platforms": {}, "warnings": []},
    }
    return report


def report_fingerprint(report):
    """稳定指纹用于同日失败恢复时复用已经创建的文档。"""
    stable_report = dict(report)
    quality = report.get("quality")
    if isinstance(quality, dict):
        stable_quality = dict(quality)
        platforms = quality.get("platforms")
        if isinstance(platforms, dict):
            stable_quality["platforms"] = {
                platform: {
                    key: value
                    for key, value in stats.items()
                    if key not in {"invalid_location_samples", "invalid_salary_samples"}
                }
                if isinstance(stats, dict) else stats
                for platform, stats in platforms.items()
            }
        stable_report["quality"] = stable_quality
    payload = json.dumps(stable_report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ============================================================
# 格式化输出
# ============================================================

def build_reference_summary(report):
    """构建参考格式的摘要数据"""
    total_by_kw = {}
    total_by_platform = {}
    for j in report["jobs"]:
        kws = j.get("keywords") or [j.get("keyword", "")]
        for kw in kws:
            if kw:
                total_by_kw[kw] = total_by_kw.get(kw, 0) + 1
        for p in canonical_platforms(j):
            total_by_platform[p] = total_by_platform.get(p, 0) + 1

    kw_str = "、".join(f"{k}:{v}" for k, v in sorted(total_by_kw.items()))
    plat_str = "、".join(f"{p}:{v}" for p, v in sorted(total_by_platform.items(), key=lambda x: -x[1]))
    return kw_str, plat_str, total_by_kw, total_by_platform


def build_docx_markdown(report, today_str):
    """生成适合飞书文档的 Markdown 内容（新增/更新/持续在招三段式）"""
    kw_str, plat_str, total_by_kw, total_by_platform = build_reference_summary(report)
    new_jobs = report.get("new_jobs", [])
    updated_jobs = report.get("updated_jobs", [])
    repeated_jobs = report.get("repeated_jobs", [])

    lines = []
    lines.append(f"# 招聘岗位日报｜无人机/CAAC @ 全国 ({today_str})")
    lines.append("")
    lines.append(f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # 第1节：今日结论
    lines.append("## 1. 今日结论")
    lines.append("")
    lines.append(f"本次全平台采集 {len(KEYWORDS)} 个关键词，共获得 **{report['total']}** 条岗位信息。")
    lines.append(f"关键词贡献（非互斥，合计可大于唯一岗位数）：{kw_str}。")
    lines.append(f"平台贡献（非互斥，跨平台岗位会分别计入）：{plat_str}。")
    relevance = report.get("relevance", {})
    lines.append(
        "相关性分层："
        f"核心岗位 {relevance.get('core', 0)}；"
        f"泛低空产业岗 {relevance.get('industry', 0)}；"
        f"弱相关待复核 {relevance.get('weak', 0)}。"
    )
    if new_jobs:
        lines.append(f"**新增岗位：{len(new_jobs)} 个**（今日首次出现）")
    if updated_jobs:
        lines.append(f"**更新岗位：{len(updated_jobs)} 个**（薪资/地点有变化）")
    if repeated_jobs:
        lines.append(f"**持续在招：{len(repeated_jobs)} 个**（往期已出现过，信息无变化）")
    lines.append("")

    # 第2节：各平台采集详情
    lines.append("## 2. 各平台采集详情")
    lines.append("")
    for platform_name in configured_platform_names():
        jobs = report["platforms"].get(platform_name, [])
        count = len(jobs)
        if count > 0:
            lines.append(f"- **{platform_name}**：{count}条")
        else:
            lines.append(f"- **{platform_name}**：暂无结果")
    lines.append("")

    quality = report.get("quality", {})
    q_platforms = quality.get("platforms", {})
    q_warnings = quality.get("warnings", [])
    q_info = quality.get("info", [])
    lines.append("## 3. 数据质量")
    lines.append("")
    if q_platforms:
        for platform_name in configured_platform_names():
            stats = q_platforms.get(platform_name)
            if not stats:
                continue
            total = stats.get("total", 0)
            if total:
                lines.append(
                    f"- **{platform_name}**：{total}条；公司缺失 {stats.get('missing_company', 0)}；"
                    f"薪资缺失 {stats.get('missing_salary', 0)}；地点缺失 {stats.get('missing_location', 0)}；"
                    f"可行动链接 {stats.get('actionable_url', 0)}"
                )
            else:
                lines.append(f"- **{platform_name}**：无采集结果")
    if q_warnings:
        lines.append("")
        lines.append("质量提醒：")
        for event in q_warnings[:12]:
            platform = event.get("platform", "")
            keyword = event.get("keyword", "")
            metric = event.get("metric", "")
            value = event.get("value", "")
            detail = event.get("detail", "")
            kw_part = f" / {keyword}" if keyword else ""
            lines.append(f"- {platform}{kw_part}：{metric}={value}，{detail}")
        if len(q_warnings) > 12:
            lines.append(f"- 另有 {len(q_warnings) - 12} 条质量提醒，详见运行日志。")
    else:
        lines.append("本次未触发质量阈值告警。")
    if q_info:
        lines.append("")
        lines.append("覆盖说明：")
        for event in q_info:
            keyword = f" / {event.get('keyword')}" if event.get("keyword") else ""
            lines.append(
                f"- {event.get('platform', '')}{keyword}："
                f"{event.get('metric', '')}={event.get('value', '')}，{event.get('detail', '')}"
            )
    lines.append("")

    # 第3节：新增岗位（首次出现）
    if new_jobs:
        lines.append("## 4. 新增岗位（今日首次出现）")
        lines.append("")
        for idx, j in enumerate(new_jobs, 1):
            lines.append(_format_job_line(j, idx))
        lines.append("")

    # 第4节：更新岗位（薪资/地点有变动）
    if updated_jobs:
        lines.append("## 5. 更新岗位（薪资/地点变化）")
        lines.append("")
        for idx, j in enumerate(updated_jobs, 1):
            base = _format_job_line(j, idx, show_update=True)
            lines.append(base)
        lines.append("")

    # 第5节：持续在招（紧凑但可行动）
    if repeated_jobs:
        lines.append("## 6. 持续在招（往期已出现）")
        lines.append("")
        lines.append(
            f"以下岗位在往期日报中已出现过，信息无变化；展示地点、薪资、来源和可点击链接。"
        )
        lines.append("")
        visible_repeated = repeated_jobs if REPEATED_DETAIL_LIMIT <= 0 else repeated_jobs[:REPEATED_DETAIL_LIMIT]
        for idx, job in enumerate(visible_repeated, 1):
            lines.append(_format_job_line(job, idx))
        if len(visible_repeated) < len(repeated_jobs):
            lines.append(
                f"- 其余 {len(repeated_jobs) - len(visible_repeated)} 个持续岗位已折叠；"
                f"本节仅保留前 {len(visible_repeated)} 个可行动条目。"
            )
        lines.append("")

    # 最后一节：说明
    lines.append("## 7. 说明")
    lines.append("")
    lines.append("本报告由自动化爬虫采集生成，覆盖猎聘、前程无忧、国聘、智联招聘四个平台。")
    lines.append("新增/更新/持续在招通过标题+公司归一化签名比对最近30天历史数据自动识别。")
    lines.append('跨平台同岗位已合并显示（如\"猎聘/前程无忧\"）。')
    lines.append("")

    return "\n".join(lines)


def _format_job_line(job, idx, show_update=False):
    """格式化单条岗位输出行"""
    title = escape_markdown_text(job.get("title", ""))
    company = escape_markdown_text(job.get("company") or "公司待解析")
    location = escape_markdown_text(job.get("location") or "地点待解析")
    salary = escape_markdown_text(job.get("salary") or "薪资面议")
    platform = escape_markdown_text(job.get("platform", ""))
    url = allowed_publish_url(job.get("url", ""), canonical_platforms(job))
    cross = job.get("cross_platform", False)

    parts = [f"{idx}. **{title}**"]
    parts.append(f"{company}")
    parts.append(f"{location}")
    parts.append(f"{salary}")
    parts.append(f"来源：{platform}")
    if cross:
        parts.append("(跨平台)")
    if show_update and job.get("_update_info"):
        parts.append(f"[{escape_markdown_text(job['_update_info'])}]")
    if url:
        # 国聘岗位无独立详情URL，链接指向该岗公司页——文案如实标注，避免"查看详情"落到公司主页的误导
        label = "查看公司页" if (platform == "国聘" and "/company?id=" in url) else "查看详情"
        parts.append(f"[{label}]({url})")
    return " | ".join(parts)


def mask_identifier(value):
    value = str(value or "")
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def redact_sensitive_text(value):
    """日志错误只保留诊断语义，不泄露文档、群或人员标识。"""
    text = str(value or "")
    text = re.sub(r"https?://\S+", "[URL_REDACTED]", text)
    text = re.sub(r"\b(?:ou|oc|om|on|cli)_[A-Za-z0-9_-]+", "[ID_REDACTED]", text)
    text = re.sub(
        r"(?i)([\"']?[a-z0-9_-]*(?:token|secret|password|api[_-]?key|open[_-]?id|"
        r"chat[_-]?id|user[_-]?id|message[_-]?id|document[_-]?id|docx?[_-]?id|"
        r"file[_-]?id|folder[_-]?id)[a-z0-9_-]*[\"']?\s*[:=]\s*[\"']?)"
        r"[^\"'\s,}\]]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(\b(?:authorization|bearer)\b\s*[:=]?\s*)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        text,
    )
    return text


def local_lark_file_reference(filepath):
    """返回 lark-cli 本地文件参数所需的 cwd 和安全相对文件名。"""
    absolute = os.path.abspath(filepath)
    return os.path.dirname(absolute), os.path.basename(absolute)


def find_nested_value(data, keys):
    """在 CLI JSON 响应中递归查找首个目标键。"""
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if value:
                return value
        for value in data.values():
            found = find_nested_value(value, keys)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_nested_value(value, keys)
            if found:
                return found
    return ""



def create_feishu_report_docx(report, today_str):
    """创建飞书日报文档；模糊失败不自动重试，避免生成重复孤儿文档。"""
    print(f"\n📝 创建飞书日报文档...")

    md_content = build_docx_markdown(report, today_str)

    # lark-cli 的 @file 不接受绝对路径；在报告目录中执行并仅传文件名。
    tmp_name = f"_job_report_{today_str}.md"
    tmp_abs = os.path.join(REPORT_DIR, f"_job_report_{today_str}.md")
    command_cwd, tmp_name = local_lark_file_reference(tmp_abs)
    with open(tmp_abs, "w", encoding="utf-8") as f:
        f.write(md_content)

    cmd = [
        LARK_CLI, "docs", "+create",
        "--api-version", "v2",
        "--doc-format", "markdown",
        "--parent-token", FOLDER_TOKEN,
        "--content", f"@{tmp_name}",
    ]
    try:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace", cwd=command_cwd
            )
        except subprocess.TimeoutExpired as e:
            raise PublishError("创建文档超时且服务端状态不确定，禁止自动重试") from e
        if result.returncode != 0:
            detail = redact_sensitive_text(result.stderr or result.stdout)[:240]
            raise PublishError(f"创建文档失败(rc={result.returncode}): {detail}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise PublishError("创建文档响应不是有效 JSON，服务端状态不确定") from e
        if not isinstance(data, dict) or not data.get("ok"):
            raise PublishError(f"创建文档服务端拒绝: {redact_sensitive_text(result.stdout)[:240]}")
        doc_id = find_nested_value(data, ("document_id", "documentId"))
        doc_url = find_nested_value(data, ("url", "document_url", "documentUrl"))
        if not doc_id or not doc_url:
            raise PublishError("建档响应 ok=true 但缺少 document_id/url，禁止重试防重复建档")
        print(f"  ✅ 文档创建成功 (id={mask_identifier(doc_id)})")
        return str(doc_url), str(doc_id)
    finally:
        # 确保临时文件始终被清理
        try:
            if os.path.exists(tmp_abs):
                os.remove(tmp_abs)
        except Exception:
            pass

def print_summary(report):
    """打印格式化的总结报告"""
    print("\n" + "="*60)
    print(f"  📊 招聘岗位日报 - {report['date']}")
    print(f"  总计: {report['total']} 个岗位")
    print("="*60)

    for platform_name in configured_platform_names():
        jobs = report["platforms"].get(platform_name, [])
        print(f"\n📋 {platform_name} ({len(jobs)} 个)")
        for j in jobs[:6]:
            salary_str = f" | 💰{j.get('salary', '')}" if j.get('salary') else ""
            loc_str = f" | 📍{j.get('location', '')}" if j.get('location') else ""
            comp_str = f" | 🏢{j.get('company', '')}" if j.get('company') else ""
            print(f"     • {j['title']}{salary_str}{loc_str}{comp_str}")
        if len(jobs) > 6:
            print(f"     ... 还有 {len(jobs) - 6} 个")

    print("\n" + "="*60 + "\n")
    quality = report.get("quality", {})
    warnings = quality.get("warnings", [])
    info = quality.get("info", [])
    if warnings:
        print(f"⚠️ 数据质量提醒 ({len(warnings)} 条)")
        for event in warnings[:8]:
            keyword = f"/{event.get('keyword')}" if event.get("keyword") else ""
            print(f"     • {event.get('platform')}{keyword} {event.get('metric')}={event.get('value')} {event.get('detail')}")
        print("")
    if info:
        print(f"ℹ️ 覆盖说明 ({len(info)} 条)")
        for event in info[:8]:
            keyword = f"/{event.get('keyword')}" if event.get("keyword") else ""
            print(f"     • {event.get('platform')}{keyword} {event.get('metric')}={event.get('value')}")
        print("")


def build_markdown(report, docx_url=None):
    """生成飞书消息用的 Markdown（新增/更新/持续在招三段式）"""
    new_jobs = report.get("new_jobs", [])
    updated_jobs = report.get("updated_jobs", [])
    repeated_jobs = report.get("repeated_jobs", [])
    all_jobs = report["jobs"]
    lines = []

    # 标题 + 总数
    lines.append(f"**招聘岗位日报 - {report['date']}**")
    lines.append(f"共采集 **{len(all_jobs)}** 个无人机/CAAC相关岗位")
    parts = []
    if new_jobs:
        parts.append(f"新增{len(new_jobs)}")
    if updated_jobs:
        parts.append(f"更新{len(updated_jobs)}")
    if repeated_jobs:
        parts.append(f"持续{len(repeated_jobs)}")
    if parts:
        lines.append(" | ".join(parts))
    if docx_url:
        lines.append(f"完整报告：{docx_url}")
    else:
        lines.append("⚠️ 完整报告文档创建失败，今日新增岗位将在明日日报再次呈现")
    q_warnings = report.get("quality", {}).get("warnings", [])
    if q_warnings:
        lines.append(f"数据质量提醒：{len(q_warnings)}条，建议查看完整报告/运行日志")
    q_info = report.get("quality", {}).get("info", [])
    if q_info:
        lines.append(f"覆盖说明：{len(q_info)}条（含空结果/可能截断，详见完整报告）")
    lines.append("")

    # 新增岗位（最多展示8个）
    if new_jobs:
        lines.append(f"**新增岗位**（{len(new_jobs)} 个）")
        for j in new_jobs[:8]:
            parts_line = [f"  - {escape_markdown_text(j['title'])}"]
            if j.get("salary"):
                parts_line.append(escape_markdown_text(j["salary"]))
            if j.get("company"):
                parts_line.append(escape_markdown_text(j["company"]))
            if j.get("location"):
                parts_line.append(escape_markdown_text(j["location"]))
            lines.append(" | ".join(parts_line))
        if len(new_jobs) > 8:
            lines.append(f"  ... 还有 {len(new_jobs) - 8} 个，详见完整报告")
        lines.append("")

    # 更新岗位（最多展示4个）
    if updated_jobs:
        lines.append(f"**更新岗位**（{len(updated_jobs)} 个）")
        for j in updated_jobs[:4]:
            parts_line = [f"  - {escape_markdown_text(j['title'])}"]
            if j.get("company"):
                parts_line.append(escape_markdown_text(j["company"]))
            if j.get("_update_info"):
                parts_line.append(f"[{escape_markdown_text(j['_update_info'])}]")
            lines.append(" | ".join(parts_line))
        if len(updated_jobs) > 4:
            lines.append(f"  ... 还有 {len(updated_jobs) - 4} 个，详见完整报告")
        lines.append("")

    # 持续在招（仅汇总数量）
    if repeated_jobs:
        lines.append(f"**持续在招**（{len(repeated_jobs)} 个，往期已出现）")
        for pn in configured_platform_names():
            count = sum(1 for job in repeated_jobs if pn in canonical_platforms(job))
            if count > 0:
                lines.append(f"  - {pn}: {count}条")
        lines.append("")

    _, _, total_by_kw, total_by_platform = build_reference_summary(report)
    lines.append(
        "**关键词贡献（非互斥）**: "
        + " | ".join(f"{key}: {value}个" for key, value in total_by_kw.items())
    )
    lines.append(
        "**平台贡献（非互斥）**: "
        + " | ".join(f"{key}: {value}个" for key, value in total_by_platform.items())
    )
    relevance = report.get("relevance", {})
    lines.append(
        f"**相关性**: 核心{relevance.get('core', 0)} | "
        f"泛低空产业{relevance.get('industry', 0)} | "
        f"弱相关待复核{relevance.get('weak', 0)}"
    )

    return "\n".join(lines)



# ============================================================
# 飞书集成
# ============================================================

def upload_to_feishu(filepath, filename):
    """上传报告到飞书云空间文件夹"""
    print(f"\n⬆️  上传到飞书云空间...")
    # lark-cli 的 --file 需要相对路径；以待上传文件目录作为 cwd。
    upload_dir, rel_path = local_lark_file_reference(filepath)
    cmd = [
        LARK_CLI, "drive", "+upload",
        "--file", rel_path,
        "--name", filename,
        "--folder-token", FOLDER_TOKEN,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        cwd=upload_dir,
    )
    stdout = result.stdout

    print(f"  上传响应: {redact_sensitive_text(stdout)[:400]}")

    if result.returncode == 0:
        # 从输出提取 file_token
        try:
            data = json.loads(stdout)
            if data.get("ok") and data.get("data", {}).get("file_token"):
                file_token = data["data"]["file_token"]
                print(f"  ✅ 上传成功! file_token: {mask_identifier(file_token)}")
                return file_token
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        # 尝试正则提取
        m = re.search(r'file_token["\s:]+["\']?([a-zA-Z0-9_]+)', stdout)
        if m:
            token = m.group(1)
            print(f"  ✅ 上传成功 (提取token): {mask_identifier(token)}")
            return token
        print(f"  ✅ 上传成功，但未提取到 file_token")
        return True
    else:
        print(f"  ❌ 上传失败 (rc={result.returncode})")
        print(f"  stderr: {redact_sensitive_text(result.stderr)[:300]}")
        return None


def permission_already_satisfied(stdout="", stderr=""):
    """识别权限创建接口的幂等冲突；只接受明确的“成员已有权限”语义。"""
    text = f"{stdout or ''}\n{stderr or ''}".lower()
    markers = (
        "permission already exists",
        "permission already exist",
        "already has permission",
        "member already exists",
        "member already exist",
        "member has been added",
        "权限已存在",
        "已有权限",
        "成员已存在",
        "已添加该成员",
    )
    return any(marker in text for marker in markers)


def grant_permissions(file_token, file_type="docx"):
    """为员工授权访问报告，返回结构化汇总，不吞失败。"""
    if not file_token or file_token is True:
        return {"ok": False, "success": 0, "total": len(ALL_STAFF), "failures": ["invalid_token"]}

    print(f"\n🔑 授权员工访问报告 (type: {file_type})...")

    success_count = 0
    already_satisfied_count = 0
    failures = []
    for index, (member_type, member_id, perm) in enumerate(ALL_STAFF, 1):
        data = json.dumps({
            "member_id": member_id,
            "member_type": member_type,
            "perm": perm,
            "type": "user",
        })
        cmd = [
            LARK_CLI, "drive", "permission.members", "create",
            "--params", json.dumps({"token": file_token, "type": file_type}),
            "--data", data,
            "--yes",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0:
                success_count += 1
            elif permission_already_satisfied(result.stdout, result.stderr):
                # 失败恢复会对同一文档重放授权；已有权限等价于本步骤已满足。
                success_count += 1
                already_satisfied_count += 1
            else:
                failures.append(
                    f"member#{index}:rc={result.returncode}:"
                    f"{redact_sensitive_text(result.stderr or result.stdout)[:80]}"
                )
        except Exception as e:
            failures.append(f"member#{index}:{type(e).__name__}:{redact_sensitive_text(e)[:80]}")

        time.sleep(0.3)  # 限速

    summary = {
        "ok": success_count == len(ALL_STAFF),
        "success": success_count,
        "total": len(ALL_STAFF),
        "already_satisfied": already_satisfied_count,
        "failures": failures,
    }
    already_note = f"（其中已有权限 {already_satisfied_count}）" if already_satisfied_count else ""
    print(f"  📊 授权完成: {success_count}/{len(ALL_STAFF)}{already_note}")
    return summary


def send_to_feishu_chat(markdown_text):
    """发送消息到人事行政群并返回 message_id；失败时抛 PublishError。"""
    print(f"\n💬 发送消息到人事行政群...")
    # 飞书markdown消息长度限制
    if len(markdown_text) > 15000:
        lines = markdown_text.split("\n")
        truncated = lines[:50]
        truncated.append("\n*报告过长，请查看云空间完整版本*")
        markdown_text = "\n".join(truncated)

    cmd = [
        LARK_CLI, "im", "+messages-send",
        "--chat-id", CHAT_ID,
        "--markdown", markdown_text,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            detail = redact_sensitive_text(result.stderr or result.stdout)[:200]
            raise PublishError(f"群消息发送失败(rc={result.returncode}): {detail}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise PublishError("群消息响应不是有效 JSON，无法确认投递") from e
        if not isinstance(data, dict) or data.get("ok") is False:
            raise PublishError(f"群消息服务端拒绝: {redact_sensitive_text(result.stdout)[:200]}")
        message_id = find_nested_value(data, ("message_id", "messageId"))
        if not message_id:
            raise PublishError("群消息命令成功但缺少 message_id，无法确认投递")
        print(f"  ✅ 群消息已接受 (message_id={mask_identifier(message_id)})")
        return str(message_id)
    except Exception as e:
        if isinstance(e, PublishError):
            raise
        raise PublishError(f"群消息发送异常({type(e).__name__}): {redact_sensitive_text(e)}") from e


def publish_report(
    report,
    today_str,
    raw_counts,
    updated_signatures,
    receipt_path=PUBLISH_RECEIPT_FILE,
    create_doc_fn=None,
    grant_permissions_fn=None,
    send_message_fn=None,
    save_signatures_fn=None,
    append_history_fn=None,
    force=False,
):
    """按 建档→授权→群回执→签名→历史 顺序完成端到端发布。"""
    create_doc_fn = create_doc_fn or create_feishu_report_docx
    grant_permissions_fn = grant_permissions_fn or grant_permissions
    send_message_fn = send_message_fn or send_to_feishu_chat
    save_signatures_fn = save_signatures_fn or save_signatures
    append_history_fn = append_history_fn or append_history

    fingerprint = report_fingerprint(report)
    existing = load_publish_receipt(receipt_path)
    if (
        not force
        and existing.get("date") == today_str
        and existing.get("message_id")
    ):
        raise PublishError("今日已有群消息回执，拒绝重复投递；人工重发需显式 --force")
    same_report = (
        not force
        and existing.get("date") == today_str
        and existing.get("report_fingerprint") == fingerprint
    )
    if same_report and existing.get("message_id"):
        raise PublishError("今日同一报告已有群消息回执，拒绝重复投递；人工重发需显式 --force")

    run_id = f"{today_str}-{datetime.datetime.now().strftime('%H%M%S')}-{os.getpid()}"
    receipt = dict(existing) if same_report else {}
    receipt.update({
        "date": today_str,
        "run_id": run_id,
        "status": "publishing",
        "stage": "preflight",
        "report_fingerprint": fingerprint,
        "started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "error": "",
    })
    write_publish_receipt(receipt, receipt_path)

    try:
        docx_url = receipt.get("docx_url", "") if same_report else ""
        docx_id = receipt.get("docx_id", "") if same_report else ""
        if docx_url and docx_id:
            print(f"  [RESUME] 复用今日已创建文档 (id={mask_identifier(docx_id)})")
        else:
            receipt["stage"] = "creating_document"
            write_publish_receipt(receipt, receipt_path)
            docx_url, docx_id = create_doc_fn(report, today_str)
            if not docx_url or not docx_id:
                raise PublishError("文档创建未返回 docx_url/docx_id")
            receipt.update({
                "stage": "document_created",
                "docx_url": str(docx_url),
                "docx_id": str(docx_id),
            })
            write_publish_receipt(receipt, receipt_path)

        permissions = receipt.get("permissions", {}) if same_report else {}
        if permissions.get("ok"):
            print(
                f"  [RESUME] 复用授权回执 "
                f"({permissions.get('success', 0)}/{permissions.get('total', 0)})"
            )
        else:
            receipt["stage"] = "granting_permissions"
            write_publish_receipt(receipt, receipt_path)
            permissions = grant_permissions_fn(docx_id)
            if not isinstance(permissions, dict):
                raise PublishError("授权函数未返回结构化结果")
            receipt["permissions"] = permissions
            receipt["stage"] = "permissions_checked"
            write_publish_receipt(receipt, receipt_path)
            if not permissions.get("ok"):
                raise PublishError(
                    f"文档授权不完整: {permissions.get('success', 0)}/{permissions.get('total', 0)}"
                )

        receipt["stage"] = "sending_message"
        write_publish_receipt(receipt, receipt_path)
        markdown_text = build_markdown(report, docx_url=docx_url)
        message_id = send_message_fn(markdown_text)
        if not message_id:
            raise PublishError("群消息发送未返回 message_id")
        receipt.update({
            "status": "delivered",
            "stage": "message_delivered",
            "message_id": str(message_id),
            "delivered_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        # 先持久化群回执，再做本地写入；后续失败也不会误发第二条群消息。
        write_publish_receipt(receipt, receipt_path)

        save_signatures_fn(updated_signatures, today_str)
        receipt["stage"] = "signatures_saved"
        write_publish_receipt(receipt, receipt_path)

        receipt.update({
            "status": "published",
            "stage": "history_writing",
            "finished_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        append_history_fn(today_str, raw_counts, report, receipt)
        receipt["stage"] = "complete"
        write_publish_receipt(receipt, receipt_path)
        return receipt
    except Exception as e:
        delivered = bool(receipt.get("message_id"))
        receipt.update({
            "status": "delivered_degraded" if delivered else "error",
            "error": f"{type(e).__name__}: {redact_sensitive_text(e)}"[:500],
            "finished_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        try:
            write_publish_receipt(receipt, receipt_path)
        except Exception as state_error:
            raise PublishError(
                f"发布失败且收据无法落盘({type(state_error).__name__})，"
                f"原错误={type(e).__name__}: {redact_sensitive_text(e)}"
            ) from e
        if isinstance(e, PublishError):
            raise
        raise PublishError(f"发布阶段失败({type(e).__name__}): {redact_sensitive_text(e)}") from e


def self_test():
    """离线自检：配置、去重、签名和报告构建，不触发浏览器或飞书发送。"""
    global SNAPSHOT_DISABLED
    SNAPSHOT_DISABLED = True  # 自检不得污染真实快照目录
    print("SELF_TEST start")
    required = [CONFIG_PATH, REPORT_DIR, SNAPSHOT_DIR]
    for path in required:
        print(f"  path: {path} exists={os.path.exists(path)}")
    validate_runtime_config(require_feishu=True)
    local_dir, local_name = local_lark_file_reference(
        os.path.join(REPORT_DIR, "custom-report.md")
    )
    if local_dir != os.path.abspath(REPORT_DIR) or local_name != "custom-report.md":
        raise AssertionError("自定义 report_dir 的 lark-cli 本地文件上下文不正确")
    redaction_sample = (
        '{"file_token":"secret-file","chat_id":"secret-chat",'
        '"message_id":"secret-message","url":"https://example.test/docx/secret-doc"}'
    )
    redacted = redact_sensitive_text(redaction_sample)
    for sensitive_value in ("secret-file", "secret-chat", "secret-message", "secret-doc"):
        if sensitive_value in redacted:
            raise AssertionError(f"日志脱敏失败: {sensitive_value}")

    sample_jobs = [
        {
            "platform": "猎聘",
            "title": "无人机飞手【五险一金】",
            "company": "武汉云技科技有限公司",
            "salary": "8-12k",
            "location": "武汉",
            "url": "https://www.liepin.com/job/12345.shtml",
            "keyword": "无人机飞手",
        },
        {
            "platform": "前程无忧",
            "title": "无人机飞手",
            "company": "武汉云技科技有限责任公司",
            "salary": "8-12k",
            "location": "武汉",
            "url": "https://jobs.51job.com/wuhan/999.html",
            "keyword": "CAAC",
        },
        {
            "platform": "智联招聘",
            "title": "无人机教员",
            "company": "",
            "salary": "",
            "location": "武汉",
            "url": "",
            "keyword": "无人机教员",
        },
    ]
    deduped = deduplicate_jobs(sample_jobs)
    if len(deduped) != 2:
        raise AssertionError(f"dedupe expected 2, got {len(deduped)}")

    # 猎聘卡片解析
    liepin_html = (
        '<div class="_x job-card-pc-container">'
        '<a data-nick="job-detail-job-info" target="_blank" '
        'href="https://www.liepin.com/a/123456.shtml?pgRef=abc">'
        '<div title="无人机飞手">无人机飞手</div>'
        '<span>【</span><span>武汉</span><span>】</span><span>10-15k</span>'
        '<span>3-5年</span><span>大专</span></a>'
        '<div data-nick="job-detail-company-info">'
        '<span class="_y ellipsis-1">武汉测试科技有限公司</span></div></div>'
        '<div class="_x job-card-pc-container">'
        '<a data-nick="job-detail-job-info" href="https://www.liepin.com/job/999.shtml?x=1">'
        '<div>招聘总监</div><span>【</span><span>深圳</span><span>】</span>'
        '<span>30-50k</span></a></div>'
    )
    lp_jobs = parse_liepin_html(liepin_html, "无人机飞手")
    if len(lp_jobs) != 1:
        raise AssertionError(f"liepin card parse expected 1 (相关性过滤), got {len(lp_jobs)}")
    lp = lp_jobs[0]
    if lp["url"] != "https://www.liepin.com/a/123456.shtml":
        raise AssertionError(f"liepin url wrong: {lp['url']}")
    if lp["company"] != "武汉测试科技有限公司" or lp["location"] != "武汉" or lp["salary"] != "10-15k":
        raise AssertionError(f"liepin fields wrong: {lp}")
    liepin_noisy_html = (
        '<div class="job-card-pc-container"><a data-nick="job-detail-job-info" '
        'href="https://www.liepin.com/job/noisy.shtml">'
        '<div title="无人机飞手">无人机飞手</div>'
        '<span>【</span><span>接受小白</span><span>】</span>'
        '<span>【</span><span>武汉-洪山区</span><span>】</span><span>9-14k</span>'
        '</a><div data-nick="job-detail-company-info">'
        '<span class="ellipsis-1">测试无人机有限公司</span></div></div>'
    )
    noisy_jobs = parse_liepin_html(liepin_noisy_html, "无人机飞手")
    if len(noisy_jobs) != 1 or noisy_jobs[0]["location"] != "武汉-洪山区":
        raise AssertionError(f"猎聘应跳过福利括号并提取合法地点: {noisy_jobs}")
    if noisy_jobs[0]["title"] != "无人机飞手":
        raise AssertionError(f"猎聘应优先使用标题属性: {noisy_jobs[0]}")

    # 前程无忧卡片解析
    sd = html_lib.escape(json.dumps({
        "jobId": "167128197", "jobTitle": "无人机教员",
        "jobSalary": "8千-1.2万", "jobArea": "武汉·洪山区",
    }, ensure_ascii=False), quote=True)
    j51_html = (
        '<div class="joblist">'
        f'<div class="joblist-item" style=""><div sensorsdata="{sd}" class="joblist-item-job">'
        '<span title="武汉测试科技有限公司" class="cname text-cut"> 武汉测试科技有限公司 </span>'
        '</div></div></div>'
    )
    j51_jobs = parse_51job_html(j51_html, "无人机教员")
    if len(j51_jobs) != 1:
        raise AssertionError(f"51job card parse expected 1, got {len(j51_jobs)}")
    j51 = j51_jobs[0]
    if j51["url"] != "https://jobs.51job.com/all/167128197.html":
        raise AssertionError(f"51job url wrong: {j51['url']}")
    if j51["company"] != "武汉测试科技有限公司" or j51["location"] != "武汉-洪山区" or j51["salary"] != "8千-1.2万":
        raise AssertionError(f"51job fields wrong: {j51}")
    # 智联卡片解析（2026-07-13 全国口径 DOM）
    zl_html = (
        '<div class="joblist-box__item clearfix joblist-box__item-unlogin">'
        '<a href="http://www.zhaopin.com/jobdetail/CCL123J456.htm?refcode=4019" '
        'target="_blank" class="jobinfo__name">无人机飞手</a>'
        '<p class="jobinfo__salary"> 5000-10000元 </p>'
        '<img class="jobinfo__other-info-location-image"> <span>成都·双流·新兴</span>'
        '<a title="四川测试无人机科技有限公司" href="https://www.zhaopin.com/companydetail/C1.htm" '
        'class="companyinfo__name"> 四川测试无人机科技有限公司 </a></div>'
        '<div class="joblist-box__item clearfix">'
        '<a href="http://www.zhaopin.com/jobdetail/CCL999J000.htm" class="jobinfo__name">销售总监</a>'
        '<p class="jobinfo__salary"> 2-3万 </p></div>'
    )
    zl_jobs = parse_zhaopin_html(zl_html, "无人机飞手")
    QUALITY_EVENTS.clear()
    if len(zl_jobs) != 1:
        raise AssertionError(f"zhaopin card parse expected 1 (相关性过滤), got {len(zl_jobs)}")
    zl = zl_jobs[0]
    if zl["url"] != "http://www.zhaopin.com/jobdetail/CCL123J456.htm":
        raise AssertionError(f"zhaopin url wrong: {zl['url']}")
    if zl["salary"] != "5000-10000元" or zl["location"] != "成都-双流-新兴" or zl["company"] != "四川测试无人机科技有限公司":
        raise AssertionError(f"zhaopin fields wrong: {zl}")

    # 智联会为较长公司名追加 companyinfo__name-short；公司主 class 必须按 token 匹配。
    zl_short_name_html = zl_html.replace(
        'class="companyinfo__name">',
        'class="companyinfo__name companyinfo__name-short">',
        1,
    )
    zl_short_name_jobs = parse_zhaopin_html(zl_short_name_html, "无人机飞手")
    if len(zl_short_name_jobs) != 1 or zl_short_name_jobs[0]["company"] != "四川测试无人机科技有限公司":
        raise AssertionError(f"zhaopin multi-class company parse failed: {zl_short_name_jobs}")
    zl_modifier_only_jobs = parse_zhaopin_html(
        zl_html.replace('class="companyinfo__name">', 'class="companyinfo__name-short">', 1),
        "无人机飞手",
    )
    if len(zl_modifier_only_jobs) != 1 or zl_modifier_only_jobs[0]["company"]:
        raise AssertionError(f"zhaopin modifier-only class must not match: {zl_modifier_only_jobs}")

    # 三平台卡片空结果分流：有标题但零相关=no_relevant_jobs；卡片有但零标题=parsed_jobs。
    parser_cases = [
        (
            "猎聘",
            parse_liepin_html,
            '<div class="job-card-pc-container"><a data-nick="job-detail-job-info" '
            'href="https://www.liepin.com/job/1.shtml"><div>销售总监</div></a></div>',
            '<div class="job-card-pc-container"><div>changed dom</div></div>',
        ),
        (
            "前程无忧",
            parse_51job_html,
            '<div class="joblist-item"><div sensorsdata="'
            + html_lib.escape(json.dumps({"jobId": "1", "jobTitle": "销售总监"}), quote=True)
            + '"></div></div>',
            '<div class="joblist-item"><div class="changed-dom"></div></div>',
        ),
        (
            "智联招聘",
            parse_zhaopin_html,
            '<div class="joblist-box__item"><a href="https://www.zhaopin.com/jobdetail/1.htm" '
            'class="jobinfo__name">销售总监</a></div>',
            '<div class="joblist-box__item"><div class="changed-dom"></div></div>',
        ),
    ]
    for platform, parser, irrelevant_html, broken_html in parser_cases:
        QUALITY_EVENTS.clear()
        parser(irrelevant_html, "无人机飞手")
        metrics = [event["metric"] for event in QUALITY_EVENTS]
        if metrics != ["no_relevant_jobs"]:
            raise AssertionError(f"{platform} 有标题但零相关应记 no_relevant_jobs: {metrics}")
        QUALITY_EVENTS.clear()
        parser(broken_html, "无人机飞手")
        metrics = [event["metric"] for event in QUALITY_EVENTS]
        if metrics != ["parsed_jobs"]:
            raise AssertionError(f"{platform} 卡片存在但零标题应记 parsed_jobs: {metrics}")
    QUALITY_EVENTS.clear()

    # 智联旧 DOM 必须在各自局部片段取字段，不能把第一份薪资/公司串给后续岗位。
    legacy_zl_html = (
        '<section><a href="https://www.zhaopin.com/jobdetail/OLD1.htm">无人机飞手</a>'
        '<span class="salary">8-10k</span>'
        '<a href="https://www.zhaopin.com/companydetail/C1">甲无人机公司</a></section>'
        '<section><a href="https://www.zhaopin.com/jobdetail/OLD2.htm">无人机教员</a>'
        '<span class="salary">12-15k</span>'
        '<a href="https://www.zhaopin.com/companydetail/C2">乙低空公司</a></section>'
    )
    legacy_jobs = parse_zhaopin_html(legacy_zl_html, "无人机飞手")
    if len(legacy_jobs) != 2:
        raise AssertionError(f"智联旧 DOM 应解析两岗: {legacy_jobs}")
    if legacy_jobs[0]["salary"] != "8-10k" or legacy_jobs[0]["company"] != "甲无人机公司":
        raise AssertionError(f"智联旧 DOM 第一岗字段错配: {legacy_jobs[0]}")
    if legacy_jobs[1]["salary"] != "12-15k" or legacy_jobs[1]["company"] != "乙低空公司":
        raise AssertionError(f"智联旧 DOM 第二岗字段错配: {legacy_jobs[1]}")

    truncated_html = (
        '<div class="joblist-box__item"></div>' * 20
        + '<div class="soupager"><a href="https://www.zhaopin.com/sou/kwX/p2" '
        'class="btn soupager__btn">下一页</a></div>'
    )
    if not detect_result_truncation("智联招聘", truncated_html):
        raise AssertionError("20 卡且存在下一页应标记 possible_truncation")
    if detect_result_truncation("智联招聘", '<div class="joblist-box__item"></div>' * 19):
        raise AssertionError("19 卡且无下一页/总数提示不应标记截断")
    zhaopin_last_page = (
        '<div class="joblist-box__item"></div>' * 20
        + '<div class="soupager"><a href="/p1" class="soupager__index soupager__index--active">1</a></div>'
    )
    if detect_result_truncation("智联招聘", zhaopin_last_page):
        raise AssertionError("智联末页即使恰好20卡也不应误报截断")
    guopin_disabled = (
        '<div class="job-card"></div>'
        '<li title="下一页" class="ant-pagination-next ant-pagination-disabled" '
        'aria-disabled="true"><button disabled>下一页</button></li>'
    )
    if detect_result_truncation("国聘", guopin_disabled):
        raise AssertionError("国聘 disabled 下一页不得误报截断")
    guopin_enabled = (
        '<div class="job-card"></div>'
        '<li title="下一页" class="ant-pagination-next" aria-disabled="false">'
        '<button>下一页</button></li>'
    )
    if not detect_result_truncation("国聘", guopin_enabled):
        raise AssertionError("国聘启用的下一页应标记存在后续页")
    guopin_missing_aria = (
        '<div class="job-card"></div>'
        '<li title="下一页" class="ant-pagination-next"><button>下一页</button></li>'
    )
    if pagination_state("国聘", guopin_missing_aria)["has_next"]:
        raise AssertionError("国聘下一页缺少 aria-disabled=false 时不得点击")
    if detect_result_truncation("国聘", guopin_missing_aria):
        raise AssertionError("国聘下一页缺少显式启用证据时不得误报截断")
    page2_url = update_url_query("https://www.liepin.com/zhaopin/?key=x", currentPage=1, pageSize=40)
    if "currentPage=1" not in page2_url or "pageSize=40" not in page2_url:
        raise AssertionError(f"猎聘分页URL构造错误: {page2_url}")
    QUALITY_EVENTS.clear()
    print("  card parsers ok (liepin + 51job + zhaopin)")

    # 国聘卡片解析（2026-07-15 快照 DOM）：逐卡公司页链接 + 相关性过滤 + 去重回退文本签名
    gp_html = (
        '<div class="ant-spin-container"><div><div class="job-card">'
        '<div class="job-left"><div class="job-title" title="无人机应用开发工程师 「北京-海淀区」">'
        '<div class="job-name">无人机应用开发工程师</div>'
        '<div class="job-district">「北京-海淀区」</div></div>'
        '<div class="job-info"><span class="job-salary">13~20K</span></div></div>'
        '<div class="job-right"><a class="substring company-name" title="北京图知天下科技有限责任公司" '
        'href="/company?id=65247263189893346" target="_blank" rel="noopener noreferrer">'
        '北京图知天下科技有限责任公司</a><div class="department-name">研发中心</div></div></div>'
        '<div class="job-card"><div class="job-left"><div class="job-title">'
        '<div class="job-name">机械员</div><div class="job-district">「上海-长宁区」</div></div>'
        '<div class="job-info"><span class="job-salary">面议</span></div></div>'
        '<div class="job-right"><a class="substring company-name" title="东方航空技术有限公司" '
        'href="/company?id=10685310023336301">东方航空技术有限公司</a></div></div>'
    )
    gp_jobs = parse_iguopin_html(gp_html, "CAAC")
    QUALITY_EVENTS.clear()
    if len(gp_jobs) != 1:
        raise AssertionError(f"国聘卡片应过滤到1个相关岗位, got {len(gp_jobs)}: {[j['title'] for j in gp_jobs]}")
    gp = gp_jobs[0]
    if gp["url"] != "https://www.iguopin.com/company?id=65247263189893346":
        raise AssertionError(f"国聘 url 应为逐卡公司页链接: {gp['url']}")
    if gp["company"] != "北京图知天下科技有限责任公司" or gp["salary"] != "13~20K" or gp["location"] != "北京-海淀区":
        raise AssertionError(f"国聘字段错误: {gp}")
    if gp["title"] != "无人机应用开发工程师":
        raise AssertionError(f"国聘标题错误: {gp['title']}")
    # 公司页 URL 不应被当作稳定岗位ID → 签名回退文本，同公司不同岗位不误并
    if extract_stable_job_id(gp["url"]):
        raise AssertionError("国聘 /company?id= 不应被识别为岗位ID")
    if not make_job_signature(gp).startswith("text|"):
        raise AssertionError(f"国聘签名应回退文本签名: {make_job_signature(gp)}")
    gp_two = [
        {"platform": "国聘", "title": "试车台软件工程师", "company": "海南航空控股股份有限公司",
         "salary": "面议", "location": "海口",
         "url": "https://www.iguopin.com/company?id=10685383535200661", "keyword": "CAAC"},
        {"platform": "国聘", "title": "无损检测技术人员", "company": "海南航空控股股份有限公司",
         "salary": "面议", "location": "海口",
         "url": "https://www.iguopin.com/company?id=10685383535200661", "keyword": "CAAC"},
    ]
    if len(deduplicate_jobs(gp_two)) != 2:
        raise AssertionError("同公司不同岗位共享公司页URL不应被误并")
    # 空匹配分流：有标题但无一相关 → no_relevant_jobs(信息型)，非 parsed_jobs(修复触发)
    QUALITY_EVENTS.clear()
    gp_irrel = (
        '<div class="job-card"><div class="job-name">机械员</div>'
        '<div class="job-district">「上海」</div></div>'
        '<div class="job-card"><div class="job-name">放行工程师</div>'
        '<div class="job-district">「北京」</div></div>'
    )
    if parse_iguopin_html(gp_irrel, "无人机飞手") != []:
        raise AssertionError("无相关岗应返回空")
    ev = [e for e in QUALITY_EVENTS if e["metric"] in ("no_relevant_jobs", "parsed_jobs")]
    if not (len(ev) == 1 and ev[0]["metric"] == "no_relevant_jobs" and ev[0]["value"] == 2):
        raise AssertionError(f"有标题但0相关应记 no_relevant_jobs=2(信息型): {ev}")
    # 真解析失败：卡片在但抽不出任何标题 → parsed_jobs(修复触发)
    QUALITY_EVENTS.clear()
    gp_broken = '<div class="job-card"><div class="jobname-CHANGED">新DOM</div></div>'
    parse_iguopin_html(gp_broken, "无人机飞手")
    ev2 = [e for e in QUALITY_EVENTS if e["metric"] in ("no_relevant_jobs", "parsed_jobs")]
    if not (len(ev2) == 1 and ev2[0]["metric"] == "parsed_jobs"):
        raise AssertionError(f"抽不出标题应记 parsed_jobs(修复触发): {ev2}")
    QUALITY_EVENTS.clear()
    print("  国聘卡片解析 ok (逐卡公司URL + 去重回退文本签名 + 空匹配分流)")

    # 相关性过滤：四级分层 + 驾驶员语境化 + 弱相关准入边界
    relevance_cases = {
        "无人机教员": "core",
        "低空经济财务经理": "industry",
        "航空座椅研发工程师": "weak",
        "货车司机": "irrelevant",
    }
    for title, expected_tier in relevance_cases.items():
        actual_tier, _ = classify_relevance(title)
        if actual_tier != expected_tier:
            raise AssertionError(f"相关性分层错误: {title} expected={expected_tier}, got={actual_tier}")
    if is_relevant_job_title("C1货车驾驶员"):
        raise AssertionError("裸'驾驶员'不应放行无关岗")
    if not is_relevant_job_title("无人机驾驶员"):
        raise AssertionError("无人机驾驶员应相关")
    if not is_relevant_job_title("飞行器结构工程师", "eVTOL"):
        raise AssertionError("eVTOL检索下行业岗应相关")
    if is_relevant_job_title("结构工程师", "eVTOL"):
        raise AssertionError("无行业词的岗不应因eVTOL检索误放行")
    weak_title = "航空座椅研发工程师"
    for keyword in ("eVTOL", "低空经济"):
        if not is_relevant_job_title(weak_title, keyword):
            raise AssertionError(f"弱相关航空岗应允许宽口径行业检索复核: {keyword}")
    for keyword in ("CAAC", "无人机飞手"):
        if is_relevant_job_title(weak_title, keyword):
            raise AssertionError(f"弱相关航空岗不应进入核心岗位检索: {keyword}")
    for title in ("航空器维修工程师", "适航工程师", "飞行器结构工程师"):
        if is_relevant_job_title(title, "CAAC"):
            raise AssertionError(f"CAAC 检索不得放行普通民航产业岗: {title}")
    if is_valid_location("接受小白"):
        raise AssertionError("招聘条件文案不应被识别为地点")
    for salary in ("面议", "8-12k", "6千-1万·13薪"):
        if not is_valid_salary(salary):
            raise AssertionError(f"合法薪资格式被误判: {salary}")

    noisy_field_jobs = [
        {
            "platform": "猎聘", "title": "无人机飞手", "company": "测试公司",
            "salary": "经验不限", "location": "接受小白",
            "url": "https://www.liepin.com/job/semantic-field.shtml", "keyword": "无人机飞手",
        },
        {
            "platform": "智联招聘", "title": "无人机飞手", "company": "测试公司",
            "salary": "8-10k", "location": "武汉",
            "url": "https://www.liepin.com/job/semantic-field.shtml", "keyword": "CAAC",
        },
        {
            "platform": "猎聘", "title": "无人机飞手", "company": "测试公司",
            "salary": "经验不限", "location": "接受小白",
            "url": "https://www.liepin.com/job/semantic-field.shtml", "keyword": "无人机教员",
        },
    ]
    cleaned_jobs = deduplicate_jobs(noisy_field_jobs)
    if len(cleaned_jobs) != 1:
        raise AssertionError(f"同岗跨关键词字段清洗后应合并为1条: {cleaned_jobs}")
    cleaned = cleaned_jobs[0]
    if cleaned.get("location") != "武汉" or cleaned.get("salary") != "8-10k":
        raise AssertionError(f"合法字段应覆盖已清空的非法字段: {cleaned}")
    observations = normalize_invalid_field_observations(cleaned.get(INVALID_FIELD_OBSERVATIONS))
    if observations["location"] != [{"value": "接受小白", "platforms": ["猎聘"]}]:
        raise AssertionError(f"非法地点观察应按平台和值幂等保留: {observations}")
    if observations["salary"] != [{"value": "经验不限", "platforms": ["猎聘"]}]:
        raise AssertionError(f"非法薪资观察应按平台和值幂等保留: {observations}")

    field_quality = analyze_quality(cleaned_jobs, raw_counts={})
    if field_quality["platforms"]["猎聘"]["invalid_location"] != 1:
        raise AssertionError(f"猎聘非法地点应计1次: {field_quality}")
    if field_quality["platforms"]["猎聘"]["missing_location"] != 0:
        raise AssertionError("已保留非法观察的空字段不得再重复计 missing")
    if field_quality["platforms"]["智联招聘"]["invalid_location"] != 0:
        raise AssertionError("跨平台合法地点不得把猎聘异常扩散到智联")

    field_report = build_report(cleaned_jobs, [], [], "2026-08-03", quality=field_quality)
    public_jobs_json = json.dumps(field_report["jobs"], ensure_ascii=False)
    if INVALID_FIELD_OBSERVATIONS in public_jobs_json or "接受小白" in public_jobs_json:
        raise AssertionError(f"原始非法字段不得进入报告岗位列表: {public_jobs_json}")
    if "接受小白" not in json.dumps(field_report["quality"], ensure_ascii=False):
        raise AssertionError("原始非法字段应保留在质量样本中供诊断")

    fingerprint_before = report_fingerprint(field_report)
    fingerprint_variant = json.loads(json.dumps(field_report, ensure_ascii=False))
    fingerprint_stats = fingerprint_variant["quality"]["platforms"]["猎聘"]
    fingerprint_stats["invalid_location_samples"] = ["另一个非法地点样本"]
    fingerprint_stats["invalid_salary_samples"] = ["另一个非法薪资样本"]
    if report_fingerprint(fingerprint_variant) != fingerprint_before:
        raise AssertionError("非法字段诊断样本变化不得改变报告指纹")
    fingerprint_variant["total"] += 1
    if report_fingerprint(fingerprint_variant) == fingerprint_before:
        raise AssertionError("报告业务内容变化必须改变报告指纹")

    coverage_quality = {
        "platforms": {},
        "warnings": [],
        "info": [
            {
                "platform": "测试平台", "keyword": "CAAC", "metric": f"coverage_{index}",
                "value": index, "detail": f"覆盖说明 {index}",
            }
            for index in range(15)
        ],
    }
    coverage_report = build_report([], [], [], "2026-08-03", quality=coverage_quality)
    coverage_markdown = build_docx_markdown(coverage_report, "2026-08-03")
    if "coverage_14=14" not in coverage_markdown:
        raise AssertionError("覆盖说明不得静默截断到前12条")

    weak_signature = make_job_signature({
        "platform": "猎聘", "title": "无人机飞手", "company": "测试公司",
        "salary": "经验不限", "location": "接受小白", "url": "",
    }, prefer_url=False)
    if weak_signature:
        raise AssertionError(f"区分字段全失效时不得生成过宽签名: {weak_signature}")
    normalized_old = _normalize_signature_info({
        "first_seen": "2026-08-01", "last_seen": "2026-08-02",
        "seen_dates": ["2026-08-01", "2026-08-02"], "times": 2,
        "last_salary": "经验不限", "last_location": "接受小白",
    })
    if normalized_old["last_salary"] or normalized_old["last_location"]:
        raise AssertionError(f"历史非法基线应归一为空: {normalized_old}")
    history_job = {
        "platform": "猎聘", "title": "无人机飞手", "company": "测试公司",
        "salary": "8-10k", "location": "武汉",
        "url": "https://www.liepin.com/job/history-semantic.shtml", "keyword": "无人机飞手",
    }
    history_sig = make_job_signature(history_job)
    _, history_updated, _, _ = categorize_jobs(
        [history_job],
        "2026-08-03",
        previous_signatures={history_sig: {
            "first_seen": "2026-08-01", "last_seen": "2026-08-02",
            "seen_dates": ["2026-08-01", "2026-08-02"], "times": 2,
            "last_salary": "经验不限", "last_location": "接受小白",
        }},
    )
    if len(history_updated) != 1 or "补全" not in history_updated[0].get("_update_info", ""):
        raise AssertionError(f"合法新值应相对非法历史基线显示为补全: {history_updated}")
    if "接受小白" in history_updated[0].get("_update_info", ""):
        raise AssertionError(f"更新文案不得暴露非法历史基线: {history_updated[0]}")

    if not permission_already_satisfied(
        '{"ok":false,"msg":"permission already exists for this member"}', ""
    ):
        raise AssertionError("重复授权的“权限已存在”响应应视为授权步骤已满足")
    if permission_already_satisfied("", "permission denied"):
        raise AssertionError("权限拒绝不得误判为已有权限")
    print("  relevance and field semantics ok")

    # 签名稳定化 + 旧格式迁移
    sig = make_job_signature({"platform": "猎聘", "title": "无人机飞手",
                              "company": "测试公司", "location": "武汉-洪山区",
                              "url": "https://www.liepin.com/job/12345.shtml"})
    if sig != "url|liepin.com:12345.shtml":
        raise AssertionError(f"url签名应为 url|host:id 不含平台集合: {sig}")
    tsig = make_job_signature({"platform": "国聘", "title": "无人机飞手",
                               "company": "测试公司", "location": "武汉-洪山区", "url": ""})
    if not tsig.endswith("|武汉"):
        raise AssertionError(f"text签名地点应归一到城市: {tsig}")
    if _migrate_signature_key("url|前程无忧+猎聘|www.liepin.com:123.shtml") != "url|liepin.com:123.shtml":
        raise AssertionError("旧url签名迁移失败")
    if _migrate_signature_key("text|a公司|b岗位|武汉-洪山区") != "text|a公司|b岗位|武汉":
        raise AssertionError("旧text签名地点迁移失败")
    if normalize_location_city("武汉·洪山区") != "武汉":
        raise AssertionError("地点中的 · 必须作为城市分隔符")
    if normalize_title("无人机飞手（固定翼）") == normalize_title("无人机飞手（多旋翼）"):
        raise AssertionError("固定翼/多旋翼语义括注不应被签名归一化删除")
    if normalize_title("无人机飞手【五险一金】") != normalize_title("无人机飞手"):
        raise AssertionError("福利修饰括注应从签名中删除")
    nc_sig = make_job_signature({
        "platform": "猎聘", "title": "无人机飞手", "company": "",
        "salary": "8-10k", "location": "武汉", "url": "",
    }, prefer_url=False)
    if nc_sig != "nc|猎聘|无人机飞手|武汉|8-10k":
        raise AssertionError(f"无公司岗位签名必须包含平台和薪资: {nc_sig}")
    print("  signature stabilization ok")

    # 签名跨日状态：同日重跑不增天数，字段从空变有时补全基线并标记更新。
    state_job = {
        "platform": "猎聘", "title": "无人机飞手", "company": "测试公司",
        "salary": "8-10k", "location": "武汉", "url": "https://www.liepin.com/job/777.shtml",
        "keyword": "无人机飞手",
    }
    state_sig = make_job_signature(state_job)
    prior_state = {
        state_sig: {
            "first_seen": "2026-08-01", "last_seen": "2026-08-02",
            "seen_dates": ["2026-08-01", "2026-08-02"], "times": 9,
            "last_salary": "", "last_location": "",
        }
    }
    _, enriched, _, state_after = categorize_jobs(
        [dict(state_job)], "2026-08-02", previous_signatures=prior_state
    )
    if len(enriched) != 1 or state_after[state_sig]["times"] != 2:
        raise AssertionError(f"同日补全字段不应增加累计天数: {state_after[state_sig]}")
    _, _, repeated_again, state_after_again = categorize_jobs(
        [dict(state_job)], "2026-08-02", previous_signatures=state_after
    )
    if len(repeated_again) != 1 or state_after_again[state_sig]["times"] != 2:
        raise AssertionError(f"同日二次分类不应增加累计天数: {state_after_again[state_sig]}")

    # 主库损坏时只回退验证通过的备份；主备均坏必须 fail closed，且不改原字节。
    with tempfile.TemporaryDirectory(prefix="job-signature-selftest-") as sig_tmp:
        sig_path = os.path.join(sig_tmp, "signatures.json")
        backup_path = sig_path + ".bak"
        valid_backup = {
            "updated": "2026-08-02",
            "retention_days": 30,
            "total": 2,
            "signatures": {
                "url|旧平台|www.example.com:1": {
                    "first_seen": "2026-08-01", "last_seen": "2026-08-01", "times": 1,
                    "last_salary": "8k", "last_location": "武汉",
                },
                "url|example.com:1": {
                    "first_seen": "2026-08-01", "last_seen": "2026-08-02", "times": 2,
                    "last_salary": "10k", "last_location": "上海",
                },
            },
        }
        atomic_write_json(backup_path, valid_backup)
        corrupt_bytes = b"{not-json"
        with open(sig_path, "wb") as f:
            f.write(corrupt_bytes)
        recovered = load_previous_signatures(sig_path)
        merged = recovered.get("url|example.com:1", {})
        if len(recovered) != 1 or merged.get("last_salary") != "10k" or merged.get("last_location") != "上海":
            raise AssertionError(f"备份恢复或迁移撞键末次字段错误: {recovered}")
        with open(sig_path, "rb") as f:
            if f.read() != corrupt_bytes:
                raise AssertionError("仅加载备份时不得改写损坏主库原字节")
        with open(backup_path, "wb") as f:
            f.write(b"{also-bad")
        try:
            load_previous_signatures(sig_path)
        except SignatureStoreError:
            pass
        else:
            raise AssertionError("签名主备均损坏时必须 fail closed")
    print("  signature store ok (daily idempotency + validated backup)")

    # 公司缺失时禁止纯"标题+城市"跨平台合并
    nc_jobs = [
        {"platform": "猎聘", "title": "无人机飞手", "company": "", "salary": "8-10k",
         "location": "武汉", "url": "", "keyword": "无人机飞手"},
        {"platform": "智联招聘", "title": "无人机飞手", "company": "", "salary": "7-9k",
         "location": "武汉", "url": "", "keyword": "无人机飞手"},
    ]
    if len(deduplicate_jobs(nc_jobs)) != 2:
        raise AssertionError("公司缺失的同名岗不应被跨平台合并")
    # 稳定ID相同必合并（即使标题略有差异）
    id_jobs = [
        {"platform": "前程无忧", "title": "无人机飞手（急聘）", "company": "", "salary": "",
         "location": "", "url": "https://jobs.51job.com/all/888.html", "keyword": "CAAC"},
        {"platform": "前程无忧", "title": "无人机飞手", "company": "甲公司", "salary": "8k",
         "location": "武汉", "url": "https://jobs.51job.com/all/888.html", "keyword": "无人机飞手"},
    ]
    merged_id = deduplicate_jobs(id_jobs)
    if len(merged_id) != 1 or merged_id[0].get("company") != "甲公司":
        raise AssertionError(f"稳定ID合并或字段补全失败: {merged_id}")
    print("  dedupe hardening ok")

    # attach_job_urls：数量不一致时禁止位置匹配
    aj = [{"title": "无人机飞手", "url": ""}, {"title": "无人机教员", "url": ""}]
    fake_html = ('<a href="https://www.iguopin.com/x/1">a</a><a href="https://www.iguopin.com/x/2">b</a>'
                 '<a href="https://www.iguopin.com/x/3">c</a>')
    attach_job_urls(aj, fake_html, "国聘", search_url="https://search", keyword="t")
    if aj[0]["url"] != "https://search" or aj[1]["url"] != "https://search":
        raise AssertionError(f"数量不一致时应搜索页兜底而非错位挂链: {aj}")
    aj2 = [{"title": "无人机飞手", "url": ""}, {"title": "无人机教员", "url": ""}]
    fake_html2 = '<a href="https://www.iguopin.com/x/1">a</a><a href="https://www.iguopin.com/x/2">b</a>'
    attach_job_urls(aj2, fake_html2, "国聘", search_url="https://search", keyword="t")
    if aj2[0]["url"] != "https://www.iguopin.com/x/1":
        raise AssertionError(f"数量一致时应位置匹配: {aj2}")
    QUALITY_EVENTS.clear()  # 清掉自检产生的质量事件，避免污染
    print("  attach_job_urls guard ok")

    # 失败状态契约：浏览器失败和智联重试耗尽必须抛错，不能伪装成 []。
    original_browser_open = browser_open
    original_browser_close = browser_close
    original_run_browser = run_browser
    original_browser_get_text = browser_get_text
    original_browser_get_html = browser_get_html
    original_browser_get_links = browser_get_links
    original_safe_browser_task = safe_browser_task
    original_fetch_zhaopin_page = fetch_zhaopin_page
    original_read_open_browser_page = read_open_browser_page
    original_sleep = time.sleep
    try:
        globals()["browser_open"] = lambda *args, **kwargs: False
        globals()["browser_close"] = lambda: None
        time.sleep = lambda _seconds: None

        try:
            safe_browser_task("https://offline.test")
        except CrawlFetchError:
            pass
        else:
            raise AssertionError("safe_browser_task 页面打开失败时必须抛 CrawlFetchError")

        try:
            crawl_zhaopin("无人机飞手")
        except CrawlFetchError:
            pass
        else:
            raise AssertionError("智联重试耗尽时必须抛 CrawlFetchError")

        # 智联短 HTML 只要命中明确空结果文案，仍是合法真零。
        globals()["browser_open"] = lambda *args, **kwargs: True
        globals()["run_browser"] = lambda *args, **kwargs: ("", "", 0)
        globals()["browser_get_text"] = lambda *args, **kwargs: "很抱歉，您搜索的职位找不到！"
        globals()["browser_get_html"] = lambda *args, **kwargs: "<div>您搜索的职位找不到</div>"
        globals()["browser_get_links"] = lambda *args, **kwargs: {}
        if crawl_zhaopin("无人机飞手") != []:
            raise AssertionError("智联明确空结果短页面应返回合法真零 []")

        def liepin_card(job_id):
            return (
                '<div class="job-card-pc-container"><a data-nick="job-detail-job-info" '
                f'href="https://www.liepin.com/job/{job_id}.shtml">'
                f'<div title="无人机飞手{job_id}">无人机飞手{job_id}</div>'
                '<span>【</span><span>武汉</span><span>】</span><span>8-10k</span></a>'
                '<div data-nick="job-detail-company-info"><span class="ellipsis-1">测试公司</span></div></div>'
            )

        liepin_pages = {
            "0": "".join(liepin_card(index) for index in range(40)),
            "1": liepin_card(40),
        }
        liepin_urls = []

        def fake_liepin_fetch(url, **_kwargs):
            liepin_urls.append(url)
            page = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("currentPage", [""])[0]
            return "岗位结果", {}, liepin_pages[page]

        globals()["safe_browser_task"] = fake_liepin_fetch
        paged_liepin = crawl_liepin("无人机飞手")
        if len(paged_liepin) != 41 or len(liepin_urls) != 2:
            raise AssertionError(f"猎聘应抓取两页并在短页停止: jobs={len(paged_liepin)}, urls={liepin_urls}")

        def zhaopin_card(job_id, next_href=""):
            pager = (
                f'<div class="soupager"><a href="{next_href}" class="btn soupager__btn">下一页</a></div>'
                if next_href else
                '<div class="soupager"><a href="/p2" class="soupager__index soupager__index--active">2</a></div>'
            )
            padding = "x" * 10050
            return (
                '<div class="joblist-box__item"><a '
                f'href="https://www.zhaopin.com/jobdetail/{job_id}.htm" class="jobinfo__name">无人机飞手</a>'
                '<p class="jobinfo__salary">8-10k</p>'
                '<img class="jobinfo__other-info-location-image"><span>武汉</span>'
                '<a class="companyinfo__name">测试公司</a></div>' + pager + padding
            )

        zhaopin_pages = {
            "https://www.zhaopin.com/sou/?kw=%E6%97%A0%E4%BA%BA%E6%9C%BA%E9%A3%9E%E6%89%8B": zhaopin_card(
                "PAGE1", "https://www.zhaopin.com/sou/kwX/p2"
            ),
            "https://www.zhaopin.com/sou/kwX/p2": zhaopin_card("PAGE2"),
        }
        zhaopin_urls = []

        def fake_zhaopin_fetch(url, _page):
            zhaopin_urls.append(url)
            return "岗位结果", {}, zhaopin_pages[url]

        globals()["fetch_zhaopin_page"] = fake_zhaopin_fetch
        paged_zhaopin = crawl_zhaopin("无人机飞手")
        if len(paged_zhaopin) != 2 or zhaopin_urls[-1] != "https://www.zhaopin.com/sou/kwX/p2":
            raise AssertionError(f"智联应跟随真实下一页href: jobs={paged_zhaopin}, urls={zhaopin_urls}")

        guopin_page1 = (
            '<div class="job-card"><div class="job-name">无人机飞手甲</div>'
            '<div class="job-district">「武汉」</div><span class="job-salary">8K</span>'
            '<a class="company-name" href="/company?id=1">甲公司</a></div>'
            '<li title="下一页" class="ant-pagination-next" aria-disabled="false"><button>下一页</button></li>'
        )
        guopin_page2 = (
            '<div class="job-card"><div class="job-name">无人机飞手乙</div>'
            '<div class="job-district">「上海」</div><span class="job-salary">9K</span>'
            '<a class="company-name" href="/company?id=2">乙公司</a></div>'
            '<li title="下一页" class="ant-pagination-next ant-pagination-disabled" '
            'aria-disabled="true"><button disabled>下一页</button></li>'
        )
        globals()["safe_browser_task"] = lambda *args, **kwargs: ("岗位结果", {}, guopin_page1)
        globals()["read_open_browser_page"] = lambda *args, **kwargs: ("岗位结果", {}, guopin_page2)
        clicked_selectors = []

        def fake_guopin_click(args, **_kwargs):
            if args and args[0] == "click":
                clicked_selectors.append(args[1])
            return "", "", 0

        globals()["run_browser"] = fake_guopin_click
        paged_guopin = crawl_iguopin("无人机飞手")
        if len(paged_guopin) != 2:
            raise AssertionError(f"国聘应点击启用下一页并在disabled页停止: {paged_guopin}")
        if not clicked_selectors or '[aria-disabled="false"]' not in clicked_selectors[0]:
            raise AssertionError(f"国聘点击选择器必须要求显式启用证据: {clicked_selectors}")
        print("  pagination loops ok (link/click/cap guards)")
    finally:
        globals()["browser_open"] = original_browser_open
        globals()["browser_close"] = original_browser_close
        globals()["run_browser"] = original_run_browser
        globals()["browser_get_text"] = original_browser_get_text
        globals()["browser_get_html"] = original_browser_get_html
        globals()["browser_get_links"] = original_browser_get_links
        globals()["safe_browser_task"] = original_safe_browser_task
        globals()["fetch_zhaopin_page"] = original_fetch_zhaopin_page
        globals()["read_open_browser_page"] = original_read_open_browser_page
        time.sleep = original_sleep

    if detect_security_marker("normal page uses Cloudflare analytics"):
        raise AssertionError("正常页面仅含 Cloudflare 厂商名不应误判安全拦截")
    if not detect_security_marker("CLOUDFLARE - Checking your browser"):
        raise AssertionError("Cloudflare 挑战页应被大小写无关地识别")

    def failed_crawler(_keyword):
        raise CrawlFetchError("离线模拟抓取失败")

    test_job = {
        "platform": "成功平台",
        "title": "无人机飞手",
        "company": "测试公司",
        "salary": "8-10k",
        "location": "武汉",
        "url": "https://example.test/job/1",
        "keyword": "无人机飞手",
    }

    # 全失败：raw_counts 必须全 -1，并触发全失守卫。
    failed_jobs, failed_counts = crawl_all(
        platform_crawlers=[("失败平台A", failed_crawler), ("失败平台B", failed_crawler)],
        keywords=["无人机飞手"],
        pause_seconds=0,
    )
    if failed_jobs or set(failed_counts.values()) != {-1}:
        raise AssertionError(f"全失败应记录为 -1: jobs={failed_jobs}, counts={failed_counts}")
    try:
        validate_crawl_results(failed_counts)
    except CrawlFetchError:
        pass
    else:
        raise AssertionError("raw_counts 全 -1 时必须触发全失守卫")

    # 合法真零：成功返回 [] 必须保留为 0，且不得触发全失守卫。
    zero_jobs, zero_counts = crawl_all(
        platform_crawlers=[("真零平台A", lambda _keyword: []), ("真零平台B", lambda _keyword: [])],
        keywords=["无人机飞手"],
        pause_seconds=0,
    )
    if zero_jobs or set(zero_counts.values()) != {0}:
        raise AssertionError(f"合法真零应记录为 0: jobs={zero_jobs}, counts={zero_counts}")
    validate_crawl_results(zero_counts)

    # 失败 + 真零且没有任何岗位：结果仍不可信，必须阻断 0 岗位日报。
    mixed_zero_counts = {"失败平台|无人机飞手": -1, "真零平台|无人机飞手": 0}
    try:
        validate_crawl_results(mixed_zero_counts)
    except CrawlFetchError:
        pass
    else:
        raise AssertionError("存在失败且没有正数结果时必须阻断 0 岗位日报")

    # 部分失败：失败组合为 -1，真零为 0，成功组合保留正数，不触发全失守卫。
    partial_jobs, partial_counts = crawl_all(
        platform_crawlers=[
            ("失败平台", failed_crawler),
            ("真零平台", lambda _keyword: []),
            ("成功平台", lambda _keyword: [dict(test_job)]),
        ],
        keywords=["无人机飞手"],
        pause_seconds=0,
    )
    expected_counts = {
        "失败平台|无人机飞手": -1,
        "真零平台|无人机飞手": 0,
        "成功平台|无人机飞手": 1,
    }
    if len(partial_jobs) != 1 or partial_counts != expected_counts:
        raise AssertionError(f"部分失败状态错误: jobs={partial_jobs}, counts={partial_counts}")
    validate_crawl_results(partial_counts, max_failed_rate=1.0)

    # 即便其他平台有正数结果，任一配置平台全部关键词失败仍应阻断不完整日报。
    failed_platform = configured_platform_names()[0]
    platform_failed_counts = {f"{failed_platform}|{keyword}": -1 for keyword in KEYWORDS}
    platform_failed_counts[f"{configured_platform_names()[1]}|{KEYWORDS[0]}"] = 1
    try:
        validate_crawl_results(platform_failed_counts, max_failed_rate=1.0)
    except CrawlFetchError:
        pass
    else:
        raise AssertionError("任一配置平台全部关键词失败时必须阻断发布")

    # 未知代码异常不能降级成组合失败，必须让整次运行失败。
    def broken_crawler(_keyword):
        raise ValueError("离线模拟代码缺陷")

    try:
        crawl_all(
            platform_crawlers=[("代码缺陷平台", broken_crawler)],
            keywords=["无人机飞手"],
            pause_seconds=0,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("未知代码异常必须越过 crawl_all 降级边界")
    QUALITY_EVENTS.clear()
    print("  crawl failure contract ok (-1 failure / 0 valid empty / positive success)")

    # 报告口径：唯一岗位不膨胀，关键词/平台贡献按非互斥维度分别计数。
    contribution_job = {
        "platform": "猎聘/智联招聘",
        "platforms": ["猎聘", "智联招聘"],
        "cross_platform": True,
        "title": "无人机飞手",
        "company": "测试公司",
        "salary": "8-12k",
        "location": "武汉",
        "url": "https://www.liepin.com/job/12345.shtml",
        "keyword": "CAAC",
        "keywords": ["CAAC", "无人机飞手"],
    }
    contribution_report = build_report([dict(contribution_job)], [], [], "2026-08-03")
    _, _, keyword_counts, platform_counts = build_reference_summary(contribution_report)
    if contribution_report["total"] != 1:
        raise AssertionError(f"多维贡献不应膨胀唯一岗位数: {contribution_report['total']}")
    if keyword_counts != {"CAAC": 1, "无人机飞手": 1}:
        raise AssertionError(f"关键词非互斥贡献错误: {keyword_counts}")
    if platform_counts != {"猎聘": 1, "智联招聘": 1}:
        raise AssertionError(f"平台非互斥贡献错误: {platform_counts}")
    contribution_markdown = build_docx_markdown(contribution_report, "2026-08-03")
    if "非互斥" not in contribution_markdown:
        raise AssertionError("报告未标明关键词/平台贡献为非互斥口径")

    repeated_report = build_report([], [], [dict(contribution_job)], "2026-08-03")
    repeated_markdown = build_docx_markdown(repeated_report, "2026-08-03")
    for expected in ("武汉", "8-12k", "https://www.liepin.com/job/12345.shtml"):
        if expected not in repeated_markdown:
            raise AssertionError(f"持续在招条目缺少可行动信息: {expected}")

    volume_events = detect_volume_drops(
        {"猎聘|无人机飞手": 3},
        [
            {"date": "2026-07-30", "raw_counts": {"猎聘|无人机飞手": 20}},
            {"date": "2026-07-31", "raw_counts": {"猎聘|无人机飞手": 20}},
            {"date": "2026-08-01", "raw_counts": {"猎聘|无人机飞手": 20}},
        ],
        today_str="2026-08-03",
    )
    if len(volume_events) != 1 or volume_events[0].get("metric") != "volume_drop":
        raise AssertionError(f"滚动基线突降应产生且仅产生一个 volume_drop: {volume_events}")

    QUALITY_EVENTS.clear()
    try:
        record_quality_event(
            "猎聘", "无人机飞手", "no_relevant_jobs", 0, None, "离线信息型事件"
        )
        event_quality = analyze_quality([dict(contribution_job)])
        if not any(event.get("metric") == "no_relevant_jobs" for event in event_quality["info"]):
            raise AssertionError("no_relevant_jobs 应进入 info")
        if any(event.get("metric") == "no_relevant_jobs" for event in event_quality["warnings"]):
            raise AssertionError("no_relevant_jobs 不应进入 warnings")
    finally:
        QUALITY_EVENTS.clear()
    print("  quality reporting ok (non-exclusive + actionable repeats + rolling alerts)")

    quality = analyze_quality(deduped)
    today_str = datetime.date.today().isoformat()
    report = build_report(deduped, [], [], today_str, quality=quality)

    unsafe_job = {
        "platform": "猎聘",
        "title": "无人机\n# [恶意](https://evil.test)\u202e",
        "company": "测试|**公司**",
        "salary": "8-10k\x00",
        "location": "武汉\r\n洪山",
        "url": "https://evil.test/job/1",
        "keyword": "无人机飞手",
    }
    unsafe_report = build_report([unsafe_job], [], [], today_str)
    public_unsafe_job = unsafe_report["jobs"][0]
    if "\n" in public_unsafe_job["title"] or "\u202e" in public_unsafe_job["title"]:
        raise AssertionError("外部岗位字段未清理换行或 Unicode 控制字符")
    if public_unsafe_job["url"]:
        raise AssertionError("越出岗位来源平台白名单的 URL 未被移除")
    for rendered in (
        build_docx_markdown(unsafe_report, today_str),
        build_markdown(unsafe_report),
    ):
        if "[恶意](https://evil.test)" in rendered or "\n# [恶意]" in rendered:
            raise AssertionError("外部岗位字段可注入 Markdown")
        if r"\[恶意\]\(https://evil.test\)" not in rendered:
            raise AssertionError("外部 Markdown 字段未按预期转义")
    allowed_url = "https://www.liepin.com/job/12345.shtml"
    allowed_report = build_report(
        [dict(unsafe_job, title="无人机飞手", url=allowed_url)], [], [], today_str
    )
    if allowed_url not in build_docx_markdown(allowed_report, today_str):
        raise AssertionError("平台白名单内的岗位 URL 被误删")
    print("  external field sanitization ok (controls + markdown + URL allowlist)")

    # 发布事务离线回归：不调用 lark-cli、不写真实签名/历史。
    with tempfile.TemporaryDirectory(prefix="job-crawler-selftest-") as tmp_dir:
        receipt_path = os.path.join(tmp_dir, "publish.json")
        history_path = os.path.join(tmp_dir, "history.jsonl")
        calls = []

        def test_create(_report, _today):
            calls.append("create")
            return "https://example.test/doc", "doc_test_123"

        def test_grant(_doc_id):
            calls.append("grant")
            return {"ok": True, "success": 2, "total": 2, "failures": []}

        def test_send(_markdown):
            calls.append("send")
            return "om_test_123"

        def test_save(_signatures, _today):
            calls.append("save")

        def test_history(_today, _counts, _report, _receipt):
            calls.append("history")

        publish_receipt = publish_report(
            report,
            today_str,
            {"测试平台|测试词": 1},
            {},
            receipt_path=receipt_path,
            create_doc_fn=test_create,
            grant_permissions_fn=test_grant,
            send_message_fn=test_send,
            save_signatures_fn=test_save,
            append_history_fn=test_history,
        )
        if calls != ["create", "grant", "send", "save", "history"]:
            raise AssertionError(f"发布动作顺序错误: {calls}")
        if publish_receipt.get("status") != "published" or publish_receipt.get("stage") != "complete":
            raise AssertionError(f"发布收据终态错误: {publish_receipt}")
        action, _ = publication_guard(
            today_str,
            receipt_path=receipt_path,
            history_path=history_path,
        )
        if action != "skip":
            raise AssertionError(f"同日成功收据必须跳过重复发布: {action}")

        # 模拟群消息已送达后被 SIGKILL/断电：收据停在 delivered，
        # 且重跑抓取结果可能已变。只要 message_id 存在就必须失败关闭。
        interrupted_receipt_path = os.path.join(tmp_dir, "hard-interrupt.json")
        atomic_write_json(interrupted_receipt_path, {
            "date": today_str,
            "status": "delivered",
            "stage": "message_delivered",
            "message_id": "om_interrupted_123",
            "report_fingerprint": "previous-report-fingerprint",
        })
        interrupted_action, _ = publication_guard(
            today_str,
            receipt_path=interrupted_receipt_path,
            history_path=history_path,
        )
        if interrupted_action != "block":
            raise AssertionError(f"硬中断后的 message_id 收据必须阻断重发: {interrupted_action}")
        interrupted_calls = []
        try:
            publish_report(
                dict(report, total=report["total"] + 1),
                today_str,
                {},
                {},
                receipt_path=interrupted_receipt_path,
                create_doc_fn=lambda *_args: interrupted_calls.append("create"),
                grant_permissions_fn=lambda *_args: interrupted_calls.append("grant"),
                send_message_fn=lambda *_args: interrupted_calls.append("send"),
                save_signatures_fn=lambda *_args: interrupted_calls.append("save"),
                append_history_fn=lambda *_args: interrupted_calls.append("history"),
            )
        except PublishError:
            pass
        else:
            raise AssertionError("硬中断收据后直接调用 publish_report 也必须失败关闭")
        if interrupted_calls:
            raise AssertionError(f"硬中断收据后不应执行任何外部动作: {interrupted_calls}")

        # 建档没有可信 ID/URL 时，授权、消息、签名和历史都不得执行。
        failed_receipt_path = os.path.join(tmp_dir, "create-failed.json")
        downstream_calls = []
        try:
            publish_report(
                report,
                today_str,
                {},
                {},
                receipt_path=failed_receipt_path,
                create_doc_fn=lambda _report, _today: (None, None),
                grant_permissions_fn=lambda _doc_id: downstream_calls.append("grant"),
                send_message_fn=lambda _markdown: downstream_calls.append("send"),
                save_signatures_fn=lambda _sigs, _today: downstream_calls.append("save"),
                append_history_fn=lambda *_args: downstream_calls.append("history"),
            )
        except PublishError:
            pass
        else:
            raise AssertionError("建档无回执时必须发布失败")
        if downstream_calls:
            raise AssertionError(f"建档失败后不应执行下游动作: {downstream_calls}")

        # 群消息失败不写签名/历史；同报告恢复时复用文档和授权，不重复建档。
        resume_receipt_path = os.path.join(tmp_dir, "resume.json")
        resume_calls = []

        def resume_create(_report, _today):
            resume_calls.append("create")
            return "https://example.test/resume", "doc_resume_123"

        def resume_grant(_doc_id):
            resume_calls.append("grant")
            return {"ok": True, "success": 1, "total": 1, "failures": []}

        def failed_send(_markdown):
            resume_calls.append("send_fail")
            raise PublishError("离线模拟群消息失败")

        try:
            publish_report(
                report,
                today_str,
                {},
                {},
                receipt_path=resume_receipt_path,
                create_doc_fn=resume_create,
                grant_permissions_fn=resume_grant,
                send_message_fn=failed_send,
                save_signatures_fn=lambda *_args: resume_calls.append("save_unexpected"),
                append_history_fn=lambda *_args: resume_calls.append("history_unexpected"),
            )
        except PublishError:
            pass
        else:
            raise AssertionError("群消息失败必须使发布失败")
        if resume_calls != ["create", "grant", "send_fail"]:
            raise AssertionError(f"群消息失败后的动作边界错误: {resume_calls}")

        publish_report(
            report,
            today_str,
            {},
            {},
            receipt_path=resume_receipt_path,
            create_doc_fn=lambda *_args: (_ for _ in ()).throw(AssertionError("恢复时不应重复建档")),
            grant_permissions_fn=lambda *_args: (_ for _ in ()).throw(AssertionError("恢复时不应重复授权")),
            send_message_fn=lambda _markdown: resume_calls.append("send_ok") or "om_resume_123",
            save_signatures_fn=lambda *_args: resume_calls.append("save"),
            append_history_fn=lambda *_args: resume_calls.append("history"),
        )
        if resume_calls != ["create", "grant", "send_fail", "send_ok", "save", "history"]:
            raise AssertionError(f"失败恢复未复用已有文档/授权: {resume_calls}")
    print("  publish transaction ok (idempotent + gated + resumable)")

    md = build_docx_markdown(report, today_str)
    if "数据质量" not in md:
        raise AssertionError("报告缺少数据质量章节")
    print("SELF_TEST ok")
    return 0


def replay_snapshot(argv):
    """
    离线回放快照：--replay <快照.html> [平台] [关键词]
    不触发浏览器和飞书，用于解析器修复后的回归验证。
    文件名符合快照约定（日期_平台_关键词_原因_摘要.html）时可省略平台/关键词。
    """
    global SNAPSHOT_DISABLED
    SNAPSHOT_DISABLED = True

    parsers = {
        "猎聘": parse_liepin_html,
        "前程无忧": parse_51job_html,
        "智联招聘": parse_zhaopin_html,
        "国聘": parse_iguopin_html,
    }
    args = [a for a in argv[argv.index("--replay") + 1:] if not a.startswith("--")]
    if not args:
        print("用法: --replay <快照.html> [平台] [关键词]")
        print(f"支持平台: {'、'.join(parsers)}")
        return 2
    path = expand_path(args[0])
    if not os.path.isfile(path):
        print(f"快照不存在: {path}")
        return 2

    parts = os.path.basename(path).split("_")
    platform = args[1] if len(args) > 1 else (parts[1] if len(parts) >= 3 else "")
    keyword = args[2] if len(args) > 2 else (parts[2] if len(parts) >= 3 else "")
    parser = parsers.get(platform)
    if not parser:
        print(f"无法识别平台「{platform}」，请显式指定: --replay <文件> <平台> [关键词]")
        print(f"支持平台: {'、'.join(parsers)}")
        return 2

    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    jobs = parser(html, keyword)

    print(f"REPLAY {platform}/{keyword} ← {os.path.basename(path)}")
    if not jobs:
        print("  解析到 0 个岗位（页面无相关岗位，或解析器不匹配该快照结构）")
        return 1
    n = len(jobs)
    cov = {k: sum(1 for j in jobs if j.get(k)) for k in ("url", "company", "salary", "location")}
    print(f"  岗位 {n} 个 | 链接 {cov['url']}/{n} | 公司 {cov['company']}/{n} | 薪资 {cov['salary']}/{n} | 地点 {cov['location']}/{n}")
    for i, j in enumerate(jobs, 1):
        print(f"  {i:2d}. {j['title']} | {j.get('salary') or '-'} | {j.get('location') or '-'} | {j.get('company') or '-'}")
        if j.get("url"):
            print(f"      {j['url']}")
    return 0


# ============================================================
# 主函数
# ============================================================

def main():
    if "--self-test" in sys.argv:
        return self_test()
    if "--replay" in sys.argv:
        return replay_snapshot(sys.argv)

    dry_run = "--dry-run" in sys.argv
    force_publish = "--force" in sys.argv
    validate_runtime_config(require_feishu=not dry_run)

    today = datetime.date.today()
    today_str = today.isoformat()
    print(f"\n{'*'*60}")
    print(f"  招聘岗位爬虫 - 开始执行")
    print(f"  日期: {today_str}")
    if dry_run:
        print(f"  模式: DRY-RUN（真实爬取，但不写签名、不发飞书）")
    print(f"  工作目录: {os.getcwd()}")
    print(f"{'*'*60}")

    try:
        if not dry_run:
            guard_action, guard_receipt = publication_guard(today_str, force=force_publish)
            if guard_action == "skip":
                print("  [IDEMPOTENT] 今日日报已有成功投递收据，跳过爬取与重复发布")
                return 0
            if guard_action == "block":
                raise PublishError(
                    "今日日报已有群消息回执，但本地收尾失败；为避免重复通知已阻断重跑，"
                    "请修复收尾状态或显式使用 --force"
                )

        # 0. 浏览器可用性硬校验：三条路径全缺时拒绝以"0岗位成功日报"继续
        if not os.path.isfile(AGENT_BROWSER):
            raise RuntimeError(
                f"agent-browser 不可用: {AGENT_BROWSER}（主路径与全部备用路径均缺失），"
                f"请检查 npm 全局前缀或修正 config 的 agent_browser 路径"
            )

        # 0.5 清理过期快照（按 snapshot_retention_days）
        if not dry_run:
            purge_old_snapshots()

        # 1. 爬取所有岗位
        jobs, raw_counts = crawl_all()

        # 1.5 全失守卫：失败(-1)与合法真零(0)严格区分。
        validate_crawl_results(raw_counts)

        # 2. 跨日分类检测（新增/更新/持续在招）
        new_jobs, updated_jobs, repeated_jobs, updated_sigs = categorize_jobs(jobs, today_str)

        # 3. 数据质量分析（签名保存延后到日报文档创建成功之后：
        #    发布失败当天不落签名，避免这批岗位次日被误判"持续在招"而员工从未见过）
        quality = analyze_quality(jobs, raw_counts=raw_counts, today_str=today_str)
        quality["warnings"] = annotate_warning_streaks(quality.get("warnings", []), today_str)

        # 4. 构建报告（含分类信息和质量信息）
        report = build_report(new_jobs, updated_jobs, repeated_jobs, today_str, quality=quality)

        # 5. 打印摘要到控制台
        print_summary(report)

        if dry_run:
            print("  [DRY-RUN] 跳过签名保存")
            print(f"\n{'*'*60}")
            print(f"  ✅ DRY-RUN 完成：已跳过飞书文档/群消息/授权")
            print(f"{'*'*60}")
            return 0

        # 6. 端到端发布门禁：建档→授权→群回执→签名→成功历史。
        receipt = publish_report(
            report,
            today_str,
            raw_counts,
            updated_sigs,
            force=force_publish,
        )

        print(f"\n{'*'*60}")
        print(f"  ✅ 执行完成，日报已发布！")
        print(
            f"  📬 发布收据: doc={mask_identifier(receipt.get('docx_id'))}, "
            f"message={mask_identifier(receipt.get('message_id'))}"
        )
        print(f"{'*'*60}")

        return 0

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        print(f"\n❌ 严重错误: {error_msg}", file=sys.stderr)
        # 失败通知由 cron_detached_runner 统一发送并校验 message_id，
        # 避免爬虫本体与 runner 同时向群里重复告警。
        return 1


if __name__ == "__main__":
    sys.exit(main())
