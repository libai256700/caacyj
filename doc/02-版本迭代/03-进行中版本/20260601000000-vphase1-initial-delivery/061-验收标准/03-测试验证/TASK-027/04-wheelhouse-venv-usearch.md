# TASK-027 wheelhouse、venv 与 USEarch 证据

## 批准边界与来源

- 用户批准以官方 PyPI 为来源准备 `server-runtime/requirements.lock` 的全部 17 项 wheelhouse。
- `jieba==0.42.1` 是唯一允许从 sdist 构建 wheel 的例外；其他 16 项均使用官方 wheel，并逐一与 PyPI 官方元数据哈希核对通过。
- jieba 官方 sdist SHA-256：`055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2`。
- 构建工具 manifest SHA-256：`8c7fec7405444cfeec8689d189f426a09da1e2d925ee44764b43fca91eca93e6`。
- jieba 使用相同受控输入独立构建两次，产出字节一致；最终 wheel SHA-256：`3917040883aaf70e82288a10a107f6a90be62e088f0a7838f306e062b84ca1f9`。

## Formal Wheelhouse

| 项目 | 事实 |
| --- | --- |
| 路径 | `/srv/knowledge-qa/wheelhouse` |
| wheel 数量 | exact 17 |
| `WHEEL_MANIFEST.json` SHA-256 | `41a0b569d44bbbc412f8fa2c4a081303079cf09ecf4302d3c4b47767c2fdd157` |
| `SHA256SUMS` 文件 SHA-256 | `9d79a7cb6cc335b0e890f5d5b3c95339ea5f1bf12f9815fc85ba63c498ca9a2c` |
| 逐文件校验 | `sha256sum -c SHA256SUMS` 全部通过 |

## 目标 Venv

- 路径：`/srv/knowledge-qa/venvs/20260905-r2`。
- 由外部 bootstrap installer 使用 `--copies --without-pip` 建立，并仅从 formal wheelhouse 以 `--no-index --no-deps --only-binary=:all:` 安装。
- Python 版本为 3.14.5，解释器不是符号链接。
- `requirements.lock` 与已安装分发均为 exact 17 项；无缺失、无额外项、无版本偏差。
- venv 内不存在 pip、setuptools 或 wheel；`usearch.__version__` 为 `2.26.2`，导入未出现依赖或 ABI 错误。

## 双索引只读加载

candidate 根：`/srv/knowledge-qa/releases/knowledge-qa-final-delivery-linux-x86_64-20260905-r2/server-runtime/data/derived/vector/local-vector/candidate/r9-fb70102bbfb4007b4546cf305b237d376cbd077496a4fc72a344feff583d0063/`。

| 索引 | 相对路径 | 对象数 | 维度 | SHA-256 | 结果 |
| --- | --- | ---: | ---: | --- | --- |
| chunk | `chunk-index/index.usearch` | 1482 | 1024 | `0960420c142f3bb286c9ba4107464cd3c4799fba786a5a101c8cd87ce4208b54` | `Index.restore(path, view=True)` 成功 |
| entity | `entity-index/index.usearch` | 22 | 1024 | `5cb069ff8573ec9c8e189e5a1737fbf9c1a92f3b5d57909a92fe9a6b6ad2b33c` | `Index.restore(path, view=True)` 成功 |

两个索引的 loaded count、manifest count、metadata count 与预期一致，metadata `count_deleted=0`，文件 SHA-256 与 candidate manifest 一致。

## Final Verifier 与现网保持

- 使用目标 venv 在 exact release 根执行 `verify_final_delivery.py`，返回 `ok:true`、`errors:[]`；authority、BM25、graph、vectors、SBOM、DLP、evidence、code manifests 与 `SHA256SUMS` 均通过。
- 系统 `/usr/bin/python3` 保持 Python 3.6.8。
- 验证后旧 API `/api/health` 为 HTTP 200，5001 保持监听，`yunji-knowledge-api` 为 running，`yunji-knowledge-graph` 为 healthy。
- 本阶段未执行 Neo4j 写入、public/ops WSGI 启动、切流或重启。
- Python/wheelhouse/venv/USEarch 阶段已经不同代理独立验收通过；本文件仅回写该阶段证据，不代表 TASK-027 完整验收完成。

```text
python_bootstrap_ready: true
trusted_wheelhouse_ready: true
target_venv_created: true
usearch_loaded: true
runtime_active: false
product_accepted: false
```

## 未执行项

- scoped Neo4j candidate 导入及 manifest/receipt 回填。
- 生产 provider、public identity、ops identity 与 secrets 注入。
- public/ops WSGI、5001 切流、真实回滚演练和产品 QA。
