# DEV-065 APP组织绑定前置身份信息采集与同步

## 实施标准

- 真实组织绑定页已确认为 `code/develop/yunjikeji/src/pages/enterprise/organization-bind.vue`；点击“申请绑定组织”或“重新申请组织”时必须先弹出身份信息采集表单，不得直接提交组织申请。
- 采集表单必须包含真实姓名、身份证号、性别三项；取消仅关闭弹窗，不触发任何保存或提交动作。
- 确认前必须完成必填校验；真实姓名、身份证号、性别缺项或非法时不得继续提交组织申请。
- 确认后必须先调用 `POST /app-api/yj/customer-info/save` 保存 `realName`、`idCard`、`sex`，再调用 `POST /app-api/yj/student-audit/submit` 提交组织申请；保存失败时不得继续提交。
- 学员基础信息同步必须落到当前登录学员对应的 `yj_customer_info`；不允许用本地缓存、假数据或组织申请记录冒充真实信息落库。
- 应用源码白名单仅限 `code/develop/yunjikeji/src/pages/enterprise/organization-bind.vue`、`code/develop/yunjikeji/src/components/OrganizationJoinApplicationDialog.vue` 与 `code/develop/yunjikeji/src/services/customerAuth.ts`；不得修改 `uni_modules/**`。

## 对应技能

- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- 组织绑定页前置信息采集弹窗与提交链路。
- 学员基础信息保存到 `yj_customer_info` 的真实接口调用链。
- `AC-ORGBIND-001`、`AC-ORGBIND-101`、`AC-ORGBIND-201`、`AC-ORGBIND-301`、`AC-ORGBIND-401` 正式验收入口。

## 分支安排详情

- 沿用当前版本实际分支 `feature/20260601000000-vphase1-initial-delivery`。
- 应用源码白名单仅限组织绑定页、绑定弹窗组件与学员账号服务；不改 `uni_modules/**`，不额外扩散到首页、练习页或企业端页面。
- 组织申请提交流程必须复用现有 `saveCustomerInfo` 与 `submitStudentAudit` 正式契约，不新增同义提交接口。

## 关联验收项

- 业务验收：`AC-ORGBIND-001`
- 技术验收：`AC-ORGBIND-101`、`AC-ORGBIND-201`、`AC-ORGBIND-301`
- 闭环项：`AC-ORGBIND-401`

## 任务产出 / 结果记录

- 2026-08-19 已完成本任务正式计划补录，确认组织绑定前置采集需落在真实姓名、身份证号、性别三项。
- 2026-08-19 已确认后端正式入口为 `POST /app-api/yj/customer-info/save` 与 `POST /app-api/yj/student-audit/submit`，`AppCustomerInfoSaveReqVO` 已包含 `realName`、`idCard`、`sex` 字段，`CustomerServiceImpl.saveCustomerInfo` 会同步写入 `yj_customer_info`。
- 2026-08-19 已确认当前组织绑定页为 `code/develop/yunjikeji/src/pages/enterprise/organization-bind.vue`，现有 `customerAuth.ts` 已暴露保存学员基础信息与提交组织申请的正式调用入口。
- 2026-08-19 已完成前端实现：弹窗新增真实姓名、身份证号、性别字段及确认前校验；确认先调用 `customer-info/save`，成功后再调用 `student-audit/submit`，取消不触发请求。
- 2026-08-19 本地验证：`npm run type-check`、`npm run build:h5`、`git diff --check` 均通过；真实测试环境交互与独立验收待执行。

## 进度总结

- 当前状态：待独立验收。
- 当前阶段：前端实现与本地静态验证完成，等待测试环境交互、接口/数据检查和独立验收。
- 当前结论：取消不提交、必填校验、确认后先保存学员基础信息再提交组织申请，且真实姓名、身份证号、性别必须同步到 `yj_customer_info`。
