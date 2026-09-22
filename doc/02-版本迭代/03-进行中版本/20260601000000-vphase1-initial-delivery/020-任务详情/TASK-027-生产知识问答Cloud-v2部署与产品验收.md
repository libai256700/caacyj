# TASK-027 生产知识问答 Cloud v2 部署与产品验收

## 实施标准

- 目标服务器为用户确认的生产节点 `106.13.71.85`；该节点已承接生产流量并运行旧版知识图谱工程。
- 先只读盘点旧服务的代码、进程/容器、端口、systemd/Compose、Nginx、Python、Neo4j、配置、数据、日志、磁盘和调用入口；未形成 exact pre-state 前不得上传、停止、覆盖、导入或切流。
- 部署前完整备份旧版代码、配置、启动单元、当前数据/索引和 Neo4j 可恢复快照，记录 SHA-256、路径和恢复命令；备份不可验证时停止。
- 仅使用 `knowledge-qa-final-delivery-linux-x86_64-20260905-r2.zip`，校验外层 SHA-256、包内 `SHA256SUMS` 并运行 `verify_final_delivery.py`；不得从源码目录临时拼包上线。
- 以 `/srv/knowledge-qa/releases/<exact-release-id>/`、suite 外 candidate/config/contract/runtime-lock 路径实施，安装锁定依赖并验证 `usearch==2.26.2`；不得覆盖 Release 内权威库、索引、manifest、SBOM、DLP 或测试证据。
- provider、Embedding、Neo4j import、public identity 和 ops identity 均只复用服务器已批准且可追溯的正式配置/secret；缺失 approval、endpoint/model、egress、secret 或外部 hash anchor 时，在真实网络调用、Neo4j 写入或监听端口前失败关闭，不得猜测或生成假配置。
- Neo4j 只从 scoped graph JSONL + manifest 通过交付 importer 导入 candidate，导入前完成 Neo4j 备份；runtime 使用独立只读账号，禁止复制 store 或开放任意 Cypher。
- public 与 ops 必须分进程、分身份、分 secret；public 仅绑定 loopback 并通过可信网关提供 `POST /api/ask`，ops 仅 loopback/私网，不得公网暴露。
- 采用候选/蓝绿方式验证；旧版在候选 Release、数据、身份、问答和完整产品 QA 通过并获得切换放行前保持运行。切换失败按 exact pre-state 同时回退 code、authority、BM25、双向量、graph 和 provider contract，禁止新旧混用。
- 正式验收由未参与部署的独立验收代理执行；生产部署、回滚演练和产品 QA 的真实结果必须回写到 `061-验收标准/`。

## 对应技能

- `00-0600-deployment-architecture-management`
- `00-1000-server-deployment-standards`
- `40-0100-project-testing`
- `50-0100-post-release-sync`

## 交付物

- 生产服务器正式信息记录与只读盘点报告
- 备份、部署、候选验证、切换和回滚演练记录
- `061-验收标准/01-验收执行详情/AC-KGCLOUD-001.md`
- `061-验收标准/01-验收执行详情/AC-KGCLOUD-101.md`
- `061-验收标准/01-验收执行详情/AC-KGCLOUD-201.md`
- `061-验收标准/01-验收执行详情/AC-KGCLOUD-301.md`
- `061-验收标准/01-验收执行详情/AC-KGCLOUD-401.md`

## 关联验收项

- `AC-KGCLOUD-001`
- `AC-KGCLOUD-101`
- `AC-KGCLOUD-201`
- `AC-KGCLOUD-301`
- `AC-KGCLOUD-401`

## 任务产出 / 结果记录

