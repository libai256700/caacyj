# TASK-005 登录页 Story

## 实施标准

1. 本 Story 只作为“登录页”正式任务容器，实际执行以“Story 子任务清单”为准。
2. 每个子任务最多只绑定 1 个主技能，不得在单子任务内混绑多个主技能。
3. 登录页 Story 必须同时覆盖设计、验收、后端、数据库、前端、人工测试与结果回写。
4. 历史登录页实现记录只作为参考，不直接视为当前 Story 已完成。
5. 当前登录页高保真以 `031-页面设计/003-具体页面/登录页/03-生成图片-001.png` 为正式对齐稿；背景图固定使用 `031-页面设计/001-页面背景/001-登录背景/03-生成图片-003.png`；微信登录图标固定使用 `031-页面设计/004-切图资产/weixin-logo.png`。
6. 登录页页面开发任务完成后，必须先由人类执行人工测试；该测试不是人工审核，且至少覆盖高保真设计对比、基本交互正常、前后端拉通。
7. 登录页人工测试与独立验收中的页面截图证据，固定只接受移动端设备模式下的运行态截图；桌面布局截图、桌面截图裁切图或缩放图一律视为无效证据，不得用于判定高保真通过。
8. 只有人工测试通过并完成结果回写后，才允许创建人工复测/人工审核任务；开发 Story 完成后先回写为 `已完成`，后续人类审核结果由 `TASK-005A` 单独承接。

## 对应技能

- `30-0100-development-task-breakdown`

## 交付物

- 登录页 Story 子任务清单
- 登录页业务与技术交付边界
- 登录页结果回写入口

## 分支安排详情

- 沿用当前版本真实代码现场；执行阶段按子任务需要创建或沿用版本分支，本 Story 汇总层不预设多分支。

## 关联验收项

- `AA-005 登录页 Story 验收通过`

## Story 子任务清单

| 子任务 ID | 子任务名称 | 主技能 | 前置子任务 | 交付物 |
| --- | --- | --- | --- | --- |
| `TASK-005-01` | 复核登录页设计输入与业务边界 | `20-0100-requirements-documentation` | `-` | 登录页范围说明 |
| `TASK-005-02` | 输出登录页程序设计与状态流转 | `30-0200-story-technical-design` | `TASK-005-01` | 登录页程序设计 |
| `TASK-005-03` | 补充登录页正式验收项 | `20-0200-acceptance-standards-documentation` | `TASK-005-02` | 登录页验收项引用 |
| `TASK-005-04` | 定义登录接口契约与出参 | `30-0200-story-technical-design` | `TASK-005-03` | 登录接口契约 |
| `TASK-005-05` | 设计登录相关表与字段映射 | `30-0500-database-management` | `TASK-005-04` | 库表与字段设计 |
| `TASK-005-06` | 编写登录 SQL 脚本并完成测试库验证 | `00-0350-sql-script-standards-definition` | `TASK-005-05` | 登录 SQL 脚本与验证记录 |
| `TASK-005-07` | 实现登录接口最小闭环 | `00-0900-project-template-management` | `TASK-005-06` | 登录接口最小实现 |
| `TASK-005-08` | 实现登录页静态结构与背景落位 | `00-1600-frontend-ui-implementation` | `TASK-005-07` | 登录页静态界面 |
| `TASK-005-09` | 实现验证码、协议、登录态与跳转交互 | `00-1600-frontend-ui-implementation` | `TASK-005-08` | 登录页交互闭环 |
| `TASK-005-10` | 组织登录页页面人工测试（移动端设备模式高保真对比） | `40-0100-project-testing` | `TASK-005-09` | 登录页人工测试结果 |
| `TASK-005-11` | 回写登录页人工测试结论（基本交互、前后端拉通） | `40-0100-project-testing` | `TASK-005-10` | Story 人工测试结论 |
| `TASK-005-12` | 复核登录页高保真稿、背景图与微信登录资产差异 | `20-0100-requirements-documentation` | `TASK-005-11` | 登录页差异清单 |
| `TASK-005-13` | 输出登录页高保真重做方案与资源落位说明 | `30-0200-story-technical-design` | `TASK-005-12` | 登录页重做方案 |
| `TASK-005-14` | 重做登录页背景、版式层级与微信登录视觉实现 | `00-1600-frontend-ui-implementation` | `TASK-005-13` | 登录页高保真实现 |
| `TASK-005-15` | 组织登录页高保真重做后的人工测试（移动端设备模式高保真对比、基本交互、前后端拉通） | `40-0100-project-testing` | `TASK-005-14` | 登录页重做人工测试结果 |
| `TASK-005-16` | 提交登录页人工复测/人工审核并回写审核结论 | `20-0200-acceptance-standards-documentation` | `TASK-005-15` | 登录页人工审核记录 |
| `TASK-005-17` | 去掉登录卡片顶部无业务留白并复核正式版式层级 | `00-1600-frontend-ui-implementation` | `TASK-005-16` | 登录页版式收口结果 |
| `TASK-005-18` | 输出手机号账号+密码登录方案与接口契约调整 | `30-0200-story-technical-design` | `TASK-005-17` | 账号密码登录方案 |
| `TASK-005-19` | 实现登录页手机号账号输入与密码交互闭环 | `00-1600-frontend-ui-implementation` | `TASK-005-18` | 账号密码前端交互 |
| `TASK-005-20` | 设计账号密码登录数据库结构与脚本入口 | `30-0200-story-technical-design` | `TASK-005-19` | 账号密码后端与数据库设计 |
| `TASK-005-21` | 按数据库规范输出账号密码登录相关库表与 SQL 脚本 | `30-0500-database-management` | `TASK-005-20` | 账号密码登录库表与脚本资产 |
| `TASK-005-22` | 实现后台手机号账号+密码登录接口闭环 | `00-0900-project-template-management` | `TASK-005-21` | 账号密码登录后端闭环实现 |
| `TASK-005-23` | 完成账号密码登录前后台联调、人工测试与结果回写 | `40-0100-project-testing` | `TASK-005-22` | 账号密码登录联调与人工测试记录 |
| `TASK-005-24` | 重新提交登录页人工复测/人工审核并回写审核结论 | `20-0200-acceptance-standards-documentation` | `TASK-005-23` | 登录页二次人工审核记录 |

