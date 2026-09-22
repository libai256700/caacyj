# DEPLOY.md - 百度云中国区生产交接手册

接收、部署或升级前，AI 和程序员必须先完整阅读
[`KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md`](KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md)，
再阅读本文及当前 release 的批准收据、manifest 和回滚材料。任何缺失、哈希漂移或合同冲突都应
失败关闭；不得从历史聊天或旧 Release 猜测当前参数。

本文面向接收开发团队，说明如何把同一 GitHub 项目交付的知识源、知识服务、
`rag_chunks.db`、BM25、scoped graph、生产向量构建器、App 技能和独立运维组件部署到
中国区域的百度云服务器。

本文不选择模型供应商，不包含真实 endpoint、model、API key、Neo4j 密码或生产审批材料。
执行任何真实模型或 Embedding API 之前，必须先取得
`stop_b_production_provider_approved`；执行 active 切换、发布、重启、回滚或清理之前，还必须
取得相应发布批准。部署成功、进程存活或 `runtime-active` 均不等于 `product_accepted`。

## 1. 交付边界

交付物已经包含：

- `knowledge_base/` 下 revision-a-r9 的 35 个批准知识源；
- clean `rag_chunks.db` 和 authority manifest；
- BM25 数据与 manifest；
- scoped graph JSONL、manifest、Neo4j 导入器和三个固定只读查询；
- provider-neutral server-answer/Embedding HTTP transport、wire contract、meter 和启动 bootstrap；
- 从 sealed SQLite 与 scoped graph 直接派生输入的生产向量 candidate builder/validator；
- eager `pipeline.wsgi:app`，启动监听前完成数据、审批、secret 和 provider 绑定；
- 只含 `knowledge-graph-cloud/` 的 App zip；
- 与公共 App 分开安装的 `operator-companion/`；
- exact allowlist、依赖锁、SBOM、DLP、manifest、测试证据和回滚材料。

接收开发团队只需要：

1. 选择生产 provider/model/version/endpoint 和 `single`、`sequential_fallback` 或
   `parallel_hedge` 策略；
2. 完成生产 Stop B 合同材料、逐角色 egress mapping 和外部 approval hash anchor；
3. 从 secret manager 注入 provider key 和 Neo4j 凭据；
4. 按 schema 填写 provider、向量、Neo4j import 和 active runtime 配置；
5. 运行交付的生产向量构建/验证与 Neo4j import 命令；
6. 由获批 Release Controller 完成 candidate 到 active 的切换、启动和验收。

不需要也不应修改 Python 源码、补写 provider transport、另写 Neo4j 查询、重新设计 RAG，
或从旧服务器复制数据库/索引/Neo4j store。

## 2. 必须分开的四个状态

| 状态 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| `stop_b_offline_handoff_ready` | fake provider、DLP、包和零网络证据通过 | 不授权真实 API |
| `stop_b_deferred_no_external_processing` | 可以交付空生产配置的便携源码/数据 | 不授权真实 API 或生产向量 |
| `stop_b_production_provider_approved` | 指定角色、数据类别、模型和合同获批 | 不等于已部署或已验收 |
| `product_accepted` | 生产环境完成完整产品验收 | 不能由 health/PID/receipt 单独替代 |

当前仓库中的 `deploy/pipeline/config.example.json` 是故意禁网的空配置。它只能用于验证默认
失败关闭，不能作为生产配置直接启动服务。

## 3. Release 目录与验签

最终 Release 必须是一个单一稳定版本，至少包含下列结构；实际文件集合以
`SUITE_MANIFEST.json` 和 `SHA256SUMS` 为准：

```text
release-root/
  app-upload/knowledge-graph-cloud-app-upload.zip
  server-runtime/
    code/
    data/
      authority/authority-manifest.json
      authority/rag_chunks.db
      derived/bm25-manifest.json
      derived/bm25.sqlite3
      derived/graph/graph-manifest.json
      derived/graph/scoped-graph.jsonl
    runtime-file-allowlist.json
    requirements.lock
    runtime-code-manifest.json
    data-release-manifest.json
    SBOM.spdx.json
    ROLLBACK_PLAN.json
    evidence/
  operator-companion/
  SUITE_MANIFEST.json
  SHA256SUMS
```

第一版生产向量已固定为本机 loopback-only Ollama `bge-m3:latest`，并随 Server Suite
交付 1,482 个 chunk vectors 和 22 个 entity vectors。身份固定为 1024 维、f32、L2、
cosine/`cos`、USEarch `2.26.2`，模型 digest 为
`7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`。fake 32 维仅是
零网络测试夹具，不得进入最终 Release，生产配置和 validator 必须拒绝。

