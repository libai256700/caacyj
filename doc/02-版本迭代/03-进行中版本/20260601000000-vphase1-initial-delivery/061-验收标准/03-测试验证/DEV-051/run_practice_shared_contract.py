#!/usr/bin/env python3
"""Run the local Story-050 contract and build checks without database access."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root not found")


def run(command: list[str], cwd: Path) -> dict[str, object]:
    print(f"[{cwd}] {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=cwd, text=True)
    return {"command": command, "cwd": str(cwd), "exitCode": completed.returncode}


def resolve_tool(*names: str) -> str:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError(f"required command not found: {', '.join(names)}")


def verify_sql_assets(repo_root: Path) -> dict[str, object]:
    sql_root = (
        repo_root
        / "doc"
        / "02-版本迭代"
        / "03-进行中版本"
        / "20260601000000-vphase1-initial-delivery"
        / "050-执行脚本"
    )
    migration = (sql_root / "20260610-yj-practice-data-migration.sql").read_text(encoding="utf-8")
    rollback_path = sql_root / "20260817113200-dml-rollback_yj_practice_data_migration.sql"
    rollback = rollback_path.read_text(encoding="utf-8") if rollback_path.exists() else ""
    normalized_migration = " ".join(migration.split())
    ddl = (sql_root / "20260817113000-ddl-normalize_practice_shared_indexes.sql").read_text(encoding="utf-8")
    script_index = (sql_root / "00-脚本索引.md").read_text(encoding="utf-8")
    backup_tables = [
        "bak_20260610_practice_category_ids",
        "bak_20260610_practice_exercises_ids",
        "bak_20260610_practice_answer_ids",
        "bak_20260610_practice_record_ids",
        "bak_20260610_practice_detail_ids",
    ]
    migration_bindings = [
        "FROM yk_question_category qc INNER JOIN bak_20260610_practice_category_ids migration_scope ON migration_scope.id = qc.id",
        "FROM yk_question q INNER JOIN bak_20260610_practice_exercises_ids migration_scope ON migration_scope.id = q.id",
        "FROM yk_question_option qo INNER JOIN bak_20260610_practice_answer_ids migration_scope ON migration_scope.id = qo.id",
        "FROM yk_practice_session ps INNER JOIN bak_20260610_practice_record_ids migration_scope ON migration_scope.id = ps.id",
        "FROM yk_practice_record pr INNER JOIN bak_20260610_practice_detail_ids migration_scope ON migration_scope.id = pr.id",
    ]
    rollback_bindings = [
        "JOIN `bak_20260610_practice_category_ids` backup ON backup.id = target.id",
        "JOIN `bak_20260610_practice_exercises_ids` backup ON backup.id = target.id",
        "JOIN `bak_20260610_practice_answer_ids` backup ON backup.id = target.id",
        "JOIN `bak_20260610_practice_record_ids` backup ON backup.id = target.id",
        "JOIN `bak_20260610_practice_detail_ids` backup ON backup.id = target.id",
    ]
    requirements = [
        rollback_path.exists(),
        all(name in migration and name in rollback for name in backup_tables),
        all(binding in normalized_migration for binding in migration_bindings),
        all(binding in rollback for binding in rollback_bindings),
        "20260817113200-dml-rollback_yj_practice_data_migration.sql" in script_index,
        "information_schema.COLUMNS" in ddl,
        "TENANT_ID_REMOVED" in ddl,
        "TENANT_ID_RETAINED_REQUIRES_INDEX_REVIEW" in ddl,
        "TENANT_ID_PRESENT_UNEXPECTED" in ddl,
    ]
    passed = all(requirements)
    print(f"SQL asset contract: {'PASS' if passed else 'FAIL'}", flush=True)
    return {
        "command": ["static-sql-asset-contract"],
        "cwd": str(sql_root),
        "exitCode": 0 if passed else 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repo_root = find_repo_root(Path(__file__).resolve())
    backend_root = repo_root / "code" / "develop" / "yunjikeji-admin-server"
    mvn = resolve_tool("mvn.cmd", "mvn")
    git = resolve_tool("git.exe", "git")
    checks = [
        verify_sql_assets(repo_root),
        run(
            [
                mvn,
                "-pl",
                "yunjikeji-admin-server",
                "-Dtest=PracticeSharedTenantContractTest,FrontPracticeServiceImplAssessmentHtmlTest",
                "test",
            ],
            backend_root,
        ),
        run(
            [mvn, "-pl", "yunjikeji-admin-server", "-am", "-DskipTests", "compile"],
            backend_root,
        ),
        run([git, "diff", "--check"], repo_root),
        run([git, "diff", "--quiet", "--", ":(glob)**/uni_modules/**"], repo_root),
        run([git, "diff", "--cached", "--quiet", "--", ":(glob)**/uni_modules/**"], repo_root),
    ]

    result = {
        "executedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "Story-050 local contract, compile, and protected-path checks",
        "databaseExecuted": False,
        "checks": checks,
        "passed": all(check["exitCode"] == 0 for check in checks),
    }
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"result: {output}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
