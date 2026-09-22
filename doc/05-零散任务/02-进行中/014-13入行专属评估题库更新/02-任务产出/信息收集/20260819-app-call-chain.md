# 自我测评 App 调用链与落表诊断

## 1. 结论

1. 截图对应移动端 `pages/practice/self-test-answer`。首页不传任何分类参数，页面内部固定以 `practiceId=uav-basic-001`、`mode=standard`、`topicId=assessment` 启动测评。
2. 当前后端把 `standard` 归一成普通练习模式，并委托 `FrontPracticeBatchService.startPracticeMode`。批次服务的 topic 映射没有 `assessment`，分类查询又固定 `catalog_type=0`；因此分类 13（`catalog_type=1`）必然无法命中，随后代码静默回退到普通练习分类的第一项。这是截图出现 59 道普通练习旧题的直接代码级原因。
3. 截图中的“入行专属评估”不是接口返回的分类名，而是页面 CSS `content` 硬编码；因此标题正确不能证明实际选中了分类 13。
4. `yj_practice_setp` 当前只在管理端自测题查询中通过 `yj_practice_exercises.step_id` 左连接读取。App 启动、批次生成、题目响应和页面模板均未读取、返回或渲染步骤，因此六步内容不会显示。
5. 自我测评不是只保存到一张表：题库配置、开始测评时的批次快照、用户作答记录、AI 报告分别使用不同表，见第 4 节。

上述分类缺陷已同时在当前工作区和 `HEAD` 提交版本中复核，不是本轮其他并行改动新引入。

## 2. 最短调用链

### 2.1 页面到接口

1. 首页入口：`code/develop/yunjikeji/src/pages/home.vue:16` 直接跳转 `/pages/practice/self-test-answer`，没有 query 分类参数。
2. 页面加载：`self-test-answer.vue:140-148` 调用 `fetchAssessmentQuestions()`；题目总数直接取返回数组长度，顶部 `1/59` 来自 `questions.length`（`:9`）。
3. 测评参数：`assessment.ts:80-83` 固定 `uav-basic-001`、`assessment`、`standard`；`:237-260` 先启动会话，再按接口返回 `totalQuestions` 逐题拉取。
4. HTTP 请求：`practice.ts:880-885` 请求 `POST /app-api/yj/practices/uav-basic-001/start?mode=standard&topicId=assessment`；`:946-956` 请求会话题目；`:969-986` 提交答案。
5. Controller：`FrontPracticeController.java:87-94` 进入 `FrontPracticeService.startPractice`；`:130-147` 分别进入取题和答题方法。

### 2.2 分类选择错误

1. `FrontPracticeServiceImpl.java:354-374` 将 `standard` 归一为普通 `PRACTICE`，随后调用批次服务；`:417-420` 是具体归一逻辑。
2. `FrontPracticeBatchService.java:109-120` 调用 `resolveSelectedPracticeCategory(topicId)` 并按返回分类取题。
3. `FrontPracticeBatchUtils.java:41-54` 的 topic 映射没有 `assessment`，所以标准化后仍是字符串 `assessment`。
4. `FrontPracticeBatchService.java:938-955` 查询分类时强制 `catalog_type=0`，而正式快照 `current-target-snapshot.json:13-24` 证明分类 13 是 `catalog_type=1`、名称“入行专属评估”。两者不可能匹配。
5. 匹配为空后，`FrontPracticeBatchService.java:792-804` 回退到 `listPracticeCategories()` 第一项；该列表在 `:931-935` 同样固定 `catalog_type=0` 并按 `sort_no,id` 排序。
6. 最终 `:884-895` 只按回退分类 ID、启用状态、`sort_no,id` 取题。截图的“无人机的英文缩写是”是普通无人机题库题，现象与该回退路径一致。
7. 页面显示的“入行专属评估”来自 `self-test-answer.vue:445-456` 的 CSS 伪元素硬编码，不来自后端分类字段。

运行态边界：以上足以证明当前代码不会选择分类 13。截图中实际回退的普通分类主键，以及 59 题是否来自新建批次或未完成批次恢复，仍需对截图账号的最新 `yj_practice_catalog_batch` 做只读核对。当前工作区 `FrontPracticeBatchService.java:416-420` 会优先恢复未完成批次，`:520-553` 证明旧批次也可能继续返回旧题集合。

## 3. `yj_practice_setp` 为什么看不到

### 3.1 数据关系存在

- `PracticeExercisesDO.java:22-24` 有 `stepId` 和 `categoryId`。
- 正式结构说明 `数据库表结构说明.md:582-594` 明确 `yj_practice_exercises.step_id -> yj_practice_setp.id`。
- 管理端 `YjAdminService.java:643-648` 会返回 `step_id` 和 `step_name`；`:1135-1138` 明确左连接 `yj_practice_setp`。

### 3.2 App 链路没有消费

- App 批次服务 `FrontPracticeBatchService.java:884-895` 取题只选 `yj_practice_exercises.id`，没有 join 步骤表，也没有按 `step_id` 分组。
- 生成题目批次时 `:447-453` 只保存 `catalogBatchId`、源题 `exercisesId` 和顺序；`PracticeExercisesBatchDO.java:15-34` 没有 `stepId` 字段。
- 取题响应 `FrontPracticeBatchService.java:226-255` 只返回题型、题干、分值和选项，不返回步骤。
- 页面 `self-test-answer.vue:13-27` 只渲染题型、题干、选项和下一题按钮，不存在步骤组件。
- 对 App 目录和上述前端文件搜索 `setp/stepId/step_id/yj_practice_setp` 无命中。

