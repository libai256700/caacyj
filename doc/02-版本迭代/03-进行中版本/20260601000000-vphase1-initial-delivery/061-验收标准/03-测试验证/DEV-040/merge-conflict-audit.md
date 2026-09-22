# DEV-040 同步冲突实施证据

## 初始 Git 状态审计

- 审计时间：2026-07-18（Asia/Shanghai）
- 当前分支：`feature/20260601000000-vphase1-initial-delivery`
- 当前提交：`2687d5da87dfe8c096857379997ca5b5be793486`
- 上游关系：`origin/feature/20260601000000-vphase1-initial-delivery`，本地 `+0/-3`
- `git diff --name-only --diff-filter=U`：无输出
- `git ls-files -u`：无输出，因此不存在可读取的 stage 1/2/3 冲突 blob
- `MERGE_HEAD`：不存在
- `REBASE_HEAD`：不存在
- `CHERRY_PICK_HEAD`：不存在
- 初始判断：当前不处于 merge、rebase 或 cherry-pick 冲突态；不能假设 ours/theirs 语义。后续以当前 `HEAD` 为共同基线，分别审计本地工作树与上游 3 个提交，再逐块整合，不使用整文件 ours/theirs 覆盖。

## 初始工作区保护结论

- 工作区存在 DEV-040 页面/路由修改、后端及其他用户脏改。
- 存在未跟踪锁文件、dump、temp 等范围外资产；本次不触碰。
- `uni_modules/**` 未出现在初始状态中；本次禁止触碰。

## 冲突文件与 stage 来源

初始索引无实际 unmerged 文件、无 stage 来源。若后续发现同步已被手工落入工作树，则按 `HEAD`（共同基线）、当前工作树（本地页面/DEV-040）与上游提交（同事短信业务）三方逐块记录。

## 上游来源与逐块取舍

- 同事短信业务提交：`1f50accd606d459a2008081e88604cc5107f866c`（`feat: wire app sms verification login`）。
- 后续上游提交 `51e38828` 仅收口 DEV-039 文档，不属于本次短信业务实施范围。
- `login.vue`：保留当前页面模板骨架、背景、配图、尺寸、边距、按钮布局、响应式 CSS 与 `.login-hero` 层级；仅把验证码输入约束、发送入口、60 秒倒计时、`codeCountdown/loginLoading` 互斥 guard、禁用态和文案映射到现有控件。同事提交中删除 `.login-hero,` 选择器的视觉变化不合入。
- `login.vue` 路由：保留 DEV-040 条件顺序；企业已有岗位、企业审核通过均使用 `redirectUrl || '/pages/home'`，学员及最终默认入口保持既有条件分支并落到 `/pages/home`。
- `customerAuth.ts`：保留并导出 `sendLoginSmsCode`，场景值使用同事提交的会员登录场景 `1`；学员、企业两处 fallback 统一采用短信业务语义“手机号或验证码错误”，不保留工作树中的旧“手机号或密码错误”。
- 企业与学员请求 VO：把密码字段的展示和校验语义改为 6 位数字短信验证码；字段名继续沿用现有接口契约 `password`。
- 企业与学员登录服务：登录/注册前消费 `SmsSceneEnum.MEMBER_LOGIN` 验证码，移除存量账号密码比对；学员登录渠道改为 `app-sms`。
- `application.yaml`：仅合入短信业务必需的 `begin-code: 100000` 与 `end-code: 999999`；当前 DeepSeek 连接、模型及 assessment 配置原样保留，未猜测或改写环境连接事实。

## 最终保留清单

- 同事短信业务：短信发送 API、60 秒倒计时、互斥 guard、发送 disabled/`@tap`/动态文案、6 位验证码前后端校验、后端验证码消费、短信登录渠道、验证码错误语义。
- 本地页面：既有 DOM 骨架、所有非短信状态 CSS、背景与图片、尺寸与间距、按钮布局、响应式规则、`.login-hero` 层级。
- DEV-040：`redirectUrl` 优先；企业岗位/审核、学员绑定/审核条件顺序未调整；2 处带 redirect 的默认 `/pages/home` 与 1 处最终默认 `/pages/home` 保留。
- 用户脏改：`application.yaml` 中短信区块以外的本地连接/模型配置未覆盖；范围外页面、后端、锁文件、dump、temp 和 `uni_modules/**` 均未触碰。

## 静态与构建证据

