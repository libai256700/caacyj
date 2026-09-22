# AC-JOBENTERPRISE-101 岗位详情门禁的真实状态与最小实现边界

- 类型：技术-代码级
- 正式入口：`code/develop/yunjikeji/src/pages/jobs.vue`、`code/develop/yunjikeji/src/components/OrganizationBindingRequiredDialog.vue`、`fetchCurrentStudentAudit()` 及 `GET /app-api/yj/student-audit/my`，以及 `061-验收标准/03-测试验证/DEV-061/`。
- 支撑的业务结果：岗位“查看详情”以真实企业绑定状态决定阻断或放行；未绑定复用既有正式组件，已绑定保持原详情链路，状态不可用时失败关闭且重复触发不叠加弹框。
- 技术边界：应用源码白名单仅限 `src/pages/jobs.vue`；直接复用正式组件和现有状态接口，不得修改考题页面/组件、services、backend、auth、其他页面、锁文件或 `uni_modules/**`；不得以假数据、硬编码、页面局部变量或新建同义弹框替代真实机制；组件旧 `cancel` 与当前 `close/service` 事件契约均须安全承接，且不得夹带组件事前 dirty。
- 通过条件：实施前已记录真实岗位页面、正式组件和真实状态来源；所有“查看详情”入口先判断真实状态；未绑定不导航且组件只出现一个实例，已绑定的参数、目标和原业务逻辑逐项保持，加载或读取失败不误放行；后续正式验证覆盖约定场景，`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 退出码均为 `0`。
- 证据承接：`061-验收标准/03-测试验证/DEV-061/`，以及后续白名单差异、真实状态来源、组件复用和原详情参数回归证据。
