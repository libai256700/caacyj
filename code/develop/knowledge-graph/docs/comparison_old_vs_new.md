# 新旧知识库架构对比图

> 旧版：v2.4（手动提取 + Neo4j 单库）
> 新版：v2.7（语义图谱 + 双 RAG + CSA）

---

## 整体架构对比

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ 【旧版】v2.4                                                                       │
│                                                                                    │
│  飞书文件 ──→ scan_feishu.py ──→ online_extract.py ──→ Neo4j（存全部）                 │
│                               (28个废弃脚本混在一起)                                  │
│                                                                                    │
│  用户问题 ──→ 搜 Neo4j MATCH ──→ 有结果？ → 直接 description 回答                      │
│                                        → 无结果？ → 回"没有数据"                       │
│                                                                                    │
│  ┌──────────────────────────────┐                                                    │
│  │  Neo4j 身兼多职:               │                                                    │
│  │  • 关系图                      │                                                    │
│  │  • 正文存储（description）      │                                                    │
│  │  • 结构化数据（混着放）          │                                                    │
│  │  • 索引就是手写 Cypher           │                                                    │
│  └──────────────────────────────┘                                                    │
│                                                                                    │
│  关系: 64% BELONGS_TO，语义模糊                                                       │
│  实体: 单一 :Entity 标签，无法按类型查询                                                │
│  质量: 手写 Cypher 一条条查                                                          │
│  评测: 无                                                                           │
│  门禁: 无                                                                           │
│  同步: 无                                                                           │
└────────────────────────────────────────────────────────────────────────────────────┘

         ▼ 升级

┌────────────────────────────────────────────────────────────────────────────────────┐
│ 【新版】v2.7                                                                       │
│                                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  三层路由 + 三重检索 + 统一回源                                                  │  │
│  │                                                                              │  │
│  │                   用户问题                                                       │  │
│  │                       │                                                         │  │
│  │         ┌─────────────┼─────────────┐                                           │  │
│  │         │             │             │                                           │  │
│  │         ▼             ▼             ▼                                           │  │
│  │   ┌─────────┐ ┌─────────────┐ ┌───────────┐                                    │  │
│  │   │ CSA     │ │ graph-first │ │ RAG/hybrid│                                    │  │
│  │   │ 秒回    │ │ KG → SQLite │ │ Dense+BM25│                                    │  │
│  │   │         │ │             │ │ +KG       │                                    │  │
│  │   └─────────┘ └─────────────┘ └───────────┘                                    │  │
│  │         │             │             │                                           │  │
│  │         └─────────────┼─────────────┘                                           │  │
│  │                       ▼                                                         │  │
│  │              ┌────────────────┐                                                  │  │
│  │              │ Merge / Rerank │                                                  │  │
│  │              └───────┬────────┘                                                  │  │
│  │                      ▼                                                           │  │
│  │              ┌────────────────┐                                                  │  │
│  │              │ SQLite 统一回源  │  2,363 chunks                                   │  │
│  │              │ = 正文唯一权威源  │                                                  │  │
│  │              └───────┬────────┘                                                  │  │
│  │                      ▼                                                           │  │
│  │              ┌────────────────┐                                                  │  │
│  │              │ Context Builder│  证据链 + 来源标注                                 │  │
│  │              └───────┬────────┘                                                  │  │
│  │                      ▼                                                           │  │
│  │              ┌────────────────┐                                                  │  │
│  │              │ DeepSeek Flash │  回答带【来源N】引用                               │  │
│  │              └────────────────┘                                                  │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                    │
│  存储分离:                                                                          │
│    Neo4j (5,730节点/391k关系)  = 关系推理层                                           │
│    SQLite rag_chunks.db        = 正文权威源                                          │
│    CSV 18个 (8,012行)          = 结构化事实源                                        │
│    bge-m3 Dense + BM25         = 检索索引层                                          │
│  关系: SUBCLASS_OF / PART_OF / DEFINED_BY 等精确关系                                │
│  实体: 双标签 :KnowledgePoint:Entity，可类型查询                                      │
│  质量: 4套门禁全自动                                                                 │
│  评测: smoke 15/15, quality 47/47, csa 6/6, semantic 6/6                          │
│  同步: 3个分域增量包 + 远端回放                                                       │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 查询流程对比

