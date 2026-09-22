import csv
import json
import os
import re
from pathlib import Path


TASK_DIR = Path(__file__).resolve().parent
RAW_DIR = TASK_DIR.parent.parent / "010-原始需求"
QUESTION_CSV = TASK_DIR / "20260513233500-question-import-staging-real.csv"
OPTION_CSV = TASK_DIR / "20260513233600-question-import-option-staging-real.csv"
REPORT_MD = TASK_DIR / "20260514043000-comprehensive-qa-asset-refresh-report.md"

QUESTION_FIELDS = [
    "batch_no",
    "source_file",
    "source_locator",
    "category_code",
    "question_code",
    "question_type",
    "stem",
    "correct_answer",
    "analysis",
    "score",
    "sort_no",
    "source_ref",
    "parse_status",
    "review_reason",
    "options_payload_json",
    "answer_payload_json",
    "raw_payload_json",
]

OPTION_FIELDS = [
    "batch_no",
    "question_code",
    "option_code",
    "option_label",
    "option_content",
    "is_correct",
    "sort_no",
]

QUESTION_RE = re.compile(r"^\s*(\d+)\.(.*)$")
OPTION_RE = re.compile(r"^\s*([A-D])\.(.*)$")
ANSWER_RE = re.compile(r"^\s*参考答案[：:]\s*(.+?)\s*$")
ANALYSIS_RE = re.compile(r"^\s*解析[：:]?\s*(.*)$")


def find_source_markdown() -> Path:
    for name in os.listdir(RAW_DIR):
        if name.endswith(".md") and not name.startswith("REQ-"):
            return RAW_DIR / name
    raise FileNotFoundError("未找到综合问答 markdown 源文件")


