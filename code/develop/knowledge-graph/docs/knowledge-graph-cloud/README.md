# 知识库迁移仓（私有）

无人机培训知识库的权威备份与线上部署交接物。**本仓为私有仓，内容含受版权保护的教材与自有题库，不得公开或对外分发。**

仓库同时保存可供 caacyj.com 和其他 App 接入的便携技能。技能代码与受版权保护的知识库源料分目录管理，不包含生产凭据、运行时状态或用户数据。

## 目录结构

下列是仓库的实际物理目录。知识问答相关组件仍按 App、Server Runtime、运维和本机源环境的
安全边界分开存放；后文提供统一的逻辑视图。

```
knowledge_base/        原始文档（4 个域，35 个文件）
  ├── 地面站考题考试条件/   10
  ├── 政策法规/            7
  ├── 无人机理论书籍/       7
  └── 理论题库/            11
deploy/                线上运行代码（运行时最小集）
  ├── pipeline/          HTTP 服务与答案治理
  ├── rag_store/         检索、路由、图谱召回、证据治理
  └── data/canonical/    地面站考题结构化条件数据
scripts/               本机向量候选探针、构建与验证工具
eval/                  线上范围题池、Cloud Gold schema 与 pending 人审模板
skills/
  evaluation-report/              无人机入行评测 V3 便携技能
  career-planning-coach/           独立职业发展评测 App 与管理后台
  weather/                        App 和风天气实时查询
  search/                         App 百度 + Google 双引擎搜索
  knowledge-graph-cloud/          知识问答 App 用户技能
  knowledge-graph/                本机源环境：问答调度与治理任务分流
  knowledge-graph-hybrid-audit/   本机源环境：审计与健康门禁
  structured-data-sync-csa/       本机源环境：结构化同步
  query-trace-quality-dashboard/  本机源环境：trace 与质量看板
operator-companion/     Server Suite 运维组件（不进入用户 App ZIP）
  ├── maintenance-controller-cloud/  受控维护任务
  ├── hybrid-audit-cloud/             线上审计
  └── quality-dashboard-cloud/        线上质量看板
DEPLOY.md              部署与验收手册（技术人员按此执行）
USAGE.md               使用说明（能回答什么、怎么判断答案可信）
APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md  本地知识问答同步到 App 的强制修改合同
KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md  迁移、迭代、GitHub 交付与接收团队交接总手册
MANIFEST.sha256        原始文档逐文件 SHA256 校验清单
CODE_MANIFEST.sha256   运行代码、云端技能、评测器与交付文档 SHA256 清单
```

## 知识问答体系逻辑分组

为方便 AI、程序员和接收团队理解，知识问答与知识图谱相关内容统一按以下逻辑目录阅读。
这是职责视图，不表示物理目录已经移动：

```text
knowledge-qa-system/                         逻辑分组（非物理目录）
  ├── app-user-skill/
  │   └── skills/knowledge-graph-cloud/      App 唯一知识问答技能
  ├── server-runtime-and-builders/
  │   ├── deploy/                            服务、检索与图谱运行代码
  │   └── scripts/                           本机向量候选构建与验证
  ├── operator-companion/
  │   ├── maintenance-controller-cloud/      受控维护任务
  │   ├── hybrid-audit-cloud/                线上审计
  │   └── quality-dashboard-cloud/           线上质量看板
  └── source-environment-reference/
      ├── skills/knowledge-graph/            本机问答调度与任务分流
      ├── skills/knowledge-graph-hybrid-audit/  本机检索与图谱审计
      ├── skills/structured-data-sync-csa/   本机结构化同步
      └── skills/query-trace-quality-dashboard/  本机 trace 与质量分析
```

四组属于同一知识系统，但不能合并为同一个可发现技能包。App 只加载
`knowledge-graph-cloud`；线上运维组件只随 Server Suite 交付；本机源环境参考不进入 App ZIP，
也不作为线上运行入口。

数据库快照、检索索引与图谱子图以 **Release 附件**形式发布，不进 git 历史。

迁移、导入或更新知识问答与知识图谱前，AI 和程序员必须先完整阅读
[`KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md`](KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md)，
再按其中顺序读取 App 合同、使用说明、技能接口、部署手册和当前任务批准材料。总手册固定
App-host-final、loopback-only Ollama BGE-M3 + 服务器本地向量、公共/运维隔离、变更分类、
fresh evidence、Stop C 和接收团队责任。文档或测试存在不等于已获批准、已部署或已验收。

## 部署

