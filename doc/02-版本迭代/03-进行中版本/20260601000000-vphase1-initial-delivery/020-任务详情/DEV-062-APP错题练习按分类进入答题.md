# DEV-062 APP错题练习按分类进入答题

## 实施标准

- 首页真实入口为 `code/develop/yunjikeji/src/pages/home.vue`；点击“错题练习 / 开始练习”且存在错题时，先导航到现有 `/pages/practice/exam-topics?mode=wrongReview`，不再以空分类直接启动错题批次；首页零错题门禁与既有提示保持不变。
- 正式分类页为 `src/pages/practice/exam-topics.vue`，卡片组件为 `src/components/PracticeTopicGrid.vue`；必须直接复用现有暖色背景、两列分类卡片、排序、编号与皮肤映射，不新建同义页面或组件，不修改 `PracticeTopicGrid.vue`。
- 分类页在 `wrongReview` 模式显示“错题练习”，继续通过 `fetchPracticeTopics('', 'wrongReview')` 读取真实启用分类；点击分类时调用现有 `startPractice(DEFAULT_PRACTICE_ID, 'wrongReview', selectedTopicId)`，并按真实返回的 `nextPage` 进入答题页。
- 进入答题页的参数至少完整承接 `id`、`sessionId`、`mode`、`topicId` 与 `topicTitle`；真实返回存在时同时承接 `recordId`、`catalogBatchId`，不得用前端假数据模拟分类过滤或错题批次。
- 后端现有错题批次服务已经按题目 `categoryId` 过滤当前用户错题；本任务不得修改 service、后端或数据库。目标分类无错题时沿用真实接口“暂无错题可练习”反馈，不伪造可练题目。
- 普通 `practice` / `chapter` 分类入口、组织绑定门禁、分类页加载态、返回分类页、答题提交与完成链路不得回归；`answer.vue` 仅允许在确有必要时补齐 `wrongReview` 模式标题，不调整答题业务。
- 应用源码白名单仅限 `src/pages/home.vue`、`src/pages/practice/exam-topics.vue`、必要时的 `src/pages/practice/answer.vue`；不得修改 `PracticeTopicGrid.vue`、`practice.ts`、后端、其他页面或 `uni_modules/**`。
- `exam-topics.vue` 已有其他任务的并行未提交改动，实施必须基于最新现场最小合并，不覆盖、不回退、不归入本任务提交。
- 正式验证至少覆盖首页到错题分类页、分类列表复用、含错题分类进入答题且请求携带目标 `topicId`、空分类反馈、返回分类页、普通逐题 / 章节练习回归及三档移动视口，并执行 `pnpm type-check`、`pnpm run build:h5`、`git diff --check`。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `00-1150-main-subagent-governance`
- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- 首页错题入口到现有分类页的导航调整。
- 分类页 `wrongReview` 模式与按分类启动真实错题批次的实现。
- `AC-WRONGCATEGORY-001`、`101`、`102`、`201` 正式验收入口。
- `061-验收标准/03-测试验证/DEV-062/` 下的正式测试资产。

## 分支安排详情

- 沿用当前版本实际分支 `feature/20260601000000-vphase1-initial-delivery`。
- 严格保护工作区既有并行改动与 `uni_modules/**`；只提交 DEV-062 白名单源码、正式计划和测试证据。

## 关联验收项

- 业务验收：`AC-WRONGCATEGORY-001`
- 技术验收：`AC-WRONGCATEGORY-101`、`AC-WRONGCATEGORY-102`
- 闭环项：`AC-WRONGCATEGORY-201`

## 任务产出 / 结果记录

- 2026-08-19 已确认真实分类页、卡片组件、前端启动 service、后端错题批次过滤和空分类反馈均已存在，无需新建页面、组件或后端能力。
- 2026-08-19 已新增 DEV-062 主计划行、任务索引、任务详情与正式验收入口。
- 2026-08-19 已完成首页错题入口改为先入 `/pages/practice/exam-topics?mode=wrongReview`，分类页支持 `wrongReview` 并按真实 `startPractice(DEFAULT_PRACTICE_ID, 'wrongReview', selectedTopicId)` 进入答题；正式测试资产已落 `061-验收标准/03-测试验证/DEV-062/`，契约脚本先红后绿通过。

## 进度总结

- 当前状态：进行中。
- 当前结论：正式计划与验收口径已建立，等待实施与独立验收。
