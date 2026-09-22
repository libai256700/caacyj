# 非目标分类只读基线

- 采集时间：`2026-08-18T12:34:35+08:00`
- 数据库口径：当前运行程序实际连接的 `yunjikeji`；端点 `114.111.30.111:13306`
- 目标边界：排除 `category_id = 13` 的题目主键，并从答案、子答案中递归排除其关联主键。
- 摘要算法：每表按 `id` 排序，对全部持久化字段规范化为 JSON 后计算 SHA-256；后续执行前后用同一算法复验，应保持行数和摘要完全一致。

| 表 | 非目标行数 | 最小ID | 最大ID | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| `yj_practice_exercises` | 1535 | 5063 | 6597 | `02fa3673246d9bf22c0616c39500cbed0439da79a863bbf9f945ff9c1c7d984b` |
| `yj_practice_exercises_answer` | 4630 | 35005 | 39634 | `d1d6f71a0ea3dd8e553735facc0ffda97c62bca28644158a8f18ddeae4f190b8` |
| `yj_practice_exercises_answer_child` | 0 | - | - | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |

注意：这是采集时点基线，不是变更执行授权；本轮未执行任何写操作。
