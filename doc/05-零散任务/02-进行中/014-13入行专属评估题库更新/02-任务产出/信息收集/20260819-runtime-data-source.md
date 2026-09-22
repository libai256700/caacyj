# T0014 自我测评运行态数据源核对

- 核对时间：2026-08-19
- 核对方式：正式连接记录、当前进程与配置、真实库只读事务、代码调用链、既有 T0014 证据交叉核对
- 数据库动作：仅 `SELECT`、`SHOW`，会话使用 `START TRANSACTION READ ONLY`，无任何写操作
- 结论状态：已定位截图 `1/59 + 无人机的英文缩写是` 的唯一数据组合与代码路由；截图本身不含请求地址，因此实际截图请求所连进程仍需网络请求记录才能做 100% 环境绑定

## 1. 结论

1. T0014 更新的数据没有丢失。正式 Local 记录对应的测试库 `yunjikeji` 中，分类 `13`、租户 `1` 当前为 6 个启用步骤、48 道启用题、243 个启用选项；48 道题全部关联有效步骤。
2. 截图中的 59 道题来自同库的普通练习分类 `category_id=1`（分类名“概述”），不是分类 13。该分类恰好 59 道启用题，首题 `id=5591`，题干正是“无人机的英文缩写是”，题目租户为 `0`，`step_id` 为空。
3. 根因是自我测评启动请求被当前后端路由成了普通练习：前端传 `mode=standard、topicId=assessment`，后端把 `standard` 归一化为 `PRACTICE`；普通练习批次服务只查 `catalog_type=0`，匹配不到 `assessment` 后回退到排序第一的普通分类 1，因此创建 59 题批次。
4. `yj_practice_setp` 页面看不到不是“表里没有数据”，而是“接口不返回 + 前端不渲染”。当前题目响应对象没有 `stepId/stepName/stepSort`，自测前端模型和页面也没有步骤字段或步骤 UI。即使正确加载分类 13，现有页面仍只会平铺 48 题。

## 2. 环境与正式入口

| 口径 | 正式事实 | 本次证据 | 结论 |
| --- | --- | --- | --- |
| Local | 远端测试库 `114.111.30.111:13306/yunjikeji`，用途为本地配置测试库 | `C:\Users\renquan\.devcenter\Operations\ApplicationConnections\Local\applications.md`；`application-local.yaml`；当前 PID 29492 监听 48080 并建立到该端点的连接 | 此前 T0014 验收库，也是本次只读复核库 |
| Test | `127.0.0.1:13306/yunjikeji` | `C:\Users\renquan\.devcenter\Operations\ApplicationConnections\Test\applications.md` | 正式记录为本机入口，本次未作为运行进程实际连接 |
| Dev | 无本项目连接事实 | `Dev/applications.md` 只有模板 | 不允许据此猜环境或连接 |
| Prod | 无本项目连接事实 | `Prod/applications.md` 只有模板 | 不允许据此猜环境或连接 |
| App 生产构建 | API 配置为 `https://yunjikeji.lai-do.com/yunjikeji-admin-api` | `code/develop/yunjikeji/.env.production` | 正式连接中心缺少其后端数据库入口，不能只凭仓库配置对生产库下结论 |

既有 T0014 快照 `current-target-snapshot.json` 记录的采集进程、`local` profile 和 `114.111.30.111:13306/yunjikeji` 与本次正式记录一致。最新只读复核再次得到分类 13 为 6 步、48 题。

## 3. 59 道旧题的来源

### 3.1 数据对照

| 项目 | 分类 13 目标自测 | 截图对应旧题集 |
| --- | --- | --- |
| 分类 | `id=13`，入行专属评估 | `id=1`，概述 |
| 分类类型 | `catalog_type=1` 自测 | `catalog_type=0` 普通练习 |
| 分类租户 | `tenant_id=1` | 分类行为 `tenant_id=1` |
| 题目租户 | `tenant_id=1` | `tenant_id=0` |
| 启用题数 | 48 | 59 |
| 首题 | 您当前的身份状态是？ | 无人机的英文缩写是 |
| 步骤 | 6 步，48 题全部有效关联 | 59 题 `step_id` 均为空 |

真实库只读查询还发现历史批次 `id=8`、`id=13` 都是 `category_id=1`、`mode=PRACTICE`、`total=59`，其第一条批次题均指向原题 `id=5591`“无人机的英文缩写是”。这与截图的总题数和首题形成完整指纹。

### 3.2 代码调用链

