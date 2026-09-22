#!/usr/bin/env python3
"""CSV 结构化数据查询脚本

用法:
  python3 csv_query.py "万志峰有多少学员"
  python3 csv_query.py --list          # 列出所有可用数据
  python3 csv_query.py --stats         # 数据统计总览
  python3 csv_query.py --ids           # 统一实体主键统计
  python3 csv_query.py --refresh       # 从飞书刷新学员培训记录csv

数据源: /Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据/*.csv
"""
import csv, json, sys, os, re, io, subprocess
from pathlib import Path
from collections import Counter, defaultdict

DATA = Path("/Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据")
CANONICAL_PROJECT = Path("/Users/xiaoji/Documents/知识库分析")
CANONICAL_DATA = CANONICAL_PROJECT / "data/canonical"
CACHE_JSON = DATA / "_query_cache.json"

# ===== 数据概览 =====
INFO = {
    "学员名单.csv": {"主题": "学员名单与培训记录数", "教员": True},
    "学员培训记录.csv": {"主题": "学员每日培训详细记录", "教员": True},
    "学员培训进度.csv": {"主题": "学员培训进度（含日期/时段/内容/完成情况）", "教员": True},
    "学员信息.csv": {"主题": "学员基本信息（含机型/年龄/学历等）", "教员": True},
    "价格表.csv": {"主题": "公司课程定价"},
    "每日岗位信息.csv": {"主题": "全历史去重后的无人机相关岗位招聘信息"},
    "岗位去重汇总.csv": {"主题": "岗位去重汇总（首次/最近出现日期、出现天数、出现次数）"},
    "客资表.csv": {"主题": "客户咨询记录"},
    "A类客户.csv": {"主题": "高意向客户跟进记录"},
    "B类客户.csv": {"主题": "中意向客户跟进记录"},
    "C类客户.csv": {"主题": "低意向客户跟进记录"},
    "官号播放量统计.csv": {"主题": "官方账号视频播放量统计"},
    "小号播放量统计.csv": {"主题": "小号账号视频播放量统计"},
    "账号管理表.csv": {"主题": "各平台账号信息"},
    "运营日常工作记录表.csv": {"主题": "运营日常任务记录"},
    "新员工培训课程表.csv": {"主题": "新员工培训课程安排"},
    "测绘公司名录.csv": {"主题": "测绘公司名录（待补充）"},
}


def load_csv(name):
    """加载csv，返回list[dict]"""
    path = DATA / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_canonical(name):
    """加载统一实体主键表，缺失时返回空列表。"""
    path = CANONICAL_DATA / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def canonical_ready():
    required = [
        "instructors.csv",
        "students.csv",
        "customers.csv",
        "courses.csv",
        "jobs.csv",
        "regulations.csv",
        "question_banks.csv",
    ]
    return all((CANONICAL_DATA / name).exists() for name in required)


def list_available():
    """列出所有可用数据文件"""
    print("📊 可用 CSV 数据源:\n")
    for name, info in sorted(INFO.items()):
        rows = load_csv(name)
        count = len(rows)
        status = "✅" if count else "⚠️ 空"
        detail = f"({info['主题']})"
        print(f"  {status} {name:20s} {count:>4}行 {detail}")
    if canonical_ready():
        print(f"\n🔑 统一实体主键表: {CANONICAL_DATA}")


def show_stats():
    """显示关键数据统计"""
    print("📈 CSV 数据统计总览\n")
    canonical = show_entity_ids(compact=True)
    if canonical:
        print()

    # 学员统计
    roster = load_csv("学员名单.csv")
    progress = load_csv("学员培训进度.csv")
    records = load_csv("学员培训记录.csv")

    if roster:
        by_teacher = Counter(r["教员"] for r in roster)
        total_students = len(roster)
        print(f"👨‍🎓 学员统计 ({total_students}人):")
        for t, count in sorted(by_teacher.items()):
            print(f"   {t}: {count}人")
        if progress:
            by_teacher_rec = Counter(r["教员"] for r in progress)
            for t, count in sorted(by_teacher_rec.items()):
                print(f"   {t}培训记录: {count}条")
        print()

    # 岗位统计
    jobs = load_csv("每日岗位信息.csv")
    if jobs:
        dates = set(r.get("日期","") for r in jobs)
        print(f"💼 去重岗位信息 ({len(jobs)}条, 最近出现日期覆盖{len(dates)}天)")
        # 按分类统计
        cats = Counter(r.get("分类","") for r in jobs if r.get("分类"))
        for cat, count in cats.most_common(5):
            print(f"   {cat}: {count}个")
        print()

    # 客资统计
    for name in ["A类客户.csv", "B类客户.csv", "C类客户.csv"]:
        rows = load_csv(name)
        if rows:
            tag = name[0]  # A/B/C
            print(f"📋 {tag}类客户: {len(rows)}人")
    print()

    # 视频数据
    for name in ["官号播放量统计.csv", "小号播放量统计.csv"]:
        rows = load_csv(name)
        if rows:
            total_play = sum(int(r.get("播放",0) or 0) for r in rows)
            print(f"🎬 {name.replace('播放量统计.csv','')}: {len(rows)}条, 总播放 {total_play:,}")


