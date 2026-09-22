# AC-CS-104 所选学员真实会话建立与复用接口契约

- 类型：技术-接口级
- 正式入口：企业端全局审核通过学员列表的分页 UI 与 `pageNo`、`pageSize=50` 请求、列表点击上下文、会话页初始化、已有会话关联、历史 GET、显式 start/create、消息发送与 WS 组成的真实调用链，以及学员端既有 `/app-api/yj/customer-service/**` 客服调用链。
- 支撑的业务结果：教员通过 `pageSize=50` 分页查看并联系所有符合既有审核通过条件的学员，包括账号 `tenantId=null` 的未入组织学员；全局可见不要求一次自动加载全部。有会话时复用真实 conversation，无会话时先进入空态并在首次发送前建立真实会话；学员端原能力保持兼容。
- 技术边界：列表、空态、已有会话关联、历史 GET、发送和 WS 均不得依赖教员或学员账号 tenant 是否存在，也不得以 `tenant_id` 做可见或权限过滤。历史 GET 不得隐式 start/create 或创建新 session；对 `conversationId + studentId` 已校验的既有 session，允许沿用既有 `bindSessionReceiver` 绑定当前教员接收方，以保持 WebSocket 实时收件，该绑定不属于隐式建会话。已有会话直接使用真实 `conversationId` 并沿用实际非空持久 `tenant_id`；账号 `tenantId=null` 的无会话学员首次发送前同样显式 start/create，以后端真实 `conversationId` 执行发送并供后续历史与 WS 使用。未入组织首次创建复用学员端既有规范化规则，将账号空 tenant 持久化为 `tenant_id=1`，不传播空值，也不新增或臆造其他默认 tenant。禁止 synthetic / 空 / default ID；企业端修复不得改变学员端既有接口语义。
- 通过条件：tenant 有值和 `null` 的审核通过学员都可经正式分页 UI 浏览并进入；101 名可区分学员在 `pageSize=50` 下形成 3 页，前后页依次请求 `pageNo=1/2/3`，首页禁用上一页、末页禁用下一页，响应只替换当前页而不累计成一次全量列表，往返翻页不混数据。任意页点击携带当前行真实 `studentId` 与可空真实 `conversationId`。有会话分支始终使用同一真实 conversation；历史 GET 可在双键校验后绑定当前教员接收方但不得增加 session。无会话分支仅在显式 start/create 返回真实 ID 后发送。
- 证据承接方式：测试环境 `pageSize=50` 与 `pageNo=1/2/3` 请求 / 响应矩阵、首中末页控件状态、三页行集合和往返翻页结果、任意页点击参数、真实调用链回执、关键请求 / 响应脱敏摘要与 `061-验收标准/03-测试验证/DEV-028/` 独立验收记录。
