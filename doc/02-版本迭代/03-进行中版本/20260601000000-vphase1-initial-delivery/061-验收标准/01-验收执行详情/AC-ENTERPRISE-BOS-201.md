# AC-ENTERPRISE-BOS-201 BOS 配置与附件数据承接

- 类型：技术-数据级
- 正式入口：`application.yaml` 的 `huiyitech.bos.baidu` 配置段、企业审核附件 `file_path`。
- 支撑结果：恢复百度 BOS 配置结构与默认语义，企业附件保存真实 BOS URL。
- 技术边界：AK/SK 不得写入 Git；仅允许通过 `BAIDU_BOS_ACCESS_KEY_ID`、`BAIDU_BOS_SECRET_ACCESS_KEY` 等环境变量注入；当前本地不改数据库、不写入生产数据。
- 通过条件：配置结构覆盖 `enabled / access-key-id / secret-access-key / endpoint / bucket-name / prefix-root`；endpoint 默认 `bj.bcebos.com`、bucket 默认 `yunjikeji`；企业上传失败时不产生七牛示例 URL。
- 证据承接：配置差异审计、源码结果、测试环境真实审核附件记录。
