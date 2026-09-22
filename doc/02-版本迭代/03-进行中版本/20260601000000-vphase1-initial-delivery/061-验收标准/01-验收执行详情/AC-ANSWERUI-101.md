# AC-ANSWERUI-101 最小源码与原创资产边界

- 类型：技术-代码级
- 正式入口：`code/develop/yunjikeji/src/pages/practice/answer.vue` 与 `code/develop/yunjikeji/src/static/practice-answer/person-map.svg`。
- 支撑的业务结果：真实答题页获得参考问卷视觉，同时服务契约、登录守卫、其他页面和三方包保持现状。
- 技术边界：应用源码只允许修改 `answer.vue` 并新增透明原创 SVG；禁止修改 `services/practice.ts`、backend、auth、center、首页、登录页、锁文件和 `uni_modules/**`；禁止嵌入或裁切参考图。
- 通过条件：白名单 diff 检查通过；原有 `fetchPracticeQuestion`、`submitPracticeAnswer`、`completePractice` 及答题状态流转关键调用仍存在；SVG 为可审查原生路径与图形构成。
- 证据承接：`061-验收标准/03-测试验证/DEV-038/`。

- 当前状态：已通过（独立验收）。
- 独立验收结果：DEV-038 应用源码白名单仅 `answer.vue` 与新增 `person-map.svg`；SVG 为可解析原生图形且 Canvas 像素非空，夹具标识未进入白名单源码，`uni_modules/**` 无差异。工作区其他并行任务差异未归入 DEV-038，验收未触碰。
