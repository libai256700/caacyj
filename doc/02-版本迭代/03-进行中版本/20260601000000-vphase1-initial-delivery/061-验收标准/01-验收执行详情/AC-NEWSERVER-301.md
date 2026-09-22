# AC-NEWSERVER-301 新测试服务器代码构建与部署边界

- 类型：技术-代码级
- 正式入口：`code/develop/knowledge-graph`、`code/develop/QwenPaw`、`code/develop/yunjikeji`、`code/develop/yunjikeji-admin-server`、`code/develop/yunjikeji-admin-ui`。
- 支撑结果：五个工程由当前 `code/develop/` 代码构建并部署到新测试服务器；`yunjikeji` 仅 H5，`yunjikeji-admin-server` 与 `yunjikeji-admin-ui` 按当前代码构建后发布。
- 技术边界：本次部署不修改 `uni_modules/**`，不引入非必要代码改动，不把未点名的 `yunjikeji-server` 纳入本轮部署范围。
- 通过条件：构建产物、部署目录、启动脚本与当前代码现场一一对应，且代码差异边界可审计。
- 证据承接：构建命令、产物哈希、启动脚本、运行目录、差异检查和部署回执。

## 验收结果

- 状态：已验证。
- 结果：通过。`knowledge-graph`、`QwenPaw` 已按既有运行态迁移；`yunjikeji` H5、`yunjikeji-admin-server` 和 `yunjikeji-admin-ui` 已使用当前 `code/develop/` 产物部署到新机并通过入口与健康检查。
- 边界：未修改 `uni_modules/**`，未将 App、uniCloud 或 `yunjikeji-server` 扩入本次部署范围。
