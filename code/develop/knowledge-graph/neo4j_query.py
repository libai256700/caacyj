#!/usr/bin/env python3
"""
云技 Neo4j 知识图谱实体查询脚本
用法:
  python3 neo4j_query.py "起飞前准备"               → 纯文本输出
  python3 neo4j_query.py --json "起飞前准备"        → JSON 输出
  python3 neo4j_query.py --keywords "起飞 检查"     → 指定关键词（空格分隔）
  python3 neo4j_query.py --stats                    → 实体类型统计
  from neo4j_query import query_entities            → Python 模块导入

走脚本层查 Neo4j，不直连数据库密码。适合在 RAG 查询后补充图谱侧信息。
输出: 匹配实体详情 + 来源文档
退出码: 0=成功, 1=失败
"""

import sys, json, os, logging, re
from neo4j import GraphDatabase, Query

# --- 配置（环境变量覆盖） ---
NEO4J_PASS_FILE = os.path.join(os.path.dirname(__file__), "neo4j", ".neo4j_pass")
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
MAX_RESULTS = int(os.environ.get("NEO4J_MAX_RESULTS", "20"))
NEO4J_TIMEOUT = float(os.environ.get("NEO4J_TIMEOUT", "2"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("neo4j_query")


def get_pass() -> str:
    """读取 Neo4j 密码（文件优先，环境变量兜底）"""
    try:
        with open(NEO4J_PASS_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return os.environ.get("NEO4J_PASS", "")


# 停用词列表（精简版）
_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "也", "都",
    "要", "什么", "怎么", "如何", "吗", "呢", "啊", "吧", "那", "这",
    "为", "而", "所", "与", "上", "下", "来", "去", "没", "把", "被",
    "让", "给", "能", "会", "可以", "应该", "需要", "一个", "一些",
    "这个", "那个", "这些", "那些", "一下",
})


def extract_keywords(text: str, max_kw: int = 5) -> list:
    """从自然语言问题中提取关键词
    
    自动拆解长词（>4字）为2字前缀子词提高匹配率。
    如「起飞前的准备」→ 保留原词 + 拆出「起飞」「起飞前」「准备」
    """
    words = re.findall(r'[\u4e00-\u9fff\w]+', text)
    result = []
    seen = set()
    for w in words:
        if len(w) >= 2 and w not in _STOPWORDS:
            if w not in seen:
                result.append(w)
                seen.add(w)
            # 长词拆出2字前缀 + 3字前缀
            if len(w) > 4:
                for i in range(2, min(len(w), 5)):
                    sub = w[:i]
                    if sub not in seen and sub not in _STOPWORDS:
                        result.append(sub)
                        seen.add(sub)
            # 如果带「的」「和」「与」，拆出后半段
            for sep in ('的', '和', '与', '及'):
                if sep in w:
                    parts = w.split(sep)
                    for p in parts:
                        if len(p) >= 2 and p not in seen and p not in _STOPWORDS:
                            result.append(p)
                            seen.add(p)
    return result[:max_kw]


def query_entities(question: str, keywords: list = None) -> dict:
    """查询 Neo4j 中与问题匹配的 Skill / KnowledgePoint / Section / Scenario 等实体。

    Args:
        question: 用户原始问题（关键词自动提取）
        keywords: 手动覆写关键词（优先级更高）

    Returns:
        成功: {"ok": True, "question": ..., "query_keywords": [...],
               "entities": [{name, types, description, source_doc, id}],
               "entity_count": N, "source_docs": [...], "doc_count": N}
        失败: {"ok": False, "error": ...}
    """
    if not keywords:
        keywords = extract_keywords(question)

    password = get_pass()
    if not password:
        return {"ok": False, "error": "无法读取 Neo4j 密码"}

    try:
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, password),
            connection_timeout=NEO4J_TIMEOUT,
        )
        seen = set()
        entities = []
        source_docs = set()

        with driver.session() as session:
            per_kw = max(MAX_RESULTS // max(len(keywords), 1) + 1, 2)

            for kw in keywords:
                result = session.run(
                    Query(
                        """MATCH (n)
                    WHERE (n:Skill OR n:KnowledgePoint)
                      AND n.name CONTAINS $kw
                    RETURN n.name AS name,
                           [l IN labels(n) WHERE l <> 'Entity'] AS types,
                           n.description AS description,
                           n.source_doc AS source_doc,
                           n.id AS id
                    LIMIT $limit""",
                        timeout=NEO4J_TIMEOUT,
                    ),
                    kw=kw, limit=per_kw,
                )
                for rec in result:
                    key = rec["name"]
                    if key in seen:
                        continue
                    seen.add(key)
                    entities.append({
                        "name": rec["name"],
                        "types": rec["types"],
                        "description": rec["description"],
                        "source_doc": rec["source_doc"],
                        "id": rec["id"],
                    })
                    if rec["source_doc"]:
                        source_docs.add(rec["source_doc"])

            # 结果太少时放宽到 Section/Scenario
            if len(entities) <= 2:
                for kw in keywords:
                    result = session.run(
                        Query(
                            """MATCH (n)
                        WHERE (n:Section OR n:Scenario)
                          AND n.name CONTAINS $kw
                        RETURN n.name AS name,
                               [l IN labels(n) WHERE l <> 'Entity'] AS types,
                               n.description AS description,
                               n.source_doc AS source_doc,
                               n.id AS id
                        LIMIT $limit""",
                            timeout=NEO4J_TIMEOUT,
                        ),
                        kw=kw, limit=per_kw,
                    )
                    for rec in result:
                        key = rec["name"]
                        if key in seen:
                            continue
                        seen.add(key)
                        entities.append({
                            "name": rec["name"],
                            "types": rec["types"],
                            "description": rec["description"],
                            "source_doc": rec["source_doc"],
                            "id": rec["id"],
                        })
                        if rec["source_doc"]:
                            source_docs.add(rec["source_doc"])

            entities = entities[:MAX_RESULTS]
            driver.close()

        log.info(
            f"QUERY OK | q={question[:30]} | "
            f"kw={keywords} | ent={len(entities)} | doc={len(source_docs)}"
        )

        return {
            "ok": True,
            "question": question,
            "query_keywords": keywords,
            "entities": entities,
            "entity_count": len(entities),
            "source_docs": sorted(source_docs),
            "doc_count": len(source_docs),
        }

    except Exception as e:
        log.error(f"QUERY FAIL | q={question[:30]} | {e}")
        return {"ok": False, "error": f"Neo4j 查询失败: {e}"}


# --- CLI ---
if __name__ == "__main__":
    import sys

    use_json = False
    manual_kw = None
    show_stats = False
    args = sys.argv[1:]

    if "--json" in args:
        use_json = True
        args.remove("--json")
    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)
    if "--keywords" in args:
        i = args.index("--keywords")
        args.pop(i)
        manual_kw = args.pop(i).split()
    if "--stats" in args:
        show_stats = True
        args.remove("--stats")

    question = args[0] if args else "无人机"

    if show_stats:
        password = get_pass()
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, password))
        with driver.session() as session:
            rows = session.run(
                Query(
                    """MATCH (n)
                WHERE n:Skill OR n:KnowledgePoint OR n:Section OR n:Scenario
                RETURN [l IN labels(n) WHERE l <> 'Entity'] AS types,
                       count(*) AS cnt
                ORDER BY cnt DESC""",
                    timeout=NEO4J_TIMEOUT,
                )
            )
            stats = {".".join(r["types"]): r["cnt"] for r in rows}
        driver.close()
        if use_json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print("📊 Neo4j 实体统计:")
            for t, c in stats.items():
                print(f"  · {t}: {c} 节点")
        sys.exit(0)

    result = query_entities(question, manual_kw)

    if result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            ents = result["entities"]
            if not ents:
                print(f"🔍 未找到与「{question}」匹配的实体")
            else:
                kw_str = ", ".join(result["query_keywords"])
                print(f"🔍 找到 {result['entity_count']} 个匹配实体（关键词: {kw_str}）\n")
                for i, e in enumerate(ents, 1):
                    t_str = "/".join(e["types"]) if e["types"] else "Entity"
                    print(f"{i}. {e['name']} ({t_str})")
                    if e["description"]:
                        print(f"   📝 {e['description'][:200]}")
                    if e["source_doc"]:
                        print(f"   📄 来源: {e['source_doc']}")
                    print()
                if result["source_docs"]:
                    print(f"📚 来源文档（{result['doc_count']}）:")
                    for d in result["source_docs"]:
                        print(f"  · {d}")
        sys.exit(0)
    else:
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"❌ {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)
