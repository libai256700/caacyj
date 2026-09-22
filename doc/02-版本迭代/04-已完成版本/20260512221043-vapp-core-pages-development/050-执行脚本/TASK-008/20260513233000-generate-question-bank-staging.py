import base64
import csv
import json
import re
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Dict, List, Tuple

import win32com.client


TASK_DIR = Path(
    r"D:\ProjPort\Work\feixingxueyuan\doc\02-版本迭代\03-进行中版本\20260512221043-vapp-core-pages-development\050-执行脚本\TASK-008"
)
RAW_DIR = Path(
    r"D:\ProjPort\Work\feixingxueyuan\doc\02-版本迭代\03-进行中版本\20260511100000-vinit-project-bootstrap\010-原始需求"
)
BASELINE_PATH = TASK_DIR / "20260513222000-question-bank-import-baseline-v2.json"

QUESTION_OUT = TASK_DIR / "20260513233500-question-import-staging-real.csv"
OPTION_OUT = TASK_DIR / "20260513233600-question-import-option-staging-real.csv"
REPORT_OUT = TASK_DIR / "20260513233700-question-bank-staging-generation-report.md"

BATCH_NO = "20260513-batch-real-001"


@dataclass
class CategoryConfig:
    category_code: str
    category_name: str
    expected_question_count: int
    default_parse_status: str
    allow_needs_manual_review: bool = False


DOCX_MAP = {
    "概述.docx": ("overview", "Q-OVERVIEW"),
    "系统组成及介绍.docx": ("system_components", "Q-SYSTEM"),
    "空中交通管制.docx": ("air_traffic_control", "Q-ATC"),
    "无人机飞行手册、法律法规及其他.docx": ("flight_manual_and_regulations", "Q-FMR"),
    "无人机操作注意事项.docx": ("operation_precautions", "Q-OP"),
    "气象.docx": ("meteorology", "Q-MET"),
    "旋翼无人机.docx": ("rotary_uav", "Q-ROTARY"),
    "无人机任务规划.docx": ("mission_planning", "Q-MISSION"),
    "飞行原理与飞行性能.docx": ("flight_principles_and_performance", "Q-FLIGHT"),
    "综合问答.docx": ("comprehensive_qa", "Q-CQA"),
}

DOC_MHT_MAP = {
    "无人机教员题库.doc": ("instructor_question_bank", "Q-INST"),
}

OPTION_RE = re.compile(r"^([A-D])\.(.*)$")
QUESTION_START_RE = re.compile(r"^(\d+)\.(.+)$")
ANSWER_RE = re.compile(r"^参考答案[:：]\s*(.+)$")
ANALYSIS_RE = re.compile(r"^解析[:：]?\s*(.*)$")


def load_baseline() -> Dict[str, CategoryConfig]:
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    result: Dict[str, CategoryConfig] = {}
    for item in data["categories"]:
        result[item["category_code"]] = CategoryConfig(
            category_code=item["category_code"],
            category_name=item["category_name"],
            expected_question_count=item["expected_question_count"],
            default_parse_status=item["default_parse_status"],
            allow_needs_manual_review=item.get("allow_needs_manual_review", False),
        )
    return result


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u3000", " ")
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def read_docx_text(path: Path) -> str:
    with path.open("rb") as f:
        header = f.read(8)
    if header.startswith(b"PK"):
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        text = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", text)
        return normalize_text(text)
    if header.startswith(b"\xD0\xCF\x11\xE0"):
        return read_ole_word_text(path)
    raise ValueError(f"Unsupported document format: {path.name}")


def read_ole_word_text(path: Path) -> str:
    app = None
    doc = None
    try:
        app = win32com.client.Dispatch("KWPS.Application")
        app.Visible = False
        doc = app.Documents.Open(str(path))
        text = doc.Content.Text
        return normalize_text(text)
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass


