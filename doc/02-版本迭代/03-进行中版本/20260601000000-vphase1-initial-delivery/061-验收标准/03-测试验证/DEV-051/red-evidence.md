# DEV-051 红灯证据

- 日期：2026-08-17（实现前）。
- 入口：`PracticeSharedTenantContractTest`。
- 结果：退出码 `1`，红灯原因与本需求一致。
- 直接证据：七个目标 DO 仍继承 `TenantBaseDO`；共享资源可写列仍包含 `tenant_id`；错题删除仍使用租户键。
- 结论：失败来自目标租户约束尚未移除，不是测试环境或依赖异常，允许进入最小实现。
- 当前复跑脚本：`run_practice_shared_contract.py`；该脚本用于验证实施后的合同、编译和受保护目录边界，不会连接数据库。
