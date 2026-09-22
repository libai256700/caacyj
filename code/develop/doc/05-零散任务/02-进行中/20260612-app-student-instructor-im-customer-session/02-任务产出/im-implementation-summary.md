# IM 实现梳理

## 1. 当前实际入口

- APP 工程：`yunjikeji`
- APP 客服中心页：`yunjikeji/src/pages/service/customer-service.vue`
- APP 客服聊天页：`yunjikeji/src/pages/service/customer-service-chat.vue`
- APP 客服 API 封装：`yunjikeji/src/services/customerService.ts`
- APP 页面注册：`yunjikeji/src/pages.json`
- 后端 APP 客服接口：`yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/controller/FrontCustomerServiceSessionController.java`
- 后端 APP 客服服务：`yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/service/FrontCustomerServiceSessionServiceImpl.java`
- 管理端通用资源接口：`yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/cn/iocoder/yudao/server/controller/admin/yj/YjAdminController.java`
- 管理端通用资源注册：`yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/cn/iocoder/yudao/server/service/yj/YjAdminTableRegistry.java`
- 管理端客服消息发送：`yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/cn/iocoder/yudao/server/service/yj/YjAdminService.java`
- 管理前端客服资源配置：`yunjikeji-admin-ui/src/views/yj/resource/config.ts`
- 管理前端客服 API：`yunjikeji-admin-ui/src/api/yj/index.ts`
- 数据库说明：`yunjikeji-admin-server/doc/数据库表结构说明.md`
- 建表脚本：`yunjikeji-admin-server/sql/mysql/20260611_im_module_tables.sql`

## 2. 当前客服会话模型

- 会话表：`yj_session_message`
  - `id`：会话 ID
  - `session_from`：发起方，当前 APP 客服会话使用当前学员账号 ID
  - `session_to`：接收方，当前平台客服固定为 `0`
  - `last_message_content`：最近一条消息
  - `last_message_time`：最近消息时间
  - `unread_count`：管理端回复后给 APP 侧累计未读数
- 消息表：`yj_message_info`
  - `session_id`：所属会话
  - `session_from`：发送方
  - `session_to`：接收方
  - `message_type`：当前 APP 已接通 `text`
  - `content`：消息内容
  - `create_time`：发送时间

## 3. 当前客服链路

1. APP 登录后通过 `buildAuthHeader()` 带 `Authorization: Bearer <token>` 请求后端。
2. `GET /app-api/yj/customer-service/session` 获取或初始化当前学员与平台客服的会话。
3. `GET /app-api/yj/customer-service/messages` 获取当前学员客服消息。
4. `POST /app-api/yj/customer-service/messages` 发送文本消息，后端写入 `yj_message_info` 并更新 `yj_session_message` 最近消息。
5. 管理端客服资源使用 `customer-session` 和 `customer-message` 通用资源查看会话和消息。
6. 管理端回复走 `POST /yj/customer-message/send`，写入消息并更新会话最近消息与未读数。

## 4. 学员和教员 IM 怎么做

建议不要重新造一套 UI；直接把现有客服会话抽象成“会话 + 消息”模型扩展：

1. 后端新增通用私聊会话能力。
   - 可以复用 `yj_session_message` / `yj_message_info`，但要把 `session_to=0` 的客服约定扩展为真实接收方。
   - 建议新增会话类型字段，如 `session_type`：`customer_service`、`student_teacher`。
   - 明确用户身份字段：学员、教员最好不要只靠裸 ID，建议增加 `session_from_type`、`session_to_type` 或建立账号统一映射。
2. APP 新增或复用 API 封装。
   - `GET /app-api/yj/im/conversations`
   - `POST /app-api/yj/im/conversations`，参数包含目标教员/学员 ID 和身份类型。
   - `GET /app-api/yj/im/conversations/{id}/messages`
   - `POST /app-api/yj/im/conversations/{id}/messages`
3. APP 页面复用客服聊天页的 UI 结构。
   - 把当前客服聊天页抽成通用聊天组件或通用页面。
   - 通过 `conversationId`、`conversationType`、`targetUserId` 区分客服会话和学员-教员私聊。
4. 管理端继续复用通用资源页。
   - 客服会话继续走 `customer-session`。
   - 学员-教员 IM 建议新增独立资源项或专门管理页，避免和客服会话混在一起。
5. 实时性后续补齐。
   - 当前客服链路是 HTTP 拉取/发送，尚未接 WebSocket。
   - 项目里有 `yudao-spring-boot-starter-websocket` 和 `yudao-module-im`，后续可用于新消息推送；首版可以先采用进入页面拉取和发送后刷新。

## 5. 当前可直接复用与待补齐

- 可直接复用：
  - APP 聊天 UI、鉴权请求封装、客服 API 封装模式。
  - 后端会话/消息表和管理端资源页。
  - 管理端 `customer-message/send` 的消息落库思路。
- 需要补齐：
  - 学员与教员的统一身份模型。
  - 真实教员账号来源和学员-教员关系校验。
  - 会话类型、双方身份类型、按会话 ID 拉取消息的后端接口。
  - WebSocket 或轮询刷新策略。
  - 图片/视频上传和消息类型接口。
