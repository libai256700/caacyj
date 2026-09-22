# AC-CAREER-ASSESS-101 分类14平行接口与分类13兼容

- 类型：技术-接口级
- 正式入口：既有分类13无参 completed、latest-status（或当前真实latest入口）、reset、start、session question/answers、record/report/regenerate 接口，以及新增分类14平行调用。
- 支撑业务结果：分类13旧开始和报告入口完全不变；分类14的状态、答题和报告只作用于分类14。
- 技术边界：分类13旧路径、旧请求参数、响应结构和无参语义保持，尤其旧无参latest仍只返回分类13原结果；分类14使用专用方法或显式 `categoryId=14`。答案接口只在最后一步调用。record、result、catalogBatch和当前用户必须一致；所有步骤详情、按步骤取题、题目反查步骤和 `step_id` 关联同时以目标 `categoryId` 校验，禁止只按 `stepId` 命中。分类14提交入口必须把固定题序原始答案重建为 `mode=self/formVersion=2`，并仅按源schema区分必答与选填校验；不得落入分类13通用“答案不能为空”分支，也不得把分类14选填题误判为分类13必答。分类14报告生成失败时必须返回明确 FAILED/failureReason，不得让前端一直停留在“生成中”。分类14报告页读取已存在报告时必须走职业报告轻量入口，只返回 `id/assessmentTime/assessmentReportStatus/assessmentReportFailureReason/selfReportContent` 等价字段且不返回 `answers`；本人记录、分类14和完成态校验以及三态/重试语义保持。
- 通过条件：分类13 completed/latest-status/reset/start/record/report/regenerate 基线请求和响应逐项一致；分类14缺失/非法分类、跨分类record、跨分类步骤/题目关联、非本人记录、源必答缺失、Top3非三项或least重叠均被分类14专属校验拒绝；分类14选填题允许按源 schema 正常为空，不应因为空值触发分类13必填错误；分类14题序14-25组页按同分类数据正常返回且不新增翻页即提交接口调用；分类14对应平行调用不影响分类13；分类14报告失败可被服务端与前端终止等待并展示失败原因。职业报告轻量入口对 `PENDING/SUCCESS/FAILED` 返回页面所需字段，不加载题目统计和答案详情，连续三次查询应相对修复前 `6.69s/13.9s` 基线显著下降。
- 证据承接：Controller/API自动化测试、服务层目标测试、前端网络请求快照和两分类交叉矩阵。
- 当前状态：待执行。
