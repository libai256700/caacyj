# AC-PRACTICE-SHARED-301 实现边界与租户回归

- 类型：技术-代码级
- 正式入口：六个目标 DO、练习通用资源服务、后台练习/通用 JDBC、APP 练习服务、错题 Mapper、租户拦截配置及验证资产。
- 支撑结果：所有 9 张运行时表路径统一取消租户机制，且未连带放开其他租户表。
- 回归边界：七个现有 DO 脱离 `TenantBaseDO` 并使用精确表级忽略或等效机制；`PracticeExercisesServiceImpl` 与通用资源服务不保留题目租户填充；步骤、测评结果的动态资源/原生 JDBC 及所有 setter、writableColumns、Mapper tenant 逻辑清除。
- 通过条件：静态扫描无 9 张运行时表显式 tenant 残留；`CustomerAccountDO` 或另一张明确非目标 `TenantBaseDO` 业务表反证隔离仍生效；条件兼容不新增 Java 路径；后端目标测试与编译、`git diff --check` 通过；前端、依赖项目和 `uni_modules/**` 无改动。
- 证据承接：`061-验收标准/03-测试验证/DEV-053/` 与独立验收 `DEV-054/`。
