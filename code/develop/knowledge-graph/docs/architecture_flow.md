# 知识图谱架构路径图

> 构建时间：2026-06-06
> 架构版本：semantic-graph-v2

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       用户问题入口                                                       │
│                                GET /api/ask?q="..."                                                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    Step 0: 路由判定                                                      │
│                                                                                                          │
│  csa_router.answer(q) ──→ classify_route(q, csa_result)                                                 │
│                                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │  判定逻辑（route_policy.py）：                                                                    │   │
│  │                                                                                                  │   │
│  │  ① graph_first 问题？                                                                             │   │
│  │     → 2个以上业务域 + 推理意图词（"适合/匹配/路径/规划/涉及哪些"等）                                 │   │
│  │     → route = "graph_first"                                                                      │   │
│  │                                                                                                  │   │
│  │  ② CSA 命中且无需 hybrid？                                                                        │   │
│  │     → 纯结构化问题（价格/学员数/岗位数/客户数）                                                   │   │
│  │     → route = "csa"  → 直接返回，不走任何检索                                                     │   │
│  │                                                                                                  │   │
│  │  ③ CSA 部分命中 + 有知识类关键词？                                                                │   │
│  │     → route = "hybrid"  → 结构+知识双路                                                          │   │
│  │                                                                                                  │   │
│  │  ④ 其他知识类问题                                                                                 │   │
│  │     → route = "rag"                                                                              │   │
│  │                                                                                                  │   │
│  │  ⑤ 含外部特色价格问询（UTC/穿越机/团培定制）                                                      │   │
│  │     → route = "rag_external_candidate"                                                           │   │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
               ┌───────────────────────────┼───────────────────────────┐
               │                           │                           │
               ▼                           ▼                           ▼
       ┌───────────────┐         ┌───────────────────┐       ┌───────────────────┐
       │    CSA 直通    │         │ Graph-First 路径   │       │  RAG / Hybrid 路径  │
       │  (route=csa)   │         │ (route=graph_first)│       │ (route=rag/hybrid)  │
       └───────┬───────┘         └─────────┬─────────┘       └─────────┬─────────┘
               │                           │                           │
               ▼                           ▼                           ▼
   ┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
   │                       │   │  Step 1: Query Rewrite │   │  Step 1: Query Rewrite │
   │  CSA SQLite 缓存      │   │  (规则模式, 无 LLM)     │   │  (规则模式, 无 LLM)     │
   │  csa_cache.sqlite     │   │                       │   │                       │
   │                       │   │  rewritten_q           │   │  rewritten_q           │
   │  18个CSV → 实时秒回     │   │  entities[]            │   │  entities[]            │
   │                       │   │  keywords[]            │   │  keywords[]            │
   │  "精英班多少钱"         │   │  intent                │   │  intent                │
   │  "沙浩的学员数"         │   │  need_kg               │   │  need_kg               │
   │                       │   └───────────┬───────────┘   └───────────┬───────────┘
   └───────────┬───────────┘               │                           │
               │                           ▼                           ▼
               │              ┌───────────────────────────┐   ┌───────────────────────────┐
               │              │  semantic_plan 构建         │   │  semantic_plan 构建         │
               │              │  (semantic_schema.py)      │   │  (semantic_schema.py)      │
               │              │                           │   │                           │
               │              │  domains: [检测到的业务域]   │   │  domains: [检测到的业务域]   │
               │              │  graph_query_plan:         │   │  graph_query_plan:         │
               │              │    entry_entities          │   │    entry_entities          │
               │              │    domain_anchors          │   │    domain_anchors          │
               │              │    relation_hints          │   │    relation_hints          │
               │              │    candidate_documents     │   │    candidate_documents     │
               │              │  needs.graph_first = true  │   │  needs.graph_reasoning = T │
               │              └───────────┬───────────────┘   └───────────┬───────────────┘
               │                          │                               │
               │                          ▼                               ▼
               │              ┌───────────────────────────┐   ┌───────────────────────────┐
               │              │  Step 2a: KG 优先召回      │   │  Step 2: Dense RAG         │
               │              │  (graph_first 模式)        │   │  (向量检索)                 │
               │              │                           │   │                           │
               │              │  kg_recall.recall(         │   │  get_embedding()            │
               │              │    entities,               │   │  → bge-m3 Dense            │
               │              │    "graph_first",          │   │  → 11M 向量库               │
               │              │    keywords,               │   │  → cos_sim TOP-K           │
               │              │    rewritten_q,            │   └───────────┬───────────────┘
               │              │    semantic_plan           │               │
               │              │  )                         │               │
               │              │                           │               ▼
               │              │  ┌───────────────────┐    │   ┌───────────────────────────┐
               │              │  │  _match_entities() │    │   │  Step 2b: BM25 关键词检索    │
               │              │  │  name模糊匹配       │    │   │  (graph_first 跳过此步)      │
               │              │  └─────────┬─────────┘    │   │                           │
               │              │            │              │   │  BM25 7M 倒排索引          │
               │              │            ▼              │   │  → TF-IDF TOP-K           │
               │              │  ┌───────────────────┐    │   └───────────┬───────────────┘
               │              │  │_expand_relations()│    │               │
               │              │  │ 1-hop: 30条       │    │               │
               │              │  │ 2-hop: 20条       │    │               │
               │              │  │ 双向路径 + 置信度   │    │               │
               │              │  └─────────┬─────────┘    │               │
               │              │            │              │               │
               │              │            ▼              │               │
               │              │  ┌───────────────────┐    │               │
               │              │  │ _collect_chunk_ids │    │               │
               │              │  │ source_doc → SQLite│    │               │
               │              │  │ probe_terms → 意图  │    │               │
               │              │  │ 实体名 → 全文搜索    │    │               │
               │              │  └─────────┬─────────┘    │               │
               │              │            │              │               │
               │              │            ▼              │               │
               │              │  kg_result = {            │               │
               │              │    chunk_ids: [...],      │               │
               │              │    paths: [{path,         │               │
               │              │             relation,     │               │
               │              │             confidence,   │               │
               │              │             domain,       │               │
               │              │             evidence}],   │               │
               │              │    evidence_bindings: [{  │               │
               │              │       chunk_id,           │               │
               │              │       doc_name,           │               │
               │              │       matched_entities,   │               │
               │              │       graph_paths,        │               │
               │              │       text_owner: "sqlite"│               │
               │              │    }]                     │               │
               │              │  }                        │               │
               │              └───────────┬───────────────┘               │
               │                          │                               │
               │                          └───────┬───────────────────────┘
               │                                  │
               │                                  ▼
               │              ┌───────────────────────────────────────────────┐
               │              │  Step 3: 双路 Merge / Rerank                  │
               │              │  (merge_rerank.py)                            │
               │              │                                               │
               │              │  Dense BM25 KG 三路的 TOP-K → 去重 → 重排序    │
               │              │  score = 0.4*dense + 0.3*bm25 + 0.3*kgsource  │
               │              │  带 source_backed 标注                        │
               │              └───────────────────┬───────────────────────────┘
               │                                  │
               │                                  ▼
               │              ┌───────────────────────────────────────────────┐
               │              │  Step 4: Context Builder                      │
               │              │  (context_builder.py)                         │
               │              │                                               │
               │              │  ┌─────────────┐  ┌─────────────────────┐    │
               │              │  │ KG 证据 20%  │  │ 文本上下文 80%        │    │
               │              │  │             │  │                     │    │
               │              │  │ 【图谱关系   │  │ 【来源1】飞行原理     │    │
               │              │  │  推理】      │  │  (相关度: 85%)       │    │
               │              │  │  空域分类    │  │  多旋翼升力由...... │    │
               │              │  │  -[DEFINED  │  │                     │    │
               │              │  │  _BY]->     │  │ 【来源2】CCAR-92部   │    │
               │              │  │  CCAR-92部  │  │  (相关度: 72%)       │    │
               │              │  │             │  │  第八章 运行管理...  │    │
               │              │  │  涉及实体:   │  │                     │    │
               │              │  │  空域分类、  │  │  + 相邻chunk补齐    │    │
               │              │  │  CCAR-92...  │  │                     │    │
               │              │  └─────────────┘  └─────────────────────┘    │
               │              │                                               │
               │              │  evidence: [{type: "graph_path|document"}]    │
               │              │  sources: [{chunk_id, doc_name, relevance}]   │
               │              └───────────────────┬───────────────────────────┘
               │                                  │
               │                                  ▼
               │              ┌───────────────────────────────────────────────┐
               │              │  Step 5: LLM Answer                          │
               │              │  (context_builder.build_answer_prompt)        │
               │              │                                               │
               │              │  意图限定 role_prompt:                        │
               │              │  regulation / company / job / training / gen  │
               │              │                                               │
               │              │  DeepSeek Flash 生成回答                      │
               │              │  250字左右 · 带【来源N】引用 · 简洁专业        │
               │              └───────────────────┬───────────────────────────┘
               │                                  │
               │                                  ▼
               │              ┌───────────────────────────────────────────────┐
               │              │  Step 6: Trace 记录                           │
               │              │                                               │
               │              │  query_traces.jsonl                           │
               │              │  {trace_id, route, semantic_domains,          │
               │              │   top_sources, elapsed, degraded,             │
               │              │   source_count, retriever_counts}             │
               │              │                                               │
               │              │  同时上报 request_quality 监控               │
               │              └───────────────────┬───────────────────────────┘
               │                                  │
               │              ┌───────────────────────────────────────────────┐
               │              │  Graph-First 补充：降级检测                     │
               │              │  (graph_first_status)                         │
               │              │                                               │
               │              │  ✅ 有 entry_entities                          │
               │              │  ✅ 有 relation_paths                         │
               │              │  ✅ 有 SQLite chunk_evidence                  │
               │              │                                               │
               │              │  缺任一 → insufficient_step 标识              │
               │              │  用于诊断：哪一步卡住了                        │
               │              └───────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    质量控制闭环                                                          │
