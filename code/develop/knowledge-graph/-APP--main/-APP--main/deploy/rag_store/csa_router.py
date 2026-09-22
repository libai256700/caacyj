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
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from rag_store.route_policy import requires_internal_kb
except ImportError:
    from route_policy import requires_internal_kb

GROUND_STATION_TOPIC_TERMS = (
    "地面站", "地面站考试", "地面站真题", "地面站题库", "地面站实操",
)
GROUND_STATION_TREND_TERMS = (
    "特点", "变化", "趋势", "新增", "新题", "新题型", "考点变化", "出题特点",
)
GROUND_STATION_TIME_TERMS = (
    "时间", "日期", "月份", "月度", "上半年", "最近", "最新", "新增", "版本", "批次", "2026",
)
GROUND_STATION_CONTEXT_TERMS = (
    "地面站", "考试条件", "真题", "题型", "题库", "实操", "专项训练",
)
GROUND_STATION_TYPE_ALIASES = {
    "避让点": "地面站避让点题型",
    "空域": "空域限制或地形限制题型",
    "地形": "空域限制或地形限制题型",
    "罗盘": "罗盘双坐标题型",
    "双坐标": "罗盘双坐标题型",
    "罗盘双坐标": "罗盘双坐标题型",
    "罗盘+双坐标": "罗盘双坐标题型",
    "罗盘+双坐标题型": "罗盘双坐标题型",
    "罗盘➕双坐标": "罗盘双坐标题型",
    "罗盘➕双坐标题型": "罗盘双坐标题型",
    "双经纬度": "双经纬度题型",
    "双起飞点": "双起飞点题型",
    "同一直线": "同一直线题型",
    "三角函数": "三角函数题型",
    "航向相同": "航向相同相反题型",
    "航向相反": "航向相同相反题型",
    "时钟夹角": "时钟夹角题题型",
    "夹角": "夹角题题型",
}


