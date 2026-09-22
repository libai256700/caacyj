# AC-CS-105 所选学员真实会话、租户与消息归属

- 类型：技术-数据级
- 正式入口：测试环境中所选学员的列表关联结果、已有 conversation 或首次 start/create 结果、历史 GET、消息发送和 WS 结果。
- 支撑的业务结果：101 人三页往返切换不混入其他页学员，任意页点击后页面历史和继续发送始终承接所选行学员同一真实 conversation；账号 tenant 是否存在不限制教员可见、进入、历史或首次发送。
- 技术边界：`tenant_id` 仅为存储事实，不参与企业教员列表、空态、已有会话关联、历史或发送的可见 / 权限判断。已有 session 与消息沿用各自实际非空持久 `tenant_id`；尚未加入组织的学员首次 start/create 产生的新 session 与消息复用学员端既有规范化规则，将账号 `tenantId=null` 持久化为 `tenant_id=1`。不得把账号空值传播到 session/message，不得新增或臆造其他默认 tenant。历史 GET 不得创建新 session；对 `conversationId + studentId` 已校验的既有 session，允许 `bindSessionReceiver` 绑定当前教员接收方以保持 WebSocket 实时收件，该绑定不得被判作隐式建会话。所有归属以 `studentId + conversationId` 校验，企业端修复不得改写学员端既有会话归属。
- 通过条件：`pageSize=50` 的三页行集合与对应响应一致，不残留、重复或混入其他页学员；点击任一页行后，已有会话的历史和新增消息只归属该行真实 `studentId + conversationId`，session 数量与持久 `tenant_id` 不被改写。未入组织无会话学员首次创建规范化为 `tenant_id=1`；篡改任一键时受控拒绝，其他页或其他学员会话不增加消息。
- 证据承接方式：测试环境三页行集合与往返翻页结果、任意页点击双键矩阵、GET 前后 session 数量、已有非空持久 `tenant_id`、未入组织首次创建 `tenant_id=1`、发送前后消息集合、WS 订阅结果、学员端回归与独立验收记录。
