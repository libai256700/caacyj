# AC-HOMEPOS-101 最小实现边界与质量门禁

- 类型：技术-代码级
- 正式入口：`code/develop/yunjikeji/src/pages/home.vue`。
- 支撑结果：顶部展示精简、位置恢复和指定导航成立。
- 技术边界：只允许目标 DOM/死代码、位置恢复值和客服导航分支发生差异；暖色背景与其他页面/服务不得变化。
- 通过条件：类型检查、H5 构建、Chrome DevTools、Playwright 三档、导航验证和 `git diff --check` 全部通过，`uni_modules/**` 无本任务差异。
- 证据承接：`061-验收标准/03-测试验证/DEV-035/`。
