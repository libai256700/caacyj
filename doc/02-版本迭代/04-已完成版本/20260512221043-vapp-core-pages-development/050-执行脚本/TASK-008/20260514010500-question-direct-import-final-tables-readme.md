# TASK-008 直导最终业务表说明

## 直导路线

本路线放弃 staging 表持久化，不再恢复或依赖 `yk_question_import_staging`、`yk_question_import_option_staging`。执行脚本只把 CSV 读入 MySQL 会话级临时表，临时表随连接释放，不属于正式结构资产。

持久化写入范围仅限：

- `yk_question`
- `yk_question_option`

分类仍使用现有 seed：

- `20260513221000-dml-question-category-seed-v2.sql`

## 输入文件

- `20260513233500-question-import-staging-real.csv`
- `20260513233600-question-import-option-staging-real.csv`

这两个文件虽然沿用 staging 命名，但在本路线中只作为整理好的真实 CSV 输入，不作为 staging 表导入依据。

## 正式脚本

- `20260514010000-dml-question-direct-import-final-tables.sql`

执行命令模板：

```powershell
mysql --host=114.111.30.111 --port=13306 --user=yunji_test --password=yunji8978_ --default-character-set=utf8mb4 --local-infile=1 yunjikeji < .\20260514010000-dml-question-direct-import-final-tables.sql
```

只能在测试库 `yunjikeji` 执行，禁止生产库执行。

## 执行顺序

1. 备份 `yk_question_category`、`yk_question`、`yk_question_option`。
2. 执行或重跑 `20260513221000-dml-question-category-seed-v2.sql`，确保 11 个分类 seed 正常。
3. 执行 `20260514010000-dml-question-direct-import-final-tables.sql`。
4. 脚本先加载 CSV 到临时表并输出源数据计数、重复键清单、排除题清单。
5. 清理目标业务表垃圾数据：
   - 本批题目范围内先删除旧选项，再 upsert 题目与选项。
   - 非本批已存在题目执行软下线，非本批选项物理删除。
   - 不物理删除 `yk_question` 主表旧题，避免破坏 `yk_practice_record.question_id` 历史外键。
6. 直导 `yk_question`，通过 `category_code -> yk_question_category.id` 派生 `category_id`。
7. 直导 `yk_question_option`，通过 `question_code -> yk_question.id` 派生 `question_id`。
8. 输出最终 category/question/option 数量和分类分布。

## 拦截与排除规则

- 5 组重复 `(question_code, option_code)` 不写入 `yk_question_option`，脚本输出异常清单。
- `needs_manual_review` 且无选项的 362 道题不写入可用题，脚本输出排除清单。
- `question_code` 为空、题干为空、答案为空、题型不在 `single_choice/multiple_choice/judge`、JSON 非法、分类缺失的记录不进入可用导入集合。

## 验收证据要求

执行后至少保留：

- 备份文件。
- seed 执行输出。
- 直导脚本执行输出。
- 直导脚本错误输出。
- 导入后校验 SQL 与结果。

独立验收代理应重点核对：

- 持久化写入只发生在 `yk_question`、`yk_question_option`。
- `category_code -> category_id`、`question_code -> question_id` 派生成立。
- 重复选项键被输出为异常清单，不是硬撞唯一键。
- 362 道 `needs_manual_review` 且无选项题未导入为可用题。
- 最终 `yk_question_category` 为 11 个有效分类。