- 受控源码与 DEV-040 证据目录冲突标记扫描：0。
- 静态契约计数：发送 `@tap` 1 处、60 秒初始化 1 处、互斥 guard 1 处、`redirectUrl || '/pages/home'` 2 处、最终 `'/pages/home'` 1 处、`.login-hero,` 选择器 1 处。
- 与 `1f50accd` 对照：4 个后端文件及 `customerAuth.ts` 无业务差异；`login.vue` 仅保留 3 处 DEV-040 路由和 `.login-hero` 视觉层级；`application.yaml` 仅保留短信区块外的本地 DeepSeek 配置差异。
- `pnpm type-check`：退出码 0，通过。
- `pnpm run build:h5`：退出码 1；在加载 `vite.config.ts` 时因系统工具链 `spawn EPERM` 失败，未进入源码编译。
- esbuild 止损诊断：已定位 0.20.1 与 0.20.2 的 `@esbuild/win32-x64/esbuild.exe`；直接执行 `--version` 均在 10 秒内无法返回并超时，因此不设置 `ESBUILD_BINARY_PATH`、不继续枚举工具链方案。
- `mvn -pl yunjikeji-admin-server -am -DskipTests compile`：退出码 0，39/39 Reactor 模块成功，目标模块重新编译 191 个源文件。
- Playwright：未执行。原因是当前 H5 构建失败，现有静态产物不能证明包含本次最新短信合并，避免用旧产物形成错误证据。

## 7 个业务文件精确差异清单

以下统计均相对当前 `HEAD 2687d5da`，状态均为未暂存 `M`：

- `AppCompanyAuthRegisterReqVO.java`：`+3/-4`；密码展示与 `@Size` 校验替换为 6 位数字短信验证码 `@Pattern`。
- `CompanyAuditServiceImpl.java`：`+15/-3`；注入 `SmsCodeApi`、登录前消费会员登录验证码、移除已有企业账号密码匹配。
- `AppCustomerAuthRegisterReqVO.java`：`+3/-4`；密码展示与 `@Size` 校验替换为 6 位数字短信验证码 `@Pattern`。
- `CustomerServiceImpl.java`：`+17/-5`；注入并消费 `SmsCodeApi`、移除已有学员密码匹配、登录渠道由 `app-password` 改为 `app-sms`。
- `application.yaml`：`+10/-5`；其中本次短信业务精确 hunk 仅为 `begin-code 9999 -> 100000`、`end-code 9999 -> 999999`，其余 `+8/-3` 为任务前已存在的 DeepSeek/assessment 用户脏改，已保留且未暂存。
- `login.vue`：`+68/-17`；短信输入/发送/倒计时/互斥/禁用态与错误映射，加上任务前 DEV-040 的 3 处 `/pages/home` 路由；既有视觉结构未替换。
- `customerAuth.ts`：`+14/-0`；新增短信发送服务与常量；相对 `HEAD` 的错误语义本已是“手机号或验证码错误”，最终继续保持该语义。

## 最终 Git 状态

- `git diff --check`：退出码 0。
- 活动 Git 操作：无；`MERGE_HEAD`、`REBASE_HEAD`、`CHERRY_PICK_HEAD` 均不存在。
- unmerged 文件：0；stage 1/2/3：0。
- 暂存文件：0。当前无 U 文件，无需用 `git add` 标记 resolved；按主代理收口要求不暂存业务、配置或证据文件。
- 当前分支相对上游：`+0/-3`。

## 2026-07-19 独立验收复核

- 复核结论：冲突解决通过，H5/Playwright 待环境复验。
- Git：`HEAD=2687d5da87dfe8c096857379997ca5b5be793486`；`MERGE_HEAD`、`REBASE_HEAD`、`CHERRY_PICK_HEAD` 均不存在；U 文件、stage 1/2/3、暂存文件均为 0；`code/` 与 `doc/` 精确冲突标记扫描为 0。
- 同事 7 文件：`AppCompanyAuthRegisterReqVO.java`、`CompanyAuditServiceImpl.java`、`AppCustomerAuthRegisterReqVO.java`、`CustomerServiceImpl.java`、`application.yaml`、`login.vue`、`customerAuth.ts`。
- 三方一致性：四个后端文件及 `customerAuth.ts` 与 `1f50accd` 逐字一致；`login.vue` 仅保留 `HEAD` 视觉层级、DEV-040 三处首页路由及短信绑定必需的最小差异；`application.yaml` 相对同事提交仅保留任务前 DeepSeek/assessment 本地键。
- 登录视觉：相对 `HEAD` 的 class 集合无差异；`.login-hero`、模板骨架、背景、配图、尺寸、边距和响应式规则保留；新增 CSS 仅为验证码发送禁用态。
- DEV-040：`homeReady` 根 `v-if` 防闪现、启动页首页落点、答题无栈返回测评和完成返回首页均保留；首页三入口及测评/答题控件条件无变化。
- 质量结果：`pnpm type-check` exit `0`；后端 Maven 39/39 Reactor 模块 `BUILD SUCCESS`；`git diff --check` exit `0`。
- 环境边界：未重复执行 H5 构建或 Playwright；引用既有原 esbuild binary 与 Temp 副本 `--version` 均超时的操作系统级证据，待环境恢复后复验。
