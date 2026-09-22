#!/usr/bin/env python3
"""AST contracts for the two manual Story-052 initialization programs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Iterable


SKIP_DIRS = {
    ".git", ".hbuilderx", ".idea", ".codex-stage-minimal", "doc", "node_modules",
    "target", "temp", "tmp", "uni_modules", "dist", "unpackage", "coverage",
}
BUSINESS_EXTENSIONS = {
    ".java", ".kt", ".xml", ".yaml", ".yml", ".properties", ".ts", ".tsx",
    ".js", ".mjs", ".cjs", ".vue", ".json", ".sql", ".py", ".sh", ".ps1",
    ".bat", ".cmd", ".gradle",
}


@dataclass(frozen=True)
class ToolSource:
    path: Path
    source: str
    tree: ast.Module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def walk_files(root: Path, suffix: str | None = None) -> Iterable[Path]:
    for child in root.iterdir():
        if child.is_dir():
            if child.name not in SKIP_DIRS:
                yield from walk_files(child, suffix)
        elif suffix is None or child.suffix.lower() == suffix:
            yield child


def load_python_tools(repo_root: Path) -> list[ToolSource]:
    tools: list[ToolSource] = []
    for file in walk_files(repo_root, ".py"):
        source = file.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source, filename=str(file))
        except SyntaxError:
            continue
        tools.append(ToolSource(file, source, tree))
    return tools


APP_CONFIG_RELATIVE = Path(
    "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/"
    "src/main/resources/application-local.yaml"
)


def tool_from_source(name: str, source: str) -> ToolSource:
    return ToolSource(Path(name), source, ast.parse(source, filename=name))


def string_literals(tool: ToolSource) -> list[str]:
    return [node.value for node in ast.walk(tool.tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def literal_value(node: ast.AST | None) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def assigned_constants(tool: ToolSource) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in tool.tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            result[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            result[node.target.id] = node.value
    return result


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def calls(tool: ToolSource) -> list[ast.Call]:
    return sorted(
        (node for node in ast.walk(tool.tree) if isinstance(node, ast.Call)),
        key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
    )


def call_names(tool: ToolSource) -> list[str]:
    return [dotted_name(call.func) for call in calls(tool)]


def function_defs(tool: ToolSource) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {node.name: node for node in tool.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def is_entry_program(tool: ToolSource) -> bool:
    for node in tool.tree.body:
        if not isinstance(node, ast.If):
            continue
        test = ast.dump(node.test, include_attributes=False)
        body = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
        if "__name__" in test and "__main__" in test and "main" in body:
            return True
    return False


def argument_contract(tool: ToolSource) -> dict[str, ast.Call]:
    result: dict[str, ast.Call] = {}
    for call in calls(tool):
        if not dotted_name(call.func).endswith("add_argument"):
            continue
        for argument in call.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value.startswith("--"):
                result[argument.value] = call
    return result


def has_store_true(call: ast.Call) -> bool:
    return any(keyword.arg == "action" and isinstance(keyword.value, ast.Constant)
               and keyword.value.value == "store_true" for keyword in call.keywords)


def names_and_attributes(tool: ToolSource) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(tool.tree):
        if isinstance(node, ast.Name):
            values.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            values.add(node.attr.lower())
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            values.add(node.name.lower())
    return values


def parse_jdbc_target(value: str) -> tuple[str, int, str] | None:
    match = re.match(r"jdbc:mysql://([^/:?#]+):(\d+)/([^?\s#]+)", value.strip())
    if not match:
        return None
    return match.group(1), int(match.group(2)), match.group(3)


def current_application_target(repo_root: Path) -> tuple[Path, tuple[str, int, str]]:
    config = repo_root / APP_CONFIG_RELATIVE
    require(config.is_file(), f"current application local config missing: {APP_CONFIG_RELATIVE}")
    targets: set[tuple[str, int, str]] = set()
    for raw_line in config.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line.startswith("#") or "jdbc:mysql://" not in line:
            continue
        jdbc = line[line.index("jdbc:mysql://"):].split()[0]
        parsed = parse_jdbc_target(jdbc)
        if parsed:
            targets.add(parsed)
    require(len(targets) == 1, "application-local.yaml must expose one host/port/database target")
    return config, next(iter(targets))


def assignment_name_for_call(owner: ast.AST, target_call: ast.Call) -> str | None:
    for node in ast.walk(owner):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is not target_call:
                continue
            target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else node.target
            if isinstance(target, ast.Name):
                return target.id
    return None


def call_uses_name(call: ast.Call, name: str) -> bool:
    return any(isinstance(node, ast.Name) and node.id == name
               for argument in [*call.args, *(keyword.value for keyword in call.keywords)]
               for node in ast.walk(argument))


def calls_in(nodes: list[ast.stmt] | ast.AST) -> list[ast.Call]:
    root = ast.Module(body=nodes, type_ignores=[]) if isinstance(nodes, list) else nodes
    return sorted((node for node in ast.walk(root) if isinstance(node, ast.Call)),
                  key=lambda node: (node.lineno, node.col_offset))


def expanded_calls_in(nodes: list[ast.stmt] | ast.AST,
                      functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
                      seen: frozenset[str] = frozenset()) -> list[ast.Call]:
    result: list[ast.Call] = []
    for call in calls_in(nodes):
        result.append(call)
        leaf = dotted_name(call.func).split(".")[-1]
        if leaf in functions and leaf not in seen:
            result.extend(expanded_calls_in(functions[leaf], functions, seen | {leaf}))
    return result


def call_kind(call: ast.Call) -> str | None:
    name = dotted_name(call.func).lower()
    leaf = name.split(".")[-1]
    if leaf in {"load_application_database_target", "parse_application_local_config"}:
        return "config"
    if leaf in {"assert_same_application_database", "validate_same_database"}:
        return "same_db"
    if "connect" in leaf and "disconnect" not in leaf:
        return "connect"
    if any(token in leaf for token in ("abort_if_exists", "ensure_id_available", "check_id_conflict",
                                        "validate_target", "preflight", "ensure_empty", "check_conflict")):
        return "precheck"
    if "backup" in leaf:
        return "backup"
    if leaf in {"begin", "start_transaction"}:
        return "begin"
    if leaf in {"autocommit", "set_autocommit"} and any(literal_value(arg) is False for arg in call.args):
        return "begin"
    if any(token in leaf for token in ("insert", "write_rows", "apply_rows", "import_rows")):
        return "write"
    if "readback" in leaf or "read_back" in leaf or "verify_after_write" in leaf:
        return "readback"
    if leaf == "commit":
        return "commit"
    if leaf == "rollback":
        return "rollback"
    return None


def find_apply_contract(tool: ToolSource, kind: str) -> tuple[ast.AST, list[ast.stmt], list[ast.stmt]]:
    owners: list[ast.AST] = [*function_defs(tool).values()]
    for owner in owners:
        statements = owner.body
        for index, node in enumerate(statements):
            if not isinstance(node, ast.If) or "apply" not in ast.dump(node.test, include_attributes=False).lower():
                continue
            negated = isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not)
            if negated:
                require(any(isinstance(item, (ast.Return, ast.Raise)) for item in node.body),
                        f"{kind} dry-run guard must terminate before writes")
                return owner, node.body, [*node.orelse, *statements[index + 1:]]
            return owner, node.orelse, node.body
    raise AssertionError(f"{kind} tool must expose an analyzable --apply control-flow guard")


def assert_connection_contract(tool: ToolSource, repo_root: Path, kind: str,
                               owner: ast.AST, apply_nodes: list[ast.stmt]) -> None:
    config_path, expected_target = current_application_target(repo_root)
    args = argument_contract(tool)
    require("--app-config" in args, f"{kind} tool must require --app-config")
    require(not ({"--host", "--port", "--database"} & args.keys()),
            f"{kind} tool must reject arbitrary host/port/database CLI targets")
    config_arg = args["--app-config"]
    defaults = [keyword.value for keyword in config_arg.keywords if keyword.arg == "default"]
    require(defaults and "application-local.yaml" in ast.unparse(defaults[0]),
            f"{kind} --app-config must default to current application-local.yaml")

    for value in string_literals(tool):
        if value.startswith("jdbc:mysql://") and "(?P<" not in value:
            require(parse_jdbc_target(value) == expected_target,
                    f"{kind} tool contains a JDBC target different from current application local database")

    ordered = calls_in(owner)
    config_calls = [call for call in ordered if call_kind(call) == "config"]
    same_calls = [call for call in ordered if call_kind(call) == "same_db"]
    connect_calls = [call for call in calls_in(apply_nodes) if call_kind(call) == "connect"]
    require(len(config_calls) >= 2 and same_calls and connect_calls,
            f"{kind} apply path must parse application config, compare same database, then connect")
    supplied_calls = [call for call in config_calls if "app_config" in ast.dump(call, include_attributes=False)]
    canonical_calls = [call for call in config_calls if any(
        isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value.replace("\\", "/").endswith(APP_CONFIG_RELATIVE.as_posix())
        for node in ast.walk(call)
    )]
    require(len(supplied_calls) == 1 and len(canonical_calls) == 1
            and supplied_calls[0] is not canonical_calls[0],
            f"{kind} must separately parse supplied config and canonical application-local.yaml")
    target_name = assignment_name_for_call(owner, supplied_calls[0])
    canonical_name = assignment_name_for_call(owner, canonical_calls[0])
    require(target_name is not None, f"{kind} parsed application database target must be assigned")
    require(canonical_name is not None, f"{kind} canonical application database target must be assigned")
    require(call_uses_name(same_calls[0], target_name) and call_uses_name(same_calls[0], canonical_name),
            f"{kind} same-database assertion must compare supplied and canonical parsed targets")
    require(call_uses_name(connect_calls[0], target_name),
            f"{kind} connection must consume parsed application target")
    require(max(supplied_calls[0].lineno, canonical_calls[0].lineno) < same_calls[0].lineno < connect_calls[0].lineno,
            f"{kind} database parse/compare/connect order changed")

    loaders = [function for function in function_defs(tool).values()
               if function.name in {"load_application_database_target", "parse_application_local_config"}]
    require(len(loaders) == 1, f"{kind} must define one application-local JDBC parser")
    loader_dump = ast.dump(loaders[0], include_attributes=False).lower()
    loader_strings = "\n".join(node.value for node in ast.walk(loaders[0])
                               if isinstance(node, ast.Constant) and isinstance(node.value, str)).lower()
    require("app_config" in loader_dump and ("read_text" in loader_dump or "open" in loader_dump),
            f"{kind} JDBC parser must read the supplied app_config")
    require("jdbc:mysql" in loader_strings
            and all(field in loader_dump for field in ("host", "port", "database"))
            and any(isinstance(node, ast.Raise) for node in ast.walk(loaders[0])),
            f"{kind} JDBC parser must extract host/port/database and reject invalid config")

    same_functions = [function for function in function_defs(tool).values()
                      if function.name in {"assert_same_application_database", "validate_same_database"}]
    require(len(same_functions) == 1, f"{kind} must define one same-database validator")
    same_dump = ast.dump(same_functions[0], include_attributes=False).lower()
    require(all(field in same_dump for field in ("host", "port", "database"))
            and any(isinstance(node, ast.Raise) for node in ast.walk(same_functions[0])),
            f"{kind} same-database validator must compare host/port/database and reject mismatch")
    require(config_path.name in tool.source, f"{kind} must visibly reuse {config_path.name}")


def assert_apply_control_flow(tool: ToolSource, repo_root: Path, kind: str,
                              conflict_name: str | None = None) -> None:
    owner, dry_nodes, apply_nodes = find_apply_contract(tool, kind)
    functions = function_defs(tool)
    dry_calls = expanded_calls_in(dry_nodes, functions)
    require(not any(call_kind(call) in {"connect", "begin", "write", "commit"} for call in dry_calls),
            f"{kind} dry-run path must execute zero connection/DML/transaction calls")
    dml_names = {name for name, value in assigned_constants(tool).items()
                 if isinstance(value, ast.Constant) and isinstance(value.value, str)
                 and re.match(r"\s*(?:INSERT|UPDATE|DELETE|REPLACE)\b", value.value, re.IGNORECASE)}
    require(not any(dotted_name(call.func).split(".")[-1].lower() in {"execute", "executemany"}
                    and any(isinstance(node, ast.Name) and node.id in dml_names
                            for argument in call.args for node in ast.walk(argument))
                    for call in dry_calls),
            f"{kind} dry-run path must not execute a DML SQL constant")
    dry_text = "\n".join(ast.unparse(node) for node in dry_nodes).upper()
    require(not re.search(r"\b(?:INSERT|UPDATE|DELETE|REPLACE)\b", dry_text),
            f"{kind} dry-run path must contain zero DML")

    assert_connection_contract(tool, repo_root, kind, owner, apply_nodes)
    apply_calls = expanded_calls_in(apply_nodes, functions)
    kinds = [(call_kind(call), call) for call in apply_calls if call_kind(call)]
    required = ["connect", "precheck", "backup", "begin", "write", "readback", "commit"]
    cursor = -1
    selected: dict[str, ast.Call] = {}
    for step in required:
        found = next(((index, call) for index, (actual, call) in enumerate(kinds)
                      if index > cursor and actual == step), None)
        require(found is not None,
                f"{kind} apply path missing ordered step {step}; actual={[name for name, _ in kinds]}")
        cursor, selected[step] = found

    tries = [node for root in apply_nodes for node in ast.walk(root) if isinstance(node, ast.Try)]
    require(tries, f"{kind} transactional writes must be inside try/except")
    transactional = next((node for node in tries if selected["write"] in list(ast.walk(node))), None)
    require(transactional is not None, f"{kind} write must be inside transaction try")
    require(all(any(call_kind(call) == "rollback" for call in expanded_calls_in(handler, functions))
                for handler in transactional.handlers),
            f"{kind} every write exception path must rollback")
    require(all(any(isinstance(node, ast.Raise) for node in ast.walk(handler))
                for handler in transactional.handlers),
            f"{kind} every rollback handler must re-raise the failure")
    require(selected["readback"] in list(ast.walk(transactional))
            and selected["commit"] in list(ast.walk(transactional)),
            f"{kind} readback and commit must remain inside transaction try")

    if conflict_name:
        conflict_calls = [call for call in apply_calls if dotted_name(call.func).split(".")[-1] == conflict_name]
        require(len(conflict_calls) == 1, f"{kind} apply path must call {conflict_name} exactly once")
        require(conflict_calls[0].lineno < selected["backup"].lineno < selected["write"].lineno,
                f"{kind} id=3 conflict check must abort before backup and every write")
        conflict = function_defs(tool).get(conflict_name)
        require(conflict is not None, f"{kind} must define {conflict_name}")
        conflict_text = "\n".join(string_literals(ToolSource(tool.path, tool.source,
            ast.Module(body=conflict.body, type_ignores=[])))).upper()
        require("SELECT" in conflict_text and any(literal_value(node) == 3 for node in ast.walk(conflict)),
                f"{kind} id=3 conflict check must query fixed id 3")
        require(any(isinstance(node, ast.Raise) for node in ast.walk(conflict)),
                f"{kind} existing id=3 must raise before writes")
        require(not re.search(r"\b(?:INSERT|UPDATE|DELETE|REPLACE)\b", conflict_text),
                f"{kind} id=3 conflict check must contain zero DML")


def assert_common_contract(tool: ToolSource, repo_root: Path, kind: str,
                           conflict_name: str | None = None) -> None:
    require(is_entry_program(tool), f"{kind} tool must be an independent executable Python entry")
    args = argument_contract(tool)
    require("--apply" in args and has_store_true(args["--apply"]),
            f"{kind} tool must default to dry-run and require explicit --apply")
    require("--source-dir" in args or "--source-file" in args,
            f"{kind} tool source location must be explicitly supplied")
    source_lower = tool.source.lower()
    require(re.search(r"(?:password|passwd)\s*=\s*['\"][^'\"]+['\"]", source_lower) is None,
            f"{kind} tool must not embed a database password")
    assert_apply_control_flow(tool, repo_root, kind, conflict_name)


def find_question_tools(tools: list[ToolSource]) -> list[ToolSource]:
    return [tool for tool in tools if "yj_practice_exercises" in tool.source
            and "yj_practice_exercises_answer" in tool.source
            and "career-planning-coach" in tool.source]


def find_agent_tools(tools: list[ToolSource]) -> list[ToolSource]:
    return [tool for tool in tools if "yj_agent_info" in tool.source and "SELF_SYSTEM_PROMPT" in tool.source]


def assert_question_constants(tool: ToolSource) -> None:
    constants = assigned_constants(tool)
    require(literal_value(constants.get("CATEGORY_ID")) == 14,
            "question tool must fix CATEGORY_ID=14")
    require(literal_value(constants.get("EXPECTED_QUESTION_COUNT")) == 47,
            "question tool must fix EXPECTED_QUESTION_COUNT=47")
    require(literal_value(constants.get("EXPECTED_ANSWER_COUNT")) == 111,
            "question tool must fix EXPECTED_ANSWER_COUNT=111")
    comparisons = [node for node in ast.walk(tool.tree) if isinstance(node, ast.Compare)]
    for name in ("CATEGORY_ID", "EXPECTED_QUESTION_COUNT", "EXPECTED_ANSWER_COUNT"):
        require(any(any(isinstance(child, ast.Name) and child.id == name for child in ast.walk(node))
                    for node in comparisons),
                f"question tool must enforce {name} in a validation comparison")


def question_contract(repo_root: Path) -> ToolSource:
    candidates = find_question_tools(load_python_tools(repo_root))
    require(len(candidates) == 1,
            f"exactly one independent career question import Python entry is required; actual={len(candidates)}")
    tool = candidates[0]
    assert_common_contract(tool, repo_root, "question import")
    strings = "\n".join(string_literals(tool))
    identifiers = names_and_attributes(tool)
    assert_question_constants(tool)
    require("career-planning-coach" in strings, "question tool must read career-planning-coach source")
    require("INSERT" in strings.upper() and "SELECT" in strings.upper(),
            "question tool must define insert and readback SQL")
    require("yj_practice_exercises" in strings and "yj_practice_exercises_answer" in strings,
            "question tool SQL must target both required tables")
    require(any(token in identifiers for token in {"conflict", "check_conflict", "ensure_empty", "validate_target"}),
            "question tool must stop on partial/conflicting target data")
    print(f"PASS question tool AST contract: {tool.path.relative_to(repo_root)}")
    return tool


def assert_agent_row_contract(tool: ToolSource) -> None:
    strings = "\n".join(string_literals(tool))
    constants = assigned_constants(tool)
    require(literal_value(constants.get("AGENT_ID")) == 3, "Agent tool must fix AGENT_ID=3")
    require(literal_value(constants.get("TENANT_ID")) == 1, "Agent tool must fix TENANT_ID=1")
    required_fields = {
        "id", "name", "status", "tenant_id", "agent_id", "knowledge_base_id",
        "reply_strategy", "prompt_config",
    }
    row_candidates: list[dict[str, ast.AST]] = []
    for node in ast.walk(tool.tree):
        if not isinstance(node, ast.Dict):
            continue
        row = {key.value: value for key, value in zip(node.keys, node.values)
               if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        if required_fields.issubset(row):
            row_candidates.append(row)
    require(len(row_candidates) == 1, "Agent tool must define one complete yj_agent_info row")
    row = row_candidates[0]
    require(literal_value(row["id"]) == 3, "Agent row id must equal 3")
    require(literal_value(row["name"]) == "职业规划评测", "Agent row name must equal 职业规划评测")
    require(literal_value(row["status"]) == 1, "Agent row status must equal 1")
    require(literal_value(row["tenant_id"]) == 1, "Agent row tenant_id must equal 1")
    for field in ("agent_id", "knowledge_base_id", "reply_strategy"):
        require(isinstance(row[field], ast.Constant) and row[field].value is None,
                f"Agent row {field} must be NULL")
    require(isinstance(row["prompt_config"], ast.Name) and row["prompt_config"].id == "SELF_SYSTEM_PROMPT",
            "Agent row prompt_config must use exact SELF_SYSTEM_PROMPT")
    prompt_value = constants.get("SELF_SYSTEM_PROMPT")
    require(isinstance(prompt_value, ast.Call)
            and "extract" in dotted_name(prompt_value.func).lower()
            and any(isinstance(node, ast.Constant) and node.value == "career-core.mjs"
                    for node in ast.walk(prompt_value)),
            "SELF_SYSTEM_PROMPT must be extracted from career-core.mjs")
    write_calls = [call for call in calls(tool) if call_kind(call) == "write"]
    require(any(call_uses_name(call, "AGENT_ROW") for call in write_calls),
            "Agent INSERT path must consume the exact AGENT_ROW")
    insert_strings = [value.upper() for value in string_literals(tool)
                      if re.search(r"INSERT\s+INTO\s+`?YJ_AGENT_INFO`?", value, re.IGNORECASE)]
    readback_strings = [value.upper() for value in string_literals(tool)
                        if re.search(r"SELECT\b.*\bFROM\s+`?YJ_AGENT_INFO`?", value,
                                     re.IGNORECASE | re.DOTALL)]
    require(insert_strings and readback_strings, "Agent tool must define INSERT and readback SELECT SQL")
    require(all(field.upper() in insert_strings[0] for field in required_fields),
            "Agent INSERT SQL must cover every fixed field")
    require(all(field.upper() in readback_strings[0] for field in required_fields),
            "Agent transaction readback SQL must cover every fixed field")


def agent_contract(repo_root: Path) -> ToolSource:
    candidates = find_agent_tools(load_python_tools(repo_root))
    require(len(candidates) == 1,
            f"exactly one independent career Agent initialization Python entry is required; actual={len(candidates)}")
    tool = candidates[0]
    assert_common_contract(tool, repo_root, "Agent initialization", "abort_if_exists")
    strings = "\n".join(string_literals(tool))
    identifiers = names_and_attributes(tool)
    args = argument_contract(tool)
    require("--id" not in args, "Agent tool must not allow id=3 to be replaced from CLI")
    require("career-core.mjs" in strings and "SELF_SYSTEM_PROMPT" in strings,
            "Agent tool must extract SELF_SYSTEM_PROMPT from career-core.mjs")
    require(any(name.endswith("sha256") for name in call_names(tool)),
            "Agent tool must calculate the exact prompt SHA-256")
    require("INSERT" in strings.upper() and "YJ_AGENT_INFO" in strings.upper(),
            "Agent tool must insert yj_agent_info")
    require(re.search(r"UPDATE\s+(?:`?\w+`?\.)?`?yj_agent_info`?", strings, re.IGNORECASE) is None,
            "Agent tool must never update an existing id=3")
    require(any(token in identifiers for token in {"abort_if_exists", "ensure_id_available", "check_id_conflict"}),
            "Agent tool must have a named id=3 conflict-abort check")
    require(not any(isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                    and "id" in ast.dump(node, include_attributes=False).lower() for node in ast.walk(tool.tree)),
            "Agent tool must not calculate or auto-increment a replacement id")
    assert_agent_row_contract(tool)
    print(f"PASS Agent tool AST contract: {tool.path.relative_to(repo_root)}")
    return tool


def isolation_contract(repo_root: Path) -> None:
    question = question_contract(repo_root)
    agent = agent_contract(repo_root)
    require(question.path != agent.path, "question and Agent tools must be separate entry files")
    require(question.path.parent != agent.path.parent or question.path.stem != agent.path.stem,
            "question and Agent tools must not share one command entry")

    forbidden_tokens = {
        question.path.name,
        question.path.stem,
        agent.path.name,
        agent.path.stem,
        str(question.path.relative_to(repo_root)).replace("\\", "/"),
        str(agent.path.relative_to(repo_root)).replace("\\", "/"),
    }
    findings: list[str] = []
    for file in walk_files(repo_root):
        if file in {question.path, agent.path} or file.suffix.lower() not in BUSINESS_EXTENSIONS:
            continue
        relative_parts = file.relative_to(repo_root).parts
        if "src" in relative_parts and "test" in relative_parts:
            continue
        if relative_parts and relative_parts[0] == "tests":
            continue
        try:
            content = file.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        normalized = content.replace("\\", "/")
        for token in forbidden_tokens:
            if token in normalized:
                findings.append(f"{file.relative_to(repo_root)} -> {token}")
    require(not findings,
            "manual tools must have zero application/startup/config/build/migration/resource references: "
            + "; ".join(findings[:10]))
    print("PASS manual tool whole-repository isolation scan")


def mutation_contract(repo_root: Path) -> None:
    good_source = '''
import argparse

CATEGORY_ID = 14
EXPECTED_QUESTION_COUNT = 47
EXPECTED_ANSWER_COUNT = 111
AGENT_ID = 3
TENANT_ID = 1
SELF_SYSTEM_PROMPT = extract_self_system_prompt("career-core.mjs")
AGENT_ROW = {
    "id": 3,
    "name": "职业规划评测",
    "status": 1,
    "tenant_id": 1,
    "agent_id": None,
    "knowledge_base_id": None,
    "reply_strategy": None,
    "prompt_config": SELF_SYSTEM_PROMPT,
}
QUESTION_SQL = "INSERT INTO yj_practice_exercises VALUES (%s)"
ANSWER_SQL = "INSERT INTO yj_practice_exercises_answer VALUES (%s)"
AGENT_SQL = "INSERT INTO yj_agent_info (id,name,status,tenant_id,agent_id,knowledge_base_id,reply_strategy,prompt_config) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
READBACK_SQL = "SELECT id,name,status,tenant_id,agent_id,knowledge_base_id,reply_strategy,prompt_config FROM yj_agent_info WHERE id = 3"
SOURCE_MARKER = "career-planning-coach"

def load_application_database_target(app_config):
    text = Path(app_config).read_text(encoding="utf-8")
    match = re.search(r"jdbc:mysql://(?P<host>[^/:]+):(?P<port>\\d+)/(?P<database>[^?\\s]+)", text)
    if not match:
        raise RuntimeError("invalid application database config")
    return {"host": match.group("host"), "port": int(match.group("port")), "database": match.group("database")}

def assert_same_application_database(target, expected):
    for field in ("host", "port", "database"):
        if target[field] != expected[field]:
            raise RuntimeError("database mismatch")

def abort_if_exists(connection):
    exists = connection.query("SELECT id FROM yj_agent_info WHERE id = %s", 3)
    if exists:
        raise RuntimeError("id 3 exists")

def validate_target(category_id, questions, answers):
    if category_id != CATEGORY_ID:
        raise RuntimeError("wrong category")
    if len(questions) != EXPECTED_QUESTION_COUNT:
        raise RuntimeError("wrong question count")
    if len(answers) != EXPECTED_ANSWER_COUNT:
        raise RuntimeError("wrong answer count")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--app-config", default="code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/resources/application-local.yaml")
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()
    target = load_application_database_target(args.app_config)
    expected = load_application_database_target("code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/resources/application-local.yaml")
    assert_same_application_database(target, expected)
    if not args.apply:
        print("dry-run")
        return 0
    connection = connect_database(target)
    try:
        validate_target(CATEGORY_ID, range(47), range(111))
        abort_if_exists(connection)
        backup_target_rows(connection)
        connection.begin()
        insert_rows(connection, AGENT_ROW)
        verify_readback(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise

if __name__ == "__main__":
    main()
'''

    def validate(source: str) -> None:
        tool = tool_from_source("mutation_fixture.py", source)
        assert_common_contract(tool, repo_root, "mutation fixture", "abort_if_exists")
        assert_question_constants(tool)
        assert_agent_row_contract(tool)

    validate(good_source)
    mutations = {
        "different JDBC database": good_source.replace(
            'SOURCE_MARKER = "career-planning-coach"',
            'SOURCE_MARKER = "career-planning-coach"\nFOREIGN_TARGET = "jdbc:mysql://example.invalid:3306/other"'),
        "connection ignores parsed target": good_source.replace(
            "connection = connect_database(target)",
            'connection = connect_database({"host": "other", "port": 3306, "database": "other"})'),
        "supplied config compared with itself": good_source.replace(
            'expected = load_application_database_target("code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/resources/application-local.yaml")',
            "expected = load_application_database_target(args.app_config)"),
        "backup after write": good_source.replace(
            "backup_target_rows(connection)\n        connection.begin()\n        insert_rows(connection, AGENT_ROW)",
            "connection.begin()\n        insert_rows(connection, AGENT_ROW)\n        backup_target_rows(connection)"),
        "dry-run DML": good_source.replace('print("dry-run")', 'insert_rows(None, AGENT_ROW)'),
        "dry-run direct SQL DML": good_source.replace('print("dry-run")', 'cursor.execute(AGENT_SQL)'),
        "missing rollback": good_source.replace("connection.rollback()", "log_failure()"),
        "readback after commit": good_source.replace(
            "verify_readback(connection)\n        connection.commit()",
            "connection.commit()\n        verify_readback(connection)"),
        "transaction not begun": good_source.replace("connection.begin()", "connection.autocommit(True)"),
        "id conflict does not abort": good_source.replace(
            'raise RuntimeError("id 3 exists")', "return None"),
        "id conflict after write": good_source.replace(
            "abort_if_exists(connection)\n        backup_target_rows(connection)\n        connection.begin()\n        insert_rows(connection, AGENT_ROW)",
            "backup_target_rows(connection)\n        connection.begin()\n        insert_rows(connection, AGENT_ROW)\n        abort_if_exists(connection)"),
        "wrong question count": good_source.replace("EXPECTED_QUESTION_COUNT = 47", "EXPECTED_QUESTION_COUNT = 46"),
        "wrong answer count": good_source.replace("EXPECTED_ANSWER_COUNT = 111", "EXPECTED_ANSWER_COUNT = 110"),
        "wrong category": good_source.replace("CATEGORY_ID = 14", "CATEGORY_ID = 13"),
        "wrong Agent id": good_source.replace('"id": 3,', '"id": 4,'),
        "wrong Agent name": good_source.replace('"name": "职业规划评测"', '"name": "自我评测"'),
        "wrong Agent status": good_source.replace('"status": 1', '"status": 0'),
        "wrong Agent tenant": good_source.replace('"tenant_id": 1', '"tenant_id": 2'),
        "non-null Agent agent_id": good_source.replace('"agent_id": None', '"agent_id": 9'),
        "non-null Agent knowledge_base_id": good_source.replace(
            '"knowledge_base_id": None', '"knowledge_base_id": 9'),
        "non-null Agent reply_strategy": good_source.replace('"reply_strategy": None', '"reply_strategy": "x"'),
        "wrong Agent prompt": good_source.replace(
            '"prompt_config": SELF_SYSTEM_PROMPT', '"prompt_config": "not SELF_SYSTEM_PROMPT"'),
    }
    for label, source in mutations.items():
        try:
            validate(source)
        except AssertionError:
            continue
        raise AssertionError(f"mutation escaped Python AST contract: {label}")
    print(f"PASS Python AST mutation proof rejected {len(mutations)} targeted false-green variants")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("question", "agent", "isolation", "mutation", "all"), default="all")
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    if args.suite == "question":
        question_contract(repo_root)
    elif args.suite == "agent":
        agent_contract(repo_root)
    elif args.suite == "isolation":
        isolation_contract(repo_root)
    elif args.suite == "mutation":
        mutation_contract(repo_root)
    else:
        question_contract(repo_root)
        agent_contract(repo_root)
        isolation_contract(repo_root)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