def normalize_line(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\u00a0", " ").replace("\u3000", " ")
    return text.strip()


def parse_markdown(path: Path):
    with path.open("r", encoding="utf-8") as f:
        lines = [normalize_line(line.rstrip("\n")) for line in f]

    questions = []
    current = None
    analysis_mode = False

    def flush():
        nonlocal current, analysis_mode
        if current is not None:
            current["analysis"] = "\n".join([line for line in current["analysis_lines"] if line]).strip()
            questions.append(current)
        current = None
        analysis_mode = False

    for line in lines:
        if not line:
            if analysis_mode and current is not None:
                current["analysis_lines"].append("")
            continue

        match = QUESTION_RE.match(line)
        if match:
            flush()
            current = {
                "source_no": int(match.group(1)),
                "stem": match.group(2).strip(),
                "options": [],
                "answer": "",
                "analysis_lines": [],
                "raw_lines": [line],
            }
            continue

        if current is None:
            continue

        current["raw_lines"].append(line)

        opt = OPTION_RE.match(line)
        if opt:
            current["options"].append(
                {
                    "optionCode": opt.group(1),
                    "optionContent": opt.group(2).strip(),
                }
            )
            analysis_mode = False
            continue

        ans = ANSWER_RE.match(line)
        if ans:
            letters = []
            for item in re.findall(r"[A-D]", ans.group(1).upper()):
                if item not in letters:
                    letters.append(item)
            current["answer"] = ",".join(letters)
            analysis_mode = False
            continue

        ana = ANALYSIS_RE.match(line)
        if ana:
            analysis_mode = True
            first = ana.group(1).strip()
            if first:
                current["analysis_lines"].append(first)
            continue

        if analysis_mode:
            current["analysis_lines"].append(line)
        elif current["options"] and not current["answer"]:
            current["stem"] = (current["stem"] + " " + line).strip()
        elif current["answer"]:
            current["analysis_lines"].append(line)
        else:
            current["stem"] = (current["stem"] + " " + line).strip()

    flush()
    return questions


def load_question_rows():
    with QUESTION_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_option_rows():
    with OPTION_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_question_rows(rows):
    with QUESTION_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUESTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_option_rows(rows):
    with OPTION_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OPTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    source_md = find_source_markdown()
    parsed_questions = parse_markdown(source_md)
    if len(parsed_questions) != 199:
        raise RuntimeError(f"综合问答解析题数异常，期望 199，实际 {len(parsed_questions)}")

    question_rows = load_question_rows()
    option_rows = load_option_rows()

    cqa_rows = [row for row in question_rows if row["question_code"].startswith("Q-CQA-")]
    if len(cqa_rows) != 199:
        raise RuntimeError(f"现有 Q-CQA 题目行数异常，期望 199，实际 {len(cqa_rows)}")

    parsed_map = {f"Q-CQA-{item['source_no']:04d}": item for item in parsed_questions}
    refreshed_question_rows = []
    created_option_rows = []

    for row in question_rows:
        code = row["question_code"]
        if not code.startswith("Q-CQA-"):
            refreshed_question_rows.append(row)
            continue

        parsed = parsed_map.get(code)
        if parsed is None:
            raise RuntimeError(f"未找到题目 {code} 的 markdown 解析结果")

        option_payload = json.dumps(parsed["options"], ensure_ascii=False)
        answer_payload = json.dumps({"correctAnswer": parsed["answer"]}, ensure_ascii=False)
        raw_payload = json.dumps(
            {
                "sourceLines": parsed["raw_lines"],
                "sourceFile": source_md.name,
            },
            ensure_ascii=False,
        )

        row["source_file"] = "raw-bank/综合问答.md"
        row["source_locator"] = f"第{parsed['source_no']}题"
        row["source_ref"] = f"raw-bank/综合问答.md#第{parsed['source_no']}题"
        row["stem"] = parsed["stem"]
        row["correct_answer"] = parsed["answer"]
        row["analysis"] = parsed["analysis"]
        row["parse_status"] = "parsed"
        row["review_reason"] = ""
        row["options_payload_json"] = option_payload
        row["answer_payload_json"] = answer_payload
        row["raw_payload_json"] = raw_payload

        refreshed_question_rows.append(row)

        correct_set = {part for part in parsed["answer"].split(",") if part}
        for index, option in enumerate(parsed["options"], start=1):
            created_option_rows.append(
                {
                    "batch_no": row["batch_no"],
                    "question_code": code,
                    "option_code": option["optionCode"],
                    "option_label": option["optionCode"],
                    "option_content": option["optionContent"],
                    "is_correct": "1" if option["optionCode"] in correct_set else "0",
                    "sort_no": str(index * 10),
                }
            )

    refreshed_option_rows = [row for row in option_rows if not row["question_code"].startswith("Q-CQA-")]
    refreshed_option_rows.extend(created_option_rows)

    write_question_rows(refreshed_question_rows)
    write_option_rows(refreshed_option_rows)

    total_option_count = len(created_option_rows)
    max_option_count = max(len(item["options"]) for item in parsed_questions)
    min_option_count = min(len(item["options"]) for item in parsed_questions)
    multi_answer_count = sum(1 for item in parsed_questions if "," in item["answer"])

    report = "\n".join(
        [
            "# TASK-008 综合问答 199 题补录资产刷新报告",
            "",
            "## 结果",
            "",
            f"- 源文件：`{source_md.name}`",
            f"- 解析题目数：`{len(parsed_questions)}`",
            f"- 刷新题目资产：`199`",
            f"- 新增选项资产：`{total_option_count}`",
            f"- 最少选项数：`{min_option_count}`",
            f"- 最多选项数：`{max_option_count}`",
            f"- 多答案题目数：`{multi_answer_count}`",
            "- 主资产状态：`needs_manual_review -> parsed`",
            "- 数据库动作：`未执行`",
            "",
            "## 说明",
            "",
            "- 本次只刷新 `Q-CQA-0001` 至 `Q-CQA-0199` 对应的 TASK-008 CSV 资产。",
            "- 题目主资产继续复用既有字段：`question_code/category_code/question_type/stem/correct_answer/analysis/options_json/answer_json`。",
            "- 选项明细资产按既有字段生成：`batch_no/question_code/option_code/option_label/option_content/is_correct/sort_no`。",
            "- 不恢复、不创建、不依赖 staging 表；本次未执行任何数据库写入。",
        ]
    )
    REPORT_MD.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
