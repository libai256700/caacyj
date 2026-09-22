# TC-CODE-PUSH-001 消息推送源码与API契约红灯

## 1. 测试层级

`代码级`

## 2. 对应验收项

- 验收项 ID：`AC-PUSH-101`、`AC-PUSH-102`、`AC-PUSH-201`、`AC-PUSH-301`
- 正式验收入口：`../../00-验收标准索引.md`

## 3. 前置条件

- 环境前置：本地可执行 `python`。
- 账号前置：无；本用例只做源码与契约红灯验证，不冒充联调。
- 数据前置：工作区根为 `E:\huiyitechworkspace\feixingxueyuan`，程序设计以 `040-程序设计/[程序设计]PD-042-20260809-Story-042-消息推送与消息中心.md` 为准。

## 4. 测试数据

```json
{
  "workspaceRoot": "E:\\huiyitechworkspace\\feixingxueyuan",
  "output": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\02-版本迭代\\03-进行中版本\\20260601000000-vphase1-initial-delivery\\061-验收标准\\03-测试验证\\DEV-043\\red-result.json"
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 使用 `ast.parse` 解析 `DEV-043/verify_notification_contract.py` | 语法检查通过，退出码 `0`，且不生成 `.pyc` |
| 2 | 在临时目录构造 App 动态路径正反例 | `${encodeURIComponent(recordId)}` 详情/read/open 正例通过，缺 read/open 反例失败 |
| 3 | 执行 `python DEV-043/verify_notification_contract.py --workspace-root E:\huiyitechworkspace\feixingxueyuan --output DEV-043/red-result.json` | 脚本可运行并输出结构化结果 |
| 4 | 检查退出码与 `red-result.json` | 当前真实缺失实现时退出码 `1`，且失败项准确指向后端模块、管理端、App 和 SQL 缺失 |

## 6. 期望结果

- 红灯来源于真实实现缺失，不允许使用硬编码失败。
- Provider 口径固定为 `PushProvider`、`NoopPushProvider`、`UniCloudHttpPushProvider/Bridge` 与 App 仓 UniCloud 云函数桥接，不期待虚构 Java UniPush SDK。
- Provider 文件条件必须使用 basename 精确等于 `PushProvider.java`、`NoopPushProvider.java`、`UniCloudHttpPushProvider.java`；`NoopPushProvider.java + FooBridge.java` 反例必须失败。
- 后端契约检查必须兼容 Spring `@RequestMapping` 类级前缀与方法级 `@GetMapping/@PostMapping/...` 组合。
- 管理页面检查只允许命中预设候选路径和明确推送特征，不允许由无关 `Push` 命名文件误通过。
- 管理平台前端 API 契约必须覆盖 `page/get/create/update/delete/publish/cancel/retry/delivery-page/statistics`。
- App 服务契约必须对齐 PD 正式 REST 路径：`/messages/{id}`、`/messages/{id}/read`、`/messages/{id}/open`，并保留 `page/unread/read-all`、`bind/unbind`。
- App 前端允许用 `${id}` 或 `${encodeURIComponent(recordId)}` 实现动态 ID；检查必须识别模板表达式，并保留路径前后缀约束。
- 失败项至少覆盖 `AC-PUSH-101`、`AC-PUSH-102`、`AC-PUSH-201`、`AC-PUSH-301`。
- 脚本在实现完成后可原命令重跑转绿。

## 7. 脚本入口

- 自动化脚本：`DEV-043/verify_notification_contract.py`
- 依赖命令：`python -c "import ast; ..."`、`python verify_notification_contract.py --workspace-root ... --output ...`
- 结果输出位置：`DEV-043/red-result.json`

## 8. 失败判定

- `ast.parse` 非 `0`，判定为脚本资产不合格。
- 契约脚本退出码不是 `1` 且没有真实通过证据，判定为红灯门禁失真。
- `PushProvider.java` 缺失时，不能仅因存在 `NoopPushProvider.java` 而判定 Provider 检查通过。
- 失败项如果只反映脚本路径、编码或语法问题，判定为无效红灯。
