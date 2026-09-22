-- ============================================
-- 脚本类型：dml
-- 脚本描述：灌入我的页测试联调账号及聚合展示样例数据
-- 创建日期：2026-05-13 05:06:20
-- 作者：Codex
-- 影响范围：yunjikeji 测试库我的页联调样例数据
-- 执行环境：测试环境
-- ============================================

-- 前置检查：确保基础账号表与我的页专用表已创建
INSERT INTO yk_user_account (mobile, nickname, avatar_url, status)
VALUES ('13800138000', '飞行学员', '', 'active')
ON DUPLICATE KEY UPDATE
    nickname = VALUES(nickname),
    avatar_url = VALUES(avatar_url),
    status = VALUES(status);

INSERT INTO yk_user_profile (user_id, avatar_url, student_no, school_name, major_name, role_label, training_direction)
SELECT id, '/static/profile/avatar-fy.png', 'FY20240001', '云技科技飞行学院', '无人机应用技术（航拍测绘方向）', '学员', '多旋翼机型'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    avatar_url = VALUES(avatar_url),
    student_no = VALUES(student_no),
    school_name = VALUES(school_name),
    major_name = VALUES(major_name),
    role_label = VALUES(role_label),
    training_direction = VALUES(training_direction);

INSERT INTO yk_learning_profile (user_id, course_total, practice_total, learning_progress, current_course_title, current_course_progress, continue_days)
SELECT id, 18, 256, 78, '无人机飞行原理与操控', 66, 12
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    course_total = VALUES(course_total),
    practice_total = VALUES(practice_total),
    learning_progress = VALUES(learning_progress),
    current_course_title = VALUES(current_course_title),
    current_course_progress = VALUES(current_course_progress),
    continue_days = VALUES(continue_days);

INSERT INTO yk_resume_profile (user_id, resume_status, completion_percent, suggestion_count, latest_note)
SELECT id, '简历已完善', 86, 2, '完整简历可提升投递成功率'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    resume_status = VALUES(resume_status),
    completion_percent = VALUES(completion_percent),
    suggestion_count = VALUES(suggestion_count),
    latest_note = VALUES(latest_note);

DELETE FROM yk_job_application_record
WHERE user_id IN (SELECT id FROM yk_user_account WHERE mobile = '13800138000');

DELETE FROM yk_interview_schedule
WHERE user_id IN (SELECT id FROM yk_user_account WHERE mobile = '13800138000');

INSERT INTO yk_job_application_record (user_id, company_name, position_name, application_status, applied_at, note)
SELECT id, 'XX科技', '无人机巡检工程师', 'applying', '2026-05-11 09:00:00', '查看了岗位的基础要求'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    application_status = VALUES(application_status),
    note = VALUES(note);

INSERT INTO yk_job_application_record (user_id, company_name, position_name, application_status, applied_at, note)
SELECT id, '云测智能', '航测助理', 'interviewing', '2026-05-10 14:30:00', '等待面试安排'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    application_status = VALUES(application_status),
    note = VALUES(note);

INSERT INTO yk_job_application_record (user_id, company_name, position_name, application_status, applied_at, note)
SELECT id, '星航教育', '教学助理', 'offer', '2026-05-08 10:30:00', '已收到录用意向'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    application_status = VALUES(application_status),
    note = VALUES(note);

INSERT INTO yk_job_application_record (user_id, company_name, position_name, application_status, applied_at, note)
SELECT id, '飞翼科技', '巡检实习生', 'rejected', '2026-05-06 16:00:00', '待优化岗位匹配'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    application_status = VALUES(application_status),
    note = VALUES(note);

INSERT INTO yk_job_application_record (user_id, company_name, position_name, application_status, applied_at, note)
SELECT id, '航测云图', '数据标注专员', 'applying', '2026-05-12 11:20:00', '已完成初步投递'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    application_status = VALUES(application_status),
    note = VALUES(note);

INSERT INTO yk_interview_schedule (user_id, company_name, position_name, interview_status, interview_time, note)
SELECT id, 'XX科技', '无人机巡检工程师', 'scheduled', '2026-05-14 15:00:00', '视频面试'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    interview_status = VALUES(interview_status),
    note = VALUES(note);

INSERT INTO yk_interview_schedule (user_id, company_name, position_name, interview_status, interview_time, note)
SELECT id, '云测智能', '航测助理', 'scheduled', '2026-05-15 09:30:00', '现场面试'
FROM yk_user_account
WHERE mobile = '13800138000'
ON DUPLICATE KEY UPDATE
    interview_status = VALUES(interview_status),
    note = VALUES(note);

-- 后置校验：我的页联调用样例数据应可稳定查询到
SELECT
    a.mobile,
    p.student_no,
    l.course_total,
    r.resume_status,
    COUNT(DISTINCT j.id) AS application_total,
    COUNT(DISTINCT i.id) AS interview_total
FROM yk_user_account a
JOIN yk_user_profile p ON p.user_id = a.id
JOIN yk_learning_profile l ON l.user_id = a.id
JOIN yk_resume_profile r ON r.user_id = a.id
LEFT JOIN yk_job_application_record j ON j.user_id = a.id
LEFT JOIN yk_interview_schedule i ON i.user_id = a.id
WHERE a.mobile = '13800138000'
GROUP BY a.mobile, p.student_no, l.course_total, r.resume_status;