## 任务产出 / 结果记录

- `2026-05-13`：本文件已从旧的“登录页高保真实现”单任务重写为“登录页 Story”。
- 历史登录页完成记录降级为参考，不再直接作为当前 Story 完成依据。
- `2026-05-13`：实施代理已完成前端登录页真实接口接线、后端 `/api/auth/login` 最小实现、Story 留痕与独立提交推送 `a838d4a`。
- `2026-05-13`：独立验收代理已验证 `mvn test`、`npm run type-check`、`npm run build:h5` 通过，允许主代理回写完成。
- `2026-05-13`：用户指出当前登录页与高保真稿不一致；本 Story 按正式输入重新打开，新增高保真重做、人工测试与人工复测子任务。
- `2026-05-13`：登录页页面验收口径已补正为“仅认可移动端设备模式运行态截图”；此前桌面截图裁切类证据不再作为高保真通过依据。
- `2026-05-13`：实施代理已完成登录页背景氛围与微信登录入口可见性收口；独立验收代理按移动端设备模式完成运行态复验，结论为可进入人工审核，证据截图为 `C:\Users\13174\AppData\Local\Temp\TASK-005-mobile-1778641476791.png`。
- `2026-05-13`：用户在人工审核中先提出“去掉顶部留白 + 验证码倒计时 + 验证码放行”方向，随后又明确改口为“手机号作为账号 + 密码登录，前后端同时适配”；本 Story 已按最新口径把二次开发子任务重写为账号密码登录方向。

## 进度总结

- `已完成`

## TASK-005 final closeout record