```
【旧版】                                                                                【新版】
                                                                                      
用户问"考CAAC需要多少钱"                                                              用户问"考CAAC需要多少钱"
        │                                                                                      │
        ▼                                                                                      ▼
 搜 Neo4j MATCH (n {name:'CAAC'})                                              CSA 路由 → 秒回价格
        │                                                                                      │
        ▼                                                                                      ▼
 找到实体 → 读 description                                              ┌──────────────────────┐
   "CAAC是中国民用航空局..."                                            │ 价格: ¥15,800        │
        │                                                             │ 超视距: ¥32,800      │
        ▼                                                             │ 精英教员就业班: ¥... │
 深度不够，不知道价格在哪                                                └──────────────────────┘
        │                                                                                      
        ▼                                                                                      
 回"价格不在知识库范围内，建议咨询老师"                                                      



用户问"考超视距执照需要什么前提条件？"                                                   用户问"考超视距执照需要什么前提条件？"
        │                                                                                      │
        ▼                                                                                      ▼
 搜 Neo4j "超视距"                                                                  route = "graph_first"  
        │                                                                          (student + course 双域)
        ▼                                                                                      ▼
 找到一个节点 "超视距驾驶员"                                                        build_semantic_plan()
  无关系，无上下文                                                                  domains = ["student", "course"]
        │                                                                          relation_hints = ["OFFERS", "REQUIRES", "AWARDS"]
        ▼                                                                                      ▼
 回答不了                                                                          KG Recall:
                                                                                    "超视距驾驶员" -[REQUIRES]-> "CAAC执照"
                                                                                    "CAAC执照" -[REQUIRES]-> "理论考试"
                                                                                    "CAAC执照" -[REQUIRES]-> "实操评定"
                                                                                    "理论考试" -[DEFINED_BY]-> "民用航空法"
                                                                                                   │
                                                                                                   ▼
                                                                                  SQLite 回源 → 合并证据
                                                                                  "需要理论考试通过和实操评定..."
```

---

## 数据存储对比

```
【旧版：Neo4j 身兼多职】                            【新版：分层解耦】

┌────────────────────────┐                        ┌────────────────────────┐
│      Neo4j             │                        │  CSV (18个, 8,012行)   │ ← 结构化事实权威源
│                        │                        │     ↓ canonical       │
│  知识点关系 + 正文      │                        │  治理层 /data/canonical│
│  结构化数据混着放       │                        │     ↓ cache           │
│  56个Document          │                        │  csa_cache.sqlite     │ ← 性能层
│  7大Category直接硬编码  │                        └────────────────────────┘
│  28个废弃脚本躺在目录里  │                        
└────────────────────────┘                        ┌────────────────────────┐
                                                   │  Neo4j (5,730节点)     │ ← 关系推理层
                                                   │  只做关系，不存正文     │
                                                   │  SUBCLASS_OF/PART_OF   │
                                                   │  DEFINED_BY 等精确关系  │
                                                   └────────────────────────┘
                                                   
                                                   ┌────────────────────────┐
                                                   │  SQLite rag_chunks.db   │ ← 正文权威源
                                                   │  2,363 chunks           │
                                                   │  24个文档               │
                                                   └────────────────────────┘
                                                   
                                                   ┌────────────────────────┐
                                                   │  Dense + BM25          │ ← 检索索引层
                                                   │  11M + 7M              │
                                                   │  bge-m3 + 倒排索引      │
                                                   └────────────────────────┘
```

---

## 关系体系对比

```
【旧版】                                【新版】

BELONGS_TO 占 64%                    SUBCLASS_OF  （子类关系）
  语义模糊、无法区分                     PART_OF     （组成关系）
  "A BELONGS_TO B" 什么意思？          DEFINED_BY  （法规依据）
   一个人属于公司？                     REGULATES   （法规约束）
   一个产品属于分类？                   REFERS_TO   （引用关系）
   一个知识点属于文档？                 REQUIRES    （前提要求）
                                     REQUIRES_SKILL（技能需求）
DESCRIBES / MENTIONS 大量滥用          AFFECTS     （影响关系）
                                     OFFERS      （提供服务）
BELONGS_TO 跨域乱串                    AWARDS      （颁发证书）
  SalaryItem BELONGS_TO Policy        ISSUED_BY   （颁发机构）
  Product LOCATED_IN Location         HAS_PROPERTY（属性关系）
                                      HAS_LEVEL   （等级关系）
                                      HAS_CLASS   （分类关系）
                                      LOCATED_AT  （位置关系）
```

---

## 质量控制对比

