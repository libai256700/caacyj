# TASK-008 直导最终业务表最终执行证据

## 执行结论

- 状态：DONE
- 执行环境：测试库 `yunjikeji`
- 未执行生产库。
- 持久化写入范围：`yk_question`、`yk_question_option`
- 分类处理：未重跑存在乱码风险的本地 seed 文件；测试库已确认 `yk_question_category` 现有 11 条有效分类，中文分类名正常。
- 输入路线：使用现有真实 CSV 生成 MySQL 安全 TSV 运行副本，再通过会话级临时表直导最终业务表；不恢复、不依赖 staging 表。

## 正式资产

- 运行副本准备脚本：`20260514014800-prepare-direct-import-runtime-csv.ps1`
- 直导最终表脚本：`20260514014000-dml-question-direct-import-final-tables-fixed.sql`
- 导入后校验脚本：`20260514020000-postcheck-direct-import-final-tables-fixed.sql`
- 本地 CSV 事实统计：`20260514021800-source-csv-local-counts.txt`

## 执行顺序

1. 备份目标表：`20260514024600-backup-before-final-rerun.sql`
2. 生成 MySQL 安全 TSV 运行副本：`20260514022500-prepare-runtime-tsv-output.txt`
3. 执行直导最终业务表：`20260514025000-exec-direct-import-final-tables-final-output.txt`
4. 执行导入后校验：`20260514025500-postcheck-direct-import-final-tables-final-output.txt`

## 关键计数

| 指标 | 结果 |
| --- | ---: |
| 源题目 CSV 行数 | 1475 |
| 源选项 CSV 行数 | 3431 |
| 重复 `question_code` | 0 |
| 重复 `(question_code, option_code)` 键组 | 5 |
| `needs_manual_review` 且无选项排除题 | 362 |
| 因全部选项落入重复键而排除题 | 1 |
| `invalid_options_json` 排除题（`Q-ROTARY-0030`） | 1 |
| 排除题合计（`1475 - 1111`） | 364 |
| 最终导入可用题 | 1111 |
| 最终导入可用选项 | 3319 |
| 最终有效分类 | 11 |

## 重复键清单

| question_code | option_code | duplicate_row_count |
| --- | --- | ---: |
| Q-FMR-0093 | A | 38 |
| Q-FMR-0093 | B | 33 |
| Q-FMR-0093 | C | 34 |
| Q-OVERVIEW-0050 | C | 2 |
| Q-ROTARY-0060 | A | 2 |

这些重复键未写入 `yk_question_option`，避免撞唯一键。

## 最终数据库校验

来自 `20260514025500-postcheck-direct-import-final-tables-final-output.txt`：

- `final_active_question_count = 1111`
- `final_active_option_count = 3319`
- `source_question_rows = 1475`
- `source_option_rows = 3431`
- `excluded_needs_manual_without_option = 362`
- `duplicate_option_key_groups = 5`
- `active_excluded_question_rows = 0`
- `active_duplicate_option_rows = 0`
- `missing_category_mapping_rows = 0`
- `missing_option_question_mapping_rows = 0`

题目差额闭环：源题目 1475 条，最终导入可用题 1111 条，实际排除题为 364 条。排除原因拆分为 362 条 `needs_manual_review` 且无选项、1 条因全部选项落入重复键而不可导入、1 条 `Q-ROTARY-0030 invalid_options_json`。

补充实时抽查：

- `yk_question_category = 11`
- `yk_question = 1111`
- `yk_question_option = 3319`
- `active_questions_without_options` 查询无返回行，表示最终无已激活但无选项的题。

## 分类分布

| category_code | category_name | final_question_count |
| --- | --- | ---: |
| overview | 概述 | 53 |
| system_components | 系统组成及介绍 | 148 |
| air_traffic_control | 空中交通管制 | 37 |
| flight_manual_and_regulations | 无人机飞行手册、法律法规及其他 | 91 |
| operation_precautions | 无人机操作注意事项 | 77 |
| meteorology | 气象 | 255 |
| rotary_uav | 旋翼无人机 | 76 |
| mission_planning | 无人机任务规划 | 74 |
| flight_principles_and_performance | 飞行原理与飞行性能 | 300 |
| comprehensive_qa | 综合问答 | 0 |
| instructor_question_bank | 无人机教员题库 | 0 |

## 说明

- 原始 CSV 文件字段中存在较复杂的引号、JSON 和换行内容，直接 `LOAD DATA ... FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'` 会被 MySQL 客户端按不完整 CSV 方言解析，导致只加载约半数行。
- 最终执行改为先从真实 CSV 生成 TSV 运行副本。运行副本只服务本次 MySQL 导入，不作为正式业务表或 staging 表。
- 直导脚本仍只持久化写入 `yk_question`、`yk_question_option`；`category_code -> category_id`、`question_code -> question_id` 均在脚本内派生。
- 错误输出文件中保留了 mysql 命令行密码警告，不包含 SQL 执行错误。
