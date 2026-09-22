-- TASK-008 practice page question category seed
-- Seed the 11 formal question bank categories.
-- Target database: yunjikeji

INSERT INTO yk_question_category (
    category_code,
    category_name,
    sort_no,
    status,
    description
) VALUES
    ('overview', '概述', 10, 'online', 'builtin category: overview'),
    ('system_components', '系统组成及介绍', 20, 'online', 'builtin category: system_components'),
    ('air_traffic_control', '空中交通管制', 30, 'online', 'builtin category: air_traffic_control'),
    ('flight_manual_and_regulations', '无人机飞行手册、法律法规及其他', 40, 'online', 'builtin category: flight_manual_and_regulations'),
    ('operation_precautions', '无人机操作注意事项', 50, 'online', 'builtin category: operation_precautions'),
    ('meteorology', '气象', 60, 'online', 'builtin category: meteorology'),
    ('rotary_uav', '旋翼无人机', 70, 'online', 'builtin category: rotary_uav'),
    ('mission_planning', '无人机任务规划', 80, 'online', 'builtin category: mission_planning'),
    ('flight_principles_and_performance', '飞行原理与飞行性能', 90, 'online', 'builtin category: flight_principles_and_performance'),
    ('comprehensive_qa', '综合问答', 100, 'online', 'builtin category: comprehensive_qa'),
    ('instructor_question_bank', '无人机教员题库', 110, 'online', 'builtin category: instructor_question_bank')
ON DUPLICATE KEY UPDATE
    category_name = VALUES(category_name),
    sort_no = VALUES(sort_no),
    status = VALUES(status),
    description = VALUES(description);