本机开发不再以 fake 32 维索引作为默认检索候选。已注册的 Ollama `bge-m3:latest`
是本机默认 Embedding，模型 digest 与实测 1024 维必须同时绑定。以下命令只允许写一个新的
candidate，并在临时只读 active 副本中验证；它们不执行生产切换：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=deploy \
  <python-with-usearch-2.26.2> scripts/ollama_local_embedding_probe.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=deploy \
  <python-with-usearch-2.26.2> scripts/build_ollama_vector_candidate.py \
  --authority-root <authority-candidate> \
  --graph-manifest <scoped-graph-manifest> \
  --output-root <new-candidate-root>

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=deploy \
  <python-with-usearch-2.26.2> scripts/verify_ollama_vector_candidate.py \
  --candidate-root <new-candidate-root> \
  --authority-database <authority-candidate>/rag_chunks.db
```

Ollama transport 只接受 `http://127.0.0.1`、`localhost` 或 `::1`，无凭据、无远端出口。
这条本机路径就是第一版生产 Embedding 身份。server answer/ops 仍保留 provider-neutral 接口，
但真实 provider、model、endpoint 和 secret 必须为空并 fail closed。未来启用任何外部模型角色
时，按 `N + M + 2` 重新取得 production Stop B；不得要求接收团队把当前向量改造成外部 API。

下载后先在隔离 staging 验证，任何一项失败立即停止：

```bash
cd /srv/knowledge-qa/releases/<release-id>
sha256sum -c SHA256SUMS
python3 - <<'PY'
import json
from pathlib import Path

root = Path(".").resolve()
for relative in (
    "SUITE_MANIFEST.json",
    "server-runtime/runtime-code-manifest.json",
    "server-runtime/data-release-manifest.json",
    "server-runtime/SBOM.spdx.json",
):
    json.loads((root / relative).read_text(encoding="utf-8"))
for path in root.rglob("*"):
    if path.is_symlink():
        raise SystemExit(f"symlink forbidden in release: {path}")
print("release JSON and no-symlink checks passed")
PY
```

不要把仓库中的整个 `artifacts/` 多版本 staging 目录上传或部署。它包含历史候选和失效证据，
不是最终 Release。


### 离线 DLP 收据复验

接收团队只复验发布方随 GitHub Release 提供的 detached final receipt。Phase-1 的
`scan-phase1` / `validate-phase1` 需要私有治理输入和完整候选闭包，属于发布方
Stop B 证据，不是接收方 Release 复验步骤。

禁止直接执行 `python -m deploy.cloud_v2.dlp` 或 `dlp.py`。DLP 必须作为
`offline_evidence` 的 `dlp` action，通过 held-byte `python -I -S -B -c` formal
bootstrap 运行。下面的外层函数只负责生成并启动该 formal 子进程；可信结果来自子进程
对完整 module closure 和实际 DLP import-time source 的复核。

```bash
KG_REPOSITORY_ROOT="/srv/knowledge-qa/source/-APP-"
KG_SUITE_ROOT="/srv/knowledge-qa/releases/<release-id>"
KG_RUNTIME_PYTHON="/srv/knowledge-qa/venv/bin/python"
KG_FINAL_DLP_RECEIPT="/srv/knowledge-qa/receipts/<release-id>/final-suite-dlp-receipt.json"
KG_CANDIDATE_DLP_RECEIPT="$KG_SUITE_ROOT/server-runtime/evidence/candidate-dlp-receipt.json"
KG_DISCLOSURE_RECEIPT="$KG_SUITE_ROOT/server-runtime/evidence/disclosure-evidence.json"
KG_OFFLINE_COMPONENT_SET="$KG_SUITE_ROOT/server-runtime/evidence/offline-test-component-set.json"
KG_OFFLINE_LOG_ROOT="$KG_SUITE_ROOT/server-runtime/evidence/logs"
KG_OFFLINE_TEST_RECEIPT="$KG_SUITE_ROOT/server-runtime/evidence/offline-test-receipt.json"
KG_SUITE_BUILD_RECEIPT="/srv/knowledge-qa/receipts/<release-id>/suite-build-receipt.json"

test -d "$KG_REPOSITORY_ROOT"
test -d "$KG_SUITE_ROOT"
test -x "$KG_RUNTIME_PYTHON"
test ! -L "$KG_RUNTIME_PYTHON"
test -f "$KG_FINAL_DLP_RECEIPT"
test -f "$KG_SUITE_BUILD_RECEIPT"

run_formal_dlp() {
  "$KG_RUNTIME_PYTHON" -I -S -B -c '
import subprocess
import sys
from pathlib import Path

repository = Path(sys.argv[1])
sys.path.insert(0, str(repository))
from deploy.cloud_v2.offline_evidence import formal_cli_command

command = formal_cli_command(repository, ["dlp", *sys.argv[2:]])
completed = subprocess.run(command, stdin=subprocess.DEVNULL, check=False)
raise SystemExit(completed.returncode)
' "$KG_REPOSITORY_ROOT" "$@"
}

run_formal_dlp validate-final \
  --repo-root "$KG_REPOSITORY_ROOT" \
  --suite-root "$KG_SUITE_ROOT" \
  --candidate-receipt "$KG_CANDIDATE_DLP_RECEIPT" \
  --receipt-path "$KG_FINAL_DLP_RECEIPT" \
  --evidence-root "disclosure-evidence=$KG_DISCLOSURE_RECEIPT" \
  --evidence-root "offline-test-component-set=$KG_OFFLINE_COMPONENT_SET" \
  --evidence-root "offline-test-logs=$KG_OFFLINE_LOG_ROOT" \
  --evidence-root "offline-test-receipt=$KG_OFFLINE_TEST_RECEIPT" \
  --evidence-root "suite-build-receipt=$KG_SUITE_BUILD_RECEIPT"
```

