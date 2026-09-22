# USAGE.md — 知识图谱问答服务使用说明

面向调用方（应用开发、集成方、日常使用人员）。读完这份文档你应该能回答三个问题：
**这套系统能答什么、怎么调、答案能不能信。**

部署与运维请看 `DEPLOY.md`。

---

## 1. 这套系统是什么

一个**只读用途**的知识问答服务。它把已经整理好的专业资料切成文本块，建了关键词索引、
向量索引和一张知识图谱，收到问题后先检索、再让大模型基于检索到的内容组织措辞。

关键点：**答案的事实来自库内检索结果，大模型只负责把检索到的内容组织成人话。**
库里没有的东西，正确行为是明说没有，而不是编一个。

### 1.1 能回答什么（只有这四个域）

| 文档域 | 内容 | 典型问题 |
| --- | --- | --- |
| **政策法规** | 民用航空法、无人驾驶航空器飞行管理暂行条例、CCAR-92 部、实名登记管理规定、操控员执照考试管理办法、训练机构规范等 | "民用无人驾驶航空器实名登记需要准备哪些材料？" |
| **无人机理论书籍** | 已入库的几本无人机理论教材（概论、系统结构与设计、技术概论、影视航拍） | "无人机数据链路如何保障通讯稳定和安全？" |
| **理论题库** | 分章节的理论考试题目、参考答案与解析（概述、飞行原理、气象、空管、系统组成、任务规划、注意事项、法律法规等） | "大气的组成是由？" |
| **地面站考题考试条件** | 2026H1 批次地面站实操题型及其结构化考试条件（避让点、双经纬度、双起飞点、同一直线、夹角、时钟夹角、罗盘双坐标、航向相同相反、空域或地形限制、三角函数） | "地面站避让点题型的考试条件有哪些？" |

### 1.2 不能回答什么

**除上表四个域之外的一切，库里都没有。** 具体包括但不限于：

- 任何机构内部经营与管理事务；
- 任何涉及具体个人的信息；
- 任何需要实时性的事情（数据是冻结快照，见第 7 章，没有"今天""最新"的概念）；
- 任何跨库统计报表（它不是报表系统）；
- 法律意见或个案判断——它能给出法规原文与条款出处，但"我这次这么飞违不违规"
  属于个案认定，请以主管部门口径为准；
- 四个域之外的其他国家/地区法规、其他行业标准、公开新闻等。

问到域外内容时，**正确的表现是明确说"知识库中没有相关数据"**。
如果你看到它给出了具体数字、金额、名单、条款号，那是异常，请按第 6 章处理。

> **给集成方的提醒**：不要因为服务"看起来什么都答得上来"就扩大使用范围。
> 大模型有能力对任何问题生成通顺的文字，但只有落在上表四个域内、且有 `sources`
> 支撑的回答才是本系统的有效输出。

`湖北云技科技有限公司`、`云技科技公司`、`湖北云技科技`、`云技科技` 属于源环境业务实体，
不在 portable 四域快照中。询问这些实体时必须返回域外拒答，不能从名称推断或借用本机数据。

---

## 2. 怎么调

### 2.1 基本调用

```
POST /api/ask
Content-Type: application/json

{"user_query": "雷暴天气下无人机飞行有什么危险和避让措施？"}
```

字段名是 **`user_query`**，不是 `q`、不是 `question`、不是 `query`。写错会被拒绝
（返回 400，`error` 字段说明原因）。

```bash
curl -s -X POST https://kg.example.com/api/ask \
  -u "$KG_USER:$KG_PASS" \
  -H 'Content-Type: application/json' \
  -d '{"user_query":"民用无人驾驶航空器实名登记需要准备哪些材料？"}' | jq .
```

### 2.2 可选字段

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `allowed_sources` | 字符串数组 | 限定本次允许使用的检索通道。建议固定传 `["csa","sqlite_exact","bm25","dense","neo4j"]` |
| `risk_level` | `low` / `standard` / `high` / `critical` | 不传则由服务按问题内容自动判定 |
| `timeliness` | `stable` / `current` / `latest` | 本服务是冻结快照，保持默认 `stable` 即可 |

```json
{
  "user_query": "CCAR-92 部对操控员执照有哪些要求？",
  "allowed_sources": ["csa", "sqlite_exact", "bm25", "dense", "neo4j"]
}
```

