# AC-CS-004 企业端教员进入所选学员真实客服会话

- 类型：业务-交互级
- 业务起点：企业端教员完成登录，从底部客服进入全局所有符合既有审核通过条件的学员列表；列表包括尚未加入组织且 `tenantId=null` 的学员，不依赖教员或学员 tenant 是否存在，也不按 `tenant_id` 过滤，并包含 LEFT JOIN 到已有会话及无会话的学员。列表采用正式分页 UI，固定 `pageSize=50`，必须可继续浏览第 2 页及以后结果，不能固定停在第 1 页。
- 触发动作：以 101 名可区分审核通过学员形成 3 页，先验证上一页 / 下一页、对应 `pageNo` 与页码、首末页禁用和翻页数据隔离，再覆盖教员与学员 tenant 有值 / `null` 的组合；至少从分页结果中选择一名尚未加入组织且 `tenantId=null` 的无会话学员，并分别完成已有会话历史查看与无会话首次发送。
- 关键交互：分页切换不混入前一页数据，每页点击都携带当前行真实 `studentId` 与可空的真实 `conversationId`。已有会话学员直接进入并复用同一真实 conversation，完整加载历史并继续发送；无会话学员进入明确空态，空态、历史 GET 和首次发送不以任一端 tenant 非空为前置条件。历史 GET 不创建新 session；对 `conversationId + studentId` 已校验的既有 session，允许沿用 `bindSessionReceiver` 绑定当前教员接收方以保持 WebSocket 实时收件，该绑定不属于隐式建会话。首次发送前显式 start/create 并取得真实 `conversationId` 后再发送。
- 业务终点：已有会话不重复创建；无会话首次发送成功后，发送、后续历史和 WS 均使用新取得的真实 `conversationId`；不得出现空 / default / synthetic 会话，离开页面无加载、卸载或键盘监听错误。
- 结果承接：tenant 只作为存储事实；已有 session 与消息沿用各自实际非空持久 `tenant_id`。尚未加入组织的学员首次 start/create 复用学员端既有规范化规则，将账号 `tenantId=null` 持久化为 `tenant_id=1`，不得传播账号空值，也不得新增或臆造其他默认 tenant；上述存储值均不影响教员可见范围。所有会话以 `studentId + conversationId` 校验归属，学员端原链路保持不变。
- 核对方式：测试环境准备 101 名可区分审核通过学员，覆盖账号 tenant 有值 / `null`、有会话 / 无会话；仅使用 `chrome-devtools-mcp` 核对 `pageSize=50`、`pageNo=1/2/3`、三页行集合、首页 / 末页禁用、往返翻页、任意页点击参数、GET 前后 session 数量、真实 `conversationId`、tenant 存储值、历史与 WS 结果。