从 [Releases](../../releases) 下载数据附件，然后按 `DEPLOY.md` 执行。最近已发布基线配对为代码 tag
`kg-code-20260804-01` + 数据 tag `snapshot-20260803`；后续治理候选在完成独立 Cloud Gold 与真实
80 题回放前不是新 Release。不得用 `main`、候选分支或其他数据附件冒充已验收配对。
**先读 DEPLOY.md 的 0.1 节**，那里列出了四条与直觉相反、必须先确认的前提。

`deploy/` 是线上服务运行代码；顶层 `scripts/` 是本机候选构建与验证工具，不进入 App 上传包。
所有 HTTP 端点均为只读，图谱写接口与任意查询接口已移除。

`deploy/` 的知识服务保留检索、证据治理与运行遥测，供维护方在服务端观察。App 最终用户不直接
消费这些工程字段；`knowledge-graph-cloud` 会把知识服务结果作为可选专业上下文，再由 App 大模型
生成自然答案。知识库未覆盖、未命中或暂时不可用时，App 大模型继续回答，不向用户展示来源、
拒答、错误、降级、路由、trace 或评测信息。

线上问答批量验收只使用 `eval/online_subset_20260803.json`。该文件从本机全量题池
按四域白名单生成；本机 `eval/qa_pool.json` 继续服务本机全量知识库，不得替换。
`eval/cloud80_gold_standard_v1.json` 在独立人审与 SSHSIG 完成前保持 pending，只能用于审阅和
report-only 采集，不能证明答案正确率。已审 Gold 与 authority snapshot 只作为仓库外
验收材料：先由人工 Gold 审批人签署，再采集真实 80 题原始响应和 hash-chain trace，
由独立评测证明人签署 attestation，最后完全离线重算。评测证明人与 Gold
审批人必须是不同 named human，并使用不同 SSH public-key fingerprint；只有最后阶段能产生 pass。

## 可复用 App 技能

- [`evaluation-report`](skills/evaluation-report/SKILL.md)：确定性计算无人机入行评测的五维分数、双指数、画像、方向与标签，准备受约束的 LLM 提示词，并校验、消毒和组装报告。
- [`career-planning-coach`](skills/career-planning-coach/SKILL.md)：可独立部署的六步职业发展评测 App，包含服务端重算、受约束报告、HR 岗位适配评估、SQLite 持久化和带鉴权/审计的管理后台。线上版本不包含用户端隐私功能；系统安全控制保留。
- [`weather`](skills/weather/SKILL.md)：城市实时天气、3/7/10 天预报、空气质量和穿衣信息；凭据由 App 宿主提供。
- [`search`](skills/search/SKILL.md)：百度千帆 + Serper/Google 双引擎搜索，用于最近新闻和其他时效问题。
- 其他电脑按需单独提取对应 `skills/<name>/`；不要随技能分发 `knowledge_base/`。私有仓库拉取和 CI 使用者必须具备相应 GitHub 权限。
- `evaluation-report` 要求 Node.js 18+，在技能目录执行 `npm ci && npm test`。真实配置和登录态必须在目标电脑重新建立。
- `career-planning-coach` 要求 Node.js 22.12+，在技能目录执行 `npm ci && npm run check && npm test`；独立启动、容器、模型和首次管理员配置见其 `references/deployment.md`。

## 知识问答 Agent 技能

技能不是部署服务所必需的（服务器只跑 `deploy/`），但**App 侧让 agent 调用问答能力时必须加载**。
它负责把知识服务的内部结果转换成最终用户能直接阅读的友好答案，并在知识服务没有可用内容时
切换到 App 自身大模型。

以后从本地知识问答同步能力、代码或知识库前，必须先执行
[`APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md`](APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md)；本地源环境与 App
对外环境不能直接整目录复制。

### App 用户技能：只用 `knowledge-graph-cloud`

- [`knowledge-graph-cloud`](skills/knowledge-graph-cloud/SKILL.md)：App 对外通用问答入口。优先调用
  HTTP `POST /api/ask` 获取四个专业文档域的上下文，再由 App 大模型生成最终回答；库外问题、
  未命中和服务异常均由 App 大模型继续回答。用户正文不展示来源、错误、拒答、降级或评测内容。
  当前问题与历史对话分开传入，回答不重复当前问题或历史问题；询问助手名称或身份时固定回复
  “我是小技，你的私人学习助理”。实时天气和联网搜索由 App 宿主大模型选择独立技能，
  `knowledge-graph-cloud` 不接管其路由、调用、配置或验收。

### 线上运维技能（不进入用户 App ZIP）

