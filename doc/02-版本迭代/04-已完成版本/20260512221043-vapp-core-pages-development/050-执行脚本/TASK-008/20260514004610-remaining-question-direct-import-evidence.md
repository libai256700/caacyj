# TASK-008 剩余题库导入执行证据

- 执行时间：`20260514004610`
- 目标环境：`测试库 yunjikeji`
- 本次恢复范围：`163` 题
- 本次恢复来源：`无人机教员 155`、`概述 5`、`无人机操作注意事项 2`、`无人机飞行手册、法律法规及其他 1`

## 资产修正

- question CSV 原件备份：`20260514004446-question-import-staging-real.before-fix.csv`
- option CSV 原件备份：`20260514004446-question-import-option-staging-real.before-fix.csv`
- 资产修正报告：`20260514004446-remaining-question-asset-fix-report.md`
- 实际修正：`163` 条 question 记录改为 `parsed`
- 实际重建：`489` 条 option 记录

## 导入前后对比

- 导入前目标题激活数：`0`
- 导入前目标选项激活数：`0`
- 导入后目标题激活数：`163`
- 导入后目标选项激活数：`489`
- 导入前总题数：`1310`
- 导入后总题数：`1473`
- 导入前总选项数：`3916`
- 导入后总选项数：`4405`
- 分类总数：`11`

## Postcheck 摘要

- `excluded_needs_manual_without_option=0`
- `active_excluded_question_rows=0`
- `active_duplicate_option_rows=0`
- `missing_category_mapping_rows=0`
- `missing_option_question_mapping_rows=0`
- 历史重复 option key 组仍有 `5` 组，但未在激活数据中生效，本次目标 163 题未受影响

## 执行文件

- 导入前快照 SQL：`20260514004610-before-target-rowcounts.sql`
- 导入前快照输出：`20260514004610-before-target-rowcounts.txt`
- 分类 seed 输出：`20260514004610-seed-output.txt`
- 运行时 TSV 输出：`20260514004610-prepare-runtime-tsv-output.txt`
- 直导输出：`20260514004610-exec-direct-import-fixed-output.txt`
- 直导错误输出：`20260514004610-exec-direct-import-fixed-errors.txt`
- 导入后校验输出：`20260514004610-postcheck-direct-import-fixed-output.txt`
- 导入后校验错误输出：`20260514004610-postcheck-direct-import-fixed-errors.txt`
- 导入后目标快照 SQL：`20260514004610-after-target-rowcounts.sql`
- 导入后目标快照输出：`20260514004610-after-target-rowcounts.txt`