DEFAULT_DATA_DIR = Path(os.environ.get(
    "CSA_DATA_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "structured"),
))
DEFAULT_CANONICAL_DIR = Path(os.environ.get(
    "CSA_CANONICAL_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "canonical"),
))
DEFAULT_EXCLUSIONS_PATH = Path(os.environ.get(
    "CSA_EXCLUSIONS_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "exclusions" / "exclusions.json"),
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
        path = self._resolve_path(filename)
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
        path = self._resolve_path(filename)
        if not path.exists():
            return {"rows": 0, "mtime": None, "cache": str(self.db_path), "refreshed_at": None}
        stat = path.stat()
        if self._needs_refresh(filename, path, stat):
            self._refresh(filename, path, stat)
        conn = self.connect()
        row = conn.execute(
            "SELECT row_count, mtime_ns, refreshed_at FROM csa_files WHERE filename = ?",
            (filename,),
        ).fetchone()
        if not row:
            return {
                "rows": 0,
                "mtime": int(stat.st_mtime),
                "cache": str(self.db_path),
                "refreshed_at": None,
            }
        return {
            "rows": int(row["row_count"]),
            "mtime": int(int(row["mtime_ns"]) / 1_000_000_000),
            "cache": str(self.db_path),
            "refreshed_at": row["refreshed_at"],
        }

    def _resolve_path(self, filename: str) -> Path:
        return self.data_dir / filename

    def _needs_refresh(self, filename: str, path: Path, stat: os.stat_result) -> bool:
        conn = self.connect()
        row = conn.execute(
            "SELECT mtime_ns, size_bytes FROM csa_files WHERE filename = ?",
            (filename,),
        ).fetchone()
        if row is None:
            return True
        try:
            return (
                int(row["mtime_ns"]) != stat.st_mtime_ns
                or int(row["size_bytes"]) != stat.st_size
            )
        except (TypeError, ValueError):
            # 历史/旧备份缓存行可能带 NULL 或非法元数据（旧可空 schema 遗留，
            # CREATE TABLE IF NOT EXISTS 不会补 NOT NULL 约束）。此时视为需要刷新，
            # _refresh 会用真实 stat 写回非空值并自愈该行，避免 int(None) 崩溃。
            return True

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
        exclusions_path: str | Path = DEFAULT_EXCLUSIONS_PATH,
    ):
        self.data_dir = Path(data_dir)
        self.canonical_dir = Path(canonical_dir)
        self.exclusions_path = Path(exclusions_path)
        self.cache = CSATableCache(self.data_dir, cache_db)

    def answer(self, question: str) -> Optional[Dict]:
        q = (question or "").strip()
        if not q:
            return None
        for handler in (
            self._answer_ground_station_exam,
        ):
            result = handler(q)
            if result:
                return result
        return None

    def _load_canonical(self, name: str) -> List[Dict[str, str]]:
        path = self.canonical_dir / name
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            return list(csv.DictReader(fh))

    def _canonical_source(self, filename: str, rows: int) -> Dict:
        path = self.canonical_dir / filename
        mtime = int(path.stat().st_mtime) if path.exists() else None
        return {
            "type": "canonical_csv",
            "file": filename,
            "doc_name": filename,
            "source_doc": filename,
            "path": str(path),
            "rows": rows,
            "mtime": mtime,
            "source_updated_at": self._format_epoch(mtime),
        }

    def _response(self, question: str, answer: str, topic: str, sources: List[Dict], data: Dict = None) -> Dict:
        normalized_sources = [source for source in sources if source]
        freshness = self._freshness_summary(normalized_sources)
        answer_with_freshness = answer
        if freshness["summary_line"]:
            answer_with_freshness = f"{answer}\n{freshness['summary_line']}"
        payload_data = dict(data or {})
        payload_data["freshness"] = freshness
        return {
            "query": question,
            "rewritten": question,
            "intent": "structured_csv",
            "route": "csa",
            "answer": answer_with_freshness,
            "sources": normalized_sources,
            "evidence": [{"type": "csv", "topic": topic}],
            "data": payload_data,
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
                "freshness": freshness,
            },
        }

    def _format_epoch(self, ts: Optional[int]) -> Optional[str]:
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def _format_sqlite_utc(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return value
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def _freshness_summary(self, sources: List[Dict]) -> Dict:
        latest_source_mtime = max(
            (source.get("mtime") for source in sources if source.get("mtime") is not None),
            default=None,
        )
        latest_cache_refresh_raw = max(
            (source.get("cache_refreshed_at") for source in sources if source.get("cache_refreshed_at")),
            default=None,
        )
        latest_source_text = self._format_epoch(latest_source_mtime)
        latest_cache_refresh_text = self._format_sqlite_utc(latest_cache_refresh_raw)
        summary_parts = []
        if latest_source_text:
            summary_parts.append(f"数据更新时间：{latest_source_text}")
        if latest_cache_refresh_text:
            summary_parts.append(f"缓存刷新时间：{latest_cache_refresh_text}")
        return {
            "latest_source_mtime": latest_source_mtime,
            "latest_source_updated_at": latest_source_text,
            "latest_cache_refreshed_at": latest_cache_refresh_raw,
            "latest_cache_refreshed_at_local": latest_cache_refresh_text,
            "sources": [
                {
                    "file": source.get("file"),
                    "type": source.get("type"),
                    "rows": source.get("rows"),
                    "source_updated_at": source.get("source_updated_at"),
                    "cache_refreshed_at": source.get("cache_refreshed_at"),
                    "cache_refreshed_at_local": source.get("cache_refreshed_at_local"),
                }
                for source in sources
            ],
            "summary_line": "；".join(summary_parts),
        }

    # 问题里点名了具体的人、但不在已知教员表时，禁止回退成全员名单（2026-07-07 修复）
    _PERSON_PATTERNS = (
        re.compile(r"([一-龥]{2,4}?)(?:教员|老师|教练)?(?:负责|带教|带了|带|名下)"),
        re.compile(r"([一-龥]{2,4}?)(?:的学员|有多少(?:个|名|位)?学员|有几(?:个|名|位)学员)"),
    )
    _PERSON_STOPWORDS = (
        "云技", "公司", "我们", "咱们", "一共", "总共", "全部", "所有", "目前",
        "现在", "今年", "本月", "上月", "累计", "分别", "每位", "各位", "哪位",
        "哪个", "哪些", "什么", "教员", "老师", "教练", "学员", "机构",
    )
    _STUDENT_PROFILE_TERMS = (
        "机型", "教员", "老师", "教练", "班型", "性别", "年龄", "状态",
        "顾问", "报名", "考试", "证书", "拿证", "信息", "详情", "资料", "是谁",
    )

    _STUDENT_EXAM_TERMS = (
        "考试", "考试记录", "考试信息", "成绩", "理论", "综合问答", "实操",
        "实飞", "地面站", "拿证", "挂科", "补考",
    )

    def _answer_ground_station_exam(self, question: str) -> Optional[Dict]:
        has_ground_station_scope = any(k in question for k in GROUND_STATION_TOPIC_TERMS)
        has_known_type = any(k in question for k in GROUND_STATION_TYPE_ALIASES)
        if not (has_ground_station_scope or has_known_type):
            return None
        if has_known_type and not has_ground_station_scope and not any(k in question for k in GROUND_STATION_CONTEXT_TERMS):
            return None
        if not any(k in question for k in ("条件", "题型", "能力", "专项", "训练", "分布", "常见", "高度", "速度", "转弯", "航向", "经纬度", "避让", "空域", "地形", "夹角", "罗盘") + GROUND_STATION_TREND_TERMS):
            return None

        cases = self._load_canonical("ground_station_exam_cases.csv")
        conditions = self._load_canonical("ground_station_exam_conditions.csv")
        skills = self._load_canonical("ground_station_exam_skills.csv")
        if not cases:
            return None

        question_type = self._ground_station_question_type(question, cases)
        scoped_cases = self._scope_ground_station_cases(question, cases, question_type)
        scoped_case_ids = {row.get("case_id") for row in scoped_cases}
        scoped_conditions = [row for row in conditions if row.get("case_id") in scoped_case_ids]
        scoped_skills = [row for row in skills if row.get("case_id") in scoped_case_ids]
        title = question_type or "地面站考试条件"

        sources = [
            self._canonical_source("ground_station_exam_cases.csv", len(cases)),
            self._canonical_source("ground_station_exam_conditions.csv", len(conditions)),
            self._canonical_source("ground_station_exam_skills.csv", len(skills)),
        ]

        if any(k in question for k in GROUND_STATION_TREND_TERMS + GROUND_STATION_TIME_TERMS):
            return self._ground_station_temporal_response(
                question,
                title,
                scoped_cases,
                scoped_conditions,
                scoped_skills,
                sources,
                question_type,
            )

        if any(k in question for k in ("能力", "专项", "训练", "知识点", "主要考")):
            skill_counts = Counter(row.get("skill_label", "") for row in scoped_skills if row.get("skill_label"))
            lines = [f"{title}：{len(scoped_cases)}个案例，关联专项能力标签{len(skill_counts)}类。"]
            if skill_counts:
                lines.append("主要能力：" + "，".join(f"{label}{count}次" for label, count in skill_counts.most_common(12)))
            return self._response(
                question,
                "\n".join(lines),
                "ground_station_exam",
                sources,
                {
                    "question_type": question_type,
                    "case_count": len(scoped_cases),
                    "condition_count": len(scoped_conditions),
                    "skill_counts": dict(skill_counts),
                },
            )

        condition_type_counts = Counter()
        for row in scoped_conditions:
            for label in (row.get("condition_type") or "other").split(";"):
                if label:
                    condition_type_counts[label] += 1
        height_values = Counter(v for row in scoped_conditions for v in (row.get("height_values") or "").split(";") if v)
        speed_values = Counter(v for row in scoped_conditions for v in (row.get("speed_values") or "").split(";") if v)
        turn_examples = [
            row.get("raw_text", "")
            for row in scoped_conditions
            if "turn_hold_loop" in (row.get("condition_type") or "")
        ][:6]

        lines = [f"{title}：{len(scoped_cases)}个案例，{len(scoped_conditions)}条可结构化考试条件。"]
        if condition_type_counts:
            lines.append("条件类型多标签命中次数：" + "，".join(f"{k}{v}条" for k, v in condition_type_counts.most_common(10)))
        if any(k in question for k in ("高度", "速度", "转弯", "分布")):
            if height_values:
                lines.append("常见高度值：" + "，".join(f"{k}{v}次" for k, v in height_values.most_common(8)))
            if speed_values:
                lines.append("常见速度值：" + "，".join(f"{k}{v}次" for k, v in speed_values.most_common(8)))
            if turn_examples:
                lines.append("转弯/停留/循环示例：" + "；".join(turn_examples[:4]))
        else:
            examples = [row.get("raw_text", "") for row in scoped_conditions[:8]]
            if examples:
                lines.append("常见条件示例：" + "；".join(examples))

        return self._response(
            question,
            "\n".join(lines),
            "ground_station_exam",
            sources,
            {
                "question_type": question_type,
                "case_count": len(scoped_cases),
                "condition_count": len(scoped_conditions),
                "condition_type_counts": dict(condition_type_counts),
                "height_values": dict(height_values.most_common(20)),
                "speed_values": dict(speed_values.most_common(20)),
                "turn_examples": turn_examples,
            },
        )

    def _scope_ground_station_cases(
        self,
        question: str,
        cases: List[Dict[str, str]],
        question_type: Optional[str],
    ) -> List[Dict[str, str]]:
        scoped = [row for row in cases if row.get("question_type") == question_type] if question_type else list(cases)
        if any(k in question for k in ("2026H1", "2026年上半年", "上半年")):
            scoped = [row for row in scoped if row.get("source_version") == "2026H1" or row.get("batch") == "2026H1"]
        elif "2026" in question:
            scoped = [row for row in scoped if (row.get("exam_date") or "").startswith("2026")]
        if any(k in question for k in ("最近", "最新")) and scoped:
            latest_date = max((row.get("exam_date") or "") for row in scoped)
            if latest_date:
                scoped = [row for row in scoped if row.get("exam_date") == latest_date]
        return scoped

    def _ground_station_temporal_response(
        self,
        question: str,
        title: str,
        cases: List[Dict[str, str]],
        conditions: List[Dict[str, str]],
        skills: List[Dict[str, str]],
        sources: List[Dict],
        question_type: Optional[str],
    ) -> Dict:
        dates = sorted({row.get("exam_date", "") for row in cases if row.get("exam_date")})
        batches = Counter(row.get("source_version") or row.get("batch") or "unknown" for row in cases)
        month_counts = Counter((row.get("exam_date") or "")[:7] for row in cases if row.get("exam_date"))
        type_counts = Counter(row.get("question_type", "") for row in cases if row.get("question_type"))
        condition_type_counts = Counter()
        for row in conditions:
            for label in (row.get("condition_type") or "other").split(";"):
                if label:
                    condition_type_counts[label] += 1
        skill_counts = Counter(row.get("skill_label", "") for row in skills if row.get("skill_label"))
        quality_counts = Counter(flag for row in cases for flag in (row.get("quality_flags") or "").split(";") if flag)
        lines = [
            f"{title}：当前匹配{len(cases)}个案例、{len(conditions)}条结构化条件。",
            "版本/批次：" + "，".join(f"{batch}{count}例" for batch, count in batches.most_common()) if batches else "版本/批次：未标记",
        ]
        if dates:
            lines.append(f"考试日期范围：{dates[0]} 至 {dates[-1]}。")
        if month_counts:
            lines.append("月度案例分布：" + "，".join(f"{month}{count}例" for month, count in sorted(month_counts.items())))
        if type_counts and not question_type:
            lines.append("题型案例分布：" + "，".join(f"{label}{count}例" for label, count in type_counts.most_common(10)))
        if condition_type_counts:
            lines.append("条件类型多标签命中次数：" + "，".join(f"{label}{count}次" for label, count in condition_type_counts.most_common(8)))
        if skill_counts:
            lines.append("高频专项能力：" + "，".join(f"{label}{count}次" for label, count in skill_counts.most_common(8)))
        if any(k in question for k in GROUND_STATION_TREND_TERMS):
            lines.append("边界说明：当前知识库只同步了2026H1这一批地面站考试条件，库内没有上一批次对照数据；因此只能分析2026上半年出题特点，不能单凭当前库证明相对往期的考点变化。")
        if quality_counts:
            lines.append("质量标记：" + "，".join(f"{label}{count}例" for label, count in quality_counts.most_common(5)))
        return self._response(
            question,
            "\n".join(lines),
            "ground_station_exam",
            sources,
            {
                "question_type": question_type,
                "case_count": len(cases),
                "condition_count": len(conditions),
                "batches": dict(batches),
                "date_range": [dates[0], dates[-1]] if dates else [],
                "month_counts": dict(sorted(month_counts.items())),
                "question_type_counts": dict(type_counts),
                "condition_type_counts": dict(condition_type_counts),
                "skill_counts": dict(skill_counts),
                "quality_flags": dict(quality_counts),
                "comparison_available": False,
            },
        )

    def _ground_station_question_type(self, question: str, cases: List[Dict[str, str]]) -> Optional[str]:
        types = sorted({row.get("question_type", "") for row in cases if row.get("question_type")}, key=len, reverse=True)
        compact_question = question.replace("+", "").replace("➕", "")
        for question_type in types:
            compact_type = question_type.replace("题型", "").replace("+", "").replace("➕", "")
            if question_type in question or compact_type in compact_question:
                return question_type
        available = {row.get("question_type", "") for row in cases}
        for key, value in GROUND_STATION_TYPE_ALIASES.items():
            if key in question and value in available:
                return value
        return None