def read_mht_doc_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(
        r"Content-Transfer-Encoding:\s*base64[\s\S]*?Content-Location:\s*tmp\.html\s+(?P<b64>[A-Za-z0-9+/=\r\n]+)",
        raw,
    )
    if not match:
        raise ValueError(f"Cannot locate base64 html body in {path.name}")
    body = re.sub(r"\s+", "", match.group("b64"))
    html = base64.b64decode(body).decode("utf-8", errors="ignore")
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</div>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    return normalize_text(html)


def split_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_questions(lines: List[str]) -> List[Dict]:
    questions: List[Dict] = []
    current = None
    analysis_mode = False

    def flush_current():
        nonlocal current, analysis_mode
        if current:
            questions.append(current)
        current = None
        analysis_mode = False

    for line in lines:
        q_match = QUESTION_START_RE.match(line)
        if q_match:
            source_no = int(q_match.group(1))
            if current is not None and source_no != current["source_no"] + 1:
                pass
            else:
                flush_current()
                current = {
                    "source_no": source_no,
                    "stem": q_match.group(2).strip(),
                    "options": [],
                    "answer": "",
                    "analysis_lines": [],
                    "raw_lines": [line],
                }
                continue

        if current is None:
            continue

        current["raw_lines"].append(line)
        opt_match = OPTION_RE.match(line)
        if opt_match:
            current["options"].append((opt_match.group(1), opt_match.group(2).strip()))
            analysis_mode = False
            continue

        answer_match = ANSWER_RE.match(line)
        if answer_match:
            current["answer"] = answer_match.group(1).strip()
            analysis_mode = False
            continue

        analysis_match = ANALYSIS_RE.match(line)
        if analysis_match:
            analysis_mode = True
            first = analysis_match.group(1).strip()
            if first:
                current["analysis_lines"].append(first)
            continue

        if analysis_mode:
            current["analysis_lines"].append(line)
            continue

        if current["options"] and not current["answer"]:
            current["stem"] += " " + line
        elif current["answer"] and not analysis_mode:
            current["analysis_lines"].append(line)
        else:
            current["stem"] += " " + line

    flush_current()
    return questions


def canonical_answer(raw_answer: str) -> str:
    answer = raw_answer.strip().upper().replace(" ", "")
    answer = answer.replace("，", ",").replace("、", ",")
    letters = re.findall(r"[A-D]", answer)
    if not letters:
        return ""
    seen = []
    for item in letters:
        if item not in seen:
            seen.append(item)
    return ",".join(seen)


def infer_question_type(answer: str) -> str:
    if answer in {"对", "错", "正确", "错误", "T", "F", "Y", "N"}:
        return "judge"
    if "," in answer:
        return "multiple_choice"
    return "single_choice"


def question_code(prefix: str, number: int) -> str:
    return f"{prefix}-{number:04d}"


def parse_status_for(category: CategoryConfig, question: Dict) -> Tuple[str, str]:
    answer = canonical_answer(question["answer"])
    options = question["options"]
    if not options:
        return "needs_manual_review", "no stable options parsed from source"
    if not answer:
        return "needs_manual_review", "no stable answer parsed from source"
    option_codes = {code for code, _ in options}
    for piece in answer.split(","):
        if piece not in option_codes:
            return "needs_manual_review", "answer does not map to parsed options"
    if category.default_parse_status == "needs_manual_review":
        return "needs_manual_review", f"category baseline defaults to {category.default_parse_status}"
    return "parsed", ""


