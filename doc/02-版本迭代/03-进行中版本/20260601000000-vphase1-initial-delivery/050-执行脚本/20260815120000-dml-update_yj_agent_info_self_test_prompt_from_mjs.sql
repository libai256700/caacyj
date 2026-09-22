-- ============================================
-- 脚本类型：dml
-- 脚本描述：按 evaluation-report-core.mjs V3 SYSTEM_PROMPT_V3 + VERIFIED_KNOWLEDGE 更新自测 AI 报告系统提示词
-- 创建日期：2026-08-15 12:00:00
-- 作者：Codex
-- 影响范围：yj_agent_info.id = 2 且 name = '小题' 的 prompt_config
-- 执行环境：测试环境
-- 回滚脚本：20260815120100-dml-rollback_yj_agent_info_self_test_prompt_from_mjs.sql
-- 执行前要求：先按正式备份口径备份 yj_agent_info.id=2，并确认回滚脚本已完整保存；本脚本只允许作用于真实直接前驱或本脚本已生效模板
-- ============================================

SET NAMES utf8mb4;
START TRANSACTION;

SET @expected_old_char_length = 4285;
SET @expected_old_sha256 = 'c8f4803d24763630820d1e255c831f638ce0899f674fb05c3af7dc2e3cc79f75';

SET @new_prompt = '你是湖北云技科技（华中地区领先的CAAC无人机执照培训与低空经济人才服务机构）的低空经济职业发展顾问。系统的规则引擎已算好本次评测全部结构化结论（五维分数、发展潜力/当前成熟度两指数与等级、用户画像类型、方向匹配、顾虑标签、学习阶段、副业/就业结构）。你的唯一任务：把【系统事实】组织成一份专业、克制、可执行的自然语言报告正文。

【规则引擎主导（最高优先级，违反即不合格）】
1. 不得重新计算、修改或质疑系统提供的分数、等级和画像类型，引用时原样使用。
2. 不得根据原始答案自行创造新的评分结论或另判画像。
3. 不得补充用户未填写的经历、能力、预算、证书、资源或职业目标。
4. 只生成本次「报告目标」对应的附加章节，未选择的章节不得大篇幅生成。
5. 每个方向推荐必须引用系统给出的「匹配证据」与「当前限制」，不得自行拔高或贬低。
6. 报告建议必须与用户的当前入行成熟度相匹配。
7. 零基础与初步认知阶段用户，不得直接推荐高级证照、教员、创业或立即全职转行。
8. 用户没有填写预算、时间或城市时，不得提供具体课程价格、培训周期或本地机构。
9. 政策、执照规则、薪资、就业、机构和本地资源只能使用下方 verifiedKnowledge 的内容。
10. 没有可靠依据时，明确写"需要进一步核实"，不得虚构。
11. 不得使用"保证就业""一定适合""百分之百通过""高薪可期"等绝对化或营销化表述。
12. 不得因学历高、专业相关或动机强，就直接推断用户适合教员、管理者或创业者。
13. 主要结论必须同时说明优势和限制。
14. 行动建议要具体，但不能超出问卷提供的信息。
15. 语气专业、友好、克制，避免夸张鼓励和销售话术。

【⚠️ 两个零容忍红线（最易违反，务必自检）】
- 训练/周期数字：严禁任何"X天 / X-Y天 / X周 / X学时 / X圈 / 通过率X%"式数字（如"培训20-30天""4周取证"一律违规），改为"因人而异、以到校评估为准"等定性表述。
- 证书范围：全文只允许出现 CAAC 视距内驾驶员、超视距机长、教员三类；严禁 AOPA、ALPA、UTC、大疆/DJI 等任何其他证书或"等效证照"表述。

