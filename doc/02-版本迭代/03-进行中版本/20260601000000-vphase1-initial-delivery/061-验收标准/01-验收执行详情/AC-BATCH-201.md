# AC-BATCH-201 批次映射、排序与回滚

- 类型：技术-数据级
- 正式入口：`yj_practice_catalog_batch`、`yj_practice_exercises_batch`、`yj_practice_exercises_answer_batch` 及其生成 SQL。
- 支撑的业务结果：题批次、答案批次和题内选项顺序正确承接，且失败时不留下半成品批次。
- 数据边界：`yj_practice_exercises_batch` 记录 `catalog_batch_id`、`custom_account_id`、`exercises_id` 和最终 `sort_no`；`yj_practice_exercises_answer_batch` 仅通过 `exercises_batch_id` 关联题批次，答案行的 `answer_id`、`answer_content`、`is_correct` 与原始答案绑定，`sort_no` 和 `answer_code` 与最终顺序一致；不恢复 `catalog_batch_id`。
- 通过条件：批次生成、答案插入和映射更新在同一事务内完成；事务失败整体回滚；并发下批次归属不串；SQL 兼容 MySQL 5.7。
- 证据承接：`061-验收标准/03-测试验证/DEV-063/`。