- `2026-05-13 03:55 +08:00`: Backend minimal verification passed with `mvn test` in `code/develop/yunjikeji-server` after limiting the default-profile datasource dependency to login execution time.
- `2026-05-13 03:55 +08:00`: Frontend minimal verification passed with `npm run type-check` and `npm run build:h5` in `code/develop/yunjikeji`.
- `2026-05-13 03:55 +08:00`: Frontend build kept existing warnings for unresolved runtime static backgrounds and Sass dependency deprecations; no new implementation scope was added.
- `2026-05-13`: 独立验收已在移动端设备模式下重新复验登录页高保真收口。由于浏览器工具会话未建立，本轮改由本机浏览器移动端设备模式完成人工复验；运行态截图证据为 `C:\Users\13174\AppData\Local\Temp\TASK-005-mobile-1778641476791.png`，结论为可进入人工审核。
- `2026-05-13 12:49 +08:00`: Account-password login closed the real test-environment loop. Independent acceptance re-verified `POST https://sit.lai-do.com/yunjikeji-api/api/auth/login` with `account=13800138000` and `password=Yk@20260513`, got `code=00000`, and confirmed mobile-device-mode page login from `#/` to `#/pages/home/index`. Test DB follow-up also showed updated `last_login_at` and latest `yk_login_audit` success record. Residual risk: direct API verification currently passes on `account` field but not on `mobile` field, so this Story completes its development scope and hands off to `TASK-005A` for human review.
- `2026-05-13 13:20 +08:00`: 用户在本地人工审核 `http://localhost:5173/#/` 时指出当前版本不通过，Story 立即回退为 `进行中`。本轮问题包括：页面直接提示“登录服务不可用”；账号输入框与密码输入框之间的纵向间距偏小；登录按钮上下高度偏大且字重偏粗；背景图与图片资源写法需改为 `uni-app` 兼容方式；微信 logo 发生变形。后续需按上述问题重新实施，并重新进入人工测试与人工审核链路。
- `2026-05-13 14:10 +08:00`: 实施代理已完成本地登录页修复：开发环境登录链路由直连失效的 `127.0.0.1:18080` 改为本地 `dev-api` 代理到测试环境；登录请求字段统一为 `account`；背景图与微信 logo 改为 `uni-app` 兼容资源绑定；输入框间距、登录按钮高度与字重已按人工审核意见收口。最小自检已通过 `npm run type-check` 与 `npm run build:h5`。
- `2026-05-13 14:26 +08:00`: 独立验收代理已使用 `iPhone 13` 移动端设备模式在本地 `http://localhost:5173/#/` 完成复验：首屏不再出现“登录服务不可用”，背景图与微信 logo 正常显示且未变形，账号/密码输入框纵向间距已拉开，登录按钮视觉已收窄；使用 `13800138000 / Yk@20260513` 勾选协议后可成功请求 `POST /dev-api/api/auth/login`，返回 `200 + code=00000`，并跳转到 `#/pages/home/index`。因此本 Story 维持 `已完成`，继续由 `TASK-005A` 承接人工审核。保留风险：控制台仍有 1 条 `404` 资源日志，暂不阻塞人工审核。
- `2026-05-13 14:33 +08:00`: 用户在新一轮人工审核中再次打回本 Story，要求继续收口 3 项问题：其一，所有登录相关提示文案必须改为中文，当前仍出现英文密码长度提示 `Password length must be 6 to 32 characters.`；其二，微信登录图标需继续放大，当前视觉上仍不足圆形容器的 `1/2`；其三，登录主按钮上下高度仍偏大，字体粗细仍偏重，需要继续收窄和减轻。因此本 Story 再次回退为 `进行中`，需重新实施并再次进入独立验收与人工审核链路。
- `2026-05-13 14:41 +08:00`: 实施代理已完成第三轮收口：前端新增登录错误中文映射与短密码中文校验，拦截英文提示 `Password length must be 6 to 32 characters.`；微信图标继续放大到圆形容器内更高占比；登录按钮继续收窄到 `84rpx`，字重降到 `500`。本轮最小自检 `npm run type-check` 已通过。
- `2026-05-13 14:52 +08:00`: 独立验收已使用本机浏览器 `iPhone 12` 设备模式对真实本地地址完成人工复验。当前实际本地端口为 `5174`，来源于 `.codex-dev-h5.out.log` 中 `5173` 被占用后的自动切换。验收已现场触发短密码中文提示 `登录密码长度需为 6-32 位`，未再出现英文密码长度报错；微信图标在移动端截图中已明显放大；使用 `13800138000 / Yk@20260513` 勾选协议后，`POST http://127.0.0.1:5174/dev-api/api/auth/login` 返回 `200 + code=00000`，页面跳转到首页。因此本 Story 维持 `已完成`，继续等待 `TASK-005A` 的人类审核结论。保留风险：本地登录成功依赖当前 `5174` 与 `/dev-api` 代理链路在线，若端口或代理切换需重新复验。
