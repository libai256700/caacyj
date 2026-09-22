# TA-VAPP-API-001 后端核心接口契约

## 验收类型

`接口级验收`

## 业务场景

六页面端到端业务链路需要后端提供稳定接口、统一鉴权、健康检查和错误返回，支撑前端在测试环境完成真实联调。

## 验收标准说明

后端接口必须在测试环境可达，接口路径、请求方式、鉴权方式、请求参数、返回结构和错误码有正式契约，并能支撑六个页面的关键业务动作。

## 核心对象

- `yunjikeji-server`
- 健康检查接口
- 登录接口
- 首页聚合接口
- 练习链路接口
- AI 深度解答接口
- 我的页聚合接口
- Nginx API 代理路由

## 前置条件

1. 后端应用级部署入口已补齐，包括应用名、部署目录、启动脚本、日志目录、运行 profile 和外部配置路径。
2. 后端服务端口已确认不与 `TEST-3DAPP-MICRO-01` 现有服务冲突。
3. Nginx API 代理路径或直连测试入口已确认。
4. 鉴权与测试账号口径已确认。

## 触发动作

1. 启动或访问测试环境后端服务。
2. 调用健康检查接口。
3. 按六页面联调顺序调用核心业务接口。
4. 使用异常参数或无权限场景核对错误返回。

## 期望结果

1. 健康检查返回可用状态。
2. 六页面所需接口均可在测试环境访问。
3. 接口返回结构满足前端页面展示和状态流转需要。
4. 鉴权失败、参数错误、数据为空等场景有可识别返回，不导致页面不可恢复。

## 执行结果

1. `2026-05-13`：测试环境预备部署健康检查已完成，目标服务器为 `TEST-3DAPP-MICRO-01`。
2. 后端直连入口：端口 `18080` 可用，`/api/health` 与 `/api/health/db` 已验证通过。
3. Nginx API 代理入口：`/yunjikeji-api/api/health` 已验证通过。
4. 当前边界：该结果只覆盖健康检查与 API 代理预备入口，不覆盖登录、首页聚合、练习链路、AI 深度解答、我的页聚合等完整业务接口契约验收。
5. `2026-05-13 / practice-mainline supplement`：练习主链后端接口已按当前程序设计与前端调用口径准备完成，并已推送到 `origin/develop@5360ec93de9b116892ed5f53125b8c6a12189600`。当前至少包含：
   - `GET /api/practices/current`
   - `POST /api/practices/{practiceId}/start`
   - `GET /api/practices/{practiceId}/sessions/{sessionId}/question`
   - `POST /api/practices/{practiceId}/sessions/{sessionId}/answers`
   - `GET /api/practices/{practiceId}/sessions/{sessionId}/progress`
6. 本轮已同步修正练习主链接口的 `multiple_choice` 支持、`wrongReview` 语义和匿名 session 访问拦截，并通过独立验证与服务集成测试。
7. 当前边界补充：本条回写只证明练习主链后端接口已准备好并完成部分接口级验收推进；首页、AI 深度解答、我的页等其余业务接口仍待后续联调验收，页面人工联调与人工审核也未在本文件中宣告完成。
