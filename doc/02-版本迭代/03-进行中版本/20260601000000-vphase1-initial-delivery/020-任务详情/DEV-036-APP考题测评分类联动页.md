# DEV-036 APP考题测评分类联动页

## 实施标准

- 新增独立 `/pages/practice/exam-assessment` 页面，首页“考题测评”改为进入该页面；旧 `/pages/practice` 和 `/pages/practice/start` 继续保留。
- 页面上部复刻参考图一的应用内结构：返回按钮、居中“考题测评”标题、右侧操作位、浅蓝背景和紧凑横向分类标签；不得重复绘制系统时间、信号或电量。
- 分类标签必须来自 `fetchPracticeStartPage(undefined, 'standard')` 的真实 `PracticeTopic[]`，过滤明确停用分类；显示真实题型分类名称，不使用 `fallbackPracticeTopics` 或其他硬编码分类冒充接口数据。
- 分类标签单行横向滚动，支持左滑和右滑；默认选中首个可用分类，选中态为蓝色块并带参考图下方指示尖角，切换后自动保证选中项可见。
- 选中分类后使用 `fieldType || id` 作为 `topicId` 重新调用 `fetchPracticeStartPage(topicId, 'standard')`，刷新下方练习确认信息；快速连续切换必须通过请求版本号防止旧响应覆盖新选择。
- 下方确认信息卡与图四一致，并从现有 `/pages/practice/start` 抽取共享正式组件；显示题目分类、题目编号、题量、总分、答题时间、阅卷方式以及“开始练习 / 错题复练”。旧开始页与新页面共用该组件，不维护两套展示结构。
- “开始练习”继续调用真实 `startPractice(id, 'standard', topicId)` 并进入答题页；“错题复练”按当前选中分类重新查询 `wrongReview`，无错题提示，有错题时启动真实错题复练答题链路。
- 加载、空数据、失败状态必须使用项目现有状态组件或等效正式状态；加载期间防止重复启动，接口为空不得显示假分类或假题量。
- 本轮不修改后端、不修改 `src/services/practice.ts`、`src/services/assessment.ts` 或当前已有用户改动的其他业务文件，不修改 `uni_modules/**`。
- `360x800`、`390x844`、`430x932` 三档视口无横向页面溢出、重叠、裁切或固定按钮遮挡，视觉门禁为 `95/pass`。

## 对应技能

- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`
- `visual-verdict`

## 交付物

- 独立考题测评页面与页面注册。
- 练习确认信息共享组件及旧开始页复用改造。
- 首页考题测评入口切换。
- 三档截图、分类滑动/联动、真实动作与质量命令证据。

## 分支安排详情

- 沿用 `feature/20260601000000-vphase1-initial-delivery`。
- 应用源码白名单：`src/pages/home.vue`、`src/pages.json`、`src/pages/practice/exam-assessment.vue`、`src/components/PracticeStartSummary.vue`、`src/pages/practice/start.vue`。
- 禁止修改后端、services、center、参考首页、登录页和 `uni_modules/**`。

## 关联验收项

- 业务验收：`AC-EXAMASSESS-001` 至 `AC-EXAMASSESS-005`
- 技术验收：`AC-EXAMASSESS-101`、`AC-EXAMASSESS-102`
- 闭环项：`AC-EXAMASSESS-201`

## 任务产出 / 结果记录

- 2026-07-18 用户提供阶段刷题页、练习确认页、题型分类和确认卡参考图，要求完整还原上部结构、替换为真实题型分类横滑联动，并复用原确认信息样式和真实练习链路。
- 实施前盘点确认：现有 `GET /app-api/yj/practices/current`、`fetchPracticeStartPage`、`startPractice` 和 `/pages/practice/start` 已覆盖本轮真实数据与动作，不需要后端变更。
- 首轮功能验收：三档、双向滑动、分类联动、竞态、四态、标准/错题动作和旧页共享组件均通过；专用 Chrome 无有效登录态，真实接口返回业务 `401 账号未登录`，已记录为真实账号端到端待复验。
- 首轮视觉证据人工复核未通过：新页面在分类标签外增加了参考图不存在的白色“题型分类”面板，并在分类栏与图四确认卡之间增加了“确认练习信息”标题和说明，不符合“上部图一 + 下部图四”的直接组合要求；`AC-EXAMASSESS-001`、`AC-EXAMASSESS-004` 退回视觉返工。
- 第一轮视觉返工复测：分类 heading 和白色外壳已正确删除，但父页面 scoped CSS 未穿透共享组件，`.practice-start__intro` 仍为 `display:block`、实际高度约 `94.6px`，swiper 到卡体间距约 `108.1px`；视觉 `84/revise`，`AC-EXAMASSESS-001/004/101` 仍未通过。下一次返工必须使用共享组件正式属性控制介绍区显示，不得继续依赖样式穿透。
- 二次返工使用共享组件 `showIntro` 正式属性闭环：新页显式关闭后 intro DOM/text 均为 `0`，旧开始页默认开启且 DOM 为 `1`；swiper 到确认卡间距为 `3.83~4.58px`。
- 最终独立验收 `97/pass`：三档、五分类左右真实 touch、请求参数联动、过期响应保护、loading/empty/error/ready、标准/错题动作防重、无错题不启动和旧页共享卡回归全部通过。
- 质量命令 `pnpm type-check`、`pnpm run build:h5`、Playwright 与 `git diff --check` 均退出码 `0`；证据位于 `061-验收标准/03-测试验证/DEV-036/`。
- 环境关注：专用 Chrome 的真实 current 请求携带 Bearer Token 发出，但登录凭证失效，服务端返回业务 `401 账号未登录`；前端接口契约与异常处理已验证，真实有效账号端到端链路等待用户登录后复验。
- 提交与推送：功能、正式验收资产和测试证据提交 `2ec70263` 已推送到 `origin/feature/20260601000000-vphase1-initial-delivery`；提交白名单与禁改目录检查通过。

## 进度总结

- 当前状态：已完成。
- 当前结论：`AC-EXAMASSESS-001` 至 `AC-EXAMASSESS-201` 全部完成，无未关闭前端缺陷；真实有效账号端到端接口联动继续列为用户复验关注项，不计作已通过。