def show_entity_ids(compact=False):
    """显示统一实体主键覆盖情况。"""
    tables = {
        "教员 instructor_id": "instructors.csv",
        "学员 student_id": "students.csv",
        "客户 customer_id": "customers.csv",
        "课程 course_id": "courses.csv",
        "岗位 job_id": "jobs.csv",
        "法规 regulation_id": "regulations.csv",
        "题库 question_bank_id": "question_banks.csv",
        "RAG文档 document_id": "documents.csv",
        "chunk_id映射": "document_chunks.csv",
    }
    loaded = {label: load_canonical(name) for label, name in tables.items()}
    if not any(loaded.values()):
        return False
    title = "🔑 统一实体主键覆盖:" if compact else f"🔑 统一实体主键覆盖 ({CANONICAL_DATA})"
    print(title)
    for label, rows in loaded.items():
        if rows:
            print(f"   {label}: {len(rows)}")
    if not compact:
        students = load_canonical("students.csv")
        instructors = load_canonical("instructors.csv")
        if instructors:
            print("\n教员主键:")
            for row in sorted(instructors, key=lambda r: r.get("name", "")):
                print(f"   {row.get('name','')}: {row.get('instructor_id','')}")
        if students:
            print("\n学员主键示例:")
            for row in sorted(students, key=lambda r: r.get("student_name", ""))[:10]:
                print(f"   {row.get('student_name','')} | {row.get('instructor_name','')} | {row.get('student_id','')}")
    return True


def query_students(question):
    """学员/教员相关查询"""
    canonical_students = load_canonical("students.csv")
    canonical_instructors = load_canonical("instructors.csv")
    # 优先使用学员信息.csv（含机型等详细信息）
    info = load_csv("学员信息.csv")
    # 回退到学员名单.csv
    roster = info if info else load_csv("学员名单.csv")
    progress = load_csv("学员培训进度.csv")

    q = question.lower()

    # 提取教员姓名
    teacher = None
    teacher_names = [r.get("name", "") for r in canonical_instructors] or ["万志峰", "沙浩"]
    for name in teacher_names:
        if name in question:
            teacher = name
            break

    # 学员数量查询
    if any(kw in question for kw in ["多少学员", "几个学员", "多少个", "多少人", "学员数", "总共有多少"]):
        if canonical_students:
            scoped = [r for r in canonical_students if not teacher or r.get("instructor_name") == teacher]
            if teacher:
                instructor_id = next((r.get("instructor_id") for r in canonical_instructors if r.get("name") == teacher), "")
                print(f"📊 {teacher}的学员: {len(scoped)}人")
                if instructor_id:
                    print(f"   instructor_id: {instructor_id}")
            else:
                print(f"📊 全部学员: {len(scoped)}人")
                for name, count in sorted(Counter(r.get("instructor_name","") for r in scoped).items()):
                    print(f"   {name}: {count}人")
            machines = Counter(r.get("aircraft_type","") for r in scoped if r.get("aircraft_type"))
            if machines:
                print(f"   机型分布: {dict(machines)}")
            if teacher:
                print("   学员列表:")
                for s in sorted(scoped, key=lambda x: x.get("student_name","")):
                    gender = f"({s.get('gender','')})" if s.get("gender") else ""
                    machine = f" {s.get('aircraft_type','')}" if s.get("aircraft_type") else ""
                    print(f"     - {s.get('student_name','')}{gender}{machine} [{s.get('student_id','')}]")
        elif teacher and roster:
            students = [r for r in roster if r["教员"] == teacher]
            print(f"📊 {teacher}的学员: {len(students)}人")
            if info:
                machines = Counter(r.get("机型","") for r in students if r.get("机型"))
                if machines:
                    print(f"   机型分布: {dict(machines)}")
            print(f"   学员列表:")
            for s in sorted(students, key=lambda x: x.get("学员",x.get("姓名",""))):
                name = s.get("姓名", s.get("学员","?"))
                gender = f"({s.get('性别','')})" if s.get('性别') else ""
                machine = f" {s.get('机型','')}" if s.get('机型') else ""
                print(f"     - {name}{gender}{machine}")
        elif not teacher and roster:
            total = len(roster)
            by_t = Counter(r["教员"] for r in roster)
            print(f"📊 全部学员: {total}人")
            for t, c in sorted(by_t.items()):
                print(f"   {t}: {c}人")
        return True

    # 学员详情查询
    if teacher and any(kw in question for kw in ["学员名单", "有哪些", "学员列表", "学员信息"]):
        if canonical_students:
            students = [r for r in canonical_students if r.get("instructor_name") == teacher]
            if students:
                print(f"📋 {teacher}的学员列表:")
                for s in sorted(students, key=lambda x: x.get("student_name","")):
                    print(f"   - {s.get('student_name','')} [{s.get('student_id','')}]")
            return True
        students = [r for r in roster if r["教员"] == teacher] if roster else []
        if students:
            print(f"📋 {teacher}的学员列表:")
            for s in sorted(students, key=lambda x: x["学员"]):
                print(f"   - {s['学员']}")
        return True

    # 培训记录查询
    if any(kw in question for kw in ["培训记录", "培训内容", "培训进度"]):
        if teacher and progress:
            records = [r for r in progress if r["教员"] == teacher]
            dates = set(r["日期"] for r in records if r.get("日期"))
            print(f"📋 {teacher}的培训记录: {len(records)}条, 共{len(dates)}天")
            return True
        elif not teacher and progress:
            dates = set(r["日期"] for r in progress if r.get("日期"))
            by_t = Counter(r["教员"] for r in progress)
            print(f"📋 全部培训记录: {len(progress)}条, 共{len(dates)}天")
            for t, c in sorted(by_t.items()):
                print(f"   {t}: {c}条")
            return True

    return False


