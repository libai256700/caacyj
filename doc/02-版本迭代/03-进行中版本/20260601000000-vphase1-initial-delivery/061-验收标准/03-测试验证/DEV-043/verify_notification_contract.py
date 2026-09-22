#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from typing import Iterable


def to_posix(path: Path) -> str:
    return path.as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def list_matches(base: Path, patterns: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        for candidate in base.glob(pattern):
            if candidate.is_file():
                matches.append(to_posix(candidate.relative_to(base)))
    return sorted(set(matches))


def search_text(base: Path, patterns: Iterable[str], needle: str) -> list[str]:
    matches: list[str] = []
    for relative_path in list_matches(base, patterns):
        if needle in read_text(base / relative_path):
            matches.append(relative_path)
    return matches


def extract_annotation_values(source: str, annotation: str) -> list[str]:
    values: list[str] = []
    pattern = re.compile(rf"@{annotation}\s*\((.*?)\)", re.DOTALL)
    for match in pattern.finditer(source):
        body = match.group(1)
        quoted = re.findall(r'"([^"]+)"', body)
        if quoted:
            values.extend(quoted)
            continue
        if body.strip() == "":
            values.append("")
    bare_pattern = re.compile(rf"@{annotation}(?!\s*\()")
    for _ in bare_pattern.finditer(source):
        values.append("")
    return values or [""]


def normalize_segments(*segments: str) -> str:
    parts = [segment.strip().strip("/") for segment in segments if segment.strip()]
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def collect_spring_routes(java_file: Path) -> set[str]:
    source = read_text(java_file)
    class_prefixes = extract_annotation_values(source, "RequestMapping")
    if not class_prefixes:
        class_prefixes = [""]
    route_set: set[str] = set()
    method_pattern = re.compile(
        r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*(\((.*?)\))?",
        re.DOTALL,
    )
    for match in method_pattern.finditer(source):
        annotation = match.group(1)
        body = match.group(3) or ""
        method_values = re.findall(r'"([^"]+)"', body)
        if not method_values:
            method_values = [""]
        if annotation == "RequestMapping" and match.start() == source.find("@RequestMapping"):
            continue
        for class_prefix in class_prefixes:
            for method_value in method_values:
                route_set.add(normalize_segments(class_prefix, method_value))
    return route_set


def find_backend_routes(base: Path, expected_routes: list[str]) -> tuple[list[str], list[str]]:
    if not base.exists():
        return [], expected_routes[:]
    files = list_matches(base, ["controller/**/*.java"])
    found_routes: dict[str, list[str]] = {route: [] for route in expected_routes}
    for relative_path in files:
        route_set = collect_spring_routes(base / relative_path)
        for route in expected_routes:
            if route in route_set:
                found_routes[route].append(relative_path)
    evidence = [f"{route} <- {','.join(paths)}" for route, paths in found_routes.items() if paths]
    missing = [route for route, paths in found_routes.items() if not paths]
    return evidence, missing


def find_frontend_contracts(base: Path, expected_contracts: list[str]) -> tuple[list[str], list[str]]:
    files = list_matches(base, ["src/**/*.ts", "src/**/*.js", "src/**/*.vue", "src/**/*.json"])
    evidence: list[str] = []
    missing: list[str] = []
    for contract in expected_contracts:
        matched_files = []
        for relative_path in files:
            source = read_text(base / relative_path)
            contract_pattern = re.escape(contract).replace(
                re.escape("{id}"), r"\$\{[^}\r\n]+\}"
            )
            if re.search(contract_pattern, source):
                matched_files.append(relative_path)
        if matched_files:
            evidence.append(f"{contract} <- {','.join(sorted(set(matched_files)))}")
        else:
            missing.append(contract)
    return evidence, missing


def has_required_provider_files(matches: list[str]) -> bool:
    basenames = {Path(match).name for match in matches}
    return (
        "PushProvider.java" in basenames
        and "NoopPushProvider.java" in basenames
        and "UniCloudHttpPushProvider.java" in basenames
    )


def add_result(
    results: list[dict],
    check_id: str,
    title: str,
    ac_ids: list[str],
    passed: bool,
    detail: str,
    evidence: list[str],
) -> None:
    results.append(
        {
            "checkId": check_id,
            "title": title,
            "acIds": ac_ids,
            "passed": passed,
            "detail": detail,
            "evidence": evidence,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (workspace_root / output_path).resolve()

    backend_root = workspace_root / "code/develop/yunjikeji-admin-server"
    admin_ui_root = workspace_root / "code/develop/yunjikeji-admin-ui"
    app_root = workspace_root / "code/develop/yunjikeji"
    notification_module_root = backend_root / "yunjikeji-module-notification"
    backend_java_base = notification_module_root / "src/main/java/com/huiyitech/notification"

    results: list[dict] = []

    pom_xml = read_text(backend_root / "pom.xml")
    add_result(
        results,
        "backend_parent_module_declared",
        "后端父 POM 已声明消息推送模块",
        ["AC-PUSH-101", "AC-PUSH-301"],
        "<module>yunjikeji-module-notification</module>" in pom_xml,
        "父 POM 必须纳入 yunjikeji-module-notification。",
        ["code/develop/yunjikeji-admin-server/pom.xml"],
    )

    add_result(
        results,
        "backend_module_pom_exists",
        "后端消息推送模块 POM 已建立",
        ["AC-PUSH-101", "AC-PUSH-301"],
        (notification_module_root / "pom.xml").exists(),
        "消息推送模块至少需要独立 pom.xml。",
        ["code/develop/yunjikeji-admin-server/yunjikeji-module-notification/pom.xml"],
    )

    admin_controller_matches = list_matches(
        backend_java_base, ["controller/admin/**/*Controller.java"]
    )
    add_result(
        results,
        "backend_admin_controller_exists",
        "后端管理端控制器目录已建立",
        ["AC-PUSH-101", "AC-PUSH-301"],
        bool(admin_controller_matches),
        "管理平台至少需要消息推送管理控制器。",
        admin_controller_matches
        or ["code/develop/yunjikeji-admin-server/yunjikeji-module-notification/src/main/java/com/huiyitech/notification/controller/admin/"],
    )

    app_controller_matches = list_matches(
        backend_java_base, ["controller/app/**/*Controller.java"]
    )
    add_result(
        results,
        "backend_app_controller_exists",
        "后端 App 控制器目录已建立",
        ["AC-PUSH-101", "AC-PUSH-102"],
        bool(app_controller_matches),
        "App 侧至少需要设备绑定、消息列表、已读、打开上报接口。",
        app_controller_matches
        or ["code/develop/yunjikeji-admin-server/yunjikeji-module-notification/src/main/java/com/huiyitech/notification/controller/app/"],
    )

    service_matches = list_matches(backend_java_base, ["service/**/*Service*.java"])
    add_result(
        results,
        "backend_service_exists",
        "后端核心服务目录已建立",
        ["AC-PUSH-101", "AC-PUSH-102", "AC-PUSH-201"],
        bool(service_matches),
        "消息发送、设备绑定、消息中心读取与状态回写必须有 service 入口。",
        service_matches
        or ["code/develop/yunjikeji-admin-server/yunjikeji-module-notification/src/main/java/com/huiyitech/notification/service/"],
    )

    provider_matches = list_matches(
        backend_java_base,
        [
            "provider/**/*PushProvider.java",
            "provider/**/*NoopPushProvider.java",
            "provider/**/*UniCloudHttpPushProvider.java",
            "provider/**/*Bridge*.java",
        ],
    )
    add_result(
        results,
        "backend_push_provider_exists",
        "后端 PushProvider 与桥接 Provider 已建立",
        ["AC-PUSH-102", "AC-PUSH-301"],
        has_required_provider_files(provider_matches),
        "后端必须按 PushProvider / NoopPushProvider / UniCloudHttpPushProvider 或等价 Bridge 方式建模，不得期待 Java UniPush SDK。",
        provider_matches
        or ["code/develop/yunjikeji-admin-server/yunjikeji-module-notification/src/main/java/com/huiyitech/notification/provider/"],
    )

    required_admin_backend_contracts = [
        "/notification/push/page",
        "/notification/push/get",
        "/notification/push/create",
        "/notification/push/update",
        "/notification/push/delete",
        "/notification/push/publish",
        "/notification/push/cancel",
        "/notification/push/retry",
        "/notification/push/delivery-page",
        "/notification/push/statistics",
    ]
    admin_backend_evidence, missing_admin_backend_contracts = find_backend_routes(
        backend_java_base, required_admin_backend_contracts
    )
    add_result(
        results,
        "backend_admin_api_contract_declared",
        "后端管理端消息推送 API 契约已落代码",
        ["AC-PUSH-101", "AC-PUSH-201", "AC-PUSH-301"],
        not missing_admin_backend_contracts,
        "必须覆盖 page/get/create/update/delete/publish/cancel/retry/delivery-page/statistics。",
        admin_backend_evidence
        or [f"MISSING {contract}" for contract in missing_admin_backend_contracts],
    )

    required_app_backend_contracts = [
        "/notification/devices/bind",
        "/notification/devices/unbind",
        "/notification/messages/page",
        "/notification/messages/{id}",
        "/notification/messages/unread",
        "/notification/messages/{id}/read",
        "/notification/messages/read-all",
        "/notification/messages/{id}/open",
    ]
    app_backend_evidence, missing_app_backend_contracts = find_backend_routes(
        backend_java_base, required_app_backend_contracts
    )
    add_result(
        results,
        "backend_app_api_contract_declared",
        "后端 App 消息推送 API 契约已落代码",
        ["AC-PUSH-101", "AC-PUSH-102", "AC-PUSH-301"],
        not missing_app_backend_contracts,
        "必须覆盖 device bind/unbind、message page/{id}/unread/{id}/read/read-all/{id}/open。",
        app_backend_evidence
        or [f"MISSING {contract}" for contract in missing_app_backend_contracts],
    )

    admin_ui_api_contracts = [
        "/notification/push/page",
        "/notification/push/get",
        "/notification/push/create",
        "/notification/push/update",
        "/notification/push/delete",
        "/notification/push/publish",
        "/notification/push/cancel",
        "/notification/push/retry",
        "/notification/push/delivery-page",
        "/notification/push/statistics",
    ]
    admin_ui_evidence, missing_admin_ui_contracts = find_frontend_contracts(admin_ui_root, admin_ui_api_contracts)
    add_result(
        results,
        "admin_ui_push_api_exists",
        "管理平台推送 API 封装已建立",
        ["AC-PUSH-101", "AC-PUSH-201"],
        not missing_admin_ui_contracts,
        "管理平台必须落前端 API 封装。",
        admin_ui_evidence or [f"MISSING {contract}" for contract in missing_admin_ui_contracts],
    )

    admin_ui_candidate_files = [
        "src/views/system/notify/push/index.vue",
        "src/views/system/notify/push/PushForm.vue",
        "src/views/system/notify/push/PushDetail.vue",
        "src/views/system/notify/push/DeliveryDetail.vue",
        "src/views/messages/push/index.vue",
        "src/views/messages/push/PushForm.vue",
        "src/views/messages/push/PushDetail.vue",
        "src/views/messages/push/DeliveryDetail.vue",
    ]
    admin_ui_view_matches = []
    for relative_path in admin_ui_candidate_files:
        file_path = admin_ui_root / relative_path
        if file_path.exists():
            source = read_text(file_path)
            if any(token in source for token in ["推送", "投递明细", "App 推送", "/notification/push"]):
                admin_ui_view_matches.append(relative_path)
    add_result(
        results,
        "admin_ui_push_view_exists",
        "管理平台推送页面已建立",
        ["AC-PUSH-101", "AC-PUSH-201"],
        bool(admin_ui_view_matches),
        "管理平台至少应存在消息管理页面、编辑页或投递明细页之一。",
        admin_ui_view_matches or admin_ui_candidate_files,
    )

    app_service_contracts = [
        "/app-api/yj/notification/devices/bind",
        "/app-api/yj/notification/devices/unbind",
        "/app-api/yj/notification/messages/page",
        "/app-api/yj/notification/messages/{id}",
        "/app-api/yj/notification/messages/unread",
        "/app-api/yj/notification/messages/{id}/read",
        "/app-api/yj/notification/messages/read-all",
        "/app-api/yj/notification/messages/{id}/open",
    ]
    app_service_evidence, missing_app_service_contracts = find_frontend_contracts(app_root, app_service_contracts)
    add_result(
        results,
        "app_service_contract_exists",
        "手机 App 消息中心服务契约已建立",
        ["AC-PUSH-101", "AC-PUSH-102"],
        not missing_app_service_contracts,
        "App 侧必须具备设备绑定、消息列表、未读数、已读和打开上报服务封装。",
        app_service_evidence or [f"MISSING {contract}" for contract in missing_app_service_contracts],
    )

    pages_json = read_text(app_root / "src/pages.json")
    add_result(
        results,
        "app_message_center_page_registered",
        "手机 App 消息中心页面已注册",
        ["AC-PUSH-101"],
        any(token in pages_json for token in ["message-center", "messageCenter", "notification/message"]),
        "pages.json 至少需要登记消息中心页面路由。",
        ["code/develop/yunjikeji/src/pages.json"],
    )

    app_vue = read_text(app_root / "src/App.vue")
    add_result(
        results,
        "app_push_lifecycle_exists",
        "手机 App 推送生命周期已接入",
        ["AC-PUSH-102"],
        "onPushMessage" in app_vue and "clientId" in app_vue,
        "App.vue 至少需要处理 clientId 获取/绑定与 onPushMessage 接收。",
        ["code/develop/yunjikeji/src/App.vue"],
    )

    manifest_json = read_text(app_root / "src/manifest.json")
    add_result(
        results,
        "app_manifest_push_config_exists",
        "手机 App manifest 已出现推送配置",
        ["AC-PUSH-102"],
        "unipush" in manifest_json.lower(),
        "manifest.json 需要出现 UniPush 相关配置锚点。",
        ["code/develop/yunjikeji/src/manifest.json"],
    )

    bridge_candidates = list_matches(
        app_root,
        [
            "uniCloud-aliyun/cloudfunctions/yj-push-bridge/index.js",
            "uniCloud-aliyun/cloudfunctions/**/index.js",
        ],
    )
    bridge_passed = any(
        match == "uniCloud-aliyun/cloudfunctions/yj-push-bridge/index.js"
        for match in bridge_candidates
    )
    add_result(
        results,
        "app_unicloud_push_bridge_exists",
        "App 仓 UniCloud 推送桥接函数已建立",
        ["AC-PUSH-102", "AC-PUSH-301"],
        bridge_passed,
        "App 仓必须存在 `uniCloud-aliyun/cloudfunctions/yj-push-bridge/index.js` 或设计最终确认的等价正式桥接路径。",
        bridge_candidates
        or ["code/develop/yunjikeji/uniCloud-aliyun/cloudfunctions/yj-push-bridge/index.js"],
    )

    sql_evidence: list[str] = []
    missing_tables: list[str] = []
    for table_name in [
        "yj_push_message",
        "yj_push_recipient",
        "yj_push_device",
        "yj_push_delivery",
    ]:
        matched_files = search_text(
            backend_root,
            ["sql/**/*.sql", "**/*.sql", "src/**/*.xml", "src/**/*.java"],
            table_name,
        )
        if matched_files:
            sql_evidence.extend(matched_files)
        else:
            missing_tables.append(table_name)
    add_result(
        results,
        "sql_push_tables_exist",
        "四张消息推送表已落脚本或代码引用",
        ["AC-PUSH-201", "AC-PUSH-301"],
        not missing_tables,
        "必须能在仓库中定位到四张推送表。",
        sorted(set(sql_evidence)) or [f"MISSING {table_name}" for table_name in missing_tables],
    )

    report = {
        "status": "PASS" if all(item["passed"] for item in results) else "FAIL",
        "workspaceRoot": to_posix(workspace_root),
        "outputGeneratedAt": "2026-08-10",
        "summary": {
            "totalChecks": len(results),
            "passedChecks": sum(1 for item in results if item["passed"]),
            "failedChecks": sum(1 for item in results if not item["passed"]),
        },
        "checks": results,
    }
    output_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    output_path.write_text(output_text, encoding="utf-8")
    print(output_text, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