def build_rows() -> Tuple[List[Dict], List[Dict], Dict]:
    baseline = load_baseline()
    question_rows: List[Dict] = []
    option_rows: List[Dict] = []
    stats = {
        "categories": {},
        "parse_status": {},
        "option_rows": 0,
    }

    for file_name, (category_code, code_prefix) in DOCX_MAP.items():
        path = RAW_DIR / file_name
        text = read_docx_text(path)
        lines = split_lines(text)
        parsed_questions = parse_questions(lines)
        category = baseline[category_code]
        stats["categories"].setdefault(category_code, {"expected": category.expected_question_count, "actual": 0, "parsed": 0, "needs_manual_review": 0})

        for item in parsed_questions:
            q_code = question_code(code_prefix, item["source_no"])
            answer = canonical_answer(item["answer"])
            q_type = infer_question_type(answer)
            status, review_reason = parse_status_for(category, item)
            analysis = normalize_text("\n".join(item["analysis_lines"]))
            options_payload = [
                {"optionCode": code, "optionContent": content}
                for code, content in item["options"]
            ]
            answer_payload = {"correctAnswer": answer} if answer else None
            raw_payload = {
                "sourceLines": item["raw_lines"],
                "sourceFile": file_name,
            }
            question_rows.append(
                {
                    "batch_no": BATCH_NO,
                    "source_file": f"raw-bank/{file_name}",
                    "source_locator": f"第{item['source_no']}题",
                    "category_code": category_code,
                    "question_code": q_code,
                    "question_type": q_type,
                    "stem": item["stem"].strip(),
                    "correct_answer": answer,
                    "analysis": analysis,
                    "score": "1",
                    "sort_no": str(item["source_no"]),
                    "source_ref": f"raw-bank/{file_name}#第{item['source_no']}题",
                    "parse_status": status,
                    "review_reason": review_reason,
                    "options_payload_json": json.dumps(options_payload, ensure_ascii=False) if options_payload else "",
                    "answer_payload_json": json.dumps(answer_payload, ensure_ascii=False) if answer_payload else "",
                    "raw_payload_json": json.dumps(raw_payload, ensure_ascii=False),
                }
            )
            stats["categories"][category_code]["actual"] += 1
            stats["categories"][category_code][status] = stats["categories"][category_code].get(status, 0) + 1
            stats["parse_status"][status] = stats["parse_status"].get(status, 0) + 1

            if status == "parsed":
                answers = set(answer.split(","))
                for index, (option_code, option_content) in enumerate(item["options"], start=1):
                    option_rows.append(
                        {
                            "batch_no": BATCH_NO,
                            "question_code": q_code,
                            "option_code": option_code,
                            "option_label": option_code,
                            "option_content": option_content,
                            "is_correct": "1" if option_code in answers else "0",
                            "sort_no": str(index * 10),
                        }
                    )

    for file_name, (category_code, code_prefix) in DOC_MHT_MAP.items():
        path = RAW_DIR / file_name
        text = read_mht_doc_text(path)
        lines = split_lines(text)
        parsed_questions = parse_questions(lines)
        category = baseline[category_code]
        stats["categories"].setdefault(category_code, {"expected": category.expected_question_count, "actual": 0, "parsed": 0, "needs_manual_review": 0})

        for item in parsed_questions:
            q_code = question_code(code_prefix, item["source_no"])
            answer = canonical_answer(item["answer"])
            q_type = infer_question_type(answer)
            status, review_reason = parse_status_for(category, item)
            if status == "parsed":
                status = "needs_manual_review"
                review_reason = "category baseline defaults to needs_manual_review"
            analysis = normalize_text("\n".join(item["analysis_lines"]))
            options_payload = [
                {"optionCode": code, "optionContent": content}
                for code, content in item["options"]
            ]
            answer_payload = {"correctAnswer": answer} if answer else None
            raw_payload = {
                "sourceLines": item["raw_lines"],
                "sourceFile": file_name,
                "sourceFormat": "mht-exported-doc",
            }
            question_rows.append(
                {
                    "batch_no": BATCH_NO,
                    "source_file": f"raw-bank/{file_name}",
                    "source_locator": f"第{item['source_no']}题",
                    "category_code": category_code,
                    "question_code": q_code,
                    "question_type": q_type,
                    "stem": item["stem"].strip(),
                    "correct_answer": answer,
                    "analysis": analysis,
                    "score": "1",
                    "sort_no": str(item["source_no"]),
                    "source_ref": f"raw-bank/{file_name}#第{item['source_no']}题",
                    "parse_status": status,
                    "review_reason": review_reason,
                    "options_payload_json": json.dumps(options_payload, ensure_ascii=False) if options_payload else "",
                    "answer_payload_json": json.dumps(answer_payload, ensure_ascii=False) if answer_payload else "",
                    "raw_payload_json": json.dumps(raw_payload, ensure_ascii=False),
                }
            )
            stats["categories"][category_code]["actual"] += 1
            stats["categories"][category_code][status] = stats["categories"][category_code].get(status, 0) + 1
            stats["parse_status"][status] = stats["parse_status"].get(status, 0) + 1

    stats["option_rows"] = len(option_rows)
    stats["question_rows"] = len(question_rows)
    return question_rows, option_rows, stats


