# TASK-027 Python bootstrap 与依赖闭包门禁证据

## 官方源码与隔离安装

| 项目 | 事实 |
| --- | --- |
| Python 版本 | `3.14.5` |
| 官方源码 | `Python-3.14.5.tar.xz` |
| 源码大小 | `23903332` bytes |
| 源码 SHA-256 | `7e32597b99e5d9a39abed35de4693fa169df3e5850d4c334337ffd6a19a36db6` |
| 校验结果 | 本地与远端 SHA-256 一致，Sigstore `messageDigest` 绑定通过 |
| 隔离前缀 | `/opt/knowledge-qa/python/3.14.5` |
| 安装方式 | 源码构建后 `make altinstall`，未替换 `/usr/bin/python3` |

## Bootstrap Installer

- 创建方式：使用隔离 Python 3.14.5 执行 `python3.14 -m venv --copies /opt/knowledge-qa/bootstrap-installer`。
- `/opt/knowledge-qa/bootstrap-installer/bin/python` 为普通文件，不是符号链接。
- bootstrap Python SHA-256：`92cad8810dd2a27ef26a35c77f480243da2ee113dca2c7ca515fb22cf64777b4`。
- 外部锚、源码锚、configure/make/altinstall、RPM 前后清单和最终验证证据目录：`/data/backup/apps/knowledge-qa/python-bootstrap-20260905T150444+0800/`。
- `ssl`、`venv`、SQLite、bz2、lzma、ctypes 与 hashlib 等核心模块导入通过；OpenSSL 为系统受控 `1.1.1k FIPS`。
- 可选 `_zstd` 因 CentOS 8 仓库只提供低于 CPython 3.14 最低要求的版本而未构建；尝试加入的开发包已撤销，RPM 前后清单完全一致。该可选模块不是当前核心阻断。

## 兼容与交付复验

- `/usr/bin/python3 --version` 仍为 `Python 3.6.8`，未更改系统 Python。
- 使用 bootstrap Python 3.14.5 运行精确 release 内 `verify_final_delivery.py`，结果为 `ok:true`、`errors:[]`。
- authority 数据库计数、BM25、scoped graph、双 USEarch 索引摘要、SBOM、DLP、测试证据、代码 manifest 和 `SHA256SUMS` 均通过 verifier。
- 验证后旧 API `/api/health` 返回 HTTP 200，`0.0.0.0:5001` 仍监听，`yunji-knowledge-api` 持续 Up，`yunji-knowledge-graph` 持续 healthy；未重启或切换旧服务。

## 后续依赖阶段结果

- 原依赖闭包门禁已由用户批准的 formal wheelhouse 解除；17 项锁定依赖、jieba 唯一 sdist 构建例外、目标 venv 与 USEarch 双索引的详细事实见 [wheelhouse、venv 与 USEarch](./04-wheelhouse-venv-usearch.md)。
- `/srv/knowledge-qa/venvs/20260905-r2` 已建立，exact 17 项、无 pip/setuptools/wheel，`usearch==2.26.2` 与双索引只读加载通过，并经不同代理独立验收。
- 尚未执行 Neo4j candidate 导入、public/ops WSGI、5001 切换、真实回滚演练或产品 QA。

```text
python_bootstrap_ready: true
trusted_wheelhouse_ready: true
target_venv_created: true
usearch_loaded: true
runtime_active: false
product_accepted: false
```

本文件是实施证据回写，不是独立验收结论。
