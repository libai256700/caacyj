# TASK-008 导入前清空边界与顺序

## 1. 这轮默认要清空的表

### 1.1 staging 表

在加载本轮 CSV 前，先清空上一轮残留 staging：

1. `yk_question_import_option_staging`
2. `yk_question_import_staging`

对应脚本：`20260514001000-dml-question-import-staging-reset.sql`

这样做的目的只有一个：避免上一轮 staging 残留继续参与本轮导入判断。

### 1.2 正式题库主数据表

在本轮 staging 已加载完成后，再按当前 staging 中 `parse_status = 'parsed'` 的 `question_code` 精确清空正式题库主数据：

1. `yk_question_option`
2. `yk_question`

对应脚本：`20260514002000-dml-question-import-target-preclear.sql`

这里不是按整张题库表全量清空，而是只清空“本轮即将重新导入的题目编码集合”对应数据，避免误伤与本轮无关的题目。

## 2. 这轮默认不清空的表

### 2.1 不清 `yk_question_category`

原因：

1. `yk_question_category` 是 11 个正式分类主数据。
2. 当前分类 seed 已经是固定入口，默认应保留，不作为“垃圾数据清空”的第一目标。
3. 只有在用户明确要求“连分类一起重置并重跑 seed”时，才考虑单独处理分类表。

### 2.2 不清 `yk_practice_record` / `yk_practice_session`

原因：

1. 这两张表承载练习行为数据，不属于“题库导入原料”。
2. 一旦直接清空，会把已产生的作答、会话、题目快照一起抹掉。
3. 本轮需求没有授权清理练习行为数据。

### 2.3 不清 `yk_wrong_question_book`

原因：

1. 这张表承载用户错题归集结果，不属于本轮题库原料。
2. 它依赖 `yk_question` 和 `yk_practice_record`，误删会扩大影响面。
3. 本轮只允许把它作为阻断检查对象，不默认纳入清空范围。

## 3. 默认清空顺序

### 3.1 导入前准备顺序

1. 先完成备份。
2. 执行 `20260514001000-dml-question-import-staging-reset.sql`，清空旧 staging。
3. 装载本轮新的 question staging CSV 和 option staging CSV。
4. 抽查本轮 staging，确认 `parsed / needs_manual_review / ignored_noise` 状态符合预期。
5. 执行 `20260514002000-dml-question-import-target-preclear.sql`。
6. 只有当脚本返回：
   - `blocked_practice_record_count = 0`
   - `blocked_wrong_book_count = 0`
7. 才继续执行 `20260513202000-dml-question-import-from-staging.sql`。

### 3.2 正式题库表内部顺序

如果阻断计数都是 `0`，正式表按以下顺序清空：

1. 先清 `yk_question_option`
2. 再清 `yk_question`

原因：`yk_question_option.question_id -> yk_question.id`，必须先删子表再删父表。

## 4. 阻断条件

只要出现以下任一情况，本轮就不应继续执行正式题库清空，更不应继续导入：

1. `yk_practice_record` 中已经有记录引用了本轮准备重导的题目。
2. `yk_wrong_question_book` 中已经有记录引用了本轮准备重导的题目。
3. 当前 staging 还没有装载完成，却直接尝试执行正式题库清空。

`20260514002000-dml-question-import-target-preclear.sql` 已做保护：

1. 它会先输出目标题目数、命中的正式题目数、阻断计数。
2. 只要阻断计数不为 `0`，正式删除语句就不会生效。

## 5. 这轮清空边界结论

本轮“导入前清空垃圾数据”的正式边界是：

1. 必清：`yk_question_import_option_staging`、`yk_question_import_staging`
2. 条件清空：`yk_question_option`、`yk_question`
3. 默认不清：`yk_question_category`、`yk_practice_record`、`yk_practice_session`、`yk_wrong_question_book`

如果后续确认测试库里的练习记录、错题记录本身也是垃圾数据，需要单独拿到用户确认后，再额外补一轮“行为数据联动清空”脚本；本轮资产先不越界。
 
## Current pause gate

This boundary note documents prepared SQL assets only. This round is paused before database execution; do not execute the staging reset, target preclear, or import scripts without a later explicit confirmation from the user.

The preclear script `20260514002000-dml-question-import-target-preclear.sql` is prepared but is not approved for execution in the current round. The existing database contains historical garbage data, and the intended future strategy is to clear the target data that will be imported before running the import, but that cleanup must wait for explicit user confirmation.
