# AC-PROFILE-301 最小实现与角色回归保护

- 类型：技术-代码级
- 正式入口：`AppCompanyAuthMeRespVO`、`CompanyAuditServiceImpl`、`customerAuth.ts`、`profile.vue` 及对应目标测试。
- 支撑的业务结果：只修复企业端教员姓名和部门展示，不改变其他业务角色与现有登录体验。
- 技术边界：后端只扩展既有 `/company-auth/me`；前端只在企业分支读取新字段。手机号继续取现有 session 并使用现有 mask；学员及其他角色、企业登录/注册/刷新令牌、岗位识别不变；`uni_modules/**` 和数据库零改动。
- 通过条件：正确红灯先于实现形成并在最小实现后转绿；后端目标测试、前端类型检查/契约测试、企业页面 Playwright、学员回归、差异白名单、`uni_modules/**` 禁区检查通过；实施代理不得承担 DEV-083 独立验收。
- 证据承接方式：DEV-081 红灯回执、DEV-082 实施测试记录、DEV-083 独立复跑结果与最终差异清单。
