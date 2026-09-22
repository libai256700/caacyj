---
name: knowledge-graph-cloud
description: "线上无人机知识问答服务的调用入口。用于无人机、CAAC、法规、气象、飞行原理、运行安全、考试、题库与教材类专业问题，走服务端统一 /api/ask。保留事实权威、回答红线与只读边界。仅覆盖四个文档域；四域之外的问题一律失败关闭，不猜测、不用模型常识补答。"
---

# 线上知识问答调用入口

本 skill 面向**接入线上服务的应用与 agent**，只负责四件事：统一问答入口、能力边界、回答红线、只读约束。

服务形态为**冻结快照**：数据由维护方在源环境构建后随 Release 发布，线上不做任何写入，
也没有导入、同步或生产治理工具链。随技能附带的只读评测器只调用 `/api/ask` 并保存验收证据，
不会修改知识库。

来源命中、HTTP 200 和终审通过都不能单独证明答案正确。正式发布验收必须使用与 80 题题池
逐题绑定、经独立人工审阅并通过 SSHSIG 激活的 Cloud Gold；仓库内 pending Gold 仅是审阅模板，
不得用于生成“正确率通过”结论。

## 覆盖范围（硬边界）

服务只覆盖四个文档域，共 35 份文档：

| 域 | 内容 |
|---|---|
| 政策法规 | CCAR-92部、民用航空法、飞行管理暂行条例、实名登记规定、执照考试管理办法、训练机构规范、大型民用无人驾驶航空器系统操控员训练要求 |
| 理论题库 | 气象、飞行原理与性能、空中交通管制、任务规划、系统组成、教员题库等 |
| 地面站考题考试条件 | 各题型的考试条件（避让点、空域限制、夹角、罗盘双坐标、航向等） |
| 无人机理论书籍 | 概论、操控技术、防控技术、系统结构与设计、安全飞行基础、影视航拍、技术概论 |

**四域之外的问题一律失败关闭**：定价、报名、名单、成绩、排期、人员、机构内部事务等，服务端不存在对应数据，正确行为是明确告知"该问题不在本服务覆盖范围"，**不得用模型常识补答，也不得暗示库里可能有**。`湖北云技科技有限公司`、`云技科技公司`、`湖北云技科技`、`云技科技` 四种名称在 portable 快照中均属于明确域外输入；不得迁移本机公司实体或通过近名猜测身份。

## 统一问答

不得把用户问题拼进 shell 命令，包括放入双引号、单引号、命令替换或 here-document。将规范化后的 `user_query` 作为一个不透明字段传入，全程不经 shell 解析：

```text
POST {SERVICE_BASE}/api/ask
Content-Type: application/json
body = {"user_query": <用户原问题>}
```

也可使用随仓交付的客户端（`deploy/kg_query.py`），它读 `RAG_URL` 环境变量：

```text
env  = {"RAG_URL": "{SERVICE_BASE}/api/ask"}
argv = ["python3", "deploy/kg_query.py", "--json", user_query]
shell = false
```

执行器若只接受 shell 字符串，应失败关闭或交给支持 argv 的受控运行器；不得退回到字符串插值。

`kg_query.py` 适合日常问答，并保留顶层 `degraded` / `degraded_reasons`；但兼容投影不保留
`graph_paths`、`evidence_bindings` 等全部原始字段。迁移验收必须使用结构化 HTTP 客户端
保留 `/api/ask` 原始 JSON，不得用客户端投影缺失字段来判定通过。

`{SERVICE_BASE}` 由部署方提供，经反向代理 + 鉴权 + TLS 访问；服务本身只绑内网，不直接暴露公网。

## Request Envelope 边界

服务端只接收规范化字段：`user_query`、`risk_level`、`timeliness`、`allowed_sources`。

Subagent Context、跨会话消息、system/developer/tool 说明、终端输出和其他控制脚手架不得进入领域识别。发现输入污染时使用服务端规范化后的 `user_query`；无法提取真实问题则失败关闭，不猜测。

## 问答后检查

- `route` 是否为预期的 `csa`、`rag` 或 `hybrid`；`governance_error`、`error` 均为异常；
- `degraded` 是否为 false（为 true 时说明检索能力受损，答案可信度下降）；
- 来源是否直接覆盖问题，不以数量替代相关性；
- 高风险断言是否有权威证据、时间范围和冲突状态；
- `claim_evidence.finalizer_invoked` 是否为 `true`、`outcome` 是否为 `passed`，且
  `unsupported_high_risk_claims` 是否为 `0`；
- `stats.answer_model` 是否完整记录主模型、Mini 备用、权威摘录与安全拒答的恢复结果；
- 精确题库与明确条款是否走了确定性快路。

线上 `csa` 路由**只服务地面站考题考试条件**，由随仓交付的结构化条件数据直答。关系、匹配、多跳或依赖问题才需要图谱；普通问题不构成调用图谱的理由。

当前迁移版为满足四域 L2 裁剪，已将 `GRAPH_FIRST_DOMAIN_COMBOS` 置空，因此
`graph_first` 不是验收时应强求的可达路由。Neo4j 仍可在 `rag` / `hybrid` 中参与召回；
若响应返回图谱路径，只能使用同时具备有效 `chunk_id` 证据绑定的路径。