> **关于外部通道**：通道清单里还存在 `official_api` / `web` 两个外部检索通道。
> 本次部署已在**服务端**用环境变量把它们摘除，调用方即使显式请求也不会生效。
> 请求里再传一次 `allowed_sources` 属于第二道保险，不是必需，但推荐加上——
> 万一将来服务端配置被改动，这一层仍然有效。

### 2.3 命令行客户端

仓库自带 `deploy/kg_query.py`，读环境变量 `RAG_URL`。以下命令从仓库根目录执行：

```bash
export RAG_URL=http://127.0.0.1:5001/api/ask
python3 deploy/kg_query.py "大气的组成是由？"          # 自然语言回答 + 来源列表
python3 deploy/kg_query.py --json "无人机分类有哪些"    # 结构化 JSON
```

它已经内置了重试、超时和"服务不可用 ≠ 库里没数据"的错误区分（见第 6 章），
写脚本时优先复用它，不要自己裸写 HTTP。

`kg_query.py --json` 会保留顶层 `degraded` / `degraded_reasons`，但仍是兼容投影，
不包含 `graph_paths`、`evidence_bindings` 等全部原始字段。执行 `DEPLOY.md` 第 9 章的迁移
验收时，应保留 `/api/ask` 原始 JSON，不能用该投影代替完整验收记录。
服务端已接受的查询即使返回 422 / 500 / 503，客户端也会从响应体保留同一组顶层降级字段；
连接失败时则使用 `service_unavailable` 作为降级原因。

### 2.4 约束

- 问题长度上限 **2000 字符**，超出返回 `user_query_too_long`；
- 单次请求建议超时设 15 s；回答模型串行预算固定为 5.2 s，完整验收要求单题最大耗时不超过 12 s；
- 用 `POST`（`GET` 是历史兼容路径，不要用）；
- 对外入口有限流（默认 10 次/分钟/IP），批量跑题请与运维约定窗口；
- 对外只开放 `/api/ask` 与 `/api/health` 两个路径，其余一律 404。

---

## 3. 响应里该看什么

一次成功响应字段很多，日常只需要盯这几个：

```json
{
  "query": "大气的组成是由？",
  "route": "rag",
  "degraded": false,
  "answer": "……",
  "sources": [
    {"doc_name": "理论题库_气象", "chunk_id": "...", "score": 0.83}
  ],
  "question_bank_hit": true,
  "question_bank_exact_hit": true,
  "question_bank_matched_question": {
    "number": "…",
    "stem": "大气的组成是由？",
    "options": ["…"],
    "answer": "…",
    "chunk_id": "question_bank:…",
    "doc_name": "理论题库_气象"
  },
  "claim_evidence": {
    "finalizer_invoked": true,
    "outcome": "passed",
    "claim_support_rate": 1.0,
    "unsupported_high_risk_claims": 0
  },
  "graph_paths": [],
  "evidence_bindings": [],
  "review_required": false,
  "stats": {
    "trace_id": "…",
    "answer_model": {
      "primary_status": "succeeded",
      "model_fallback_status": "not_attempted",
      "extractive_fallback_used": false,
      "fallback_recovered_answer": false,
      "unrecovered_model_failure": false,
      "answer_method": "primary_model",
      "answer_status": "answered"
    }
  }
}
```

| 字段 | 怎么读 |
| --- | --- |
| `route` | 本次走了哪条链路，见第 4 章 |
| `degraded` | **最重要的开关**。`false` = 正常检索并有证据支撑；`true` = 链路降级（某个检索器失败、证据不足、被守卫拦截），答案可信度显著下降 |
| `degraded_reasons` | `degraded` 为 `true` 时给出原因清单，排障用 |
| `sources` | 支撑答案的来源。**空数组意味着这个回答没有库内依据** |
| `question_bank_exact_hit` | 是否命中了题库原题，见 5.3 |
| `graph_paths` / `evidence_bindings` | 图谱辅助召回的路径与证据绑定；出现路径时必须有可解析到当前快照 `chunk_id` 的绑定 |
| `review_required` | 命中了需要人工复核的冲突内容（例如同一事项存在新旧两版表述），这时答案要人来判 |
| `claim_evidence` | 回答发布前的 claim/evidence 终审遥测；正常接受必须为 `finalizer_invoked=true`、`outcome=passed`、`unsupported_high_risk_claims=0` |
| `stats.answer_model` | 回答恢复链遥测。顺序固定为 DeepSeek、Doubao Mini、权威摘录、安全拒答；重点检查 `fallback_recovered_answer` 与 `unrecovered_model_failure` |
| `stats.trace_id` | 本次请求的唯一 ID。**报障时务必附上它**，运维能据此拉出完整检索轨迹 |

