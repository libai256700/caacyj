# AC-ENTERPRISE-BOS-101 企业营业执照专用上传接口

- 类型：技术-接口级
- 正式入口：`POST /app-api/yj/enterprise-audit/license/upload`
- 支撑结果：企业营业执照上传固定走百度 BOS，不再误用 `/app-api/infra/file/upload` 和数据库 `master=22` 七牛示例存储器。
- 技术边界：接口只接收 `multipart file`，上传目录固定为 `enterprise/license`；BOS 未配置时返回明确业务失败，不泄露密钥。
- 通过条件：专用接口返回真实 BOS URL；BOS 未配置或不可用时返回明确失败；企业注册上传入口不再调用通用文件上传接口。
- 证据承接：后端控制器测试、BOS 工具测试、源码审计脚本和测试环境复验。
