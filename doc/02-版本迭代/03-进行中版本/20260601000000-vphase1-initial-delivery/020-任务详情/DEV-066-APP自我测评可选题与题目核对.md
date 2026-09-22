# DEV-066 APP自我测评可选题与题目核对

## 实施标准

- 自测流程使用真实题目响应中的 `is_required`，同时兼容后端序列化为 `isRequired`；缺失字段按必填处理，避免普通题意外放空。
- 仅自测分类 `category_id=13` 的非必填题允许空答案进入下一题和最终提交；普通练习页面行为不变。
- 自测题干在 `is_required=false` 时追加“（选填）”，必填题不追加。
- 题库核对以 `https://caacyj.com/` 的 B1-E2 为外部参照；截图红框 sort_no 28-42 与网站逐字一致，为动态模块题，保留 15 题，不执行删除。
- 不修改 `uni_modules/**`，不以假数据或本地题目替代真实接口响应。

## 对应技能

- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- `code/develop/yunjikeji/src/services/practice.ts` / `assessment.ts` 的字段链路。
- `code/develop/yunjikeji/src/pages/practice/self-test-answer.vue` 的自测可选题交互。
- `AC-SELFTEST-001`、`AC-SELFTEST-101`、`AC-SELFTEST-201`、`AC-SELFTEST-301`、`AC-SELFTEST-401` 正式验收入口及 `061-验收标准/03-测试验证/DEV-066/` 测试资产。

## 分支安排详情

- 沿用当前版本实际分支 `feature/20260601000000-vphase1-initial-delivery`。
- 前端源码白名单仅限自测答题页及其题目类型透传服务；不得修改后端 Java、`uni_modules/**` 或无关页面。

## 关联验收项

- 业务验收：`AC-SELFTEST-001`
- 技术验收：`AC-SELFTEST-101`、`AC-SELFTEST-201`、`AC-SELFTEST-301`
- 闭环项：`AC-SELFTEST-401`

## 任务产出 / 结果记录

- 2026-08-21 完成 `is_required` / `isRequired` 兼容透传；缺失值默认必填。
- 2026-08-21 完成自测非必填题空答放行及题干“（选填）”展示；普通练习页未改动。
- 2026-08-21 外部网站核对结论：B1-E2 对应红框 sort_no 28-42 共 15 题，与 caacyj.com 逐字一致，保留，不删除。
- 2026-08-21 本地验证：`npm run type-check` 通过（退出码 0）；测试环境接口、数据及浏览器交互尚未执行。

## 进度总结

- 当前状态：待测试环境验收。
- 当前阶段：静态独立验收通过，等待测试环境接口、数据及浏览器交互复核。
- 未解决风险：需在测试环境确认真实响应字段命名、`category_id=13` 的题目数量与空答入库结果；不得仅凭本地静态检查宣称验收通过。
