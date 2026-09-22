# 业务本体 v1：图谱驱动 Hybrid RAG 的第一步

更新时间：2026-06-05

## 目标

这份本体用于把知识库从“文档切片检索”继续推进到“图谱驱动的 Hybrid RAG”。它先定义业务世界里的实体、关系、证据边界和第一批 graph-first 测试问题。

当前系统边界保持不变：

- `rag_chunks.db` 是权威正文来源，负责 `chunk_id -> text`。
- BM25 和 dense index 是文本召回层。
- Neo4j 是业务实体、关系、路径、`source_doc`、`source_chunk_ids` 的图谱推理层。
- 最终答案必须能回到 SQLite chunk 证据；图谱路径负责解释“为什么这些证据相关”。

## 第一步怎么做

第一步不是先写算法，而是先把业务本体固定下来。建议按这个顺序执行：

1. 确定核心业务域。
2. 给每个业务域列出实体类型。
3. 给实体之间定义关系。
4. 给每类关系绑定证据要求。
5. 写 5-10 个 graph-first 候选问题，作为后续评测集雏形。

本目录里的 [business_ontology.yaml](business_ontology.yaml) 是机器可读草案，后续可以被覆盖率脚本、graph-first 路由和 eval 读取。

## 核心业务域

| 业务域 | 作用 | 当前可对接数据 |
| --- | --- | --- |
| `company` | 公司介绍、组织结构、业务方向、制度 | `documents`, `document_chunks` |
| `course` | 课程产品、班型、价格、周期、能力目标 | `courses`, `training_tracks`, `documents` |
| `student` | 学员画像、训练状态、推荐上下文 | `students`, `training_tracks` |
| `customer` | 客资、咨询、需求、跟进 | `customers`, `customer_source_rows`, `courses` |
| `instructor` | 教员、可授课程、能力匹配 | `instructors`, `students`, `courses` |
| `job_market` | 岗位、职责、薪资、市场需求 | `jobs`, `job_occurrences` |
| `regulation` | 法规、规章、合规约束 | `regulations`, `documents`, `document_chunks` |
| `question_bank` | 题库、知识点、考试能力 | `question_banks`, `documents`, `document_chunks` |

## 核心实体

第一版不要追求特别复杂，先固定这些实体：

| 实体 | 含义 | 证据要求 |
| --- | --- | --- |
| `Company` | 公司或组织 | 来源文档或结构化表 |
| `Course` | 课程/培训产品 | 课程表、价格表、产品文档 |
| `TrainingTrack` | 班型/训练轨道 | 结构化课程或训练表 |
| `Student` | 学员 | 学员表 |
| `Customer` | 客户/线索 | 客资表 |
| `Instructor` | 教员 | 教员表、学员训练关联 |
| `Position` | 岗位 | 岗位表、招聘记录、公司文档 |
| `Regulation` | 法规/规章/条款 | 法规文档 chunk |
| `QuestionBank` | 题库 | 题库文档 chunk |
| `KnowledgePoint` | 知识点 | 题库、教材、法规或课程文档 |
| `Skill` | 能力项 | 岗位、课程、题库或法规证据 |
| `Policy` | 制度/流程 | 公司制度文档 chunk |
| `Document` | 文档 | 文档元数据 |
| `ChunkRef` | SQLite chunk 引用 | 必须能解析到 `rag_chunks.db` |

## 核心关系

| 关系 | 起点 | 终点 | 用途 |
| --- | --- | --- | --- |
| `OFFERS` | `Company` | `Course` | 公司提供哪些课程 |
| `HAS_PROPERTY` | `Course` | `Value` | 价格、周期、容量、等级等属性 |
| `REQUIRES` | `Course` | `Skill` | 课程需要或培养哪些能力 |
| `REQUIRES_SKILL` | `Position` | `Skill` | 岗位需要哪些能力 |
| `REGULATES` | `Regulation` | `Course` | 法规约束课程或训练行为 |
| `DEFINED_BY` | `Skill` | `Regulation` | 能力或知识点由哪些法规定义 |
| `MENTIONS` | `Document` | `KnowledgePoint` | 文档提到知识点 |
| `REFERS_TO` | `Customer` | `Course` | 客户需求关联课程 |
| `HAS_CLASS` | `Course` | `TrainingTrack` | 课程关联班型或训练轨道 |
| `BELONGS_TO` | `Position` | `Company` | 岗位属于公司/组织 |
| `AFFECTS` | `Policy` | `Position` | 制度影响岗位或流程 |
| `CONTAINS` | `Document` | `ChunkRef` | 文档包含权威 chunk 证据 |

## 第一批 graph-first 测试问题

这些问题不是普通文本检索题，而是用来验证图谱是否真的能连接业务实体和证据：

1. 某课程适合哪些客户？依据是什么？
2. 某学员下一步应该推荐什么课程？
3. 某岗位面试应该考察哪些能力？
4. 某课程涉及哪些法规要求和题库知识点？
5. 某教员能否承担某类培训？证据是什么？
6. 某价格是否和课程内容、客户类型匹配？
7. 某客户如果想做低空业务，应该走什么培训路径？
8. 某岗位需求如何反向影响课程设计？
9. 某知识点在哪些题库、教材、法规里同时出现？
10. 某业务动作是否有合规风险？依据是什么？

## 第一阶段完成标准

第一步做到位，不是看文档写得多漂亮，而是看后续能不能被检查：

- 每个业务域都有实体类型。
- 每个核心实体都有来源。
- 每条核心关系都有证据要求。
- 至少 5 个 graph-first 问题有预期路径。
- 后续脚本能根据本体统计实体覆盖率、关系覆盖率、孤岛节点和无证据关系。

## 下一步

下一步应该做“图谱覆盖率检查”：

1. 读取 `business_ontology.yaml`。
2. 查询 Neo4j 当前实体和关系数量。
3. 按业务域统计覆盖率。
4. 找孤岛节点、无 `source_doc` 关系、无 `source_chunk_ids` 关系。
5. 输出一份 `graph_coverage_report.json`。

做到这一步后，我们就能知道：图谱到底只是“有数据”，还是已经具备支撑业务推理的结构。
