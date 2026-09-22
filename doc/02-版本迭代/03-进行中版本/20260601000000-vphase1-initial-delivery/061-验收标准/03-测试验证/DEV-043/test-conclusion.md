# DEV-043 测试结论

## 2026-08-10 消息推送前置验证入口与红灯确认

- 脚本入口：`DEV-043/verify_notification_contract.py`
- 语法校验命令：`python -c "import ast,pathlib; ast.parse(pathlib.Path(r'E:\huiyitechworkspace\feixingxueyuan\doc\02-版本迭代\03-进行中版本\20260601000000-vphase1-initial-delivery\061-验收标准\03-测试验证\DEV-043\verify_notification_contract.py').read_text(encoding='utf-8'))"`
- 语法校验退出码：`0`
- 红灯命令：`python E:\huiyitechworkspace\feixingxueyuan\doc\02-版本迭代\03-进行中版本\20260601000000-vphase1-initial-delivery\061-验收标准\03-测试验证\DEV-043\verify_notification_contract.py --workspace-root E:\huiyitechworkspace\feixingxueyuan --output E:\huiyitechworkspace\feixingxueyuan\doc\02-版本迭代\03-进行中版本\20260601000000-vphase1-initial-delivery\061-验收标准\03-测试验证\DEV-043\red-result.json`
- 红灯退出码：`1`
- 结构化结果：`DEV-043/red-result.json`
- 结果统计：`16` 项检查，`0` 项通过，`16` 项未通过。
- Provider 正反例验证：反例 `NoopPushProvider.java + FooBridge.java -> False`；正例 `PushProvider.java + NoopPushProvider.java + UniCloudHttpPushProvider.java -> True`。
- App 动态路径正反例验证：`${encodeURIComponent(recordId)}` 详情/read/open 完整正例 `True`；缺 read/open 反例 `False`。

### 红灯失败项摘要

- 后端父 POM 未声明 `yunjikeji-module-notification`，模块 `pom.xml` 也不存在。
- 后端 `controller/admin`、`controller/app`、`service`、`PushProvider/NoopPushProvider/UniCloudHttpPushProvider|Bridge` 目录与消息推送 API 契约均未落源码。
- 后端管理端契约缺失：`page/get/create/update/delete/publish/cancel/retry/delivery-page/statistics`。
- 后端 App 契约缺失：`devices/bind`、`devices/unbind`、`messages/page`、`messages/{id}`、`messages/unread`、`messages/{id}/read`、`messages/read-all`、`messages/{id}/open`。
- 管理平台未发现推送 API 封装与推送页面。
- 手机 App 未发现消息中心服务契约、页面注册、`clientId + onPushMessage` 生命周期、UniPush manifest 配置与 `uniCloud-aliyun/cloudfunctions/yj-push-bridge/index.js` 桥接函数。
- 仓库内未定位到 `yj_push_message`、`yj_push_recipient`、`yj_push_device`、`yj_push_delivery` 四张表。

### 误判修复证据

- Provider 判定已收紧：必须以 basename 精确命中 `PushProvider.java`，不再允许仅由 `NoopPushProvider.java`、`FooPushProvider.java` 或 `FooBridge.java` 命中通过。
- 后端路由判定已改为兼容 Spring 类级 `@RequestMapping` 与方法级 `@GetMapping/@PostMapping/...` 的组合，不再依赖完整 URL 字面量。
- 管理端页面判定已改为预设候选路径加推送特征词校验，不再允许无关 `Push` 命名文件误通过。
- 管理端前端 API 已补齐 `get/retry` 契约检查。
- App 服务契约已改为 PD 正式 REST 路径：`/messages/{id}`、`/messages/{id}/read`、`/messages/{id}/open`，不再发明 `/messages/get|read|open`。
- App 前端动态 ID 检查已兼容 `${id}` 与 `${encodeURIComponent(recordId)}` 等模板表达式，并要求动态表达式两侧的固定路径同时匹配。
- `__pycache__/verify_notification_contract.cpython-312.pyc` 已删除，`__pycache__` 目录已清空移除。

### 结论

- 本轮红灯有效，来源于真实缺失实现，不是脚本语法、路径或编码问题。
- 本轮返工已满足：`PushProvider.java` 独立校验、Admin/App 契约全覆盖、Spring 类级+方法级映射兼容、页面路径白名单校验、App 动态 ID 模板识别与清除 `__pycache__`。
- 当前允许第四次独立复验并进入 `DEV-044/045` 继续实现；实现完成后必须原命令重跑本脚本并转绿，当前不得把 `AC-PUSH-101/102/201/301` 标记为通过。
