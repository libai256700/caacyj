#!/usr/bin/env python3
"""
知识图谱抽取后验证模块
在 LLM 抽取结果写入 Neo4j 之前，进行语义验证和清理

功能：
1. 阻止 SalaryRange 创建 LOCATED_IN / BELONGS_TO 等语义错误的关系
2. 检测并合并实体名子串重复（如 "5000-9000" ⊆ "5000-9000元"）
3. 检查纯数字无单位 SalaryRange
4. 防止同标签实体类型混淆
"""

import re
import json
from collections import defaultdict
from typing import List, Dict, Tuple


# ============ 语义验证规则 ============

# 实体类型 → 允许的关系（白名单制）
ALLOWED_RELATIONS = {
    "SalaryRange": [
        # SalaryRange 只能被 Position 引用，不能主动指向位置/公司
        # 向外不创建任何关系，只接收 HAS_SALARY 等从 Position 来的入边
        # 所以在提取时 NOTHING 外出
    ],
    "Position": [
        "LOCATED_IN",        # 职位 → 地点
        "BELONGS_TO",        # 职位 → 公司
        "REQUIRES",          # 职位 → 技能/资格
        "PROVIDES",          # 职位 → 薪资
        "REFERENCES",        # 职位 → 文档
    ],
    "Location": [
        "CONTAINS",          # 地点 → 公司/子区域
    ],
    "Company": [
        "LOCATED_IN",        # 公司 → 地点
        "CONTAINS",          # 公司 → 职位
        "PROVIDES",          # 公司 → 产品/服务
    ],
    "Organization": [
        "LOCATED_IN",        # 组织 → 地点
        "CONTAINS",          # 组织 → 子组织/成员
        "PROVIDES",          # 组织 → 服务/产品
        "REGULATES",         # 组织 → 监管对象（如民航局→培训机构）
        "MANAGES",           # 组织 → 管理对象
        "REFERENCES",        # 组织 → 引用
    ],
    "default": [
        "BELONGS_TO",        # 通用
        "CONTAINS",          # 包含
        "REFERENCES",        # 引用
        "REQUIRED_BY",       # 被要求
        "MANAGES",           # 管理
        "REGULATES",         # 规范
        "PROVIDES",          # 提供
    ]
}

# 所有 SalaryRange 的别名规则（匹配时忽略单位后缀）
SALARY_UNIT_SUFFIXES = ["元", "k", "K"]


def strip_salary_unit(name: str) -> str:
    """去除薪资实体名的单位后缀"""
    for suffix in SALARY_UNIT_SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def is_pure_number(name: str) -> bool:
    """判断是否为纯数字（含范围）"""
    return bool(re.match(r'^\d+(-\d+)?$', name))


def is_salary_range(name: str) -> bool:
    """判断是否为薪资范围格式"""
    return bool(re.match(r'^\d+(-\d+)?[kK元]?$', name))


# ============ 验证函数 ============

def validate_entities_and_relations(entities: List[Dict], relations: List[Dict], doc_name: str = "") -> Tuple[List[Dict], List[Dict], List[str]]:
    """
    验证并修复实体和关系
    
    Args:
        entities: LLM 抽取的实体列表
        relations: LLM 抽取的关系列表
        doc_name: 文档名（用于日志）
        
    Returns:
        (validated_entities, validated_relations, warnings)
    """
    warnings = []
    
    # Step 1: 建立实体ID→信息和名字→信息双索引
    entity_by_id = {}     # id -> {"index", "type", "name"}
    entity_by_name = {}   # name -> {"index", "type", "id"}
    for i, e in enumerate(entities):
        eid = e.get("id", "") or e.get("name", "")
        name = e.get("name", "")
        e_type = e.get("type", "Unknown")
        entity_by_id[eid] = {"index": i, "type": e_type, "name": name}
        entity_by_name[name] = {"index": i, "type": e_type, "id": eid}
    
    # 所有有效的ID集合
    all_valid_ids = set(entity_by_id.keys())
    
    # Step 2: 检查实体重复（仅对 SalaryRange 类型的子串去重）
    to_remove_indices = set()
    to_remove_ids = set()
    salary_entities = [e for e in entities if e.get("type") == "SalaryRange"]
    
    for sr in salary_entities:
        name = sr.get("name", "")
        base = strip_salary_unit(name)
        if base != name and base in entity_by_name:
            other = entity_by_name[base]
            other_id = other["id"]
            to_remove_indices.add(other["index"])
            to_remove_ids.add(other_id)
            warnings.append(
                f"⚠️ 去重: \"{base}\" ⊆ \"{name}\" "
                f"(纯数字版本被合并，保留带单位版本)"
            )
    
    # 过滤掉要删除的重复实体
    validated_entities = [
        e for i, e in enumerate(entities) if i not in to_remove_indices
    ]
    validated_ids = all_valid_ids - to_remove_ids
    
    # Step 3: 验证关系语义
    validated_relations = []
    for rel in relations:
        from_id = rel.get("from_id", "")
        to_id = rel.get("to_id", "")
        rel_type = rel.get("type", "").upper()
        
        # 获取 from 实体的类型（优先按ID，其次按名字）
        from_info = entity_by_id.get(from_id) or entity_by_name.get(from_id)
        from_type = from_info["type"] if from_info else "Unknown"
        
        # 检查关系是否允许
        allowed_from = ALLOWED_RELATIONS.get(from_type, ALLOWED_RELATIONS["default"])
        
        if rel_type not in allowed_from:
            fi_name = from_info["name"] if from_info else from_id
            warnings.append(
                f"🚫 拦截关系: ({from_type})\"{fi_name}\" -[{rel_type}]-> \"{to_id}\" "
                f"(关系类型 \"{rel_type}\" 不被实体类型 \"{from_type}\" 允许)"
            )
            # 只有 SalaryRange 创建的这种关系被拦截
            if from_type == "SalaryRange":
                continue  # 跳过这个关系
        
        # 检查 to 实体是否还存在（去重后）
        if to_id and to_id not in validated_ids:
            warnings.append(
                f"🔄 关系跳过: 目标实体 \"{to_id}\" 已被去重合并"
            )
            continue
        
        validated_relations.append(rel)
    
    # Step 5: 检查纯数字无单位的 SalaryRange
    for e in validated_entities:
        if e.get("type") == "SalaryRange":
            name = e.get("name", "")
            if is_pure_number(name) and not any(s in name for s in ["k", "K", "元"]):
                warnings.append(
                    f"⚠️ 纯数字无单位 SalaryRange: \"{name}\" "
                    f"(可能缺少单位后缀，建议加 \"元\" 或 \"k\")"
                )
    
    return validated_entities, validated_relations, warnings


