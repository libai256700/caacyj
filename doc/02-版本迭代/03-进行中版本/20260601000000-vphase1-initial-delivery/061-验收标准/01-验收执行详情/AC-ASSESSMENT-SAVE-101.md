# AC-ASSESSMENT-SAVE-101 双评测 latest-status 保存状态契约

- 类型：技术-接口级
- 正式入口：分类13既有无参 latest-status（或当前真实 latest 入口）与分类14专用/显式 `categoryId=14` latest-status。
- 支撑业务结果：首页能够在进入任一评测前准确识别该分类最新批次是否仍在写入，状态1时安全短路原启动链路。
- 技术边界：分类13接口保留原路径、请求、既有响应字段和语义，仅加法返回 `batchSaveStatus`；分类14显式按14过滤。两者均校验当前用户并只返回对应分类最新批次，字段映射 `yj_practice_catalog_batch.status`，无批次按0。不得用另一分类批次、`is_completed` 推测值或报告 `PENDING/SUCCESS/FAILED` 替代。
- 通过条件：两分类0/1/2与无批次矩阵返回准确，并覆盖失败独立补偿置2；状态1时前端不发生 reset/start/navigation，状态0/2继续原 completed/restart/reset/start/navigation 链路，且状态2不得被接口或前端解释为完成；DEV-078 不改变 `is_completed` 的请求、响应、判断或数据，分类13旧调用兼容，分类14既有 report-entry 完成语义、报告三态和重试语义不变。
- 证据承接：Controller/API契约测试、服务层分类与用户过滤测试、前端请求快照及0/1/2交叉矩阵。
- 当前状态：通过（独立验收）；DEV-078整体待用户审核。
