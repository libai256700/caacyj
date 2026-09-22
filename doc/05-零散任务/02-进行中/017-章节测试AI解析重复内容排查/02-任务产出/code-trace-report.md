# 章节测试 AI 解析代码链路排查报告

## 结论

静态代码检查未发现“章节测试中单次点击 AI 解析后必然把同一份正文渲染两次”的确定性证据。当前实际学员端链路在 AI 页面首次加载时只调用一次知识库查询，并把查询结果包装为一个 `知识库解答` section；模板在结构化 section 与纯文本流之间使用互斥分支，因此正常单次请求不会同时显示两份正文。

但存在一个可导致重复/串接内容的并发风险：AI 页的 `loadAiAnswer()` 调用前会尝试 abort，却没有创建新的 `AbortController`，而 `queryKnowledge()` 使用 `uni.request` 且没有取消信号。用户在首个查询尚未返回时触发重试，旧请求返回后仍会执行 `enqueueAiContent()`，可能把旧响应追加到新请求已重置的队列中。该风险需要运行态重复点击/网络延迟样本确认，不能仅凭静态代码认定线上已复现。

## 真实调用链

1. 章节测试主题页识别 `mode === 'chapter-test'`，点击主题后调用 `startChapterTestBatch(DEFAULT_PRACTICE_ID, selectedTopicId)`，然后跳转 `/pages/practice/exam-assessment`。证据：[exam-topics.vue:162](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/exam-topics.vue:162)、[exam-topics.vue:164](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/exam-topics.vue:164)、[practice.ts:917](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/services/practice.ts:917)。
2. 批次确认页调用 `/app-api/yj/practices/catalog-batches/{catalogBatchId}`，点击开始后把 `id/sessionId/recordId/catalogBatchId/mode` 等参数带到答题页。证据：[exam-assessment.vue:142](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/exam-assessment.vue:142)、[exam-assessment.vue:154](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/exam-assessment.vue:154)、[exam-assessment.vue:183](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/exam-assessment.vue:183)。
3. 答题页按 `mode` 加载单题；提交答案后保存 `answeredQuestionSnapshot`，并在结果卡提供“AI 深度解答”。证据：[answer.vue:474](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/answer.vue:474)、[answer.vue:484](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/answer.vue:484)、[answer.vue:120](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/answer.vue:120)。
4. 点击 AI 按钮时，答题页把题目、用户答案、正确答案按 `questionId` 写入本地缓存，再只导航一次 `/pages/practice/ai-answer`。证据：[answer.vue:532](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/answer.vue:532)、[answer.vue:536](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/answer.vue:536)、[answer.vue:541](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/answer.vue:541)。
5. AI 页 `onLoad` 读取 query 和缓存题目，然后调用 `loadAiAnswer()`；当前实现实际调用的是 `queryKnowledge(buildKnowledgeQuery())`，不是旧的 `/api/practices/.../ai-answer` 或 SSE 路径。证据：[ai-answer.vue:881](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:881)、[ai-answer.vue:894](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:894)、[ai-answer.vue:904](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:904)、[ai-answer.vue:822](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:822)。
6. `queryKnowledge()` 将问题截断到 1200 字后请求 `GET /app-api/yj/knowledge/query?q=...`；开发环境基地址默认为 `/yj-app-api`，生产环境为 `https://yunjikeji.lai-do.com/yunjikeji-admin-api`。证据：[practice.ts:865](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/services/practice.ts:865)、[practice.ts:870](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/services/practice.ts:871)、[apiBase.ts:27](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/services/apiBase.ts:27)。
7. 后端 APP 知识库控制器接收该 GET 请求，服务层将 `KnowledgeService.query()` 的 `finalAnswer` 映射到 `answer`，并同时返回 `knowledgeAnswer`。当前 `KnowledgeServiceImpl` 明确令 `finalAnswer = knowledgeAnswer`，所以响应数据中两个字段可能是同一文本，但前端 `normalizeKnowledgeQueryResult()` 只选第一个非空 `answer` 字段。证据：[FrontKnowledgeController.java:46](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/knowledge/controller/FrontKnowledgeController.java:46)、[FrontKnowledgeServiceImpl.java:28](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/knowledge/service/FrontKnowledgeServiceImpl.java:28)、[FrontKnowledgeServiceImpl.java:33](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/knowledge/service/FrontKnowledgeServiceImpl.java:33)、[KnowledgeServiceImpl.java:27](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/knowledge/service/KnowledgeServiceImpl.java:27)、[KnowledgeServiceImpl.java:32](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/knowledge/service/KnowledgeServiceImpl.java:32)、[practice.ts:485](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/services/practice.ts:485)。

## 重复内容判断

### 正常单次进入：未发现确定性重复渲染

- `buildKnowledgeAiAnswer()` 只构造一个 section，标题为 `知识库解答`，内容为查询返回的单个 `answer`。[ai-answer.vue:538](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:538)
- 查询返回后只调用一次 `enqueueAiContent(result.answer)`。[ai-answer.vue:821](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:821)、[ai-answer.vue:826](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:826)
- 模板的 `aiSectionItems` 与 `aiStreamText` 是 `v-if / v-else` 互斥关系，不会在同一状态同时显示 section 正文和纯文本正文。[ai-answer.vue:109](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:109)、[ai-answer.vue:138](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:138)
- 引用名称通过 `Set` 去重；同名来源不会重复显示。[ai-answer.vue:504](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:504)、[ai-answer.vue:513](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:513)

### 明确风险：重试并发会追加旧响应

- `loadAiAnswer()` 在开始时调用 `aiAbortController.value?.abort()`，但整个函数没有为该 ref 赋值新的 `AbortController`；`finally` 只是置空。[ai-answer.vue:816](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:816)、[ai-answer.vue:833](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:833)
- `queryKnowledge()` 底层是 `uni.request`，没有接收或传入取消信号，因此前一次请求即使逻辑上“abort”也会继续返回。[practice.ts:673](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/services/practice.ts:673)、[practice.ts:675](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/services/practice.ts:675)
- 每次重试只清空当前 `aiStreamQueue/aiStreamContent`，旧请求返回后仍执行 `aiAnswer.value = ...` 与 `enqueueAiContent(...)`；并发返回顺序不受保护。[ai-answer.vue:817](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:817)、[ai-answer.vue:822](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:822)、[ai-answer.vue:826](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:826)、[ai-answer.vue:639](/E:/huiyitechworkspace/feixingxueyuan/code/develop/yunjikeji/src/pages/practice/ai-answer.vue:639)

这条风险需要“首个知识库请求仍处于 pending 时点击重新加载”作为真实样本；当前没有浏览器 Network、请求时间线或页面截图，因此不能宣称已经在运行中复现。

## 未决点与建议取证

- TA-T0017-API-001：在测试环境从章节测试错答进入 AI 页，记录 `/app-api/yj/knowledge/query` 请求次数、完整脱敏 query、响应 `answer/knowledgeAnswer/sources` 字段；正常单次进入应为 1 次。
- TA-T0017-DATA-001：对同一响应比较 `answer` 与 `knowledgeAnswer`，确认是否同值；同时比较前端最终 `aiStreamContent` 和 section 内容，确认正文只出现一次。
- TA-T0017-CODE-001：静态检查已确认入口、状态、队列、渲染 key 和去重逻辑；重点保留上述并发风险，后续修复应增加请求代次或有效请求锁，并由独立验收代理复核。
- 本报告未运行浏览器、未调用生产接口、未修改业务代码，也未修改 `uni_modules/**`。