所以 `yj_practice_setp` 不是“写入了但页面偶发没显示”，而是当前 App 接口契约和页面从未实现步骤消费。分类选错是本次旧题问题；步骤未接入是另一条独立缺口。

## 4. 表清单与作用

| 层次 | 表 | 当前作用与代码证据 |
| --- | --- | --- |
| 分类配置 | `yj_practice_category` | 决定题目分类；`catalog_type=0` 为练习、`1` 为自测，结构说明见 `数据库表结构说明.md:569-578`。分类 13 正式快照见 `current-target-snapshot.json:13-24`。 |
| 步骤配置 | `yj_practice_setp` | 保存步骤名称、状态、顺序；题目用 `step_id` 逻辑关联。当前仅管理端消费，App 不消费。 |
| 题目配置 | `yj_practice_exercises` | 保存题干、题型、状态、排序、`category_id`、`step_id`；DO 表名和字段见 `PracticeExercisesDO.java:10-36`。 |
| 一级选项配置 | `yj_practice_exercises_answer` | 保存题目选项、编码、内容、是否标准答案、排序；见 `PracticeExercisesAnswerDO.java:11-34`。 |
| 二级选项配置 | `yj_practice_exercises_answer_child` | 保存一级选项下的二级答案；见 `PracticeExercisesAnswerChildDO.java:11-30`。当前分类 13 正式数据为 0 条，且 App 批次服务没有读取该 Mapper。 |
| 测评批次头 | `yj_practice_catalog_batch` | 开始测评时保存用户、实际分类、会话、总题数、进度、完成态、关联记录；创建代码 `FrontPracticeBatchService.java:425-440`，DO 表名/字段 `PracticeCatalogBatchDO.java:15-53`。 |
| 本次题目集合 | `yj_practice_exercises_batch` | 保存本次批次到源题的关联和顺序；创建代码 `FrontPracticeBatchService.java:445-454`，DO `PracticeExercisesBatchDO.java:15-34`。题干仍从源题表读取，不是完整题干快照。 |
| 本次选项快照 | `yj_practice_exercises_answer_batch` | 开始时复制源选项 ID、编码、内容、正确标记、顺序；创建代码 `FrontPracticeBatchService.java:459-484`，DO `PracticeExercisesAnswerBatchDO.java:15-40`。 |
| 用户测评记录头 | `yj_user_practice_exercises_record` | 开始批次即插入，保存用户、关联批次、总分、对错数、领域；`FrontPracticeBatchService.java:489-499`，DO `UserPracticeExercisesRecordDO.java:10-32`。注意当前代码把 `category_id` 写成 `catalogBatch.id`，不是源分类 13。 |
| 用户逐题作答 | `yj_user_practice_exercises_record_detail` | 每次提交 upsert，保存 `record_id`、题目批次 ID、所选答案编码、正确答案编码、是否正确；`FrontPracticeBatchService.java:704-725`，DO `UserPracticeExercisesRecordDetailDO.java:11-32`。 |
| 错题明细 | `yj_user_practice_exercises_wrong_record_detail` | 判错时同步保存源题、所选答案、错次和时间；`FrontPracticeBatchService.java:729-756`，DO `UserPracticeExercisesWrongRecordDetailDO.java:17-42`。自测选项标准答案全空时，`:266-280` 把题判为正确，通常不会新增错题。 |
| AI 自测报告 | `yj_assessment_result` | 报告持久化 SQL 在 `FrontPracticeServiceImpl.java:1592-1633`，查询在 `:290-304`、`:326-348`。 |

## 5. 额外代码风险

1. 当前 `FrontPracticeServiceImpl.submitAnswer` 在 `:443-447` 直接委托批次服务并返回；仓内搜索显示 `enqueueAssessmentEvaluation()` 只有定义，没有调用方。因此当前工作区静态调用链会保存批次记录和逐题作答，但不会进入 `yj_assessment_result` 的报告生成/持久化逻辑。截图运行环境是否部署了同一版本，需要运行态接口与数据库确认。
2. 当前记录头的 `category_id` 实际写 `catalogBatch.id`（`FrontPracticeBatchService.java:489-504`），后续 `FrontPracticeServiceImpl.java:283-304` 却把它当 `yj_practice_category.id` 查询；这会影响记录分类名和自测记录筛选，属于与本次题目错配相关的后续风险。
3. 即使修正分类 13 选择，已存在的未完成错误批次仍可能被恢复；修复验证必须使用新账号/清理测试账号未完成批次，或明确让恢复逻辑只复用同一正确分类和正确题库版本。

## 6. 建议的下一步证据

只读核对截图账号最新一条 `yj_practice_catalog_batch` 及其 `yj_practice_exercises_batch`：确认 `category_id/category_name/total/session_id/is_completed`，再关联源题统计真实 `category_id` 和首题。该证据可直接区分“分类回退生成的新错误批次”与“恢复历史 59 题旧批次”，无需继续猜环境或改数据库。
