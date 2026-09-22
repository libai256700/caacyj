# DEV-070 测试执行结论

## 当前结论

- 状态：TDD红灯已确认。
- 本任务只建立TDD红灯与分类13保护基线，不宣称 `AC-CAREER-ASSESS-*` 已通过。
- 数据库：未连接、未查询、未写入。
- 业务源码：未修改。

## 分层覆盖

| 层级 | 用例 | 目标 |
| --- | --- | --- |
| 交互级 | `TC-UI-CAREER-ASSESS-001` | 首页点击后选择层、整棵dialog事件树、自评原函数复用、取消零动作 |
| 接口级 | `TC-API-CAREER-ASSESS-101` | 分类13旧HTTP动词/path/参数/调用链保护、分类14平行接口和末题统一提交 |
| 数据级 | `TC-DATA-CAREER-ASSESS-201` | record-batch-category路由、Agent 3精确字段、同库与两手工工具事务隔离 |
| 代码级 | `TC-CODE-CAREER-ASSESS-301` | 分类13语义结构、控制流、真实调用链、mutation自证、禁区和边界 |

## 执行结果

- 分类13保护命令退出码 `0`，`passed=3 failed=0`：首页原函数控制流、非末题零提交、末题统一提交、旧前端服务签名/端点、后端精确HTTP注解/参数，以及Controller/Service到分类13、Agent2、`SelfAssessmentV3RuleEngine`真实调用链均通过。
- 内置mutation自证退出码 `0`：dialog根/遮罩/关闭/选项越界动作、HTTP动词/path/参数/调用链、异库或错误目标数据流、事务顺序、dry-run DML、rollback、id3冲突时机、题库计数和Agent全部固定字段等22个错误变体均被测试拒绝。
- 聚合红灯命令退出码 `1`：`passed=3 failed=7`，失败精确命中尚未实现的Story-052能力。
- 精确缺口：首页开始入口仍直接调用原自评；首页报告入口仍直接调用原自评报告；答题页和前端服务无分类14上下文；后端无分类14平行契约；题库工具和Agent工具均不存在，因此工具隔离前置不成立。
- 详细命令和原始摘要见 `command-results.md`。

## 当前判定

- 支持继续DEV-071至DEV-073实施；后续每次修改须先跑 protection suite，再跑 aggregate suite。
- 保护套件变红时必须先恢复分类13既有语义，不得通过放宽结构化断言掩盖业务改动。
- 功能转绿不等于正式AC通过；真实数据初始化、测试环境接口、Playwright交互和独立验收仍属后续任务。

## 后续实现文件白名单

- 前端：`code/develop/yunjikeji/src/pages/home.vue`、`src/pages/practice/self-test-answer.vue`、`src/services/assessment.ts`及确有必要的职业规划报告页/类型文件。
- 后端：`FrontPracticeController.java`、`FrontPracticeService.java`、`FrontPracticeServiceImpl.java`、新增职业规划规则类及其目标测试；必须合并DEV-049现有改动，不得覆盖。
- 手工工具：两个互相独立的Python文件及各自测试；不得接入业务、启动、build或migration。
- 禁止：`uni_modules/**`、数据库写入、与Story-052无关文件。
