# AC-HOMETONE-101 最小代码边界与质量门禁

- 类型：技术-代码级
- 正式入口：`code/develop/yunjikeji/src/pages/home.vue`。
- 支撑结果：真实首页完成两行移除和暖色背景替换。
- 技术边界：仅允许目标 DOM、对应死代码与背景颜色字面量发生差异；参考页、登录页、旧首页、服务层和 `uni_modules/**` 不得产生本任务差异。
- 通过条件：类型检查、H5 构建、Chrome DevTools、Playwright 三档复验和 `git diff --check` 全部通过。
- 证据承接：`061-验收标准/03-测试验证/DEV-034/`。
