# AC-IOT-QUARTZ-101 测试环境运行入口与线程边界

- 类型：技术-接口级
- 正式入口：`application-test.yaml`、`/actuator/health`、`jcmd <pid> Thread.print` / `jstack <pid>`、`yunjikeji-admin-server-start.sh`
- 支撑结果：测试环境服务健康检查返回 `UP`，并且线程检查中不再出现 `iotScheduler` 线程或实例。
- 技术边界：不关闭全局 Quartz 的其它调度能力；不修改 `uni_modules/**`；不删除 DEVICE 路径与既有场景规则业务逻辑。
- 通过条件：测试 profile 启用时程调度器不装配，健康检查通过，线程检查无 `iotScheduler`，启动脚本可稳定拉起服务。
- 证据承接：健康接口返回结果、线程打印结果、启动脚本与部署日志。