> `answer` 里出现的 `【来源N】` 标注对应 `sources` 数组的下标顺序；
> 若你没有显式追问出处，服务会在输出时把它渲染成《文档名》或直接去掉。

Mini 或权威摘录完整恢复且 claim/evidence 终审通过时，`fallback_recovered_answer=true`，该次回答
可以保持 `degraded=false`；主模型故障仍由 `primary_status` / `primary_timed_out` 留痕。只有恢复失败、
答案流水线异常或终审阻断才把回答标为 degraded，正式门禁要求
`unrecovered_model_failure=false`，而不是要求永不使用备用链。

批量验收比较 `expected_docs` 时，响应里的 `doc_name` 可能省略末尾 `.txt`。两边只去掉这个
末尾扩展名后做精确比较，不做模糊包含或临时别名映射。普通题至少命中一个预期文档；
`sys_04` 与 `app_05` 是跨文档代表题，必须命中各自两个预期文档，少一个也不通过。

来源覆盖仍不等于答案正确。正式验收还必须加载与 80 题逐字绑定、80/80 独立人审并由 SSHSIG
激活的 Cloud Gold，对 required claims、forbidden claims、同义表达、authority SHA 与有效期逐题
评分。安全拒答必须与人工签署模板字符串全等；标点、空白或夹带猜测都失败。
pending Gold、`--report-only` 或未签名的 `--prepare-attestation` 只能生成诊断/待签证据，
不能生成发布通过结论。独立 attestation 要求证明人与 Gold 审批人的 normalized named human
和 SSH public-key fingerprint 都不同；decision 同时绑定 Gold decision/signature/public-key 哈希、指纹与
`approved_by` / `approved_at`。正式结论只来自验证了这些绑定的 `--formal-offline`。

---

## 4. 路由

服务在检索前会先给问题分类，决定走哪条链路。路由结果在 `route` 字段里。

当前迁移版正常可达值只有 `csa`、`rag`、`hybrid`，异常值为 `governance_error`、
`error`。代码保留 `graph_first` 的响应结构，但四域 L2 裁剪后没有启用它的跨域组合，
因此不应把 `graph_first` 当作当前部署的验收目标。

### 4.1 `csa` —— 结构化直答

**是什么**：问题问的是已经结构化成表的确定性数据（当前只有地面站考题的考试条件）。
服务直接查表给答案，不经过模糊检索。

**特点**：确定、可复现、快。答案里的条件、题型、数量都是表里逐行取出来的。

**什么问题走这条**：

- `地面站避让点题型的考试条件有哪些？`
- `罗盘双坐标题型考察哪些能力？`
- `空域限制题型的高度和航向要求是什么？`

### 4.2 `rag` —— 文本检索问答

**是什么**：默认链路。关键词检索（BM25）+ 向量检索并行召回，合并重排后交给模型基于
上下文作答。绝大多数问题走这条。

**什么问题走这条**：

- `雷暴天气下无人机飞行有什么危险和避让措施？`
- `民用无人驾驶航空器实名登记需要准备哪些材料？`
- `无人机数据链路如何保障通讯稳定和安全？`
- 任何一道理论题库原题

### 4.3 `hybrid` —— 结构化 + 文本混合

**是什么**：问题一半问结构化数据、一半问文本知识，或者问的是"趋势/特点/变化"这类
需要在结构化统计之上再加文本解释的题。服务把两边结果合到一起作答。

**什么问题走这条**：

- `2026H1 地面站考试条件有哪些出题特点？`
- `地面站题型近期有哪些新题型？`

**注意边界**：地面站结构化数据当前只覆盖 2026H1 这一个批次，库内**没有**上一批次可对照。
所以问"相比往期有什么变化"，正确回答是"只能总结当前批次特点，无法证明相对往期的变化"。
如果它斩钉截铁地说"与往年基本一致"或"新增了 X 题型"，那是编的，按第 6 章处理。

### 4.4 图谱辅助 —— 当前仍显示为 `rag` / `hybrid`

**是什么**：迁移版保留裁剪后的知识图谱作为派生召回层。问题需要实体关系或跨文档
证据时，普通 `rag` / `hybrid` 链路可以同时查询图谱，再以 SQLite 文本块校验路径证据。

