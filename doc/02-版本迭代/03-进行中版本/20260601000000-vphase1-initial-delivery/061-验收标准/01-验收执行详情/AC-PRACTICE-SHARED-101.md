# AC-PRACTICE-SHARED-101 既有后台与 APP 接口契约

- 类型：技术-接口级
- 正式入口：`/admin-api/practice/practice-category/**`、`practice-exercises-answer/**`、`practice-exercises-answer-child/**`、`user-practice-exercises-record/**`，以及 `/app-api/yj/practices/**` 和兼容启动入口。
- 支撑结果：既有接口在不同租户上下文使用相同考题整体数据，前端无需新增或传递业务租户参数。
- 技术边界：不新增、不改名接口；前端全局认证 `tenant-id` 请求头和未绑定组织门禁保留；9 张运行时表接口、原生 JDBC 和动态资源不接收、不拼接、不回填 tenant 条件。
- 通过条件：相关接口请求、SQL 与响应均无目标表 tenant 业务字段；后台题目 CRUD 与 APP 均跨租户一致；记录/测评结果归属越权仍失败；前端和依赖项目无改动。
- 证据承接：`061-验收标准/03-测试验证/DEV-051/` 与 `DEV-053/`。
