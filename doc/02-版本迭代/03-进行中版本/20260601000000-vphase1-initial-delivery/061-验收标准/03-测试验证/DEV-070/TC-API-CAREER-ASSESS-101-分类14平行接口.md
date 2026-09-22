# TC-API-CAREER-ASSESS-101 分类14平行接口

## 1. 测试层级

`接口级`

## 2. 对应验收项

- 验收项 ID：`AC-CAREER-ASSESS-002/101/202`
- 正式验收入口：`../../01-验收执行详情/AC-CAREER-ASSESS-101.md`

## 3. 前置条件

- 环境前置：只读源码；不启动服务、不写数据库。
- 账号前置：无。
- 数据前置：分类13为保护基线，分类14为目标红灯。

## 4. 测试数据

`categoryId=14`；旧无参 completed/latest-status/reset 与旧 regenerate、start、record/report 契约。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 执行 protection suite | completed/latest-status/records/detail为精确GetMapping；reset/regenerate/start为精确PostMapping；唯一path、参数声明、响应及Service调用保持绿色 |
| 2 | 执行 feature suite | 分类14存在显式分类上下文的平行前后端能力 |
| 3 | 检查提交时机 | 非末题零提交，末题统一提交并携带分类上下文 |

## 6. 期望结果

- 当前分类13保护基线通过。
- 当前因分类14平行接口不存在而红灯。

## 7. 脚本入口

- 自动化脚本：`dev070-contract.mjs`
- 依赖命令：Node.js
- 结果输出位置：`command-results.md`

## 8. 失败判定

- 修改旧无参分类13签名或语义。
- 旧Controller发生GET/POST互换、path属性或参数注解变化，或Service调用与参数不一致。
- 分类14没有显式 `categoryId=14`，或翻页时提交答案。
