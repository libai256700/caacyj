# KG Noise Audit

- Created: 2026-06-12T22:30:34
- Nodes: 5903
- Entities: 5850
- Relationships: 153269
- Relationships per entity: 26.2
- Chunk nodes: 0

## Recommendations
- 存在重复同类型边；可做去重脚本，但先确认关系属性是否有业务差异。
- 先把本报告纳入评测观察，不建议直接删边；下一步优先在 KG recall 层做 relation cap/weight。

## Top Relationship Types
- PART_OF: 54307
- DEFINED_BY: 27352
- REQUIRES: 14058
- MENTIONS: 9055
- REGULATES: 8226
- REFERS_TO: 7065
- DESCRIBES: 5246
- OFFERS: 4974
- REQUIRES_SKILL: 4657
- CONTAINS: 4162
- HAS_PROPERTY: 3625
- AFFECTS: 3074
- BELONGS_TO: 2702
- ISSUED_BY: 2416
- HAS_CLASS: 2339
- LOCATED_AT: 11

## High-Degree Nodes
- 第1章 航空器与无人机 | degree=1172 | type=Chapter | source=教材第1章
- 第2章 无人机的飞行原理及结构 | degree=1169 | type=Chapter | source=教材第2章
- 第3章 无人机的动力 | degree=1168 | type=Chapter | source=教材第3章
- 第4章 无人机飞控操作系统 | degree=1164 | type=Chapter | source=教材第4章
- 第5章 无人机通信 | degree=1164 | type=Chapter | source=教材第5章
- 第6章 无人机材料 | degree=1161 | type=Chapter | source=教材第6章
- 第8章 无人机与体育竞技 | degree=1156 | type=Chapter | source=教材第8章
- 第7章 任务载荷及应用场景 | degree=1142 | type=Chapter | source=教材第7章
- 第9章 反无人机方法 | degree=1141 | type=Chapter | source=教材第9章
- 湖北云技科技有限公司无人机执照培训项目客户管理与跟进制度 | degree=1062 | type=Policy | source=人事制度_湖北云技科技有限公司无人机执照培训项目客户管理与跟进制度.txt
- 设计教材·P4T3_固定翼结构设计（章节） | degree=964 | type=Chapter | source=设计教材·P4T3_固定翼结构设计
- 无人机任务规划（知识点） | degree=961 | type=KnowledgePoint | source=无人机任务规划
- 结构设计软件介绍 | degree=961 | type=Section | source=设计教材·P4T1_结构设计软件
- 无人机制作的准备 | degree=961 | type=Chapter | source=设计教材·P5T1_制作准备
- 空中交通管制（知识点） | degree=961 | type=KnowledgePoint | source=空中交通管制
- 设计准备 | degree=959 | type=Section | source=设计教材·P4T2_设计准备
- 固定翼无人机制作 | degree=957 | type=Section | source=设计教材·P5T2_固定翼制作
- 旋翼无人机（知识点） | degree=952 | type=KnowledgePoint | source=旋翼无人机
- 学习任务3 多旋翼无人机制作 | degree=947 | type=Chapter | source=设计教材·P5T3_多旋翼制作
- 无人机 | degree=937 | type=KnowledgePoint | source=概述

## Self-Loops
- none

## Duplicate Edges
- 湖北云技科技有限公司薪酬体系 -[AFFECTS]-> 无人机飞手 | count=22
- 无人机飞手 -[REQUIRES_SKILL]-> 无人机综合能力 | count=22
- 湖北云技科技有限公司 -[BELONGS_TO]-> 无人机飞手 | count=22
- 云技科技员工手册 -[AFFECTS]-> 无人机飞手 | count=22
- 湖北云技科技新员工面试及入职流程 -[AFFECTS]-> 无人机飞手 | count=22
- 云技科技新员工培训资料 -[AFFECTS]-> 无人机飞手 | count=22
- 湖北云技科技有限公司无人机执照培训项目客户管理与跟进制度 -[AFFECTS]-> 无人机飞手 | count=22
- 云技科技员工手册 -[AFFECTS]-> \*\*无人机飞手\*\* | count=12
- \*\*无人机飞手\*\* -[REQUIRES_SKILL]-> 无人机综合能力 | count=12
- 湖北云技科技有限公司 -[BELONGS_TO]-> \*\*无人机飞手\*\* | count=12
- 湖北云技科技有限公司无人机执照培训项目客户管理与跟进制度 -[AFFECTS]-> \*\*无人机飞手\*\* | count=11
- 湖北云技科技有限公司薪酬体系 -[AFFECTS]-> \*\*无人机飞手\*\* | count=11
- 湖北云技科技新员工面试及入职流程 -[AFFECTS]-> \*\*无人机飞手\*\* | count=11
- 云技科技新员工培训资料 -[AFFECTS]-> \*\*无人机飞手\*\* | count=11
- 私信 -[REFERS_TO]-> 多旋翼教员考证班 | count=6
- 私信 -[REFERS_TO]-> 装调检修班 | count=6
- 湖北云技科技有限公司无人机执照培训项目客户管理与跟进制度 -[AFFECTS]-> 私信 | count=6
- 私信 -[REFERS_TO]-> 垂起教员考证班 | count=6
- 概述 -[MENTIONS]-> 无人机综合能力 | count=5
- 旋翼无人机 -[MENTIONS]-> 多旋翼操控 | count=5
