# 知识库迁移仓（私有）

无人机培训知识库的权威备份与线上部署交接物。**本仓为私有仓，内容含受版权保护的教材与自有题库，不得公开或对外分发。**

仓库同时保存可供 caacyj.com 和其他 App 接入的便携技能。技能代码与受版权保护的知识库源料分目录管理，不包含生产凭据、运行时状态或用户数据。

## 目录结构

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
eval/                  线上范围题池、Cloud Gold schema 与 pending 人审模板
skills/
  evaluation-report/              无人机入行评测 V3 便携技能
  recruitment-crawler/            无人机/CAAC 四平台岗位爬取与飞书日报技能
  knowledge-graph-cloud/          ★ 接入线上服务用这一个
  knowledge-graph/                源环境版（本机运行仓，含导入/治理 SOP）
  knowledge-graph-hybrid-audit/   源环境版：审计与健康门禁
  structured-data-sync-csa/       源环境版：结构化同步
  query-trace-quality-dashboard/  源环境版：trace 与质量看板
DEPLOY.md              部署与验收手册（技术人员按此执行）
USAGE.md               使用说明（能回答什么、怎么判断答案可信）
MANIFEST.sha256        原始文档逐文件 SHA256 校验清单
CODE_MANIFEST.sha256   运行代码、云端技能、评测器与交付文档 SHA256 清单
```

数据库快照、检索索引与图谱子图以 **Release 附件**形式发布，不进 git 历史。

## 部署

从 [Releases](../../releases) 下载数据附件，然后按 `DEPLOY.md` 执行。最近已发布基线配对为代码 tag
`kg-code-20260804-01` + 数据 tag `snapshot-20260803`；后续治理候选在完成独立 Cloud Gold 与真实
80 题回放前不是新 Release。不得用 `main`、候选分支或其他数据附件冒充已验收配对。
**先读 DEPLOY.md 的 0.1 节**，那里列出了四条与直觉相反、必须先确认的前提。

`deploy/` 是**运行时最小集**：只包含服务启动与问答所需的模块，不含导入、评测、治理等离线工具链。所有 HTTP 端点均为只读，图谱写接口与任意查询接口已移除。

portable 治理候选在原有三项门禁上增加：Cloud 80 独立 Gold 正确性、hash-chain trace 与安全
轮转、四个云技公司名称的明确域外拒答，以及
`DeepSeek -> Doubao Mini -> 权威摘录 -> 安全拒答` 的完整恢复遥测。每个可接受回答仍必须经过
claim/evidence 终审，并在响应的 `claim_evidence` 与 `stats` 中公开结果和耗时。

线上问答批量验收只使用 `eval/online_subset_20260803.json`。该文件从本机全量题池
按四域白名单生成；本机 `eval/qa_pool.json` 继续服务本机全量知识库，不得替换。
`eval/cloud80_gold_standard_v1.json` 在独立人审与 SSHSIG 完成前保持 pending，只能用于审阅和
report-only 采集，不能证明答案正确率。已审 Gold 与 authority snapshot 只作为仓库外
验收材料：先由人工 Gold 审批人签署，再采集真实 80 题原始响应和 hash-chain trace，
由独立评测证明人签署 attestation，最后完全离线重算。评测证明人与 Gold
审批人必须是不同 named human，并使用不同 SSH public-key fingerprint；只有最后阶段能产生 pass。

## 可复用 App 技能

- [`evaluation-report`](skills/evaluation-report/SKILL.md)：确定性计算无人机入行评测的五维分数、双指数、画像、方向与标签，准备受约束的 LLM 提示词，并校验、消毒和组装报告。
- [`recruitment-crawler`](skills/recruitment-crawler/SKILL.md)：采集猎聘、前程无忧、国聘和智联招聘的无人机/CAAC/低空经济岗位，执行相关性过滤、跨平台去重、质量门禁、幂等飞书日报和独立缺跑监控。
- 其他电脑按需单独提取对应 `skills/<name>/`；不要随技能分发 `knowledge_base/`。私有仓库拉取和 CI 使用者必须具备相应 GitHub 权限。
- 只提取岗位技能：`git clone --depth 1 --filter=blob:none --sparse https://github.com/CAACYJ/-APP-.git caacyj-app-skills && cd caacyj-app-skills && git sparse-checkout set skills/recruitment-crawler`。
- `evaluation-report` 要求 Node.js 18+，在技能目录执行 `npm ci && npm test`；`recruitment-crawler` 要求 Python 3、`agent-browser` 和 `lark-cli`，从仓库根目录运行 `bash skills/recruitment-crawler/scripts/install.sh` 安装，再运行已安装目录内的 `bash scripts/verify.sh` 离线验收。真实配置和登录态必须在目标电脑重新建立。

