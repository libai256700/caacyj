# 知识问答与知识图谱迁移、更新和交接总手册

> 文档版本：v1.0
>
> 适用对象：AI 实施 Agent、程序员、发布审查人和接收团队
>
> 文档性质：每次迁移、更新、发布准备或部署接收前的强制阅读入口
>
> 状态边界：本文是执行合同，不是批准收据、部署证明或产品验收证明

本手册把首次迁移、后续不定期迭代、GitHub 交付和接收团队部署交接统一为一套可重复执行的流程。任何人不得只凭历史对话、旧候选名称、测试数量或文件时间戳推断当前状态。

## 1. 强制阅读与失败关闭

开始任何比较、同步、实现、封装、GitHub 写入或部署前，必须完整阅读：

1. 本手册；
2. `APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md`；
3. `USAGE.md`；
4. `skills/knowledge-graph-cloud/SKILL.md`；
5. `DEPLOY.md`；
6. 当前任务的控制文件、批准收据、source manifest、release manifest 和回滚材料。

执行者必须在基线记录中写出上述文件的 SHA-256。缺少任一文件、读取不完整、文件哈希在执行期间变化、远端基线前进或合同互相冲突时，立即停止并报告；不得自行选择更宽松的旧条款。

规则优先级如下：

1. 用户对当前任务给出的明确控制文件和批准范围；
2. 本手册的迁移、发布和交接边界；
3. App 同步合同和 `USAGE.md` 的最终用户体验；
4. `SKILL.md` 的实际 App 接口；
5. `DEPLOY.md` 的接收团队操作步骤；
6. 历史文档和历史证据仅作追溯，不作为当前授权。

## 2. 文档职责与保留策略

| 文件 | 唯一职责 | 是否保留独立 |
| --- | --- | --- |
| 本手册 | 迁移、迭代、门禁、GitHub 交付和团队交接总流程 | 是，唯一强制入口 |
| `APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md` | 本地能力转换为便携 App 技能的强制合同 | 是 |
| `USAGE.md` | App 开发者接入和最终用户体验 | 是 |
| `skills/knowledge-graph-cloud/SKILL.md` | App Agent 实际运行接口和回答合同 | 是 |
| `DEPLOY.md` | GitHub 移交后接收团队的部署、验证和回滚 | 是 |

`KNOWLEDGE_QA_CLOUD_MIGRATION_GUIDE.md` 与 `KNOWLEDGE_QA_CLOUD_UPDATE_AND_HANDOFF_RUNBOOK.md` 的有效内容已经合并到本手册。它们不再作为并行入口，避免未来 AI 只读其中一份。

以后删除陈旧文件前必须证明：新文件完整承接有效内容、仓库内无活动引用、manifest 已更新、精确删除清单已进入获批的 Stop C。不得因文件名、时间戳、目录杂乱或存在 `.orig` 就自行删除。

## 3. 不可变系统合同

### 3.1 权威与派生层

- 批准的源文件和 source manifest 定义允许迁移的数据范围。
- `rag_chunks.db` 是 `chunk_id -> text` 的唯一权威正文。
- BM25、chunk/entity 向量和 Neo4j scoped graph 都是派生层，不能反向覆盖权威正文。
- chunk 命中必须 100% 回填 SQLite；entity 命中必须回填 scoped graph 并绑定 SQLite evidence。
- Neo4j 交付形式是 portable scoped JSONL + manifest + importer，不交付某台机器的 store 目录。
- source allowlist、正文、切分、schema 或 identity 变化时，相关派生层必须从新权威全量重建。

### 3.2 App-host-final

- `/api/ask` 提供可选专业上下文，不是最终聊天界面。
- App 宿主模型生成并清理最终用户回答。
- App 不展示 source、route、degraded、error、trace、评测、原始 JSON 或内部处理过程。
- 知识库未命中、内容不足或服务不可用时，App 大模型继续形成自然回答。
- 确定性和权威路径优先；证据充分时服务器回答模型调用数必须为零。
- 服务器回答模型保持 provider-neutral；未获批时 provider、model、endpoint 和 secret 必须为空并失败关闭。

### 3.3 第一版生产向量身份

第一版生产向量固定为：

