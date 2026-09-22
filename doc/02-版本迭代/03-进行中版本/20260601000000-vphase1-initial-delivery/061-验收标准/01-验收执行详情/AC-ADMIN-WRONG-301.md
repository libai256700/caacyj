# AC-ADMIN-WRONG-301 后台错题管理实现边界与代码回归控制

- 类型：技术-代码级
- 关联任务：`DEV-011`
- 正式入口：`code/develop/yunjikeji-admin-ui/src/views/yj/resource/config.ts`、`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/practice/service/UserPracticeExercisesRecordServiceImpl.java`、`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/practice/controller/UserPracticeExercisesRecordController.java`。
- 支撑结果：前端后台资源配置、后端分页查询和详情查询只改动错题管理这一条链路，不引入第二套 `DEV-011`，也不影响练习记录列表和其它练习资源。
- 技术边界：不修改 `uni_modules/**`；不新增数据库脚本；实现只围绕列展示、筛选语义、题干关联、`COUNT` / list 共用 SQL、以及详情按钮按行 `id` 工作展开；`is_correct` 采用字段级三态配置，默认值必须只落在错题管理这一条资源链路上，不能通过全局 switch 默认值、全局组件副作用或其他资源页共享配置实现“首次进入/重置默认 false”。
- 通过条件：前端静态检查、后端聚焦测试、构建与 Playwright 交互验收全部通过；列表列名、筛选条件、详情按钮和分页行为与正式口径一致；`git diff --check` 无格式问题；任何与 `uni_modules/**` 相关的变更都不得出现；页面首次进入与重置后默认查询为 `false`，用户主动选“不限”时不带出 `d.is_correct` 过滤，且默认值没有扩散到其他资源页。
- 证据承接方式：前端静态检查、后端聚焦测试、构建结果和 Playwright 交互结果回写 `061-验收标准/03-测试验证/DEV-011/`。