```
【旧版】                                【新版】

┌────────────────────────┐            ┌────────────────────────────────┐
│ 手写 Cypher 逐个查      │            │      4 套自动门禁 ✔              │
│                        │            │                                │
│ MATCH (n) RETURN n     │            │ smoke 15/15  → 基础烟雾测试     │
│ MATCH (d:Doc) RETURN d │            │ quality 47/47 → 50题扩展评测    │
│                        │            │ csa 6/6      → 结构化路由校验   │
│ 全靠人眼扫结果找问题     │            │ semantic 6/6  → 语义图谱覆盖    │
│ 复盘了才去执行 cleanup  │            │                                │
│ 没有评测数据留存         │            │ 自动生成 eval/query_traces.jsonl│
│                        │            │ 每次问答都留 trace              │
│ 导入后不校验质量         │            │                                │
│                        │            │ 导入/迁移后必须跑:              │
│                        │            │   check_index_freshness.py     │
│                        │            │   eval_route_policy.py         │
│                        │            │   eval_health_gate.py          │
│                        │            │                                │
│                        │            │ 定期审计:                       │
│                        │            │   audit_kg_noise.py            │
│                        │            │   gap_scan.py (盲区分析)        │
└────────────────────────┘            └────────────────────────────────┘
```

---

## 目录结构对比

```
【旧版】                                【新版】

knowledge-graph/                      knowledge-graph/
├── pipeline/                          ├── pipeline/          ← 核心流水线（精简到16个活跃脚本）
│   ├── online_extract.py     当前     │   ├── server.py      ★ 统一 API 入口
│   ├── sync.py              废弃     │   ├── extract_one.py  ★ 单文件抽取
│   ├── scan_feishu.py       废弃     │   └── _legacy/        (28个废弃脚本都在这)
│   ├── fast_extract.py      废弃     │
│   ├── fix_*                 等     ├── rag_store/          ★ NEW 检索核心库
│   ├── retry_*               /      │   ├── route_policy.py   路由策略
│   ├── kg_extract.py        共     │   ├── csa_router.py     CSA 路由
│   ├── run.py              28     │   ├── kg_recall.py      KG 召回
│   ├── optimize.py         个     │   ├── dense_index.py    Dense 向量检索
│   └── ...                        │   ├── bm25_index.py     BM25 检索
│                                   │   ├── merge_rerank.py  融合重排
│   └── 56个Document 躺在 neo4j      │   ├── context_builder.py 上下文组装
│                                   │   ├── query_rewrite.py  查询改写
│                                   │   ├── sqlite_store.py  SQLite 存储
│                                   │   ├── semantic_schema.py 语义契约
│                                   │   ├── remote_shadow.py  远端影子
│                                   │   └── index_freshness.py 新鲜度检查
│                                   ├── rag_index/           ★ NEW 索引持久化
│                                   │   ├── dense_bge_m3.sqlite  11M
│                                   │   ├── bm25/               7M
│                                   │   └── csa_cache.sqlite    1.3M
│                                   ├── scripts/              ★ NEW 治理工具集 (24个)
│                                   │   ├── build_ingest_manifest.py
│                                   │   ├── eval_health_gate.py
│                                   │   ├── check_index_freshness.py
│                                   │   ├── dedupe_kg_relationships.py
│                                   │   └── ...
│                                   ├── eval/                ★ NEW 评测体系 (47文件)
│                                   ├── sync_packages/       ★ NEW 分域同步包
│                                   └── remote_replay/       ★ NEW 远端回放验证
```

---

## 一张表总结

| 维度 | 旧版（v2.4） | 新版（v2.7） | 提升 |
|------|:----------:|:----------:|:----:|
| **Neo4j 节点** | ~1,913 | **5,730** | **3x** |
| **Neo4j 关系** | ~381k | **391k** | +2.7% |
| **正文存储** | Neo4j description | **SQLite rag_chunks.db** | ✅ 分离 |
| **索引** | 无 | **Dense + BM25 + CSA** | ✅ 新增 |
| **路由** | 单路 MATCH 硬查 | **CSA → graph-first → RAG/hybrid** | ✅ 智能 |
| **关系精确度** | 64% BELONGS_TO | **SUBCLASS_OF/PART_OF** 等精确关系 | ✅ 提升 |
| **实体标签** | 单一 `:Entity` | **双标签 `:KnowledgePoint:Entity`** | ✅ 可按类型查 |
| **结构化数据** | 混在 Neo4j 里 | **CSV → canonical → cache** 三分层 | ✅ 解耦 |
| **质量门禁** | 无 | **smoke/quality/csa/semantic 4 套** | ✅ 自动化 |
| **评测数据留存** | 无 | **eval/query_traces.jsonl** | ✅ 可追溯 |
| **知识盲区** | 未排查 | **26个补充，覆盖度 83%→96%** | ✅ 提升 |
| **远端同步** | 无 | **3域增量包 + remote_replay** | ✅ 新增 |
| **活跃脚本数** | ~28 个废弃混在一起 | **16个精简 + 24个治理脚本** | ✅ 工程化 |