- [`maintenance-controller-cloud`](operator-companion/maintenance-controller-cloud/SKILL.md)：执行获批的
  受控维护任务，不提供给公共 App Agent。
- [`hybrid-audit-cloud`](operator-companion/hybrid-audit-cloud/SKILL.md)：检查线上检索、图谱与证据状态。
- [`quality-dashboard-cloud`](operator-companion/quality-dashboard-cloud/SKILL.md)：读取线上质量指标和趋势。

这些技能属于 Server Suite 的 `operator-companion/`，与公共 App 使用不同的进程、身份、
audience、secret scope、network policy 和工具注册表。它们不是本机源环境技能，也不能由
`knowledge-graph-cloud` 发现或调用。

### 本机源环境参考技能（**不要用于线上**）

下列四个描述维护方本机环境。其中 `knowledge-graph` 是问答调度与治理任务分流入口，另外三个
分别保存结构化同步、审计和质量分析规则；引用的脚本、结构化数据源与业务域在线上**均不存在**。
随仓交付仅为存档和后续迭代迁移时的源环境对照。

- [`knowledge-graph`](skills/knowledge-graph/SKILL.md)、
  [`knowledge-graph-hybrid-audit`](skills/knowledge-graph-hybrid-audit/SKILL.md)、
  [`structured-data-sync-csa`](skills/structured-data-sync-csa/SKILL.md)、
  [`query-trace-quality-dashboard`](skills/query-trace-quality-dashboard/SKILL.md)

源环境技能保留本机建设、审计和治理合同；App 技能不加载这些内部 SOP，也不把其工程状态展示给用户。

### 第一版生产向量身份

本机向量开发默认使用已经注册的 `bge-m3:latest`，通过 loopback-only Ollama
`/api/embed` 生成 1024 维 build/query/entity 向量。`scripts/ollama_local_embedding_probe.py`
验证模型 digest、维度和三种用途共用同一 identity；
`scripts/build_ollama_vector_candidate.py` 只写新的 candidate 路径；
`scripts/verify_ollama_vector_candidate.py` 在临时只读 active 布局中使用正式 reader 验证查询和
SQLite 回填。三个脚本不进入 App 上传包；必要的接收侧 probe、builder 和 verifier 随 Server Suite 交付。

当前本机候选位于
`artifacts/candidates/revision-a-r9/ollama-bge-m3-r1/`：1482 个 chunk、22 个实体，
Embedding identity 为 `1420abc56de9dc70b55517f0879a64acc66947d89d194b6f43bb326e135b9d4b`，
local-vector manifest 为 `956c52b63c05dabaf58d56dbf0ad16f51053a944b9aa9d4490508bea510a6705`。
该 candidate 的字节已冻结为第一版生产向量并随 Server Suite 交付，但本地未切换 active。
Linux x86_64 USEarch 加载、目标配置注入和启动属于接收团队，标记为
`pending_receiving_team`。fake 32 维只保留为零网络测试夹具，不得进入 production-only
suite；真实 server answer/ops provider 字段保持为空并 fail closed。未来如启用外部模型角色，
必须按 `N + M + 2` 重新取得 production Stop B。

## 校验

```bash
shasum -a 256 -c MANIFEST.sha256
bash skills/knowledge-graph-cloud/scripts/verify.sh
```

第一条校验 35 份原始文档；第二条运行云端技能单元测试，并验证 `CODE_MANIFEST.sha256`
对运行代码、技能、评测器和交付文档的精确覆盖。仓库校验通过不等于云端已部署，也不等于 Gold
已激活；接收团队仍须按 `DEPLOY.md` 部署和启动服务，执行 `Gold review/SSHSIG ->`
`report-only collection -> attestation SSHSIG -> formal-offline` 的真实 80 题流程，并取得独立的
`runtime-active` 证据。

## 数据说明

- 原始文档是知识库的**源料**；线上问答服务实际读取的是由其派生的数据库快照与检索索引（见 Release）。
- 本仓内容为**冻结快照**。源料更新后由维护方重新推送并发布新 Release，tag 即数据截止点。
- 服务器上的原始文档副本应置于 Web 目录之外、权限收紧（`chmod 700`），仅供重建索引使用。

## 边界

- 线上知识服务的专业材料覆盖上述四个文档域；App 对外问答范围不受此限制。
- 服务端口不得裸露公网，须经反向代理 + 鉴权 + TLS，并限制来源。
- 服务器侧凭据（数据库密码、模型密钥）由部署方独立生成，不复用任何其他环境的凭据。
