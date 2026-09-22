# AC-WRONGCATEGORY-102 前端复用与回归边界

- 类型：技术-代码级
- 正式入口：`src/pages/home.vue`、`src/pages/practice/exam-topics.vue`，必要时仅补 `src/pages/practice/answer.vue` 的模式标题。
- 支撑的业务结果：错题练习复用现有分类页面与卡片风格，且不会破坏普通练习、答题和并行开发现场。
- 技术边界：不修改 `PracticeTopicGrid.vue`、`practice.ts`、后端、其他页面或 `uni_modules/**`；不得覆盖 `exam-topics.vue` 事前并行改动，不新增同义页面、组件、假数据或测试开关。
- 通过条件：源码变更限定在白名单；普通 `practice/chapter` 路径回归通过；三档移动视口无溢出、遮挡或错位；`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 退出码均为 `0`。
- 证据承接方式：差异白名单检查、浏览器自动化结果、构建输出和正式测试资产。
