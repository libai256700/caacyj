#!/usr/bin/env python3
"""导入飞书数据到Neo4j知识图谱"""

import re
import json
import urllib.request
import urllib.error
import sys
import traceback

NEO4J_URL = "http://localhost:7474/db/neo4j/tx/commit"
NEO4J_AUTH = "Basic " + __import__('base64').b64encode(b"neo4j:yj123456").decode()

def neo4j_query(statements):
    """执行Cypher语句，statements是列表"""
    payload = json.dumps({"statements": [{"statement": s} for s in statements]}).encode()
    req = urllib.request.Request(NEO4J_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": NEO4J_AUTH})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"❌ Neo4j Error: {body[:500]}")
        raise

def clear_old_data():
    """清理旧的飞书导入数据（按source_platform=feishu）"""
    queries = [
        "MATCH (d:Document {source_platform: 'feishu'}) DETACH DELETE d",
        "MATCH (p:Position {source_platform: 'feishu'}) DETACH DELETE p",
        "MATCH (c:SocialContent {source_platform: 'feishu'}) DETACH DELETE c",
        "MATCH (a:SocialAccount {source_platform: 'feishu'}) DETACH DELETE a",
        "MATCH (p:PlatformPresence {source_platform: 'feishu'}) DETACH DELETE p",
    ]
    for q in queries:
        try:
            neo4j_query([q])
        except:
            pass
    print("✅ 已清理旧数据")

# ============================================================
# Task 1: 岗位报告入库
# ============================================================
def parse_position_report(filepath):
    """解析岗位报告，提取每个岗位的：名称、公司、薪资、地点、链接、来源平台、分类"""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # 提取报告标题和日期
    title_match = re.search(r'每日岗位信息报告[_\s]*(\d{4}-\d{2}-\d{2})', text)
    report_date = title_match.group(1) if title_match else "unknown"
    doc_name = f"每日岗位信息报告_{report_date}"

    positions = []
    current_category = ""  # "CAAC优先" or "低门槛" or "其他"

    # 匹配分类标题
    category_patterns = [
        (r'🏆\s*CAAC\s*执照优先推荐?', 'CAAC执照优先'),
        (r'📌\s*低门槛岗位推荐?', '低门槛'),
        (r'📌\s*其他岗位', '其他'),
    ]

    # 按行解析
    lines = text.split('\n')

    # 岗位正则：编号. 名称 | 公司 | 💰薪资 | 📍地点(可选)
    pos_pattern = re.compile(
        r'^(\d+)\.\s+(.+?)\s+\|\s+(.+?)\s+\|\s*💰([\d\-,.km万wK千]+)\s*(?:\|\s*📍(.+))?$'
    )
    # 更宽松的匹配：有些行格式不太标准
    pos_pattern2 = re.compile(
        r'^(\d+)\.\s+(.+?)\s+\|\s+(.+?)\s+\|\s*💰([\d\-,.km万wK千]+)'
    )

    link_pattern = re.compile(r'🔗\s*\[(.+?)\]\s+(https?://[^\s]+)')
    edu_pattern = re.compile(r'📝\s+(.+)')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 检测分类
        for pat, cat_name in category_patterns:
            if re.search(pat, line):
                current_category = cat_name
                break

        # 检测岗位行
        m = pos_pattern.match(line)
        if not m:
            m = pos_pattern2.match(line)

        if m:
            idx = m.group(1)
            name = m.group(2).strip()
            company = m.group(3).strip()
            salary = m.group(4).strip()
            location = m.group(5).strip() if len(m.groups()) >= 5 and m.group(5) else ""

            # 查找链接（下一行或下几行）
            link = ""
            source_plat = ""
            for j in range(i+1, min(i+5, len(lines))):
                lm = link_pattern.search(lines[j])
                if lm:
                    source_plat = lm.group(1).strip()
                    link = lm.group(2).strip()
                    break

            # 查找学历/经验（下几行）
            education = ""
            for j in range(i+1, min(i+6, len(lines))):
                em = edu_pattern.match(lines[j].strip())
                if em:
                    education = em.group(1).strip()
                    break

            # 清理公司名（有些行包含更多噪音）
            # 截断过长的公司名
            if len(company) > 80:
                company = company[:80] + "..."

            positions.append({
                'idx': idx,
                'name': name,
                'company': company,
                'salary': salary,
                'location': location,
                'link': link,
                'source_platform': source_plat,
                'education': education,
                'category': current_category,
            })

        i += 1

    return doc_name, report_date, positions

def import_positions_to_neo4j(report_data_list):
    """将多个报告的岗位数据导入Neo4j"""
    all_queries = []
    stats = {"documents": 0, "positions": 0}

    for filepath in report_data_list:
        doc_name, report_date, positions = parse_position_report(filepath)

        # 创建Document节点
        all_queries.append(f"""
        CREATE (d:Document {{
            name: '{escape_cypher(doc_name)}',
            report_date: '{report_date}',
            source_platform: 'feishu',
            total_positions: {len(positions)},
            import_time: timestamp()
        }})
        """)
        stats["documents"] += 1

        # 创建每个Position节点并关联
        for pos in positions:
            safe_name = escape_cypher(pos['name'][:200])
            safe_company = escape_cypher(pos['company'][:200])
            safe_location = escape_cypher(pos['location'][:100])
            safe_link = escape_cypher(pos['link'][:500])
            safe_edu = escape_cypher(pos['education'][:200])
            safe_cat = escape_cypher(pos['category'][:50])
            safe_src = escape_cypher(pos['source_platform'][:50])

            all_queries.append(f"""
            MATCH (d:Document {{name: '{escape_cypher(doc_name)}'}})
            CREATE (p:Position {{
                entityType: 'Position',
                name: '{safe_name}',
                company: '{safe_company}',
                salary: '{escape_cypher(pos["salary"][:50])}',
                location: '{safe_location}',
                url: '{safe_link}',
                education_requirement: '{safe_edu}',
                category: '{safe_cat}',
                source_job_platform: '{safe_src}',
                report_date: '{report_date}',
                source_platform: 'feishu',
                import_time: timestamp()
            }})
            CREATE (d)-[:CONTAINS]->(p)
            """)
            stats["positions"] += 1

    # 批量执行（每50条一批）
    batch_size = 50
    for batch_start in range(0, len(all_queries), batch_size):
        batch = all_queries[batch_start:batch_start + batch_size]
        neo4j_query(batch)
        print(f"  批量执行: {batch_start+1}-{min(batch_start+batch_size, len(all_queries))}/{len(all_queries)}")

    return stats

def escape_cypher(s):
    """转义Cypher字符串中的特殊字符"""
    if not s:
        return ''
    s = str(s)
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace("'", "\\'")
    return s

# ============================================================
# Task 2: 客资信息入库
# ============================================================
def parse_social_content(filepath):
    """解析客资信息CSV"""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    lines = text.strip().split('\n')
    # 跳过表头（前2行是表头信息）
    # 格式: 行号,日期,平台,账号,类型,标题,播放,点赞,评论,收藏,分享,留资
    # 其中有些行可能字段不完整

    contents = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('---') or line.startswith('日期'):
            continue

        # 用逗号分割，但由于标题可能包含逗号，需要智能匹配
        # 第一列是行号（数字），后面是日期,平台,账号,类型,标题...
        parts = line.split(',')
        if len(parts) < 5:
            continue

        try:
            row_id = parts[0].strip()
            if not row_id.isdigit():
                continue

            date_str = parts[1].strip() if len(parts) > 1 else ""
            platform = parts[2].strip() if len(parts) > 2 else ""
            account = parts[3].strip() if len(parts) > 3 else ""
            acc_type = parts[4].strip() if len(parts) > 4 else ""
            title = parts[5].strip() if len(parts) > 5 else ""

            views = parts[6].strip() if len(parts) > 6 else ""
            likes = parts[7].strip() if len(parts) > 7 else ""
            comments = parts[8].strip() if len(parts) > 8 else ""
            saves = parts[9].strip() if len(parts) > 9 else ""
            shares = parts[10].strip() if len(parts) > 10 else ""
            leads = parts[11].strip() if len(parts) > 11 else ""

            contents.append({
                'date': date_str,
                'platform': platform,
                'account': account,
                'acc_type': acc_type,
                'title': title,
                'views': views,
                'likes': likes,
                'comments_num': comments,
                'saves': saves,
                'shares': shares,
                'leads': leads,
            })
        except Exception as e:
            continue

    return contents

def import_social_content_to_neo4j(contents):
    """导入社交媒体内容到Neo4j"""
    stats = {"contents": 0, "accounts": 0}

    # 先创建唯一的账号节点
    accounts_seen = set()
    account_queries = []
    for c in contents:
        key = f"{c['platform']}:{c['account']}"
        if key not in accounts_seen:
            accounts_seen.add(key)
            safe_plat = escape_cypher(c['platform'])
            safe_acc = escape_cypher(c['account'])
            safe_type = escape_cypher(c['acc_type'])
            account_queries.append(f"""
            MERGE (a:SocialAccount {{
                platform: '{safe_plat}',
                account_name: '{safe_acc}'
            }})
            ON CREATE SET a.source_platform = 'feishu',
                          a.account_type = '{safe_type}',
                          a.import_time = timestamp()
            """)
            stats["accounts"] += 1

    # 创建内容节点并关联账号
    content_queries = []
    for c in contents:
        safe_plat = escape_cypher(c['platform'])
        safe_acc = escape_cypher(c['account'])
        safe_title = escape_cypher(c['title'][:200])
        safe_date = escape_cypher(c['date'])
        safe_type = escape_cypher(c['acc_type'])

        content_queries.append(f"""
        MATCH (a:SocialAccount {{platform: '{safe_plat}', account_name: '{safe_acc}'}})
        CREATE (sc:SocialContent {{
            entityType: 'SocialContent',
            title: '{safe_title}',
            platform: '{safe_plat}',
            content_type: '{safe_type}',
            publish_date: '{safe_date}',
            views: '{escape_cypher(c["views"][:20])}',
            likes: '{escape_cypher(c["likes"][:20])}',
            comments_num: '{escape_cypher(c["comments_num"][:20])}',
            saves: '{escape_cypher(c["saves"][:20])}',
            shares: '{escape_cypher(c["shares"][:20])}',
            leads: '{escape_cypher(c["leads"][:20])}',
            source_platform: 'feishu',
            import_time: timestamp()
        }})
        CREATE (a)-[:PUBLISHED]->(sc)
        """)
        stats["contents"] += 1

    # 批量执行
    all_queries = account_queries + content_queries
    batch_size = 50
    for batch_start in range(0, len(all_queries), batch_size):
        batch = all_queries[batch_start:batch_start + batch_size]
        neo4j_query(batch)
        print(f"  客资批量: {batch_start+1}-{min(batch_start+batch_size, len(all_queries))}/{len(all_queries)}")

    return stats

# ============================================================
# Task 3: 账号登记入库
# ============================================================
def parse_account_registration(filepath):
    """解析账号登记信息"""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    accounts = []
    # 格式: 编号,手机号,抖音,视频号,小红书,负责人
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('---') or line.startswith('手机号码'):
            continue
        if line.startswith('1号') and '手机号' not in line:
            # 跳过没有数据的行
            parts = line.split(',')
            if len(parts) < 2:
                continue

        parts = line.split(',')
        if len(parts) < 5:
            continue

        try:
            label = parts[0].strip()  # 1号, 2号...
            phone = parts[1].strip() if len(parts) > 1 else ""
            douyin = parts[2].strip() if len(parts) > 2 else ""
            shipinhao = parts[3].strip() if len(parts) > 3 else ""
            xiaohongshu = parts[4].strip() if len(parts) > 4 else ""
            person = parts[5].strip() if len(parts) > 5 else ""

            accounts.append({
                'label': label,
                'phone': phone,
                'douyin': douyin,
                'shipinhao': shipinhao,
                'xiaohongshu': xiaohongshu,
                'person': person,
            })
        except Exception as e:
            continue

    return accounts

def import_account_registration_to_neo4j(accounts):
    """导入账号登记到Neo4j"""
    stats = {"persons": 0, "platform_presences": 0}

    all_queries = []

    for acc in accounts:
        safe_label = escape_cypher(acc['label'])
        safe_phone = escape_cypher(acc['phone'])
        safe_person = escape_cypher(acc['person'])

        # 创建负责人节点
        if safe_person:
            all_queries.append(f"""
            MERGE (p:SocialAccount {{
                account_name: '{safe_person}',
                entityType: 'AccountManager'
            }})
            ON CREATE SET p.source_platform = 'feishu',
                          p.phone = '{safe_phone}',
                          p.account_label = '{safe_label}',
                          p.import_time = timestamp()
            """)
            stats["persons"] += 1

        # 创建各平台账号记录
        platform_map = {
            '抖音': acc['douyin'],
            '视频号': acc['shipinhao'],
            '小红书': acc['xiaohongshu'],
        }

        for plat_name, plat_account in platform_map.items():
            if plat_account and plat_account not in ('没注册', '', '无'):
                safe_plat = escape_cypher(plat_name)
                safe_pacc = escape_cypher(plat_account)

                all_queries.append(f"""
                MERGE (pp:PlatformPresence {{
                    platform: '{safe_plat}',
                    account_name: '{safe_pacc}'
                }})
                ON CREATE SET pp.source_platform = 'feishu',
                              pp.phone = '{safe_phone}',
                              pp.manager = '{safe_person}',
                              pp.account_label = '{safe_label}',
                              pp.import_time = timestamp()
                """)

                # 关联到负责人
                if safe_person:
                    all_queries.append(f"""
                    MATCH (mgr:SocialAccount {{account_name: '{safe_person}', entityType: 'AccountManager'}}),
                          (pp:PlatformPresence {{platform: '{safe_plat}', account_name: '{safe_pacc}'}})
                    MERGE (mgr)-[:MANAGES]->(pp)
                    """)

                stats["platform_presences"] += 1

    # 批量执行
    batch_size = 50
    for batch_start in range(0, len(all_queries), batch_size):
        batch = all_queries[batch_start:batch_start + batch_size]
        neo4j_query(batch)
        print(f"  账号批量: {batch_start+1}-{min(batch_start+batch_size, len(all_queries))}/{len(all_queries)}")

    return stats

# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    BASE = '/Users/xiaoji/.openclaw/workspace/feishu_raw'

    print("=" * 60)
    print("🔥 飞书数据导入Neo4j知识图谱")
    print("=" * 60)

    # 清理旧数据
    print("\n🧹 清理旧飞书数据...")
    clear_old_data()

    # Task 1: 岗位报告
    print("\n📋 Task 1: 岗位报告入库")
    report_files = [
        f"{BASE}/_岗位报告_2026-05-18.txt",
        f"{BASE}/_岗位报告_2026-05-19.txt",
    ]
    stats1 = import_positions_to_neo4j(report_files)
    print(f"  ✅ Document节点: {stats1['documents']} 个")
    print(f"  ✅ Position节点: {stats1['positions']} 个")

    # Task 2: 客资信息
    print("\n📱 Task 2: 客资信息入库")
    contents = parse_social_content(f"{BASE}/_客资信息.txt")
    stats2 = import_social_content_to_neo4j(contents)
    print(f"  ✅ SocialAccount节点: {stats2['accounts']} 个")
    print(f"  ✅ SocialContent节点: {stats2['contents']} 个")

    # Task 3: 账号登记
    print("\n🔐 Task 3: 账号登记入库")
    accounts = parse_account_registration(f"{BASE}/_账号登记.txt")
    stats3 = import_account_registration_to_neo4j(accounts)
    print(f"  ✅ AccountManager节点: {stats3['persons']} 个")
    print(f"  ✅ PlatformPresence节点: {stats3['platform_presences']} 个")

    # 汇总
    print("\n" + "=" * 60)
    print("📊 最终统计")
    print("=" * 60)
    print(f"""
┌─────────────────────────────────┬───────┐
│ Task 1: 岗位报告                │       │
│   Document (每日岗位信息报告)    │ {stats1['documents']:>5} │
│   Position (岗位实体)           │ {stats1['positions']:>5} │
│   CONTAINS 关系                 │ {stats1['positions']:>5} │
├─────────────────────────────────┼───────┤
│ Task 2: 客资信息                │       │
│   SocialAccount (运营账号)       │ {stats2['accounts']:>5} │
│   SocialContent (内容记录)      │ {stats2['contents']:>5} │
│   PUBLISHED 关系                │ {stats2['contents']:>5} │
├─────────────────────────────────┼───────┤
│ Task 3: 账号登记                │       │
│   AccountManager (负责人)       │ {stats3['persons']:>5} │
│   PlatformPresence (平台账号)   │ {stats3['platform_presences']:>5} │
│   MANAGES 关系                  │ ~{stats3['platform_presences']:>4} │
├─────────────────────────────────┼───────┤
│ 总计节点                        │ {stats1['documents'] + stats1['positions'] + stats2['accounts'] + stats2['contents'] + stats3['persons'] + stats3['platform_presences']:>5} │
│ 总计关系                        │ {stats1['positions'] + stats2['contents'] + stats3['platform_presences']:>5} │
└─────────────────────────────────┴───────┘
""")

    # 验证查询
    print("🔍 验证查询:")
    verify_queries = [
        "MATCH (d:Document {source_platform:'feishu'}) RETURN count(d) as cnt",
        "MATCH (p:Position {source_platform:'feishu'}) RETURN count(p) as cnt",
        "MATCH (:Document)-[r:CONTAINS]->(:Position) RETURN count(r) as cnt",
        "MATCH (a:SocialAccount) RETURN count(a) as cnt",
        "MATCH (c:SocialContent) RETURN count(c) as cnt",
        "MATCH (:SocialAccount)-[r:PUBLISHED]->(:SocialContent) RETURN count(r) as cnt",
        "MATCH (pp:PlatformPresence) RETURN count(pp) as cnt",
    ]
    for q in verify_queries:
        try:
            result = neo4j_query([q])
            data = result.get('results', [{}])[0].get('data', [{}])
            cnt = data[0].get('row', ['?'])[0] if data else '?'
            label = q.split('RETURN')[0].strip().replace('MATCH ', '')
            print(f"  {label}: {cnt}")
        except Exception as e:
            print(f"  ⚠️ 验证失败: {e}")

    print("\n🎉 飞书数据入库完成！")
