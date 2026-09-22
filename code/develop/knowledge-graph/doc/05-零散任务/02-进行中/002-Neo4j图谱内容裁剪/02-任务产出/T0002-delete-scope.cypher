// T0002 Neo4j graph content trim
// Target: local container yunji-knowledge-graph, database neo4j.
// Scope: business labels and obvious Yunji/company source documents.

MATCH (n)
WITH n,
     [k IN [
       'name',
       'canonical_name',
       'source_doc',
       'doc_name',
       'canonical_doc_name',
       'path',
       'source',
       'source_csv',
       'source_table'
     ]
     WHERE n[k] IS NOT NULL |
       CASE
         WHEN valueType(n[k]) STARTS WITH 'LIST'
         THEN reduce(s = '', x IN n[k] | s + ' ' + toString(x))
         ELSE toString(n[k])
       END
     ] AS vals
WITH n, reduce(txt = '', v IN vals | txt + ' ' + v) AS txt
WHERE any(label IN labels(n) WHERE label IN ['Customer', 'Position', 'Company', 'Student'])
   OR txt =~ '(?s).*(云技科技|湖北云技|员工手册|新员工培训|新员工面试|入职流程|公司介绍|公司产品介绍|价格表|薪酬体系|客户管理与跟进制度|客户跟进制度|jobs\\.csv|customers\\.csv|学员信息\\.csv|价格表\\.csv|新员工培训课程表\\.csv|人事制度_|企业信息_).*'
WITH collect(DISTINCT n) AS nodes, count(DISTINCT n) AS deletedNodes
UNWIND nodes AS n
DETACH DELETE n
RETURN deletedNodes;
