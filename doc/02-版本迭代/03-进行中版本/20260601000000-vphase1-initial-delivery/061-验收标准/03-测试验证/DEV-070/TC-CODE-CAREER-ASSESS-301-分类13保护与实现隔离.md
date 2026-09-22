# TC-CODE-CAREER-ASSESS-301 分类13保护与实现隔离

## 1. 测试层级

`代码级`

## 2. 对应验收项

- 验收项 ID：`AC-CAREER-ASSESS-001/002/101/201/202/301`
- 正式验收入口：`../../01-验收执行详情/AC-CAREER-ASSESS-301.md`

## 3. 前置条件

- 环境前置：当前工作区含DEV-049并行暂存改动，测试不得覆盖或夹带。
- 账号前置：无。
- 数据前置：DEV-070开始时分类13真实接口、控制流、导航、提交时序和Agent2/V3调用链。

## 4. 测试数据

保护对象：`startSelfTest`、`openLatestSelfTestReport`、`goNext`、`submitCurrent`、`assessment.ts`旧无参/原参数服务以及后端分类13常量与Controller。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | Vue SFC与TypeScript AST解析 | 两个首页原函数的守卫、确认/重置、异常、finally、导航语义保持；格式和注释变化不触发失败，行为字面量变化可被识别 |
| 2 | 控制流检查 | 非末题分支先goNext并return，提交调用只在其后 |
| 3 | 接口签名与Java结构树检查 | 旧无参接口不加分类参数，精确HTTP动词/path/参数/响应/Service调用不变，分类13仍经批次服务、Agent2和V3规则调用链执行 |
| 4 | 内置mutation自证 | dialog事件越界、HTTP动词/path/参数/调用链、同库/事务/Agent/题库关键变体均被拒绝 |

## 6. 期望结果

- 当前保护套件退出码0。
- 后续功能实现不得通过修改分类13内部逻辑让红灯转绿。

## 7. 脚本入口

- 自动化脚本：`node dev070-contract.mjs --suite=protection`
- 依赖命令：Node.js及前端现有编译依赖
- 结果输出位置：`command-results.md`

## 8. 失败判定

- 两个原函数的既有行为、调用顺序、导航、异常或状态复位变化。
- 非末题发生提交，旧服务签名或分类13路由变化。