│                                                                                                          │
│  每轮修改后自动跑：                                                                                      │
│                                                                                                          │
│  make domain-sync-gate                                                                                   │
│    ├─ build_ingest_manifest.py    ──→  CSV/SQLite/Neo4j/BM25/Dense 统一盘点                             │
│    ├─ check_index_freshness.py    ──→  SQLite fingerprint 对齐检查                                       │
│    ├─ build_domain_sync_package.py ──→ 分域增量包 (regulation/question_bank/textbook)                   │
│    ├─ replay_domain_sync_package.py──→ 远端回放验证                                                       │
│    ├─ eval_route_policy.py        ──→ 路由策略抽样验证                                                    │
│    ├─ eval_health_gate.py         ──→ 4套门禁自动跑                                                       │
│    └─ eval_smoke.py + eval_csa.py ──→ 烟雾测试 + CSA 专业化                                              │
│                                                                                                          │
│  eval/query_traces.jsonl → 每次问答的完整诊断 trace                                                       │
│  scripts/audit_kg_noise.py  → 图谱关系噪声审计                                                           │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 数据流标记说明

| 标记 | 含义 |
|:----:|------|
| `→` | 同步调用 |
| `⇢` | 异步/未来 |
| `●` | 数据持久化层 |
| `◆` | 路由决策点 |
| `■` | LLM 调用 |
| `⚠` | 降级/兜底 |

## 存储层一览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  存储层                           │  用途                        │  规模     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Neo4j bolt://localhost:7687      │  语义关系推理 (不做正文存储)    │  5,730节点 │
│                                   │                                │  391k关系  │
│  rag_chunks.db (SQLite)           │  Chunk 正文唯一权威源          │  2,363条   │
│  rag_index/dense_bge_m3.sqlite    │  bge-m3 向量索引               │  11MB      │
│  rag_index/bm25/                  │  BM25 倒排索引                │  7MB       │
│  rag_index/csa_cache.sqlite       │  CSA 结构化缓存                │  1.3MB     │
│  小技结构化数据/ (CSV 18个)        │  结构化事实权威源               │  8,012行   │
│  知识库分析/data/canonical/       │  canonical 治理层              │  7个实体域  │
└─────────────────────────────────────────────────────────────────────────────┘
```