def write_csv(path: Path, rows: List[Dict], headers: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_report(stats: Dict) -> None:
    expected_total = sum(item["expected"] for item in stats["categories"].values())
    actual_total = sum(item["actual"] for item in stats["categories"].values())
    manual_count = stats["parse_status"].get("needs_manual_review", 0)
    parsed_count = stats["parse_status"].get("parsed", 0)
    ignored_count = stats["parse_status"].get("ignored_noise", 0)
    manual_ratio = (manual_count / actual_total * 100) if actual_total else 0
    lines = [
        "# TASK-008 真实 staging 题库载荷生成说明",
        "",
        "## 生成方法",
        "",
        "- `docx` 文件：直接读取 `word/document.xml`，按题号、选项、参考答案、解析做规则化抽取。",
        "- `无人机教员题库.doc`：该文件实际是 `mht` 导出内容，先解 base64 HTML，再按同一规则抽取。",
        "- 输出严格对齐 `yk_question_import_staging` / `yk_question_import_option_staging` 的当前字段契约。",
        "- `综合问答` 与 `无人机教员题库` 按 baseline 默认落 `needs_manual_review`，不伪造成可直接导入的 `parsed`。",
        "",
        "## 统计结果",
        "",
        f"- baseline 目标题数：{expected_total}",
        f"- 实际生成 question staging 行数：{actual_total}",
        f"- 实际生成 option staging 行数：{stats['option_rows']}",
        f"- parsed：{parsed_count}",
        f"- needs_manual_review：{manual_count}",
        f"- ignored_noise：{ignored_count}",
        f"- manual review 比例：{manual_ratio:.2f}%",
        "",
        "## 分类统计",
        "",
        "| category_code | expected | actual | parsed | needs_manual_review | gap |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category_code, item in stats["categories"].items():
        lines.append(
            f"| {category_code} | {item['expected']} | {item['actual']} | {item.get('parsed', 0)} | {item.get('needs_manual_review', 0)} | {item['actual'] - item['expected']} |"
        )

    lines.extend(
        [
            "",
            "## 已知难点",
            "",
            "- baseline 1512 题与当前原始文档实际抽取题数存在明显缺口；当前载荷忠实反映原始材料，不补造缺失题。",
            "- `题库比例.xls` 未参与本轮解析，仅作为 baseline 对照线索；本机缺少旧版 `xls` 解析依赖。",
            "- `无人机教员题库.doc` 不是传统二进制 Word，而是 `mht` 导出体；已按真实内容解析，但整类仍保持 `needs_manual_review`。",
            "",
            "## 结论",
            "",
            "- 当前结果已经补齐 11 个正式分类的真实 staging 入口。",
            "- 当前结果可以支撑下一步测试库做真实 from-staging 导入链路验证，但不能宣称已经满足 baseline 1512 题全量导入。",
            "- 如果后续必须达到 1512 全量，需要补齐缺失来源或确认 `题库比例.xls` 是否只是配额口径而非完整题面来源。",
        ]
    )
    REPORT_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    question_rows, option_rows, stats = build_rows()
    write_csv(
        QUESTION_OUT,
        question_rows,
        [
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
        ],
    )
    write_csv(
        OPTION_OUT,
        option_rows,
        [
            "batch_no",
            "question_code",
            "option_code",
            "option_label",
            "option_content",
            "is_correct",
            "sort_no",
        ],
    )
    write_report(stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