## 固定权威

- `rag_chunks.db` 是 `chunk_id -> text` 的文档事实源。
- 地面站结构化条件数据是该域的确定性事实源。
- BM25、向量索引、`ChunkRef` 与 Neo4j 图谱是派生层。
- 图谱路径只有匹配查询域和关系意图，并回填有效 `chunk_id` 后，才能作为文本证据。
- 不允许图谱取代 SQLite，不允许模型生成任意 SQL/Cypher，不允许问答 Agent 写生产数据。

> 已知情况：图谱中有部分历史文本块引用在当前快照中不存在（源系统既有状态）。遇到这类引用时服务按设计失败关闭，不会产出无证据的答案。

## 回答红线

### 知识库优先与失败关闭

- 无人机、CAAC、法规、气象、飞行原理、运行安全、考试与题库类问题默认先查库。
- 生成、改写、方案、SOP 或报告只要依赖上述事实，也必须先查库。
- `HTTP 502/503/504`、`ECONNREFUSED`、`service_unavailable` 表示**服务不可用，不等于库里没有数据**；此时不得用模型常识冒充已查库答案，应如实说明服务不可用。
- 回答生成只允许依次尝试 `DeepSeek -> 豆包 Mini -> 已接受 SQLite 证据的权威摘录 -> 安全拒答`。前一阶段未失败时不得跳到后一阶段；两个模型都失败后，若没有带 `chunk_id`、原文和四域文档身份的合格证据，必须安全拒答。
- Mini 或权威摘录完整恢复且终审通过时以 `fallback_recovered_answer=true` 留痕，不因使用备用链本身判 degraded；恢复失败、流水线异常或终审阻断必须 `degraded=true`，并设置 `unrecovered_model_failure` 或明确错误状态。

### 题库与法规

- `question_bank_hit=true` 只表示检索到题库文档。
- 只有 `question_bank_exact_hit=true` 才能输出题号、原题、选项和正确答案；
  `question_bank_matched_question` 必须是含 `number`、`stem`、`options`、`answer`、
  `chunk_id`、`doc_name` 的对象，内容逐字取自这些字段。
- 明确法规条款走确定性检索与现行法规优先规则；外搜摘要或模型记忆不得覆盖库内权威原文。

### 高风险 Claim

法规、数字、时效、排名和安全动作等断言必须绑定可验证证据。证据不足、冲突或过期时，删除确定性表述、降级说明或转人工复核，不得补造。

服务端要求模型正文附带机器可读 claim-map 控制尾，该控制尾在返回用户前会被移除。终审会校验
正文句覆盖、证据别名白名单、SQLite 原文相关性，以及资格/法规要求是否绑定法规权威来源；未知、
无关或越权证据均失败关闭。调用方不得自行伪造或覆盖 `claim_evidence` 遥测。

### 面向用户的展示

- 默认直接给结论，不汇报检索内部过程。
- 默认不输出 `【来源N】` 临时编号，也不用"根据知识库已有信息"开场。
- 用户明确追问来源时，给《文档名》+条款号/题号。
- 不相关的检索命中不进入答案。

## 只读边界

- 服务端所有 HTTP 端点均为只读；图谱写接口与任意查询接口在交付版中已移除。任何"写入知识库"的请求都应拒绝并说明服务为冻结快照。
- 不读取或输出数据库密码、模型密钥或其他 secrets。
- 数据更新只能由维护方发布新 Release 后由部署方重新部署，agent 侧无任何写入路径。
- `/api/export`、`/api/stats` 会暴露图谱全量与规模信息，不应对最终用户开放。

## 与源环境技能的关系

源环境另有 `knowledge-graph`、`knowledge-graph-hybrid-audit`、`structured-data-sync-csa`、`query-trace-quality-dashboard` 四个技能，它们面向**本机运行仓**，包含导入、同步、审计、治理与评测 SOP，其中引用的脚本、结构化数据源与业务域在线上均不存在。**接入线上服务时不要加载它们**，以本 skill 为准。

## 迁移验收题

在完整交付仓中，以仓库根目录的 `eval/online_subset_20260803.json` 为唯一批量验收题池。
该文件固定为 80 题，来源池 143 题，排除 63 题；不要复制第二份题池，也不要修改或覆盖
维护方的源题池。交付文件 SHA-256 必须为
`7f9cc4c2470f6aa5dcfef6d928429e6b08fb73453d592e3a188d913128e85e2d`。先从该文件按
`id` 读取问题与 `expected_docs`，再调用 `/api/ask`。

比较来源时，仅去掉 `expected_docs` 与响应 `sources[].doc_name` 末尾的 `.txt` 后做精确比较；
不得使用模糊包含或临时别名。服务省略 `.txt` 不算失败。

首轮至少抽检以下五题，题面以 JSON 文件为准，不在 skill 内另存副本：