```text
provider: ollama-local
base_url: http://127.0.0.1:11434/api/embed
model: bge-m3:latest
model_digest: 7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab
dimension: 1024
dtype: f32
normalization: l2
metric: cosine
engine_metric: cos
engine: usearch
engine_version: 2.26.2
network_scope: loopback-only
credentials: none
```

build、query 和 entity 必须共享同一个 Embedding identity。当前批准基线为 1,482 个 chunk 向量和 22 个 entity 向量；数量随获批 source/schema 变化时必须重新冻结证据，不能把本节历史数量当作自动授权。

生产向量随唯一 Server Suite 交付，不进入 App ZIP。fake 32 维向量只允许存在于零网络测试夹具，生产配置、validator、启动和 production-only suite 必须拒绝。

不得把外部 Embedding API 写成当前第一版生产前提。未来如启用任何外部模型或 Embedding 角色，按 `N + M + 2` 重新取得 production Stop B，并全量重建受 identity 影响的派生物。

### 3.4 外部角色与配置

`N + M + 2` 明确表示：1 个 App 宿主最终回答模型、`N` 个服务器回答模型、1 个 Embedding 角色和 `M` 个运维 Agent 模型。即使多个角色复用同一供应商，也必须按用途分别记录和批准。

每个拟启用角色必须冻结 provider 法人和产品、exact endpoint/model/API version/region、数据驻留、不训练条款、retention/delete、输入输出上限、timeout/retry/concurrency、quota/预算/熔断、密钥撤销和允许接收的数据类别。仓库只保存 schema、变量名和 secret reference，不保存真实 endpoint、key、密码或生产身份。

当前本地离线候选不物化这些外部角色，真实 provider 字段保持为空且 fail closed，`real_provider_calls=0`。接收团队未来配置真实调用前必须取得 `stop_b_production_provider_approved`。

### 3.5 两类交付单元


只生成两类最终交付单元：

1. App ZIP：恰好一个 `knowledge-graph-cloud/` 根和一个可发现的 `SKILL.md`，不含 server、ops、数据库、索引、图谱、日志、缓存、内部路径或 secret。
2. Server Suite：包含 server runtime、批准 authority、BM25、生产 chunk/entity 向量、scoped graph、importer、operator companion、App ZIP、SBOM、suite manifest 和 `SHA256SUMS`。

公共 App 与运维组件必须使用不同进程、入口、audience、service account、secret scope、network policy 和 tool registry。公共身份不能发现或调用运维工具。

## 4. 状态与审批边界

以下状态必须分开报告：

```text
local_delivery_package_complete: <true|false>
stop_b_offline_handoff_ready: <true|false>
stop_b_deferred_no_external_processing: <pending|approved>
stop_c: <pending|approved>
github_delivery_complete: <true|false>
deployment_handoff_ready: <true|false>
runtime_active: <true|false>
product_accepted: <true|false>
```

- Stop A 批准架构、source scope 和本地实现边界。
- Stop B 批准外部处理合同；离线无外部处理批准不授权真实 provider。
- Stop C 只授权请求中列出的 GitHub commit、push、tag、Release 和 asset 写入。
- Stop C 不授权 App/server 上传、部署、安装生产依赖、身份/secret 注入、重启、切流、active switch、回滚或生产清理。
- HTTP 200、health、PID、测试数量、manifest 存在、包哈希或 `runtime_active` 均不能单独证明 `product_accepted`。

## 5. 每次迭代的变更分类

开始时逐项填写，不得只写“代码更新”：

| 类别 | 必查差异 | 必须重做的最小证据 |
| --- | --- | --- |
| App 技能 | prompt、客户端、sanitizer、身份回答、schema | App 合同测试、单技能 ZIP、no-secret、Stop C |
| Runtime | route、authority、回答协调器、API、只读边界 | 定向测试、DLP、SBOM、源码 manifest、Stop C |
| Source | 路径、字节、许可、allowlist | 新 source manifest、DLP、Stop A；涉及外发再开 Stop B |
| Authority/BM25 | 抽取、chunk、SQLite schema、索引格式 | 权威覆盖、回填、全量重建、回滚、Stop C |
| Embedding/vector | model/digest/dim/dtype/normalization/metric/engine | identity probe、双索引、正式 reader、全量重建；身份漂移重开 Stop B |
| Graph | schema、实体/关系、manifest、importer、reader | scoped 覆盖、SQLite evidence、portable import 测试、Stop C |
| Server answer | role、provider、model、endpoint、策略、预算 | `N` 个角色合同、披露 ledger、egress、production Stop B |
| Ops/identity | Agent、handler、job、权限、network、audience | public/ops 隔离；架构或权限变化重开 Stop A |
| 依赖/runtime | Python、wheel、USEarch、系统工具、容器 | exact runtime lock、启动探针、SBOM、Stop C |
| 文档/交接 | 合同、命令、清单、责任分配 | 链接、冲突扫描、manifest、Stop C |

