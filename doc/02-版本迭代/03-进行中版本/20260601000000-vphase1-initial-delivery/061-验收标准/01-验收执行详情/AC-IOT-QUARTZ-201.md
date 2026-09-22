# AC-IOT-QUARTZ-201 测试 profile 开关与日志结果

- 类型：技术-数据级
- 正式入口：`yunjikeji-admin-server/src/main/resources/application-test.yaml`
- 支撑结果：测试 profile 显式写入 `yudao.iot.scheduler.enable=false`，并在重启后不再新增 `DataSourceClosedException` 或 IoT Scheduler 初始化/关闭相关异常日志。
- 技术边界：不新增数据库脚本，不修改 Quartz 持久化表，不改生产 profile。
- 通过条件：测试 profile 配置落位正确，服务启动后日志稳定，无新的 IoT Scheduler 异常滚动输出。
- 证据承接：配置文件内容、启动日志、健康检查后的运行日志。