五个 `--evidence-root` label 必须恰好匹配上述集合，不能缺少、重复或增加。DLP CLI
不替代 held-byte disclosure/test 证据；最终 handoff 必须同时绑定两者。成功时 stdout
是单个 canonical JSON。普通业务失败在 stderr 返回 `cloud-v2-dlp-cli-error-v1` 并退出 1；
参数或 formal context 错误退出 2；receipt 可能已经提交的发布异常返回
`cloud-v2-dlp-cli-publication-error-v1` 并退出 3，其中 `safe_to_retry=false`，必须按
`publication_outcome` 对账，禁止盲目重试。

## 4. 主机与身份隔离

推荐至少使用四个独立服务账号或等价容器身份：

| 身份 | 权限 |
| --- | --- |
| `kg-public` | 只读 active code/data，只访问批准的 provider endpoint 和本机 Neo4j |
| `kg-ops` | 私网运维入口，只调用 allowlisted ops 工具，不持有 provider secret |
| `kg-builder` | 读取 sealed authority/graph，写指定 candidate 根，不写 active |
| `kg-release` | 只执行获批 exact switch/restart/rollback，不做构建或问答 |

公共服务与运维服务必须使用不同进程/容器、入口、认证 audience、service account、secret、
网络策略和 tool registry。公共服务不能发现或调用运维服务。运维入口只能通过 VPN、堡垒机或
零信任网络访问，不得绑定公网地址。

建议目录：

```text
/srv/knowledge-qa/releases/<release-id>/     # 不可写的 Release
/srv/knowledge-qa/current                    # Release Controller 管理的 active 引用
/var/lib/knowledge-qa/candidate/             # kg-builder 可写
/var/lib/knowledge-qa/active/                # runtime 只读
/var/lib/knowledge-qa/backup/                # Release Controller 管理
/etc/knowledge-qa/                           # root 管理的非 secret 配置
/run/secrets/knowledge-qa/                   # secret manager 挂载
```

candidate、active、backup 必须是不同的精确目录。不要用 glob 删除，也不要让 builder 对
`active/` 有写权限。

## 5. Python 运行时

使用 Release `server-runtime/requirements.lock` 中的精确版本。当前候选以 Python 3.14 验证，
其中 Neo4j driver 固定为 `6.2.0`、USEarch 固定为 `2.26.2`，生产 WSGI server 固定为
`waitress==3.0.2`。不要安装 provider SDK；HTTP transport 使用交付的 provider-neutral 实现。

```bash
: "${KG_BOOTSTRAP_INSTALLER_PYTHON_SHA256:?missing external installer Python hash anchor}"
test ! -e /srv/knowledge-qa/venv
test -x /opt/knowledge-qa/bootstrap-installer/bin/python
test ! -L /opt/knowledge-qa/bootstrap-installer/bin/python
test "$(sha256sum /opt/knowledge-qa/bootstrap-installer/bin/python | cut -d ' ' -f 1)" \
  = "$KG_BOOTSTRAP_INSTALLER_PYTHON_SHA256"

python3.14 -m venv --copies --without-pip /srv/knowledge-qa/venv
test ! -L /srv/knowledge-qa/venv/bin/python

/opt/knowledge-qa/bootstrap-installer/bin/python -B -m pip \
  --python /srv/knowledge-qa/venv/bin/python install \
  --no-deps --only-binary=:all: --no-index --no-compile --no-cache-dir \
  --find-links /srv/knowledge-qa/wheelhouse \
  -r /srv/knowledge-qa/releases/<exact-release-id>/server-runtime/requirements.lock
```

`bootstrap-installer` 位于目标 venv 之外，必须由部署控制面固定自身 Python、pip 版本和字节哈希；
上面的 SHA-256 锚必须来自独立信任域，不能从 installer 所在目录现场计算后自证。目标 venv 路径
必须在创建前完全不存在；`venv` 会复用已有目录并保留其中的残留文件，因此不得省略该门禁。
`wheelhouse` 必须先按组织批准的 wheel manifest 逐文件验证。不得在目标 venv 内升级或安装 pip、
setuptools、wheel，也不得移除 `--no-deps` 后让安装器自行解析漂移依赖。后续
`capture-runtime` 会要求目标环境的 installed distribution 名称和版本集合与
`requirements.lock` 精确相等，并绑定其 METADATA、RECORD 和完整 runtime tree；任何额外包
都会失败关闭。依赖准备属于部署活动，不是模型数据出站。

## 6. 生产 Stop B 与 provider 配置

