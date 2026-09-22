# TASK-008 综合问答补录后测试库正式导入执行证据

## 执行结论

- 状态：DONE
- 执行环境：测试库 `yunjikeji`
- 生产库操作：无
- 持久化写入范围：`yk_question`、`yk_question_option`
- 本次目标：将已补齐的 `综合问答` 199 题与现有 TASK-008 全量题库资产一起，按最终业务表直导路线落入测试库

## 实际执行脚本

- 运行时 TSV 准备：`20260514014800-prepare-direct-import-runtime-csv.ps1`
- 最终导入脚本：`20260514014000-dml-question-direct-import-final-tables-fixed.sql`
- 导入后校验脚本：`20260514020000-postcheck-direct-import-final-tables-fixed.sql`

## 选择 fixed/final 路线的理由

- 原始 `20260514010000-dml-question-direct-import-final-tables.sql` 直接读取 CSV，面对题干、解析、JSON、换行混排内容时稳定性不足。
- `fixed` 版本先将真实 CSV 转为 MySQL 安全 TSV，再通过会话级临时表直导最终业务表，更适合当前补录后的真实资产。
- `fixed` 版本额外补齐了“题目必须至少存在 1 条可导入选项”的过滤口径，避免无有效选项题进入最终业务表。

## 导入前证据

- 运行时 TSV 生成结果：题目 `1475` 行，选项 `4028` 行
- 测试库导入前计数：
  - `yk_question_category = 11`
  - `yk_question = 1112`
  - `yk_question_option = 3322`
  - `Q-CQA-* question = 0`
  - `Q-CQA-* option = 0`
- 备份文件：`20260513232727-backup-before-comprehensive-qa-import.sql`
- 备份说明：使用 `mysqldump` 对 `yk_question_category`、`yk_question`、`yk_question_option` 做测试库备份；错误文件仅保留 mysql 命令行密码警告，无 SQL 失败

## 导入执行摘要

来自 `20260513232727-exec-direct-import-final-tables-comprehensive-qa-output.txt`：

- 源题目行数：`1475`
- 源选项行数：`4028`
- 重复 `question_code`：`0`
- 重复 `(question_code, option_code)` 键组：`5`
- `needs_manual_review` 且无选项排除：`163`
- 无可导入选项排除：`1`
- `invalid_options_json`：`1`（`Q-ROTARY-0030`）
- 可导入题目：`1310`
- 可导入选项：`3916`
- 清理结果：
  - `batch_option_deleted_rows = 3319`
  - `non_batch_option_deleted_rows = 3`
  - `batch_non_importable_question_soft_deleted_rows = 0`
  - `non_batch_question_soft_deleted_rows = 1`
- 写入结果：
  - `question_upsert_affected_rows = 199`
  - `option_upsert_affected_rows = 3916`

## 导入后关键计数

来自 `20260513232727-postcheck-direct-import-final-tables-comprehensive-qa-output.txt`：

- `yk_question_category = 11`
- `yk_question = 1310`
- `yk_question_option = 3916`
- `active_excluded_question_rows = 0`
- `active_duplicate_option_rows = 0`
- `missing_category_mapping_rows = 0`
- `missing_option_question_mapping_rows = 0`

分类分布：

- `overview = 53`
- `system_components = 148`
- `air_traffic_control = 37`
- `flight_manual_and_regulations = 91`
- `operation_precautions = 77`
- `meteorology = 255`
- `rotary_uav = 76`
- `mission_planning = 74`
- `flight_principles_and_performance = 300`
- `comprehensive_qa = 199`
- `instructor_question_bank = 0`

## 综合问答专项校验

来自 `20260513232727-postcheck-comprehensive-qa-counts.txt`：

- `Q-CQA-* question = 199`
- `Q-CQA-* option = 597`
- `Q-CQA-* delete_status <> 0 = 0`
- 抽查：
  - `Q-CQA-0001 -> comprehensive_qa / online / delete_status=0`
  - `Q-CQA-0199 -> comprehensive_qa / online / delete_status=0`

说明：

- `Q-CQA-*` 199 题已全部进入最终业务表。
- `Q-CQA-*` 当前无排除项、无软删除项。
- `active_q_cqa_distinct_source_rows = 0` 是因为 `source_ref` 保留了原 CSV 中既有字段值，而不是 `raw-bank/综合问答.md#...` 形式，不影响题目实际入库结果。

## 仍被排除的题目

- 仍排除总数：`165`
- 组成：
  - `163` 题：`needs_manual_review` 且无可导入选项
  - `1` 题：全部选项落入重复键，导致无可导入选项
  - `1` 题：`Q-ROTARY-0030`，`invalid_options_json`
- 本次新增的 `综合问答` 199 题不在排除集合中

## 相关证据文件

- `20260513232727-prepare-runtime-tsv-output.txt`
- `20260513232727-before-direct-import-rowcounts.txt`
- `20260513232727-backup-before-comprehensive-qa-import.sql`
- `20260513232727-backup-before-comprehensive-qa-import-errors.txt`
- `20260513232727-exec-direct-import-final-tables-comprehensive-qa-output.txt`
- `20260513232727-exec-direct-import-final-tables-comprehensive-qa-errors.txt`
- `20260513232727-postcheck-direct-import-final-tables-comprehensive-qa-output.txt`
- `20260513232727-postcheck-direct-import-final-tables-comprehensive-qa-errors.txt`
- `20260513232727-postcheck-comprehensive-qa-counts.txt`
- `20260513232727-postcheck-comprehensive-qa-counts-errors.txt`