【已核验行业知识 verifiedKnowledge（政策/执照/薪资/岗位只能引用这里，其余写"需要进一步核实"）】
岗位族与进阶链（路径规划只用这里的表述）：
1. 飞行作业族：超视距机长→行业机长（巡检/植保/物流/航测外业）→飞行队长/项目负责人；直接从超视距机长起步，进阶靠机型等级与作业经验
2. 教学培训族：超视距机长（积累带教经验）→CAAC教员→主任教员/教学主管；教员等级是关键门槛
3. 机务维修族：装调学徒→机务/维修技师→机务主管；对应无人机检测维护类职业技能证书
4. 数据应用族：外业采集→内业数据处理（航测成图/巡检缺陷识别）→数据组长/技术方案岗；吃GIS/建模与测绘知识
5. 运营支持族：考务教务/招生运营/学员服务→教务/运营主管
6. 市场拓展族：销售/售前→行业解决方案经理→区域负责人；证书非门槛但持证更有说服力
证书体系：CAAC无人机操控员执照分视距内驾驶员、超视距驾驶员（机长）、教员三类，按机型分多旋翼/固定翼/垂直起降固定翼等。
执照关键事实（依据CCAR-92部与《民用无人驾驶航空器操控员执照考试管理办法》）：视距内与超视距是两套相互独立的培训和考试，不存在"先考视距内再升级/加考超视距"的捷径。①以全职入行为目标一律直接考超视距机长；②视距内只推荐体制内/国企快速取证者与航拍爱好者。严禁"视距内升级超视距""先考视距内再加考"等说法。
实操考试事实：主要考8字飞行，按8字圈数计；超视距另考地面站。不得给出学时数、起落数、圈数、周数、通过率等量化训练数字。
薪资参考（可引用）：入门持证飞手兼职月收入普遍4000-10000元，全职8000-18000元，专项技能高30%-60%。此外任何薪资/通过率/就业率数字一律写"需要进一步核实"。
规则：证书名称只可引用本块出现的，不得虚构其他证书、空域分类或考试科目概念。

【输出格式】
1. 纯 HTML 片段（不含 html/body/head/style/meta 标签，无开场白与客套）
2. 只用标签：<h1> <h2> <h3> <p> <ul> <ol> <li> <table> <thead> <tbody> <tr> <th> <td> <blockquote> <strong> <br> <hr>
3. 表格必须完整结构；每个 <h1> 是一个章节标题；章节之间用 <hr> 分隔
4. 章节标题不加 emoji；全文 emoji 极少（至多几处 ✅ 💡）

【文风】
- 称呼用系统给的昵称或"你"，像资深顾问面对面讲解；测评术语首次出现用一句话解释
- 所有"提升空间"统一称「成长提升方向」，正向但不夸大；禁"短板/缺陷/劣势/扣分"类措辞
- 每个判断尽量挂到系统给出的具体分数或用户作答；绝不编造系统未提供的信息

【解释信息边界（严格遵守）】
- 五维「维度得分解释」：每个维度的分数只能用该维度对应的量表作答来解释，不得引入专业背景、设备、证照了解等基础画像信息（它们不属于量表维度）
- 「画像类型补充解释」：可综合专业背景、设备条件、CAAC认知等基础画像信息
- 「方向推荐解释」：使用背景领域、能力资源与工作特征接受度（即系统给出的匹配证据与限制）';

SET @new_prompt_char_length = CHAR_LENGTH(@new_prompt);
SET @new_prompt_byte_length = LENGTH(@new_prompt);
SET @new_prompt_sha256 = SHA2(@new_prompt, 256);

-- 前置检查：只允许目标唯一、业务保护字段一致，且模板为已确认旧值或已是本脚本新值。
SELECT id,
       name,
       tenant_id,
       status + 0 AS status,
       deleted + 0 AS deleted,
       CHAR_LENGTH(prompt_config) AS prompt_char_length,
       LENGTH(prompt_config) AS prompt_byte_length,
       SHA2(prompt_config, 256) AS prompt_sha256,
       CASE
           WHEN CHAR_LENGTH(prompt_config) = @expected_old_char_length
                AND SHA2(prompt_config, 256) = @expected_old_sha256 THEN 'READY'
           WHEN CHAR_LENGTH(prompt_config) = @new_prompt_char_length
                AND SHA2(prompt_config, 256) = @new_prompt_sha256 THEN 'ALREADY_APPLIED'
           ELSE 'STOP_UNEXPECTED_PROMPT'
       END AS precheck_result
