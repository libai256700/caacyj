#!/usr/bin/env python3
"""Static validation for the T0024 technical documentation deliverables."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


DELIVERABLES = {
    "technical": "02-任务产出/项目架构与功能实现技术文档.md",
    "research": "02-任务产出/源码调研记录.md",
}

REQUIRED_TERMS = {
    "technical": (
        "文档边界",
        "项目定位",
        "仓库与工程矩阵",
        "系统架构",
        "鉴权、租户与状态管理",
        "数据与状态边界",
        "核心功能的端到端实现",
        "配置分层与外部依赖",
        "构建、启动与测试环境部署",
        "测试资产与覆盖盲区",
        "扩展与维护指南",
        "源码确认的风险与技术债",
        "Evidence-supported Inference",
        "Unknowns And Limits",
        "yunjikeji",
        "yunjikeji-admin-ui",
        "yunjikeji-admin-server",
    ),
    "research": (
        "调研范围与方法",
        "工程矩阵",
        "后端与数据证据索引",
        "前端与功能证据索引",
        "运行、部署与测试证据索引",
        "本记录边界",
        "Fact",
        "Inference",
        "Unknown",
    ),
}

FORBIDDEN_TERMS = (
    "yunjikeji-server",
    "fly-llm",
)

FORBIDDEN_REFERENCE_PARTS = (
    "/yunjikeji-server/",
    "/fly-llm/",
    "/uni_modules/",
)

PLACEHOLDER_PATTERNS = (
    ("acceptance placeholder", re.compile(r"(?:TA|BA)-XXX-")),
    ("template replacement marker", re.compile(r"replace-me", re.IGNORECASE)),
    ("unfinished marker", re.compile(r"\[(?:完成后填写|待填写)\]|\b(?:TODO|TBD)\b", re.IGNORECASE)),
    ("template expression", re.compile(r"\{\{[^{}]+\}\}")),
)

SENSITIVE_PATTERNS = (
    ("private key material", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("OpenAI-style secret", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("JWT-like token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    (
        "literal credential assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|access[-_]?token|api[-_]?key|secret[-_]?key)\b\s*[:=]\s*[`\"']?(?!<|\*|\$\{|redacted|none|null)[A-Za-z0-9/+_.-]{8,}"
        ),
    ),
)

REFERENCE_RE = re.compile(
    r"`(?P<path>(?:code|tests|doc)/[^`\r\n:]+):(?P<line>[1-9][0-9]*)(?:-[1-9][0-9]*)?`"
)


@dataclass
class Report:
    passes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    citation_count: int = 0
    valid_citation_count: int = 0
    mermaid_count: int = 0

    def passed(self, message: str) -> None:
        self.passes.append(message)

    def failed(self, message: str) -> None:
        self.failures.append(message)

    def warned(self, message: str) -> None:
        self.warnings.append(message)


def count_lines_without_decoding(path: Path) -> int:
    count = 0
    saw_data = False
    last_byte = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            saw_data = True
            count += chunk.count(b"\n")
            last_byte = chunk[-1:]
    if saw_data and last_byte != b"\n":
        count += 1
    return count


def validate_mermaid(name: str, text: str, report: Report) -> None:
    in_fence = False
    current_kind = ""
    mermaid_open = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("```"):
            continue
        if not in_fence:
            in_fence = True
            current_kind = stripped[3:].strip().lower()
            if current_kind == "mermaid":
                mermaid_open += 1
        else:
            if stripped != "```":
                report.failed(f"{name}:{line_number} nested or malformed fenced block")
            in_fence = False
            current_kind = ""
    if in_fence:
        report.failed(f"{name}: unclosed fenced block ({current_kind or 'plain'})")
    else:
        report.passed(f"{name}: fenced blocks are balanced")
    report.mermaid_count += mermaid_open


def validate_document(
    name: str,
    path: Path,
    project_root: Path,
    report: Report,
) -> None:
    if not path.is_file():
        report.failed(f"{name}: deliverable is missing")
        return
    report.passed(f"{name}: deliverable exists")
    text = path.read_text(encoding="utf-8")

    missing_terms = [term for term in REQUIRED_TERMS[name] if term not in text]
    if missing_terms:
        report.failed(f"{name}: missing {len(missing_terms)} required sections or terms")
    else:
        report.passed(f"{name}: required sections and terms are present")

    forbidden_hits = [term for term in FORBIDDEN_TERMS if term.casefold() in text.casefold()]
    if forbidden_hits:
        report.failed(f"{name}: forbidden excluded-project terms detected ({', '.join(forbidden_hits)})")
    else:
        report.passed(f"{name}: excluded-project terms are absent")

    validate_mermaid(name, text, report)

    for label, pattern in PLACEHOLDER_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            line_numbers = sorted({text.count("\n", 0, match.start()) + 1 for match in matches})
            report.failed(f"{name}: {label} at lines {','.join(map(str, line_numbers))}")
    if not any(pattern.search(text) for _, pattern in PLACEHOLDER_PATTERNS):
        report.passed(f"{name}: no template placeholders detected")

    sensitive_locations: list[tuple[str, int]] = []
    for label, pattern in SENSITIVE_PATTERNS:
        for match in pattern.finditer(text):
            sensitive_locations.append((label, text.count("\n", 0, match.start()) + 1))
    if sensitive_locations:
        locations = ", ".join(f"{label}@{line}" for label, line in sensitive_locations)
        report.failed(f"{name}: sensitive-value pattern detected ({locations})")
    else:
        report.passed(f"{name}: no sensitive-value pattern detected")

    references = list(REFERENCE_RE.finditer(text))
    report.citation_count += len(references)
    if len(references) < 20:
        report.failed(f"{name}: only {len(references)} path:line citations found")
        return

    bad_references: list[str] = []
    line_counts: dict[Path, int] = {}
    for match in references:
        relative_path = match.group("path")
        line_number = int(match.group("line"))
        normalized_reference = f"/{relative_path.replace(chr(92), '/').casefold()}/"
        if any(part in normalized_reference for part in FORBIDDEN_REFERENCE_PARTS):
            bad_references.append(f"forbidden-scope:{relative_path}:{line_number}")
            continue
        target = (project_root / Path(relative_path)).resolve()
        try:
            target.relative_to(project_root)
        except ValueError:
            bad_references.append(f"outside-root:{relative_path}:{line_number}")
            continue
        if not target.is_file():
            bad_references.append(f"missing:{relative_path}:{line_number}")
            continue
        if target not in line_counts:
            line_counts[target] = count_lines_without_decoding(target)
        if line_number > line_counts[target]:
            bad_references.append(f"out-of-range:{relative_path}:{line_number}")
            continue
        report.valid_citation_count += 1

    if bad_references:
        report.failed(f"{name}: {len(bad_references)} invalid path:line citations")
        for reference in bad_references[:20]:
            report.failed(f"{name}: {reference}")
    else:
        report.passed(f"{name}: all {len(references)} path:line citations are valid")


def git_paths(project_root: Path, args: list[str]) -> list[str]:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=project_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError("git command failed without exposing command output")
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def validate_git(project_root: Path, task_dir: Path, report: Report) -> None:
    try:
        tracked_changes = set(git_paths(project_root, ["diff", "--name-only"]))
        tracked_changes.update(git_paths(project_root, ["diff", "--cached", "--name-only"]))
        status_lines = git_paths(project_root, ["status", "--short", "--untracked-files=all"])
    except (OSError, RuntimeError):
        report.failed("git: unable to inspect repository status")
        return

    status_paths: list[str] = []
    for line in status_lines:
        raw_path = line[3:] if len(line) >= 4 else line
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        status_paths.append(raw_path.strip('"'))

    changed_paths = sorted(tracked_changes.union(status_paths))
    uni_module_changes = [
        path for path in changed_paths if "/uni_modules/" in f"/{path.lower().strip('/')}" + "/"
    ]
    if uni_module_changes:
        report.failed(f"git: {len(uni_module_changes)} changed uni_modules paths detected")
    else:
        report.passed("git: no changed uni_modules paths detected")

    tracked_product_changes = [path for path in tracked_changes if path.startswith("code/")]
    if tracked_product_changes:
        report.failed(f"git: {len(tracked_product_changes)} tracked product-source changes detected")
    else:
        report.passed("git: no tracked product-source changes detected")

    task_relative = task_dir.relative_to(project_root).as_posix().rstrip("/") + "/"
    task_changes = [path for path in changed_paths if path.startswith(task_relative)]
    if task_changes:
        report.passed(f"git: {len(task_changes)} task-directory paths detected")
    else:
        report.failed("git: no task-directory changes detected")

    outside_changes = [path for path in changed_paths if not path.startswith(task_relative)]
    if outside_changes:
        report.warned(f"git: {len(outside_changes)} unrelated dirty paths exist outside T0024")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    parser.add_argument("task_dir", type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    task_dir = args.task_dir.resolve()
    report = Report()

    if not (project_root / ".git").exists():
        report.failed("project_root: .git is missing")
    if not task_dir.is_dir():
        report.failed("task_dir: directory is missing")
    else:
        try:
            task_dir.relative_to(project_root)
        except ValueError:
            report.failed("task_dir: outside project_root")

    if not report.failures:
        for name, relative_path in DELIVERABLES.items():
            validate_document(name, task_dir / relative_path, project_root, report)
        if report.mermaid_count < 1:
            report.failed("deliverables: no Mermaid diagram found")
        else:
            report.passed(f"deliverables: {report.mermaid_count} Mermaid diagrams found")
        validate_git(project_root, task_dir, report)

    output_lines = [f"[PASS] {message}" for message in report.passes]
    output_lines.extend(f"[WARN] {message}" for message in report.warnings)
    output_lines.extend(f"[FAIL] {message}" for message in report.failures)
    output_lines.append(
        "[SUMMARY] "
        f"passes={len(report.passes)} failures={len(report.failures)} warnings={len(report.warnings)} "
        f"citations={report.citation_count} valid_citations={report.valid_citation_count} "
        f"mermaid={report.mermaid_count}"
    )
    output = "\n".join(output_lines) + "\n"
    print(output, end="")
    Path(__file__).with_name("validation-result.txt").write_text(output, encoding="utf-8")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