1. 前端自测固定参数位于 `code/develop/yunjikeji/src/services/assessment.ts:80-83`，实际启动调用位于 `:237-238`：`standard + assessment`。
2. `FrontPracticeServiceImpl.java:356-362` 调用 `normalizeStartMode` 后进入普通练习批次服务；`:417-419` 明确把 `standard` 返回为 `PRACTICE`。
3. `FrontPracticeBatchService.java:792-803` 先尝试按 topic 匹配，失败后回退普通练习分类第一项。
4. `FrontPracticeBatchService.java:938-955` 把可匹配分类硬限制为 `catalog_type=0`，所以自测分类 13（`catalog_type=1`）不可能匹配 `assessment`。
5. `FrontPracticeBatchService.java:884-895` 随后仅按选中的 `category_id=1` 取题，得到 59 道旧题。该查询没有显式租户条件，配合接口的 `@TenantIgnore`，因此会取到该分类下 `tenant_id=0` 的旧题。

该路由由提交 `c82df1657`（2026-08-18 16:10，`fix: align practice batch wrong-answer flow`）引入；其父版本的标准自测路径会调用 `listPracticeExerciseIds("assessment")`，按 `catalog_type=1` 选题。

## 4. `yj_practice_setp` 为什么看不到

| 层级 | 核对结果 | 证据结论 |
| --- | --- | --- |
| 数据库 | 6 条启用步骤存在：基础画像、核心量表、主要顾虑、报告目标、补充模块、确认提交；48 道分类 13 题全部通过 `step_id` 有效关联 | 不是“数据库没有 step 数据” |
| 当前截图批次 | 实际选中分类 1 的 59 道旧题，全部无 `step_id` | 错误分类本身没有可展示步骤 |
| 接口 | `AppPracticeQuestionItemRespVO` 只有 id/type/title/stem/score/options；`getQuestion` 不查询或返回步骤 | 属于“接口没有返回 step” |
| 前端 | `AssessmentQuestion` 没有步骤字段；`self-test-answer.vue` 只展示题数、题型、题干、选项 | 属于“前端没有渲染 step” |

因此即使只修正分类选择为 13，页面会从 59 道旧题变成 48 道新题，但六步仍不会显示；要显示步骤，还需要扩展接口契约和前端分步展示。

## 5. 自我测评数据保存在哪些表

“自我测评保存表”不是单表，按生命周期分层如下：

| 数据 | 主表 | 关联表/说明 |
| --- | --- | --- |
| 自测分类定义 | `yj_practice_category` | 分类 13 的 `catalog_type=1` |
| 自测步骤定义 | `yj_practice_setp` | 通过题目 `step_id` 反向关联；步骤表本身没有 `category_id` |
| 自测题目 | `yj_practice_exercises` | 分类 13、租户 1；选项在 `yj_practice_exercises_answer`，子选项在 `yj_practice_exercises_answer_child` |
| 启动后的题目批次 | `yj_practice_catalog_batch` | 批次题在 `yj_practice_exercises_batch`，批次选项快照在 `yj_practice_exercises_answer_batch` |
| 用户答题主记录 | `yj_user_practice_exercises_record` | 每题作答在 `yj_user_practice_exercises_record_detail`；错题另在 `yj_user_practice_exercises_wrong_record_detail` |
| 最终自测报告 | `yj_assessment_result` | `FrontPracticeServiceImpl` 完成自测后写入报告内容并按用户/记录查询 |

## 6. 最小修复边界

1. 自我测评 `standard + assessment` 必须走自测分类选择，明确限定 `catalog_type=1`，最好进一步固定或唯一解析分类 13，不得回退普通分类第一项。
2. 题目查询必须显式带目标分类与租户边界，不能依赖 `@TenantIgnore` 后只按 `category_id` 查询。
3. 如本次验收要求六步可见，需要给题目接口补 `stepId/stepName/stepSort`，并由前端按步骤分组或显示当前步骤；这属于接口与页面改造，不是继续改数据库可以解决。
4. 修复后需从真实自测入口复验：总数 48、首题“您当前的身份状态是？”，并验证六步 UI 是否按明确验收口径展示。

## 7. 证据边界与止损点

- 当前截图的 `59 + 首题` 与正式 Local 测试库中的分类 1 及历史批次完全一致，代码路由也能确定性产生该结果，足以定位数据源选择错误。
- 截图未携带 URL、请求头、响应体或服务端请求日志；生产 API 对应数据库在正式连接中心缺失。因此不能把截图 100% 声称为某个生产/测试进程的单次请求。若需要做最终环境归属，只需补一条最小证据：截图复现时 `/app-api/yj/practices/uav-basic-001/start?mode=standard&topicId=assessment` 的请求地址与响应中的 `catalogBatchId/categoryId/total`。