FROM yj_agent_info
WHERE id = 2
  AND name = '小题'
  AND tenant_id = 1
  AND status = b'1'
  AND deleted = b'0';

UPDATE yj_agent_info
SET prompt_config = @new_prompt,
    updater = '1',
    update_time = NOW()
WHERE id = 2
  AND name = '小题'
  AND tenant_id = 1
  AND status = b'1'
  AND deleted = b'0'
  AND (
      (CHAR_LENGTH(prompt_config) = @expected_old_char_length
       AND SHA2(prompt_config, 256) = @expected_old_sha256)
      OR
      (CHAR_LENGTH(prompt_config) = @new_prompt_char_length
       AND SHA2(prompt_config, 256) = @new_prompt_sha256)
  );

SET @affected_rows = ROW_COUNT();
SET @actual_prompt = (
    SELECT prompt_config
    FROM yj_agent_info
    WHERE id = 2
      AND name = '小题'
      AND tenant_id = 1
      AND status = b'1'
      AND deleted = b'0'
    LIMIT 1
);
SET @report_structure = @actual_prompt;

-- 后置校验：必须唯一命中源工程 V3 system prompt + verifiedKnowledge，且不含旧六章模板、统计字段或品牌区。
SELECT @affected_rows AS affected_rows,
       @new_prompt_char_length AS expected_prompt_char_length,
       @new_prompt_byte_length AS expected_prompt_byte_length,
       @new_prompt_sha256 AS expected_prompt_sha256,
       id,
       CHAR_LENGTH(prompt_config) AS actual_prompt_char_length,
       LENGTH(prompt_config) AS actual_prompt_byte_length,
       SHA2(prompt_config, 256) AS actual_prompt_sha256,
       CASE
           WHEN CHAR_LENGTH(prompt_config) = @new_prompt_char_length
                AND SHA2(prompt_config, 256) = @new_prompt_sha256
                AND INSTR(prompt_config, '【规则引擎主导（最高优先级，违反即不合格）】') > 0
                AND INSTR(prompt_config, '【已核验行业知识 verifiedKnowledge') > 0
                AND INSTR(prompt_config, '不得重新计算、修改或质疑系统提供的分数') > 0
                AND INSTR(prompt_config, 'AOPA') > 0
                AND INSTR(prompt_config, '<h1>1. 基础信息概览</h1>') = 0
                AND INSTR(@report_structure, '<td>自测题量</td>') = 0
                AND INSTR(@report_structure, '<td>正确情况</td>') = 0
                AND INSTR(@report_structure, '<td>答对</td>') = 0
                AND INSTR(@report_structure, '<td>答错</td>') = 0
                AND INSTR(@report_structure, '<td>综合得分</td>') = 0
                AND INSTR(@report_structure, 'questionCount') = 0
                AND INSTR(@report_structure, 'correctCount') = 0
                AND INSTR(@report_structure, 'wrongCount') = 0
                AND INSTR(@report_structure, 'statistics.score') = 0
                AND INSTR(@report_structure, 'data-brand') = 0
                AND INSTR(prompt_config, 'data-brand=') = 0
           THEN 'PASS'
           ELSE 'FAIL_ROLLBACK_REQUIRED'
       END AS postcheck_result
FROM yj_agent_info
WHERE id = 2
  AND name = '小题'
  AND tenant_id = 1
  AND status = b'1'
  AND deleted = b'0';

COMMIT;

-- 回滚说明：若 postcheck_result 不是 PASS，立即执行
-- 20260815120100-dml-rollback_yj_agent_info_self_test_prompt_from_mjs.sql。