在任何真实 API 调用之前准备以下四份 exact-byte 文件：

1. approval-ready `cloud-v2-stop-b-external-processing-request-v3`；
2. 实际合同材料 manifest；
3. 逐角色 egress policy/mapping；
4. 绑定上述文件与 provider config 的生产 approval receipt。

provider 配置遵循 `deploy/pipeline/provider_runtime_config.schema.json`。每个 server-answer 通道和
Embedding 角色必须独立绑定用途、数据类别、provider、endpoint、region、model/version、
API version、限额、预算、wire schema 和合同证据；通道数量和策略不得写死在源码中。

关键环境变量：

```text
KG_PROVIDER_RUNTIME_CONFIG=/etc/knowledge-qa/provider-runtime.json
KG_PROVIDER_NETWORK_MODE=https
KG_STOP_B_PRODUCTION_APPROVAL_SHA256=<由部署控制面或 secret manager 注入的 receipt SHA-256>
KG_<ROLE>_API_KEY=<由 provider config 中 secretref 指向的真实 secret>
```

`KG_STOP_B_PRODUCTION_APPROVAL_SHA256` 不能从 provider config 自身推导或由同一可写配置目录自证。
缺失、过期、hash 不符、角色漂移、五类数据决策缺项、材料换字节或 egress 不一致时，bootstrap
必须在解析 secret 和建立 transport 之前失败关闭。

生产防火墙只放行 approval 中列出的 exact HTTPS endpoint。不要放行供应商整个域名集合，
不要为公共服务开放任意互联网访问。

## 7. 构建生产 chunk/entity 向量

生产向量构建器只接受 sealed authority manifest、对应 `rag_chunks.db`、scoped graph manifest
和 provider config。chunk 文本从 SQLite 固定查询读取；entity 文本和 entity id 从经 SQLite
evidence 回填的 scoped graph 读取。调用方不能自行提供或删减 chunk/entity 列表来伪造覆盖率。

按 `deploy/pipeline/production_embedding_config.schema.json` 的 v2 合同创建配置。
`base_suite.manifest` 必须指向精确 Release 根的 `SUITE_MANIFEST.json`，
`base_suite.pending_contract` 必须指向同一根内保持原字节不变的
`server-runtime/production-vector-build-contract.json` v1 pending 合同。`authority` 和 `graph`
也必须来自该同一 suite root；本地向量数据根必须指向
`/var/lib/knowledge-qa/candidate/` 下一个尚不存在的精确 release id。不得使用
`/srv/knowledge-qa/current` 等符号链接别名代替精确 Release 根。

生产 Stop B 获批、provider 配置与 egress 完成绑定后，先由独立部署控制面注入
base suite 外部锚，再使用精确 Release 内的 held-byte bootstrap 捕获 Python、venv、
stdlib、native dependency 和 requirements 闭包。runtime lock 的输出父目录必须预先存在且
不是符号链接，输出文件必须尚不存在：

```bash
export KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256='<externally-trusted-suite-manifest-sha256>'
/srv/knowledge-qa/venv/bin/python -I -S -B \
  /srv/knowledge-qa/releases/<exact-release-id>/server-runtime/code/deploy/pipeline/production_embedding_bootstrap.py \
  capture-runtime \
  --output /var/lib/knowledge-qa/runtime-locks/<exact-release-id>-production-embedding-runtime-lock.json
```

Release Controller 在独立信任域重新读取 runtime lock 的精确字节并封存 SHA-256；该值不得
由 runtime lock 所在的可写目录自证。注入 runtime 外部锚后，先复核当前运行时与精确 Release：

```bash
export KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256='<externally-trusted-suite-manifest-sha256>'
export KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256='<externally-trusted-runtime-lock-sha256>'
/srv/knowledge-qa/venv/bin/python -I -S -B \
  /srv/knowledge-qa/releases/<exact-release-id>/server-runtime/code/deploy/pipeline/production_embedding_bootstrap.py \
  --runtime-lock /var/lib/knowledge-qa/runtime-locks/<exact-release-id>-production-embedding-runtime-lock.json \
  verify-runtime
```

只有 `verify-runtime` 返回 `"ok":true` 后，才通过同一个 bootstrap 物化 suite 外 configured
v2 合同。合同输出父目录必须预先存在且不是符号链接，输出文件必须尚不存在：

```bash
export KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256='<externally-trusted-suite-manifest-sha256>'
export KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256='<externally-trusted-runtime-lock-sha256>'
/srv/knowledge-qa/venv/bin/python -I -S -B \
  /srv/knowledge-qa/releases/<exact-release-id>/server-runtime/code/deploy/pipeline/production_embedding_bootstrap.py \
  --runtime-lock /var/lib/knowledge-qa/runtime-locks/<exact-release-id>-production-embedding-runtime-lock.json \
  materialize \
  --config /etc/knowledge-qa/production-embedding.json \
  --output /var/lib/knowledge-qa/contracts/<exact-release-id>-production-vector-build-contract-v2.json
```

