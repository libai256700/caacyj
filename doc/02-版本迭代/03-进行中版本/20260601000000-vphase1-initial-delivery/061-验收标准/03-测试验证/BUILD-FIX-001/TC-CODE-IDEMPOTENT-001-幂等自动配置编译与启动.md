# TC-CODE-IDEMPOTENT-001 幂等自动配置编译与启动

## 1. 测试层级

`技术-代码级 / 构建与启动冒烟`

## 2. 对应验收项

- 验收项 ID：`AC-BACKEND-BOOT-001`、`AC-BACKEND-BOOT-101`
- 正式验收入口：`../../01-验收执行详情/AC-BACKEND-BOOT-001.md`、`../../01-验收执行详情/AC-BACKEND-BOOT-101.md`

## 3. 前置条件

- 在 `code/develop/yunjikeji-admin-server/` 使用项目既有 JDK 与 Maven 环境。
- 清理前确认目标绝对路径只指向 `yudao-framework/yudao-spring-boot-starter-protection/target`。
- 不修改源码、POM、自动配置清单、数据库或 `uni_modules/**`。

## 4. 执行动作与预期结果

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 记录 protection 模块清理前的 `target/classes` 内容与目标路径 | 当前缺失 `.class` 的失败现场可追溯，目标路径位于指定模块内 |
| 2 | 删除且只删除 protection 模块 `target`，重新编译该模块及必要依赖 | Maven 退出码 `0`，输出 `BUILD SUCCESS` |
| 3 | 检查编译输出 | `target/classes/cn/iocoder/yudao/framework/idempotent/config/YudaoIdempotentConfiguration.class` 存在，相关 Java `.class` 不再为空 |
| 4 | 按既有入口启动 `YunjikejiAdminServerApplication` 并观察日志 | 启动过程越过幂等自动配置元数据读取，不再出现指定 `IllegalStateException` 或 `FileNotFoundException`；如有后续无关错误，单独记录 |
| 5 | 检查 Git 边界 | 本次操作未引入源码、POM、自动配置清单或 `uni_modules/**` 变更，用户原有工作区改动保持不动 |

## 5. 失败判定

- 清理范围超出指定模块 `target`。
- Maven 非零退出或未输出 `BUILD SUCCESS`。
- 目标 `YudaoIdempotentConfiguration.class` 仍不存在，或模块 Java `.class` 仍为空。
- 启动仍出现相同 `Unable to read meta-data` / `FileNotFoundException`。
- 为规避错误而修改源码、POM、自动配置清单或 `uni_modules/**`。

## 6. 当前状态

- 通过；原 `Unable to read meta-data` / 目标类 `FileNotFoundException` 已消除。
- 实施证据：限定执行 `mvn -pl yudao-framework/yudao-spring-boot-starter-protection -DskipTests clean compile`，退出码 `0` 且输出 `BUILD SUCCESS`；只清理目标模块 `target`，恢复 29 个 Java `.class`。
- 独立编译复验：2026-07-17 19:24 执行 `mvn -pl yudao-framework/yudao-spring-boot-starter-protection -DskipTests compile`，退出码 `0`，输出 `Nothing to compile - all classes are up to date.` 与 `BUILD SUCCESS`。
- 产物证据：`YudaoIdempotentConfiguration.class`、`core/aop/IdempotentAspect.class`、`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` 均存在；`target/classes` 共 29 个 `.class`。
- 字节码证据：`javap` 成功解析 `YudaoIdempotentConfiguration`，可见构造方法以及 `idempotentAspect`、`idempotentRedisDAO`、三个 `IdempotentKeyResolver` Bean 方法。
- 独立启动证据：使用 JDK 17 argfile 与独立端口 `48081` 启动 `YunjikejiAdminServerApplication`；日志先输出 `Starting YunjikejiAdminServerApplication`，随后到达 `Tomcat initialized with port(s): 48081 (http)`，未出现原 `Unable to read meta-data`、目标类路径 `FileNotFoundException`、`IllegalStateException` 或 `Application run failed`。
- 完整运行复验：2026-07-17 对用户已启动且持续运行的 Java PID `56620` 进行只读复核；`netstat -ano` 显示该进程同时监听 `0.0.0.0:48080` 与 `[::]:48080`，`GET /actuator/health` 返回 HTTP `200` 和 `{"status":"UP"}`，`GET /` 返回 HTTP `200`（业务体为未登录提示）。完整应用上下文已对外提供 HTTP 服务，原自动配置缺类异常不可能仍阻断当前进程启动主链路。
- 历史启动关注（已关闭）：此前独立 PID `39952` 的 60 秒观察窗内未输出完整 `Started YunjikejiAdminServerApplication` 或 `Tomcat started`，当时未据此声明完整服务启动成功；该进程按原记录停止且未影响 IDEA 原有 Java 进程。本次 PID `56620` 的监听与 HTTP 健康证据已关闭该关注项，本次未停止、重启或修改用户进程。
- Git 边界：目标 protection 模块的 `git status`、工作区 diff 和暂存区 diff 均无输出；源码、POM、自动配置清单未改，用户原有工作区改动保持不动。
