import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[7]
CONFIG_PATH = ROOT / "code/develop/yunjikeji-admin-ui/src/views/yj/resource/config.ts"
INDEX_PATH = ROOT / "code/develop/yunjikeji-admin-ui/src/views/yj/resource/index.vue"
SERVER_TEST_PATH = ROOT / "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/test/java/com/huiyitech/practice/UserPracticeExercisesRecordSqlContractTest.java"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_block(source: str, anchor: str, next_anchor: str) -> str:
    start = source.find(anchor)
    require(start != -1, f"missing anchor: {anchor}")
    end = source.find(next_anchor, start)
    require(end != -1, f"missing next anchor: {next_anchor}")
    return source[start:end]


def main() -> None:
    config_source = load(CONFIG_PATH)
    index_source = load(INDEX_PATH)
    server_test_source = load(SERVER_TEST_PATH)

    wrong_detail_block = extract_block(
        config_source,
        "'practice-record-detail': {",
        "  },\n  post: {"
    )
    wrong_detail_field = extract_block(
        wrong_detail_block,
        "      {\n        prop: 'is_correct'",
        "      },\n      { prop: 'create_time'"
    )

    require("label: '是否正确'" in wrong_detail_field, "wrong-question field label changed")
    require("{ label: '不限', value: '' }" in wrong_detail_field, "missing unlimited option")
    require("{ label: '是', value: true" in wrong_detail_field, "missing true option")
    require("{ label: '否', value: false" in wrong_detail_field, "missing false option")
    require("queryDefaultValue: false" in wrong_detail_field, "missing queryDefaultValue false")
    require(config_source.count("queryDefaultValue: false") == 1, "queryDefaultValue false leaked to other resources")

    reset_dynamic_query = extract_block(
        index_source,
        "const resetDynamicQuery = () => {",
        "\nconst QWENPAW_AGENT_ID_PREFIX"
    )
    require("queryParams[field.prop] = getFieldQueryDefaultValue(field)" in reset_dynamic_query, "resetDynamicQuery no longer reapplies field defaults")

    build_params = extract_block(
        index_source,
        "const buildParams = (params: Record<string, any>) => {",
        "\nconst getList = async () => {"
    )
    require("value !== undefined && value !== null && value !== ''" in build_params, "buildParams no longer keeps false values")

    reset_query = extract_block(
        index_source,
        "const resetQuery = () => {",
        "\nwatch(\n  () => currentConfig.value.resource,"
    )
    require(reset_query.find("resetDynamicQuery()") < reset_query.find("handleQuery()"), "resetQuery no longer applies defaults before querying")

    resource_watch = extract_block(
        index_source,
        "watch(\n  () => currentConfig.value.resource,",
        "\nwatch(\n  () => route.query.callId,"
    )
    require(resource_watch.find("resetDynamicQuery()") < resource_watch.find("getList()"), "resource watch no longer resets defaults before first load")

    require('params.put("is_correct", "false");' in server_test_source, "backend false filter contract missing")
    require('params.put("is_correct", "");' in server_test_source, "backend blank filter contract missing")
    require('assertTrue(whereSql.contains("AND d.is_correct = ?"));' in server_test_source, "backend false SQL assertion missing")
    require('assertFalse(whereSql.contains("d.is_correct = ?"));' in server_test_source, "backend unlimited SQL assertion missing")

    result = {
        "checked_at": "2026-09-02T17:22:12+08:00",
        "resource": "practice-record-detail",
        "assertions": [
            "is_correct field keeps tri-state options with queryDefaultValue=false only on wrong-question resource",
            "resetDynamicQuery reapplies field query defaults",
            "buildParams preserves false while filtering empty string only",
            "resetQuery reapplies defaults before handleQuery",
            "resource watcher reapplies defaults before first getList",
            "backend contract test covers false filter and blank unlimited branch"
        ],
        "result": "PASS"
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
