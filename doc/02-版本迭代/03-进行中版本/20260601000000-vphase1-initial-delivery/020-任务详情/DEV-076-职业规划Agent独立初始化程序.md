# DEV-076 职业规划Agent独立初始化程序

## 实施标准

- 上游规格：`PD-052`第2.4、2.5、6.2节和 `AC-CAREER-ASSESS-201/202/301`。
- 新增第二个独立Python手工程序，仅从 `career-planning-coach/scripts/career-core.mjs` 提取 `SELF_SYSTEM_PROMPT` 原文并初始化一条 `yj_agent_info`；不得与题库程序共用入口。
- 程序可放项目仓库独立人工工具目录，但业务、启动、构建、migration、依赖注入、资源初始化、定时和业务接口零引用。
- 只连接当前程序同库 `114.111.30.111:13306/yunjikeji`；连接参数由人工显式传入，凭据不入代码、回执或Git。
- 当前只读事实：id=1、2、6、7已占，id=3、4、5空闲，AUTO_INCREMENT=8；本工具固定检查和写入id=3，禁止自选或换号。
- 默认dry-run，检查id=3仍为空、真实字段、同名/同prompt记录和prompt hash；目标字段固定为name=职业规划评测、tenant_id=1、status=1、knowledge_base_id=NULL、prompt_config=SELF_SYSTEM_PROMPT、reply_strategy=NULL、agent_id=NULL。
- 显式apply必须带 `--id 3`；写前备份、单事务插入、异常回滚，回读主键、核心字段和prompt hash。只要id=3已存在，无论内容是否完全相同，本次apply都判定为中止且零修改；不得更新或换号。
- 不修改分类13 `yj_agent_info.id=2`、tenant_id=1；模型继续来自 `yj_ai_model_config.practice_assessment`。

## 对应技能

- `00-0350-sql-script-standards-definition`
- `30-0100-development-task-breakdown`

## 交付物

- 与题库工具分离的Agent初始化程序、提取测试、dry-run/apply说明和回执模板；本任务不写数据库。

## 分支安排详情

- 前置任务：DEV-070正确红灯；可与DEV-071并行，不修改业务源码、数据库连接配置或 `uni_modules/**`。

## 关联验收项

- `AC-CAREER-ASSESS-201/202/301`。

## 任务产出 / 结果记录

- DEV-070第三轮独立验收PASS后，本任务与DEV-071并行启动并完成独立Python人工工具实现。
- 初版实现曾通过不同代理独立静态验收；实现与验收全程未连接数据库、未执行dry-run或apply，不得进入业务源码、启动、构建或运行链路。
- 新证据显示 DEV-077 首次显式 `--apply --id 3` 在写前备份阶段因 JSON 序列化 `datetime` 失败而中止，错误发生于事务 / INSERT 前；现场确认为 `id=3` 仍为空、`id=2` 未变、无备份 / 回执、数据库零修改。
- 备份序列化返工已由不同代理独立验收 PASS，覆盖 `7 tests`、Agent AST、备份 round-trip、异常非零退出与 `pycache` 卫生；现已恢复为已完成，并重新放行 DEV-077 继续人工执行。

## 进度总结

- 当前状态：已完成。
