# AC-CAREER-ASSESS-202 职业规划规则、固定主键 Agent 与报告

- 类型：技术-数据级
- 正式入口：分类14末题统一提交的答案、职业规划专用规则、分类14结果记录和人工初始化的 `yj_agent_info` 固定主键记录。
- 支撑业务结果：职业规划报告真实反映源规则，不使用分类13报告语义、分类13 Agent或其他分类答案。
- 技术边界：报告必须经 `result.record_id -> record.category_id(catalogBatchId) -> catalog_batch.category_id=14` 路由；分类14服务端按源schema重建`mode=self/formVersion=2`并重算12题RIASEC与四维工作风格，姓名、成果经历、12道RIASEC和刚好3项工作价值必填，工作风格按源题目配置选填处理，未作答题目不应被当成分类13必答空答；最不看重项如选择不得与Top3重复，其他字段只服从源schema。分类14运行时以 `CAREER_ASSESSMENT_AGENT_INFO_ID=3L`读取id=3，禁止按 `agent_id`/name查询或运行时创建更新；提示词仅以 `career-planning-coach/scripts/career-core.mjs` 的 `SELF_SYSTEM_PROMPT` 原文初始化。模型输入只以重算事实放入`<submitted_data>`；输出必须经源HTML白名单、固定三标题、300-3500可见字符与安全规则校验，有警告或错误即待复核不发布。报告生成全过程必须写结构化日志，至少包含 `recordId / categoryId / batchId / agentId / model / stage / status / errorType`，只记录阶段与结果，不记录答案全文、提示词全文或其他敏感原文；失败时必须能根据日志定位真实失败阶段。分类13继续由 `SelfAssessmentV3RuleEngine` 和固定 `id=2` 处理；两类报告均继续使用 `yj_ai_model_config.practice_assessment` 场景的同一大模型调用链，不在Agent记录或职业规划代码中另行固化模型。
- 通过条件：职业规划固定样本的规范化输入、RIASEC/风格计算和报告校验与源规则一致；id=3的prompt hash与 `SELF_SYSTEM_PROMPT` 原文一致；id=3缺失/字段不匹配、必答缺失、互斥冲突、跨分类答案、步骤/题目分类不匹配、题库不完整、危险HTML、缺少职业报告三标题或报告长度越界均不能生成可展示报告；职业规划调用的是现有 `practice_assessment` 模型配置；分类13报告结果无回归；分类14末题点击后直接统一提交，提交请求发出后立即显示与分类13一致的等待弹框，题目选填处理和报告生成后校验均不得串到分类13；报告失败必须返回 FAILED 并承接失败原因，不能长期停留在生成中。
- 证据承接：源规则和prompt哈希、规则单元测试、固定样本对照、Agent回读、测试环境分类14真实报告和分类13回归报告。
- 当前状态：待执行。
