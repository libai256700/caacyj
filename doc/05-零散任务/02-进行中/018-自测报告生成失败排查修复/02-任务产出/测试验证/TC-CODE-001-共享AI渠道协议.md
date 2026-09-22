# TC-CODE-001 共享 AI 渠道协议

## 1. 测试层级

`技术-代码级`

## 2. 对应验收项

- 验收项 ID：`TA-T0018-CODE-001`
- 正式验收入口：`../../01-验收标准.md`

## 3. 前置条件

- 环境前置：当前代码可完成 Maven 测试与编译；不访问外部 AI。
- 账号前置：无。
- 数据前置：使用项目正式 channel 语义构造请求契约，不启本地伪服务。

## 4. 测试数据

```json
{
  "channels": ["ANTHROPIC", "OPENAI_COMPATIBLE", "openai-compatible", ""],
  "fallback": "blank channel uses URL protocol hint"
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 使用非空正式 channel 构造协议 | channel 优先于 URL 形状 |
| 2 | 使用大小写和连字符别名 | 归一到正式协议 |
| 3 | 使用空 channel | 才允许按 URL 兼容回退 |
| 4 | 检查请求 path/header/body | Anthropic 与 OpenAI 兼容契约分别正确，且不输出密钥 |

## 6. 期望结果

- 自测、岗位提取与知识库共享客户端遵循数据库正式 channel。
- 本地测试不启动伪 HTTP/AI 服务，不发真实外部请求。

## 7. 脚本入口

- 自动化脚本：`DeepSeekOpenAiClientTest`
- 依赖命令：`mvn -pl yunjikeji-admin-server "-Dtest=DeepSeekOpenAiClientTest" test`
- 结果输出位置：`04-测试执行结论.md`

## 8. 失败判定

- 非空 channel 被 URL 后缀覆盖。
- 请求协议、鉴权头或 body 与 channel 不一致。
- 测试引入本地伪服务、替身客户端或外部 AI 请求。

## 9. 执行记录

- 当前状态：`已通过`
- 执行时间：`2026-08-27 12:45`
- 已执行证据：无网络请求契约测试 5/5 通过，Maven compile 通过；真实外部 AI 联调仍待正式测试环境。
