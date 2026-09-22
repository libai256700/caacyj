# AC-PAGEROUTE-102 自动化覆盖与质量门禁

- 类型：技术-代码级
- 正式入口：`061-验收标准/03-测试验证/DEV-040/`。
- 支撑结果：自动验证冷启动、登录分流、新首页三入口、测评/答题链路、退出与控件条件未回退。
- 技术边界：Playwright 可使用确定性会话/接口夹具，但不得写入应用或冒充真实账号联调。
- 通过条件：目标 Playwright 场景、`pnpm type-check`、`pnpm run build:h5`、`git diff --check`、白名单和条件表达式审计全部通过。
- 证据承接：测试用例、脚本、结构化结果、命令结果和测试结论。

## 2026-07-18 独立验收结果

- 状态：待验收。
- 历史 Playwright：曾检出未登录首页内容闪现；当前源码已加入 `homeReady` 根 `v-if`，历史失败证据保留，不冒充修复后结果。
- 2026-07-19 质量命令：`pnpm type-check` exit `0`；后端 Maven 39/39 模块 `BUILD SUCCESS`；`git diff --check` exit `0`。
- 待复验：操作系统级 esbuild 执行故障导致原 binary 与 Temp 副本执行 `--version` 均超时，未生成最新 H5 产物；本轮按止损规则不重复 H5 构建，Playwright 同步待环境恢复后执行。
