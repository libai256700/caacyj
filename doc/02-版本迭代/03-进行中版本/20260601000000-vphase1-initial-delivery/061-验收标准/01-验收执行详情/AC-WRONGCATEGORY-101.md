# AC-WRONGCATEGORY-101 按分类启动错题批次接口契约

- 类型：技术-接口级
- 正式入口：`GET /app-api/yj/practices/current?mode=wrongReview` 与 `POST /app-api/yj/practices/{practiceId}/start?mode=wrongReview&topicId={categoryId}`。
- 支撑的业务结果：分类页展示真实练习分类，选择分类后创建仅含目标分类错题的真实批次并进入答题页。
- 技术边界：不新增或修改 service 与后端契约；前端必须传递真实 `mode`、`topicId`，并承接真实 `nextPage`、`sessionId` 及响应中存在的批次标识。
- 通过条件：启动请求携带所选分类 ID；答题请求沿用返回的 session；目标分类题目不混入其他分类；空分类返回既有“暂无错题可练习”反馈。
- 证据承接方式：浏览器网络/请求桩验证、现有后端契约测试与 `061-验收标准/03-测试验证/DEV-062/` 正式结果记录。
