# AC-SELFTEST-301 自测可选题实现边界

- 类型：技术-代码级
- 正式入口：`code/develop/yunjikeji/src/pages/practice/self-test-answer.vue`、`src/services/assessment.ts`、`src/services/practice.ts`。
- 通过条件：只在自测页面依据 `isRequired` 放宽非必填校验并追加“（选填）”；普通练习页面行为不变；类型检查通过；不修改 `uni_modules/**`。
- 证据承接方式：源码契约、`npm run type-check` 与差异检查结果写入 `061-验收标准/03-测试验证/DEV-066/`。
