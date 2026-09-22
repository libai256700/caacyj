# TC-CODE-ENTERPRISE-LICENSE-BOS-001 企业注册营业执照 BOS 上传

- 对应验收项：`AC-ENTERPRISE-BOS-001`、`AC-ENTERPRISE-BOS-101`、`AC-ENTERPRISE-BOS-201`、`AC-ENTERPRISE-BOS-301`
- 测试层级：接口级 / 数据级 / 代码边界
- 前置条件：后端源码存在 `BaiduBosUtil`、`FrontComanpanyAuditController`；前端源码存在 `customerAuth.ts`、`register.vue`；本地仅做代码与构建验证。
- 执行入口：`node 061-验收标准/03-测试验证/05-自动化测试脚本/check-enterprise-license-upload.mjs`
- 场景：恢复 `2310754d` 的 BOS 配置与默认语义；企业营业执照上传必须走 `/app-api/yj/enterprise-audit/license/upload`；BOS 未配置时企业端失败并中断 `save/submit`。
- 预期：企业营业执照上传不再引用 `/app-api/infra/file/upload`；`BaiduBosUtil` 无静默 `FileApi` 回退；前端继续保持先上传、后保存、再提交的顺序；真实 BOS 上传待测试环境注入 `BAIDU_BOS_*` 后复验。