`materialize` 必须返回 `"ok":true`、`"network_calls":0` 和 `"source_count":35`。Release
Controller 在独立信任域重新校验该 configured v2 文件的精确字节，封存其
`contract_sha256`，并以 configured-contract 外部锚注入。三个锚含义不同：

- `KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256` 锚定不可变 base `SUITE_MANIFEST.json`；
- `KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256` 锚定 suite 外的精确 Python 运行时闭包；
- `KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256` 锚定 suite 外、已绑定生产 provider 的 configured v2 合同。

不得在启动时从合同文件现场计算三个锚，也不得把它们写入同一可写
provider/config 目录自证。保留 Release 内 v1 pending 合同的原字节；不得覆盖它，也不得
将它直接传给 `validate/build`。

然后先执行不发起 provider 请求的完整预检：

```bash
export KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256='<externally-trusted-suite-manifest-sha256>'
export KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256='<externally-trusted-runtime-lock-sha256>'
export KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256='<externally-trusted-configured-v2-contract-sha256>'
/srv/knowledge-qa/venv/bin/python -I -S -B \
  /srv/knowledge-qa/releases/<exact-release-id>/server-runtime/code/deploy/pipeline/production_embedding_bootstrap.py \
  --runtime-lock /var/lib/knowledge-qa/runtime-locks/<exact-release-id>-production-embedding-runtime-lock.json \
  validate \
  --config /etc/knowledge-qa/production-embedding.json \
  --contract /var/lib/knowledge-qa/contracts/<exact-release-id>-production-vector-build-contract-v2.json
```

只有 `validate` 返回 `"ok":true` 且 `"network_calls":0` 后，才由获批的 Release
Controller 执行真实 Embedding 构建：

```bash
export KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256='<externally-trusted-suite-manifest-sha256>'
export KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256='<externally-trusted-runtime-lock-sha256>'
export KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256='<externally-trusted-configured-v2-contract-sha256>'
/srv/knowledge-qa/venv/bin/python -I -S -B \
  /srv/knowledge-qa/releases/<exact-release-id>/server-runtime/code/deploy/pipeline/production_embedding_bootstrap.py \
  --runtime-lock /var/lib/knowledge-qa/runtime-locks/<exact-release-id>-production-embedding-runtime-lock.json \
  build \
  --config /etc/knowledge-qa/production-embedding.json \
  --contract /var/lib/knowledge-qa/contracts/<exact-release-id>-production-vector-build-contract-v2.json
```

五个命令都必须使用同一个绝对 Python 可执行文件、`-I -S -B`、精确 Release 内的 bootstrap
及相同 runtime lock；不得直接运行 candidate 文件或 `python -m`，也不得通过 `/current`、
`PYTHONPATH`、工作目录或用户 site 注入模块。runtime lock 与 configured v2 合同位于 suite 外，
Release 内 pending v1 合同保持原字节。`build` 只写配置声明的 candidate release 目录，不切换
active；它返回的结构化 receipt 由 Release Controller 封存。

构建完成必须核对：

- chunk vector id 集合与 SQLite `chunk_id` 集合 100% 相等；
- entity vector id 集合与 scoped graph `entity_id` 集合 100% 相等；
- entity 的每个 evidence id 都能回填 SQLite；
- manifest 中 Embedding identity、dimension、normalization、metric 和 provider config hash 一致；
- candidate 目录之外无写入，active state 未改变；
- receipt/ledger 不包含原文、secret 或 provider 响应正文。

生产 query embedding 必须使用与 chunk/entity build 相同的 identity 和 policy。provider、
endpoint、region、model/version、API version、input type、dimension、normalization，或
provider config、approval、policy 的任何绑定哈希改变时，都必须使用新的 suite 外路径重新
执行 `materialize`、建立新 configured-contract 外部锚并重建两个索引；不得混用旧合同或旧索引。

## 8. Neo4j 导入

scoped graph 的交付权威形式是 JSONL + manifest + importer，不是某台机器的 Neo4j store 目录。
Neo4j 只监听本机或私有容器网络，runtime 用户只授予 `READ`，import 用户单独授予受控写权限。

按 `deploy/pipeline/neo4j_import_config.schema.json` 创建配置，例如：

```json
{
  "schema_version": "kg-scoped-neo4j-import-config-v1",
  "graph_manifest_path": "/srv/knowledge-qa/releases/<exact-release-id>/server-runtime/data/derived/graph/graph-manifest.json",
  "authority_database_path": "/srv/knowledge-qa/releases/<exact-release-id>/server-runtime/data/authority/rag_chunks.db",
  "receipt_output_path": "/var/lib/knowledge-qa/candidate/<release-id>/neo4j-import-receipt.json",
  "driver": "neo4j",
  "driver_version": "6.2.0",
  "uri_env": "KG_NEO4J_IMPORT_URI",
  "username_env": "KG_NEO4J_IMPORT_USERNAME",
  "password_env": "KG_NEO4J_IMPORT_PASSWORD",
  "database_env": "KG_NEO4J_IMPORT_DATABASE",
  "batch_size": 500,
  "query_timeout_seconds": 10.0
}
```

