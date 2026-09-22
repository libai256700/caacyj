# AC-ENTERPRISE-BOS-301 BOS 代码边界与质量门禁

- 类型：技术-代码级
- 正式入口：`BaiduBosUtil`、`FrontComanpanyAuditController`、`customerAuth.ts`、`register.vue`。
- 支撑结果：恢复 `2310754d` 的 BOS 直传语义，并把企业注册上传改接当前专用接口。
- 技术边界：保留企业注册页面与审核流程后续修复；不修改 `uni_modules/**`，不引入明文 AK/SK，不整仓回退。
- 通过条件：后端最小测试通过；前端 `pnpm type-check`、`pnpm run build:h5`、`git diff --check` 通过；自动化脚本证明企业上传入口不再引用 `/app-api/infra/file/upload`。
- 证据承接：JUnit 结果、前端命令结果、`DEV-024/front-static-check.json`、`git diff --check` 输出。
