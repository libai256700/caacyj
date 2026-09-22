# TC-UI-ASSESSMENT-RETURN-001 自测报告返回首页

## 1. 测试层级

`交互级 / 代码契约复核`

## 2. 对应验收项

- 验收项 ID：`AC-ASSESSMENT-AI-001`
- 正式验收入口：`../../01-验收执行详情/AC-ASSESSMENT-AI-001.md`

## 3. 验收范围

- 首页“查看报告”使用最新自测记录 ID 进入 `/pages/center/self-test-report`。
- 答题提交完成后使用最新自测记录 ID 进入同一报告页。
- 报告页只保留一个主操作按钮，文案为“返回首页”，点击调用 `goHome`。
- 顶部返回失败时复用 `goHome`。
- `goHome` 使用 `uni.reLaunch({ url: '/pages/home' })`，不进入 AI 中心。

## 4. 独立复跑结果

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 实施差异与唯一页面 | 通过 | 应用实现只修改正式 `src/pages/center/self-test-report.vue`；仓库内仅一份同名正式页面 |
| 首页入口 | 通过 | `src/pages/home.vue` 读取 `records[0]?.id` 并拼接报告页 `id` 参数 |
| 答题提交入口 | 通过 | `src/pages/practice/self-test-answer.vue` 读取最新记录 ID 并 `redirectTo` 报告页 |
| 返回首页契约脚本 | 通过 | `check-self-test-report-return-home.mjs` 退出码 `0`，输出 `self-test report return-home contract passed` |
| 类型检查 | 通过 | `npm run type-check` 退出码 `0` |
| H5 构建 | 通过 | `npm run build:h5` 退出码 `0`，输出 `DONE Build complete.` |
| 差异格式 | 通过 | `git diff --check` 退出码 `0`，仅有换行格式提示 |
| 三方包边界 | 通过 | `uni_modules/**` 工作区与暂存区变更数为 `0` |
| Playwright 两入口与按钮点击 | 未执行 | 本机 `5173` 服务可用，但现有浏览器未开放 CDP，且没有可直接复用的 Playwright 合法登录上下文；未伪造账号、Token 或报告数据 |

## 5. 契约脚本有效性

脚本直接读取正式 Vue 源码并执行非空断言，覆盖：

- `report-action` 按钮数量严格等于 `1`。
- 按钮 `@tap="goHome"` 且显示“返回首页”。
- 旧文案“返回中心继续对话”和旧函数 `goCenter` 均为零命中。
- `goBack` 的 `navigateBack` 失败回调为 `goHome`。
- `goHome` 调用 `uni.reLaunch`，目标严格为 `/pages/home`。

## 6. 结论

`PARTIAL`：源码、入口、契约、类型检查、构建和边界审计全部通过，未发现实现缺陷；因缺少可复用合法登录上下文，真实浏览器中的两个入口点击和返回按钮点击尚未执行，不能将交互级验收判定为全部通过。
