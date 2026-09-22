MATCH (n {name: 'BEC'}) RETURN n.name, n.description LIMIT 1;
MATCH (n {name: '中空飞行'}) RETURN n.name, n.description LIMIT 1;
MATCH (n {name: 'CCA61部'}) RETURN n.name, n.description LIMIT 1;
MATCH (n {name: '无人机信号失联后的应急处置流程'}) RETURN n.name, left(n.description, 80) AS desc LIMIT 1;