凭据只通过环境或 secret manager 注入，不写进 JSON 或命令行：

```bash
KG_REPOSITORY_ROOT=/srv/knowledge-qa/source/-APP-
KG_RUNTIME_PYTHON=/srv/knowledge-qa/venv/bin/python
export KG_NEO4J_IMPORT_CONFIG=/etc/knowledge-qa/neo4j-import.json
export KG_NEO4J_IMPORT_URI='bolt://127.0.0.1:7687'
export KG_NEO4J_IMPORT_USERNAME='<secret-manager-injected>'
export KG_NEO4J_IMPORT_PASSWORD='<secret-manager-injected>'
export KG_NEO4J_IMPORT_DATABASE='<configured-database>'
"$KG_RUNTIME_PYTHON" -I -S -B -c '
import os
import sys
from pathlib import Path

repository = Path(sys.argv[1])
sys.path.insert(0, str(repository))
from deploy.cloud_v2.offline_evidence import formal_cli_command

command = formal_cli_command(repository, ["neo4j-import-candidate"])
os.execve(command[0], command, dict(os.environ))
' "$KG_REPOSITORY_ROOT"
```

Importer 只使用五个固定、参数化写查询；runtime 只使用三个固定、参数化读查询，并以
Neo4j `READ_ACCESS` 打开 session。没有任意 Cypher 接口。receipt 中 graph release、authority
database hash、config hash 和计数必须与 Release manifest 一致。
生产 importer 和 runtime 只接受直连 `bolt://` 或 `bolt+s://`；拒绝 `neo4j://`、
`neo4j+s://`、`bolt+ssc://` 以及公网、link-local 或其他非批准目标。

## 9. Active runtime 配置

生产向量和 Neo4j candidate 均验证通过后，由获批 Release Controller 形成只读 active 树，
再按 `deploy/pipeline/cloud_runtime_config.schema.json` 创建 active runtime 配置。该配置必须绑定：

- runtime release id 和绝对 `active_root`；
- provider runtime config SHA-256；
- authority/BM25 data + manifest 的相对路径和 SHA-256；
- graph manifest SHA-256、release id、Neo4j driver/version 和四个环境变量名；
- regulation timeline/superseded registry 的路径和 SHA-256；
- Embedding identity/policy SHA-256；
- local-vector release、manifest、dimension、metric、index name、metadata allowlist 和容量；
- server-answer strategy、ordered channel identities、总时限/成本预算和 circuit breaker。

runtime 配置中的路径和 hash 必须来自最终 active candidate receipts，不能手工猜测。active 数据
目录和文件对 `kg-public` 必须只读；startup 不会建库、补向量、导入图谱、切换 release 或清理旧版。

Neo4j runtime 凭据示例：

```text
KG_NEO4J_RUNTIME_URI=bolt://127.0.0.1:7687
KG_NEO4J_RUNTIME_USERNAME=<read-only-user>
KG_NEO4J_RUNTIME_PASSWORD=<secret-manager-injected>
KG_NEO4J_RUNTIME_DATABASE=<configured-database>
```

环境变量名必须与 cloud runtime config 中的 `uri_env`、`username_env`、`password_env`、
`database_env` 完全相同。

## 10. 公共服务启动

必需环境：

```text
KG_CLOUD_RUNTIME_CONFIG=/etc/knowledge-qa/cloud-runtime.json
KG_CLOUD_RUNTIME_CONFIG_SHA256=<由部署控制面注入的 cloud-runtime.json SHA-256>
KG_PROVIDER_RUNTIME_CONFIG=/etc/knowledge-qa/provider-runtime.json
KG_PROVIDER_NETWORK_MODE=https
KG_STOP_B_PRODUCTION_APPROVAL_SHA256=<external anchor>
KG_PUBLIC_IDENTITY_CONFIG=/etc/knowledge-qa/public-identity.json
KG_PUBLIC_IDENTITY_CONFIG_SHA256=<由部署控制面注入的 public-identity.json SHA-256>
KG_PUBLIC_IDENTITY_HS256_SECRET=<secret manager 注入的 base64url、至少 32 字节密钥>
KG_PUBLIC_BIND_HOST=127.0.0.1
KG_PUBLIC_BIND_PORT=5001
KG_PUBLIC_ALLOWED_HOSTS=<反向代理发送的精确 Host 集合>
KG_PUBLIC_RETRIEVAL_SOURCES=sqlite_exact,bm25,dense,neo4j
```

`KG_CLOUD_RUNTIME_CONFIG_SHA256` 必须由 cloud runtime config 所在的可写配置包之外提供，不得从该配置
自身或同一可写目录推导。启动器在打开 authority、BM25、vector 或 graph 之前必须稳定读取并验证
该 hash；缺失或换字节时必须在端口监听前失败关闭。

`public-identity.json` 必须符合 `deploy/pipeline/public_identity_config.schema.json`。下面的 issuer
和 secretref 环境变量名由部署团队按其可信认证网关填写；算法、audience、token 来源和公共身份合同
不可改成其他值：

