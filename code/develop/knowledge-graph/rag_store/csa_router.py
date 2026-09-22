#!/usr/bin/env python3
"""CSA structured-data router for /api/ask.

CSA answers deterministic questions from structured business data. CSV files
remain the source of truth, while a local SQLite cache avoids parsing full CSVs
on every question.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

try:
    from rag_store.route_policy import requires_internal_kb
except ImportError:
    from route_policy import requires_internal_kb


DEFAULT_DATA_DIR = Path(os.environ.get(
    "CSA_DATA_DIR",
    "/Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据",
))
DEFAULT_CANONICAL_DIR = Path(os.environ.get(
    "CSA_CANONICAL_DIR",
    "/Users/xiaoji/Documents/知识库分析/data/canonical",
))
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DB = Path(os.environ.get(
    "CSA_CACHE_DB",
    BASE_DIR / "rag_index" / "csa_cache.sqlite",
))


class CSATableCache:
    """SQLite cache for CSV-backed CSA tables."""

    def __init__(self, data_dir: str | Path, db_path: str | Path = DEFAULT_CACHE_DB):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        conn = self.connect() if self._conn is None else self._conn
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS csa_files (
                filename TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                row_count INTEGER NOT NULL,
                refreshed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS csa_rows (
                filename TEXT NOT NULL,
                row_num INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY (filename, row_num)
            );
            CREATE INDEX IF NOT EXISTS idx_csa_rows_filename ON csa_rows(filename);
            """
        )
        conn.commit()

    def rows(self, filename: str) -> List[Dict[str, str]]:
        path = self.data_dir / filename
        if not path.exists():
            return []
        stat = path.stat()
        if self._needs_refresh(filename, path, stat):
            self._refresh(filename, path, stat)
        conn = self.connect()
        rows = conn.execute(
            "SELECT row_json FROM csa_rows WHERE filename = ? ORDER BY row_num",
            (filename,),
        ).fetchall()
        return [json.loads(row["row_json"]) for row in rows]

    def metadata(self, filename: str) -> dict:
        path = self.data_dir / filename
        if not path.exists():
            return {"rows": 0, "mtime": None, "cache": str(self.db_path)}
        stat = path.stat()
        if self._needs_refresh(filename, path, stat):
            self._refresh(filename, path, stat)
        conn = self.connect()
        row = conn.execute(
            "SELECT row_count, mtime_ns FROM csa_files WHERE filename = ?",
            (filename,),
        ).fetchone()
        if not row:
            return {"rows": 0, "mtime": int(stat.st_mtime), "cache": str(self.db_path)}
        return {
            "rows": int(row["row_count"]),
            "mtime": int(int(row["mtime_ns"]) / 1_000_000_000),
            "cache": str(self.db_path),
        }

    def _needs_refresh(self, filename: str, path: Path, stat: os.stat_result) -> bool:
        conn = self.connect()
        row = conn.execute(
            "SELECT mtime_ns, size_bytes FROM csa_files WHERE filename = ?",
            (filename,),
        ).fetchone()
        return (
            row is None
            or int(row["mtime_ns"]) != stat.st_mtime_ns
            or int(row["size_bytes"]) != stat.st_size
        )

    def _refresh(self, filename: str, path: Path, stat: os.stat_result) -> None:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            rows = list(csv.DictReader(fh))
        conn = self.connect()
        with conn:
            conn.execute("DELETE FROM csa_rows WHERE filename = ?", (filename,))
            conn.executemany(
                "INSERT INTO csa_rows(filename, row_num, row_json) VALUES (?, ?, ?)",
                [
                    (filename, idx, json.dumps(row, ensure_ascii=False, sort_keys=True))
                    for idx, row in enumerate(rows)
                ],
            )
            conn.execute(
                """
                INSERT INTO csa_files(filename, path, mtime_ns, size_bytes, row_count, refreshed_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(filename) DO UPDATE SET
                    path = excluded.path,
                    mtime_ns = excluded.mtime_ns,
                    size_bytes = excluded.size_bytes,
                    row_count = excluded.row_count,
                    refreshed_at = CURRENT_TIMESTAMP
                """,
                (filename, str(path), stat.st_mtime_ns, stat.st_size, len(rows)),
            )


