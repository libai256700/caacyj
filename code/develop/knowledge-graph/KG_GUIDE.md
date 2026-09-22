# 🗺️ 知识图谱操作指南（KG Guide）

> 最后更新：2026-06-05 15:30 v2.7
> 
> 📌 操作原则：所有规则、经验、踩坑统一定义在此。
> 📌 用户指令与手册冲突时，必须先与用户确认后再执行。
> 📌 增删改只改这一个文件，不再分散。本指南为唯一准绳。
> 📌 每次知识图谱操作前翻阅此指南，按本子办事。

---

## 目录

1. [架构总览](#1-架构总览)
2. [权限与凭据](#2-权限与凭据)
3. [实体抽取规则](#3-实体抽取规则)
4. [关系语义规则](#4-关系语义规则)
5. [导入与删除安全规则](#5-导入与删除安全规则)
6. [质量门禁（健康检查清单）](#6-质量门禁健康检查清单)
7. [踩坑编年史](#7-踩坑编年史)
8. [已知问题（待修）](#8-已知问题待修)
9. [常用操作速查](#9-常用操作速查)
    - [附录A：业务问答引用KG数据规范](#附录a业务问答引用kg数据规范三级分层)
    - [附录B：Model使用规范](#附录bmodel使用规范)

---

## 1. 架构总览

### 目录结构

```
projects/knowledge-graph/
├── pipeline/            # 核心流水线
│   ├── extract_one.py      # ⭐ 主抽取脚本
│   ├── server.py           # ⭐ API/可视化面板
│   ├── cleanup_relations.py # ⭐ 关系清理
│   ├── review_report.py    # 🆕 复盘报告生成器
│   ├── kg_health_check.py  # 🆕 健康检查
│   ├── restore.sh          # 🆕 灾难恢复
│   ├── white_list.json     # 白名单+黑名单
│   ├── config.json         # 配置
│   ├── backup.sh           # 每日备份
│   └── _legacy/            # 🗑️ 废弃脚本（28个历史遗留）
├── feishu_raw/            # 飞书下载的原始文本
├── neo4j/
│   └── .neo4j_pass         # Neo4j密码
└── neo4j-docker/           # Docker部署配置
    ├── docker-compose.yml
    ├── data/               # 数据目录（挂载到容器 /data）
    ├── logs/               # Neo4j日志
    └── plugins/            # 插件（如APOC）
```

### 抽取数据流

```
老文下指令 → 我分析文件类型 → 给出建议
  → 老文确认 → extract_one.py / GPT-5.5 直抽
  → 复盘 → 老文确认 → 下一个
```

### 问答检索数据流（v2.8）

```
用户问题
  → /api/ask
  → CSA结构化快路由（canonical实体表优先，SQLite缓存提速，CSV仍为权威源）
  → 未命中CSA时：Query Rewrite → Dense(bge-m3) + BM25 + Neo4j KG
  → Merge/Rerank → SQLite chunk文本回源 → LLM回答
```

**当前契约：**
- SQLite `rag_chunks.db` 是 chunk 正文唯一回源库。
- Dense/BM25/Neo4j 只提供 `chunk_id`、实体、路径和来源线索，不保存权威全文。
- Neo4j 不再承担 Chunk 全文存储；实体图谱服务于关系推理和证据扩展。
- 结构化业务事实的权威源仍是 `/Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据` 下的 CSV；`/Users/xiaoji/Documents/知识库分析/data/canonical/` 是治理层，`rag_index/csa_cache.sqlite` 是性能缓存层，二者都不能反过来覆盖原始事实源。
- CSA 不进入 Dense/BM25/Neo4j 索引；CSV 更新无需重建 RAG，但必须刷新/验证 canonical 表和 CSA 缓存。
- 7 个 canonical 实体域为：学员、客户、课程、教员、岗位、法规、题库。`document_id` / `regulation_id` / `question_bank_id` 是语义/元数据 ID，不能当作 `chunk_id`；最终证据文本仍只用 `chunk_id` 回源。
- 路由边界统一在 `rag_store/route_policy.py`；CSV-only、RAG-only、hybrid、internal-profile/policy、external-completion 的修改必须配套跑 `scripts/eval_route_policy.py`。
- 统一 ingest 盘点入口：`python3 scripts/build_ingest_manifest.py`，覆盖 CSV、rag_docs/feishu_raw、SQLite、Neo4j、BM25、dense。
- 索引新鲜度入口：`python3 scripts/check_index_freshness.py`，以 SQLite chunk fingerprint 为准，不只看行数。
- 自动健康门禁入口：`python3 scripts/eval_health_gate.py`，每次导入、迁移 chunk、改路由或改检索逻辑后都要跑。
- 业务图谱门禁入口：`make business-graph-governance-check`；完整同步入口：`make business-graph-gate`。
- 业务图谱的 `Skill` / `KnowledgePoint` 必须做命名消歧：能力节点显示为 `xxx（能力）`，证据型知识点显示为 `xxx（知识点证据）`；不能用同名 Skill/KP 合并来凑多跳路径。
- 招聘 Company 只在公司名确实撞岗位标题时才创建 `未标注招聘公司（岗位名）` 消歧节点；普通 jobs.csv 公司必须按公司名稳定合并，并用 `scripts/govern_job_company_duplicates.py` 防止行级 Company 膨胀。
- 业务图谱门禁绿色不等于全图历史关系证据都完整；`REQUIRES` / `REGULATES` / `REFERS_TO` / `HAS_PROPERTY` / `REQUIRES_SKILL` / `HAS_CLASS` 的存量证据治理单独走 `scripts/govern_graph_evidence.py`。
- 统一业务入口：`RAG_URL=http://localhost:5001/api/ask python3 kg_query.py "问题"`。
- 回归命令：`python3 scripts/eval_csa.py`、`python3 scripts/eval_smoke.py`。
- 扩展质量评测：`python3 scripts/eval_smoke.py --questions eval/quality_questions.json --min-source-rate 0.95 --min-hit5-rate 0.80 --max-degraded-rate 0.05`。
- 问答诊断 trace：`eval/query_traces.jsonl`；KG 噪声审计：`python3 scripts/audit_kg_noise.py`。

### 关键变化（v2.8）
- ⚡ **业务图谱治理门禁**：新增 `make business-graph-governance-check` / `make business-graph-gate`，把多跳业务 eval、bridge dry-run、type conflict dry-run、jobs.csv Company 去重 dry-run 串成固定门禁。
- ⚡ **Skill/KP 命名消歧**：业务入口 `Skill` 统一显示为 `xxx（能力）`；用于连接 SQLite chunk 证据的 `KnowledgePoint` 统一显示为 `xxx（知识点证据）`，禁止靠同名合并凑路径。
- ⚡ **jobs.csv Company 膨胀治理**：Company 消歧只允许在公司名撞岗位标题时发生；历史行级 Company 重复由 `scripts/govern_job_company_duplicates.py` 合并并由 dry-run 防回归。
- ⚡ **当前业务图谱基线**：2026-06-06 gate 后 Neo4j 为 5749 节点 / 392660 关系 / 76 文档 / 5673 实体；Company 295，其中 jobs.csv Company 293；同名跨类型冲突 0，jobs.csv Company duplicate groups 0。
- ⚡ **关系证据 backlog 分离**：业务图谱 gate 只保证本轮业务同步和多跳桥接干净；历史关系证据缺口仍需单独治理，不得把 gate 绿色解释成全图关系均已具备 `source_doc/source_chunk_ids`。

### 关键变化（v2.7）
- ⚡ **结构化层三分法**：CSV 是事实源，canonical 表是治理层，CSA SQLite cache 是性能层；任何修复都不能把 cache 当主库。
- ⚡ **统一实体主键**：7 个业务/知识实体域采用稳定 canonical id；法规/题库/文档语义 ID 与 `chunk_id` 分离。
- ⚡ **统一 ingest manifest**：用 `ingest_manifest.json` 盘点 CSV、源文档、SQLite、Neo4j、BM25、dense，不再靠手写清单判断覆盖。
- ⚡ **导入后自动校验**：SQLite/BM25/dense 新鲜度、route policy、smoke/quality/CSA health gate 作为导入和路由改动后的标准动作。
- ⚡ **source_doc 别名规则**：判断 Neo4j 文档覆盖时必须走 `rag_store/source_doc_aliases.json`，不能只做字符串等值。

### 关键变化（v2.6）
- ⚡ **统一 /api/ask 入口**：结构化 CSV 和双 RAG 问答都先走 `kg_query.py`。
- ⚡ **CSA 已集成**：学员、教员、培训进度、价格、岗位、客户/客资问题自动走实时 CSV。
- ⚡ **双 RAG 稳定契约**：bge-m3 Dense + BM25 + Neo4j KG，最终文本统一从 SQLite 回源。
- ⚡ **评测闭环**：CSA 5题评测 + smoke 15题评测为当前健康基线。

### 关键变化（v2.4）
- ⚡ **不再自动扫描飞书**：按需抽取，老文指哪个文件才抽
- ⚡ **不再批量全量跑pipeline**：逐个文件手动抽取，GPT-5.5 主抽取
- ⚡ **结构化数据不抽图谱**：播放量、岗位报告等分流到CSV
- ⚡ **28个废弃脚本移入 `_legacy/`**，活跃脚本精简为 3 个
- ⚡ **关系体系升级**：新增 SUBCLASS_OF / PART_OF / DEFINED_BY 三类精确关系，降低 BELONGS_TO 占比
- ⚡ **实体双标签机制**：`:KnowledgePoint:Entity` 替代单 `:Entity` 标签

### 可视化面板
- 启动: `python3 pipeline/server.py`
- 前端: `pipeline/static/index.html`（本地CDN引用）
- API: `http://localhost:5001/api/health`
- ⚠️ 图谱节点 > 1500 时需同步提升 server.py 的 LIMIT 值（当前实体=2000，文档→实体边=4000）
- ⚠️ canvas=0 原因：edge ID重复或e.id未设（已修复）

### 数据库凭据
- URL: `bolt://localhost:7687`
- 用户: `neo4j`
- 密码: `projects/knowledge-graph/neo4j/.neo4j_pass`
- 部署: Docker容器（`neo4j:latest`→2026.04.0，2026-05-17从brew迁移）
- 容器名: `yunji-knowledge-graph`
- 主机数据目录: `projects/knowledge-graph/neo4j-docker/data/`
- 启停: `docker start yunji-knowledge-graph` / `docker stop yunji-knowledge-graph`
- 状态检查: `docker ps | grep yunji-knowledge-graph` / `docker logs --tail 50 yunji-knowledge-graph`
- 配置文件: `projects/knowledge-graph/neo4j-docker/conf/neo4j.conf`

---

## 2. 权限与凭据

### 飞书App
- App ID: `cli_a9671c9b1b78dbd9`
- 自动获取token（online_extract.py内建refresh_token()，旧流程代码）
- 飞书API直调：在python脚本中用requests调用即可
- 文件操作需要使用正确的Authorization头: `Bearer {token}`（⚠️ 不要写成`***{token}`）

### Neo4j
- 密码存于`.neo4j_pass`文件
- 本项目查询结果对象中观察到`r.get('name')`返回None，统一使用index访问: `r[0]` 代替 `r.get('name')`

---

---

## 3. 实体抽取规则

### 3.1 类型约束

实体类型必须从**类型白名单**中选择（见3.3节，当前共22类），LLM抽取时必须严格遵守：

| 真实类型 | 必须标注 | 禁止标注 |
|---------|---------|---------|
| 地名（北京、武汉、南京等） | `Location` | `Event` ❌ |
| 公司/组织 | `Company` / `Organization` / `PlatformPresence` | - |
| 岗位/职位 | `Position` | - |
| 事件/活动 | `Event` | - |
| 知识点 | `KnowledgePoint` | - |
| 课程 | `Course` | - |
| 考试 | `Exam` | - |

⚠️ **Company类型**：不限于特定公司。LLM识别为公司的即可归入此类，不用设举例限制。

⚠️ **Position类型**：无人机飞手、教员，以及所有与低空经济相关的岗位。范围不限，LLM可用自身知识判断。**不确定是否低空经济相关岗位 → 停下来问我确认**。

⚠️ **Event类型**：和教学、考试、云技科技公司业务相关的所有活动。

⚠️ **Certification类型**：证书/资质，包括CAAC执照、ASFC执照、人社部证书等。LLM可用自身知识补充其他相关证书。

⚠️ **Category类型**：以知识库的文件夹和文件名进行分类。

⚠️ **Student类型**：所有参加学习的学生。

⚠️ **Teacher类型**：具备CAAC教员执照的老师。

⚠️ **Policy类型**：包括但不限于中国民航局（CAAC）、民航局下属协会颁发的法律法规，以及国家颁布的所有法律法规。

⚠️ **Regulation类型**：同Policy类型的定义。

⚠️ **PlatformPresence类型**：平台账号，包括但不限于视频号、抖音号、小红书等。

⚠️ **Location标成Event** 是2026-05-21踩过的坑，会导致同一个地名出现两个独立节点。

⚠️ **Organization类型**：涉及CAAC执照培训的相关组织，包括但不限于：
    - CAAC（中国民用航空局）
    - AOPA（中国航空器拥有者及驾驶员协会）
    - CAGIS（中国地理信息产业协会）
    - CATA（中国航空运输协会）
    - ASFC（中国航空运动协会·国家体育总局）

⚠️ **Exam类型**：CAAC执照考试（理论/实飞/地面站/应急返航），具体内容参考「云技科技新员工培训资料」第二部分·CAAC执照考试内容。

⚠️ **Course类型**的参考范围不限于举例。所有课程表和新员工培训资料中涉及的课程都可以归为Course。实际图谱中有101个Course实体，以课程表和培训方案中的内容为准。

⚠️ **KnowledgePoint类型**范围广，不用举例限制。LLM能识别为知识点的即可归入此类。**LLM不确定是否知识点 → 停下来问我确认**。

⚠️ **SocialContent类型**：社交内容（帖子、视频内容等），包括各平台发布的文案、视频、图文内容。

⚠️ **禁止抽取表头/字段名作为实体**（如"核查内容"被当成学生姓名），LLM需排除表格标题行。

⚠️ **禁止类型留空或标Other**，必须归入白名单中的某类。

### 3.2 命名与去重

- 同名实体必须 **MERGE**（用 `name` 匹配），不能 **CREATE**
- ⚠️ **不要用 `id` 做MERGE！** 不同的文档抽取时LLM会生成不同id（如`每日岗位信息_16` vs `每日岗位信息_55`），id不同但name相同的实体应该合并为一个节点
- ⚠️ **此规则已通过name MERGE机制在pipeline代码中落地**，执行前如有疑问可人工复核
- 正确写法：`MERGE (e:Entity {name: '北京'})` 而不是 `MERGE (e:Entity {id: '每日岗位信息_16'})`
- 同名+同类型实体合并，保留非空属性和所有关系
- 同名但不同类型（如一个标Location一个标Event）→ 先修正类型再合并
- 纯数字实体（如"5000-9000"）⊆ 带单位版本（"5000-9000元"）时删除纯数字版本

#### 3.2.1 离散关系处理规则（2026-05-21新增）

- LLM抽取的关系中，如果 `from_id` / `to_id` 在 name_map 中找不到对应的已入库实体 → 该关系**不应成为孤立边**
- 处理方式：将关系端点改为来源文档（`Document`节点），即 `(Document)-[:MENTIONS]->(Entity)` 或 `(Entity)-[:MENTIONED_IN]->(Document)`
- 不要在写入时静默丢弃，而是标记为 `_unresolved` 并记录日志
- 后续可根据文档名回溯校验

#### 3.2.2 同名别名合并规则（2026-05-22 GPT审计新增）
- ⚠️ 同一实体的别名必须手动合并：如「湖北云技科技」≠「湖北云技科技有限公司」但指向同一公司
- 全称+简称同时出现时 → 保留全称，简称作为别名属性 | 或使用统一标准名
- 抽取prompt中增加提示：「如果遇到公司/组织名称，优先使用全称」
- 写入时按name MERGE，但需人工审核别名情况
- 别名问题优先级：P1，影响实体去重和查询召回

### 3.3 类型白名单（22类）

Entity的类型必须从以下22类中选择，不能留`Other`或`null`：

```
Location, Position, Company, Organization, PlatformPresence,
Event, Course, Exam, Certification,
KnowledgePoint, Category, Student, Teacher, Person,
Policy, Regulation, SocialContent, Skill, EducationRequirement,
AircraftType, LicenseLevel, WeightClass
```

**规则：**
- LLM抽取时每个实体必须归入这22类之一，不能写`Other`、`''`、`null`
- `Person`类无限制：LLM识别出人名即可归入，不用设举例限制
- ⚠️ **LLM不确定是否人名的 → 停下来告诉我确认**
- ⚠️ **LLM不知道归哪类 → 停下来告诉我，由我手动增加实体类型白名单**
- 🆕 `AircraftType`: 无人机机型（多旋翼、单旋翼、垂直起降固定翼、固定翼、直升机、飞艇、滑翔机、自由气球、特殊类等）
- 🆕 `LicenseLevel`: 执照等级（视距内驾驶员、超视距驾驶员、教员、动力升空器等）
- 🆕 `WeightClass`: 重量分类（微型、轻型、小型、中型、大型、农用）
- 🆕 关系 `HAS_CLASS`: AircraftType→WeightClass
- 🆕 关系 `HAS_LEVEL`: Certification→LicenseLevel
- 🆕 关系 `USES`: Course→AircraftType
- 🆕 关系 `REQUIRES`: Course→LicenseLevel（例如精英教员就业班 REQUIRES 超视距驾驶员）

### 3.4 文件夹映射与实体归属

**⚠️ 铁律：实体抽取后必须自动归属到对应Category**（基于文档→实体CONTAINS关系链反推）

| 文件来源 | 实体类型 | 归属Category |
|---------|---------|------|
| 岗位信息报告 | Position, Company, Location, PlatformPresence | 就业资源 |
| 制度/员工手册/入职 | Policy, Event | 公司制度 |
| 培训计划/题库 | Course, Exam, Certification, KnowledgePoint | 培训体系 |
| 咨询客户/测绘 | Company, Organization, Category | 咨询客户 |
| 学员记录 | Student, Teacher | 学员管理 |
| 法规/规范文件 | Policy, Regulation | 行业规范 |
| 无人机理论知识文档 | KnowledgePoint, Skill | 无人机理论知识 |
| 公众号内容 | — | ⛔ 黑名单 |

归属算法（`write_neo4j` + 健康检查脚本均实现）：
1. 先看 `source_doc` 字段推断
2. source_doc为NULL时，通过实体被哪个Document→CONTAINS反推
3. 仍无法判断时，通过BELONGS_TO链推断

⚠️ **Category实体必须设置id属性**，否则可视化API返回id=None，前端无法渲染BELONGS_TO边。
⚠️ **可视化API的Entity→Entity边需用ORDER BY优先BELONGS_TO**（骨架边），防止关键归属连接被LIMIT截断。

### 3.5 LLM调用逻辑（提取的核心引擎）

#### 3.5.1 降级链

```
GPT-5.5（主抽取，中转站）→ 失败 → 停下来问老文确认 → Doubao（降级执行）
    ↓                                        ↓
  重试3次                                 尝试抽取JSON
  180s超时                                180s超时
```

**降级必须经老文确认后再执行，不可自动跳过。**

🚨 **模型降级铁律（2026-05-27 老文补充）：**
- 抽取阶段：必须使用 GPT-5.5，不可切到 DeepSeek Flash
- 审计阶段（单文件抽取后质量审计）：优先 Claude Opus，不可用时经老文确认后降级 Doubao
> ⚠️ 注意：此处的「审计」特指单文件抽取后的 **实体类型/关系/粒度质量检查**。另有一种 **全量实体内容审计**（检查已入库实体描述的事实正确性和完整性），使用 Doubao Seed 2.0 Pro，详见 §11.4。
- 任何自动降级行为视为违规
- 实战证明：GPT-5.5 本地中转对 15k+ 文件有超时风险，但坚持 GPT-5.5 + 加长超时 + 换 http.client 直连即可全部跑通

**全部失败时**：返回空 `{"entities": [], "relations": []}`，不阻塞后续文件。

#### 3.5.2 各层级参数

| 层级 | 模型 | max_tokens | temperature | retry | 用途 |
|------|------|:----------:|:-----------:|:-----:|------|
| **GPT-5.5** | gpt-5.5(中转站) | 8192 | 0.1 | 3次(间隔3s) | 主抽取引擎（所有文件默认用此） |
| **Claude Opus** | claude-opus-4-7(t8star) | — | — | — | 🔍 质量审计/交叉验证（t8star中转站） |
| **Doubao** | doubao-seed-2.0-pro | 8192 | 0.1 | - | 降级兜底（须经老文确认后使用） |

⚠️ **审计铁律：单文件抽取后的质量审计、交叉验证、复盘检查必须用 Claude Opus，不可用 GPT-5.5 代替。** 注：此处「审计」指抽取实体类型/关系/粒度的质量判断（§11.2），不包含全量实体描述内容审计（§11.4，后者用 Doubao）。

#### 3.5.3 Prompt策略

**系统消息**（所有层级通用）：
```
只输出JSON，不要markdown代码块
```

**抽取Prompt**（GPT-5.5 和 Doubao 通用）：
- 提供文件夹上下文（`folder_hint` + `entity_types`）
- 输出格式：`{"entities":[{"name":"","type":"","properties":{}}], "relations":[{"from":"","to":"","type":""}]}`

#### 3.5.3 截断策略（2026-05-27 实战补充）

| 文件大小 | 策略 | 示例 |
|---------|------|------|
| ≤15k 字符 | 全量提取，一次过 | 概述(12k)、空中交通管制(10k) |
| 15k~50k 字符 | 优先分段或提高截断上限；不得只取前段后宣称完整 | 综合问答(49k)、飞行手册(36k) |
| >50k 字符 | 必须分段提取，每段独立 JSON | 飞行原理(101k)、气象(59k) |

⚠️ **2026-05-27 教训**：最初用 12000 截断导致飞行原理（101k）只抽了 12% 内容（约 36/300 题），后改为分段抽取才算完整性。
⚠️ 分段提取需确保每段输出独立 JSON，MERGE 去重时不会冲突（同一 `name` 只会保留一个节点）
- 当前 `extract_one.py` 仍有 12000 字符读取限制；处理 15k+ 文件前必须确认覆盖策略，不得把部分抽取当成全文抽取
- 关系白名单：`SUBCLASS_OF | PART_OF | DEFINED_BY | REFERS_TO | REQUIRES_SKILL | INCLUDES | REGULATES | HAS_PROPERTY | OFFERS | AWARDS | REQUIRES | USES | ISSUED_BY | LOCATED_AT | BELONGS_TO | HAS_CLASS | HAS_LEVEL`
- ⚠️ schema文件（规范/制度/价格表）有多行数据，LLM抽取可能会漏掉其中的重要实体。建议：优先逐行读文档，每行检查实体后再输出JSON
- ⚠️ 价格表、学员、岗位、客户等结构化数据优先进入 CSA/CSV；只有用户明确要求把课程实体纳入图谱时，才按"行=Course"模式抽取，每行课程必须包含 price/duration/content 属性

**分析Prompt**（降级确认前使用，不用来抽数据）：
- 只用前3000字符预览
- 输出规则：`{"doc_type":"", "entity_types":[], "relation_rules":{}}`

#### 3.5.4 文件夹上下文注入表（FOLDER_TYPE_MAP）

不同文件夹自动注入不同的实体类型提示：

| 文件夹 | 注入类型 |
|--------|---------|
| 企业信息/介绍 | Company, KnowledgePoint, Skill, Course, Category, Policy |
| 企业信息/产品 | Category, Skill, KnowledgePoint, Course, Regulation |
| 企业信息/价格 | Course, Certification, LicenseLevel, AircraftType, WeightClass |
| 企业信息/培训 | Course, Certification, LicenseLevel, AircraftType, WeightClass, Organization, Regulation, Event |
| 企业信息/规范 | Regulation, Organization, Certification, Course, AircraftType, LicenseLevel, KnowledgePoint |
| 岗位信息报告 | Position, Company, Location, EducationRequirement, PlatformPresence |
| 咨询客户情况 | Person, Organization, Category |
| 培训学员记录 | Person, Course, Skill |
| 培训计划 | Course, Event, KnowledgePoint, Person |
| CAAC题库 | KnowledgePoint, Regulation, Certification, Skill |
| 制度 | Policy, Position, Event |
| 运营组 | PlatformPresence, SocialContent, Person |
| 企业信息 | Organization, Course, Certification, KnowledgePoint |
| 教材/理论书籍 | Chapter, Section, KnowledgePoint, Scenario, Skill, Regulation |
| default | Organization, Person, Event |

⚠️ 运营组下的「公众号内容」在黑名单中，不会走到抽取流程。
⚠️ 教材/理论书籍（2026-05-27 新增）：走三层架构（Chapter→Section→KnowledgePoint），用 PART_OF 串联层级，ApplicationScenario 标注应用场景。

#### 3.5.5 JSON解析策略

1. `json.loads(text)` — 如果以`{`开头直接解析
2. 失败 → 返回None → 触发降级到下一层
3. 所有实体和关系的`id`字段由LLM生成（`ent_1`格式）→ 写入Neo4j时会映射为`name_map`

#### 3.5.6 写入Neo4j逻辑（v1.5 已修复为name MERGE）

```python
# 实体（✅ v1.5已改为按name MERGE + ON CREATE SET id）
result = session.run("MERGE (e:Entity {name:$n}) ON CREATE SET e.id=$eid SET e.type=$t, ... RETURN e.id AS actual_id", ...)
actual_eid = result.single()[0]  # 返回已有id（合并）或新id（新建）

# 关系（通过name_map将LLM生成的id映射到Neo4j实际id）
# ⚠️ 05-20踩坑：实体用「每日岗_1」创建，关系用LLM原始「ent_1」匹配
# → name_map加入 orig_id → actual_id 映射解决
MATCH (a:Entity {id: name_map[rel.from_id]})
MATCH (b:Entity {id: name_map[rel.to_id]})
CREATE (a)-[:BELONGS_TO]->(b)  # 关系类型从LLM输出映射（实际代码根据rel_type动态选择）
```

---

#### 3.5.7 代理/网络故障排查（2026-05-27 新增）

**症状**：`requests.post()` 超时，日志显示 `Read timed out (host='127.0.0.1', port=7897)`

**原因**：Clash Verge 等代理软件在系统层面劫持 HTTP 流量

**解决方案（按优先级）：**
1. `requests.Session().trust_env = False` — 禁用 requests 的系统代理
2. `os.environ.pop('http_proxy', None)` — 清除环境变量
3. **终极方案**：用 `http.client.HTTPConnection` 直连，绕过 requests 库的代理处理
4. 或：Clash Verge → 设置 → 添加目标 IP 到绕过列表

**超时设置建议：**
- 小文件（≤15k）：180s
- 大文件（15k+）：600s
- 所有中转站均失败后降级：先询问老文，不可自动降级

---

## 4. 关系语义规则

### 4.1 铁律：实体关系禁区（2026-05-22 GPT 5.5审计更新）

#### SalaryRange（2026-05-22 已从图谱中删除）

> SalaryRange类型已从20类白名单中移除。图谱中原有的14个SalaryRange（价格表8个+薪酬体系6个）已在2026-05-22审计修复中全部删除。

#### SalaryItem 禁区
```
✅ SalaryItem 只应收：Policy-CONTAINS→SalaryItem 或 Position-HAS_SALARY→SalaryItem
🚫 SalaryItem 不应有外出关系（MANAGES / CONTAINS / REGULATES / LOCATED_IN / BELONGS_TO 全禁止）
```

#### LOCATED_IN 约束
```
✅ LOCATED_IN 的目标必须是 Location 类型实体
🚫 目标不是 Location 的 LOCATED_IN 关系 → 删除
```

#### BELONGS_TO 严格约束
```
✅ BELONGS_TO 仅限以下场景：
  - Person → Organization (员工属于公司)
  - Entity → Category (实体属于分类)
  - Person → Person (学员属于教员)
🚫 BELONGS_TO 不可用于：非层级关系的弱关联
  - SalaryItem → Policy ❌
  - Product → Department ❌
```

#### MANAGES / REGULATES 约束
```
✅ MANAGES 仅限：Person / Position → 被管理对象
✅ REGULATES 仅限：Policy / Regulation → 被规约对象
🚫 SalaryItem / Product / Event 不可 MANAGES 或 REGULATES 其他实体
```

#### REFERENCES 约束
```
✅ REFERENCES 仅用于文档或政策条款的相互引用
🚫 薪酬项不应对多个政策无差别 REFERENCES → 改为 CONTAINS 或 HAS_SALARY
```

### 4.2 文档关联

- pipeline自动建立关联（`write_neo4j` 内置，2026-05-21新增）
- 新导入的岗位报告自动建立 `RELATED_TO` 给已有同类文档
- `每日岗位信息报告_*` 系列间互相关联
- `每日岗位信息报告_*` 与 `低空经济岗位周度分析报告_*` 关联
- `无人机岗位招聘日报_*` 与所有岗位报告关联

### 4.3 实体分类归属

- 每批提取的实体自动挂到五分类Category下（`write_neo4j`自动执行）
- 就业资源 ← 岗位报告实体 | 公司制度 ← 制度实体 | 培训体系 ← 培训实体
- 咨询客户 ← 客户实体 | 学员管理 ← 学员实体
- Category本身必须有 `id` 属性，否则可视化无法显示BELONGS_TO边
- 归属逻辑：source_doc → Document CONTAINS反推 → BELONGS_TO链兜底

### 4.4 关系类型规范（2026-05-27 更新：SUBCLASS_OF / PART_OF / DEFINED_BY）

#### 优先使用的精确关系
| 关系类型 | 适用场景 | 示例 | 替代 |
|---------|---------|------|------|
| `SUBCLASS_OF` | 分类层级：子类→父类 | A类空域→管制空域、微型无人机→无人机空机质量分类 | 替代泛化的 BELONGS_TO |
| `PART_OF` | 组成部分：部件/成员→整体 | 空中交通管制服务→空中交通服务、机场起落航线→机场飞行空域 | 替代泛化的 BELONGS_TO |
| `DEFINED_BY` | 法规依据：知识点→法规 | 空域分类→中华人民共和国民用航空法、飞行高度划分→CCAR-71部 | 替代方向混乱的 REGULATES |
| `REFERS_TO` | 引用关系：知识点引用法规 | 无人机分类→民用无人机驾驶员管理规定 | — |
| `REQUIRES_SKILL` | 技能需求：知识点→操作技能 | 农林喷洒作业→超低空飞行作业技能 | — |
| `INCLUDES` | 集合→元素 | 空中交通服务→包含→空中交通管制服务 | — |
| `REGULATES` | 法规约束：法规→知识点 | 中华人民共和国民用航空法→空域分类 | 方向必须为 Regulation→其他 |
| `HAS_PROPERTY` | 属性关系：实体→属性 | 电机→KV值、电池→记忆效应 | — |

#### 慎用（语义模糊，仅在归类困难时用）
- `BELONGS_TO` — 仅保留用于人员归属（学员→教员）、客户归属（客户→分类）
- **不要用于等级归属**（应改用 SUBCLASS_OF）
- **不要用于整体-部件关系**（应改用 PART_OF）
- **不要用于文档来源关系**（应改 `MENTIONED_IN` / `EXTRACTED_FROM`）
- **不要用于弱语义关联**（如SalaryItem BELONGS_TO Policy → 应用 CONTAINS）

#### 禁止使用的模糊关系
- `MENTIONS` — 语义空洞，应替换为 DEFINED_BY 或 REFERS_TO
- `DESCRIBES` — 同MENTIONS，应替换为更精确的关系或用 HAS_PROPERTY

---

## 5. 导入与删除安全规则

### 5.1 导入顺序铁律（2026-05-17 老文指令）

**必须先更新飞书云文档，确认无误后才能导入知识图谱**

```
❌ 错误：先入库再回头看云文档
✅ 正确：飞书云文档更新 → 确认内容无误 → 再导入KG

### 5.1.1 导入后自动清理违规关系（2026-05-22 新增）
- 每次抽取入库后必须运行 `python3 pipeline/cleanup_relations.py`
- 该脚本自动删除以下违规关系：
  - SalaryItem 所有外出关系
  - LOCATED_IN 指向非Location的关系
  - MANAGES/REGULATES 主体是 SalaryItem/Product/Event 的关系
  - BELONGS_TO 源头是 SalaryItem 的关系

### 5.1.2 CONTAINS 边保护规则（2026-05-22 新增）

**背景**：抽取脚本用 `MERGE (e:Entity {name:...})` 合并同名实体。培训方案LLM输出了已在制度中存在的"基本工资""五险一金"等实体名，MERGE找到旧节点后建了CONTAINS边，导致培训方案文档错误关联了制度实体。

**规则**：
1. `extract_one.py` 写入时使用 `_created_by` 字段标记首次创建该实体的文档
2. `MERGE` 时 `ON CREATE SET e._created_by = $doc_name`，`ON MATCH` 不变更
3. 仅 `_created_by == doc_name` 时才建立 `(d:Document)-[:CONTAINS]->(e:Entity)` 边
4. 已有实体（`_created_by` 指向其他文档）→ 不建CONTAINS边，防止交叉污染

**修复脚本**：`extract_one.py` 的 `write_neo4j()` 函数已实现此逻辑

**锚定机制**：
- 每次提取后自动将文档锚定到核心实体「湖北云技科技有限公司」
- 确保新文档的实体不会成为孤立岛
- `extract_one.py` 的 `extract()` 函数末尾自动执行

**验证方式**：
```cypher
MATCH (d:Document)-[r:CONTAINS]->(e:Entity)
WHERE e._created_by <> d.name
RETURN d.name AS 文档, count(r) AS 污染数
```

### 5.1.3 导入分类铁律（2026-05-21 教训）

**禁止在导入脚本中硬编码Category！**

```
❌ 错误：写入脚本里写死 category = '公司制度'，不看文件内容
   → 导致政府管理规范文件被错误挂到公司制度下
✅ 正确：导入前确认文件类型 → 人工或自动判断所属Category → 再执行
```

当前7大Category：就业资源 | 公司制度 | 培训体系 | 咨询客户 | 学员管理 | 行业规范 | 无人机理论知识

判断依据：
1. 文件名/文件夹名推断
2. 文件内容主题（如含"规范"→行业规范，含"员工"→公司制度）
3. 老文确认 🤚

**不确定归属时→先问老文，不要猜！**
```

### 5.2 知识冲突规则（2026-05-17）

### 🔑 核心原则：保护名单 > 冲突确认 > 自动覆盖

不同实体在冲突时的处理优先级：

| 优先级 | 实体类型 | 冲突时行为 |
|:------:|----------|-----------|
| 1（最高） | **核心保护名单** | 自动跳过，保留旧值，记录日志 |
| 2 | **普通实体** | 生成冲突清单，手动确认后才能覆盖 |
| 3 | **孤立/无引用实体** | 可以自动覆盖 |

### 5.2.1 核心实体保护名单

以下实体**只读保护，不允许任何自动覆盖或删除**：

⚠️ **此规则已在操作规范层面生效，但pipeline代码（white_list.json protected_entities字段 + 自动跳过逻辑）尚未完全落地**

| 类型 | 内容 |
|------|------|
| **公司** | 湖北云技科技、云技科技及相关品牌 |
| **核心资质** | CAAC资质、培训资质、认证等 |
| **核心课程** | CAAC执照培训方案、核心课程体系 |

保护名单由`white_list.json`中的`protected_entities`字段管理。

### 5.2.2 冲突处理流程

导入新知识时：
1. 自动扫描新旧内容冲突，生成冲突清单（冲突实体、旧值、新值、来源文档）
2. 核心保护名单中的实体 → **自动跳过**，记录日志（如："湖北云技科技 被新文档覆盖，已跳过"）
3. 其他实体 → **等待手动确认**后才能执行覆盖/删除
4. 禁止任何自动修改冲突数据的行为

### 5.3 删除前必须查共享（铁律）

```cypher
// 正确流程：
// 1. 查实体是否有其他文档引用
MATCH (d:Document {name:'xxx'})-[c:CONTAINS]->(e:Entity)
OPTIONAL MATCH (e)<-[:CONTAINS]-(other:Document)
WHERE other <> d
RETURN e.name, count(other) AS shared_refs

// 2. 共享实体：只删关系，不删节点
DELETE c

// 3. 独有实体：确认无其他引用后再删
DETACH DELETE e
```

### 5.4 禁止的操作

- ❌ 直接 `DETACH DELETE d, e` 删文档+实体组合（会误删共享实体）
- ❌ `MATCH (d:Document)-[c:CONTAINS]->(e) WHERE ... DETACH DELETE d, e`

### 5.5 重建被误删的实体

如果不小心删了共享实体：
1. 检查其他文档是否丢失了关系
2. 用MERGE重建同名实体
3. 但重建的节点是孤立的（无其他文档引用），需要标记或清理

---

## 6. 质量门禁（健康检查清单）

每次pipeline抽取后或定期检查时，按以下清单验证：

### 6.1 覆盖率检查
```
✅ 5个一级子文件夹是否全部扫描
✅ 每个文件夹的文件数是否记录
✅ 新增文件是否被处理
```

### 6.2 类型合规检查
```
✅ 无 NULL 类型的 Entity
✅ 无 Folder/Document 混入 Entity
✅ 所有 Location 类型的实体确认为地名
✅ 无 type='Other' 或 type='' 的实体
```

### 6.3 关系合规检查
```
✅ SalaryItem 无任何外出关系（MANAGES/CONTAINS/REGULATES/LOCATED_IN/BELONGS_TO全禁止）
✅ LOCATED_IN 的目标都是 Location 类型
✅ BELONGS_TO 仅用于层级归属（Person→Org / Entity→Category / Person→Person）
✅ MANAGES/REGULATES 的主体是 Person/Position/Policy，不是 SalaryItem/Product/Event
✅ REFERENCES 仅用于文档/政策引用，非薪酬项到政策的扩散引用
✅ 无逆向关系
```

### 6.4 完整性检查
```
✅ 无 description 为空的 Entity（影响检索消歧）
✅ 无 0 实体的 Document（空导入）
✅ 无 name 为空的 Entity
```

### 6.5 文档检查
```
✅ 无重复同名文档
✅ 新文档有 RELATED_TO 关联同类旧文档
✅ 无 deprecated 文档残留
```

### 6.6 同名去重检查
```
✅ 无同名不同id的Entity（同名实体已合并）
✅ 无name为'核查内容'等错误字段名的实体
✅ 无name为null或空字符串的实体
✅ 别名实体已手动合并（如`湖北云技科技`=`湖北云技科技有限公司`）
```

### 6.7 增量检查
```
✅ 飞书文件数 ≈ 图谱Document数（允许有未提取的新文件）
✅ 差异文件有记录原因（黑名单/格式不支持/新建等）
```

### 6.8 状态同步规则
```
✅ 每次启动活跃会话时，运行 python3 pipeline/kg_health_check.py --stats-only 检查节点数是否变化
✅ 节点数比上次多 → 同步更新知识图谱状态
✅ 节点数异常减少 → 立即排查原因（可能数据丢失或误删）
```

### ⚡ 临时人工检查命令（底层排查时使用）

```bash
cd ~/.openclaw/workspace

# SalaryRange外出关系
python3 -c "
from neo4j import GraphDatabase
d=GraphDatabase.driver('bolt://localhost:7687',auth=('neo4j',open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with d.session() as s:
  r=s.run('MATCH (e:Entity {type:\"SalaryRange\"})-[r]->() RETURN count(r)')
  print('SalaryRange外出:',r.single()[0])
"

# 同名不同id实体
python3 -c "
from neo4j import GraphDatabase
d=GraphDatabase.driver('bolt://localhost:7687',auth=('neo4j',open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with d.session() as s:
  r=s.run('MATCH (e:Entity) WITH e.name AS n,count(e) AS c WHERE c>1 RETURN count(n)')
  print('同名不同id组数:',r.single()[0])
"

# 0实体Document
python3 -c "
from neo4j import GraphDatabase
d=GraphDatabase.driver('bolt://localhost:7687',auth=('neo4j',open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with d.session() as s:
  r=s.run('MATCH (d:Document) WHERE (d.deprecated IS NULL OR d.deprecated<>true) AND NOT (d)-[:CONTAINS]->() RETURN count(d)')
  print('0实体文档:',r.single()[0])
"

# 重复Document
python3 -c "
from neo4j import GraphDatabase
d=GraphDatabase.driver('bolt://localhost:7687',auth=('neo4j',open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with d.session() as s:
  r=s.run('MATCH (d:Document) WHERE d.deprecated IS NULL OR d.deprecated<>true WITH d.name AS n,collect(d) AS docs WHERE size(docs)>1 RETURN n')
  for row in r: print('重复文档:',row[0])
"
```

---

## 7. 踩坑编年史

### 2026-05-26: 企业信息抽取 + GPT-5.5模型规则
- **漏读手册导致模型选错**：hybrid_extract.py 最初用 DeepSeek Flash 而非手册规定的 GPT-5.5
  → 根因：写了脚本但没读完 KG_GUIDE §3.5 模型规范
  → 切换后实体质量大幅提升（143→259 实体，Skill 0→31）
  → 教训：写知识图谱相关脚本前必须按 KG_GUIDE.md 全量翻阅
- **ListLevel 与 AircraftType 混淆**：GPT-5.5 将"动力升空器"同时标为 LicenseLevel 和 AircraftType
  → 动力升空器是机型不是执照等级，合并为 AircraftType
  → 修复：审计发现→手动合并
- **全称vs简称别名未合并**："垂起教员考证班"≠"垂直起降固定翼教员考证班"→同一课程两个节点
  → 修复：保留全称节点，搬运关系，删除简称节点，设 aliases 属性
  → 对应规则 §3.2.2 同名别名合并规则已存在但 prompt 引导不足
- **新增实体类型导致白名单不同步**：AircraftType、LicenseLevel、WeightClass 在脚本中启用但手册未更新
  → 修复：手册 §3.3 白名单 19→22类，关系类型 +HAS_CLASS/+HAS_LEVEL
- **审计包 LIMIT 截断误判**：审计包每文档限30实体，培训资料65实体→后35个被截→Claude 看到的是不完整快照
  → 教训：审计包不设 LIMIT 上限，确保全量实体在审计范围内
- **价格表该直接导入而非 LLM 抽取**：结构化表格（课程名/价格/时长/内容）用Python解析导入比LLM抽更准确
  → 教训：已知schema的结构化数据直接导入，不走LLM抽取
- **抽取Prompt与手册关系白名单不一致**：hybrid_extract.py用 DESCRIBES/INCLUDES/USES，手册§3.5.3依然写 BELONGS_TO/CONTAINS
  → 修复：§3.5.3 同步更新为新关系白名单

### 2026-05-16: 初始抽取
- **TrainingDay节点膨胀**：把每日培训记录建成独立节点（899个），导致图谱膨胀
- **修复**：改为存 JSON 到学员节点属性，不抽每日明细

### 2026-05-20: Pipeline修复
- **KG验证ID/名称混淆**：post_extract_validation.py用from_id查索引，被跳过所有关系
- **online_extract.py CLI不写库**：命令行入口只验证不调用write_neo4j()
- **关系写入ID不匹配**：实体用"每日岗_1"创建，关系用LLM原始"ent_1"匹配
- **修复**：ID+名称双索引、CLI补写库调用、name_map加入orig_id→actual_id映射

### 2026-05-21: 审计+大规模修复（持续更新中）

**下午补充（15:00完整检查发现）：**
- **同名实体未被MERGE（51个冗余节点）**：LLM抽取生成不同id→写入用id MERGE→name相同但id不同→各自创建独立节点
  → **根因**：pipeline写库逻辑用`MERGE (e:Entity {id:...})` 而不是 `MERGE (e:Entity {name:...})`
  → **规则已定**（5.2章要求按name MERGE），**代码待改**（pipeline写库逻辑和抽取prompt需同步修改）
  → **影响**：深圳×2、武汉×3、无人机飞手×4、智联招聘×3、前程无忧×4等42组
- **37个"核查内容"错误实体**：学生表格抽取时，统计表的"核查内容"字段名被当成实体name写入
  → **修复**：已DETACH DELETE删除 ✅
  → **教训**：抽取prompt需排除表头/字段名等非业务实体
- **公众号文章误导入**：藏在云技资料库内子文件夹（Cj3D...），pipeline递归扫到
  → **修复**：white_list.json加black_list，scan()加黑名单检查
- **DETACH DELETE误删共享实体**：美团/顺丰/京东等12个被删
  → **修复**：删前先查共享，共享只删关系不删节点
- **Location标成Event**：北京/南京/成都等出现两个独立节点
  → **修复**：抽取prompt加类型约束
- **新文档孤立**：无人机岗位招聘日报未关联其他岗位报告
  → **修复**：导入后自动建RELATED_TO
- **同名文档重复**：员工手册×2、薪酬体系×2、入职流程×2
  → **修复**：导入前查重名，合并后标记deprecated
- **扫描漏掉运营组**：没查看运营组/客资信息下的表格文件
  → **修复**：本指南第3章明确规定——必须扫全部5个子文件夹（历史上曾写入MEMORY.md，当前以本指南为唯一准绳）
- **查询方式太糙**：搜Document没搜到就报"未提取"，没查Entity层
  → **修复**：搜Document后用Entity兜底
- **服务器LIMIT截断导致离散**：Entity→Entity总边3809限1500→批量修复时增的BELONGS_TO被字母序排在末尾截断 → 物流/海城市等断开
  → **修复**：ORDER BY type优先BELONGS_TO + LIMIT 2500 + Category补id

### 2026-05-22: GPT 5.5审计 + 规则优化（v2.0）

**上午发现（全量提取运营组后审计）：**
- **SalaryItem外出关系123条**：SalaryItem被LLM抽出MANAGES/CONTAINS/BELONGS_TO等违规外出关系
  → **修复**：prompt加约束（prompt + cleanup_relations.py双保险 ✅）
- **SalaryRange外出关系18条**：同SalaryItem受害者
  → **修复**：prompt加约束 + 入库后自动清理 ✅
- **LOCATED_IN指向非Location 624条**：LLM乱用LOCATED_IN
  → **修复**：prompt加约束 + 入库后清理 ✅
- **招聘平台被误标Location（6个）**：BOSS直聘/猎聘/拉勾/智联被标成Location
  → **修复**：prompt加反例说明「招聘平台不是Location」 ✅
- **湖北云技科技≠湖北云技科技有限公司 未合并**：别名导致两个实体
  → **规则**：5.2.2新增别名合并规则 ✅
- **双向循环关系1070条**：A BELONGS_TO B + B REFERENCES A 形成环
  → **修复**：清理脚本已删 ✅；后续prompt约束关系方向
- **自引用边20条**：不同实体因ID重复自指
  → **修复**：已清理 ✅；后续脚本生成唯一ID
- **运营数据被误抽**：播放量统计/工作记录本身没有实体关系，不适合KG
  → **规则**：4.5新增文件类型预判规则 ✅；运营数据改存CSV
- **岗位信息报告误抽风险**：每日岗位信息514条，数据量大且结构化，抽进图谱会造成大量噪音节点
  → **规则**：4.5新增岗位信息→只存CSV，不抽图谱 ✅；加入同步清单每晚22:00自动更新
- **培训方案CONTAINS交叉污染（2026-05-22 重抽修复）**：
  - 问题：LLM输出已存在的实体名（如"基本工资"），MERGE找到旧节点后建CONTAINS边
  - 影响：培训方案文档错误关联了527条制度/运营实体
  - 修复：`extract_one.py` 新增 `_created_by` 字段，仅首次创建的实体建CONTAINS边 ✅
  - 提示词优化：新增培训方案特殊规则，禁止将制度/运营实体关联到培训方案 ✅

**下午发现（GPT-5.5最终审计+二次修复）：**
- **自环关系64条**：实体A→PROVIDES→自己、实体A→CONTAINS→自己等（LLM抽取bug）
  → 修复：`MATCH (n)-[r]->(n) DELETE r`，已清0 ✅
- **source_doc→_created_by不同步致孤**：旧实体source_doc保留但_created_by被重置为NULL
  → 修复：用source_doc恢复_created_by + 重建CONTAINS ✅
  → 规则：§16新增source_doc回收流程
- **运营数据误入库21个孤儿残留**：文档已删（运营数据不该进KG）但实体残留
  → 修复：DETACH DELETE 25个运营数据孤儿 ✅
  → 教训：运营数据文档不要创建Document节点，实体不要在第一次抽取时引入
- **网页API LIMIT截断**：server.py LIMIT 900只加载47%节点，800条边只加载2%
  → 修复：节点900→2000，文档→实体边800→4000 ✅
  → 规则：图谱节点>1000时需同步提升server.py LIMIT
- **不要建虚拟文档**：有source_doc但无对应Document时，不自动创建虚拟文档
  → 用户确认：孤儿保持现状，不建假文档
- **删除前先查实体来源**：运营数据实体删除前确认无其他文档引用 ✅

---

## 8. 已知问题（待修）

| 优先级 | 问题 | 状态 |
|--------|------|:----:|
| 🔴 | 核心实体保护名单未在pipeline中落地 — 防止误删公司/资质/课程 | 📋 待实现 |
| 🟡 | `sync.py` 增量同步一直假装写入 — 已有online_extract.py替代 | 🟡 可跑增量 |
| 🟢 | 岗位报告文件夹有重复文件（05-19×2, 05-20×2） | 📋 待整理 |
| 🟢 | Python Neo4j driver的get()方法有bug → 用index访问 | 🏳️ 已知 |
| 🟢 | 每日结构化数据（播放量/工作记录）→ 未分域导入CSV | 📋 待建自动管线 |

### ✅ 已修复/已过时
| 原问题 | 修复说明 |
|--------|---------|
| 同名实体未MERGE | v1.4已修复 |
| 运营组4个sheet未提取 | 运营数据走CSV，不抽KG |
| 岗位报告05-12~05-15未提取 | 岗位信息走CSV，不抽KG |
| 培训计划docx未提取 | 2026-05-22已入库 |
| 11个题库文件缺file_token | 2026-05-22全部入库（GPT-5.5直抽） |
| 抽取prompt需排除表头 | 已修复（核查内容已删，prompt更新） |

---

## 9. 常用操作速查

### 9.0 每次抽取后·复盘清单（铁律 🔒）

**抽完一个文件后，必须逐条执行，不得跳过：**

```
[ ] Step 1: 查自有实体数（MATCH (d:Document {name:'xxx'})-[:CONTAINS]->(e) RETURN count(e)）
[ ] Step 2: 查实体类型分布（RETURN labels(e)[0], count(*)）
[ ] Step 3: 列出前5个实体名称和类型，核查归类是否合理
[ ] Step 4: 判断：实体类型是否合理？数量是否够？
[ ] --- 参考标准：纯文本每1000字→2-5实体；含表格每1000字→3-8实体；题库每1000字→5-12实体 ---
[ ] --- ⚠️ 如果实体数低于参考标准50%以下 → 必须问用户，不得自行跳过 ---
[ ] Step 5: 👑 Claude Opus 交叉审计（参见 §3.5.2 审计铁律）
[ ] --- 生成审计包：源文前2000字 + MATCH (d)-[:CONTAINS]->(e) 实体列表 + 最近20条关系
[ ] --- ⚠️ 审计包不设 LIMIT 上限，确保所有实体都在审计范围内
[ ] Step 6: 把结果发给用户看（不能自己默默清了就过）
[ ] Step 7: 用户说「继续」→ 才能抽下一个
[ ] Step 8: 用户说「有问题」→ 讨论优化 → 再抽下一个
```

⚠️ **违反本清单 = 违反工作手册铁律，每次复盘后必须等用户确认才能继续。**

### 9.1 抽取后数据清洗清单（2026-05-27 实战新增）

**每份文件抽取入库后，必须执行以下 5 步清洗：**

```
□ Step 1: 删除跨文档污染关系
  → 查询其他文档的实体名列表
  → 对目标文档的每条关系，检查两端实体是否都属于本文档
  → 不属于 → DELETE r
  代码示例：MATCH (n)-[r]->(m) WHERE n.source_doc = $doc
           AND NOT EXISTS { MATCH (m) WHERE m.source_doc = $doc }
           DELETE r

□ Step 2: 删除元实体（文档标题作为实体）
  → MATCH (n) WHERE n.source_doc = $doc AND n.name = $doc
  → DETACH DELETE n
  → 常见案例：概述.docx 抽出了 "概述" 实体 — 这是文档名不是知识点

□ Step 3: 检查并补充缺失的类型标签
  → MATCH (n) WHERE n.source_doc = $doc RETURN n.type, count(*)
  → 如果 100% 是 KnowledgePoint → 手动排查：
    - 法规类条款 → SET n.type = 'Regulation'
    - 操作技能类 → SET n.type = 'Skill'
    - 认证/考核类 → SET n.type = 'Certification'

□ Step 4: 检查孤立实体
  → MATCH (n) WHERE NOT EXISTS((n)--()) AND n.source_doc = $doc
  → 孤立实体可能是：① 有价值的但被遗漏了关系 ② 应该删除的
  → 判断后决定补关系或删除

□ Step 5: 验证跨模块关联是否合理
  → 随机抽查 5-10 条关系
  → 检查有没有 "空域分类 -[INCLUDES]-> 电子调速器" 这种明显跨域的
  → 有 → DELETE r
```

**这 5 步是本轮实战的核心经验，不执行就等着被 Claude/Doubao 审计打回。**

### 9.2 业务问答审计清单（2026-05-28 踩坑后新增）

**在回答任何业务问题（法规/制度/培训/学员/流程/就业等）前，检查以下步骤是否完成：**

```
□ Step 1: 统一入口查询（kg_query.py → /api/ask）
  → 结构化问题会自动返回 route=csa；知识类问题返回普通 RAG 结果
□ Step 2: 数据交叉验证（按需选择验证方式）
  → 操作/知识点类（RAG覆盖充分：非degraded，≥3个source-backed命中；或2个高度精确且来源对应的命中）→ 用教材/原文做二次校验即可
  → 法规/制度/流程/条款类 → Neo4j查对应KnowledgePoint做对比
  → 结构化数据问题优先采用 /api/ask 的 CSA 结果；必要时用 `csv_query.py --ids` 核对 canonical 主键覆盖
  → CSA 来源判断：原始 CSV 是事实源，`data/canonical/` 是治理层，`rag_index/csa_cache.sqlite` 只是缓存层
  → 一致 → 输出
  → 不一致 → 标记冲突，优先输出更准确的版本
  → 不确定 → 回复"可能有偏差，建议核实"
□ Step 3: 法规类条款 → 额外校验
  → RAG 结果涉及法规条款时，须与条例原文（教材/官方文档）做二次比对
  → 知识库知识点有误 → 立即修正 KnowledgePoint
□ Step 4: 有结构化数据可用？
  → 学员/教员/价格/岗位等确认 /api/ask 是否 route=csa，不凭印象推断
□ Step 5: 整合回答
  → 按三级回答标准（A级有数据/B级专业推断/C级不确定）标注
  → 融合RAG+图谱+CSV结果，不标注来源标签
```

> ⚠️ 这步来自 2026-05-28 实战踩坑：小技回答"中型无人机空域"问题时，① 未做交叉验证直接拿RAG结果当答案 ② 凭印象说"学员大多考小型" ③ 回答前没走完 AGENTS.md 流程。老文指正后已修正3个KnowledgePoint，新增本清单防重犯。

### 9.3 导入、路由和结构化数据治理清单（2026-06-05 新增）

**适用场景：新增/重导文档、迁移 chunks、修改 `rag_store/route_policy.py`、修改 `rag_store/csa_router.py`、刷新结构化 CSV、修复 Neo4j 文档来源。**

```
□ Step 1: 先确认权威源
  → 结构化业务事实：/Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据
  → chunk 正文：rag_chunks.db 的 chunk_id -> text
  → canonical 实体治理层：/Users/xiaoji/Documents/知识库分析/data/canonical/
  → 派生层：BM25、dense、Neo4j、CSA SQLite cache

□ Step 2: 刷新/验证 canonical 结构化层
  → cd /Users/xiaoji/Documents/知识库分析
  → python3 scripts/build_canonical_entities.py
  → python3 scripts/validate_canonical_entities.py
  → reports/canonical_validation.json 必须 ok=true
  → 不允许把 CSV 行号、文档名、图谱节点 id 当长期主键

□ Step 3: 做跨层 ingest 盘点
  → cd /Users/xiaoji/.openclaw/workspace/projects/knowledge-graph
  → python3 scripts/build_ingest_manifest.py
  → 检查 coverage_summary、BM25/dense freshness、graph source_doc coverage
  → source_doc 覆盖必须通过 rag_store/source_doc_aliases.json 解析；不要只做字符串等值

□ Step 4: 检查 SQLite/BM25/dense 新鲜度
  → python3 scripts/check_index_freshness.py
  → 以 SQLite fingerprint 为准：chunk_count、doc_count、text_bytes、max_created_at、schema、sha256
  → BM25 indexed_docs、dense indexed_count、dense embeddings 行数都要对齐

□ Step 5: 路由/检索改动后跑自动门禁
  → 知识库分域同步完整门禁：make domain-sync-gate
    串联 build_ingest_manifest、check_sync_readiness、build_domain_sync_package、
    replay_domain_sync_package、隔离 Neo4j 导入验证、60 条分域 eval
  → 分域 eval 每域 20 条（法规、题库、教材共 60 条），除召回外还检查
    top chunk/doc 是否符合 fixture 期望、top 文本是否含关键证据、所有最终 source 是否来自 replay SQLite
  → 分域包是 v2 增量包：按 domain/doc/chunk fingerprint 判断 added/modified/deleted，
    写入 changed_chunks.jsonl、deleted_chunks.jsonl、tombstones.jsonl；
    远端 replay 先校验 base fingerprint 后应用增量，失败则自动全量重建该 domain
  → 快速抽样 dense 复验：make domain-sync-gate-fast
  → 单域复验示例：make domain-sync-gate DOMAINS="regulation"
  → python3 scripts/eval_route_policy.py
  → python3 scripts/eval_health_gate.py
  → 若只改 CSA，可额外跑 python3 scripts/eval_csa.py
  → 若改 RAG/KG 检索，可额外跑 python3 scripts/eval_smoke.py --questions eval/quality_questions.json

□ Step 5.5: 业务图谱同步/多跳桥接门禁
  → 涉及 canonical 结构化表、业务实体同步、Neo4j 类型治理、关系证据治理后必须跑：
    make business-graph-governance-check
  → 完整业务图谱同步门禁：
    make business-graph-gate
  → 完整门禁顺序：
    1. /Users/xiaoji/Documents/知识库分析/scripts/build_canonical_entities.py 重建 canonical 表
    2. /Users/xiaoji/Documents/知识库分析/scripts/validate_canonical_entities.py 校验 canonical 表
    3. scripts/sync_business_entities_to_neo4j.py 同步业务实体和关系
    4. scripts/govern_type_conflicts.py --confirm 治理同名跨类型冲突
    5. scripts/govern_job_company_duplicates.py --confirm 合并 jobs.csv Company 重复节点
    6. scripts/graph_coverage_report.py 输出覆盖报告
    7. scripts/eval_multihop_business_graph.py 验证经营多跳路径
    8. scripts/govern_multihop_bridges.py dry-run 确认无待补桥/待回填
    9. scripts/govern_type_conflicts.py dry-run 确认同名跨类型冲突为 0
    10. scripts/govern_job_company_duplicates.py dry-run 确认重复 Company 为 0
    11. scripts/check_business_graph_governance.py 汇总 gate
    12. scripts/eval_route_policy.py 确认路由策略未回归
  → 门禁口径：
    1. scripts/eval_multihop_business_graph.py 必须 failed=0 且 total_failed_paths=0
    2. scripts/govern_multihop_bridges.py dry-run 必须没有待规范化 node chunk、待补桥、待回填审计字段
    3. scripts/govern_type_conflicts.py dry-run 必须 before_conflict_groups=0 且 after_conflict_groups=0
    4. scripts/govern_job_company_duplicates.py dry-run 必须 planned_duplicates=0
    5. 业务入口 Skill 必须通过独立的 “知识点证据” KnowledgePoint 连接到 SQLite chunk 证据
  → 不允许用同名 Skill/KnowledgePoint 合并来凑路径；Skill 显示名应使用 “能力” 消歧，KP 证据节点使用 “知识点证据” 消歧
  → jobs.csv Company 消歧规则：
    - 普通公司名：entity_id = stable_id("company", company_name)，按公司名稳定合并
    - 只有 company_name 与岗位标题集合相撞时，才使用 company_unknown + 岗位 entity_id 消歧
    - 若 Company 数异常膨胀，先跑 scripts/govern_job_company_duplicates.py dry-run，再 confirm
  → 2026-06-06 当前验收基线：
    - business full gate：nodes_created=0，nodes_updated=3830，relationships_created=0，relationships_updated=9148，missing_evidence_total=0
    - type conflict：confirm 前 2 组，confirm 后 0；后续 dry-run before=0 / after=0
    - jobs.csv Company duplicate：confirm 合并 467 个 Company、迁移 467 条关系；后续 dry-run planned_duplicates=0
    - multihop eval：25/25，failed_paths=0；bridge counts 为 Course 74 / Student 189 / Position 1483 / Instructor 18
    - Neo4j 健康：5749 节点、392660 关系、76 文档、5673 实体；Company 295，其中 jobs.csv Company 293

□ Step 5.6: 历史关系证据治理（独立于业务图谱 gate）
  → 业务图谱 gate 绿色只说明本轮业务同步、多跳桥接和防回归通过；不代表全图历史关系均有完整证据。
  → 重点关系类型：
    REQUIRES / REGULATES / REFERS_TO / HAS_PROPERTY / REQUIRES_SKILL / HAS_CLASS
  → 只读盘点：
    python3 scripts/govern_graph_evidence.py
  → 申请变更后再执行：
    python3 scripts/govern_graph_evidence.py --confirm
  → 2026-06-06 dry-run 基线：
    - Position tier 污染：0（未发现 type/category/entityType/label 为 “管理” 或 “基层” 的待归一化节点）
    - 缺 source_doc/source_chunk_ids 的历史关系仍有存量：REQUIRES 81663、REGULATES 48873、REFERS_TO 28784、HAS_PROPERTY 15816、REQUIRES_SKILL 14511、HAS_CLASS 12691
  → 处理原则：
    - 可以从关系自身、两端节点共享 source_doc、source_doc_aliases、SQLite chunk 回源推断证据
    - 推断不到的关系只标记 unresolved，不得编造 source_doc 或 chunk_id
    - 治理完成后再把该脚本接入正式 gate；接入前不要把它当作 business-graph-gate 的失败项

□ Step 6: 用 trace 做质量复盘
  → 查看 eval/query_traces.jsonl
  → 关注 external_completion、top_sources、latency、degraded_reasons、KG 召回多但答案贡献低的问题
  → 优先修路由边界、source alignment、freshness 和噪声治理；不要在健康架构上盲目重构
```

**关键经验：**
- CSV / SQLite chunk store 是权威层；BM25、dense、Neo4j、CSA cache、manifest 都是派生或治理层。
- `document_id` / `regulation_id` / `question_bank_id` 用于语义实体和元数据，不替代 `chunk_id`。
- 复合问题应保留 `route=hybrid`、`rag_query`、`csa_topic` 等 trace 字段，不能把结构化片段和知识片段混成一个不可审计的问题。
- 对“内部事实依赖”的生成任务（JD、培训方案、SOP、面试题、销售话术等），先走 KG/RAG/CSA，再做表达生成；不要因为输出格式像创作就跳过内部知识库。

### 查询知识图谱（RAG 优先，Neo4j 按需补充）
> 查询前先看 SKILL.md 强制自检清单 — 每次回答业务问题前必须逐条确认。
> 查询规则：操作/知识点类在 RAG 覆盖充分时跳过手动 Neo4j 补充；充分覆盖=非degraded，≥3个source-backed命中，或2个高度精确且来源对应的命中。`≥2` 不单独构成充分覆盖。法规/制度/条款类须查Neo4j做交叉验证。详见 §9.2 业务问答审计清单。

> 📌 `neo4j_query.py` 已存在，可直接调用按需补充图谱实体信息：

```bash

> 📌 `neo4j_query.py` 已存在，可直接调用按需补充图谱实体信息（参见 SKILL.md §3.5 补充规则）：

```bash
cd projects/knowledge-graph
python3 neo4j_query.py "问题"          # 自然语言查询
python3 neo4j_query.py --json "问题"   # JSON 结构化输出
python3 neo4j_query.py --stats         # 实体类型统计
```

也可直接用 Python 连接 Neo4j 查询：

```bash
# 统计（节点/关系数）
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687',
    auth=('neo4j', open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with driver.session() as session:
    r = session.run('MATCH (n) RETURN count(n) as cnt')
    print(f'Nodes: {r.single()[0]}')
    r = session.run('MATCH ()-[r]->() RETURN count(r) as cnt')
    print(f'Rels: {r.single()[0]}')
"

# 查实体
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687',
    auth=('neo4j', open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with driver.session() as session:
    r = session.run('MATCH (n:Entity) WHERE n.name CONTAINS \$kw RETURN n.name, labels(n) LIMIT 20',
        kw='关键词')
    for rec in r:
        print(rec['n.name'], rec['labels(n)'])
"

# 查关系
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687',
    auth=('neo4j', open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with driver.session() as session:
    r = session.run('MATCH (n)-[r]-(m) WHERE n.name CONTAINS \$kw RETURN n.name, type(r), m.name LIMIT 30',
        kw='关键词')
    for rec in r:
        print(f'{rec[\"n.name\"]} -[{rec[\"type(r)\"]}]-> {rec[\"m.name\"]}')
"
```

### 单文件抽取（extract_one.py）

```bash
# 用法：python3 pipeline/extract_one.py <文件路径> <文档名> <分类> [实体类型]
python3 pipeline/extract_one.py 制度.txt "云技科技员工手册" "制度" "Policy,Department,Position"
```

### GPT-5.5 直抽（题库/大文件）

```bash
# 见 §10 GPT-5.5 直抽脚本模板
# 不需要extract_one.py，直接在Shell里跑python脚本
```

### 清理违规关系
```bash
python3 pipeline/cleanup_relations.py
```

### 执行健康检查
```bash
python3 pipeline/kg_health_check.py
python3 pipeline/kg_health_check.py --stats-only
python3 pipeline/kg_health_check.py --full
```

### 每日备份
```bash
bash pipeline/backup.sh
```
定时：每天02:30自动执行（cron）。
备份存储目录：`/Users/xiaoji/Downloads/同步空间/openclaw/kg_backups/`

### 灾难恢复

备份文件是Neo4j原生数据目录（raw store files），不可直接覆盖到运行中的容器。标准恢复流程：

```bash
# 1. 停容器
docker stop yunji-knowledge-graph

# 2. 用neo4j-admin从备份创建dump
#    先启动一个临时容器提取数据
BACKUP_FILE="/path/to/kg_backup_YYYYMMDD_HHMM.tar.gz"
DATA_DIR="/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j-docker/data"
TMP_DIR=$(mktemp -d)
tar xzf "$BACKUP_FILE" -C "$TMP_DIR"
# 把备份store文件放到databases目录
rm -rf "$DATA_DIR/databases/neo4j"
cp -r "$TMP_DIR/neo4j" "$DATA_DIR/databases/neo4j"
# 运行neo4j-admin dump
docker run --rm \
  -v "$DATA_DIR/databases:/data/databases" \
  --entrypoint neo4j-admin \
  neo4j:latest database dump neo4j --to-path=/data/databases/
# 清理store文件
rm -rf "$DATA_DIR/databases/neo4j"

# 3. 启动干净的Neo4j（会自动创建system库）
docker start yunji-knowledge-graph
# 等待healthy...

# 4. 加载dump
# 先停容器
docker stop yunji-knowledge-graph
# 清空system库和事务日志
rm -rf "$DATA_DIR/databases/system"
rm -rf "$DATA_DIR/transactions/neo4j" "$DATA_DIR/transactions/system"
mkdir -p "$DATA_DIR/transactions/neo4j" "$DATA_DIR/transactions/system"
# load dump
docker run --rm \
  -v "$DATA_DIR/databases:/data/databases" \
  -v "$DATA_DIR/transactions:/data/transactions" \
  --entrypoint neo4j-admin \
  neo4j:latest database load neo4j --from-path=/data/databases/ --overwrite-destination=true
# 清理dump文件
rm -f "$DATA_DIR/databases/neo4j.dump"

# 5. 启动容器
docker start yunji-knowledge-graph

# 6. 验证
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with driver.session() as session:
    r = session.run('MATCH (n) RETURN count(n)')
    print(f'Nodes: {r.single()[0]}')
"
```

> ⚠️ **踩坑记录**：直接复制raw store文件到容器的`databases/`目录会导致`Mismatching store id`错误（system库与数据库StoreID不匹配），以及`Transaction logs are missing`错误。标准流程必须走 `dump → load`。
>
> 如果只是缺失事务日志（`Transaction logs are missing and recovery is not possible`），可在`neo4j.conf`中临时添加`db.recovery.fail_on_missing_files=false`来强制启动（⚠️ 启动成功后应立即移除该配置）。

### Neo4j直接查询
```bash
# 用exec直接跑Cypher
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', 
    auth=('neo4j', open('projects/knowledge-graph/neo4j/.neo4j_pass').read().strip()))
with driver.session() as session:
    result = session.run('MATCH (n) RETURN count(n)')
    print(result.single()[0])
"
```

---

### 版本变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-05-21 | 初版创建，汇总全部踩坑+规则 |
| v1.1 | 2026-05-21 | 补充同名实体去重、核心实体保护名单、导入顺序铁律 |
| v1.2 | 2026-05-21 | Pro审计后修复：类型修正(Client→Company等)、Docker运维、灾难恢复、可视化面板、三级分层附录、状态同步 |
| v1.3 | 2026-05-21 | GPT 5.5审计后修复：20类计数修正、附录目录、醒目标注、人工检查命令、版本历史表 |
| v1.4 | 2026-05-21 | 新增5.5 LLM调用逻辑：降级链、参数表、Prompt策略、FOLDER_TYPE_MAP、JSON解析、写入逻辑 |
| v1.6 | 2026-05-21 | 五分类骨架 + BELONGS_TO自动归属 + Category必须设id + server.py LIMIT优化 |
| v1.8 | 2026-05-21 22:49 | 导入分类铁律 + 3D网页管理功能（左侧列表hover删除节点） |
| **v2.0** | **2026-05-22 09:00** | **GPT 5.5审计+全面规则优化：关系禁区、文件类型预判、运营数据CSV分流、cleanup_relations自动清理、alias合并规则** |
| **v2.1** | **2026-05-22 11:23** | **培训方案重抽+CONTAINS污染修复：_created_by防交叉污染、prompt培训特殊规则、结构化数据清洗+数据字典+分析规则** |

---

### 附录A：业务问答引用KG数据规范（三级分层）

回答学员/客户/岗位/价格等业务问题时，默认先走统一 `/api/ask`；结构化数据由 CSA 返回，CSA 优先使用 canonical 实体表和 SQLite cache，但事实权威仍是原始 CSV，图谱只作为知识类补充。引用规范分三级判断：

| 层级 | 条件 | 规则 | 示例 |
|:---:|------|------|------|
| **A级** | /api/ask 有明确来源（CSV或知识库） | 直接引用业务结论，不机械写"据RAG/CSV/KG" | 「沙浩当前有24名学员」 |
| **B级** | 知识库无精确数据，但可专业推断 | 用限定语自然表达 | 「从行业趋势来看，无人机测绘需求在上升」 |
| **C级** | 没有可靠依据 | 老实说没有准确数据 | 「这部分我没有准确数据，建议你核实一下」 |

各场景具体规则：

| 场景 | 规则 |
|------|------|
| 就业薪资 | 先查 /api/ask；有岗位CSV或知识库来源→直接引用；无数据→C级 |
| 公司介绍/制度 | 先查 /api/ask；必要时用原文或Neo4j交叉验证 |
| 培训/学员/教员 | 先查 /api/ask 的 CSA 结果；必要时用 `csv_query.py --ids` 核对 canonical 主键 |
| 招聘岗位 | 先查 /api/ask 的 CSA 岗位结果；区分 `job_id` 实体和 `job_occurrence_id` 出现记录，不要从Neo4j岗位旧节点推断实时数据 |
| 其他开放域 | 先查 /api/ask→不够→联网补充→B级表达 |

### 附录B：Model使用规范

| 用途 | 模型 |
|------|------|
| 日常统一问答 | /api/ask：CSA 或 bge-m3 Dense + BM25 + Neo4j KG + DeepSeek Flash |
| KG深度审计/复杂分析 | DeepSeek Pro（手动切换） |
| LLM单文件抽取 | GPT-5.5（主抽取，中转站）→ 失败问老文 → Doubao（降级） |
| 审计/验证/兜底 | GPT 5.5（审计/验证专用，需显式指定模型） |
| LLM抽取降级链 | GPT-5.5（主）→老文确认→Doubao（降级） |
| 题库大文件(>8000字)抽取 | GPT-5.5；15k+ 文件必须明确分段/覆盖策略，失败 → 问老文 → Doubao |
| 知识图谱最终审计 | GPT-5.5（用诊断数据喂入，出审计报告） |

## 10. 抽取方法选择：extract_one vs GPT-5.5 直抽

### 10.1 决策树

```
所有文件 → GPT-5.5 主抽取（中转站）
    ↓ 成功 → 写入Neo4j → 复盘
    ↓ 失败 → 重试3次（180s超时）
        ↓ 仍失败 → 停下来问老文
            ↓ 老文确认 → Doubao降级
            ↓ 老文否定 → 跳过此文件
```

**模型不按文件大小自动降级，默认仍用 GPT-5.5。** 但抽取策略必须按文件大小处理：15k+ 文件要明确分段或覆盖上限，50k+ 文件必须分段；不得只截取前段后宣称全文已抽取。

### 10.2 GPT-5.5 直抽脚本模板

```python
import json, time, requests
from neo4j import GraphDatabase

cfg = json.load(open("pipeline/config.json"))
px = cfg["models"]["full"]["proxies"]  # 双中转站

text = open("文件.txt").read()
prompt = f"""提取知识点...{text}"""

for p in px:  # 先rehdasu→再t8star
    try:
        r = requests.post(f"{p['base_url']}/chat/completions",
            json={"model":"gpt-5.5","messages":[...],"max_tokens":8192}, timeout=300)
        result = json.loads(r.json()["choices"][0]["message"]["content"])
        break
    except: continue

# 写入Neo4j（同extract_one.py逻辑）
```

### 10.3 注意事项

- ⚠️ GPT-5.5 超长文本(>80000字)可能token截断，需截取前80000字
- ⚠️ 关系格式可能和extract_one不一致，需要容错处理（from_id/from, to_id/to）
- ✅ GPT-5.5 零交叉污染比例远高于DeepSeek
- ✅ 题库类文件用GPT-5.5，速度快+质量高

## 11. 质量审计框架

### 11.1 每次抽取后·轻量审计

见 §9 复盘清单（7步）

### 11.2 阶段性·深度审计（用GPT-5.5）

每完成一个文件夹或一批文档，运行一次深度审计：

**步骤：**
1. 采集诊断数据（10项指标）
2. 喂给GPT-5.5
3. 产出审计报告
4. 按P0→P1→P2优先级修复

**10项诊断指标：**
```
1. 节点/关系/文档总数
2. 实体类型分布
3. 交叉污染（e._created_by ≠ d.name）
4. 孤儿实体（无Document连接）
5. 关系类型分布
6. 违规关系（制度→培训文档）
7. 重复实体名
8. 自环关系
9. 无描述实体
10. 各文档 own/cross 统计

### 11.3 审计节奏（2026-05-27 5轮实战经验）

**分阶段审计策略：**

| 阶段 | 审计范围 | 审计内容 | 审计模型 |
|------|---------|---------|---------|
| 单文件 | 抽完一份立刻审 | 类型分布、产品型号、粒度、关系方向 | Doubao/Claude |
| 三文件 | 每3份做一次 | 重复实体、跨文件关联 | Doubao |
| 全量 | 全部抽完后 | 评分、缺失关系、跨模块精度 | Doubao |

**多次审计的价值**（2026-05-27 经验）：
- 第一次审计 → 发现 model 粒度过细、BELONGS_TO 滥用
- 第二次审计 → 发现 REFERS_TO/INCLUDES 语义模糊
- 第三次审计 → 确认错误关系已清除
- 第四次审计 → 发现跨模块关联缺失
- 第五次审计 → 终审 8/10，确认可用

⚠️ t8star Claude 间歇 401/500 → 用 Doubao 替代审计，稳定、详细、可控
⚠️ 每次审计修完后，跑一次全量统计，确认节点和关系数没有意外变化

```

### 11.4 全量实体内容审计（2026-05-28 新增）

> 与 §11.2 的「抽取质量审计」不同，全量内容审计检查的是已有实体描述的正确性、完整性和分类合理性，而非抽取过程的实体类型/关系质量。

**审计目的：** 发现并修复实体描述中的事实错误、过简描述、分类错误和矛盾信息，提升 RAG 回答的事实准确性。

#### 审计流程

**准备阶段：**
1. 导出所有实体（过滤无 embedding 的非知识类节点）：
   ```cypher
   MATCH (n)
   WHERE n.source_doc IS NOT NULL
   AND any(label IN labels(n) WHERE label IN ['Entity','KnowledgePoint','Course','Regulation','Policy','Skill'])
   RETURN n.name, n.type, n.description, n.source_doc, n.category
   ```
2. 分批处理：每批 25 个实体，避免 API 超时
3. 增量保存审计结果（JSONL），支持断点续审

**审计模型选择：**
> 与 §11.2/§3.5.2 的区别：§11.2 的「深度审计」检查的是抽取质量（实体类型、关系粒度是否正确），用 Claude Opus；§11.4 的「全量内容审计」检查的是已有实体的**描述事实正确性**，用 Doubao。二者用途不同，互补不冲突。

**审计模型选择：**
- 使用 **Doubao Seed 2.0 Pro** 作为独立审计模型（2026-05-28 经验）
- 不与被审计的 RAG 生成模型（DeepSeek Flash）同源，避免偏见
- Doubao 稳定、无限频问题，适合大批量审计（实测868实体35批无中断）

**审计提示词：**

参考 §9.0 单文件抽取审计提示词。仅需将审计目标从「抽取实体质量检查」改为「已有实体描述的正确性、完整性和分类合理性检查」，并添加以下审计维度（原提示词的结构化/非结构化条款同样适用于本场景）：


#### 问题分类体系

| 问题类型 | 严重等级 | 影响 | 修复优先级 |
|---------|:-------:|:----:|:---------:|
| **事实错误** | 🔴 高 | 直接导致 RAG 输出错误答案 | P0（必须先修） |
| **描述过简** | 🟡 中 | RAG 回答空洞、信息量不足 | P1 |
| **分类错误** | 🟡 中 | 实体混入不相关领域，影响检索排序 | P1 |
| **矛盾** | 🟠 中 | 同一概念多标准但未说明适用场景 | P1 |
| **其他** | 🟢 低 | 实体名拼写错误、描述为空、source_doc缺失、格式不一致等 | P2 |

#### 审计实战数据（2026-05-28 全量审计）

| 指标 | 数值 |
|------|:----:|
| 审计实体总数 | 868 个 |
| 发现问题总数 | 168 个 |
| 问题发现率 | 19.4% |
| 高优先级（事实错误） | 62 个 |
| 描述过简 | 54 个 |
| 分类错误 | 38 个 |
| 矛盾 | 8 个 |
| 其他 | 6 个 |
| 审计模型 | Doubao Seed 2.0 Pro |
| 审计耗时 | 约 15 分钟（35 批） |

#### 修复流程

**修复顺序（用户 2026-05-28 确认）：**
1. **P0 事实错误**优先修复 → 直接更新 Neo4j 节点 description 字段
2. 再修 **描述过简** → 补充实质内容
3. 再修 **分类错误** → 补充领域上下文（不直接删除，保留并挂靠无人机场景）
4. 最后修 **矛盾** → 说明多标准适用场景

**修复方式：**
```cypher
MATCH (n {name: '实体名称'})
SET n.description = '修正后的准确描述'
```
> 当前双 RAG 的最终正文上下文来自 SQLite chunk store；Neo4j 实体 description 主要用于图谱证据、实体向量检索和关系扩展。直接更新 Neo4j description 会立即影响图谱证据，但不等于更新正文 chunk；若修复的是文档正文事实，应同步更新源文/SQLite chunk，并按需重建 Dense/BM25 索引。

**验证：** 修复后用 Cypher 抽查关键实体，确认描述已更新且内容正确。

#### 踩坑记录

- **全量导出注意过滤：** 非知识类节点（_created_by 特殊节点等）应排除在外；当前可按 `source_doc IS NOT NULL`、实体类型和业务标签过滤，不要仅依赖 `embedding IS NOT NULL`
- **分批处理避免超时：** 25 个/批是安全值，50 个/批可能导致 API 超时（特别是 Doubao 长上下文场景）
- **矛盾处理原则：** 不要二选一简化，应保留两套标准并说明各自的适用场景（如中空飞行高度：空管标准和行业标准并存）
- **分类错误的处理：** 不要删除跨领域实体，应补充无人机上下文使其在知识库中有意义（如「生物防治法」改为「无人机植保作业中的生物防治」）
- **批量修复脚本注意：** 使用参数化查询避免引号冲突。写复杂脚本时用 heredoc `<< 'PYEOF'` 单引号 heredoc 避免 shell 展开

### 11.5 持续监控阈值

| 指标 | 告警阈值 |
|------|:--------:|
| 孤儿实体比例 | > 5% |
| 交叉污染边 | > max(50, 文档数的5%) |
| 无描述实体 | > 0 个 |
| 单文档 CONTAINS 异常增长 | 环比 > 50% |

## 12. 交叉污染治理流程

### 12.1 检测

```cypher
MATCH (d:Document)-[c:CONTAINS]->(e:Entity)
WHERE e._created_by IS NOT NULL AND e._created_by <> d.name
RETURN d.name, count(c) AS cross
ORDER BY cross DESC
```

### 12.2 清理（保留自有）

```cypher
MATCH (d:Document {name:$doc})-[c:CONTAINS]->(e)
WHERE e._created_by IS NULL OR e._created_by <> $doc
DELETE c
```

### 12.3 治理优先级

1. 培训计划类文档（易交叉污染课程/考试/证书）
2. 价格表（易交叉污染课程/产品）
3. 个性化方案（易交叉污染学员/课程）

## 13. 孤儿实体治理流程

### 13.1 检测

```cypher
MATCH (e:Entity)
WHERE NOT (e)<-[:CONTAINS]-(:Document)
RETURN e.type, count(e)
ORDER BY count(e) DESC
```

### 13.2 处理方案

```
1. 可追溯来源 → 补充 Document 关系
2. 属于主数据 → 挂接到"主数据目录"文档
3. 无法确认来源 → 标记 status='deprecated'，隔离不参与问答
```

### 13.3 治理优先级

Course > Product > Certification > Exam > TrainingPlan > Organization

## 14. CONTAINS vs REFERENCES 语义规范（2026-05-22 新增）

> 📌 此规范来自GPT-5.5最终审计建议，解决交叉污染根因

| 关系 | 语义 | 何时使用 |
|------|------|---------|
| **CONTAINS** | 该实体由本文档产生或明确承载 | 实体首次出现在本文档中 |
| **REFERENCES** | 本文档提及/引用了已有实体 | 实体由其他文档创建，本文档只是提到 |

**规则：**
- ❌ 禁止多文档共同 CONTAINS 同一实体
- ✅ 跨文档引用统一用 REFERENCES
- ⚠️ 培训计划引用课程/考试/证书 → 用新关系(PREPARES_FOR / LEADS_TO)，不用CONTAINS

## 15. 文档域分类（2026-05-22 新增）

> 📌 此分类来自GPT-5.5审计建议，用于防止业务边界混淆

| 域 | 文档类型 | 典型实体类型 | 可见范围 |
|----|---------|------------|:--------:|
| 题库知识域 | 理论题库 | KnowledgePoint | 全员 |
| 培训课程域 | 培训方案/计划 | Course,Exam,Cert | 学员+内部 |
| 公司产品域 | 公司介绍/产品介绍 | Product,Service | 全员 |
| 人事制度域 | 员工手册/薪酬体系 | Policy,SalaryItem | 仅内部 |
| 客户管理域 | 客资表/跟进制度 | Person,Task,Policy | 仅内部 |

**铁律：制度类(Policy/SalaryItem)连到培训文档 = 违规，每次抽取后自动检测。**

## 16. 重抽后孤儿治理：source_doc 回收流程（2026-05-22 新增）

> 文档被删除后重新抽取时，旧实体变成孤儿（`_created_by=NULL` 但 `source_doc` 保留）。

### 16.1 检测

```cypher
-- 检测 orphan：有source_doc但无CONTAINS的实体
MATCH (e:Entity)
WHERE e.source_doc IS NOT NULL
AND NOT (e)<-[:CONTAINS]-(:Document {name:e.source_doc})
RETURN e.source_doc AS src, count(e) AS cnt
ORDER BY cnt DESC
```

### 16.2 回收

```cypher
-- 把旧实体挂回对应文档
MATCH (e:Entity)
WHERE e.source_doc = '文档名称'
AND (e._created_by IS NULL OR e._created_by <> '文档名称')
SET e._created_by = '文档名称'
WITH e
MATCH (d:Document {name:'文档名称'})
MERGE (d)-[:CONTAINS]->(e)
```

### 16.3 原理

```
第一次抽取 → ON CREATE 写死 source_doc='文档A'
删文档重抽 → _created_by 被重置为 NULL
           但 source_doc 永远不变（ON SELECT不更新它）
回收 → 用 source_doc 恢复 _created_by + 重建 CONTAINS
```

### 16.4 注意事项

- ⚠️ `source_doc` 仅在 ON CREATE 时写入，ON MATCH/SELECT 不更新
- ⚠️ 只适合回收同一文档的旧实体，不要用于跨文档收回
- ✅ 回收后需要跑一次清交叉（§12），防止旧实体被错误挂到其他文档

---

## 17. 知识盲区覆盖管理（2026-05-28 新增）

> 全量内容审计后，发现部分核心领域完全没有被知识库覆盖。本章定义盲区分析方法和补充流程。

### 17.1 盲区来源与检视方法

**盲区来源：** 全量内容审计后，独立审计模型（Doubao Seed 2.0 Pro）基于现有实体分布推断缺失的知识领域。

**检视方法：**
1. 统计现有实体按来源文档和领域分类的分布
2. 对比 CAAC 考试大纲要求的完整知识点体系
3. 标注缺失的核心模块
4. 按重要性和影响面排序

### 17.2 盲区分类与优先级

| 优先级 | 类别 | 典型缺失内容 | 影响 |
|:-----:|------|-------------|:----:|
| 🔴 高 | 法规类 | CCAR-91部、低空域使用规则、禁飞区解禁流程、执照等级签注 | 考试必考、飞行合规操作必备 |
| 🔴 高 | 操作类 | 起飞前全系统检查、信号失联应急处置、超视距操作规范 | 飞行安全核心内容 |
| 🔴 高 | 飞行原理类 | 多旋翼升力原理、固定翼失速改出 | 考试必考、理解操作逻辑的基础 |
| 🔴 高 | 气象类 | 风切变危害与处置、能见度/云高限制 | 航空气象考试必考、安全决策依据 |
| 🔴 高 | 培训/考试类 | CAAC理论考试大纲、实操评分标准 | 学员备考核心依据 |
| 🔴 高 | 硬件系统类 | 动力系统匹配计算、避障系统原理 | 选型与故障排查必备 |
| 🔴 高 | 行业应用类 | 测绘正射影像规范、电力巡检安全距离 | 行业作业合规必备 |
| 🟡 中 | 法规类 | 违规飞行处罚标准 | 合规认知 |
| 🟡 中 | 飞行原理类 | PID控制原理、续航估算 | 考试参考 |
| 🟡 中 | 气象类 | 气温对电池影响、强对流天气限制 | 实操参考 |
| 🟡 中 | 其他 | 图传干扰优化、植保漂移控制 | 特定场景需求 |

### 17.3 实体生成与入库流程

**准备阶段：**
1. 确定盲区清单：通过 `gap_scan.py` 或人工对比 CAAC 大纲 → 现有实体分布得出
2. 整理知识点描述：参考 CAAC 官方规范、民航法规原文、行业通用教材（如《无人机飞行原理》《航空气象学》），描述必须准确
   - 法规类知识点优先引用法规原文条款号
   - 操作类知识点覆盖标准流程 + 安全注意事项
   - 考试类知识点应与 CAAC 考试大纲一致

**实体构造规范：**
```python
# 每个盲区知识点生成一个 KnowledgePoint 节点，字段如下：
{
    "name": "知识点标准名称",           # 例："CCAR-91部民用航空运行一般规则无人机相关条款"
    "type": "KnowledgePoint",           # 固定值
    "category": "法规类|飞行原理类|气象类|操作类|培训/考试类|硬件/系统类|行业应用类",
    "importance": "高|中",             # 高=考试必考/作业必备，中=参考知识
    "description": "完整描述文本，200~500字为宜，含定义、原理、操作细节、注意事项",
    "source_doc": "来源文档标识",        # 如 "CAAC法规" / "飞行原理教材" / "行业标准"
    "source": "来源文档名或标准号"        # 如 "CCAR-91部" / "民用航空低空空域管理规定"
}
```

**入库方式：**
- 推荐：使用 Python neo4j 驱动批量写入（CREATE 语句），支持一次写入多个节点
- 也可：用 Cypher 逐条写入（手动操作不推荐，容易丢字段或引号冲突）
- 不推荐：用 LLM 抽取方式创建盲区节点（抽取得太慢，且可能抽偏）

**批量写入示例（Python）：**
```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', password))
with driver.session() as session:
    for gap in gap_list:
        session.run('CREATE (n:KnowledgePoint {id: $id, name: $name, type: $type, '
                     'category: $cat, description: $desc, source_doc: $src})',
                     id=str(uuid.uuid4()), name=gap['name'], type='KnowledgePoint',
                     cat=gap['category'], desc=gap['description'], src=gap['source_doc'])
driver.close()
```

**验证步骤：**
1. 数量验证：`MATCH (n:KnowledgePoint) RETURN count(*)` 确认节点数新增正确
2. 内容验证：`MATCH (n {name: "知识点名"}) RETURN n.description` 确认描述准确
3. 搜索验证：重启 RAG 服务后，用 `kg ask "相关关键词"` 确认新知识点能被检索到

**踩坑记录：**
- 字段名 `source` 和 `source_doc` 不要混淆：前者存标准号/法规名，后者存文档标识
- 批量写入时注意引号嵌套问题（用参数化查询 `$var` 避免）
- 补充完成后建议更新版本历史和覆盖度数据

### 17.4 实战数据（2026-05-28）

| 指标 | 数值 |
|------|:----:|
| 发现盲区 | 26 个 |
| 高优先级 | 17 个 |
| 中优先级 | 9 个 |
| 已全部补充 | ✅ 26/26 |
| 新增 KnowledgePoint 节点 | +26 个 |
| 知识库覆盖度提升 | 83% → 96% |
| 补充依据 | CAAC法规/民航标准/行业通用教材 |

---

## 版本历史

> 版本历史只记录当时状态和踩坑背景，不作为当前操作规则。若历史条目与正文规则冲突，以正文最新章节和 OpenClaw `knowledge-graph` / `rag-neo4j-hybrid` skill 为准。

### v2.8 (2026-06-06 12:15)
- 🚨【业务图谱门禁】新增并固化 `make business-graph-gate` / `make business-graph-governance-check`：完整 gate 串联 canonical 表重建校验、业务实体同步、type conflict 治理、jobs.csv Company 去重、多跳 eval、三类 dry-run 和路由 eval
- 🚨【命名消歧契约】业务入口 `Skill` 使用 `xxx（能力）`，证据型 `KnowledgePoint` 使用 `xxx（知识点证据）`；禁止用同名 Skill/KP 合并来凑多跳路径
- 🚨【Company 防膨胀】修正 jobs.csv Company 消歧范围：只有公司名撞岗位标题时才使用 `company_unknown` + 岗位 ID；普通 Company 按公司名稳定合并，并由 `scripts/govern_job_company_duplicates.py` 防回归
- 🟡 【多跳桥接治理】新增 `scripts/govern_multihop_bridges.py`，统一规范旧 `source_chunk_ids`、补业务 Skill 到证据 KP 的 bridge、回填 bridge 审计字段；dry-run 必须无待处理项
- 🟡 【类型冲突治理】新增 `scripts/govern_type_conflicts.py`，处理同名跨类型节点、岗位/概念撞名、伪 Company 等冲突；dry-run 必须 before=0 / after=0
- 🟡 【治理汇总】新增 `scripts/check_business_graph_governance.py`，把 multihop、bridge、type conflict、jobs Company duplicate 四类结果汇总成一个可失败的 gate
- 🟡 【当前验收基线】2026-06-06 business full gate 后：多跳 eval 25/25，Company 295，jobs.csv Company duplicate groups 0，同名跨类型冲突 0，健康门禁 smoke 15/15、quality 47/47、CSA 6/6、semantic 6/6
- 🟡 【关系证据 backlog】新增 `scripts/govern_graph_evidence.py` dry-run 盘点：Position tier 污染为 0，但 REQUIRES / REGULATES / REFERS_TO / HAS_PROPERTY / REQUIRES_SKILL / HAS_CLASS 仍有历史证据缺口；该项独立于 business graph gate，待专项确认后再 confirm 和接入 gate

### v2.7 (2026-06-05 15:30)
- 🚨【架构同步】补充结构化层三分法：原始 CSV 是结构化事实源，`/Users/xiaoji/Documents/知识库分析/data/canonical/` 是治理层，`rag_index/csa_cache.sqlite` 是性能缓存层；cache/canonical 不能反向覆盖原始事实源
- 🚨【主键契约】新增 7 个 canonical 实体域：学员、客户、课程、教员、岗位、法规、题库；语义 ID（`document_id` / `regulation_id` / `question_bank_id`）不得替代 `chunk_id`
- 🚨【盘点入口】新增统一 ingest manifest 规则：`python3 scripts/build_ingest_manifest.py` 覆盖 CSV、源文档、SQLite、Neo4j、BM25、dense，优先用于真实情况审计、备份和同步检查
- 🚨【别名规则】判断 Neo4j `source_doc` 覆盖必须走 `rag_store/source_doc_aliases.json`；直接字符串等值会低估覆盖并造成误报
- 🟡 【自动门禁】新增导入/迁移/路由改动后的标准验证：`scripts/check_index_freshness.py`、`scripts/eval_route_policy.py`、`scripts/eval_health_gate.py`
- 🟡 【质量治理】明确优先用 `eval/query_traces.jsonl` 复盘 external completion、top sources、latency、degraded reasons、KG 低贡献召回；当前优化重点是治理/路由/新鲜度/评估自动化，不是重做架构

### v2.6 (2026-05-29 10:30)
- 🚨【架构同步】补充当前双 RAG + CSA 问答数据流：`/api/ask` 先做 CSA 结构化 CSV 路由，未命中再走 bge-m3 Dense + BM25 + Neo4j KG，最终正文统一由 SQLite chunk store 回源
- 🚨【手册冲突修复】业务问答从“先查 csv_query”改为“先查统一 /api/ask”，`csv_query.py` 仅用于调试、核对、统计和刷新
- 🚨【手册冲突修复】删除 `kg_query.py --stats` 旧命令口径，状态同步改用 `python3 pipeline/kg_health_check.py --stats-only`
- 🚨【手册冲突修复】抽取复盘示例从旧 `DESCRIBES` 关系改为 `CONTAINS`，关系白名单同步为 SUBCLASS_OF/PART_OF/DEFINED_BY 等精确关系
- 🚨【手册冲突修复】修正“RAG 直接拉 Neo4j description”旧说法：当前正文来自 SQLite，Neo4j description 影响图谱证据；正文事实修复需同步源文/SQLite chunk，并按需重建 Dense/BM25
- 🟡 新增健康基线：`scripts/eval_csa.py` 5/5 OK，`scripts/eval_smoke.py` 15/15 OK、hit@5 100%、degraded 0%
- 🟡 【规则口径】明确操作/飞行/知识点类 RAG 覆盖充分阈值：非degraded，≥3个source-backed命中；或2个高度精确且来源对应的命中。`≥2` 不自动视为充分覆盖。
- 🟡 【质量闭环】新增 `eval/quality_questions.json` 50题扩展评测、`eval/query_traces.jsonl` 诊断 trace、`scripts/audit_kg_noise.py` 只读关系噪声审计；当前质量基线 50/50 OK、source-backed 100%、hit@5 92%、degraded 0%。

### v2.5 (2026-05-28 16:00)
- 🚨【重大】完成 868 个实体的全量内容审计（Doubao Seed 2.0 Pro），发现并修复 168 个问题，其中 62 个高优先级事实错误、54 个描述过简、38 个分类错误、8 个矛盾
- 🚨【重大】知识库覆盖度提升：新增 26 个核心盲区知识点，覆盖 CAAC 法规/低空空域/操作检查/气象/考试大纲/行业应用等缺失领域，覆盖度从 83% 提升至 96%
- 🚨【SKILL优化】`knowledge-graph/SKILL.md` §3.5 规则修订：将 RAG 后强制同步查 Neo4j 改为按需触发（RAG 结果薄弱或用户追问时才触发），减少 70% 无效调用
- 🚨【修复顺序确认】事实错误（P0）→ 描述过简（P1）→ 分类错误（P1）→ 矛盾（P1），用户 2026-05-28 确认该修复顺序
- 🟡 §11 新增 11.4 全量实体内容审计章节：审计流程、模型选择、问题分类体系（4类18型）、修复流程、实战数据（868实体/168问题/19.4%发现率）
- 🟡 新增 §17 知识盲区覆盖管理章节：盲区检视方法、分类优先级、实体生成入库流程、实战数据（26个盲区/覆盖度96%）
- 🟡 新增全量审计脚本 `pipeline/rag_audit.py`：支持分批审计、增量保存 JSONL、断点续审
- 🟡 新增盲区分析脚本 `pipeline/gap_scan.py`：基于现有实体分布推断缺失领域
- 🟡 审计报告自动保存 `/tmp/rag_audit_report.md`（含168项明细+26个盲区清单）
- 踩坑：shell 中双引号嵌套 Python 字符串导致引号冲突、文件路径与工作目录不一致导致 import 失败（修复：用临时 .py 文件执行）
- 踩坑：Neo4j cypher-shell 在 macOS 上未预装（修复：使用 python neo4j 驱动 + 参数化查询）
- 踩坑：RAG server（localhost:5001）在审计修复期间未运行，导致无法通过 RAG 接口直接验证修复效果（已改为直接查 Neo4j 验证）

### v2.4 (2026-05-27 13:45)
- 🚨【铁律】知识库抽取禁止自动降级模型：必须使用 GPT-5.5，可 fallback 到多个 GPT-5.5 中转站，但没有用户确认不得切到 DeepSeek Flash 或其他低成本模型（用户 2026-05-27 指令）
- 🚨【铁律】实体节点必须双标签：`Entity` + 具体类型（如 `:KnowledgePoint:Entity`），不能只标 `:Entity`（2026-05-27 Claude审计修正）
- 🚨 prompt 关系约束细化：新增 `SUBCLASS_OF`（子类）、`PART_OF`（组成部分）、`DEFINED_BY`（法规依据），替代语义模糊的 BELONGS_TO
- 🟡 prompt 新增「理论题库特殊规则」：产品型号作为 example 属性不建独立节点、别名合并（罗马数字→阿拉伯数字）、排除过细实体
- 🟡 关系原则：优先使用精确关系（SUBCLASS_OF / PART_OF / DEFINED_BY），`BELONGS_TO` 降级为最后兜底
- 🟡 实体瘦身标准：题库类文档实体数应为题目数的 1~1.5 倍（66 题→66 实体 ✅），大于 2 倍则为过细
- 🟡 Neo4j 写入增加 example 属性支持：LLM 标记 example 字段时自动写入节点属性，避免型号信息丢失
- 踩坑：GPT-5.5 prompt 未对理论题库做特殊约束导致产品型号被抽成独立节点（已通过 prompt 特殊规则修正）
- 踩坑：BELONGS_TO 占比 64% → AP 关系语义贫乏，无法区分等级、组成和法规依据（已通过 SUBCLASS_OF/PART_OF/DEFINED_BY 修正）
- 踩坑：所有实体只标 Entity 标签导致图谱无法按类型查询（已通过双标签机制修正）
- 踩坑：t8star Claude Opus 间歇性 401 无效令牌（重试一次即可恢复，可能是限频）
- 踩坑：shell heredoc 中 `***`（三个星号）被 zsh 展开为递归 glob 导致 API Key 被截断为 3 字符（修复：改用 `<< 'PYEOF'` 单引号 heredoc 避免展开）
- 🚨 修复Cypher MERGE跨文档污染：用 `:KnowledgePoint:Entity` 双标签 MERGE 无法匹配旧 `:Entity` 单标签节点，导致重复节点和跨文档关系污染。修复：用 `:Entity` 单标签 MERGE，`ON CREATE/ON MATCH SET` 具体类型标签
- 🚨 关系过滤不能仅依赖 prompt 约束，LLM 会自行关联已有实体名。必须在脚本层用 `_created_by` 或 `new_ids` 做代码级校验
- 🚨 `new_ids` 过滤无效原因分析：实际 `_created_by` 在 ON MATCH 中未被修改，但 LLM 输出中所有实体名都是该文档独有的（不包含旧实体名），导致筛选器从未触发。跨文档污染由 LLM 在关系维度引入（关联未在当前文档中出现的实体名）。但方案仍有价值：清空后用 `_created_by` 做 post-processing 清洗更可靠
- 🚨 12k截断导致大文件仅抽取4~39%：extract_one.py 默认截断12000字符，对于50k+的文件覆盖严重不足。《飞行原理》101k仅抽12%。修复：大文件需分段抽取或将截断值提升至50000+字符。此条已在§3.5.3补充

### v2.3 (2026-05-26 07:56)
- 修复：容器名 `neo4j` → `yunji-knowledge-graph`
- 修复：数据目录 `/opt/homebrew/var/neo4j/data/` → `neo4j-docker/data/`
- 修复：删除 `scripts/` 引用（从未实际创建），替换为直接 Neo4j 查询示例
- 新增：灾难恢复标准流程（`dump → load`），附踩坑说明
- 新增：`db.recovery.fail_on_missing_files=false` 急救参数说明
- 踩坑：raw store 覆盖导致 `Mismatching store id` 和 `Transaction logs missing`
- 🚨 全文章节编号重排（Codex P0-6）：子节号统一与父章节对齐
- 🚨 修复白名单数量矛盾：`20类` → `19类`（P0-1）
- 🚨 清理 5.4/5.5.4 映射表非白名单类型：`Platform`→`PlatformPresence`，删除 `Department/SalaryItem/Component/Score/Progress/SocialAccount/Product/Document`（P0-2）
- 🚨 5.2.1/5.2.2 重排序：离散关系规则在前，别名合并在后（P0-3）
- 🚨 统一降级链：5.5.1 与附录B 一致为 `Flash→Pro→MiniMax→Doubao`（P0-4）
- 🚨 统一name MERGE落地状态：5.2 与 5.5.6 描述一致（P0-5）
- 🟡 5.4 新增「行业规范」「无人机理论知识」分类映射（P1-1）
- 🟡 修复 `当前6大Category` → `当前7大Category`（P1-2）
- 🟡 Prompt关系白名单统一大写下划线：`BELONGS_TO | CONTAINS | REFERENCES | ...`（P1-4）
- 🟡 关系白名单新增 `LOCATED_IN | HAS_SALARY`，与 6.1 约束保持一致（P1-4）
- 🟡 5.5.2 表 GPT-5.5 重标注为「审计/大文件专用，非默认降级链」
- 🟡 5.5.6 代码示例关系类型统一为大写 `BELONGS_TO`
- 踩坑：raw store 文件直接覆盖导致 `Mismatching store id` 和 `Transaction logs missing`

### v2.2 (2026-05-22 17:45)
- 新增 §9：每次抽取后复盘清单（7步铁律）
- 新增 §10：抽取方法选择（extract_one vs GPT-5.5直抽）
- 新增 §11：质量审计框架（10项诊断指标 + 持续监控阈值）
- 新增 §12：交叉污染治理流程
- 新增 §13：孤儿实体治理流程
- 新增 §14：CONTAINS vs REFERENCES 语义规范
- 新增 §15：文档域分类（题库/培训/产品/人事/客户）
- 新增 §16：重抽后孤儿治理：source_doc 回收流程
- 删除 §3 文件夹扫描规则（废弃，不再用飞书scan流程）
- 删除 §4 白名单/黑名单（废弃，改用本地文件直抽）
- 更新 §9.1：模型选用加GPT-5.5（大文件+审计）
- 踩坑：_created_by 只预防不修复，删文档重抽导致孤儿标记
- 踩坑：复盘跳过用户确认环节（已通过 §9 防止）
- 踩坑：GPT-5.5直抽脚本列别名冲突（RETURN e.id AS i 与循环变量i冲突）
- 踩坑：source_doc与_created_by不同步导致孤儿（删文档重抽后source_doc残留但_created_by被清）
- 踩坑：网页API LIMIT=900只加载47%节点，让用户误以为有孤立节点
- 踩坑：运营数据误入库后，删文档但不删实体→orphan残留
- 踩坑：不该建虚拟文档（同用户确认后删除）
- 踩坑：self-loop关系（A-PROVIDES->A）由LLM抽取时from_id=to_id导致

### v2.1 (2026-05-22 11:23)
- CONTAINS边保护规则
- 培训方案特殊抽取规则
- 文件类型预判规则（正式文档/运营数据/岗位信息/培训方案/价格表）
- _created_by 防交叉污染机制
- 锚定机制（防孤岛）