```json
{
  "schema_version": "kg-public-identity-gateway-config-v1",
  "verifier": {
    "kind": "hs256-jwt-gateway-v1",
    "algorithm": "HS256",
    "issuer": "urn:example:trusted-public-gateway",
    "audience": "public-app-agent",
    "secret_ref": {
      "value": "secretref:KG_PUBLIC_IDENTITY_HS256_SECRET",
      "encoding": "base64url"
    },
    "token_source": {
      "wsgi_environ_key": "HTTP_AUTHORIZATION",
      "scheme": "Bearer"
    },
    "time_policy": {
      "leeway_seconds": 5,
      "max_lifetime_seconds": 300
    },
    "claim_mapping": {
      "subject": "sub",
      "roles": "roles",
      "authn_methods": "amr"
    },
    "identity_contract": {
      "service_account": "public-app-agent",
      "token_kind": "public-app-access",
      "network_zone": "public-app",
      "required_roles": ["app-user"]
    }
  }
}
```

配置必须使用绝对非 symlink 路径，文件不能由 group/other 写入。其原字节 SHA-256 必须由配置目录
之外的部署控制面注入；HS256 secret 只进入认证网关和 `kg-public` secret 环境，不写入配置、仓库、
日志或命令行。

生产入口使用 eager WSGI module，不使用 `pipeline.server` 的 Flask 开发服务器：

```bash
cd /srv/knowledge-qa/current/server-runtime/code/deploy
exec /srv/knowledge-qa/venv/bin/waitress-serve \
  --listen=127.0.0.1:5001 \
  pipeline.wsgi:app
```

`pipeline.wsgi` 在 import 时先核验 public identity 配置/hash/secret，再打开并核验
SQLite/BM25/vector/graph、验证 Stop B approval、解析 provider secret、构造 transport 并绑定
coordinator，最后包装认证 middleware。任一步失败都会在监听端口之前退出；不要通过延迟加载或
捕获异常绕过 preflight。

裸 HTTP header 不能直接成为用户身份。可信认证网关先验证 App token，删除客户端提供的
`Authorization` 和身份转发头，再用独享 HS256 secret 签发短时 gateway JWT；交付的 middleware
仅验证 `Authorization: Bearer <gateway-jwt>`，验证签名、issuer、audience、`iat`/`nbf`/`exp`、
生命周期和映射 claims 后，才在 WSGI environ 中注入 typed `kg.verified_identity`。公共身份固定为：

```text
audience=public-app-agent
service_account=public-app-agent
token_kind=public-app-access
network_zone=public-app
roles exactly [app-user]
```

无 JWT、坏签名、`alg=none`、错误 issuer/audience、过期/未来 token、缺少或追加 role，以及仅提供
`X-KG-*` 等身份头的请求均返回 `403 access_denied`，且不会触达 Flask handler。公网只放行
`POST /api/ask`，知识数据库、Neo4j、vector files、`/ops/*` 和内部诊断信息均不得公网可达。

## 11. 运维服务

`operator-companion/` 不进入 App zip，必须单独安装为 `ops-admin-agent`。其 WSGI 进程只绑定
loopback/私网，要求 audience/service account 均为 `ops-admin-agent`、network zone 为
`private-admin`，并同时具备 MFA、mTLS 和 OIDC 认证标记。

`offline-phase1-fake` 只出现在 Stop B 负向测试中，不进入 production-only Release 的运行配置或
handler assembly；生产启动器检测到该模式必须在监听前失败关闭。生产 handler assembly、
candidate job runner 和 Release Controller 必须使用同一 Release 中的 allowlist/schema，并在其对应发布
批准完成后启用。公共进程不得复用运维 secret、tool registry 或 service account。

运维进程有两份彼此独立的 hash-bound 配置：

- `ops-runtime-config.schema.json` 绑定 active suite/data/runtime、只读数据文件、candidate workspace、
  确认账本和 loopback 监听参数；
- `ops-identity-config.schema.json` 绑定可信私网网关 issuer、两个固定 audience、JWT 时效、claim
  mapping、MFA/mTLS/OIDC 要求和可用 ops role。

以 `operator-companion/ops-agent-config/` 中的两个 `*.example.json` 为模板，在 root 管理的
`/etc/knowledge-qa/` 下分别物化生产配置。模板不含 secret；其中
`ops-runtime-config.example.json` 故意不可直接启动，部署团队必须用 active receipts 的精确路径和
hash 替换全部占位项。两份配置均须为绝对非 symlink regular file，且不能由 group/other 写入。
部署控制面必须在配置目录之外审阅并固定各自的 exact-byte SHA-256，再通过独立信任值注入；不得由
同一可写配置包在启动脚本里现场计算后自证。

必需环境：

