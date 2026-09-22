# AC-PROFILE-101 当前企业账号资料接口契约

- 类型：技术-接口级
- 正式入口：`GET /app-api/yj/company-auth/me`，使用当前企业端 `company-front` Bearer Token，无客户端 tenantId/mobile 参数。
- 支撑的业务结果：企业端“我的”页取得与当前教员一致的后台用户昵称和部门名称。
- 技术边界：入口身份来自 `yj_company_account_front`；服务端从当前账号取得已绑定 `tenantId` 与登录手机号，再在该租户上下文唯一关联后台用户。不得复用 `/post-codes` 跨租户候选 `first` 逻辑。
- 通过条件：样本账号响应 `nickname=教员1`、`deptName=教学部`，既有响应字段兼容；无后台用户、无 `deptId` 或部门不存在时对应新字段受控为 `null`，接口不串租户、不改账号绑定。
- 证据承接方式：Controller/Service 契约测试、真实接口响应摘要和 `061-验收标准/03-测试验证/DEV-083/` 独立验收记录。