**适合观察图谱辅助的题**：

- `无人机物流配送的技术发展和法规现状如何？`
- `无人机数据链路如何保障通讯稳定和安全？`

**判读要点**：是否可信首先看 `sources` 是否覆盖题池的 `expected_docs`。响应若提供
`graph_paths`，必须同时提供有效 `evidence_bindings`；没有绑定的路径不得作为依据。
普通 RAG 已有充分文本证据时，`graph_paths` 为空本身不构成失败。

### 4.5 异常路由值

| 值 | 含义 | 你该做什么 |
| --- | --- | --- |
| `governance_error` | 证据治理组件不可用，服务主动失败关闭 | 这**不是**"库里没有"，按第 6 章当作服务故障上报 |
| `error` | 服务内部异常 | 同上 |

---

## 5. 怎么判断答案可信

按顺序过这四关，四关都过才算可信。

### 5.1 第一关：`degraded` 必须是 `false`

`degraded: true` 表示这一轮检索没能正常完成或证据不足。此时答案可以看，但**不能直接采信**，
需要人工回到原文核对。配合 `degraded_reasons` 看具体是哪一环出了问题。

常见原因里有一个要特别注意：`embedding_failed:*` 或 `dense_index_stale_or_missing`
表示向量检索这条腿断了，此时只剩关键词检索，同义/近义问法的召回会明显变差。
这属于运维故障，请报障而不是换问法硬试。

### 5.2 第二关：来源覆盖

- `sources` **非空**；
- 来源的 `doc_name` 与问题主题**对得上**（问法规却只有教材来源，说明检索跑偏了）；
- 答案里的每个关键结论都能在某条来源里找到对应。

**没有来源的答案 = 没有依据的答案。** 无论措辞多确定，都按"不可信"处理。

### 5.3 第三关：题库精确命中的含义

问理论题库的原题时，注意区分两个字段：

| 字段 | 含义 |
| --- | --- |
| `question_bank_hit: true` | 只是**检索命中了题库文档**，可能只是命中了同章节的相邻内容 |
| `question_bank_exact_hit: true` | **命中了题库里的那道原题**，`question_bank_matched_question` 会返回含题号、题干、选项、答案和来源坐标的对象 |

**只有 `question_bank_exact_hit` 为 `true` 时，答案里的"参考答案"才是题库里的标准答案。**
该对象的固定字段为 `number`、`stem`、`options`、`answer`、`chunk_id`、`doc_name`；
验收时至少要求 `stem`、`answer`、`chunk_id`、`doc_name` 非空。

如果只有 `question_bank_hit` 为 `true`、`exact` 为 `false`，说明服务没找到你问的那道题，
此时它给出的选项判断是模型基于相关材料的推断，**不能当标准答案用**，尤其不能直接印进试卷。

### 5.4 第四关：`review_required`

`review_required: true` 表示命中的内容存在需要人工裁决的冲突（典型是法规新旧版本并存）。
这类答案必须由懂业务的人确认适用哪一版之后再使用。

### 5.5 快速自检脚本

```bash
resp=$(curl -s -X POST "$RAG_URL" -H 'Content-Type: application/json' \
       -d '{"user_query":"民用无人驾驶航空器实名登记需要准备哪些材料？"}')
echo "$resp" | jq '{route, degraded, degraded_reasons,
                    src_count: (.sources|length),
                    docs: [.sources[].doc_name] | unique,
                    qb_exact: .question_bank_exact_hit,
                    review: .review_required,
                    trace: .stats.trace_id}'
```

`degraded == false` 且 `src_count > 0` 且 `docs` 与问题主题相符 → 可以用。
否则 → 回原文核对，或换个问法重问。

---

## 6. 回答红线

### 6.1 服务不可用 ≠ 库里没数据

**这是最重要的一条。**

当你遇到下面任何一种情况：

- HTTP `401` / `404` / `502` / `503` / `504`
- `ECONNREFUSED` / `Connection refused` / 连接超时 / DNS 解析失败
- 响应体里 `route` 是 `error` 或 `governance_error`
- `kg_query.py` 返回 `error_type: service_unavailable`

这说明的是 **"服务没连通或上游出错"**，**不是** "知识库里查不到"。

此时**绝对不允许**：

