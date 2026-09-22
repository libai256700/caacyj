# DEV-060 TDD 红灯证据

- 执行时间：2026-08-18（应用源码修改前）
- 命令：`node "doc/02-版本迭代/03-进行中版本/20260601000000-vphase1-initial-delivery/061-验收标准/03-测试验证/DEV-060/dev060-correct-result.spec.cjs"`
- 退出码：`1`
- 失败场景：正确单选普通题提交后保留当前题结果态。
- 关键断言：`correctSingle must retain 回答正确 on the submitted question; observed resultTitleCount=0, questionGetCount=2`
- 实际结果：正确结果标题不可见，题目 GET 从初始一次增至两次，证明旧逻辑在正确提交后自动请求下一题。
- 红灯有效性：断言检查真实页面状态与真实页面发出的请求次数，未使用人为恒失败断言。

关键输出：

```text
AssertionError [ERR_ASSERTION]: correctSingle must retain 回答正确 on the submitted question; observed resultTitleCount=0, questionGetCount=2

0 !== 1
```