一项变更可同时属于多类，证据取并集。source、provider、model、Embedding identity、架构、权限或公开合同漂移时，旧证据失效；不得以“功能相似”复用旧批准。

## 6. 可重复迁移流程

### 6.1 冻结授权和基线

1. 读取第 1 节全部材料并记录哈希。
2. 记录 repository、branch、HEAD、实时 `origin/main`、staged/unstaged/untracked 文件。
3. 记录 source manifest、authority、vector、graph、runtime、App、operator 和 suite identity。
4. 检查是否存在运行中的旧测试或构建进程。
5. 写明本次变更分类、批准范围、排除项和接收团队待办。

使用当前控制文件指定的工作树。只有控制文件未指定且明确允许新建时，才从最新远端基线创建隔离工作树；不得为了流程形式擅自新建、清理、重置或回滚。

### 6.2 比较真实差异

- 比较文件清单和逐文件 SHA-256，不以名称或时间戳判断。
- 比较 prompt、schema、调用链、异常路径、权限、DLP、构建器、validator 和测试，不只比较测试分数。
- 分开报告本地能力、GitHub 当前实现、派生数据和部署状态。
- GitHub 基线在实施期间前进时，停止写入准备，重新审计冲突。

### 6.3 转换和实现

- 只迁移获批差异，不复制整个本地运行目录。
- 移除本机绝对路径、OpenClaw/Feishu/Cron/LaunchAgent、登录态、缓存、PID、trace 和私有 helper 耦合。
- 凭据仅保留变量名、schema 和 secret reference；真实值不得进入 Git。
- runtime 保持只读 active；Builder 只写 candidate；Release Controller 只处理获批 exact identity。
- 保留所有无关 dirty 修改。重叠文件先备份并记录，不得覆盖未知来源的改动。

### 6.4 重建受影响派生物

按以下顺序执行：

```text
approved source manifest
  -> clean rag_chunks.db authority
  -> BM25
  -> loopback-only Ollama BGE-M3 vectors
  -> scoped graph
  -> offline gates
  -> sealed candidate
```

只重建被真实变更影响的层。若现有冻结候选内容与新合同一致且 fresh evidence 可在包外绑定，不得为改名、时间戳、JSON 排版或追求更多测试重新打包。

### 6.5 验证

至少执行与变更范围对应的检查：

- source manifest 和 `CODE_MANIFEST.sha256` 精确覆盖及逐项哈希；
- authority/BM25/vector/graph 定向测试和 SQLite evidence 回填；
- BGE-M3 digest、1024 维、L2、共享 identity、正式 reader 加载；
- production fake-32 拒绝；
- App ZIP 单技能、边界和包内 manifest；
- public/ops 身份、权限、网络和工具隔离；
- DLP 零 finding、合成阳性 canary 拒绝、SBOM 和最终 `SHA256SUMS`；
- 相关单元/集成测试、文档链接、陈旧合同扫描和 `git diff --check`。

DLP 必须覆盖 source 文件及 DOCX/PDF 内嵌 metadata/OCR、SQLite 全部表列、BM25 和向量 metadata、Neo4j label/type/属性/关系两端、provider request fixture、代码、文档、测试输出、日志、receipt、OCI layer 和 zip/tar member。真实候选必须零 finding，合成阳性 canary 必须被拒绝；扫描 receipt 绑定 scanner、规则和对象哈希。

第一次真实运行结果必须保留，失败不能被重试覆盖。Linux x86_64 USEarch、目标 Neo4j import、生产配置/身份、WSGI 和产品 QA 由接收团队执行时，应标记 `pending_receiving_team`，不是本地离线交付阻断项。

