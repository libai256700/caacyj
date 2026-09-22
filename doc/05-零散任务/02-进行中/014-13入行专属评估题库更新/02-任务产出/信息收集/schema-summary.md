# 三表结构摘要

- 采集时间：`2026-08-18T12:34:35+08:00`
- 数据库：当前运行程序实际连接的 `yunjikeji`（`114.111.30.111:13306`）
- 会话约束：连接后执行 `SET SESSION TRANSACTION READ ONLY` 与 `START TRANSACTION READ ONLY`。

## `yj_practice_exercises`

| 字段 | 类型 | 可空 | 默认值 | 键/附加 |
| --- | --- | --- | --- | --- |
| `id` | `bigint(20)` | NO | `NULL` | PRI / auto_increment |
| `step_id` | `bigint(20)` | YES | `NULL` | - |
| `category_id` | `bigint(20)` | NO | `NULL` | MUL |
| `question_stem` | `varchar(2000)` | NO | `NULL` | - |
| `question_type` | `varchar(32)` | NO | `NULL` | MUL |
| `question_status` | `bit(1)` | NO | `b'1'` | MUL |
| `score` | `int(11)` | NO | `0` | - |
| `sort_no` | `int(11)` | NO | `0` | - |
| `correct_memo` | `varchar(2000)` | YES | `NULL` | - |
| `tenant_id` | `bigint(20)` | NO | `0` | - |
| `creator` | `varchar(64)` | YES | `` | - |
| `create_time` | `datetime` | NO | `CURRENT_TIMESTAMP` | - |
| `updater` | `varchar(64)` | YES | `` | - |
| `update_time` | `datetime` | NO | `CURRENT_TIMESTAMP` | on update CURRENT_TIMESTAMP |
| `deleted` | `bit(1)` | NO | `b'0'` | - |

索引：
- `idx_yj_practice_exercises_category_id`：`category_id`（非唯一，BTREE）
- `idx_yj_practice_exercises_status`：`question_status`（非唯一，BTREE）
- `idx_yj_practice_exercises_type`：`question_type`（非唯一，BTREE）
- `PRIMARY`：`id`（唯一，BTREE）

## `yj_practice_exercises_answer`

| 字段 | 类型 | 可空 | 默认值 | 键/附加 |
| --- | --- | --- | --- | --- |
| `id` | `bigint(20)` | NO | `NULL` | PRI / auto_increment |
| `exercises_id` | `bigint(20)` | NO | `NULL` | MUL |
| `question_type` | `varchar(32)` | NO | `NULL` | - |
| `answer_code` | `varchar(10)` | YES | `NULL` | MUL |
| `answer_content` | `varchar(255)` | NO | `NULL` | - |
| `is_correct` | `bit(1)` | NO | `b'0'` | - |
| `sort_no` | `int(11)` | NO | `0` | - |
| `tenant_id` | `bigint(20)` | NO | `0` | - |
| `creator` | `varchar(64)` | YES | `` | - |
| `create_time` | `datetime` | NO | `CURRENT_TIMESTAMP` | - |
| `updater` | `varchar(64)` | YES | `` | - |
| `update_time` | `datetime` | NO | `CURRENT_TIMESTAMP` | on update CURRENT_TIMESTAMP |
| `deleted` | `bit(1)` | NO | `b'0'` | - |

索引：
- `idx_yj_practice_answer_code`：`answer_code`（非唯一，BTREE）
- `idx_yj_practice_answer_exercises_id`：`exercises_id`（非唯一，BTREE）
- `PRIMARY`：`id`（唯一，BTREE）

## `yj_practice_exercises_answer_child`

| 字段 | 类型 | 可空 | 默认值 | 键/附加 |
| --- | --- | --- | --- | --- |
| `id` | `bigint(20)` | NO | `NULL` | PRI / auto_increment |
| `answer_id` | `bigint(20)` | NO | `NULL` | MUL |
| `question_type` | `varchar(32)` | NO | `NULL` | - |
| `answer_content` | `varchar(255)` | NO | `NULL` | - |
| `is_correct` | `bit(1)` | NO | `b'0'` | - |
| `tenant_id` | `bigint(20)` | NO | `0` | - |
| `creator` | `varchar(64)` | YES | `` | - |
| `create_time` | `datetime` | NO | `CURRENT_TIMESTAMP` | - |
| `updater` | `varchar(64)` | YES | `` | - |
| `update_time` | `datetime` | NO | `CURRENT_TIMESTAMP` | on update CURRENT_TIMESTAMP |
| `deleted` | `bit(1)` | NO | `b'0'` | - |

索引：
- `idx_yj_practice_answer_child_answer_id`：`answer_id`（非唯一，BTREE）
- `PRIMARY`：`id`（唯一，BTREE）

## 关联与边界

- 分类边界：`yj_practice_exercises.category_id = 13`；分类表主键唯一定位，分类为 tenant `1`、未删除、自测类。
- 逻辑关系：`yj_practice_exercises_answer.exercises_id -> yj_practice_exercises.id`。
- 逻辑关系：`yj_practice_exercises_answer_child.answer_id -> yj_practice_exercises_answer.id`。
- 物理外键：信息架构查询结果为 `0` 条；当前三表未声明物理外键，必须用逻辑关联校验孤儿记录。
- 排序：题目与答案均使用 `sort_no`；子答案表没有独立排序字段，只能按主键/业务约定稳定排序。
- 公共边界：三表均含 `tenant_id`、`deleted`、创建/更新时间与创建/更新人。
- 标准答案：`is_correct` 全部为 `0` 是用户确认的预期规则，不属于缺失；不得补造。
