# AC-ADMIN-WRONG-201 后台错题管理数据关联、题干回填与排序规则

- 类型：技术-数据级
- 关联任务：`DEV-011`
- 正式入口：`UserPracticeExercisesRecordServiceImpl` 的 SQL 组装、`practice-record-detail` 列表查询、`yj_user_practice_exercises_record`、`yj_user_practice_exercises_record_detail`、`yj_practice_catalog_batch`、`yj_practice_category`、`yj_practice_exercises_batch`、`yj_practice_exercises`。
- 支撑结果：列表和 `COUNT` 共用同一关联、同一过滤、同一分页口径；分类名和题干展示都来自真实关联数据。
- 数据边界：`练习记录` 展示值按 `r.create_time + ' + ' + 分类名称` 生成；分类名优先取批次快照，再回退分类主表，并显式处理 collation 为 `utf8mb4_unicode_ci`；`题目题干` 通过 `detail.exercises_id -> yj_practice_exercises_batch.id -> yj_practice_exercises.id -> question_stem` 取得当前主表题干；`record_id` / `exercises_id` 保留内部关联用途，不再作为列表列或查询条件；`is_correct` 采用真实布尔/bit 值，查询端按是/否下拉映射，页面首次进入与重置时默认 `false` 仅承接错题明细，“不限”不生成过滤条件且不额外注入默认 `false` 条件。
- 通过条件：相同条件下 `COUNT` 与列表行数一致；分类筛选支持模糊匹配且不再触发 utf8mb4 排序错误；历史题干若已变更，以题目主表当前值为准，且该风险在结果里明确写出；页面首次进入与重置默认只看 `false` 集合，“不限”查询不改变现有结果集且不再强制补默认 `false`。
- 风险说明：本次不承诺作答时快照题干回显，页面取的是题目主表当前值，题目后改会同步影响后台显示。
- 证据承接方式：SQL 组装与字段对照回写 `061-验收标准/03-测试验证/DEV-011/`。
