# TC-UI-WRONG-001 错题管理默认错题筛选交互

## 1. 测试层级

`交互级`

## 2. 对应验收项

- 验收项 ID：`AC-ADMIN-WRONG-001`
- 正式验收入口：`../../01-验收执行详情/AC-ADMIN-WRONG-001.md`

## 3. 前置条件

- 环境前置：`localhost:3000/yj/practice/wrong-question` 可访问，且当前 UI 工程具备可用 Playwright 依赖
- 账号前置：如页面有登录门禁，必须使用正式测试账号或已存在登录态
- 数据前置：测试环境存在错题记录、分类与题干真实数据

## 4. 测试数据

```json
{
  "entry": "http://localhost:3000/yj/practice/wrong-question",
  "expectedVisibleValue": "否",
  "expectedRequests": [
    "首次进入 is_correct=false",
    "点击重置后 is_correct=false",
    "主动选择不限时不带 is_correct"
  ]
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 使用 Playwright 打开错题管理页 | 页面可进入并显示查询区 |
| 2 | 观察首次进入的“是否正确”默认值与首个请求 | 默认显示“否”，请求带 `is_correct=false` |
| 3 | 点击重置，再切换为“不限” | 重置恢复“否”并带 `false`；主动“不限”时请求不带该参数 |

## 6. 期望结果

- 页面首次进入和重置后默认只看错题
- 用户主动选择“不限”后，系统尊重用户选择，不再补默认 `false`

## 7. 脚本入口

- 自动化脚本：待正式运行态与 Playwright 依赖具备后补充
- 依赖命令：待补
- 结果输出位置：待补

## 8. 失败判定

- 首次进入或重置后未默认显示“否”
- 主动选择“不限”后请求仍带 `is_correct=false`
- 当前环境无 Playwright 依赖、无正式登录态或无真实数据时，不伪造通过结果
