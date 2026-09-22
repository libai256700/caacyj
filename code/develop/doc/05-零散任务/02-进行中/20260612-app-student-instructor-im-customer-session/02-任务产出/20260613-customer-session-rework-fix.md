# 2026-06-13 客服接口返工修复记录

## 根因

- APP 端真实请求为 `GET /app-api/yj/customer-service/session`，管理端资源调用为 `/admin-api/yj/customer-session/**`、`/admin-api/yj/customer-message/**`。
- 后端客服相关 Controller、Service、Repository 位于 `com.huiyitech.message` 包，但启动类扫描范围未包含该包，运行服务没有注册客服接口映射，导致 APP 端和管理端客服入口 404。
- 404 后 Tomcat error forward 再进入访问日志拦截器，开发环境日志拦截器尝试读取 JSON body，触发 `getInputStream() has already been called for this request` 二次异常，掩盖了原始 404 根因。

## 改动

- `YunjikejiAdminServerApplication` 增加 `com.huiyitech.message` 扫描包，让客服 Controller、Service、Repository 进入 Spring 容器。
- `ApiAccessLogInterceptor` 对 `DispatcherType.ERROR` 直接放行，并在 `afterCompletion` 中保护空或已停止的 `StopWatch`，避免错误页转发阶段二次读 body 或空计时器异常。
- APP 前端 `src/services/customerService.ts` 已是 `/app-api/yj/customer-service/session`、`/messages`、`POST /messages`，本次未改。
- 管理后台 `src/api/yj/index.ts` 与资源配置已是 `/yj/customer-session/**`、`/yj/customer-message/**`，叠加后台 axios 的 `/admin-api` base 后与后端一致，本次未改。

## 验证

- `mvn -pl yunjikeji-admin-server -am -DskipTests compile`
  - 首次 124 秒超时，未得到失败点。
  - 再次 304 秒超时，仍未得到失败点。
- `mvn -pl yudao-framework/yudao-spring-boot-starter-web,yunjikeji-admin-server -am -DskipTests compile`
  - 通过，Reactor `BUILD SUCCESS`，覆盖访问日志拦截器所在 web starter 与后端启动模块。
- `npm run type-check`，目录 `code/develop/yunjikeji`
  - 通过。
- `pnpm ts:check`，目录 `code/develop/yunjikeji-admin-ui`
  - 未通过；失败为既有大面积非客服类型错误，首批包括 `src/api/mall/statistics/trade.ts`、`src/components/bpmnProcessDesigner/**`、`src/views/pay/**` 等，客服相关 `src/api/yj/index.ts`、`src/views/yj/resource/**` 未出现在错误列表。

## 未覆盖风险

- 未连接真实测试环境调用接口；本次基于源码映射、扫描配置和编译验证确认路径修复。
- 管理后台全量类型检查存在既有错误，无法用该命令证明全仓前端类型健康。
