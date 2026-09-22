# 入库执行记录

## 执行结论

- 执行状态：已执行
- 是否执行入库：是
- 是否生成导入脚本：是，`import_yj_practice_survey.py`
- 是否生成回滚脚本：是，`rollback_yj_practice_survey.sql`
- 执行数据库：测试库 `114.111.30.111:13306/yunjikeji`
- 执行时间：2026-06-11 14:21:46 至 14:21:52
- 执行结果：`committed`

## 已完成工作

- 已使用 chrome-devtools 访问 `https://120.79.4.220/`。
- 已采集“入行专属评估”问卷真实页面题目。
- 已整理 21 道主问题和条件补充输入。
- 已核对仓库中的 `yj_practice` 系列表结构。
- 已确认现有题型字典只覆盖 `single_choice`、`multiple_choice`、`judge`。

## 执行策略

1. 使用用户明确允许的仓库测试库连接。
2. 使用 Python + `pymysql` 执行，执行前已安装本机依赖 `pymysql`。
3. 导入前自动备份同名分类关联数据到备份表：
   - `yj_practice_category_bak_20260611_survey_import`
   - `yj_practice_exercises_bak_20260611_survey_import`
   - `yj_practice_exercises_answer_bak_20260611_survey_import`
   - `yj_practice_exercises_answer_child_bak_20260611_survey_import`
4. 因测试库开启 GTID 一致性，备份方式采用 `CREATE TABLE LIKE` + `INSERT IGNORE INTO ... SELECT`。
5. 导入前将 3 张题目相关表的 `question_type` 扩展为 `varchar(32)`，并补齐题型字典：
   - `single_choice`
   - `multiple_choice`
   - `judge`
   - `text`
6. 文本题以 `question_type = text` 写入 `yj_practice_exercises`，不写入答案选项。
7. 单选/多选题写入 `yj_practice_exercises_answer`，所有 `is_correct` 均为 `b'0'`，避免把调查问卷选项误标为标准答案。

## 执行结果

- 分类 ID：`13`
- 分类名称：`入行专属评估`
- `field_type`：`low_air`
- `tenant_id`：`1`
- 导入题目数：`21`
- 导入选项数：`101`
- 题型分布：
  - `single_choice`：`10`
  - `multiple_choice`：`9`
  - `text`：`2`
- 文本题答案数：`0`

## 复核结果

- `yj_practice_category.id = 13` 的分类存在，名称 UTF-8 十六进制为 `E585A5E8A18CE4B893E5B19EE8AF84E4BCB0`，对应“入行专属评估”。
- `yj_practice_exercises` 中 `category_id = 13`、`tenant_id = 1`、未删除题目数为 `21`。
- `yj_practice_exercises_answer` 中关联选项数为 `101`。
- `yj_practice_exercises`、`yj_practice_exercises_answer`、`yj_practice_exercises_answer_child` 的 `question_type` 字段长度均为 `32`。
- `system_dict_data` 已存在 `single_choice`、`multiple_choice`、`judge`、`text` 四个 `yj_practice_question_type` 字典值。

## 当前收口

- 当前任务状态建议：待独立验收。
- 当前验收结论：待独立验收。
- 未操作生产数据库。
- 未修改业务代码。
- 未修改 `uni_modules/**`。
