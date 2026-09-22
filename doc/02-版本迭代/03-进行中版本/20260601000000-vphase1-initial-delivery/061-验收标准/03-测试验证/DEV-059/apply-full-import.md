# DEV-059 理论题库正式替换实施报告

- 执行时间：`2026-08-17 22:32:08 +08:00`
- 执行环境：`local`
- 目标数据库：`114.111.30.111:13306/yunjikeji`
- 题库目录：`E:\huiyitechworkspace\knowledge-graph\-APP--main\-APP--main\knowledge_base\理论题库`

## 执行结果

- `python sql/tools/test_practice_theory_bank_import.py`：`Ran 9 tests ... OK`
- `practice_theory_bank_import.py --import-incomplete-questions` dry-run：通过
- `practice_theory_bank_import.py --apply --confirm-apply REPLACE_PRACTICE_THEORY_BANK`：成功提交

## 备份表

- `yj_practice_category_bak_20260817223208139166`：`12` 行
- `yj_practice_exercises_bak_20260817223208139166`：`1556` 行
- `yj_practice_exercises_answer_bak_20260817223208139166`：`4731` 行
- `yj_practice_exercises_answer_child_bak_20260817223208139166`：`0` 行

## 替换前后计数

- 分类 `1..11` 题目：`1535 -> 1535`
- 分类 `1..11` 答案：`4630 -> 4630`
- 分类 `1..11` 子答案：`0 -> 0`
- 分类 `13` 题目：`21 -> 21`

## 替换后校验

- 空题干题目：`22`
- 非唯一正确答案题目：`1`
- `category_id + sort_no` 重复组数：`0`
- 题目 `tenant_id != 0`：`0`
- 答案 `tenant_id != 0`：`0`
- `correct_memo` 最大长度：`761`

## 说明

- 23 道待维护题已按约定导入，其中 `22` 道为空题干，`1` 道没有唯一正确答案。
- 分类 `13`“入行专属评估”未参与替换，替换前后题量保持 `21`。
- importer 原有 `postApplyStats` SQL 会漏掉 “0 个正确答案” 场景；本轮已在 `sql/tools/practice_theory_bank_import.py` 修正，并补了单元回归测试。
- 独立验收结果：`PASS`，详见 `independent-acceptance-pass.md`。