## 知识问答 Agent 技能

技能不是部署服务所必需的（服务器只跑 `deploy/`），但**App 侧让 agent 调用问答能力时必须加载**——
它们定义了正确的调用方式与安全红线，缺少时接入方容易把 `/api/ask` 当普通接口误用。

### 接入线上服务：只用 `knowledge-graph-cloud`

- [`knowledge-graph-cloud`](skills/knowledge-graph-cloud/SKILL.md)：**与线上部署严格对齐**——只覆盖四个文档域共 35 份文档，
  四域之外（定价、报名、名单、成绩、排期、人员等）一律失败关闭；调用方式为 HTTP `POST /api/ask`；
  不引用任何线上不存在的脚本、数据源或工具链。

### 源环境版（本机运行仓，**不要用于线上**）

下列四个描述的是维护方本机环境：包含导入、同步、审计、治理与评测 SOP，其中引用的脚本、
结构化数据源与业务域在线上**均不存在**。随仓交付仅为存档与源环境参考。

- [`knowledge-graph`](skills/knowledge-graph/SKILL.md)、
  [`knowledge-graph-hybrid-audit`](skills/knowledge-graph-hybrid-audit/SKILL.md)、
  [`structured-data-sync-csa`](skills/structured-data-sync-csa/SKILL.md)、
  [`query-trace-quality-dashboard`](skills/query-trace-quality-dashboard/SKILL.md)

关键红线摘要（两版一致）：题库只有 `question_bank_exact_hit=true` 才能输出题号与原题；服务不可用
（502/503/504、ECONNREFUSED）**不等于**库里没数据，此时不得用模型常识冒充查库结果；
高风险断言必须绑定可验证证据，证据不足时降级或人工复核，不得补造。

## 校验

```bash
shasum -a 256 -c MANIFEST.sha256
bash skills/knowledge-graph-cloud/scripts/verify.sh
```

第一条校验 35 份原始文档；第二条运行云端技能单元测试，并验证 `CODE_MANIFEST.sha256`
对运行代码、技能、评测器和交付文档的精确覆盖。仓库校验通过不等于云端已部署，也不等于 Gold
已激活；线上完成仍须按 `DEPLOY.md` 重启服务，执行 `Gold review/SSHSIG ->`
`report-only collection -> attestation SSHSIG -> formal-offline` 的真实 80 题流程，并取得独立的
`runtime-active` 证据。

## 数据说明

- 原始文档是知识库的**源料**；线上问答服务实际读取的是由其派生的数据库快照与检索索引（见 Release）。
- 本仓内容为**冻结快照**。源料更新后由维护方重新推送并发布新 Release，tag 即数据截止点。
- 服务器上的原始文档副本应置于 Web 目录之外、权限收紧（`chmod 700`），仅供重建索引使用。

## 边界

- 线上服务仅覆盖上述四个文档域。
- 服务端口不得裸露公网，须经反向代理 + 鉴权 + TLS，并限制来源。
- 服务器侧凭据（数据库密码、模型密钥）由部署方独立生成，不复用任何其他环境的凭据。
