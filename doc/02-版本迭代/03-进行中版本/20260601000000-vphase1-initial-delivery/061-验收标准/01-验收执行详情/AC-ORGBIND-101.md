# AC-ORGBIND-101 组织绑定提交接口顺序

- 类型：技术-接口级
- 正式入口：`POST /app-api/yj/customer-info/save`、`POST /app-api/yj/student-audit/submit`
- 业务支撑：确认提交时先保存真实姓名、身份证号、性别，再提交组织申请。
- 技术边界：取消或必填未通过时两条接口都不得触发；`saveCustomerInfo` 失败时不得继续调用 `submitStudentAudit`；提交用户必须是当前登录学员。
- 通过条件：接口调用顺序、请求体字段和失败阻断逻辑与现有 `customerAuth.ts`、`FrontCustomerController`、`CustomerServiceImpl` 契约一致。
- 证据承接方式：以 `src/services/customerAuth.ts`、`FrontCustomerController.java` 与后续正式测试结果为准。
