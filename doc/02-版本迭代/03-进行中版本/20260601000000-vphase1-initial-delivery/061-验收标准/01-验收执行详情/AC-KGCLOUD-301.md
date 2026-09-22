# AC-KGCLOUD-301 生产部署变更边界

- 类型：技术-代码级
- 正式入口：`knowledge-qa-final-delivery-linux-x86_64-20260905-r2.zip`、部署清单、release/candidate/config 路径和服务单元。
- 支撑的业务结果：生产运行内容与审核过的交付物完全一致，不夹带本地脏文件、旧派生层或敏感配置。
- 技术边界：不从源码临时构建上线，不手改 Release 数据/索引/manifest，不覆盖旧版根目录，不提交 secret、运行配置或临时文件，不修改 `uni_modules/**`。
- 通过条件：上传包 SHA 与本地一致；远端解压清单与 SHA256SUMS 一致；变更文件全部在批准路径；旧版保留且可回退；无禁区改动。
- 证据承接方式：上传前后 SHA、远端文件清单、权限、部署差异、Git 检查与服务单元摘要。

## 验收结果

- 状态：进行中，未通过完整验收。
- 已有证据：仅上传精确 final delivery 到 `/srv/knowledge-qa/incoming/` 并解压到独立 `/srv/knowledge-qa/releases/`；本地/远端包 SHA-256 一致，解压树无符号链接，未修改 Release 字节。formal wheelhouse 与目标 venv 均位于 suite 外批准路径，venv 通过外部 bootstrap installer 仅离线安装 exact 17 项，未写入 Release。
- 变更边界：未覆盖 `/home/soft/knowledge-graph` 旧版代码或活动 store；Neo4j 仅执行获批短暂停机的一致性 dump 后恢复原容器，未导入 candidate；未修改 Nginx、Java、5001 或 `uni_modules/**`；未把任何 secret 值写入文档。
- 未满足：Community import/runtime 账户隔离方案、provider Stop B approval、服务单元、候选启动、切换和回滚命令尚未执行；完整 AC 仍需后续独立验收。
- 证据入口：`../03-测试验证/TASK-027/02-release-staging-and-runtime.md`、`../03-测试验证/TASK-027/04-wheelhouse-venv-usearch.md`、`../03-测试验证/TASK-027/05-neo4j-consistency-backup.md`。