### 6.6 封存和 Stop B

最终候选冻结后再生成 receipt、manifest、DLP、SBOM、测试和 hash 证据，所有证据必须绑定同一最终字节。历史 suite 和旧证据只保留追溯用途。

无真实 provider 的本地阶段必须证明：

```text
real_provider_calls: 0
external_data_sent: false
provider_secrets_present: false
```

达到离线门禁后提交完整 Stop B 报告并停止，等待用户批准。不得自行批准任何停点。

### 6.7 Stop C 与 GitHub 写入

Stop C 请求至少列出：

- exact repository、remote、branch/ref、base commit 和拟提交文件；
- staged/unstaged/untracked 差异和保留的无关 dirty 文件；
- 拟 commit message、push refspec、tag、Release 名称；
- 每个 asset 的绝对路径、大小和 SHA-256；
- DLP、SBOM、manifest、测试和回滚材料；
- 被替代文件的精确删除清单及其替代映射；
- 明确排除部署、重启、切流和生产清理。

展示后停止等待用户批准。获批后只执行列出的 GitHub 动作；远端前进、文件集合或 asset 字节变化会使请求失效，必须生成新请求。

GitHub 写入后复核远端 commit/tree/tag/Release asset hash，并生成 `github_delivery_complete` 与 `deployment_handoff_ready` 收据，然后停止。不得进入接收团队部署阶段。

## 7. 接收团队交接

移交材料必须让接收团队无需修改业务源码即可完成：

1. 复算 GitHub commit、tag、Release asset、suite 和包内 manifest 哈希；
2. 在 Linux x86_64 安装锁定依赖并以 `usearch==2.26.2` 加载双索引；
3. 导入 portable scoped graph 并复核计数、归属和 evidence；
4. 注入生产 identity、runtime config、provider config 和 secrets；
5. 分离启动 public WSGI 与 ops WSGI，验证权限、网络和工具边界；
6. 执行 health、回滚演练、安全门禁和完整产品 QA；
7. 只有代表性业务问答和验收门禁通过后声明 `product_accepted=true`。

本地交接报告统一写为：

```text
linux_x86_64_usearch_load: pending_receiving_team
neo4j_import: pending_receiving_team
production_config_and_identity: pending_receiving_team
wsgi_startup: pending_receiving_team
product_qa: pending_receiving_team
```

接收团队应按 `DEPLOY.md` 执行，保存原始输出和 exact release identity。任何失败只证明对应部署项未完成，不能反向篡改本地发布证据。

## 8. 回滚与清理

- 每个 release 必须能同时回退 code、authority、BM25、vector、graph、provider contract 和配置 identity。
- 切换前冻结 pre-state、备份位置、owner/mode 和恢复命令；新旧 release 禁止混用。
- 删除只能针对 Stop C/部署审批中列出的 exact path、object 或 release；禁止宽泛 glob、共享根递归清理和临时手工清库。
- 历史 candidate、receipt、`.orig` 或未知 dirty 文件未经单独批准不得删除。
- 回滚后重新执行同一组部署与产品验收，不得因进程恢复就宣称产品恢复。

## 9. AI 和程序员执行模板

每次迭代任务开头至少提供：

```text
repository: <absolute path or GitHub URL>
designated_worktree: <absolute path>
target_remote_and_ref: <exact remote/ref>
base_commit: <exact commit>
change_scope: <classified changes>
source_manifest: <path + sha256>
current_suite: <path + sha256>
allowed_actions: <exact list>
forbidden_actions: <exact list>
approval_state: <Stop A/B/C status>
receiving_team_boundary: <exact pending items>
```

执行报告至少包含：

```text
baseline_verified: <true|false>
mandatory_files_read: <paths + sha256>
change_classification: <categories>
files_changed: <exact paths>
files_deleted: <exact paths + replacement>
tests_and_gates: <command + first result>
package_identity: <path + size + sha256>
external_processing: <calls/data/secrets>
approval_state: <Stop A/B/C>
github_delivery_complete: <true|false>
deployment_handoff_ready: <true|false>
receiving_team_pending: <exact list>
runtime_active: <true|false>
product_accepted: <true|false>
```

没有相应证据的字段必须写 `false`、`pending` 或 `unknown`，不得补写推测性成功。
