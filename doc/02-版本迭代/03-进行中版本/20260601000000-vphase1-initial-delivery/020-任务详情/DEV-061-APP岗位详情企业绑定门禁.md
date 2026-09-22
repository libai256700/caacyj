# DEV-061 APP岗位详情企业绑定门禁

## 实施标准

- 真实岗位招聘页面已确认为 `code/develop/yunjikeji/src/pages/jobs.vue`；页面只有一个 `v-for` 内“查看详情”入口，统一调用 `openJobDetail(job)`，应用源码白名单仅限该文件。
- 考题场景正式组件已确认为 `code/develop/yunjikeji/src/components/OrganizationBindingRequiredDialog.vue`；岗位页必须直接导入并在列表外只渲染一个实例，不修改该组件，不新建同义弹框。
- 真实企业绑定状态来源已确认为 `fetchCurrentStudentAudit()` 对 `GET /app-api/yj/student-audit/my` 的响应；仅 `auditStatus === 2` 表示已绑定并允许放行，`null`、非 `2`、加载中或请求失败均不得进入岗位详情。
- 岗位招聘页点击任一“查看详情”时必须先读取项目真实企业绑定状态，不得以假数据、硬编码或仅页面局部变量冒充真实绑定机制。
- 未绑定企业时不得执行原详情导航；必须直接复用考题场景当前使用的同一个正式企业绑定组件，不新建同义弹框，组件文案、关闭动作和绑定动作与考题场景保持一致；重复点击不得叠加多个弹框。
- 已绑定企业时不得弹出绑定组件，原 `detailUrl`、URL 标准化及 App `plus.runtime.openURL`、H5 `window.open('_blank')`、其他运行时复制链接三分支保持不变。
- 企业绑定状态加载中或读取失败时不得误放行进入岗位详情；按项目现有机制保持阻断，并复用现有错误或加载承接，不伪造已绑定结果。
- 应用源码白名单仅限 `code/develop/yunjikeji/src/pages/jobs.vue`；不得修改正式弹框组件、考题页面、services、backend、auth、其他页面或 `uni_modules/**`。岗位页同时监听组件旧 `cancel` 与当前 `close/service` 事件，确保远端旧契约和当前并行组件契约均可承接，但不得把组件既有 dirty 归入 DEV-061。
- 后续正式验证覆盖未绑定、已绑定、重复点击、现有机制可测范围内的读取失败/加载态，以及原详情参数、导航目标和业务逻辑回归；执行 `pnpm type-check`、`pnpm run build:h5`、`git diff --check`。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `00-1150-main-subagent-governance`
- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- `code/develop/yunjikeji/src/pages/jobs.vue` 的“查看详情”企业绑定门禁实现。
- 对考题场景当前正式企业绑定组件的直接复用，不新增同义弹框。
- `AC-JOBENTERPRISE-001`、`AC-JOBENTERPRISE-101`、`AC-JOBENTERPRISE-201` 正式验收入口。
- `061-验收标准/03-测试验证/DEV-061/` 下的后续正式测试资产入口。

## 分支安排详情

- 沿用当前版本实际分支 `feature/20260601000000-vphase1-initial-delivery`。
- 应用源码白名单仅限 `code/develop/yunjikeji/src/pages/jobs.vue`；正式组件、状态接口、原详情外链三分支均直接复用，不新增 service 或组件改动。
- `OrganizationBindingRequiredDialog.vue`、`home.vue`、`practice/exam-modes.vue`、`practice/exam-topics.vue` 存在事前并行 dirty，禁止覆盖或归入 DEV-061；岗位页必须兼容组件旧 `cancel` 与当前 `close/service` 契约。

## 关联验收项

- 业务验收：`AC-JOBENTERPRISE-001`
- 技术验收：`AC-JOBENTERPRISE-101`
- 闭环项：`AC-JOBENTERPRISE-201`

## 任务产出 / 结果记录

- 2026-08-18 已新增 DEV-061 主计划行、任务索引、任务详情与正式验收入口。
- 2026-08-18 已明确未绑定阻断、已绑定放行、正式组件复用、真实绑定状态、防重复触发和状态不可用时失败关闭的实施边界。
- 2026-08-18 信息收集确认：真实入口为 `src/pages/jobs.vue` 的唯一 `openJobDetail(job)`；正式组件为 `OrganizationBindingRequiredDialog.vue`；权威状态为 `fetchCurrentStudentAudit()`，仅 `auditStatus === 2` 放行；原详情承接为 App / H5 / 其他运行时三分支外链逻辑。
- 2026-08-18 已确认 DEV-061 无需修改组件、store、service、考题页或 `uni_modules/**`；组件当前工作区与远端存在并行事件契约差异，岗位页实现必须兼容且不得夹带组件 dirty。
- 2026-08-18 已在 `src/pages/jobs.vue` 直接复用正式组件与真实审核接口；未绑定、非通过状态、加载中或请求失败均阻断外链，仅 `auditStatus === 2` 放行原详情三运行时逻辑；旧 `cancel` 与当前 `close/service/bind` 事件均可承接。
- 2026-08-18 TDD 红灯准确命中门禁缺失；绿色 Playwright 共 14 项场景通过，覆盖未绑定、已绑定、延迟双击、500 失败关闭、三运行时、无效 URL、服务/绑定动作和三档移动视口，浏览器错误为 `0`。
- 2026-08-18 `pnpm type-check`、`pnpm run build:h5`、指定 `git diff --check` 均退出码 `0`；用户已完成页面测试并明确要求提交到 Gitee。
- 正式证据：`061-验收标准/03-测试验证/DEV-061/`；当前待提交与远程推送闭环。

## 进度总结

- 当前状态：待提交闭环。
- 当前阶段：实现、自动化验证、质量命令和用户页面测试已通过。
- 当前结论：应用源码仅修改 `src/pages/jobs.vue`；完成提交与远程推送后方可标记已完成。
