# AC-IOT-QUARTZ-301 IoT Scheduler 代码边界与兼容性

- 类型：技术-代码级
- 正式入口：`IotJobConfiguration`、`IotSceneRuleTimerHandler`、`IotSceneRuleServiceImpl`、`IotSceneRuleTimerHandlerTest`
- 支撑结果：默认行为保持兼容，只有测试 profile 关闭 IoT Scheduler；`IotSceneRuleTimerHandler` 在 scheduler 缺失时安全 no-op；DEVICE 路径不删除、不改写。
- 技术边界：不关闭全局 Quartz 或其它调度，不改 `uni_modules/**`，不引入新的数据库结构或 SQL。
- 通过条件：后端编译和对应测试通过，代码白名单仅含 IoT Scheduler 相关改动，且不影响现有场景规则主链路。
- 证据承接：源码 diff、单元测试结果、编译结果与后续部署验证记录。