```text
KG_PROCESS_ROLE=ops-admin-agent
KG_OPS_RUNTIME_CONFIG=/etc/knowledge-qa/ops-runtime.json
KG_OPS_RUNTIME_CONFIG_SHA256=<deployment-control-plane external anchor>
KG_OPS_IDENTITY_CONFIG=/etc/knowledge-qa/ops-identity.json
KG_OPS_IDENTITY_CONFIG_SHA256=<deployment-control-plane external anchor>
KG_OPS_IDENTITY_HS256_SECRET=<secret-manager base64url, decoded length >= 32 bytes>
KG_OPS_CONFIRMATION_HS256_SECRET=<different secret-manager base64url, decoded length >= 32 bytes>
```

两把 HS256 secret 必须由 secret manager 独立生成、轮换和注入，值不得相同，也不得与
`KG_PUBLIC_IDENTITY_HS256_SECRET` 复用。它们不能写入配置、仓库、日志、命令行或 Release。
缺少配置/hash/secret、配置换字节、两把 secret 相同或 runtime binding 失败时，进程会在
Waitress 监听前失败关闭。

可信私网认证网关必须执行以下顺序：

1. 只接受 VPN、堡垒机或零信任私网入口，并在网关终止和验证 mTLS、OIDC 与 MFA；
2. 删除客户端提供的 `Authorization`、`X-KG-Maintenance-Confirmation` 及所有身份转发头；
3. 使用 identity 专用 secret 签发短时 `Authorization: Bearer <gateway-jwt>`，其中
   `aud=ops-admin-agent`、`sub` 为稳定操作者 id、`roles` 只能取
   `ops-observer`/`ops-maintainer`，`amr` 至少包含 `mfa`、`mtls`、`oidc`；
4. 只有管理员已在独立确认步骤批准与请求正文相同的 `plan_id` 时，才使用 confirmation 专用
   secret 签发短时 `X-KG-Maintenance-Confirmation: Bearer <confirmation-jwt>`；其
   `aud=maintenance-controller-cloud`、`confirmed_by` 必须等于 identity `sub`、
   `decision=approved`，且只发送到 `/ops/maintenance/jobs`；
5. 网关到 Waitress 的连接只走 loopback 或受控私网，不把两个签名 secret 下发给浏览器、App
   进程或 public gateway。

middleware 会先删除任何 WSGI environ 中预注入的 typed identity/confirmation，再验证 HS256
签名、`alg`/`typ`、issuer/audience、`iat`/`nbf`/`exp`、最大生命周期、认证方法和 role。
四个只读路由只安装 `VerifiedIdentity`；维护路由同时安装与同一操作者绑定的
`VerifiedMaintenanceConfirmation`。App/public audience、裸 `X-KG-*` 身份头、缺少 mTLS/MFA、
过期确认票据或伪造进程内对象均返回 `403 access_denied`，不会触达 Flask handler。

在独立的 `kg-ops` 服务账号或容器中启动；当前工作目录必须是解压后的 operator companion，而
不是 App zip 或源码仓：

```bash
cd /srv/knowledge-qa/releases/<exact-release-id>/operator-companion
exec /srv/knowledge-qa/venv/bin/python -m server.ops_server
```

`server.ops_server` 只调用锁定版本的 Waitress，并从 hash-bound runtime config 读取 loopback
host、port 和线程数。不得使用 `flask run`、`app.run()`、公网 bind 或把 public/ops 两个入口放进
同一进程。反向代理 health check 也必须携带有效的 ops gateway JWT；HTTP 200 只证明该请求通过，
不等于 release、provider 或产品验收完成。

## 12. 验收与回滚

至少执行以下分层验收，不能只看 HTTP 200：

1. Release：`SHA256SUMS`、manifest、SBOM 和 DLP/测试证据均匹配；
2. Authority：SQLite integrity/foreign-key、35 文档、chunk/provenance 计数和 source manifest 绑定；
3. Retrieval：BM25、chunk vector、entity vector 覆盖率和 SQLite/graph 回填为 100%；
4. Graph：Neo4j release/count/evidence 与 scoped graph manifest 一致，无范围外 label/type；
5. Provider：每个角色匹配批准的 endpoint/model/version/region/预算和 egress；
6. Runtime：eager preflight 失败关闭，公共/运维身份和网络隔离生效；
7. 产品：确定性/权威路径优先、必要时 provider-neutral server answer，最终客户回答仍由 App 宿主生成；
8. 代表性问答：法规、题库、教材、地面站、库外问题、服务不可用和身份问候均符合合同。

回滚必须同时回退 code、authority、BM25、chunk/entity vector、graph 和 provider contract，禁止
新旧 release 混用。执行前由 Release Controller 验证 `ROLLBACK_PLAN.json` 中的 exact pre-state；
任何 hash、receipt、备份或目标不一致都应停止。删除只允许 exact target，禁止 glob、递归共享根或
人工临时清库。

最终报告必须分开写：

```text
github_delivery_complete: <true|false>
deployment_handoff_ready: <true|false>
runtime_active: <true|false>
product_accepted: <true|false>
```

只有接收团队完成真实 provider 配置、部署和完整产品验收后，才能将 `product_accepted` 置为
`true`。
