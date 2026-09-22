# TC-UI-001 岗位列表交互验收

## 对应验收项

- `BA-T0022-INT-001`

## 验证目标

- 三个下拉出现在岗位列表上方。
- 选择任一筛选后会从第一页重新加载，并保留原分页 / 下拉刷新 / 触底加载模式。
- 移动端布局无明显溢出。

## 当前状态

- 未执行
- 原因：未找到可直接复用的正式测试账号 / Token 入口，也未找到可核对的岗位测试数据联动环境，未启动 Playwright。

## 证据

- 代码核对：`code/develop/yunjikeji/src/pages/jobs.vue`
- 代码核对：`code/develop/yunjikeji/src/services/jobs.ts`
- 交互验证：未执行

## 结论

- 待人工审核