def query_jobs(question):
    """岗位信息查询"""
    canonical_jobs = load_canonical("jobs.csv")
    canonical_occurrences = load_canonical("job_occurrences.csv")
    jobs = load_csv("每日岗位信息.csv")
    if not jobs and not canonical_jobs:
        return False

    q = question.lower()
    if any(kw in q for kw in ["岗位", "招聘", "就业", "工作", "职位", "薪资"]) or any(kw in question for kw in ["岗位", "招聘"]):
        if canonical_occurrences:
            dates = sorted(set(r.get("date","") for r in canonical_occurrences if r.get("date")))
            scoped_occurrences = canonical_occurrences
            scope_label = ""
            if dates and any(kw in question for kw in ["今天", "今日", "当天", "最新", "最近一天"]):
                latest_date = dates[-1]
                scoped_occurrences = [r for r in canonical_occurrences if r.get("date") == latest_date]
                scope_label = f"{latest_date} "
            scoped_job_ids = {r.get("job_id") for r in scoped_occurrences}
            print(f"💼 {scope_label}岗位实体: {len(scoped_job_ids)}个，岗位出现记录: {len(scoped_occurrences)}条")
            print(f"   canonical job_id 总数: {len(canonical_jobs)}")
            platforms = Counter(r.get("platform","") for r in scoped_occurrences if r.get("platform"))
            if platforms:
                print("\n平台分布:")
                for platform, count in platforms.most_common(10):
                    print(f"   {platform}: {count}条")
            cats = Counter(r.get("category","") for r in scoped_occurrences if r.get("category"))
            if cats:
                print("\n岗位分类:")
                for cat, count in cats.most_common(10):
                    print(f"   {cat}: {count}个")
            return True

        dates = sorted(set(r.get("日期","") for r in jobs if r.get("日期")))
        scoped_jobs = jobs
        scope_label = ""
        if dates and any(kw in question for kw in ["今天", "今日", "当天", "最新", "最近一天"]):
            latest_date = dates[-1]
            scoped_jobs = [r for r in jobs if r.get("日期") == latest_date]
            scope_label = f"{latest_date} "
        print(f"💼 {scope_label}去重岗位信息 ({len(scoped_jobs)}条, CSV共{len(jobs)}条/最近出现日期覆盖{len(dates)}天)")
        platforms = Counter(r.get("平台","") for r in scoped_jobs if r.get("平台"))
        if platforms:
            print("\n平台分布:")
            for platform, count in platforms.most_common(10):
                print(f"   {platform}: {count}条")
        # 按分类
        cats = Counter(r.get("分类","") for r in scoped_jobs if r.get("分类"))
        if cats:
            print("\n岗位分类:")
            for cat, count in cats.most_common(10):
                print(f"   {cat}: {count}个")
        return True

    return False


