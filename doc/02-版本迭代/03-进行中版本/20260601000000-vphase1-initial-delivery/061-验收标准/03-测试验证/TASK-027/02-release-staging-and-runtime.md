# TASK-027 release staging 与运行时门禁证据

## Release Identity

| 对象 | 路径 | 大小 / SHA-256 |
| --- | --- | --- |
| 外层开发交接包 | 本地 `developer-handoff-kg-cloud-v2-offline-20260905-r2.zip` | `b72131c61da816d404118075e8dce92ed6eec1e6c8f32b8a0ce9d317d2e14bd4` |
| final delivery ZIP | `/srv/knowledge-qa/incoming/knowledge-qa-final-delivery-linux-x86_64-20260905-r2.zip` | `15072245` bytes / `cc140e2a3191095ea333c874f559c68043856983ee466392a0cb4e3dc589eaaa` |
| RELEASE_MANIFEST.json | release 根 | `ff9c68d2747587c7c952e7c3dc70aa2b159eabb681733b0c0b00663f9f71586a` |
| SUITE_MANIFEST.json | release 根 | `0a23b3dbf7db6ab601b8bf50c67efb18be586de1d01286266f76a7fe6201f239` |
| SHA256SUMS | release 根 | `a8c8f2c02ca5ff3a5e1067bcd997af596b0bdc54c8871249fd72658f4a783bef` |

## Staging 结果

- 精确 release 根：`/srv/knowledge-qa/releases/knowledge-qa-final-delivery-linux-x86_64-20260905-r2/`。
- 本地与远端 final delivery SHA-256 完全一致。
- ZIP 完整性检查退出 0。
- 包内 `sha256sum -c SHA256SUMS` 退出 0，全部文件通过。
- 解压树符号链接数量为 0。
- 未覆盖旧工程 `/home/soft/knowledge-graph`，未修改 Release 内容。

## 首次 Verifier 结果

- 命令：在精确 release 根执行 `python3 verify_final_delivery.py`。
- 首次结果：退出码 1。
- 原因：宿主 `python3` 为 3.6.8，不能解析 `from __future__ import annotations`。
- 首次失败结果保留，不以其他未锁定解释器覆盖为“成功”。

## 受信 Python 3.14 Verifier 结果

- 官方 Python 3.14.5 与 bootstrap installer 已按独立证据完成后，使用 `/opt/knowledge-qa/bootstrap-installer/bin/python` 在精确 release 根重跑 `verify_final_delivery.py`。
- 结果返回 `ok:true`、`errors:[]`；authority、BM25、graph、双向量摘要、SBOM、DLP、evidence、code manifest 与 `SHA256SUMS` 均通过。
- 首次宿主 Python 失败证据仍保留；后续成功结果不表示锁定依赖、WSGI 或产品验收完成。
- 详细入口：[Python bootstrap 与依赖闭包门禁](./03-python-bootstrap.md)。

## 锁定运行时门禁

- `server-runtime/requirements.lock` 要求 Python 3.14，并锁定 `usearch==2.26.2`、`neo4j==6.2.0`、`waitress==3.0.2` 等依赖。
- Python 3.14.5 已隔离安装到 `/opt/knowledge-qa/python/3.14.5`，系统 Python 未替换。
- `/opt/knowledge-qa/bootstrap-installer/bin/python` 已建立为非符号链接普通文件，外部 SHA-256 锚已在独立证据目录固化。
- 用户已批准以官方 PyPI 为来源的 17 项 formal wheelhouse，并批准 `jieba==0.42.1` 作为唯一 sdist 可复现构建例外；16 个官方 wheel 的官方哈希与 jieba 双构建一致性均通过。
- `/srv/knowledge-qa/wheelhouse` 已包含 exact 17 个运行时 wheel，manifest 和逐文件 `SHA256SUMS` 均通过。
- `/srv/knowledge-qa/venvs/20260905-r2` 已使用外部 bootstrap installer、`--copies --without-pip` 和只离线参数建立；exact 17 项无缺失、无额外包，未使用系统 pip 或公网临时依赖。
- `usearch==2.26.2` 与双索引只读加载已通过；详细入口：[wheelhouse、venv 与 USEarch](./04-wheelhouse-venv-usearch.md)。

## 未执行项

- scoped Neo4j candidate 导入与回填验证。
- provider、public identity、ops identity、外部 hash anchors 和 secrets 注入；仅允许使用合同声明的变量名。
- public/ops WSGI 启动、5001 切换、真实回滚演练、代表性产品 QA 与独立验收。

## 状态

```text
github_delivery_complete: true
python_bootstrap_ready: true
deployment_handoff_ready: false
runtime_active: false
product_accepted: false
```

TASK-027 保持进行中；Python 3.14、bootstrap installer、受信 wheelhouse、目标 venv、USEarch 双索引和目标 venv 下 final verifier 已具备实施及独立验收证据。完整部署仍受后续 provider/identity/Neo4j 写入/WSGI/切流审批与产品验收门禁约束。
