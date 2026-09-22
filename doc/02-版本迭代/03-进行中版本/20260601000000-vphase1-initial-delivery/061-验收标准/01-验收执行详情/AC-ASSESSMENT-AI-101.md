# AC-ASSESSMENT-AI-101 AI 上游调用与错误可诊断

- 类型：技术-接口级
- 正式入口：自测报告服务到 OpenAI 兼容 AI 服务的调用链。
- 支撑结果：测试环境能够使用实际启用的模型生成报告，异常时可从脱敏日志直接判断故障层级。
- 通过条件：自测报告入口保持现有 `DeepSeekOpenAiClient.complete(sceneCode, systemPrompt, userPrompt, null)` 非流式调用和现有模型配置机制，请求固定 `stream=false`，不新增流式分支、流式配置或阶段正文协议；共享客户端知识库旧调用路径及其他 AI 场景行为必须保持不变。业务入口线程只负责创建/复用 `PENDING` 并入队；异步线程必须先按分类13真实48题的稳定题目 ID 完成 V3 映射，未知 ID、ID/题干冲突、已作答但无法映射、必填值缺失或非规范值均直接失败，不得由默认值或题干模糊命中静默代替。真实非流式调用返回完整内容后，对 HTML 标签、属性和结构执行安全硬校验；配置缺失、映射、网络、鉴权、模型、参数、超时、空响应和 HTML 安全异常分别留下可区分的脱敏原因或错误类型，并使最终记录进入 `FAILED`。字数、标题/章节、分数、等级、训练、金额、证书和方向等正文偏差只记录审计，不使记录失败；不得转换成简版 HTML；日志不得输出 API Key。自测报告页读取已存在报告时必须走分类13轻量报告入口，只返回 `id/assessmentTime/assessmentReportStatus/assessmentReportFailureReason/selfReportContent` 等价字段，不返回 `answers`，并保持本人记录、分类13和完成态校验；`PENDING/SUCCESS/FAILED` 与重试语义不变。
- 证据承接：脱敏请求配置、上游状态、日志摘要与自动化测试结果统一回写 `061-验收标准/03-测试验证/DEV-049/`。
