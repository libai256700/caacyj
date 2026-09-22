# DEV-011 测试执行结论

## 执行范围

- 业务：后台错题管理首次进入与重置默认 `is_correct=false`，用户主动选择“不限”时不传 `is_correct`
- 接口：后端 where 条件区分默认 `false` 与用户主动清空
- 数据：默认值只落在错题管理资源，不扩散到其他资源页
- 代码：`resetDynamicQuery`、`buildParams`、资源监听顺序共同保证默认错题筛选时序

## 执行结果

| 验证项 | 命令 / 入口 | 结果 |
| --- | --- | --- |
| AC-ADMIN-WRONG-101 | `mvn '-Dtest=UserPracticeExercisesRecordSqlContractTest' test` | 通过；后端 `6/6`，`false` 与空串分支同时被断言 |
| AC-ADMIN-WRONG-201 | `python verify_wrong_question_default_filter.py` | 通过；`queryDefaultValue=false` 仅存在于 `practice-record-detail.is_correct` |
| AC-ADMIN-WRONG-301 | `python verify_wrong_question_default_filter.py`、`pnpm exec eslint ...`、`pnpm build:testhost`、`git diff --check` | 通过；默认值读取、重置时序、请求参数构建、构建与禁区检查均成立 |
| AC-ADMIN-WRONG-001 | 交互级 Playwright 复验 | 未执行；当前 UI 包无 Playwright 依赖，且仅证明本地 Vite 页面骨架可达，未证明无登录即可进入错题管理正式页 |

## 证据边界

- 本轮未修改 `code/**`、验收标准、计划、数据库或 `uni_modules/**`
- 本轮未伪造浏览器交互、登录态、网络请求或真实错题数据
- `git diff --check` 的输出仅为工作区既有 CRLF 警告，不构成本任务新增格式错误

## 当前结论

- `AC-ADMIN-WRONG-101`、`AC-ADMIN-WRONG-201`、`AC-ADMIN-WRONG-301` 已具备正式本地证据
- `AC-ADMIN-WRONG-001` 仍待具备正式 Playwright 依赖与可进入页面的运行态后补交互级证据
- 因交互级未闭环，本轮测试结论为：`部分通过`