def query_prices(question):
    """价格查询"""
    canonical_courses = load_canonical("courses.csv")
    prices = load_csv("价格表.csv")
    if not prices and not canonical_courses:
        return False

    if any(kw in question for kw in ["价格", "多少钱", "费用", "学费", "收费"]):
        print("💰 课程价格表:")
        rows = canonical_courses or [
            {"course_name": p.get("课程",""), "price": p.get("价格",""), "duration": p.get("时长",""), "content": p.get("内容",""), "course_id": ""}
            for p in prices
        ]
        for p in rows:
            course = p.get("course_name","")
            price = p.get("price","")
            duration = p.get("duration","")
            content = p.get("content","")
            course_id = f" [{p.get('course_id','')}]" if p.get("course_id") else ""
            print(f"   {course}{course_id} | {price} | {duration}")
            if content:
                print(f"     {content[:60]}...")
        return True

    return False


def query_customers(question):
    """客户/客资查询"""
    if any(kw in question for kw in ["客户", "客资", "咨询", "意向"]):
        canonical_customers = load_canonical("customers.csv")
        source_rows = load_canonical("customer_source_rows.csv")
        if canonical_customers:
            print(f"📋 客户实体: {len(canonical_customers)}人，来源记录: {len(source_rows)}条")
            classes = Counter(r.get("customer_class","") or "未分级" for r in canonical_customers)
            print(f"   分级分布: {dict(classes)}")
            needs_contact = [r for r in canonical_customers if r.get("needs_contact_key") == "true"]
            if needs_contact:
                print(f"   待补联系方式: {len(needs_contact)}人")
            sources = Counter()
            for r in canonical_customers:
                for source in (r.get("sources","") or "").split(";"):
                    if source:
                        sources[source] += 1
            if sources:
                print(f"   来源分布: {dict(sources.most_common(8))}")
            return True
        for name in ["A类客户.csv", "B类客户.csv", "C类客户.csv"]:
            rows = load_csv(name)
            if rows:
                tag = name[0]
                print(f"📋 {tag}类客户: {len(rows)}人")
                # 按来源统计
                sources = Counter(r.get("来源","") for r in rows if r.get("来源"))
                if sources:
                    print(f"   来源分布: {dict(sources.most_common(5))}")
        return True
    return False


def refresh_data():
    """从飞书全量刷新CSV数据"""
    print("🔄 正在全量刷新CSV数据...")
    script = DATA / "sync_all_csv.py"
    if not script.exists():
        print(f"⚠️ 找不到 {script}")
        return
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=600)
    print(result.stdout)
    if result.stderr:
        print("⚠️ 错误输出:", result.stderr[:500])
    if result.returncode != 0:
        print(f"❌ 刷新失败 (exit code {result.returncode})")
        return
    build_script = CANONICAL_PROJECT / "scripts/build_canonical_entities.py"
    validate_script = CANONICAL_PROJECT / "scripts/validate_canonical_entities.py"
    if build_script.exists() and validate_script.exists():
        print("🔑 正在重建统一实体主键表...")
        build = subprocess.run([sys.executable, str(build_script)], cwd=str(CANONICAL_PROJECT), capture_output=True, text=True, timeout=120)
        if build.stdout:
            print(build.stdout)
        if build.stderr:
            print("⚠️ 主键构建错误输出:", build.stderr[:500])
        if build.returncode != 0:
            print(f"❌ 主键构建失败 (exit code {build.returncode})")
            return
        validate = subprocess.run([sys.executable, str(validate_script)], cwd=str(CANONICAL_PROJECT), capture_output=True, text=True, timeout=120)
        if validate.returncode == 0:
            print("✅ 统一实体主键验证通过")
        else:
            print(validate.stdout)
            if validate.stderr:
                print("⚠️ 主键验证错误输出:", validate.stderr[:500])
            print(f"❌ 主键验证失败 (exit code {validate.returncode})")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 csv_query.py <问题>")
        print("      python3 csv_query.py --list")
        print("      python3 csv_query.py --stats")
        print("      python3 csv_query.py --ids")
        print("      python3 csv_query.py --refresh")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--list":
        list_available()
        return
    elif cmd == "--stats":
        show_stats()
        return
    elif cmd == "--ids":
        if not show_entity_ids():
            print(f"⚠️ 未找到统一实体主键表: {CANONICAL_DATA}")
        return
    elif cmd == "--refresh":
        refresh_data()
        return

    question = " ".join(sys.argv[1:])

    # 按主题路由查询
    handlers = [
        query_students,
        query_jobs,
        query_prices,
        query_customers,
    ]

    handled = False
    for h in handlers:
        if h(question):
            handled = True
            break

    if not handled:
        print(f"🤷 不确定问题「{question}」对应哪个csv数据源")
        print("可查的数据源:")
        list_available()
        print("\n或尝试更明确的问题，如「万志峰有多少学员」「岗位信息有哪些」")


if __name__ == "__main__":
    main()
