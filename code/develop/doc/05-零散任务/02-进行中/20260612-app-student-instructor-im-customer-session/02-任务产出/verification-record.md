# 验证记录

## 验证时间

2026-06-12

## 范围

- APP 学员客服会话页与 `src/services/customerService.ts`。
- 后端 `com.huiyitech.message` 下的 app/admin controller、service、dal。
- 管理端 UI `src/views/yj/resource/index.vue` 的客服会话回复。
- `yj_session_message`、`yj_message_info` 的现有表结构承载能力。

## 关键结论

- 学员端客服接口只走 `/app-api/yj/customer-service/**`，不再访问 `/admin-api`。
- 管理端会话列表、消息列表、客服回复走 `/admin-api/yj/customer-session/**` 与 `/admin-api/yj/customer-message/**`。
- 后端 message 实现已经迁移到 `com.huiyitech.message`，并按 `controller/service/dal` 分层。
- `tenant_id` 没有被忽略：APP 侧按学员账号绑定 tenant 获取/创建会话，管理端按 admin 登录 tenant 查询和回复。
- 学员 token 不能访问 `/admin-api`：框架按 `/admin-api` 前缀要求 `ADMIN` 用户类型，`MEMBER` 学员 token 会被拒绝；message admin service 也二次校验 `UserTypeEnum.ADMIN`。
- 现有 `yj_session_message`、`yj_message_info` 可以支撑本次文本会话功能，无需新增表。

## 命令验证

### APP 类型检查

目录：

```text
E:\huiyitechworkspace\feixingxueyuan\code\develop\yunjikeji
```

命令：

```powershell
npm run type-check
```

结果：通过。

### 后端聚焦编译

目录：

```text
E:\huiyitechworkspace\feixingxueyuan\code\develop\yunjikeji-admin-server
```

命令：使用 `javac` 参数文件聚焦编译本次相关 Java 文件：

- `com/huiyitech/message/**/*.java`
- `com/huiyitech/customer/service/CustomerServiceImpl.java`
- `cn/iocoder/yudao/server/controller/admin/yj/YjAdminController.java`
- `cn/iocoder/yudao/server/service/yj/YjAdminService.java`
- `cn/iocoder/yudao/server/service/yj/YjAdminTableRegistry.java`

结果：通过，仅提示 `YjAdminService` 使用过时 API。

### 管理端相关文件 ESLint

目录：

```text
E:\huiyitechworkspace\feixingxueyuan\code\develop\yunjikeji-admin-ui
```

命令：

```powershell
npx eslint src/views/yj/resource/index.vue src/views/yj/resource/config.ts src/api/yj/index.ts
```

结果：通过。

### 运行中接口路由探测

本机后端 `48080` 正在监听，执行未登录探测：

```powershell
Invoke-WebRequest http://localhost:48080/app-api/yj/customer-service/session
Invoke-WebRequest http://localhost:48080/app-api/yj/customer-service/messages
Invoke-WebRequest http://localhost:48080/admin-api/yj/customer-session/page?pageNo=1&pageSize=10
Invoke-WebRequest http://localhost:48080/admin-api/yj/customer-message/page?pageNo=1&pageSize=10
Invoke-WebRequest http://localhost:48080/admin-api/yj/customer-message/send
```

结果：全部进入后端安全链路，HTTP 200 + 业务码 `401`，消息为“账号未登录”；说明路由已注册，不是 404。

### H5 页面探测

使用本机 Chrome + Playwright 打开：

```text
http://localhost:5173/yunjikeji/#/pages/service/customer-service-chat?conversationId=default
```

结果：未登录状态重定向到 `/pages/auth/login`；客服相关资源加载无 500/404。页面有 1 条非客服资源 404，不影响本次接口判断。

## 已知未通过/未完成项

- `mvn -pl yunjikeji-admin-server -am -DskipTests compile` 未作为最终结论使用：全仓存在与本任务无关的 `yudao-module-ai` 编译/编码问题。
- `npm run ts:check` 在管理端全仓失败：错误集中在 BPMN、pay、system 等既有模块；本次相关文件已用 ESLint 通过。
- 未使用真实学员 token 和真实 admin token 完整发送/接收，因为当前对话未提供可用测试账号或 token。

## 风险说明

- 如果要做完整联调，需要使用同一 `tenant_id` 下的已审核学员账号和管理端账号各登录一次，验证学员发消息、管理端回复、学员刷新可见同一会话。
- 当前工作区存在多处无关脏改和未跟踪文件，本次验证未回退也未纳入本功能提交。
