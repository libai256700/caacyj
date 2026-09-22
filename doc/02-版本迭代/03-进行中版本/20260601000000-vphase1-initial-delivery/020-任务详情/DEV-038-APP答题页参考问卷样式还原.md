# DEV-038 APP答题页参考问卷样式还原

## 实施标准

- 仅修改 `code/develop/yunjikeji/src/pages/practice/answer.vue`，并新增原创透明人物地图插画 `code/develop/yunjikeji/src/static/practice-answer/person-map.svg`。
- 页面背景为浅黄绿到薄荷青的纵向柔和渐变；顶部仅返回箭头、动态题号与细蓝进度线；题卡采用约 90% 宽白色主卡与下移叠层，人物地图插画位于题卡上方。
- 单选单列且点击即提交；多选保持双列稳定网格并显式提交；文本题非空提交；选中、正确、错误、禁用、解析与 AI 深度解答均由真实组件状态驱动。
- 保留 `fetchPracticeQuestion`、`submitPracticeAnswer`、`completePractice`、提交防重、答题快照、答错后下一题、答对自动下一题、完成练习等现有逻辑。
- 题号与总数使用 `currentIndex + 1` 和 `totalQuestions`；普通题与末题按钮语义按真实状态变化，不硬编码固定进度。
- 不修改 services、backend、auth、center、首页、登录页、锁文件或 `uni_modules/**`；不得使用参考图裁切、假业务结果或源码测试开关。
- 执行 `pnpm type-check`、`pnpm run build:h5`、`git diff --check`，并用 Playwright 在 `360x800`、`390x844`、`430x932` 验证单选、多选、末题、错误解析与溢出；视觉判定达到 `90/pass`。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`
- `visual-verdict`

## 交付物

- 高保真答题页与原创人物地图插画。
- `AC-ANSWERUI-001`、`AC-ANSWERUI-002`、`AC-ANSWERUI-003`、`AC-ANSWERUI-101`、`AC-ANSWERUI-102`、`AC-ANSWERUI-201` 正式验收入口。
- `061-验收标准/03-测试验证/DEV-038/` 下的 Playwright 脚本、三档截图、交互结果、命令结果和 visual-verdict JSON。

## 分支安排详情

- 沿用当前版本实际分支。
- 应用源码白名单仅限 `code/develop/yunjikeji/src/pages/practice/answer.vue` 与 `code/develop/yunjikeji/src/static/practice-answer/person-map.svg`。
- 功能与证据提交 `39035c61` 已推送到 `origin/feature/20260601000000-vphase1-initial-delivery`。

## 关联验收项

- 业务验收：`AC-ANSWERUI-001`、`AC-ANSWERUI-002`、`AC-ANSWERUI-003`
- 技术验收：`AC-ANSWERUI-101`、`AC-ANSWERUI-102`
- 闭环项：`AC-ANSWERUI-201`

## 任务产出 / 结果记录

- 2026-07-18 已建立 DEV-038 主计划、任务详情、索引及正式验收入口。
- 2026-07-18 已完成 `answer.vue` 高保真结构与样式改造并新增原创 `person-map.svg`；真实拉题、提交、防重、快照、结果解析、AI 入口、自动下一题和完成跳转保持现状。
- 2026-07-18 Playwright 三档视口、单选、多选、末题和错误解析全部通过，共生成 12 张截图与 12 条交互结果；`visual-verdict=94/pass`。
- `pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均 exit `0`；证据位于 `061-验收标准/03-测试验证/DEV-038/`。
- 当前基线没有名为 `completePractice` 的服务导出或页面调用，完成态继续沿用 `completed=true` 后返回练习页的既有机制，未新增或猜测服务契约。
- 2026-07-18 独立验收通过：三档 Playwright 共 15 张截图，单选/多选/文本/末题/错误解析、双击防重、长内容滚动与 SVG 像素检查全部通过，390 单选与多选均为 `95/pass`。
- 2026-07-18 功能与证据提交 `39035c61` 已推送远程，`AC-ANSWERUI-201` 提交闭环完成。

## 进度总结

- 当前状态：已完成。
- 当前结论：`AC-ANSWERUI-001` 至 `AC-ANSWERUI-201` 全部通过；功能与证据提交 `39035c61` 已推送，DEV-038 完成闭环。
