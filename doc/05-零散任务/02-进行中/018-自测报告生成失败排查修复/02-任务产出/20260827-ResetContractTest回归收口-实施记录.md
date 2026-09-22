# ResetContractTest 回归收口实施记录

## 结论

- `FrontPracticeAssessmentResetContractTest` 的失败均来自测试夹具过期或 Mockito 返回值绕过数据库查询条件，未发现生产代码的 reset、用户归属或 assessment 模式行为回归。
- 本次仅修正目标测试，未修改生产代码、前端或 `uni_modules/**`。

## 失败根因与修正

1. 5 个 error：测试反射注入已不存在的 `knowledgeProperties` 字段，生产实现已改为通过 `AiModelConfigService` 读取报告最小长度。删除无关注入，并仅在完整报告校验辅助方法中注入正式配置服务 mock。
2. 普通批次断言失败：`selectList(any())` 无条件返回普通批次，绕过了真实数据库对用户、分类、模式和完成态的过滤。恢复空查询结果，并捕获 Lambda 查询条件，明确断言用户 `9001`、分类 `13`、模式 `ASSESSMENT`、完成态 `true`。
3. 未完成批次断言失败：同样由 mock 直接返回未完成行导致。恢复数据库过滤后的空结果，并断言查询包含 `completed=true`，同时保留所有删除方法不得调用的断言。
4. 删除 SQL 校验参数数量错误：恢复对 `customer_account_id=9001`、`user_id=9001`、`record_id=201` 的精确参数断言。

## 命令结果

- 修复前：`mvn -pl yunjikeji-admin-server "-Dtest=FrontPracticeAssessmentResetContractTest" test` -> 9 个测试，1 failure、5 errors。
- 修复后：`mvn -pl yunjikeji-admin-server "-Dtest=FrontPracticeAssessmentResetContractTest" test` -> 9/9 通过。
- 历史关联回归曾记录合计 `47/47`；其中原 `FrontPracticeAssessmentRegenerateTest` 使用替身和内存库，其结果现已撤回，不再作为真实入口或真实落库证据。Reset 合同自身 `9/9` 结论不受本次替换影响。

## 影响与后续

- 未改变 reset、首次生成、重生成、报告 HTML 或数据库写入生产逻辑。
- 当前结果待独立验收代理复核后收口。
