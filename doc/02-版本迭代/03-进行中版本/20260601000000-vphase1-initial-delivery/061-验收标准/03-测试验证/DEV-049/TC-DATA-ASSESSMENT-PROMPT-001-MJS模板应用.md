# TC-DATA-ASSESSMENT-PROMPT-001 V3 数据库提示词迁移

## 当前结论

- 数据库专项结论：`DATABASE_V3_PROMPT=PASS`。
- 执行日期：`2026-08-27`。
- 目标记录：测试库 `yj_agent_info.id=2`、`name=小题`、`tenant_id=1`。
- 当前实值：`2627` 个 Unicode 码点、`6770` 个 UTF-8 字节、SHA-256 `3f2a53619b12ea47e94978d47aff1028781ea52903fe2e845362027f8160dbc1`。
- 结构检查：规则引擎最高优先级 marker、`verifiedKnowledge`、V3 证照表述规则和 V3 等级自然解释规则均存在；旧六章 marker 与 `data-brand` 均不存在。
- 证照规则：只有系统事实明确给出白名单具体证书名称时才允许引用；无具体证书时统一写“已有培训或学习基础”；四类泛化证照措辞及虚构具体证书均被禁止。
- 等级规则：程序评分仪表盘原样展示官方分数与等级；AI 正文可作不改变含义的自然解释，但不得重算、另判或出现冲突的其他官方等级。

## 备份与恢复

- 执行前完整快照：`database-backup-yj_agent_info-id2-before-v3-20260827.sql`，`11194` 字节，SHA-256 `28f238c850463136766cbcfb82beb14b01170b7a664648ab24632eef986e1b2b`。
- restore-safe 文件：`database-backup-yj_agent_info-id2-before-v3-20260827-restore.sql`，`10937` 字节，SHA-256 `1625ade26898b5ad937ad0dbaae266a261e35681c3763abe584b28da08f4ad45`。
- 本次证照提示词变更前仓外快照：`C:\Users\renquan\.codex\db-backups\feixingxueyuan\DEV-049\20260827205100-yj_agent_info-id2-before-v3-certificate.sql`，`7093` 字节、1 条目标 INSERT，SHA-256 `9248b9194765de1fb4a7f0ed91da1354a8af149c5fd43ea87759e3d95cdc8386`。
- 本次等级规则变更前仓外快照：`C:\Users\renquan\.codex\db-backups\feixingxueyuan\DEV-049\20260827221545-yj_agent_info-id2-before-v3-level-natural-explanation.sql`，`6944` 字节、1 条目标 INSERT，SHA-256 `081450fa6792b4bc9e86913654b71a05f45f95dd6f7f5545a347642f9e69b180`。
- 本次正向脚本：`../../../050-执行脚本/20260827221545-dml-update_yj_agent_info_v3_level_natural_explanation_prompt.sql`。
- 本次回滚脚本：`../../../050-执行脚本/20260827221546-dml-rollback_yj_agent_info_v3_level_natural_explanation_prompt.sql`。

## 验收结果

1. 首次执行为 `READY / updated_rows=1 / postcheck=1 / PASS`；幂等复跑为 `ALREADY_APPLIED / updated_rows=0 / postcheck=1 / PASS`。
2. 当前数据库值精确命中 `2627 / 6770 / 3f2a5361...dbc1` 目标，`reply_strategy` 哈希和 `practice_assessment` 模型配置指纹均未变化。
3. AI 正文 `2500-3800` Unicode 码点继续由 V3 user prompt 约束生成目标；后端只记录越界审计，不再作为 `FAILED` 硬门禁，未在数据库 system prompt 重复定义。
4. 仪表盘精确等级、正文近义解释及冲突等级不阻断均已有代码测试；冲突只记录审计，规则引擎 marker、`verifiedKnowledge`、证照规则和等级自然解释规则 marker 均存在。
5. 数据库专项验收通过；真实 AI 报告生成、持久化、详情接口和 APP 页面链路仍按其他验收项独立验证。

## 边界

- 本结论只覆盖测试库 `AC-ASSESSMENT-AI-201` 的提示词实值，不代表 DEV-049 整体完成。
- 生产库禁止直接执行，本证据未记录连接密码或完整提示词。
- 完整 `systemPrompt`、`userPrompt`、`rawResult` INFO 日志按用户明确要求保持现状，不作为本数据库专项验收的阻塞项。
- 证照规则脱敏回执：[database-certificate-prompt-application-result-20260827.json](database-certificate-prompt-application-result-20260827.json)。
- 等级规则脱敏回执：[database-level-natural-explanation-prompt-application-result-20260827.json](database-level-natural-explanation-prompt-application-result-20260827.json)。

## 历史前驱

- `2440 / 6243 / 974ef05f...d414` 是本次等级规则补丁的真实直接前驱；`2284 / 5809 / d7794b51...3c16ce` 是证照规则补丁前驱；更早的 `4285 / 9305 / c8f4803d...79f75` 仅保留为旧六章历史证据。
