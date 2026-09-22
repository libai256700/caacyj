# TASK-008 真实 staging 题库载荷生成说明

## 生成方法

- `docx` 文件：直接读取 `word/document.xml`，按题号、选项、参考答案、解析做规则化抽取。
- `无人机教员题库.doc`：该文件实际是 `mht` 导出内容，先解 base64 HTML，再按同一规则抽取。
- 输出严格对齐 `yk_question_import_staging` / `yk_question_import_option_staging` 的当前字段契约。
- `综合问答` 与 `无人机教员题库` 按 baseline 默认落 `needs_manual_review`，不伪造成可直接导入的 `parsed`。

## 统计结果

- baseline 目标题数：1512
- 实际生成 question staging 行数：1475
- 实际生成 option staging 行数：3431
- parsed：1113
- needs_manual_review：362
- ignored_noise：0
- manual review 比例：24.54%

## 分类统计

| category_code | expected | actual | parsed | needs_manual_review | gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| overview | 58 | 58 | 53 | 5 | 0 |
| system_components | 148 | 148 | 148 | 0 | 0 |
| air_traffic_control | 37 | 37 | 37 | 0 | 0 |
| flight_manual_and_regulations | 130 | 93 | 92 | 1 | -37 |
| operation_precautions | 79 | 79 | 77 | 2 | 0 |
| meteorology | 255 | 255 | 255 | 0 | 0 |
| rotary_uav | 77 | 77 | 77 | 0 | 0 |
| mission_planning | 74 | 74 | 74 | 0 | 0 |
| flight_principles_and_performance | 300 | 300 | 300 | 0 | 0 |
| comprehensive_qa | 199 | 199 | 0 | 199 | 0 |
| instructor_question_bank | 155 | 155 | 0 | 155 | 0 |

## 已知难点

- baseline 1512 题与当前原始文档实际抽取题数存在明显缺口；当前载荷忠实反映原始材料，不补造缺失题。
- `题库比例.xls` 未参与本轮解析，仅作为 baseline 对照线索；本机缺少旧版 `xls` 解析依赖。
- `无人机教员题库.doc` 不是传统二进制 Word，而是 `mht` 导出体；已按真实内容解析，但整类仍保持 `needs_manual_review`。

## 结论

- 当前结果已经补齐 11 个正式分类的真实 staging 入口。
- 当前结果可以支撑下一步测试库做真实 from-staging 导入链路验证，但不能宣称已经满足 baseline 1512 题全量导入。
- 如果后续必须达到 1512 全量，需要补齐缺失来源或确认 `题库比例.xls` 是否只是配额口径而非完整题面来源。
