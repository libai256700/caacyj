#!/usr/bin/env python3
"""Import the public survey into yj_practice tables in the test database."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pymysql


TASK_DIR = Path(__file__).resolve().parent
RESULT_PATH = TASK_DIR / "import_execution_result.json"

DB_CONFIG = {
    "host": "114.111.30.111",
    "port": 13306,
    "user": "yunjikeji_test",
    "password": "yunjikeji_test8978_",
    "database": "yunjikeji",
    "charset": "utf8mb4",
    "autocommit": False,
}

TENANT_ID = 1
CATEGORY_NAME = "入行专属评估"
FIELD_TYPE = "low_air"
CREATOR = "admin"
BACKUP_SUFFIX = "20260611_survey_import"

QUESTIONS = [
    {"stem": "姓名", "type": "text", "memo": "调查问卷文本题，无标准答案。", "options": []},
    {"stem": "性别", "type": "single_choice", "options": ["男", "女"]},
    {"stem": "您的年龄区间是", "type": "single_choice", "options": ["16-25岁", "26-35岁", "36-45岁", "45岁以上"]},
    {
        "stem": "您的学历及相关专业是",
        "type": "single_choice",
        "memo": "选择大专、本科、本科以上时填写补充字段：专业。",
        "options": ["高中及以下", "大专", "本科", "本科以上"],
    },
    {
        "stem": "您当前的职业状态是",
        "type": "multiple_choice",
        "memo": "选择职场人（想转行）时填写补充字段：行业经历。",
        "options": ["学生（待入行）", "职场人（想转行）", "有飞行基础"],
    },
    {"stem": "您是否了解 CAAC 执照", "type": "single_choice", "options": ["非常了解", "基本了解", "不太了解", "没听过"]},
    {"stem": "您目前是否有无人机设备", "type": "single_choice", "options": ["是", "否"]},
    {
        "stem": "您最初了解到无人机/低空经济，是因为？",
        "type": "single_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["刷短视频/刷新闻", "身边朋友推荐", "自己/公司有需求", "纯兴趣爱好", "其他"],
    },
    {
        "stem": "您能说出几个低空经济的具体工作岗位？",
        "type": "single_choice",
        "memo": "页面内部值：说不出、1-2个、3个以上、非常了解。选择后 3 项时填写补充字段：了解的岗位名称。",
        "options": ["完全无概念", "能说出1-2个", "能说出3个以上", "能说出5个以上"],
    },
    {
        "stem": "您学习无人机，最核心的诉求是？",
        "type": "multiple_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["先拿证备用", "怕错过风口", "赚外快", "想全职转行", "公司要求", "纯兴趣", "其他"],
    },
    {
        "stem": "您的过往工作/学习经历中，最擅长的是？",
        "type": "multiple_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["动手操作", "视频制作", "电脑技术", "沟通谈判", "工程施工", "行业经验", "教学培训", "无突出技能", "其他"],
    },
    {
        "stem": "您拥有哪些可以和低空经济结合的资源？",
        "type": "multiple_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["行业人脉", "传媒资源", "商家资源", "自媒体", "创业资金", "无直接可利用资源", "其他"],
    },
    {
        "stem": "您觉得自己最大的性格特点是？",
        "type": "multiple_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["细心耐心", "外向开朗", "逻辑清晰", "创意十足", "踏实稳重", "其他"],
    },
    {
        "stem": "您的兴趣爱好是？",
        "type": "multiple_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["户外运动", "球类运动", "健身锻炼", "旅游出行", "影音娱乐", "摄影摄像", "阅读学习", "无人机飞行", "其他"],
    },
    {
        "stem": "以下低空经济细分方向，您最感兴趣的是？",
        "type": "multiple_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["航拍传媒", "工程测绘", "行业巡检", "农业植保", "无人机清洗", "无人机吊运", "应急救援", "无人机培训", "装调维修", "无人机表演", "不清楚希望评估", "其他"],
    },
    {"stem": "您能接受的工作场景和模式是？", "type": "multiple_choice", "options": ["经常户外作业", "室内+户外结合", "办公室办公", "自由职业", "全职", "兼职"]},
    {
        "stem": "您每周能投入的有效学习时间是？",
        "type": "single_choice",
        "memo": "页面内部值：周末、每日1-2h、脱产、不确定。",
        "options": ["仅周末抽空学习", "每日固定学习1-2小时", "可全程脱产学习", "目前暂时不确定"],
    },
    {"stem": "您能接受的学习和待岗周期是？", "type": "single_choice", "options": ["1个月以内", "1-2个月", "2-3个月", "6个月以内"]},
    {"stem": "您能接受的学习预算是？", "type": "single_choice", "options": ["10000元以内", "10000-20000元", "20000元以上", "可根据岗位需要设定预算"]},
    {
        "stem": "如果给您一份专属的评估报告，您最希望得到什么内容？",
        "type": "multiple_choice",
        "memo": "选择其他时填写补充说明。",
        "options": ["是否适合进入低空经济行业", "最适合的细分方向和岗位信息", "具体的学习路径", "行业合规飞行与安全须知", "其他"],
    },
    {"stem": "您还有其他问题或想补充的内容吗？", "type": "text", "memo": "调查问卷文本域，非必填，无标准答案。", "options": []},
]


def fetch_one(cursor, sql: str, args=None):
    cursor.execute(sql, args)
    return cursor.fetchone()


def fetch_all(cursor, sql: str, args=None):
    cursor.execute(sql, args)
    return cursor.fetchall()


def ensure_question_type_width(cursor):
    for table in ("yj_practice_exercises", "yj_practice_exercises_answer", "yj_practice_exercises_answer_child"):
        cursor.execute(
            """
            SELECT CHARACTER_MAXIMUM_LENGTH AS length
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'question_type'
            """,
            (table,),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"{table}.question_type column not found")
        if row["length"] < 32:
            cursor.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `question_type` varchar(32) NOT NULL COMMENT '题型（字典表 yj_practice_question_type）'")


def ensure_dict(cursor):
    cursor.execute(
        """
        INSERT INTO system_dict_type
          (name, type, status, remark, creator, create_time, updater, update_time, deleted, deleted_time)
        SELECT '练习题题型', 'yj_practice_question_type', 0, '练习题目管理题型：单选题/多选题/判断题/文本题', %s, NOW(), %s, NOW(), b'0', NULL
        WHERE NOT EXISTS (
          SELECT 1 FROM system_dict_type WHERE type = 'yj_practice_question_type' AND deleted = b'0'
        )
        """,
        (CREATOR, CREATOR),
    )
    rows = [
        (1, "单选题", "single_choice", "primary", "调查问卷单选题"),
        (2, "多选题", "multiple_choice", "success", "调查问卷多选题"),
        (3, "判断题", "judge", "warning", "练习题判断题"),
        (4, "文本题", "text", "info", "调查问卷文本题，无标准答案"),
    ]
    for sort, label, value, color_type, remark in rows:
        cursor.execute(
            """
            INSERT INTO system_dict_data
              (sort, label, value, dict_type, status, color_type, css_class, remark, creator, create_time, updater, update_time, deleted)
            SELECT %s, %s, %s, 'yj_practice_question_type', 0, %s, '', %s, %s, NOW(), %s, NOW(), b'0'
            WHERE NOT EXISTS (
              SELECT 1 FROM system_dict_data
              WHERE dict_type = 'yj_practice_question_type' AND value = %s AND deleted = b'0'
            )
            """,
            (sort, label, value, color_type, remark, CREATOR, CREATOR, value),
        )


def create_backup(cursor):
    backups = {
        "yj_practice_category": f"yj_practice_category_bak_{BACKUP_SUFFIX}",
        "yj_practice_exercises": f"yj_practice_exercises_bak_{BACKUP_SUFFIX}",
        "yj_practice_exercises_answer": f"yj_practice_exercises_answer_bak_{BACKUP_SUFFIX}",
        "yj_practice_exercises_answer_child": f"yj_practice_exercises_answer_child_bak_{BACKUP_SUFFIX}",
    }
    for source, backup in backups.items():
        cursor.execute(f"CREATE TABLE IF NOT EXISTS `{backup}` LIKE `{source}`")

    cursor.execute(
        f"""
        INSERT IGNORE INTO yj_practice_category_bak_{BACKUP_SUFFIX}
        SELECT *
        FROM yj_practice_category
        WHERE tenant_id = %s AND category_name = %s AND deleted = b'0'
        """,
        (TENANT_ID, CATEGORY_NAME),
    )
    cursor.execute(
        f"""
        INSERT IGNORE INTO yj_practice_exercises_bak_{BACKUP_SUFFIX}
        SELECT e.*
        FROM yj_practice_exercises e
        JOIN yj_practice_category c ON c.id = e.category_id
        WHERE c.tenant_id = %s AND c.category_name = %s AND c.deleted = b'0' AND e.deleted = b'0'
        """,
        (TENANT_ID, CATEGORY_NAME),
    )
    cursor.execute(
        f"""
        INSERT IGNORE INTO yj_practice_exercises_answer_bak_{BACKUP_SUFFIX}
        SELECT a.*
        FROM yj_practice_exercises_answer a
        JOIN yj_practice_exercises e ON e.id = a.exercises_id
        JOIN yj_practice_category c ON c.id = e.category_id
        WHERE c.tenant_id = %s AND c.category_name = %s AND c.deleted = b'0' AND e.deleted = b'0' AND a.deleted = b'0'
        """,
        (TENANT_ID, CATEGORY_NAME),
    )
    cursor.execute(
        f"""
        INSERT IGNORE INTO yj_practice_exercises_answer_child_bak_{BACKUP_SUFFIX}
        SELECT ac.*
        FROM yj_practice_exercises_answer_child ac
        JOIN yj_practice_exercises_answer a ON a.id = ac.answer_id
        JOIN yj_practice_exercises e ON e.id = a.exercises_id
        JOIN yj_practice_category c ON c.id = e.category_id
        WHERE c.tenant_id = %s AND c.category_name = %s AND c.deleted = b'0' AND e.deleted = b'0' AND a.deleted = b'0' AND ac.deleted = b'0'
        """,
        (TENANT_ID, CATEGORY_NAME),
    )


def ensure_category(cursor) -> int:
    row = fetch_one(
        cursor,
        """
        SELECT id FROM yj_practice_category
        WHERE tenant_id = %s AND category_name = %s AND deleted = b'0'
        ORDER BY id LIMIT 1
        """,
        (TENANT_ID, CATEGORY_NAME),
    )
    if row:
        category_id = row["id"]
        cursor.execute(
            """
            UPDATE yj_practice_category
            SET category_status = b'1', field_type = %s, updater = %s, update_time = NOW()
            WHERE id = %s
            """,
            (FIELD_TYPE, CREATOR, category_id),
        )
        return category_id

    cursor.execute(
        """
        INSERT INTO yj_practice_category
          (category_name, category_status, field_type, sort_no, tenant_id, creator, create_time, updater, update_time, deleted)
        VALUES (%s, b'1', %s, 1, %s, %s, NOW(), %s, NOW(), b'0')
        """,
        (CATEGORY_NAME, FIELD_TYPE, TENANT_ID, CREATOR, CREATOR),
    )
    return cursor.lastrowid


def upsert_question(cursor, category_id: int, question: dict, sort_no: int) -> int:
    row = fetch_one(
        cursor,
        """
        SELECT id FROM yj_practice_exercises
        WHERE category_id = %s AND question_stem = %s AND tenant_id = %s AND deleted = b'0'
        ORDER BY id LIMIT 1
        """,
        (category_id, question["stem"], TENANT_ID),
    )
    memo = question.get("memo") or "调查问卷题，无标准答案。"
    if row:
        question_id = row["id"]
        cursor.execute(
            """
            UPDATE yj_practice_exercises
            SET question_type = %s, question_status = b'1', score = 0, sort_no = %s,
                correct_memo = %s, updater = %s, update_time = NOW()
            WHERE id = %s
            """,
            (question["type"], sort_no, memo, CREATOR, question_id),
        )
    else:
        cursor.execute(
            """
            INSERT INTO yj_practice_exercises
              (category_id, question_stem, question_type, question_status, score, sort_no, correct_memo,
               tenant_id, creator, create_time, updater, update_time, deleted)
            VALUES (%s, %s, %s, b'1', 0, %s, %s, %s, %s, NOW(), %s, NOW(), b'0')
            """,
            (category_id, question["stem"], question["type"], sort_no, memo, TENANT_ID, CREATOR, CREATOR),
        )
        question_id = cursor.lastrowid

    cursor.execute("DELETE FROM yj_practice_exercises_answer WHERE exercises_id = %s AND tenant_id = %s", (question_id, TENANT_ID))
    for idx, option in enumerate(question["options"], start=1):
        cursor.execute(
            """
            INSERT INTO yj_practice_exercises_answer
              (exercises_id, question_type, answer_code, answer_content, is_correct, sort_no,
               tenant_id, creator, create_time, updater, update_time, deleted)
            VALUES (%s, %s, %s, %s, b'0', %s, %s, %s, NOW(), %s, NOW(), b'0')
            """,
            (question_id, question["type"], chr(64 + idx), option, idx, TENANT_ID, CREATOR, CREATOR),
        )
    return question_id


def collect_state(cursor):
    category = fetch_one(
        cursor,
        """
        SELECT id, category_name, field_type, sort_no, tenant_id
        FROM yj_practice_category
        WHERE tenant_id = %s AND category_name = %s AND deleted = b'0'
        ORDER BY id LIMIT 1
        """,
        (TENANT_ID, CATEGORY_NAME),
    )
    category_id = category["id"] if category else None
    summary = {"category": category}
    if category_id:
        summary["question_count"] = fetch_one(
            cursor,
            "SELECT COUNT(*) AS count FROM yj_practice_exercises WHERE category_id = %s AND tenant_id = %s AND deleted = b'0'",
            (category_id, TENANT_ID),
        )
        summary["answer_count"] = fetch_one(
            cursor,
            """
            SELECT COUNT(*) AS count
            FROM yj_practice_exercises_answer a
            JOIN yj_practice_exercises e ON e.id = a.exercises_id
            WHERE e.category_id = %s AND a.tenant_id = %s AND e.deleted = b'0' AND a.deleted = b'0'
            """,
            (category_id, TENANT_ID),
        )
        summary["question_types"] = fetch_all(
            cursor,
            """
            SELECT question_type, COUNT(*) AS count
            FROM yj_practice_exercises
            WHERE category_id = %s AND tenant_id = %s AND deleted = b'0'
            GROUP BY question_type
            ORDER BY question_type
            """,
            (category_id, TENANT_ID),
        )
    return summary


def main() -> int:
    result = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
        "category_name": CATEGORY_NAME,
        "tenant_id": TENANT_ID,
        "source_question_count": len(QUESTIONS),
    }
    conn = pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            ensure_question_type_width(cursor)
            ensure_dict(cursor)
            create_backup(cursor)
            result["before"] = collect_state(cursor)
            category_id = ensure_category(cursor)
            result["category_id"] = category_id
            imported_ids = []
            for idx, question in enumerate(QUESTIONS, start=1):
                imported_ids.append(upsert_question(cursor, category_id, question, idx))
            result["imported_question_ids"] = imported_ids
            result["after"] = collect_state(cursor)

            question_count = result["after"]["question_count"]["count"]
            if question_count != len(QUESTIONS):
                raise RuntimeError(f"post-check failed: expected {len(QUESTIONS)} questions, got {question_count}")

        conn.commit()
        result["status"] = "committed"
        return 0
    except Exception as exc:
        conn.rollback()
        result["status"] = "rolled_back"
        result["error"] = repr(exc)
        return 1
    finally:
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
