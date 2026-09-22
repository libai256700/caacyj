# DEV-078 红灯命令回执

## 1. 基线

- 命令：`mvn -pl yunjikeji-admin-server '-Dtest=FrontPracticeServiceImplBatchStartContractTest,CareerAssessmentIsolationContractTest' -DfailIfNoTests=false test`
- 退出码：`0`
- 结果：`Tests run: 16, Failures: 0, Errors: 0, Skipped: 0`。

## 2. DEV-078 后端红灯

- 命令：`mvn -pl yunjikeji-admin-server '-Dtest=AssessmentBatchSaveStatusContractTest,FrontPracticeServiceImplBatchStartContractTest,CareerAssessmentIsolationContractTest' -DfailIfNoTests=false test`
- 工作目录：`code/develop/yunjikeji-admin-server`。
- 退出码：`1`（预期红灯）。
- 汇总：`Tests run: 23, Failures: 7, Errors: 0, Skipped: 0`。
- 既有保护：`FrontPracticeServiceImplBatchStartContractTest` 10项通过，`CareerAssessmentIsolationContractTest` 6项通过。
- 关键失败：批次DO缺少 `status`、latest-status DTO缺少 `batchSaveStatus`、startBatch缺少显式0、首条明细前条件置1缺失、分类13/14完成点置2缺失、失败后独立事务置2缺失、分类14独立 latest-status 缺失。

## 3. DEV-078 前端红灯

- 命令：`node "E:\huiyitechworkspace\feixingxueyuan\doc\02-版本迭代\03-进行中版本\20260601000000-vphase1-initial-delivery\061-验收标准\03-测试验证\DEV-078\dev078-contract.mjs"`
- 工作目录：`code/develop/yunjikeji`。
- 退出码：`1`（预期红灯）。
- 汇总：`SUMMARY passed=0 failed=3`。
- 关键失败：self latest-status类型缺少 `batchSaveStatus`；首页缺少精确保存提示与独立弹窗状态；`startSelfTest` 未先查询分类13保存状态。职业入口/API亦由聚合契约覆盖，当前首个缺失断言即终止对应组。
- 脚本语法：`node --check .\dev078-contract.mjs`，退出码 `0`。
- 说明：首次以错误相对路径执行产生 `MODULE_NOT_FOUND`，已纠正为绝对路径重跑；错误命令不计入红灯证据。

## 4. DEV-070 保护脚本

- 命令：`node .\dev070-contract.mjs --suite=protection`
- 工作目录：`061-验收标准/03-测试验证/DEV-070`。
- 退出码：`1`（并行基线偏差，非DEV-078测试改动）。
- 结果：前端分类13语义与答题/service保护两组通过；Java保护组失败，原因是当前并行修改后的 `FrontPracticeServiceImpl.submitAnswer` 已不再包含旧 `isAssessmentSession` 调用，DEV-070仍要求该调用顺序。
- 处置：未修改或回退生产代码，也未改写DEV-070脚本；交由对应实施/验收代理处理该并行保护偏差。

## 5. Diff 检查

- 命令：`git diff --check`
- 退出码：`0`；仅输出其他并行文件的LF/CRLF转换提示，无空白错误。
- DEV-078专属命令：`git diff --check -- <DEV-078后端测试> <DEV-078测试资产目录>`，退出码 `0`。
- 行尾扫描：`rg -n "[ \t]+$" <DEV-078后端测试> <DEV-078测试资产目录>`，退出码 `1`且无输出。
- 禁区审计：`git status --short -- ':(glob)**/uni_modules/**'`，退出码 `0`且无输出。
