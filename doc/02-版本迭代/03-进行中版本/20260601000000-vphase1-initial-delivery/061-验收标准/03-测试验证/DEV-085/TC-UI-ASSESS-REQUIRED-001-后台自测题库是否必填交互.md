# TC-UI-ASSESS-REQUIRED-001 后台自测题库是否必填交互

## 1. 测试层级

`交互级`

## 2. 对应验收项

- 验收项 ID：`AC-ASSESS-REQUIRED-001`、`AC-ASSESS-REQUIRED-301`
- 正式验收入口：`061-验收标准/01-验收执行详情/AC-ASSESS-REQUIRED-001.md`

## 3. 前置条件

- 环境前置：`http://127.0.0.1:3000/yj/assessment/question` 可访问。
- 账号前置：真实管理后台账号缺失；本用例使用受控权限响应，仅验证真实前端渲染与交互。
- 数据前置：两条受控题目数据分别携带 `is_required=false/true`。

## 4. 测试数据

见 `test-data.json`。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 打开题库页面 | 表格出现“是否必填”列，受控两行分别显示“否 / 是” |
| 2 | 编辑 `false` 行 | 下拉回显“否”，展开后选项只有“是 / 否” |
| 3 | 切换为“是”并保存，再次编辑 | 列表与弹窗均显示“是” |
| 4 | 切回“否”并保存 | 更新载荷显式包含 `is_required=false`，列表显示“否” |
| 5 | 打开新增弹窗 | “是否必填”默认显示“是” |
| 6 | 核对原操作 | 状态开关、题型、详情、编辑、自测答案、删除入口继续渲染 |

## 6. 期望结果

- 前端全部交互断言通过，页面无运行时异常。
- 受控接口桩结果不得替代真实后端与数据库持久化验收。

## 7. 脚本入口

- 自动化脚本：`dev085-assessment-required.spec.cjs`
- 依赖命令：`node dev085-assessment-required.spec.cjs`
- 结果输出位置：`playwright-results.json`、`assessment-required.png`

## 8. 失败判定

- 列名、行值、编辑回显、下拉选项、新增默认任一不符。
- `false` 更新载荷缺少 `is_required`，或原操作入口缺失。