- 2026-09-05 用户确认目标为生产环境，服务器已运行旧版本工程，并要求补全 Linux 侧操作。
- 受控 SSH key 已建立并验证；远端 `authorized_keys` 变更前备份位于 `/data/backup/apps/knowledge-qa/access/20260905T140440+0800/authorized_keys.before`，SHA-256 为 `4b9f59b0d417831172ee1373824c3f26650503a1114e9973a93fd872b5b1b492`。既有密码入口保留，密码未写入项目或证据。
- exact pre-state 已确认：旧 API 容器 `yunji-knowledge-api` 使用 host network，将 `/home/soft/knowledge-graph` 以 rw 挂载到 `/app`，通过 Python 3.11 执行 `pipeline/server.py` 并监听 `0.0.0.0:5001`；Neo4j 2026.05.0 使用 `/home/soft/knowledge-graph/neo4j-docker/data`。Java 通过 `http://127.0.0.1:5001/api/ask` 调用旧服务，当前无 JWT。
- 旧工程备份位于 `/data/backup/apps/knowledge-qa/pre-v2-20260905T141131+0800/`；`knowledge-graph-prestate.tar.gz` 大小 `373703921` bytes，SHA-256 为 `a45a9e9f647f2213758081ad1a5e726d0f2942064b0a8ec0a860138cc52eb88e`，`SHA256SUMS` 与 `tar -tzf` 均通过。归档明确排除活动 Neo4j store、logs、venv 和 cache，并提供 `RESTORE.txt`；Neo4j 后续仍需一致性 dump 或蓝绿独立导入。
- final delivery 内层包本地及远端 SHA-256 均为 `cc140e2a3191095ea333c874f559c68043856983ee466392a0cb4e3dc589eaaa`，远端路径为 `/srv/knowledge-qa/incoming/knowledge-qa-final-delivery-linux-x86_64-20260905-r2.zip`；已解压到 `/srv/knowledge-qa/releases/knowledge-qa-final-delivery-linux-x86_64-20260905-r2/`，ZIP 完整性和包内 `sha256sum -c SHA256SUMS` 均退出 0，解压树符号链接数量为 0。
- 四层交付哈希：外层开发交接包 `b72131c61da816d404118075e8dce92ed6eec1e6c8f32b8a0ce9d317d2e14bd4`；内层 final delivery `cc140e2a3191095ea333c874f559c68043856983ee466392a0cb4e3dc589eaaa`；`RELEASE_MANIFEST.json` 为 `ff9c68d2747587c7c952e7c3dc70aa2b159eabb681733b0c0b00663f9f71586a`；`SUITE_MANIFEST.json` 为 `0a23b3dbf7db6ab601b8bf50c67efb18be586de1d01286266f76a7fe6201f239`，包内 `SHA256SUMS` 文件为 `a8c8f2c02ca5ff3a5e1067bcd997af596b0bdc54c8871249fd72658f4a783bef`。
- 官方 `Python-3.14.5.tar.xz` 大小为 `23903332` bytes，SHA-256 为 `7e32597b99e5d9a39abed35de4693fa169df3e5850d4c334337ffd6a19a36db6`，远端源码与 Sigstore `messageDigest` 绑定校验通过；已通过 `make altinstall` 隔离安装到 `/opt/knowledge-qa/python/3.14.5`，未替换系统 Python。
- `/opt/knowledge-qa/bootstrap-installer` 已由隔离 Python 执行 `venv --copies` 建立，`bin/python` 为普通文件而非符号链接，SHA-256 为 `92cad8810dd2a27ef26a35c77f480243da2ee113dca2c7ca515fb22cf64777b4`；外部锚和构建/安装证据位于 `/data/backup/apps/knowledge-qa/python-bootstrap-20260905T150444+0800/`。`ssl`、`venv`、SQLite、bz2、lzma、ctypes 和 hashlib 等核心模块通过；可选 `_zstd` 因 CentOS 8 仓库版本不足未构建，不是当前核心阻断。
- `python3 verify_final_delivery.py` 首次真实执行因宿主 Python 3.6.8 不兼容退出 1；随后使用受信 bootstrap Python 3.14.5 重跑，返回 `ok:true`、`errors:[]`，authority、BM25、graph、双向量摘要、SBOM、DLP、证据和代码 manifest 均通过。系统 `/usr/bin/python3` 仍为 3.6.8，RPM 前后清单完全一致。
- 用户已批准以官方 PyPI 为来源准备全部 17 项锁定依赖，并批准 `jieba==0.42.1` 作为唯一 sdist 可复现构建例外。16 个官方 wheel 均与 PyPI 官方元数据哈希一致；jieba 官方 sdist SHA-256 为 `055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2`，构建工具 manifest SHA-256 为 `8c7fec7405444cfeec8689d189f426a09da1e2d925ee44764b43fca91eca93e6`，两次独立构建产出字节一致，wheel SHA-256 为 `3917040883aaf70e82288a10a107f6a90be62e088f0a7838f306e062b84ca1f9`。
- formal wheelhouse 已原子落位到 `/srv/knowledge-qa/wheelhouse`，包含 exact 17 个运行时 wheel；`WHEEL_MANIFEST.json` SHA-256 为 `41a0b569d44bbbc412f8fa2c4a081303079cf09ecf4302d3c4b47767c2fdd157`，`SHA256SUMS` 文件 SHA-256 为 `9d79a7cb6cc335b0e890f5d5b3c95339ea5f1bf12f9815fc85ba63c498ca9a2c`，逐文件 `sha256sum -c SHA256SUMS` 全部通过。
- 目标 venv 已按 `--copies --without-pip` 建立于 `/srv/knowledge-qa/venvs/20260905-r2`，使用外部 bootstrap installer、formal wheelhouse 及 `--no-index --no-deps --only-binary=:all:` 安装；Python 为 3.14.5，解释器非符号链接，已安装分发与 lock 均为 exact 17 项且无缺失、无额外项、无版本偏差，venv 内不含 pip、setuptools 或 wheel。
- `usearch==2.26.2` 已成功导入。chunk 索引 `server-runtime/data/derived/vector/local-vector/candidate/r9-fb70102bbfb4007b4546cf305b237d376cbd077496a4fc72a344feff583d0063/chunk-index/index.usearch` 以 `Index.restore(..., view=True)` 只读加载 1482 条、1024 维、SHA-256 `0960420c142f3bb286c9ba4107464cd3c4799fba786a5a101c8cd87ce4208b54`；同目录 entity 索引只读加载 22 条、1024 维、SHA-256 `5cb069ff8573ec9c8e189e5a1737fbf9c1a92f3b5d57909a92fe9a6b6ad2b33c`。
- 使用目标 venv 重跑 exact release 的 `verify_final_delivery.py` 返回 `ok:true`、`errors:[]`；Python/wheelhouse/venv/USEarch 阶段已由不同代理独立验收通过。
- 旧服务在候选准备全过程持续可用：`/api/health` 返回 HTTP 200，首次受控 `/api/ask` 探测返回 HTTP 200 且答案非空；Neo4j 只读计数为 `3986 nodes / 143661 relationships`，旧 API 容器持续 Up，Neo4j 容器持续 healthy。
- Neo4j 一致性备份已完成：Community `2026.05.0` 停止后由同版本 `neo4j-admin database dump neo4j` 导出至 `/data/backup/apps/knowledge-qa/neo4j-consistency-20260905T1810+0800/neo4j.dump`，大小 `78390872` bytes，SHA-256 `7738a27a7c7bd18ae7db4eb5476e4f55d06d9a34557d70ca29f9a4f1feea9dc1`；原容器 ID 未变，恢复后 healthy，旧 API HTTP 200、5001 监听、Neo4j `3986/143661` 计数恢复。
- Neo4j 导入阻塞：当前 Community 单实例只有 `neo4j`/`system` 数据库和现有 `neo4j` 用户，未配置可验证的 import/runtime 账户分离；交付 importer 虽支持同库 `graph_release_id` namespace，但尚未获批“同库 namespace + 独立最小权限账户”方案，也没有独立 Neo4j 实例，因此未执行 scoped graph 导入。
- provider 阻塞：旧配置 SHA-256 为 `19cc96b1d92d0a5a4df835284130225654fea62882b16b34a2d86d8d694df9a3`，包含外部 provider secret；未发现可验证 Stop B approval、egress mapping 或 external hash anchor，secret 仅记录变量名、不记录值，未映射或启动 provider。
- Embedding identity 已核对：Ollama `bge-m3:latest` digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab` 与交付 identity 一致。
- 未执行项：scoped Neo4j candidate 导入、生产 provider/identity/secrets 配置、public/ops WSGI、5001 切换、Java/Nginx 修改、真实回滚演练和产品 QA；`runtime_active:false`、`product_accepted:false`。
- 正式证据入口：[pre-state 与备份](../061-验收标准/03-测试验证/TASK-027/01-prestate-and-backup.md)、[release staging 与运行时门禁](../061-验收标准/03-测试验证/TASK-027/02-release-staging-and-runtime.md)、[Python bootstrap](../061-验收标准/03-测试验证/TASK-027/03-python-bootstrap.md)、[wheelhouse、venv 与 USEarch](../061-验收标准/03-测试验证/TASK-027/04-wheelhouse-venv-usearch.md)、[Neo4j 一致性备份](../061-验收标准/03-测试验证/TASK-027/05-neo4j-consistency-backup.md)。

## 进度总结

- 当前状态：进行中（Python/wheelhouse/venv/USEarch 阶段已完成并经独立验收；完整生产部署未完成）。
- 当前结论：备份、上传、隔离解压、包内哈希、隔离 Python、bootstrap installer、受信 wheelhouse、exact 17 项目标 venv、USEarch 双索引只读加载和目标 venv 下 final verifier 均已取得实施及独立验收证据；TASK-027 与关联 AC 仍不得标记完整完成。
- 下一步门禁：先取得同库 namespace+独立最小权限账户方案批准或独立 Neo4j 实例；同时取得 provider Stop B approval、egress mapping 和 external hash anchor。满足后再执行 Neo4j candidate 导入与回填、正式 identity/secrets、public/ops WSGI、5001 切流、真实回滚演练与产品 QA；上述步骤完成前保持旧服务运行。