| ID | 覆盖点 | 预期文档 |
|---|---|---|
| `reg_07` | 实名登记法规 | `政策法规_CCAR-92部.txt` |
| `wth_04` | 雷暴风险与避让 | `理论题库_气象.txt` |
| `sys_04` | 数据链路与系统安全 | `理论题库_系统组成及介绍.txt` + `无人机理论书籍_2023_无人机系统结构与设计_机械工业出版社_李宏达.txt` |
| `app_05` | 物流应用与法规 | `政策法规_CCAR-92部.txt` + `无人机理论书籍_2024_无人机技术概论(第2版)_机械工业出版社_贾恒旦.txt` |
| `trn_07` | 教员考试重点 | `理论题库_无人机教员题库.txt` |

这五题当前都应走 `rag`，不得为了测试图谱而臆造 `graph_first` 预期。每题必须返回可解析
响应、非空 `stats.trace_id`、非空 `sources`，且所有来源均属于四域；`reg_07`、`wth_04`、
`trn_07` 至少命中一个预期文档，`sys_04`、`app_05` 必须命中各自全部两个预期文档。
`degraded=true`、域外来源或无依据肯定回答均判失败。

题池之外另保留五类迁移边界测试：

- 地面站直答：`地面站避让点题型的考试条件有哪些？` 应为 `csa` 且来源非空。
- 混合路由：`2026H1 地面站考试条件有哪些出题特点？` 应为 `hybrid`，同时包含结构化统计与文本依据。
- 精确题库：`大气的组成是由？` 必须 `question_bank_exact_hit=true`，并逐字回显原题。
- 失败关闭：分别询问培训价格、学员名单/成绩、人员排期；三类请求必须返回 HTTP 422、
  `error_type=out_of_scope`、`request_rejected=true`、空 `sources` 和
  `stats.external_completion=false`，不得返回域外事实或启用外部补全。
- 公司身份：四种云技公司名称必须在检索前以 `company_identity` 返回 HTTP 422；
  `星云技术公司` 是近名负控，不得命中该身份规则。

批量完成判据：保留 80 题全部 `/api/ask` 原始 JSON；每题都有 `trace_id`，实际来源不越域，
普通题与各自 `expected_docs` 至少相交，`sys_04` 与 `app_05` 全覆盖；分类计数与题池
`categories` 一致，且全部 `degraded=false`。此外要求激活 Gold 的逐题语义正确性 80/80、终审覆盖率
100%、未恢复模型失败为 0、无依据高风险断言为 0、P95 不超过 7 秒、最大耗时不超过 12 秒，
并证明 80 个 `trace_id` 与同批 hash-chain trace 一一绑定。HTTP 成功只证明接口可用，不等于答案质量通过。

未完成人审时只能显式运行 report-only（输出目录应放在仓库外）：

```bash
python3 skills/knowledge-graph-cloud/scripts/eval_cloud_subset.py \
  --url http://127.0.0.1:5001/api/ask \
  --report-only \
  --output-dir /var/tmp/kg-cloud-eval-report-only
```

report-only 的 `quality_gate_evaluated` 必须为 `false`，不能转述成正确率或发布通过。正式命令还必须
显式提供已完成的 Gold、Gold schema、approval decision、SSHSIG、公钥、预期签名指纹、authority
snapshot 与本批 trace log；缺任一项即失败关闭。顺序固定为：

1. `cloud_gold.py --prepare-approval-decision` 生成待 Gold SSHSIG 决策，固定退出 `3`；
2. `--report-only` 串行采集真实 80 题和原始响应，固定退出 `3`；
3. `--prepare-attestation` 离线重算并生成待评测 SSHSIG 决策，固定退出 `4`；
4. `--formal-offline` 禁止网络和题目子集，验签后重算；只有此步退出 `0` 才是正式通过。

安全拒答必须与已签 Gold 模板字符串全等。评测证明人与 Gold 审批人必须是不同 named human，
并使用不同 SSH public-key fingerprint；decision 构建与 formal 验证都会失败关闭。评测 attestation
必须绑定 80 个原始响应、`trace_id` 顺序、trace 文件哈希/链头/序号、`answer_model`、claim、Gold
approval decision/signature/public-key 哈希、Gold key fingerprint 和 `approved_by` / `approved_at`、
authority、results 与 gate-core。具体参数以脚本 `--help` 和 `DEPLOY.md` 为准。

迁移或升级前先运行 `bash skills/knowledge-graph-cloud/scripts/verify.sh`，校验单元测试、代码清单、
Python/JSON 语法、便携路径与凭据边界。

## 完成检查

- 问题在四域覆盖范围内；不在范围内的已明确失败关闭而非猜测作答。
- 回答使用真实 `/api/ask` 结果，或明确说明服务不可用。
- `degraded` 为 true 时已在答案可信度上作出反映。
- 已接受回答的 `claim_evidence.outcome` 为 `passed`，且没有未支持的高风险 claim。
- 正式批量验收使用已激活 Gold，且不是 report-only；逐题 correctness 与 trace binding 均通过。
- 题号/原题/选项只在 `question_bank_exact_hit=true` 时输出。
- 最终输出没有内部脚手架、临时来源编号或无证据的确定性断言。
