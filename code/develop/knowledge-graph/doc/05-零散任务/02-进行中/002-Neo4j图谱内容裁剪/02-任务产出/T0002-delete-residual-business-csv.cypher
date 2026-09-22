// T0002 residual business CSV cleanup.
// Deletes remaining business-oriented CSV imports that are outside the requested keep scope.
// Kept policy Course nodes are sourced from policy documents, not from these CSV files.

MATCH (n)
WHERE n.source_doc IS NOT NULL
WITH n,
     CASE
       WHEN valueType(n.source_doc) STARTS WITH 'LIST'
       THEN n.source_doc
       ELSE [toString(n.source_doc)]
     END AS docs
WHERE any(doc IN docs WHERE doc IN [
  'courses.csv',
  'training_tracks.csv',
  'instructors.csv',
  'question_banks.csv',
  'documents.csv'
])
WITH collect(DISTINCT n) AS nodes, count(DISTINCT n) AS deletedNodes
UNWIND nodes AS n
DETACH DELETE n
RETURN deletedNodes;
