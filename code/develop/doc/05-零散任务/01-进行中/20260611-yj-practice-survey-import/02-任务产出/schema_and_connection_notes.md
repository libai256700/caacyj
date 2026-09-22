# yj_practice 表结构与连接核对记录

## 连接入口结论

- 按 `00-0400-application-connection-management` 要求，数据库写入前应先核对正式连接入口。
- 当前本机未发现正式连接中心目录：
  - `C:\Users\renquan\.devcenter\Operations\ApplicationConnections\`
- 仓库配置中发现测试库连接事实：
  - 文件：`yunjikeji-admin-server/yunjikeji-admin-server/src/main/resources/application-local.yaml`
  - 地址：`114.111.30.111:13306/yunjikeji`
  - 用户：`yunjikeji_test`
- 用户已在 2026-06-11 当前对话中明确允许使用仓库里的测试库继续导入。

## 工具链核对

- 当前环境未发现可直接使用的 `mysql` CLI。
- 已通过 `python -m pip install pymysql` 安装本机执行依赖。
- 已使用 Python + `pymysql` 完成测试库实时查询与写入。

## 目标表结构结论

### `yj_practice_category`

来源：
- `PracticeCategoryDO.java`
- `数据库表结构说明.md`

关键字段：
- `id`
- `category_name`
- `category_status`
- `field_type`
- `sort_no`
- 通用审计字段
- `tenant_id`

目标分类：
- `入行专属评估`

### `yj_practice_exercises`

来源：
- `PracticeExercisesDO.java`
- `数据库表结构说明.md`

关键字段：
- `id`
- `category_id`
- `question_stem`
- `question_type`
- `question_status`
- `score`
- `sort_no`
- `correct_memo`
- 通用审计字段
- `tenant_id`

### `yj_practice_exercises_answer`

来源：
- `PracticeExercisesAnswerDO.java`
- `数据库表结构说明.md`

关键字段：
- `id`
- `exercises_id`
- `question_type`
- `answer_code`
- `answer_content`
- `is_correct`
- `sort_no`
- 通用审计字段
- `tenant_id`

注意：代码中的字段名是 `is_correct`，旧文档里出现过拼写不一致描述，应以代码和真实表结构为准。

### `yj_practice_exercises_answer_child`

来源：
- `PracticeExercisesAnswerChildDO.java`
- `数据库表结构说明.md`

关键字段：
- `id`
- `answer_id`
- `question_type`
- `answer_content`
- `is_correct`
- 通用审计字段
- `tenant_id`

## 题型约束

仓库中已确认的题型字典：
- `single_choice`
- `multiple_choice`
- `judge`

外部问卷题型：
- 文本题
- 单选题
- 多选题
- 条件补充文本输入

本次处理：
- 已补齐 `text` 字典值承接文本题。
- 单选/多选选项全部按调查选项导入，`is_correct = b'0'`，不设置标准答案。
- 条件补充输入写入题目 `correct_memo` 说明，不拆成独立题目。

## 当前结论

- 真实问卷已采集。
- 目标表结构已从仓库代码、文档和测试库实时结构核对。
- 用户已允许使用仓库测试库。
- 本轮已完成测试库导入和结果复核。
