# AC-NEWSERVER-101 新测试服务器基础环境与运行入口

- 类型：技术-接口级
- 正式入口：`E:\huiyitechworkspace\feixingxueyuan\服务器信息.txt`、`E:\huiyitechworkspace\feixingxueyuan\数据库信息.txt`、受控 SSH 接入、`java -version`、`docker --version`、`nginx -t`、`systemctl status`、各服务启动脚本与健康接口。
- 支撑结果：SSH 已切换到受控 key，Java / Docker / Nginx / 必要运行依赖可用，`yunjikeji-admin-server` 启动与配置验收可以证明其连接新机本地 Redis，并直连内网数据库 `172.16.32.2:3306/yunjikeji_test`，五个应用的监听端口、反向代理和健康检查可以按正式记录核对。
- 技术边界：不新增额外对外端口，不改 DNS，不停旧机，不把未点名的 `yunjikeji-server` 纳入本轮部署；部署验证只承接新测试服务器的正式入口。
- 通过条件：基础环境安装完成，关键服务状态和健康接口均可被正式核验，`yunjikeji-admin-server` 的启动 / 配置证明可以回读到新机本地 Redis，并直连 `172.16.32.2:3306/yunjikeji_test`，没有本地数据库代理或依赖明文口令的长期接入方式。
- 证据承接：部署命令、端口监听结果、`systemctl` / 容器状态、健康检查输出和启动日志。

## 验收结果

- 状态：已验证。
- 结果：通过。受控 SSH、Java、Docker、Docker Compose、Nginx 及必要运行依赖均已由独立代理核验；相关容器、服务、监听与健康入口正常。
- 依赖连接：`yunjikeji-admin-server` 使用新机本地 Redis，并直接连接内网数据库 `172.16.32.2:3306/yunjikeji_test`；没有使用本地 `13306` 或 `127.0.0.1:3306` 数据库代理。
- 边界：未切换 DNS，旧测试服务器保持运行，未记录任何用户名、密码或密钥。
