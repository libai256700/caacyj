# AC-ASSESS-REQUIRED-101 自测题库是否必填接口契约

- 类型：技术-接口级
- 关联任务：`DEV-084`、`DEV-085`
- 正式入口：`/admin-api/yj/assessment-question/page`、`get`、`create`、`update`。
- 支撑的业务结果：列表能展示真实必填状态，编辑弹窗能回显并保存选择。
- 技术边界：仅扩展 assessment-question 资源的字段白名单、分页/详情查询和创建/更新值映射；不扩大通用资源写权限。
- 通过条件：分页和详情响应包含 `is_required`；创建/更新接受 snake_case `is_required` 并兼容 camelCase `isRequired`；false 能完整传递并持久化，不被空值处理丢弃。
- 证据承接方式：聚焦后端契约测试及真实接口回执写入 `061-验收标准/03-测试验证/DEV-084/` 或 `DEV-085/`。
