# AC-KGCLOUD-101 生产运行入口与身份隔离

- 类型：技术-接口级
- 正式入口：final delivery 的 `verify_final_delivery.py`、锁定依赖、public `pipeline.wsgi:app`、独立 ops WSGI、生产健康检查与身份网关。
- 支撑的业务结果：生产请求只能经已验证身份访问 public 问答，运维能力不暴露给 App 或公网。
- 技术边界：必须使用 exact release、绝对 Python 与 eager WSGI；public/ops 分进程、分账号、分 secret、分网络，失败必须在监听前关闭。
- 通过条件：SHA256SUMS 与 verifier 通过；`usearch==2.26.2` 可加载；public/ops 各自启动；合法身份可用，缺失/伪造/过期/错误角色被拒绝；后台调用契约兼容。
- 证据承接方式：命令退出码、版本输出、进程/端口、配置 hash、HTTP 响应和日志摘要。

## 验收结果

- 状态：进行中，未通过完整验收。
- 已有证据：final delivery 远端 ZIP 校验、隔离解压和包内 `SHA256SUMS` 全项通过；官方 Python 3.14.5、bootstrap installer、用户批准的 formal wheelhouse 和目标 venv 均已建立。目标 venv exact 17 项、无 pip/setuptools/wheel，`usearch==2.26.2` 成功导入，双索引只读加载通过；同一 venv 执行 `verify_final_delivery.py` 返回 `ok:true`、`errors:[]`。该阶段已由不同代理独立验收。系统 Python 仍为 3.6.8，旧服务 `/api/health` HTTP 200、5001 正常监听、Neo4j healthy。
- 已解除门禁：`/srv/knowledge-qa/wheelhouse` 含 exact 17 个 wheel，manifest 与逐文件哈希均通过；`/srv/knowledge-qa/venvs/20260905-r2` 已按只离线、无依赖解析方式安装。
- 未满足：provider/identity/secrets 尚未注入，public/ops WSGI、eager preflight、生产身份拒绝矩阵和正式调用契约均未执行；`runtime_active:false`。
- 证据入口：`../03-测试验证/TASK-027/02-release-staging-and-runtime.md`、`../03-测试验证/TASK-027/03-python-bootstrap.md`、`../03-测试验证/TASK-027/04-wheelhouse-venv-usearch.md`。