def print_validation_report(warnings: List[str], doc_name: str = ""):
    """打印验证报告"""
    if not warnings:
        return
    
    print(f"\n  📋 验证报告 ({doc_name or '抽取'}):")
    errors = [w for w in warnings if w.startswith("🚫")]
    warnings_only = [w for w in warnings if not w.startswith("🚫")]
    
    if errors:
        print(f"    拦截了 {len(errors)} 个错误关系:")
        for w in errors:
            print(f"      {w}")
    
    if warnings_only:
        print(f"    提醒 {len(warnings_only)} 条:")
        for w in warnings_only:
            print(f"      {w}")


# ============ 批量修复 Neo4j 中已有的错误关系 ============

def fix_existing_salary_relationships(dry_run: bool = False) -> List[str]:
    """
    修复 Neo4j 中已有的 SalaryRange 错误关系
    
    Args:
        dry_run: True=只报告不执行
        
    Returns:
        操作日志
    """
    from neo4j import GraphDatabase
    
    logs = []
    URI = "bolt://localhost:7687"
    AUTH = ("neo4j", "yj123456")
    
    driver = GraphDatabase.driver(URI, auth=AUTH)
    
    with driver.session() as session:
        # 1. 查出所有 SalaryRange→其他实体的 LOCATED_IN 和 BELONGS_TO
        if dry_run:
            result = session.run("""
                MATCH (e:Entity {entityType: "SalaryRange"})-[r]->(other)
                WHERE type(r) IN ["LOCATED_IN", "BELONGS_TO"]
                RETURN e.name as salary, type(r) as rel, other.name as target, other.entityType as target_type
                ORDER BY e.name
            """).data()
            logs.append(f"  待清理: {len(result)} 条 SalaryRange 外出关系")
            for r in result:
                logs.append(f"    \"{r['salary']}\" -[{r['rel']}]-> \"{r['target']}\" (type={r['target_type']})")
        else:
            # 执行清理
            result = session.run("""
                MATCH (e:Entity {entityType: "SalaryRange"})-[r]->(other)
                WHERE type(r) IN ["LOCATED_IN", "BELONGS_TO"]
                WITH r, count(r) AS c
                DELETE r
                RETURN c AS deleted
            """).data()
            cnt = result[0]['deleted'] if result else 0
            logs.append(f"  已清理: {cnt} 条 SalaryRange 外出关系")
        
        # 2. 清理纯数字 SalaryRange 实体（如果存在带单位的对应版本）
        result = session.run("""
            MATCH (e:Entity {entityType: "SalaryRange"})
            WHERE NOT (e.name ENDS WITH "元") AND NOT (e.name ENDS WITH "k") AND NOT (e.name ENDS WITH "K")
            RETURN e.name as name
            ORDER BY e.name
        """).data()
        pure_numbers = [r['name'] for r in result if r.get('name')]
        logs.append(f"  纯数字 SalaryRange: {len(pure_numbers)} 个")
        
        for name in pure_numbers:
            # 检查是否有带单位的对应版本
            has_yuan = session.run(
                "MATCH (e:Entity {name: $name}) RETURN count(e) AS c",
                name=name + "元"
            ).single()['c']
            if has_yuan:
                if dry_run:
                    logs.append(f"    ⏭️  \"{name}\" → 已有 \"{name}元\" 可合并")
                else:
                    # 转移关系并从薪水范围→位置的关系中删除
                    # 先把出边从旧实体转移到新实体
                    session.run("""
                        MATCH (old:Entity {name: $old_name})
                        OPTIONAL MATCH (old)-[r]->(target)
                        WHERE type(r) NOT IN ["LOCATED_IN", "BELONGS_TO"]
                        WITH old, r, target
                        MATCH (new:Entity {name: $new_name})
                        MERGE (new)-[nr:PROVIDES]->(target)
                        SET nr.description = r.description
                        DELETE r
                    """, old_name=name, new_name=name + "元")
                    
                    session.run("""
                        MATCH (old:Entity {name: $old_name})
                        OPTIONAL MATCH (source)-[r]->(old)
                        WHERE type(r) NOT IN ["LOCATED_IN", "BELONGS_TO"]
                        WITH old, r, source
                        MATCH (new:Entity {name: $new_name})
                        MERGE (source)-[nr:HAS_SALARY]->(new)
                        SET nr.description = r.description
                        DELETE r
                    """, old_name=name, new_name=name + "元")
                    
                    # 删除旧实体
                    session.run("MATCH (e:Entity {name: $name}) DETACH DELETE e", name=name)
                    logs.append(f"    ✅  \"{name}\" → 合并到 \"{name}元\"")
            else:
                logs.append(f"    ⏭️  \"{name}\" → 无对应带单位版本，跳过")
        
        # 3. 清理 SalaryRange 带单位的子串重复
        result2 = session.run("""
            MATCH (sr1:Entity {entityType: "SalaryRange"})
            WHERE sr1.name ENDS WITH "元" OR sr1.name ENDS WITH "k" OR sr1.name ENDS WITH "K"
            RETURN sr1.name as name
        """).data()
        for r in result2:
            name = r['name']
            base = strip_salary_unit(name)
            if base != name:
                # 检查无单位版本是否存在
                exists = session.run(
                    "MATCH (e:Entity {name: $name}) RETURN count(e) AS c",
                    name=base
                ).single()['c']
                if exists:
                    if dry_run:
                        logs.append(f"    ⏭️  子串重复: \"{base}\" ⊆ \"{name}\"")
                    else:
                        session.run("MATCH (e:Entity {name: $name}) DETACH DELETE e", name=base)
                        logs.append(f"    ✅ 删除子串重复: \"{base}\" (已由 \"{name}\" 覆盖)")
        
        # 4. 处理从其他实体指向 SalaryRange 的 LOCATED_IN（语义上应该是 HAS_SALARY）
        if not dry_run:
            result3 = session.run("""
                MATCH (other)-[r:LOCATED_IN]->(e:Entity {entityType: "SalaryRange"})
                WITH r, other, e
                MERGE (other)-[nr:HAS_SALARY]->(e)
                SET nr.description = r.description
                DELETE r
                RETURN count(r) AS fixed
            """).data()
            logs.append(f"  修正 LOCATED_IN→SalaryRange 为 HAS_SALARY: {result3[0]['fixed']} 条")
            
            # 同样处理 BELONGS_TO→SalaryRange（从 semantic 上它也不对，改成 HAS_SALARY）
            result4 = session.run("""
                MATCH (other)-[r:BELONGS_TO]->(e:Entity {entityType: "SalaryRange"})
                WITH r, other, e
                MERGE (other)-[nr:HAS_SALARY]->(e)
                SET nr.description = r.description
                DELETE r
                RETURN count(r) AS fixed
            """).data()
            logs.append(f"  修正 BELONGS_TO→SalaryRange 为 HAS_SALARY: {result4[0]['fixed']} 条")
    
    driver.close()
    return logs


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--fix-existing":
        dry_run = "--dry-run" in sys.argv
        logs = fix_existing_salary_relationships(dry_run=dry_run)
        print("\n".join(logs))
        print(f"\n{'🧪 DRY RUN' if dry_run else '✅ 修复完成'}")
    else:
        # 测试模式
        test_entities = [
            {"name": "5000-9000元", "type": "SalaryRange", "description": "月薪"},
            {"name": "5000-9000", "type": "SalaryRange", "description": "月薪"},
            {"name": "黄骅市", "type": "Location", "description": "河北沧州"},
            {"name": "无人机飞手", "type": "Position", "description": "岗位"},
        ]
        test_relations = [
            {"from_id": "5000-9000元", "to_id": "5000-9000", "type": "LOCATED_IN", "description": ""},
            {"from_id": "5000-9000元", "to_id": "黄骅市", "type": "BELONGS_TO", "description": ""},
            {"from_id": "无人机飞手", "to_id": "5000-9000元", "type": "PROVIDES", "description": "提供薪资"},
        ]
        
        validated, valid_rels, warns = validate_entities_and_relations(test_entities, test_relations, "[测试]")
        print_validation_report(warns)
        print(f"\n验证后实体: {len(validated)} 个")
        print(f"验证后关系: {len(valid_rels)} 条")
        for r in valid_rels:
            print(f"  {r['from_id']} -[{r['type']}]-> {r['to_id']}")
