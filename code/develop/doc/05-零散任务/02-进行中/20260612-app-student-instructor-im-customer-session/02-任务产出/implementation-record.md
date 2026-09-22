# 实现记录

## 1. 后端新增 APP 客服接口

新增文件：

- `yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/controller/FrontCustomerServiceSessionController.java`
- `yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/controller/vo/AppCustomerServiceMessageRespVO.java`
- `yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/controller/vo/AppCustomerServiceSendReqVO.java`
- `yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/controller/vo/AppCustomerServiceSessionRespVO.java`
- `yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/service/FrontCustomerServiceSessionService.java`
- `yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/customer/service/FrontCustomerServiceSessionServiceImpl.java`

接口：

- `GET /app-api/yj/customer-service/session`
- `GET /app-api/yj/customer-service/messages`
- `POST /app-api/yj/customer-service/messages`

实现要点：

- 使用 `AppMobileAuthUtils.requireStudentLoginUser()` 获取当前 APP 学员。
- 当前客服账号约定为 `PLATFORM_SERVICE_USER_ID = 0`。
- 无会话时自动创建 `yj_session_message`。
- 文本发送写入 `yj_message_info`，并更新 `yj_session_message.last_message_content` 与 `last_message_time`。

## 2. APP 接口封装

新增文件：

- `yunjikeji/src/services/customerService.ts`

能力：

- 复用 `getApiBaseUrl()`、`buildAuthHeader()`、`handleUnauthorizedResponse()`。
- 封装客服会话、消息列表、文本发送三个入口。
- 统一处理超时、未登录和后端错误消息。

## 3. APP 客服中心列表

修改文件：

- `yunjikeji/src/pages/service/customer-service.vue`

变更：

- 移除本地 storage 最近消息读取。
- 非企业身份进入客服中心时调用真实 `fetchCustomerServiceSession()`。
- 最近消息、时间和未读数来自后端会话。
- 加入加载失败提示，点击可重试。

## 4. APP 客服聊天页

修改文件：

- `yunjikeji/src/pages/service/customer-service-chat.vue`

变更：

- 移除本地种子消息和 `uni.setStorageSync()` 假会话。
- 页面显示时调用 `fetchCustomerServiceSession()` 初始化并加载消息。
- 发送文本调用 `sendCustomerServiceTextMessage()`，成功后刷新消息列表。
- 图片/视频按钮改为明确提示“接口暂未开放”，避免把本地文件伪装为真实发送。
- 增加加载、空态、错误态。

## 5. 未做事项

- 未接 WebSocket 推送；当前是进入页面加载、发送后刷新。
- 未开放图片/视频客服消息上传。
- 未把聊天页抽成通用组件；当前先完成客服会话最小闭环。
- 未修改 `uni_modules/**`。
