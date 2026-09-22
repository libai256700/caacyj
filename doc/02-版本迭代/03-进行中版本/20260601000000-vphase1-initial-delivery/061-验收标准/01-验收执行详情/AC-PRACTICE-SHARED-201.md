# AC-PRACTICE-SHARED-201 九表运行时 SQL、条件兼容与唯一性

- 类型：技术-数据级
- 正式入口：9 张运行时表 SQL、后台/APP 原生 JDBC 与 Mapper、当前版本迁移 SQL、2 张兼容表存在性检查、错题唯一键及测试环境数据验证。
- 支撑结果：考题整体读写与组织无关，同时保持用户记录、测评结果和错题业务唯一性。
- 数据边界：9 张运行时表 SELECT/UPDATE/DELETE 不含 `tenant_id`，INSERT 列不含 `tenant_id`；记录和测评结果使用 `customer_account_id/user_id`、`record_id`；错题唯一性使用 `customer_account_id + exercises`。
- 通过条件：双租户 SQL 结果一致；`050-执行脚本/20260610-yj-practice-data-migration.sql` 目标表 INSERT 不写 tenant；两张兼容表仅在确认存在且继续保留时由幂等兼容 SQL 处理；错题查询、删除、upsert 和索引不依赖 tenant；不改旧历史 SQL、不执行生产库。
- 风险门禁：若只读检查发现跨租户重复错题，立即停止实现并提交受审迁移方案，不得自动合并或宣称通过。
- 证据承接：`061-验收标准/03-测试验证/DEV-051/` 与 `DEV-053/`。
