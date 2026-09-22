# DEV-079 APP答题AI深度解答与AI助手历史隔离

## 实施标准

- 上游口径：所有答题过程中的 AI 深度解答仅在数据库层面不再保存 AI 助手历史；普通答题、错题练习、首次解答、后续追问的当前页即时展示、当前页追问体验、现有前端状态、页面布局、页面文案和交互全部保持不变。AI 助手入口自身问答继续按现状落库并可重进查看；既有污染记录本任务不删除。
- 已确认根因：答题页 AI 深度解答与 AI 助手当前共用 `/app-api/yj/knowledge/query`；后端查询链路无条件按 `KNOWLEDGE_CHAT` 向 `yj_ai_center` 写历史，导致 AI 助手读取到答题过程内容。当前证据仅支持历史污染，不支持模型继承答题上下文。
- 正式方案允许在现有请求中增加不可见来源标识，仅供后端判断是否写入 `yj_ai_center`；不得把“不保存历史”提示、开关或任何视觉/交互变化改到页面上，也不得把验收写成不保留当前页临时内容或修改 UI。
- TDD 门禁：必须先建立红灯，精确证明普通答题/错题练习两条答题链路下的首次解答与后续追问会污染 AI 助手历史，同时证明 AI 助手自身历史落库链路保持现状；再做最小修复转绿；最后由独立验收代理重跑目标场景与关联回归。
- 预计影响源码以实施证据为准，当前优先关注 `code/develop/yunjikeji/src/services/practice.ts`、`code/develop/yunjikeji/src/pages/practice/ai-answer.vue`、`code/develop/yunjikeji/src/pages/center/center.vue`、`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/knowledge/controller/FrontKnowledgeController.java`、`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/knowledge/service/FrontKnowledgeService.java`、`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/knowledge/service/FrontKnowledgeServiceImpl.java`；若能仅以后端最小改动闭环，不得额外扩散范围。
- 正式验证必须覆盖普通答题、错题练习、首次解答、后续追问、AI 助手自身历史回看、不同账号隔离、既有污染历史不被误删，以及并行改动和 `uni_modules/**` 保护边界。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `30-0100-development-task-breakdown`
- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- 答题 AI 深度解答与 AI 助手历史隔离的最小实现方案与对应源码改动。
- `AC-AI-CONTEXT-001`、`AC-AI-CONTEXT-101`、`AC-AI-CONTEXT-201`、`AC-AI-CONTEXT-301` 正式验收入口。
- `061-验收标准/03-测试验证/DEV-079/` 下的后续正式测试资产入口。

## 分支安排详情

- 沿用当前版本实际分支 `feature/20260601000000-vphase1-initial-delivery`。
- 实施时必须先保护工作区既有并行改动，只围绕本任务白名单文件增量修改；不得删除、回退、覆盖其他开发内容，不得触碰 `uni_modules/**`。
- 若现有两入口请求完全相同，仅允许补不可见来源标识和后端历史写入门禁；页面视觉、文案、提示、即时对话体验和现有前端临时状态不得作为本任务改动范围。

## 关联验收项

- 业务验收：`AC-AI-CONTEXT-001`
- 技术验收：`AC-AI-CONTEXT-101`、`AC-AI-CONTEXT-201`、`AC-AI-CONTEXT-301`

## 任务产出 / 结果记录

- 2026-08-31 已核对 `DEV-079` 与 `AC-AI-CONTEXT-001/101/201/301` 当前无编号冲突，并已在主计划、任务索引、任务详情、验收索引和验收结论建立正式入口。
- 2026-08-31 已按用户最终口径收敛边界：所有答题过程中的 AI 深度解答继续保留当前页即时展示与追问体验，仅数据库层面禁止写入 `yj_ai_center` AI 助手历史；AI 助手入口自身历史落库与回看保持不变；既有污染记录不清理。
- 2026-08-31 已记录当前根因证据：`/app-api/yj/knowledge/query` 被答题页 AI 深度解答与 AI 助手共用，而后端历史写入对答题来源与 AI 助手来源未做隔离，统一按 `KNOWLEDGE_CHAT` 写库，导致 AI 助手历史展示污染。
- 2026-08-31 已明确本任务必须走 TDD：先红灯准确命中“答题 AI 内容进入 AI 助手历史”，再做最小修复，最后由不同代理独立验收；当前尚未宣称代码修复、测试通过或历史数据清理完成。
- 2026-08-31 已完成本地独立验收复跑：`FrontKnowledgeServiceImplHistoryIsolationContractTest` 实测 `4/4` 通过，`npm run type-check` 通过；后端调用方已收敛为 `ask(reqVO) -> query(reqVO.getQuestion(), null)` 保持旧行为兼容，`AppKnowledgeAskReqVO` 已无残留 diff，`center.vue` 无本任务 diff，`uni_modules/**` 无变更。

## 进度总结

- 当前状态：本地独立验收通过，待测试环境验收。
- 当前结论：正式计划与验收口径已建立，本地复跑已通过；后续只等测试环境与真实浏览器/数据链路验收，不宣称最终完成。
