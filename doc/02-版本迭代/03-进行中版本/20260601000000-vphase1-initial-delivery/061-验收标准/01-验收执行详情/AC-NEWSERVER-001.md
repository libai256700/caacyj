# AC-NEWSERVER-001 新测试服务器正式入口可访问

- 类型：业务-交互级
- 前置条件：新测试服务器已经完成基础环境安装并按正式记录完成受控接入，旧测试服务器保持可用。
- 正式入口：新测试服务器 `106.13.71.85` 的 IP + Host / `curl --resolve` 访问入口；`knowledge-graph`、`QwenPaw`、`yunjikeji`、`yunjikeji-admin-server`、`yunjikeji-admin-ui` 的正式访问地址。
- 支撑结果：用户可以按正式记录逐一访问五个应用的新机入口，核对它们均已迁移到新测试服务器。
- 技术边界：不改 DNS，不停旧机，不把未点名的 `yunjikeji-server` 纳入本轮范围；`yunjikeji` 仅 H5，不部署 App / uniCloud。
- 通过条件：新机入口可访问且响应稳定，旧测试服务器保持原状，没有把“旧机仍可用”误写成停机替换完成。
- 证据承接：IP + Host 访问记录、`curl --resolve` 回执、健康检查截图或日志、版本详细计划回写。

## 验收结果

- 状态：已验证。
- 结果：通过。新机 `106.13.71.85` 上五个工程的运行入口已完成 IP + Host / `curl --resolve` 独立复核，外部请求返回 `HTTP 200`。
- 边界：DNS 未切换，旧测试服务器继续运行；本次仅部署 `yunjikeji` H5，未部署 App、uniCloud 或未点名的 `yunjikeji-server`。