class CSARouter:
    """Route simple structured CSV questions to deterministic answers."""

    def __init__(
        self,
        data_dir: str | Path = DEFAULT_DATA_DIR,
        cache_db: str | Path = DEFAULT_CACHE_DB,
        canonical_dir: str | Path = DEFAULT_CANONICAL_DIR,
    ):
        self.data_dir = Path(data_dir)
        self.canonical_dir = Path(canonical_dir)
        self.cache = CSATableCache(self.data_dir, cache_db)

    def answer(self, question: str) -> Optional[Dict]:
        q = (question or "").strip()
        if not q:
            return None
        for handler in (
            self._answer_training_progress,
            self._answer_students,
            self._answer_prices,
            self._answer_customers,
            self._answer_jobs,
        ):
            result = handler(q)
            if result:
                return result
        return None

    def _load_csv(self, name: str) -> List[Dict[str, str]]:
        return self.cache.rows(name)

    def _load_canonical(self, name: str) -> List[Dict[str, str]]:
        path = self.canonical_dir / name
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            return list(csv.DictReader(fh))

    def _source(self, filename: str, rows: int) -> Dict:
        path = self.data_dir / filename
        meta = self.cache.metadata(filename)
        return {
            "type": "sqlite_cache",
            "file": filename,
            "doc_name": filename,
            "source_doc": filename,
            "path": str(path),
            "rows": rows,
            "mtime": meta["mtime"],
            "cache_db": meta["cache"],
        }

    def _canonical_source(self, filename: str, rows: int) -> Dict:
        path = self.canonical_dir / filename
        return {
            "type": "canonical_csv",
            "file": filename,
            "doc_name": filename,
            "source_doc": filename,
            "path": str(path),
            "rows": rows,
        }

    def _response(self, question: str, answer: str, topic: str, sources: List[Dict], data: Dict = None) -> Dict:
        return {
            "query": question,
            "rewritten": question,
            "intent": "structured_csv",
            "route": "csa",
            "answer": answer,
            "sources": sources,
            "evidence": [{"type": "csv", "topic": topic}],
            "data": data or {},
            "stats": {
                "csa_hit": True,
                "topic": topic,
                "degraded": False,
                "degraded_reasons": [],
                "vector_results": 0,
                "entity_evidence": 0,
                "sparse_results": 0,
                "kg_results": 0,
                "merged_results": 0,
            },
        }

    def _teacher_name(self, question: str) -> Optional[str]:
        instructors = self._load_canonical("instructors.csv")
        names = [row.get("name", "") for row in instructors if row.get("name")] or ["万志峰", "沙浩"]
        for name in names:
            if name in question:
                return name
        return None

    def _answer_students(self, question: str) -> Optional[Dict]:
        if requires_internal_kb(question):
            return None
        if "考试记录" in question or "成绩记录" in question:
            return None
        student_keywords = ("学员", "学生")
        count_keywords = ("多少", "几个", "几名", "多少个", "多少人", "学员数", "人数")
        list_keywords = ("名单", "有哪些", "列表", "信息")
        if not any(k in question for k in student_keywords):
            return None
        if not any(k in question for k in count_keywords + list_keywords):
            return None

        canonical_students = self._load_canonical("students.csv")
        canonical_instructors = self._load_canonical("instructors.csv")
        if canonical_students:
            teacher = self._teacher_name(question)
            rows = [row for row in canonical_students if row.get("instructor_name") == teacher] if teacher else canonical_students
            title = f"{teacher}的学员" if teacher else "全部学员"
            machine_counts = Counter(row.get("aircraft_type", "") for row in rows if row.get("aircraft_type"))
            names = [
                self._canonical_student_name(row)
                for row in rows
            ]
            lines = [f"{title}：{len(rows)}人。"]
            if teacher:
                instructor_id = next((row.get("instructor_id", "") for row in canonical_instructors if row.get("name") == teacher), "")
                if instructor_id:
                    lines.append(f"instructor_id：{instructor_id}")
            if machine_counts:
                lines.append("机型分布：" + "，".join(f"{k}{v}人" for k, v in machine_counts.items()))
            if any(k in question for k in list_keywords) or len(rows) <= 30:
                lines.append("学员名单：" + "、".join(names))
            return self._response(
                question=question,
                answer="\n".join(lines),
                topic="students",
                sources=[self._canonical_source("students.csv", len(canonical_students))],
                data={
                    "teacher": teacher,
                    "count": len(rows),
                    "students": [
                        {
                            "student_id": row.get("student_id", ""),
                            "name": row.get("student_name", ""),
                            "instructor_id": row.get("instructor_id", ""),
                            "instructor_name": row.get("instructor_name", ""),
                        }
                        for row in rows
                    ],
                    "machine_counts": dict(machine_counts),
                },
            )

        info = self._load_csv("学员信息.csv")
        roster = info or self._load_csv("学员名单.csv")
        if not roster:
            return None

        teacher = self._teacher_name(question)
        rows = [row for row in roster if row.get("教员") == teacher] if teacher else roster
        title = f"{teacher}的学员" if teacher else "全部学员"
        names = [self._student_name(row) for row in rows]
        machine_counts = Counter(row.get("机型", "") for row in rows if row.get("机型"))

        lines = [f"{title}：{len(rows)}人。"]
        if machine_counts:
            lines.append("机型分布：" + "，".join(f"{k}{v}人" for k, v in machine_counts.items()))
        if any(k in question for k in list_keywords) or len(rows) <= 30:
            lines.append("学员名单：" + "、".join(names))

        return self._response(
            question=question,
            answer="\n".join(lines),
            topic="students",
            sources=[self._source("学员信息.csv" if info else "学员名单.csv", len(roster))],
            data={
                "teacher": teacher,
                "count": len(rows),
                "students": names,
                "machine_counts": dict(machine_counts),
            },
        )

    def _student_name(self, row: Dict[str, str]) -> str:
        name = row.get("姓名") or row.get("学员") or "未知学员"
        gender = row.get("性别") or ""
        machine = row.get("机型") or ""
        suffix = ""
        if gender:
            suffix += f"({gender})"
        if machine:
            suffix += f" {machine}"
        return f"{name}{suffix}".strip()

    def _canonical_student_name(self, row: Dict[str, str]) -> str:
        name = row.get("student_name") or "未知学员"
        gender = row.get("gender") or ""
        machine = row.get("aircraft_type") or ""
        student_id = row.get("student_id") or ""
        suffix = ""
        if gender:
            suffix += f"({gender})"
        if machine:
            suffix += f" {machine}"
        if student_id:
            suffix += f" [{student_id}]"
        return f"{name}{suffix}".strip()

    def _answer_training_progress(self, question: str) -> Optional[Dict]:
        if requires_internal_kb(question):
            return None
        if not any(k in question for k in ("培训记录", "培训进度", "培训内容")):
            return None
        progress = self._load_csv("学员培训进度.csv")
        if not progress:
            return None
        teacher = self._teacher_name(question)
        rows = [row for row in progress if row.get("教员") == teacher] if teacher else progress
        dates = sorted({row.get("日期", "") for row in rows if row.get("日期")})
        title = f"{teacher}的培训记录" if teacher else "全部培训记录"
        answer = f"{title}：{len(rows)}条，覆盖{len(dates)}个日期。"
        return self._response(
            question,
            answer,
            "training_progress",
            [self._source("学员培训进度.csv", len(progress))],
            {"teacher": teacher, "record_count": len(rows), "date_count": len(dates)},
        )

    def _answer_prices(self, question: str) -> Optional[Dict]:
        if requires_internal_kb(question) and not any(k in question for k in ("价格", "多少钱", "费用", "学费", "收费")):
            return None
        if not any(k in question for k in ("价格", "多少钱", "费用", "学费", "收费")):
            return None
        canonical_courses = self._load_canonical("courses.csv")
        if canonical_courses:
            prices = [
                {
                    "课程": row.get("course_name", ""),
                    "价格": row.get("price", ""),
                    "时长": row.get("duration", ""),
                    "内容": row.get("content", ""),
                    "course_id": row.get("course_id", ""),
                }
                for row in canonical_courses
            ]
        else:
            prices = self._load_csv("价格表.csv")
        if not prices:
            return None

        matched_prices = self._filter_price_rows(question, prices)
        if matched_prices is None:
            return None

        lines = ["课程价格表："]
        items = []
        for row in matched_prices:
            course = row.get("课程", "")
            price = row.get("价格", "")
            duration = row.get("时长", "")
            if not course and not price:
                continue
            course_id = row.get("course_id", "")
            items.append({"course_id": course_id, "course": course, "price": price, "duration": duration, "content": row.get("内容", "")})
            line = f"- {course}"
            if course_id:
                line += f" [{course_id}]"
            line += f"：{price}"
            if duration:
                line += f"，{duration}"
            lines.append(line)
        return self._response(
            question,
            "\n".join(lines),
            "prices",
            [self._canonical_source("courses.csv", len(canonical_courses))] if canonical_courses else [self._source("价格表.csv", len(prices))],
            {"items": items},
        )

    def _filter_price_rows(self, question: str, prices: List[Dict[str, str]]) -> Optional[List[Dict[str, str]]]:
        """Return matching price rows, all rows for broad asks, or None for unknown specific asks."""
        broad_markers = ("课程价格", "价格表", "收费标准", "学费标准", "有哪些价格", "所有价格")
        if any(marker in question for marker in broad_markers):
            return prices

        normalized_q = question.lower()
        matched = []
        for row in prices:
            haystack = f"{row.get('课程', '')} {row.get('内容', '')}".lower()
            course = row.get("课程", "")
            if course and course in question:
                matched.append(row)
                continue
            # Allow partial course asks such as "教员考证多少钱" to stay in CSA.
            course_terms = [term for term in course.replace("班", " ").split() if len(term) >= 2]
            if course_terms and all(term.lower() in normalized_q for term in course_terms[:2]):
                matched.append(row)
                continue
            if haystack and any(term in haystack for term in ("utc", "上门")) and any(term in normalized_q for term in ("utc", "上门")):
                matched.append(row)

        if matched:
            return matched

        unknown_specific_markers = (
            "utc", "上门", "到校", "到场", "企业内训", "团培", "定制",
            "fpv", "穿越机",
        )
        if any(marker in normalized_q for marker in unknown_specific_markers):
            return None
        return prices

    def _answer_customers(self, question: str) -> Optional[Dict]:
        if not any(k in question for k in ("客户", "客资", "咨询", "意向")):
            return None
        # "客户管理/跟进制度/流程要求" belongs to RAG policy docs, not live CSV customer counts.
        policy_context = any(k in question for k in ("制度", "规定", "流程", "要求", "管理与跟进", "客户管理", "跟进制度"))
        structured_context = any(k in question for k in ("A类", "A 类", "B类", "B 类", "C类", "C 类", "多少", "几", "人数", "名单", "来源分布"))
        if policy_context and not structured_context:
            return None

        canonical_customers = self._load_canonical("customers.csv")
        customer_sources = self._load_canonical("customer_source_rows.csv")
        if canonical_customers:
            scoped = canonical_customers
            if "A类" in question or "A 类" in question:
                scoped = [row for row in canonical_customers if row.get("customer_class") == "A"]
            elif "B类" in question or "B 类" in question:
                scoped = [row for row in canonical_customers if row.get("customer_class") == "B"]
            elif "C类" in question or "C 类" in question:
                scoped = [row for row in canonical_customers if row.get("customer_class") == "C"]

            class_counts = Counter(row.get("customer_class") or "未分级" for row in scoped)
            source_counts = Counter()
            for row in scoped:
                for source in (row.get("sources") or "").split(";"):
                    if source:
                        source_counts[source] += 1
            lines = [f"客户实体：{len(scoped)}人，来源记录：{len(customer_sources)}条。"]
            if class_counts:
                lines.append("分级分布：" + "，".join(f"{k}: {v}人" for k, v in class_counts.items()))
            if source_counts:
                lines.append("来源分布：" + "，".join(f"{k}: {v}人" for k, v in source_counts.most_common(8)))
            needs_contact = [row for row in scoped if row.get("needs_contact_key") == "true"]
            if needs_contact:
                lines.append(f"待补联系方式：{len(needs_contact)}人。")
            return self._response(
                question,
                "\n".join(lines),
                "customers",
                [
                    self._canonical_source("customers.csv", len(canonical_customers)),
                    self._canonical_source("customer_source_rows.csv", len(customer_sources)),
                ],
                {
                    "customer_count": len(scoped),
                    "source_row_count": len(customer_sources),
                    "class_counts": dict(class_counts),
                    "source_counts": dict(source_counts),
                    "needs_contact_count": len(needs_contact),
                },
            )

        matched_files = []
        if "A类" in question or "A 类" in question:
            matched_files = ["A类客户.csv"]
        elif "B类" in question or "B 类" in question:
            matched_files = ["B类客户.csv"]
        elif "C类" in question or "C 类" in question:
            matched_files = ["C类客户.csv"]
        else:
            matched_files = ["A类客户.csv", "B类客户.csv", "C类客户.csv"]

        counts = {}
        sources = []
        lines = []
        for filename in matched_files:
            rows = self._load_csv(filename)
            if not rows:
                continue
            label = filename[0] + "类客户"
            counts[label] = len(rows)
            sources.append(self._source(filename, len(rows)))
            lines.append(f"{label}：{len(rows)}人")
            source_counts = Counter(row.get("来源", "") for row in rows if row.get("来源"))
            if source_counts:
                top_sources = "，".join(f"{k}: {v}人" for k, v in source_counts.most_common(5))
                lines.append(f"{label}来源分布：{top_sources}")

        if not lines:
            return None
        return self._response(question, "\n".join(lines), "customers", sources, {"counts": counts})

    def _answer_jobs(self, question: str) -> Optional[Dict]:
        if requires_internal_kb(question):
            return None
        primary_keywords = ("岗位", "招聘", "职位", "薪资")
        if not any(k in question for k in primary_keywords):
            employment_context = "就业" in question and any(k in question for k in ("信息", "机会") + primary_keywords)
            work_context = "工作" in question and any(k in question for k in ("机会",) + primary_keywords)
            if not employment_context and not work_context:
                return None
        if any(k in question for k in ("工作流程", "工作要求", "岗位职责", "工作职责", "职责说明", "任职要求")):
            return None
        canonical_jobs = self._load_canonical("jobs.csv")
        canonical_occurrences = self._load_canonical("job_occurrences.csv")
        if canonical_occurrences:
            dates = sorted({row.get("date", "") for row in canonical_occurrences if row.get("date")})
            scoped_rows = canonical_occurrences
            scope_label = ""
            if dates and any(k in question for k in ("今天", "今日", "当天", "最新", "最近一天")):
                latest_date = dates[-1]
                scoped_rows = [row for row in canonical_occurrences if row.get("date") == latest_date]
                scope_label = f"{latest_date} "
            scoped_job_ids = {row.get("job_id", "") for row in scoped_rows if row.get("job_id")}
            category_counts = Counter(row.get("category", "") for row in scoped_rows if row.get("category"))
            platform_counts = Counter(row.get("platform", "") for row in scoped_rows if row.get("platform"))
            lines = [
                f"{scope_label}岗位实体：{len(scoped_job_ids)}个，岗位出现记录：{len(scoped_rows)}条，canonical job_id 总数：{len(canonical_jobs)}。"
            ]
            if platform_counts:
                lines.append("平台分布：" + "，".join(f"{k}{v}条" for k, v in platform_counts.most_common(10)))
            if category_counts:
                lines.append("岗位分类：" + "，".join(f"{k}{v}个" for k, v in category_counts.most_common(10)))
            return self._response(
                question,
                "\n".join(lines),
                "jobs",
                [
                    self._canonical_source("jobs.csv", len(canonical_jobs)),
                    self._canonical_source("job_occurrences.csv", len(canonical_occurrences)),
                ],
                {
                    "job_count": len(scoped_job_ids),
                    "occurrence_count": len(scoped_rows),
                    "total_job_count": len(canonical_jobs),
                    "date_count": len(dates),
                    "scope": scope_label.strip(),
                    "category_counts": dict(category_counts),
                    "platform_counts": dict(platform_counts),
                },
            )

        jobs = self._load_csv("每日岗位信息.csv")
        if not jobs:
            return None
        dates = sorted({row.get("日期", "") for row in jobs if row.get("日期")})
        scoped_jobs = jobs
        scope_label = ""
        if dates and any(k in question for k in ("今天", "今日", "当天", "最新", "最近一天")):
            latest_date = dates[-1]
            scoped_jobs = [row for row in jobs if row.get("日期") == latest_date]
            scope_label = f"{latest_date} "
        category_counts = Counter(row.get("分类", "") for row in scoped_jobs if row.get("分类"))
        platform_counts = Counter(row.get("平台", "") for row in scoped_jobs if row.get("平台"))
        lines = [f"{scope_label}去重岗位信息：{len(scoped_jobs)}条，CSV共{len(jobs)}条，最近出现日期覆盖{len(dates)}天。"]
        if platform_counts:
            lines.append("平台分布：" + "，".join(f"{k}{v}条" for k, v in platform_counts.most_common(10)))
        if category_counts:
            lines.append("岗位分类：" + "，".join(f"{k}{v}个" for k, v in category_counts.most_common(10)))
        return self._response(
            question,
            "\n".join(lines),
            "jobs",
            [self._source("每日岗位信息.csv", len(jobs))],
            {
                "job_count": len(scoped_jobs),
                "total_job_count": len(jobs),
                "date_count": len(dates),
                "scope": scope_label.strip(),
                "category_counts": dict(category_counts),
                "platform_counts": dict(platform_counts),
            },
        )


if __name__ == "__main__":
    import json
    import sys

    router = CSARouter()
    result = router.answer(" ".join(sys.argv[1:]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
