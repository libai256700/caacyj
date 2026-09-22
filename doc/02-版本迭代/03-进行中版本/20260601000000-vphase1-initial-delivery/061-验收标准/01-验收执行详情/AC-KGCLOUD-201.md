# AC-KGCLOUD-201 生产数据、索引、图谱与回滚

- 类型：技术-数据级
- 正式入口：authority SQLite、BM25、chunk/entity USEarch、scoped graph JSONL/manifest/importer、Neo4j candidate、receipts、active config、备份和 `ROLLBACK_PLAN.json`。
- 支撑的业务结果：生产检索使用同一 exact release 的完整数据层，故障时能够整体回退。
- 技术边界：Neo4j 导入前必须可恢复备份；只从 scoped graph 导入，不复制 store；Release 只读，candidate 与 active 分离；禁止新旧 release 混用。
- 通过条件：35 docs/1482 chunks、BM25 与双向量覆盖、22 entities/3920 edges、SQLite/graph evidence 回填均与 manifest 一致；备份完整性和恢复命令通过检查；回滚演练能恢复 exact pre-state。
- 证据承接方式：备份路径/SHA、verifier、vector/graph receipts、Neo4j 只读统计、active binding 和回滚演练记录。

## 验收结果

- 状态：进行中，未通过完整验收。
- 已有证据：旧工程归档 `373703921` bytes，SHA-256 `a45a9e9f647f2213758081ad1a5e726d0f2942064b0a8ec0a860138cc52eb88e`，清单与归档可读性校验通过；Release 内 authority、BM25、双向量和 scoped graph 文件通过包内 SHA 校验；旧 Neo4j 只读计数为 `3986 nodes / 143661 relationships`。Linux 目标 venv 已使用 `usearch==2.26.2` 以 `view=True` 只读加载 chunk/entity 双索引，分别为 1482/22 条、1024 维，文件 SHA-256 与 manifest 一致；该阶段已由不同代理独立验收。
- 边界：活动 Neo4j store 已从文件归档排除；已完成 Community `2026.05.0` 一致性 dump，原容器恢复后计数与旧 API 均恢复；恢复入口仍要求获批停旧服务，Neo4j 必须使用独立实例或获批的同库 namespace+独立最小权限账户方案。
- 阻塞：当前仅有 `neo4j`/`system` 数据库和现有 `neo4j` 用户，未形成可验证 import/runtime 账户分离；因此 scoped Neo4j candidate 导入及 manifest 回填未执行。
- 未满足：active binding、provider/identity、public/ops WSGI、5001 切流和真实回滚演练均未执行；`runtime_active:false`、`product_accepted:false`。
- 证据入口：`../03-测试验证/TASK-027/01-prestate-and-backup.md`、`../03-测试验证/TASK-027/02-release-staging-and-runtime.md`、`../03-测试验证/TASK-027/04-wheelhouse-venv-usearch.md`、`../03-测试验证/TASK-027/05-neo4j-consistency-backup.md`。