- ❌ 用自己的常识、经验或印象编一个答案，冒充查库结果；
- ❌ 把别处（搜索引擎、其他模型、旧文档）的内容当成本知识库的查询结果往下传；
- ❌ 对使用者说"知识库里没有这条"；
- ❌ 在自动化链路里把服务错误静默降级成"无结果"，让下游以为查过了。

**正确做法**：

- ✅ 原样上报错误，明确说明"**知识库问答服务当前不可用**，不是库里没有数据"；
- ✅ 附上请求的 URL、HTTP 状态码、原始错误信息；
- ✅ 通知运维按 `DEPLOY.md` 第 10 章排查；
- ✅ 待服务恢复后**重新查一遍**再下结论。

`kg_query.py` 已经内置了这个区分：传输层错误会返回
`error_type: "service_unavailable"` 并在 `error` 文本里写明
"这不是知识库无结果，而是服务未连通或上游返回错误"。集成时请把这个字段透传出去，
**不要在自己的封装里把它抹平成空结果**。

### 6.2 域外问题不得补全

问到四个文档域以外的内容，正确结果是明确的"库内没有数据"。任何形态的
"我猜大概是……""一般行业里是……""根据公开资料……"都属于越界输出。
遇到就记下 `trace_id` 报障。

### 6.3 无来源不得当结论

`sources` 为空、`graph_paths` 非空但缺少有效 `evidence_bindings`、
`question_bank_exact_hit` 为 `false` 却给出了"标准答案"、或 `claim_evidence.outcome`
不是 `passed`——这些情况下的输出
一律不得作为对外结论、教学材料或考务依据。

### 6.4 报障要带什么

1. `stats.trace_id`
2. 原始问题文本
3. 完整响应 JSON（至少含 `route` / `degraded` / `degraded_reasons` / `sources`）
4. 发生时间

运维凭 `trace_id` 能拉出这次请求的完整检索轨迹，没有它排障效率会差一个量级。

> 注意：服务会把每次提问的问题原文（截断 500 字符）与路由元数据写进服务器端的
> 追踪日志。请不要在问题里输入任何与四个文档域无关的敏感信息。

---

## 7. 数据是冻结快照

- 库里的内容对应某一个 **Release 版本**，部署之后**不会自动更新**，也不会自我学习。
- 对外入口只开放问答与健康检查两个路径，你**无法**通过对外接口往库里加内容。
- 需要新增/更正资料时，**联系维护方**。流程是：维护方在源环境完成整理与校验 →
  发布新的 Release（代码 tag + 数据附件 + sha256）→ 贵方技术人员按 `DEPLOY.md`
  升级并重跑验收。
- **不要在服务器上直接改 SQLite、改索引文件、往图库里写节点。**
  本交付版已移除图谱写接口与任意 Cypher 接口，反向代理还会再次拦截除问答和健康检查
  之外的路径。直接改底层文件或数据库仍会让 Release 快照、索引、图谱与来源标注失配；
  任何数据变更都必须走发版流程。
- 想知道当前跑的是哪一版：问运维要上线单里的代码 tag、数据 tag 与代码 commit。

---

## 8. 常见疑问

**Q：同一个问题两次问，答案措辞不一样，是不是不稳定？**
A：措辞由大模型组织，允许有差异；但 `route`、`sources`、`question_bank_exact_hit`、
`claim_evidence.outcome`
应当稳定。如果这几个字段在同样的问题上来回变，那是异常，报障。

**Q：问题里带错别字还能查到吗？**
A：向量检索有一定容错，但关键术语（条款号、题型名、专业名词）写错会明显影响命中。
命中不理想时先检查术语写法。若 `degraded_reasons` 里出现 `embedding_failed`，
说明容错能力这条腿当前是断的，属于故障。

**Q：能一次问多个问题吗？**
A：能，但不建议。复合问题容易被路由成 `hybrid` 后两边都答得浅。拆成单问效果更好。

**Q：为什么问"最新规定"结果不理想？**
A：库是冻结快照，没有"最新"的概念。请直接问具体法规名或条款内容。
若某事项存在新旧两版，`review_required` 会置 `true`，由人来判定适用版本。

**Q：`route` 和我预期的不一样，算 bug 吗？**
A：路由是按问题措辞确定性分类的，换个问法就可能换路由。只要 `degraded` 为 `false`
且来源对得上主题，就不算问题。持续跑偏（例如问法规却总走结构化直答）才需要报障。
