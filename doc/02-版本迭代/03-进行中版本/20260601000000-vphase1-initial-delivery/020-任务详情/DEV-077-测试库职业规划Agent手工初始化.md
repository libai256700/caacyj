# DEV-077 测试库职业规划Agent手工初始化

## 实施标准

- 上游规格：DEV-076正式Agent工具、`PD-052`固定主键与事务口径和 `AC-CAREER-ASSESS-201/202/401`。
- 人工确认连接参数来自当前程序同一测试数据库 `114.111.30.111:13306/yunjikeji`，不新增或切换数据库。
- 先执行dry-run，复核 `yj_agent_info.id=3`仍为空、真实字段、名称/prompt冲突和 `career-planning-coach/scripts/career-core.mjs` 中 `SELF_SYSTEM_PROMPT` 的原文 hash；若已进入 apply，任何写前备份步骤也必须先成功完成，失败则整体中止且不得进入事务写入。
- 目标固定为id=3、name=职业规划评测、tenant_id=1、status=1、knowledge_base_id=NULL、prompt_config=源 `SELF_SYSTEM_PROMPT` 原文、reply_strategy=NULL、agent_id=NULL。apply时只要id=3已存在，无论内容是否相同，本次apply都安全中止且零修改；禁止更新或自动改用4、5及AUTO_INCREMENT值。
- dry-run通过后备份、显式 `--apply --id 3`并回读主键、核心字段和prompt hash；回读作为DEV-072落 `CAREER_ASSESSMENT_AGENT_INFO_ID=3L`的实施输入。分类14报告模型仍由运行时既有 `yj_ai_model_config.practice_assessment` 选择，本工具不得写入或覆盖模型配置。不得修改id=2，不得按agent_id或名称运行时选取。
- 凭据不入回执或Git；不在生产数据库执行。

## 对应技能

- `00-0350-sql-script-standards-definition`
- `40-0100-project-testing`

## 交付物

- Agent工具id=3 dry-run冲突检查、备份、apply、事务和回读真实回执；`id=2`不变反证。

## 分支安排详情

- 前置任务：DEV-076程序通过独立静态/测试验收；本任务是人类固定主键和数据写入门禁。

## 关联验收项

- `AC-CAREER-ASSESS-201/202/401`。

## 任务产出 / 结果记录

- DEV-076 备份序列化返工已由不同代理独立验收 PASS，当前任务继续进行中。
- 第一次显式 `--apply --id 3` 已在写前备份阶段因 JSON 序列化 `datetime` 失败而安全中止；事务 / INSERT 未开始，现场仍是 `id=3` 为空、`id=2` 未变、无备份 / 回执、数据库零修改。
- 当前已解除等待修复阻塞；下一步为重新 dry-run，确认现场仍满足固定主键条件后，再发起一次新的显式 apply。

## 进度总结

- 当前状态：进行中。
