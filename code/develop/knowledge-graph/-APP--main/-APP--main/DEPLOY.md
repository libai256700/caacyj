# DEPLOY.md — 知识图谱问答服务上线部署手册

本手册面向执行部署的技术人员（具备 Linux / Docker 基础，但不了解本系统内部实现）。
按章节顺序执行即可完成一次全新部署。全文命令均以 `root` 或具备 `sudo` 的账号执行，
运行时账号统一使用不可登录的系统用户 `yunji`。

服务本体是一个 Flask + Waitress 的 HTTP 服务，监听 `5001`。数据来自一份**冻结快照**：
SQLite 文本块库、BM25 索引、稠密向量索引、结构化表、Neo4j 子图。

> **第 0.1 节是本手册最重要的部分，务必先读完再动手。**

---

## 0. 部署总览

| 组件 | 形态 | 说明 |
| --- | --- | --- |
| 问答服务 | systemd 服务 `yunji-kg.service` | Python，监听 `127.0.0.1:5001` |
| 图数据库 | Docker 容器 `yunji-kg-neo4j` | Neo4j Community，仅监听 `127.0.0.1` |
| 向量化后端 | 本机 Ollama，模型 `bge-m3` | 服务硬编码访问 `http://127.0.0.1:11434` |
| 生成模型 | 外部大模型 API（HTTPS 出站） | 仅用于改写与措辞组织，事实来自检索结果 |
| 对外入口 | 反向代理 + TLS + 鉴权 | 5001 端口**不得**直接暴露公网 |

### 0.1 必须先知道的四件事（与直觉相反，逐条确认）

**(1) 唯一运行根是仓库内的 `deploy/`，SQLite/索引用软链接，trace 必须直写数据盘。**
代码里 `BASE_DIR` 被写死为 `deploy/`（`deploy/pipeline/server.py`、
`deploy/rag_store/bm25_index.py`、`deploy/rag_store/dense_index.py` 都以源码父目录计算）。
因此 systemd 的 `WorkingDirectory` 与 `ExecStart` 必须指向
`/opt/yunji/knowledge-graph/deploy`，不能把仓库根当成运行根。服务启动前按第 3.1 节为
`rag_chunks.db`、`rag_index` 创建指向 `/opt/yunji/data` 的软链接；两个 trace 由环境变量
直接指向数据盘上的单硬链接普通文件，**不得建立软链接**。配置完成后代码树本体由部署账号持有、对运行账号只读，
`ProtectSystem=strict` 与 `ReadWritePaths=/opt/yunji/data` 可以同时成立。

**(2) 凭据不落盘（本交付版已处理，只需核对）。**
上游版本会在启动时把 **Neo4j 明文密码**写进代码目录下的 `neo4j-docker/.neo4j_pass` 与 `.env`。
本交付版已把 `neo4j_runtime.ensure_runtime_secret_files()` 改为空实现，
`pipeline/server.py` 的 `load_secret_env()` 也改为只读进程环境变量，**不再写任何凭据文件**。
核对方式：部署后确认代码目录下没有生成 `neo4j-docker/` 目录。

**`NEO4J_PASSWORD` 是硬性启动条件**：`rag_store/kg_recall.py` 在 import 阶段即解析密码，
未设置时进程直接启动失败（快速失败，符合预期）。请务必在 systemd 环境文件中提供。

**(3) 这些环境变量在代码里不存在，配了等于没配。**
`AGENTIC_KG_BOUNDED_EXECUTOR_ENABLED`、`RAG_RUNTIME_READ_ONLY`、
`RAG_PERSIST_NEO4J_SECRET_FILES`、`RAG_BASE_DIR`、`RAG_BM25_INDEX_DIR`、
`RAG_DENSE_INDEX_PATH`、`RAG_MODEL_CONFIG_PATH`。
本手册不使用它们。若你在别处看到含这些变量的配置模板，那份模板已过期。

**(4) 本交付版已移除全部写接口，但入口层防线仍然必须做。**
上游版本注册了 10 个图谱写方法（entity 3 个、edge 2 个、node 3 个、edge-3d 2 个）、
任意 Cypher 执行接口 `/api/cypher`，以及演示接口 `/api/presentation/<route>`。
**本交付版已将这 12 个方法/路径组合整体切除**，剩余端点全部只读：
`/`、`/api/health`、`/api/stats`、`/api/graph`、`/search`、`/api/search`、
`/api/ask`、`/api/entity/<id>`(GET)、`/api/export`、`/api/graph-3d`。
即便如此，纵深防御两条仍然必须做，不可因"已无写接口"而省略：
① 只绑 `127.0.0.1`；② 反向代理只放行 `/api/ask` 与 `/api/health`（第 8.2 节）。
注意 `/api/export` 会导出整张图，`/api/stats` 会暴露规模信息，都不应对外开放。

---

## 1. 前置条件

### 1.1 操作系统与基础软件

- Linux x86_64，systemd 发行版（Ubuntu 22.04 / 24.04 或 Rocky 9 均可）
- Docker Engine 24+ 与 Docker Compose v2（`docker compose version` 可用）
- `curl`、`tar`、`gzip`、`sha256sum`、`git`、GitHub CLI `gh`、`jq`、`sqlite3`、`openssl`
- 当前部署账号已通过 `gh auth status` 验证可读取私有仓 `CAACYJ/-APP-`
- 磁盘：数据与索引约 1.5 GB，Neo4j 数据目录建议预留 10 GB，日志另留 5 GB
- 内存：建议 8 GB 起（Neo4j 堆 2 GB + 页缓存 1 GB，问答进程约 1 GB，Ollama 约 2 GB）

### 1.2 Python

- **Python 3.11 或更高**（源环境实测 3.14.6）
- 使用独立虚拟环境，不要装进系统 Python

依赖清单（版本为源环境实测基线）：

| 包 | 版本 | 用途 |
| --- | --- | --- |
| `Flask` | 3.1.3 | HTTP 框架 |
| `flask-cors` | 6.0.2 | 跨域白名单 |
| `waitress` | 3.0.2 | 生产 WSGI 服务器（缺失时静默回退 Flask 开发服务器，**必须安装**） |
| `neo4j` | 6.2.0 | Neo4j 官方驱动 |
| `Whoosh` | 2.7.4 | BM25 稀疏检索 |
| `jieba` | 0.42.1 | 中文分词 |

> **不需要 `openai` 包。** 服务调用大模型走的是标准库 `urllib` 直接 POST，
> 没有引用任何模型厂商 SDK。装了也不会被用到。

```bash
sudo useradd -r -s /usr/sbin/nologin -d /opt/yunji yunji || true
sudo mkdir -p /opt/yunji
sudo python3 -m venv /opt/yunji/venv
sudo /opt/yunji/venv/bin/pip install --upgrade pip
sudo /opt/yunji/venv/bin/pip install \
  "Flask==3.1.3" "flask-cors==6.0.2" "waitress==3.0.2" \
  "neo4j==6.2.0" "Whoosh==2.7.4" "jieba==0.42.1"
```

> **Whoosh 兼容性预检（必做）**：Whoosh 2.7.4 自 2016 年停止维护，未适配 Python 3.12+。
> 装完立刻验证，失败则改用 API 兼容的 `whoosh-reloaded`（注意：换包后**索引二进制格式可能不同，
> 必须由发布方重建 BM25 索引**，不能在服务器上就地转换）：
> ```bash
> sudo /opt/yunji/venv/bin/python -c "import whoosh, whoosh.index; print(whoosh.versionstring())"
> ```

### 1.3 Neo4j

- Neo4j Community 固定为 `2026.04.0`，与迁移源容器的实测版本一致；镜像同时固定
  多架构 OCI index digest：
  `neo4j:2026.04.0@sha256:7d8d70f78c0c55830a162e6ae212799649b0cfd349dbfe413aab8124f7cabf1b`。
  驱动固定为 6.2.0。**不要改成 `neo4j:latest`**，否则镜像会漂移、回滚无法复现。
- 以 Docker 运行，端口只绑 `127.0.0.1`
- 需要 APOC 插件

### 1.4 向量化后端（Ollama）

问答链路在**每次请求**都要把用户问题向量化（`pipeline/server.py` 的 `get_embedding()`），
该地址在代码里是硬编码的 `http://127.0.0.1:11434/api/embeddings`，模型名 `bge-m3`。因此：

- Ollama 必须与问答服务**装在同一台机器**，监听默认端口 11434
- 必须预先拉取 `bge-m3` 模型
- 该模型维度 1024，必须与 Release 中的稠密索引一致，**不得换别的嵌入模型**
- Ollama 不可用时不会崩服务，而是记 `degraded_reasons: embedding_failed:*` 后
  **静默降级**成"只有关键词检索"，表现为答案质量下降——属于最难发现的故障，
  务必纳入巡检（第 10.2 节）

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull bge-m3
# 自检：应返回 1024
curl -s http://127.0.0.1:11434/api/embeddings \
  -d '{"model":"bge-m3","prompt":"自检"}' | jq '.embedding | length'
```

### 1.5 出站网络

服务需要访问外部大模型 API（HTTPS 443）用于问题改写与答案措辞组织。
若公司出口有白名单策略，请放行 `https://api.deepseek.com` 以及 `config.json` 中
`models.doubao_mini.base_url` 对应的域名。

**除此之外不需要任何其他出站访问。** 代码里另有两条联网检索通路（Serper、百度千帆），
它们只在对应密钥存在时才启用；本次交付**不配置**这些密钥，并在第 7 章用
`RAG_ALLOWED_RETRIEVAL_SOURCES` 从检索通道层面再关一道。

---

## 2. 目录布局与权限

仓库根与运行根不是同一个目录。仓库固定放在 `/opt/yunji/knowledge-graph`，唯一运行根为
`/opt/yunji/knowledge-graph/deploy`。SQLite 与索引采用
**真实数据放 `/opt/yunji/data`、运行根下用软链接指过去**的方式分根；trace 不经代码目录，
由 systemd 环境变量直指数据盘普通文件。实际写入只落在数据盘。

```
/opt/yunji/
├── venv/
├── knowledge-graph/               # Git 仓库根
│   ├── eval/                         # Git 跟踪，只读评测契约
│   │   ├── online_subset_20260803.json
│   │   ├── cloud80_gold_standard_v1.schema.json
│   │   └── cloud80_gold_standard_v1.json       # 80 条 pending 模板
│   └── deploy/                    # 唯一运行根
│       ├── pipeline/
│       │   ├── server.py
│       │   ├── config.example.json
│       │   └── config.json        # 服务器本地生成，进程只读
│       ├── rag_store/
│       ├── data/                  # 随代码交付的 canonical / exclusions 源
│       ├── rag_chunks.db -> /opt/yunji/data/rag_chunks.db
│       └── rag_index     -> /opt/yunji/data/rag_index
├── data/                          # 真实数据根（唯一可写）
│   ├── rag_chunks.db
│   ├── rag_index/
│   │   ├── bm25/
│   │   ├── dense_bge_m3.sqlite
│   │   └── csa_cache.sqlite       # 服务自建
│   ├── canonical/                 # 结构化表（地面站考试条件）
│   ├── exclusions/
│   │   └── exclusions.json
│   └── eval/
│       ├── query_traces.jsonl
│       └── remote_shadow_traces.jsonl
├── knowledge_base/                # 原始文档留档（只读、不参与运行）
└── neo4j/
    ├── data/  logs/  import/  plugins/
```

### 2.1 建目录

```bash
sudo mkdir -p /opt/yunji/{data,knowledge_base,neo4j,release}
sudo mkdir -p /opt/yunji/data/{rag_index/bm25,canonical,exclusions,eval}
sudo mkdir -p /opt/yunji/neo4j/{data,logs,import,plugins}
```

SQLite/索引软链接与 trace 普通文件在第 3 章 clone 完代码之后准备（见 3.1）。

### 2.2 权限

代码仓由执行部署的账号维护，运行账号 `yunji` 只有组读取/执行权限；`ProtectSystem=strict`
会在进程侧再加一层只读保护。以下代码权限命令在第 3 章 clone 后执行；数据权限现在即可执行。

```bash
# 代码：clone 后由部署账号可更新，运行账号只读执行
if [ -d /opt/yunji/knowledge-graph/.git ]; then
  sudo chown -R "$(id -u)":yunji /opt/yunji/knowledge-graph
  sudo chmod -R u=rwX,g=rX,o= /opt/yunji/knowledge-graph
fi

# 数据：运行账号可写（SQLite 要写 WAL，追踪日志要追加）
sudo chown -R yunji:yunji /opt/yunji/data
sudo chmod -R 750 /opt/yunji/data

# config.json 含密钥引用，收紧
sudo chown "$(id -u)":yunji /opt/yunji/knowledge-graph/deploy/pipeline/config.json 2>/dev/null || true
sudo chmod 640 /opt/yunji/knowledge-graph/deploy/pipeline/config.json 2>/dev/null || true

# Neo4j 挂载目录（容器内 uid/gid 均为 7474）
sudo chown -R 7474:7474 /opt/yunji/neo4j
sudo chmod -R 750 /opt/yunji/neo4j
```

### 2.3 原始文档目录（硬性要求）

`/opt/yunji/knowledge_base` 用于留档四个文档域的原始文本，**运行时不读取它**。它必须：

1. **位于任何 Web / 静态资源目录之外**（不得放在 `/var/www`、Nginx `root`/`alias`
   覆盖的路径下，也不得被反向代理以任何形式映射为 URL）；
2. 权限 `chmod 700`，属主为 `root`（服务账号不需要读它）；
3. 不建立任何指向它的软链接到 Web 目录。

```bash
sudo chown -R root:root /opt/yunji/knowledge_base
sudo chmod 700 /opt/yunji/knowledge_base
sudo -u yunji ls /opt/yunji/knowledge_base   # 期望：Permission denied
```

> 内容资产保护要求：原始文档一旦被 Web 目录覆盖，等于全文对外公开。
> 部署完成后请把该校验命令纳入巡检脚本。

---

## 3. 获取代码

本基线使用两个独立版本标识，禁止混用或用 `main` 代替：

- 代码 tag：`kg-code-20260804-01`
- 数据 Release tag：`snapshot-20260803`（第 4 章）

首次安装与已有部署升级必须走各自分支。私有仓认证使用当前部署账号的 `gh` 登录态；
不要把 GitHub token 写入命令行或配置文件。

```bash
set -euo pipefail

REPO=CAACYJ/-APP-
REPO_ROOT=/opt/yunji/knowledge-graph
CODE_TAG=kg-code-20260804-01

if [ ! -e "$REPO_ROOT" ]; then
  # 首次安装：gh 使用当前部署账号的私有仓授权。
  sudo install -d -m 0750 -o "$(id -u)" -g "$(id -g)" "$REPO_ROOT"
  gh repo clone "$REPO" "$REPO_ROOT"
elif [ -d "$REPO_ROOT/.git" ]; then
  # 已有部署升级：先拒绝覆盖任何已跟踪修改。
  tracked_status="$(git -C "$REPO_ROOT" status --short --untracked-files=no)" || exit 1
  [ -z "$tracked_status" ] || { printf '%s\n' "$tracked_status"; exit 1; }

  # 旧版曾把整个 eval/ 指向数据盘。只移除这个已知目标的软链接，不删除数据盘内容。
  if [ -L "$REPO_ROOT/eval" ]; then
    [ "$(readlink "$REPO_ROOT/eval")" = "/opt/yunji/data/eval" ] \
      || { echo "未知 eval 软链接目标，停止升级"; exit 1; }
    unlink "$REPO_ROOT/eval"
  fi
else
  echo "$REPO_ROOT 已存在但不是 Git 仓库，停止部署"
  exit 1
fi

origin_url="$(git -C "$REPO_ROOT" remote get-url origin)"
case "$origin_url" in
  https://github.com/CAACYJ/-APP-|https://github.com/CAACYJ/-APP-.git|\
  git@github.com:CAACYJ/-APP-|git@github.com:CAACYJ/-APP-.git)
    ;;
  *)
    echo "origin 不是 CAACYJ/-APP-：$origin_url"
    exit 1
    ;;
esac

git -C "$REPO_ROOT" fetch --tags --prune origin
git -C "$REPO_ROOT" rev-parse --verify "refs/tags/$CODE_TAG^{commit}" >/dev/null
git -C "$REPO_ROOT" checkout --detach "$CODE_TAG"
test "$(git -C "$REPO_ROOT" describe --tags --exact-match)" = "$CODE_TAG"
git -C "$REPO_ROOT" rev-parse HEAD   # 记录到上线单，回滚时使用
test -f "$REPO_ROOT/deploy/pipeline/server.py"
test -f "$REPO_ROOT/eval/online_subset_20260803.json"
bash "$REPO_ROOT/skills/knowledge-graph-cloud/scripts/verify.sh"
```

**只允许 checkout 上述代码 tag，不要跟踪分支 HEAD。** 数据另按第 4 章的数据 tag 获取。

### 3.1 建立数据软链接与 trace 普通文件

```bash
RUNTIME_ROOT=/opt/yunji/knowledge-graph/deploy

link_exact() {
  link=$1
  target=$2
  if [ -L "$link" ]; then
    [ "$(readlink "$link")" = "$target" ] \
      || { echo "未知软链接目标：$link"; exit 1; }
  elif [ -e "$link" ]; then
    echo "$link 已存在且不是软链接；不自动删除，停止部署"
    exit 1
  else
    ln -s "$target" "$link"
  fi
}

link_exact "$RUNTIME_ROOT/rag_chunks.db" /opt/yunji/data/rag_chunks.db
link_exact "$RUNTIME_ROOT/rag_index" /opt/yunji/data/rag_index

# trace logger 使用 O_NOFOLLOW、单硬链接和哈希链校验；目标必须是数据盘普通文件。
sudo touch /opt/yunji/data/eval/query_traces.jsonl \
  /opt/yunji/data/eval/remote_shadow_traces.jsonl
sudo chown yunji:yunji /opt/yunji/data/eval/query_traces.jsonl \
  /opt/yunji/data/eval/remote_shadow_traces.jsonl
sudo chmod 600 /opt/yunji/data/eval/query_traces.jsonl \
  /opt/yunji/data/eval/remote_shadow_traces.jsonl
sudo chmod 700 /opt/yunji/data/eval

ls -l "$RUNTIME_ROOT/rag_chunks.db" "$RUNTIME_ROOT/rag_index" /opt/yunji/data/eval/*.jsonl
test -f /opt/yunji/knowledge-graph/eval/online_subset_20260803.json
test -L "$RUNTIME_ROOT/rag_chunks.db"
test -L "$RUNTIME_ROOT/rag_index"
for trace in /opt/yunji/data/eval/query_traces.jsonl \
             /opt/yunji/data/eval/remote_shadow_traces.jsonl; do
  test -f "$trace" && test ! -L "$trace"
  test "$(stat -c %h "$trace")" = 1
  test "$(stat -c %a "$trace")" = 600
done
tracked_status="$(git -C /opt/yunji/knowledge-graph status --short --untracked-files=no)" || exit 1
test -z "$tracked_status" || { printf '%s\n' "$tracked_status"; exit 1; }
```

### 3.2 交付完整性自检

```bash
cd /opt/yunji/knowledge-graph/deploy
# 这 4 个随码数据文件缺任何一个，服务都不报错，但答案质量会塌陷
for f in rag_store/source_doc_aliases.json rag_store/duplicate_passages.json \
         rag_store/superseded_passages.json rag_store/regulation_timeline.json; do
  test -s "$f" || { echo "缺失或为空：$f，停止部署"; exit 1; }
  echo "OK   $f"
done
# 不能只看文件非空：这些运行时读取器遇到损坏 JSON 会回退为空登记。
python3 - <<'PY'
import json
from pathlib import Path

contracts = {
    "rag_store/source_doc_aliases.json": ("aliases", dict),
    "rag_store/duplicate_passages.json": ("entries", list),
    "rag_store/superseded_passages.json": ("passages", list),
    "rag_store/regulation_timeline.json": ("documents", dict),
}
for filename, (field, expected_type) in contracts.items():
    path = Path(filename)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"无法解析治理文件 {filename}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"治理文件顶层必须为对象: {filename}")
    value = payload.get(field)
    if not isinstance(value, expected_type) or not value:
        raise SystemExit(f"治理文件字段必须为非空 {expected_type.__name__}: {filename}#{field}")
    if isinstance(value, dict):
        valid = all(
            isinstance(key, str) and key.strip()
            and (
                isinstance(item, dict)
                or isinstance(item, list) and item
            )
            for key, item in value.items()
        )
    else:
        valid = all(isinstance(item, dict) and item for item in value)
    if not valid:
        raise SystemExit(f"治理文件包含空键或错误条目类型: {filename}#{field}")
    print(f"JSON OK   {filename}#{field}")
PY
# 确认凭据不落盘：函数除 docstring 外只能有 `return None`，否则立即停止。
python3 - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path("neo4j_runtime.py").read_text(encoding="utf-8"))
matches = [
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "ensure_runtime_secret_files"
]
if len(matches) != 1:
    raise SystemExit("ensure_runtime_secret_files 定义数量异常")
body = matches[0].body
if (
    body
    and isinstance(body[0], ast.Expr)
    and isinstance(body[0].value, ast.Constant)
    and isinstance(body[0].value.value, str)
):
    body = body[1:]
valid = (
    len(body) == 1
    and isinstance(body[0], ast.Return)
    and isinstance(body[0].value, ast.Constant)
    and body[0].value.value is None
)
if not valid:
    raise SystemExit("ensure_runtime_secret_files 不是凭据不落盘的空实现")
print("OK  凭据不落盘")
PY

# 即使代码树残留旧 .env / .neo4j_pass，缺少进程环境变量也必须失败。
env -u NEO4J_PASSWORD -u NEO4J_PASS python3 - <<'PY'
from neo4j_runtime import resolve_neo4j_password

try:
    resolve_neo4j_password()
except FileNotFoundError:
    print("OK  Neo4j 密码仅接受进程环境变量")
else:
    raise SystemExit("Neo4j 密码解析仍接受代码树文件，停止部署")
PY

# 确认写接口已移除（应无输出）
if unexpected_routes="$(grep -nE '@app\.route.*(POST|PUT|DELETE)' pipeline/server.py \
  | grep -v "/api/ask")"; then
  printf '仍存在写接口，停止部署：\n%s\n' "$unexpected_routes"
  exit 1
else
  echo "OK  仅剩 /api/ask 接受 POST"
fi

# canonical 与 exclusions 是数据安装的强依赖，不允许静默缺失。
for f in data/canonical/ground_station_exam_cases.csv \
         data/canonical/ground_station_exam_conditions.csv \
         data/canonical/ground_station_exam_skills.csv \
         data/exclusions/exclusions.json; do
  test -s "$f" || { echo "缺失或为空：$f"; exit 1; }
done
```

---

## 4. 下载并校验数据附件

数据不进 Git，走 GitHub Release 附件交付。该 Release 只有两个压缩包与一份汇总
`SHA256SUMS`，没有五套旧式分包，也没有逐附件 `.sha256` 文件。
**先校验 `SHA256SUMS` 自身的固定摘要，再校验两个压缩包；任一步失败都不得继续。**

### 4.1 附件清单

实际发布的附件只有三个（tag = `snapshot-20260803`）：

| 附件 | 内容 | 落地位置 |
| --- | --- | --- |
| `kg-data-20260803.tar.gz` | `rag_chunks.snapshot.db`（文本块裁剪快照，35 文档 / 3,629 块）+ `rag_index/`（BM25 目录 + `dense_bge_m3.sqlite` 向量索引） | 解包到 `/opt/yunji/data/`，其中 db 重命名为 `rag_chunks.db` |
| `kg-graph-20260803.tar.gz` | `graph/nodes.jsonl`、`graph/rels.jsonl`、`graph/schema.json`、`graph/import_graph.py` | 解包到本次 Release 工作目录，导入后保留作回滚证据 |
| `SHA256SUMS` | 两个压缩包的校验和 | — |

结构化表（地面站考试条件）与排除规则**随代码仓交付**，位于 `deploy/data/canonical/` 与
`deploy/data/exclusions/`，不在 Release 附件中。

### 4.2 下载与校验

```bash
REPO=CAACYJ/-APP-
DATA_TAG=snapshot-20260803
DATA_DATE=20260803
WORK=/opt/yunji/release/$DATA_TAG

sudo install -d -m 0700 -o "$(id -u)" -g "$(id -g)" "$WORK"
test -z "$(find "$WORK" -mindepth 1 -maxdepth 1 -print -quit)" \
  || { echo "$WORK 非空；请使用新的工作目录，停止下载"; exit 1; }
gh release download "$DATA_TAG" --repo "$REPO" --dir "$WORK" \
  --pattern "kg-data-$DATA_DATE.tar.gz" \
  --pattern "kg-graph-$DATA_DATE.tar.gz" \
  --pattern SHA256SUMS

cd "$WORK"
test -f "kg-data-$DATA_DATE.tar.gz"
test -f "kg-graph-$DATA_DATE.tar.gz"
test -f SHA256SUMS

# 先钉住校验清单本身，再用它校验两个压缩包。
echo 'db99bf7a8ffe429637b2abfbad4318ffa2e4d0b7d5865b80389932889cd1bbe5  SHA256SUMS' \
  | sha256sum -c -
sha256sum -c SHA256SUMS
```

固定摘要应为：

- `kg-data-20260803.tar.gz`：`7e0bfe322184abe00adf6dadf727e3cd9811e8886f68388dc143d33199f0bce6`
- `kg-graph-20260803.tar.gz`：`e81b0f34fa0a6c61696501af151357b865b74fa67ca00b59bb845db0bdef8821`

### 4.3 就位

```bash
REPO_ROOT=/opt/yunji/knowledge-graph
RUNTIME_ROOT=$REPO_ROOT/deploy
STAGE=$WORK/extracted

test ! -e "$STAGE" || { echo "$STAGE 已存在；请换空工作目录，禁止叠加解包"; exit 1; }
mkdir -m 0700 "$STAGE"
tar --no-same-owner --no-same-permissions -xzf "kg-data-$DATA_DATE.tar.gz" -C "$STAGE"
tar --no-same-owner --no-same-permissions -xzf "kg-graph-$DATA_DATE.tar.gz" -C "$STAGE"

# 实际三附件契约：缺一项都停止，不用不存在的旧附件名兜底。
for f in "$STAGE/rag_chunks.snapshot.db" \
         "$STAGE/rag_index/dense_bge_m3.sqlite" \
         "$STAGE/graph/nodes.jsonl" \
         "$STAGE/graph/rels.jsonl" \
         "$STAGE/graph/schema.json" \
         "$STAGE/graph/import_graph.py"; do
  test -s "$f" || { echo "附件内容缺失或为空：$f"; exit 1; }
done
test -d "$STAGE/rag_index/bm25"
test -z "$(find "$STAGE" -type l -print -quit)" || { echo "附件含软链接，停止部署"; exit 1; }

# 升级时必须确认问答进程已停；只有明确的 unit-not-found 才按首次安装处理。
LOAD_STATE="$(systemctl show yunji-kg.service --property=LoadState --value 2>/dev/null)" \
  || { echo "无法读取 yunji-kg.service 状态，停止部署"; exit 1; }
case "$LOAD_STATE" in
  not-found)
    echo "yunji-kg.service 尚未安装，按首次安装继续"
    ;;
  loaded)
    sudo systemctl stop yunji-kg.service \
      || { echo "yunji-kg.service 停止失败，禁止切换数据"; exit 1; }
    test "$(systemctl show yunji-kg.service --property=ActiveState --value)" = inactive \
      || { echo "yunji-kg.service 未进入 inactive，禁止切换数据"; exit 1; }
    ;;
  *)
    echo "yunji-kg.service LoadState 异常：$LOAD_STATE，停止部署"
    exit 1
    ;;
esac

# 保留本次切换前的数据作为回滚点，不覆盖未知类型或软链接。
BACKUP="$WORK/pre-install-data"
test ! -e "$BACKUP" || { echo "$BACKUP 已存在，禁止覆盖回滚点"; exit 1; }
sudo install -d -m 0700 "$BACKUP"
if [ -e /opt/yunji/data/rag_chunks.db ]; then
  [ -f /opt/yunji/data/rag_chunks.db ] && [ ! -L /opt/yunji/data/rag_chunks.db ] \
    || { echo "rag_chunks.db 不是普通文件，停止部署"; exit 1; }
  sudo mv /opt/yunji/data/rag_chunks.db "$BACKUP/rag_chunks.db"
fi
if [ -e /opt/yunji/data/rag_index ]; then
  [ -d /opt/yunji/data/rag_index ] && [ ! -L /opt/yunji/data/rag_index ] \
    || { echo "rag_index 不是普通目录，停止部署"; exit 1; }
  sudo mv /opt/yunji/data/rag_index "$BACKUP/rag_index"
fi
if [ -e /opt/yunji/data/canonical ]; then
  [ -d /opt/yunji/data/canonical ] && [ ! -L /opt/yunji/data/canonical ] \
    || { echo "canonical 不是普通目录，停止部署"; exit 1; }
  sudo mv /opt/yunji/data/canonical "$BACKUP/canonical"
fi
if [ -e /opt/yunji/data/exclusions ]; then
  [ -d /opt/yunji/data/exclusions ] && [ ! -L /opt/yunji/data/exclusions ] \
    || { echo "exclusions 不是普通目录，停止部署"; exit 1; }
  sudo mv /opt/yunji/data/exclusions "$BACKUP/exclusions"
fi

sudo install -m 0640 "$STAGE/rag_chunks.snapshot.db" /opt/yunji/data/rag_chunks.db
sudo install -d -m 0750 /opt/yunji/data/rag_index
sudo cp -a "$STAGE/rag_index/." /opt/yunji/data/rag_index/

# canonical 与 exclusions 随代码 tag 交付，必须显式复制到数据盘。
sudo install -d -m 0750 /opt/yunji/data/canonical /opt/yunji/data/exclusions
for f in ground_station_exam_cases.csv ground_station_exam_conditions.csv \
         ground_station_exam_skills.csv; do
  test -s "$RUNTIME_ROOT/data/canonical/$f" || { echo "随码数据缺失：$f"; exit 1; }
  sudo install -m 0640 "$RUNTIME_ROOT/data/canonical/$f" "/opt/yunji/data/canonical/$f"
done
test -s "$RUNTIME_ROOT/data/exclusions/exclusions.json" \
  || { echo "随码排除规则缺失"; exit 1; }
sudo install -m 0640 "$RUNTIME_ROOT/data/exclusions/exclusions.json" \
  /opt/yunji/data/exclusions/exclusions.json

sudo chown -R yunji:yunji /opt/yunji/data
sudo find /opt/yunji/data -type d -exec chmod 750 {} \;
sudo find /opt/yunji/data -type f -exec chmod 640 {} \;
sudo chmod 700 /opt/yunji/data/eval
sudo find /opt/yunji/data/eval -maxdepth 1 -type f \
  \( -name '*.jsonl' -o -name '*.jsonl.lock' \) -exec chmod 600 {} \;

# 自检 1：快照完整、计数与本 Release 固定基线一致。
test "$(sudo -u yunji sqlite3 /opt/yunji/data/rag_chunks.db \
  'PRAGMA integrity_check;')" = ok
test "$(sudo -u yunji sqlite3 /opt/yunji/data/rag_chunks.db \
  'SELECT count(*) FROM documents;')" = 35
test "$(sudo -u yunji sqlite3 /opt/yunji/data/rag_chunks.db \
  'SELECT count(*) FROM chunks;')" = 3629

# 自检 2（重要）：documents 与 chunks 必须全部属于四域；打印不是门禁。
OUT_OF_SCOPE_DOCS="$(sudo -u yunji sqlite3 /opt/yunji/data/rag_chunks.db "
  SELECT DISTINCT 'documents:' || COALESCE(doc_name, '<NULL>')
  FROM documents
  WHERE doc_name IS NULL OR NOT (
    doc_name GLOB '政策法规_*' OR doc_name GLOB '理论题库_*' OR
    doc_name GLOB '实操题库_*' OR doc_name GLOB '无人机理论书籍_*'
  )
  UNION
  SELECT DISTINCT 'chunks:' || COALESCE(doc_name, '<NULL>')
  FROM chunks
  WHERE doc_name IS NULL OR NOT (
    doc_name GLOB '政策法规_*' OR doc_name GLOB '理论题库_*' OR
    doc_name GLOB '实操题库_*' OR doc_name GLOB '无人机理论书籍_*'
  );
")" || { echo "四域 SQL 门禁执行失败"; exit 1; }
test -z "$OUT_OF_SCOPE_DOCS" || {
  printf '发现四域外文档，停止部署：\n%s\n' "$OUT_OF_SCOPE_DOCS"
  exit 1
}
echo "OK  documents/chunks 全部属于四域"

# 自检 3：运行时所需索引、结构化表与排除规则全部存在。
test -d /opt/yunji/data/rag_index/bm25
test -s /opt/yunji/data/rag_index/dense_bge_m3.sqlite
test "$(find /opt/yunji/data/canonical -maxdepth 1 -name '*.csv' -type f | wc -l)" = 3
test -s /opt/yunji/data/exclusions/exclusions.json

# 自检 4：BM25 / Dense 数量与来源指纹必须一致，不能把旧索引和新快照混用。
test "$(jq -r '.indexed_docs' /opt/yunji/data/rag_index/bm25/manifest.json)" = 3629
test "$(sqlite3 /opt/yunji/data/rag_index/dense_bge_m3.sqlite \
  'SELECT count(*) FROM embeddings;')" = 3629
BM25_FP=$(jq -r '.source.fingerprint' /opt/yunji/data/rag_index/bm25/manifest.json)
DENSE_FP=$(sqlite3 /opt/yunji/data/rag_index/dense_bge_m3.sqlite \
  "SELECT json_extract(value,'$.fingerprint') FROM manifest WHERE key='source';")
test -n "$BM25_FP"
test "$BM25_FP" = "$DENSE_FP"
```

图谱导入文件保留在 `$STAGE/graph`，第 5 章直接从这里导入；不要再套一层 `graph/graph`。

---

## 5. Neo4j：起容器并导入子图

### 5.1 生成独立密码并起容器

密码**在本服务器现场生成**，不要复用任何其他环境的密码。

```bash
sudo mkdir -p /etc/yunji && sudo chmod 700 /etc/yunji
NEO_PASS="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"

printf 'NEO4J_PASSWORD=%s\n' "$NEO_PASS" | sudo tee /etc/yunji/kg.env >/dev/null
sudo chown root:yunji /etc/yunji/kg.env && sudo chmod 640 /etc/yunji/kg.env

printf 'NEO4J_PASSWORD=%s\n' "$NEO_PASS" | sudo tee /opt/yunji/neo4j/.env >/dev/null
sudo chmod 600 /opt/yunji/neo4j/.env
unset NEO_PASS
```

两份文件各管各的：compose 的 `.env` 只有 Neo4j 密码，避免模型密钥被带进容器环境。

`/opt/yunji/neo4j/docker-compose.yml`：

```yaml
services:
  neo4j:
    image: neo4j:2026.04.0@sha256:7d8d70f78c0c55830a162e6ae212799649b0cfd349dbfe413aab8124f7cabf1b
    container_name: yunji-kg-neo4j
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    volumes:
      - ./data:/data
      - ./logs:/logs
      - ./import:/var/lib/neo4j/import
      - ./plugins:/plugins
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - NEO4J_server_memory_heap_initial__size=1G
      - NEO4J_server_memory_heap_max__size=2G
      - NEO4J_server_memory_pagecache_size=1G
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_security_procedures_unrestricted=apoc.*
      - NEO4J_apoc_import_file_enabled=true
      - NEO4J_apoc_export_file_enabled=false
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p \"$$NEO4J_PASSWORD\" 'RETURN 1' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
```

```bash
cd /opt/yunji/neo4j
sudo docker compose up -d
sudo docker compose ps          # STATUS 应为 healthy
```

### 5.2 建约束与索引，再导入数据

**顺序不能颠倒**：先约束/索引，后数据。否则导入会产生重复节点且大幅变慢。

```bash
DATA_TAG=snapshot-20260803
WORK=/opt/yunji/release/$DATA_TAG
STAGE=$WORK/extracted

# 导入脚本自带约束/索引重建，无需单独执行 cypher 文件。
# 凭据只在 root 子进程内从 EnvironmentFile 读取——脚本不接受命令行明文密码。
# 目标库必须为空，非空时脚本会拒绝执行以防误覆盖。
sudo sh -c '
  set -a
  . /etc/yunji/kg.env
  set +a
  export NEO4J_URI=bolt://127.0.0.1:7687
  export NEO4J_USER=neo4j
  cd "$1"
  exec /opt/yunji/venv/bin/python import_graph.py
' sh "$STAGE/graph"

# 只想重跑校验（不重新导入）：
# 把上面 exec 行末改为：import_graph.py --verify
```

`kg.env` 权限为 `root:yunji 0640`，部署账号不需要直接读取它；上面的 root 子进程负责导出变量，
避免把密码放进命令行、shell 历史或当前账号环境。

### 5.3 导入结果核对

```bash
sudo docker exec -i yunji-kg-neo4j sh -c \
  'cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n) AS nodes;"'
sudo docker exec -i yunji-kg-neo4j sh -c \
  'cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH ()-[r]->() RETURN count(r) AS relationships;"'
```

期望值：节点 **8,901**，关系 **81,889**。导入脚本结束时会自动打印这两项的实际值与期望值比对，
并检查范围外标签必须为 0；任何一项不符会明确报错。人工复核用上面的 cypher 命令，
**必须完全一致**。不一致说明导入中断，清库后重来：

```bash
sudo docker exec -i yunji-kg-neo4j sh -c \
  'cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) DETACH DELETE n;"'
```

---

## 6. config.json 生成

### 6.1 复制模板

```bash
RUNTIME_ROOT=/opt/yunji/knowledge-graph/deploy
sudo cp "$RUNTIME_ROOT/pipeline/config.example.json" "$RUNTIME_ROOT/pipeline/config.json"
sudo chown "$(id -u)":yunji "$RUNTIME_ROOT/pipeline/config.json"
sudo chmod 640 "$RUNTIME_ROOT/pipeline/config.json"
```

文件名和位置都是代码里写死的（`deploy/pipeline/config.json`），不要改名或移走。
缺失时服务能正常启动，但**第一次真实提问才会报错**，启动自检发现不了。

### 6.2 密钥引用方式

`config.json` 中 `api_key` 支持两种写法：

- `"secretref:变量名"` —— 运行时从**环境变量**读取同名变量（推荐，保持模板原样）
- 明文字符串 —— 兼容写法，**本次部署禁止使用**

真值放进 systemd 的 `EnvironmentFile`：

```bash
sudo tee -a /etc/yunji/kg.env >/dev/null <<'EOF'
KG_DEEPSEEK_API_KEY=<在本服务器侧新申请的密钥>
KG_DOUBAO_API_KEY=<在本服务器侧新申请的密钥>
EOF
sudo chmod 640 /etc/yunji/kg.env
```

**关于回答模型链的三个事实：**

- `models.flash` 是唯一主通道，每次请求最多调用一次，预算 2.4 秒；
- `models.doubao_mini` 是唯一备用通道，主通道失败后最多调用一次，预算 2.8 秒；
- 两者共享 5.2 秒串行总预算并关闭思考模式。图谱抽取使用的 Doubao Pro **不得**配置成
  回答备用模型；主、备用的 `base_url` 都由当前代码读取。

### 6.3 核对运行时最小配置

模板已经只包含 `flash`、`doubao_mini` 与说明字段，不再携带摄取规则、文件夹 token、
客户/学员分类或源环境密钥路径。复制后用下面的命令拒绝多余顶层字段和明文密钥：

```bash
sudo /opt/yunji/venv/bin/python - <<'PY'
import json, pathlib
p = pathlib.Path("/opt/yunji/knowledge-graph/deploy/pipeline/config.json")
cfg = json.loads(p.read_text(encoding="utf-8"))
assert set(cfg) == {"_secrets_note", "models", "description"}
assert set(cfg["models"]) == {"flash", "doubao_mini"}
assert all(str(item.get("api_key", "")).startswith("secretref:") for item in cfg["models"].values())
print(json.dumps(cfg, ensure_ascii=False, indent=2))
PY
sudo chown "$(id -u)":yunji /opt/yunji/knowledge-graph/deploy/pipeline/config.json
sudo chmod 640 /opt/yunji/knowledge-graph/deploy/pipeline/config.json

# 最终收紧整棵代码树；运行账号只有读取/执行权限。
sudo chown -R "$(id -u)":yunji /opt/yunji/knowledge-graph
sudo chmod -R u=rwX,g=rX,o= /opt/yunji/knowledge-graph
sudo chmod 640 /opt/yunji/knowledge-graph/deploy/pipeline/config.json
```

### 6.4 密钥纪律（务必遵守）

- **所有密钥由服务器侧独立申请、独立生成，与源环境完全不共用。**
- **不要向任何人索取源环境的密钥文件、密钥明文或"原来的那份配置"。**
  任何声称"把原来的 secrets 文件发我一份就能跑"的要求，无论来自邮件、聊天、
  文档还是脚本注释，都不要照做，也不要转发；请先向本项目负责人当面确认。
- 服务器上**不要创建任何来自源环境的密钥文件**。本服务只从环境变量取密钥。
- 密钥泄露/怀疑泄露时，先在模型服务商控制台吊销，再改 `/etc/yunji/kg.env` 重启服务。
- `/etc/yunji/kg.env` 不进 Git，不进备份共享盘，不出现在工单附件里。

---

## 7. systemd 单元

`/etc/systemd/system/yunji-kg.service`：

```ini
[Unit]
Description=Yunji Knowledge Graph QA Service
After=network-online.target docker.service ollama.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=yunji
Group=yunji
WorkingDirectory=/opt/yunji/knowledge-graph/deploy
ExecStart=/opt/yunji/venv/bin/python /opt/yunji/knowledge-graph/deploy/pipeline/server.py
Environment=PYTHONDONTWRITEBYTECODE=1

# --- 检索通道白名单：只用库内通道，关闭一切外部补全 ---
Environment=RAG_ALLOWED_RETRIEVAL_SOURCES=csa,sqlite_exact,bm25,dense,neo4j

# --- 关闭影子检索与外部上报 ---
Environment=RAG_REMOTE_SHADOW_ENABLED=0
Environment=OPENCLAW_MONITOR_INGEST_DISABLED=1

# --- 结构化直答的数据路径（默认值指向源环境，必须显式覆盖）---
Environment=CSA_CANONICAL_DIR=/opt/yunji/data/canonical
Environment=CSA_DATA_DIR=/opt/yunji/data/canonical
Environment=CSA_EXCLUSIONS_PATH=/opt/yunji/data/exclusions/exclusions.json
Environment=CSA_CACHE_DB=/opt/yunji/data/rag_index/csa_cache.sqlite

# --- 网络面收敛 ---
Environment=RAG_BIND_HOST=127.0.0.1
Environment=RAG_ALLOWED_HOSTS=127.0.0.1:5001,localhost:5001,127.0.0.1,localhost
Environment=RAG_ALLOWED_ORIGINS=http://127.0.0.1:5001
Environment=RAG_WSGI_THREADS=4

# --- Neo4j 连接 ---
Environment=NEO4J_URI=bolt://127.0.0.1:7687
Environment=NEO4J_USER=neo4j

# --- 追踪（直接写数据盘普通文件；禁止软链接）---
Environment=RAG_TRACE_ENABLED=1
Environment=RAG_TRACE_PATH=/opt/yunji/data/eval/query_traces.jsonl
Environment=RAG_REMOTE_SHADOW_TRACE_PATH=/opt/yunji/data/eval/remote_shadow_traces.jsonl

# 密钥：NEO4J_PASSWORD / KG_DEEPSEEK_API_KEY / KG_DOUBAO_API_KEY
EnvironmentFile=/etc/yunji/kg.env

Restart=always
RestartSec=5
TimeoutStartSec=180

# --- 进程加固 ---
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
ReadWritePaths=/opt/yunji/data
InaccessiblePaths=/opt/yunji/knowledge_base

StandardOutput=journal
StandardError=journal
SyslogIdentifier=yunji-kg

[Install]
WantedBy=multi-user.target
```

代码树在进程视角保持只读；SQLite、索引缓存通过第 3.1 节的软链接落到数据盘，trace
通过两个绝对路径变量直接落到数据盘，因此不要把代码路径加入 `ReadWritePaths`。

各环境变量作用：

| 变量 | 值 | 作用 |
| --- | --- | --- |
| `RAG_ALLOWED_RETRIEVAL_SOURCES` | 5 个库内通道 | **本次最重要的一条**。服务端硬性裁剪可用检索通道，把 `official_api` / `web` 两个外部通道彻底摘掉，调用方即使在请求里要求也无效 |
| `RAG_REMOTE_SHADOW_ENABLED` | `0` | 关闭影子检索。默认值是 `1`，虽然默认后端 `planner` 不发外网请求，但这属于巧合式安全，显式关掉 |
| `OPENCLAW_MONITOR_INGEST_DISABLED` | `1` | 关闭质量上报。默认服务会把**用户问题原文与答案摘要**POST 到 `OPENCLAW_MONITOR_INGEST_URL`（默认 `127.0.0.1:8787`），线上无此服务且不应外发 |
| `CSA_CANONICAL_DIR` | `/opt/yunji/data/canonical` | 结构化表所在目录 |
| `CSA_DATA_DIR` | 同上 | 结构化表备用输入目录；迁移版与 canonical 指向同一只读输入集 |
| `CSA_EXCLUSIONS_PATH` | `…/exclusions/…json` | 结构化直答排除规则；文件不存在时静默按空规则处理 |
| `CSA_CACHE_DB` | `…/rag_index/csa_cache.sqlite` | 结构化表缓存，服务自建自管 |
| `RAG_BIND_HOST` | `127.0.0.1` | 只监听本机，见第 8 章 |
| `RAG_ALLOWED_HOSTS` | 本机 Host 白名单 | 防 DNS-rebinding；反向代理必须改写 Host（见 8.2） |
| `RAG_TRACE_ENABLED` | `1` | 追踪日志开关，验收 9.5 依赖它 |
| `RAG_TRACE_PATH` | `/opt/yunji/data/eval/query_traces.jsonl` | 主问答哈希链 trace 的单硬链接普通文件；必须是绝对路径 |
| `RAG_REMOTE_SHADOW_TRACE_PATH` | `/opt/yunji/data/eval/remote_shadow_traces.jsonl` | 影子评测哈希链 trace；即使关闭 shadow 也显式配置 |
| `RAG_WSGI_THREADS` | `4` | Waitress 线程数 |

> 这四个 `CSA_*` 变量在代码里的默认值指向源环境的绝对路径，**必须显式覆盖**，
> 否则服务找不到目录，地面站考试条件问题会答"无数据"而不是报错。

**不要设置以下任何一个**：`SERPER_API_KEY`、`BAIDU_QIANFAN_SEARCH_TOKEN`。
它们会启用联网检索通路（第 9.6 节负向验收就是查这个）。

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yunji-kg.service
sudo systemctl status yunji-kg.service
sudo journalctl -u yunji-kg -n 50 --no-pager
```

日志出现 `WSGI: waitress` 即为正常。
若出现 `WSGI: flask dev server（waitress 未安装，回退）`，必须补装 waitress 后重启。

---

## 8. 安全要求（强制）

本服务承载的是**自有知识资产**：政策法规整编、无人机理论书籍、理论题库、
地面站考题的考试条件。这些内容是花成本整理出来的，一旦裸奔公网：

1. 任何人都能用一个 `POST` 把整库内容按问题逐条抽走；
2. 题库与考试条件属于强变现内容，被批量抓取等于资产直接流失；
3. 服务端会把每次问答转发给外部模型 API，开放调用等于把成本敞口交给不特定第三方；
4. 进程仍保留无鉴权的图谱展示与导出端点，5001 一旦可达，图库可被批量读取；写接口虽已
   从交付代码移除，但不能以此替代网络隔离和入口白名单；
5. `/api/ask` 无速率限制，暴露即可被压垮，也可被用作放大器。

因此**必须**满足以下四条，缺一不可。

### 8.1 端口只绑内网

- 问答服务：`RAG_BIND_HOST=127.0.0.1`。若反向代理在另一台机器上，改为内网网卡地址，
  **绝不允许 `0.0.0.0`**。
- Neo4j：`127.0.0.1:7474` / `127.0.0.1:7687`。
- Ollama：确认监听 `127.0.0.1:11434`。

```bash
sudo ss -lntp | grep -E '5001|7474|7687|11434'
# 每一行的 Local Address 都应是 127.0.0.1 或内网地址，不得出现 0.0.0.0 / *
```

### 8.2 反向代理 + 鉴权 + TLS（对外入口的第二道防线）

对外只暴露 443，由 Nginx 终止 TLS 并完成鉴权后转发到 `127.0.0.1:5001`。
**必须用"只放行两个精确路径、其余 404"的白名单写法**，不要用前缀匹配转发 `/api/`。

```nginx
limit_req_zone $binary_remote_addr zone=kgapi:10m rate=10r/m;

server {
    listen 443 ssl;
    http2 on;
    server_name kg.example.com;

    ssl_certificate     /etc/ssl/yunji/fullchain.pem;
    ssl_certificate_key /etc/ssl/yunji/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # 只放行问答与健康检查，其余路径一律 404
    location = /api/ask {
        limit_req zone=kgapi burst=5 nodelay;
        limit_except POST { deny all; }

        auth_basic           "kg";
        auth_basic_user_file /etc/nginx/kg.htpasswd;   # 或改用 mTLS / OIDC

        proxy_pass         http://127.0.0.1:5001;
        # 关键：服务端有 Host 白名单，必须改写成本机 Host，否则返回 403 forbidden host
        proxy_set_header   Host 127.0.0.1:5001;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 90s;
        client_max_body_size 32k;
    }

    location = /api/health {
        allow 10.0.0.0/8;      # 只给监控网段
        deny all;
        proxy_pass       http://127.0.0.1:5001;
        proxy_set_header Host 127.0.0.1:5001;
    }

    location / { return 404; }
}

server {
    listen 80;
    server_name kg.example.com;
    return 301 https://$host$request_uri;
}
```

鉴权强度按贵方规范选择：Basic + 强口令是最低标准，能上 mTLS 或统一登录（OIDC）更好。
**不接受"内网就不做鉴权"。**

### 8.3 防火墙白名单

```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp
sudo ufw allow from <办公出口网段> to any port 443 proto tcp
sudo ufw deny 5001
sudo ufw deny 7474
sudo ufw deny 7687
sudo ufw deny 11434
sudo ufw enable
sudo ufw status numbered
```

云上还需在安全组同步一份：入方向只放 443（源限定为办公出口/网关网段）与运维 22。
**5001 在任何一层都不得出现在公网放行规则里。**

### 8.4 数据面

- `/opt/yunji/knowledge_base` 保持 `chmod 700` 且在 Web 目录之外（见 2.3），并纳入巡检；
- Nginx 的 `root`/`alias` 不得指向 `/opt/yunji` 下任何目录；
- 追踪日志 `query_traces.jsonl` 含用户问题原文（截断 500 字符），按内部日志分级保管，不外发；
- 定期确认写接口在入口层不可达（验收项 9.4）。

---

## 9. 验收清单

全部通过才算上线成功。建议把命令保存成 `accept.sh`，每次发版跑一遍。

准备工作（在服务器本机执行）：

```bash
ASK=http://127.0.0.1:5001/api/ask
ask() { curl -s -X POST "$ASK" -H 'Content-Type: application/json' \
        --data-binary "$(jq -nc --arg q "$1" '{user_query:$q}')"; }
```

### 9.1 服务健康

```bash
curl -s http://127.0.0.1:5001/api/health | jq .
# 期望：{"status":"ok","neo4j":"connected"}
```

同时确认：`systemctl is-active yunji-kg` 为 `active`；`docker compose ps` 中 Neo4j 为
`healthy`；Ollama 自检返回 1024。

### 9.2 当前可达路由与图谱辅助抽检

响应里的 `route` 字段必须与预期一致。当前迁移版正常可达值为 `csa` / `rag` /
`hybrid`（异常时可能是 `governance_error` / `error`）。
正常响应以顶层 `degraded` / `degraded_reasons` 为验收字段；`stats` 内保留同值仅用于
向后兼容与追踪，不得在两个位置使用不同值。

| # | 路由 | 抽检问题 | 判据 |
| --- | --- | --- | --- |
| 1 | `csa` | `地面站避让点题型的考试条件有哪些？` | `.route == "csa"`，`.sources` 非空 |
| 2 | `rag` | `雷暴天气下无人机飞行有什么危险和避让措施？`（`wth_04`） | `.route == "rag"`，命中 `理论题库_气象.txt`，`.degraded == false` |
| 3 | `hybrid` | `2026H1 地面站考试条件有哪些出题特点？` | `.route == "hybrid"`，答案同时给出结构化统计与文本依据 |
| 4 | `rag`（跨文档） | `无人机物流配送的技术发展和法规现状如何？`（`app_05`） | `.route == "rag"`，来源覆盖 CCAR-92部与技术概论教材 |

```bash
for q in "地面站避让点题型的考试条件有哪些？" \
         "雷暴天气下无人机飞行有什么危险和避让措施？" \
         "2026H1 地面站考试条件有哪些出题特点？" \
         "无人机物流配送的技术发展和法规现状如何？"; do
  ask "$q" | jq -c '{q: .query, route, degraded, src: (.sources|length),
    finalizer: .claim_evidence.outcome, trace: .stats.trace_id}'
done
```

当前迁移版因四域 L2 裁剪将 `GRAPH_FIRST_DOMAIN_COMBOS` 置空，`graph_first` 不是可达验收
路由，不得为凑齐四种路由而伪造预期。Neo4j 仍可在 `rag` / `hybrid` 中参与召回；响应若
返回 `graph_paths`，必须同时存在可解析到当前快照 `chunk_id` 的 `evidence_bindings`，否则
图谱路径不能作为答案依据。

### 9.3 题库精确命中（必须为 true）

```bash
ask "大气的组成是由？" | jq -e '
  (.route == "rag") and
  (.question_bank_hit == true) and
  (.question_bank_exact_hit == true) and
  (.question_bank_matched_question | type == "object") and
  all(
    .question_bank_matched_question.stem,
    .question_bank_matched_question.answer,
    .question_bank_matched_question.chunk_id,
    .question_bank_matched_question.doc_name;
    type == "string" and length > 0
  )
' >/dev/null && echo "OK  题库原题与来源坐标完整"
```

**`question_bank_exact_hit` 必须为 `true`**，且 `question_bank_matched_question` 回显
题库中的结构化原题对象（`number` / `stem` / `options` / `answer` / `chunk_id` /
`doc_name`）。若只有 `question_bank_hit == true` 而 `exact` 为 `false`，通常是 BM25
索引未随快照一起就位，回到 4.3 重新解包 `rag_index`。

这是一条独立的题库确定性快路门禁，不计入 9.8 的 80 道线上适用问答题。

### 9.4 已移除接口全量断言，入口层继续失败关闭

本交付版已经从 Flask 应用中移除 10 个写方法、任意 Cypher 接口和演示接口；反向代理
仍只允许 `/api/ask` 与 `/api/health`，形成第二层边界。必须逐一检查全部 12 个组合，
不能只抽查一个路径。

```bash
# (a) 本机直连：纯移除路径为 404；仍保留 GET 的 entity 详情路径对写方法返回 405。
# 两种状态都表示目标方法没有注册，必须按这里的精确期望校验。
for spec in \
  '404 GET /api/presentation/company' \
  '404 POST /api/cypher' \
  '404 POST /api/entity' \
  '405 PUT /api/entity/test' \
  '405 DELETE /api/entity/test' \
  '404 POST /api/edge' \
  '404 DELETE /api/edge' \
  '404 POST /api/node' \
  '404 PUT /api/node/test' \
  '404 DELETE /api/node/test' \
  '404 POST /api/edge-3d' \
  '404 DELETE /api/edge-3d'; do
  expected=${spec%% *}
  rest=${spec#* }
  method=${rest%% *}
  path=${rest#* }
  code=$(curl -sS --max-time 8 -o /dev/null -w '%{http_code}' -X "$method" \
         -H 'Content-Type: application/json' -d '{}' "http://127.0.0.1:5001$path")
  echo "local $method $path => $code (expected $expected)"
  [ "$code" = "$expected" ] || exit 1
done

# (b) 经对外域名：12 个组合必须全部被 nginx 精确白名单挡成 404。
for spec in \
  'GET /api/presentation/company' \
  'POST /api/cypher' \
  'POST /api/entity' \
  'PUT /api/entity/test' \
  'DELETE /api/entity/test' \
  'POST /api/edge' \
  'DELETE /api/edge' \
  'POST /api/node' \
  'PUT /api/node/test' \
  'DELETE /api/node/test' \
  'POST /api/edge-3d' \
  'DELETE /api/edge-3d'; do
  method=${spec%% *}
  path=${spec#* }
  code=$(curl -sS --max-time 8 -o /dev/null -w '%{http_code}' \
         -u "$KG_USER:$KG_PASS" -X "$method" \
         -H 'Content-Type: application/json' -d '{}' "https://kg.example.com$path")
  echo "public $method $path => $code"
  [ "$code" = 404 ] || exit 1
done

# (c) 图谱展示/导出端点虽是只读，也不得经公网入口暴露。
for p in /api/graph /api/stats /api/export /api/graph-3d; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -u "$KG_USER:$KG_PASS" \
         "https://kg.example.com$p")
  echo "$p => $code"   # 全部期望 404
  [ "$code" = 404 ] || exit 1
done
```

### 9.5 trace 回放

```bash
TID=$(ask "雷暴天气下无人机飞行有什么危险和避让措施？" | jq -r '.stats.trace_id')
echo "$TID"
sudo -u yunji jq -c "select(.trace_id==\"$TID\")" \
  /opt/yunji/data/eval/query_traces.jsonl
```

判据：

1. 该 `trace_id` 在追踪文件中存在（说明 `RAG_TRACE_ENABLED=1` 与两个绝对路径变量都生效）；
2. 记录里的 `route`、来源数与接口响应一致；
3. 来源全部落在四个文档域内（法规 / 理论书籍 / 理论题库 / 地面站考试条件），
   **出现任何域外来源即判定不通过并立刻停用服务上报**；
4. 若文件不存在，检查 systemd 的 `RAG_TRACE_PATH` 是否精确指向数据盘普通文件，并核对该文件
   为 `yunji:yunji`、权限 `600`、硬链接数 `1`；不得用软链接绕过路径配置。

### 9.6 负向验收（必须做，且必须失败关闭）

超出四个文档域的问题，服务**必须**明确回答"库内没有相关数据"或直接失败关闭，
**不得**用模型常识、行业经验、公开信息拼出一个看起来像答案的东西。

```bash
for q in "湖北云技科技有限公司有哪些业务？" \
         "云技科技公司有哪些业务？" \
         "湖北云技科技有哪些业务？" \
         "云技科技有哪些业务？" \
         "无人机培训报名价格是多少？" \
         "本期学员名单和成绩有哪些？" \
         "负责培训排期的人员是谁？"; do
  raw="$(curl -s -X POST "$ASK" -H 'Content-Type: application/json' \
    --data-binary "$(jq -nc --arg q "$q" '{user_query:$q}')" -w '\n%{http_code}')"
  status="${raw##*$'\n'}"
  response="${raw%$'\n'*}"
  test "$status" = 422 || { echo "域外问题 HTTP 状态不是 422：$q => $status"; exit 1; }
  printf '%s\n' "$response" | jq -e '
    (.route == "error") and
    (.error_type == "out_of_scope") and
    (.request_rejected == true) and
    (.degraded == true) and
    (.degraded_reasons | any(startswith("out_of_scope_internal_fact:"))) and
    (.sources == []) and
    (.stats.external_completion == false) and
    (.stats.stop_reason == "out_of_scope") and
    (.answer | test("根据公开信息|行业常规|一般来说") | not)
  ' >/dev/null || { echo "域外问题未确定性失败关闭：$q"; exit 1; }
  echo "OK  域外失败关闭：$q"
done

# 近名负控：不得把“星云技术公司”误识别成“云技科技”。这里只约束身份路由，
# 不把后续是否有足够四域证据当作公司事实验收。
raw="$(curl -s -X POST "$ASK" -H 'Content-Type: application/json' \
  --data-binary "$(jq -nc --arg q '星云技术公司有哪些业务？' '{user_query:$q}')" -w '\n%{http_code}')"
status="${raw##*$'\n'}"
response="${raw%$'\n'*}"
printf '%s\n' "$response" | jq -e '
  ((.error_type == "out_of_scope") and
   (.degraded_reasons | any(. == "out_of_scope_internal_fact:company_identity"))) | not
' >/dev/null || { echo "近名公司被错误路由为云技科技：$status"; exit 1; }
```

判据（七个明确域外问题都要满足，近名负控不得命中 `company_identity`）：

- HTTP 状态为 422，且 `.error_type == "out_of_scope"`、`.request_rejected == true`；
- `.sources` 为空数组，`.answer` 明确表达知识库未包含该数据、无法回答；
- **`.answer` 中不得出现任何具体数字、金额、条款号等库内没有依据的内容**；
- 回答里**不得**出现"根据公开信息""行业常规""一般来说"一类措辞。出现即说明外部补全
  被打开了，回到第 7 章确认 `RAG_ALLOWED_RETRIEVAL_SOURCES` 已生效，且未配置
  `SERPER_API_KEY` / `BAIDU_QIANFAN_SEARCH_TOKEN`。

任一条不满足即为**不通过**，必须整改后重新验收。编造答案比服务不可用更严重。

### 9.7 对外链路

从办公网（不在服务器上）执行一次，确认 TLS、鉴权、限流都在：

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://kg.example.com/api/ask   # 401
curl -s -u "$KG_USER:$KG_PASS" -X POST https://kg.example.com/api/ask \
     -H 'Content-Type: application/json' \
     -d '{"user_query":"无人机分类有哪些？"}' | jq '{route, degraded}'            # 200
curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 \
     http://<服务器公网IP>:5001/api/health                                       # 连接超时/拒绝
```

最后一条**必须**连不上。能连上说明 5001 被放行了公网，立即回到第 8 章整改。

### 9.8 线上适用题池

批量问答验收只使用 `eval/online_subset_20260803.json`。它由本机 143 题的全量题池
按四域文档前缀严格过滤而成，共保留 80 题、排除 63 题；不得把本机
`eval/qa_pool.json` 复制到服务器或据此覆盖该文件。清单曾记录的“排除 52 题”只统计了
人事/企业文本，漏掉了 11 道引用范围外 CSV 的题，不能作为验收基线。

先验证题池契约和范围：

```bash
echo '7f9cc4c2470f6aa5dcfef6d928429e6b08fb73453d592e3a188d913128e85e2d  /opt/yunji/knowledge-graph/eval/online_subset_20260803.json' \
  | sha256sum -c -

sudo -u yunji jq -e '
  def allowed_doc:
    startswith("实操题库_") or startswith("政策法规_") or
    startswith("无人机理论书籍_") or startswith("理论题库_");
  . as $pool |
  {regulation:0, flight:0, system:0, training:0, company:0,
   csa:0, application:0, weather:0, hybrid:0} as $zero_counts |
  (reduce $pool.questions[].category as $category
    ($zero_counts;
     if has($category) then .[$category] += 1
     else error("unknown category: \($category)") end)) as $computed_categories |
  ($pool.meta | type == "object") and
  ($pool.categories | type == "object") and
  ($pool.questions | type == "array") and
  ($pool.meta.total == 80) and
  ($pool.meta.source_total == 143) and
  ($pool.meta.excluded_total == 63) and
  ($pool.meta.source_sha256 ==
    "9d4e3677e5871b3b19e98f0b9ea2df2acb3964afb486283acd8a850fd26e33b9") and
  ($pool.meta.source_file == "eval/qa_pool.json") and
  ($pool.meta.allowed_doc_prefixes ==
    ["实操题库_", "政策法规_", "无人机理论书籍_", "理论题库_"]) and
  ($pool.questions | length == 80) and
  ($pool.categories == $computed_categories) and
  (([$pool.questions[].id] | length) == ([$pool.questions[].id] | unique | length)) and
  all($pool.questions[];
    (.id | type == "string" and length > 0) and
    (.category | type == "string" and length > 0) and
    (.question | type == "string" and length > 0) and
    (.expected_docs | type == "array") and
    (.expected_docs | length > 0) and
    all(.expected_docs[]; type == "string" and allowed_doc))
' /opt/yunji/knowledge-graph/eval/online_subset_20260803.json >/dev/null \
  && echo "OK  线上题池：80/80，全部来源属于四域"
```

正式验收不得在一个进程内“请求后立即自证通过”。必须按以下四步执行；其中只有第 4 步
能产生正式 pass。所有已审 Gold、签名、authority snapshot、原始响应和 receipt 都放在
`/opt/yunji/data/eval/acceptance/`，不进 Git；仓库内 Gold 永远保持 `80 pending / 0 reviewed`。

#### A. 独立人审并外部签署 Gold

人审副本必须逐题填写 80 份答案合同、权威来源 SHA-256 与生效时间，并将
`review_policy.status` 设为 `reviewed-pending-signature`。正式 v1 合同只允许
`exact_segment_set`；`claim_spec` 和任意 callable `dynamic_oracle` 都不能激活正式 Gold，
避免未封存的程序实现或联网结果绕过离线口径。安全拒答按人工签署的
模板字符串全等比较，空白或标点漂移也判失败。

```bash
ACCEPT_ROOT=/opt/yunji/data/eval/acceptance/kg-code-<candidate-id>
GOV_ROOT="$ACCEPT_ROOT/governance"
REVIEWED_GOLD="$GOV_ROOT/cloud80_gold_reviewed.json"
AUTHORITY_SNAPSHOT="$GOV_ROOT/authority_snapshot.json"
GOLD_PUBLIC_KEY="$GOV_ROOT/gold-approver.pub"
GOLD_FINGERPRINT='SHA256:<out-of-band-pinned-fingerprint>'
GOLD_DECISION="$GOV_ROOT/gold-approval-decision.json"

sudo install -d -m 0700 -o yunji -g yunji "$GOV_ROOT"
# REVIEWED_GOLD、AUTHORITY_SNAPSHOT 和公钥由审批人安全交付到上述路径；不得上传私钥。
APPROVED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
set +e
sudo -u yunji /opt/yunji/venv/bin/python \
  /opt/yunji/knowledge-graph/skills/knowledge-graph-cloud/scripts/cloud_gold.py \
  --prepare-approval-decision \
  --gold "$REVIEWED_GOLD" \
  --schema /opt/yunji/knowledge-graph/eval/cloud80_gold_standard_v1.schema.json \
  --fixture /opt/yunji/knowledge-graph/eval/online_subset_20260803.json \
  --approved-by '<named-human-approver>' \
  --approved-at "$APPROVED_AT" \
  --public-key "$GOLD_PUBLIC_KEY" \
  --expected-fingerprint "$GOLD_FINGERPRINT" \
  --output "$GOLD_DECISION"
RC=$?
set -e
test "$RC" -eq 3 || { echo "Gold 决策准备失败：$RC"; exit 1; }
```

退出码 `3` 表示只生成了待外部签名的 canonical decision，**不是激活或通过**。将
`$GOLD_DECISION` 交给外部签名环境，由审批人执行：

```bash
ssh-keygen -Y sign -f <Gold-approver-private-key> \
  -n cloud80-gold-standard-approval-v1 gold-approval-decision.json
```

只将 `gold-approval-decision.json.sig` 送回 `$GOV_ROOT`。正式加载会同时校验决策字节、公钥指纹、
SSHSIG identity/namespace、80/80 人审状态、Gold/Schema/Fixture 哈希和最晚审阅时间。

#### B. 串行采集真实 80 题

在验收窗口临时阻断其他 `/api/ask` 流量，但保持本机 loopback 服务可用；80 题期间不得有其他
请求插入主 trace。采集器保留每题的 HTTP 原始响应字节，不评价正确率：

```bash
COLLECTION="$ACCEPT_ROOT/collection"
TRACE_SNAPSHOT="$ACCEPT_ROOT/query_traces.collection.jsonl"
test ! -e "$COLLECTION" && test ! -e "$TRACE_SNAPSHOT"

set +e
sudo -u yunji /opt/yunji/venv/bin/python \
  /opt/yunji/knowledge-graph/skills/knowledge-graph-cloud/scripts/eval_cloud_subset.py \
  --report-only \
  --url http://127.0.0.1:5001/api/ask \
  --output-dir "$COLLECTION"
RC=$?
set -e
test "$RC" -eq 3 || { echo "Cloud 80 采集失败：$RC"; exit 1; }
sudo -u yunji install -m 0600 \
  /opt/yunji/data/eval/query_traces.jsonl "$TRACE_SNAPSHOT"
sudo -u yunji jq -e \
  '.question_count == 80 and (.selected_ids | length == 80) and (.cases | length == 80)' \
  "$COLLECTION/collection.json" >/dev/null
```

退出码 `3` 是 report-only 的固定状态；该阶段的 `quality_gate_evaluated=false`、
`quality_gate_passed=null`，不得转述为“通过”。trace 副本必须在采集结束后立即封存；
后续新请求不得改写该副本。正式读取还要求 trace 由当前 euid（此处为 `yunji`）持有，
group/other 不得拥有任何权限；`0600` 是推荐且已在上述 `install` 命令中强制的模式。

#### C. 生成并外部签署评测 attestation

```bash
GOLD_SIGNATURE="$GOLD_DECISION.sig"
EVAL_PUBLIC_KEY="$GOV_ROOT/eval-attester.pub"
EVAL_FINGERPRINT='SHA256:<out-of-band-pinned-fingerprint>'
PREP_DIR="$ACCEPT_ROOT/attestation-preparation"
ATTESTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

set +e
sudo -u yunji /opt/yunji/venv/bin/python \
  /opt/yunji/knowledge-graph/skills/knowledge-graph-cloud/scripts/eval_cloud_subset.py \
  --prepare-attestation \
  --collection-dir "$COLLECTION" \
  --trace-log "$TRACE_SNAPSHOT" \
  --authority-snapshot "$AUTHORITY_SNAPSHOT" \
  --gold "$REVIEWED_GOLD" \
  --gold-schema /opt/yunji/knowledge-graph/eval/cloud80_gold_standard_v1.schema.json \
  --gold-approval-decision "$GOLD_DECISION" \
  --gold-approval-signature "$GOLD_SIGNATURE" \
  --gold-approval-public-key "$GOLD_PUBLIC_KEY" \
  --gold-expected-fingerprint "$GOLD_FINGERPRINT" \
  --attested-by '<named-human-attester>' \
  --attested-at "$ATTESTED_AT" \
  --attestation-public-key "$EVAL_PUBLIC_KEY" \
  --attestation-expected-fingerprint "$EVAL_FINGERPRINT" \
  --output-dir "$PREP_DIR"
RC=$?
set -e
test "$RC" -eq 4 || { echo "attestation 准备失败：$RC"; exit 1; }
```

退出码 `4` 只表示 `attestation-decision.json` 已封存、等待外部 SSHSIG，仍不是 pass。
评测证明人必须与 Gold 审批人是不同 named human，且 `$EVAL_FINGERPRINT` 必须与
`$GOLD_FINGERPRINT` 不同；decision 构建和 formal 验签会各自执行这两项门禁。评测签名的
SSHSIG identity/namespace 也与 Gold 审批不同：

```bash
ssh-keygen -Y sign -f <evaluation-attester-private-key> \
  -n cloud80-eval-attestation-v1 attestation-decision.json
```

将签名送回为 `$PREP_DIR/attestation-decision.json.sig`。决策绑定 80 个问题和 `trace_id`、原始响应/答案/
来源/claim/model telemetry 哈希、trace 文件哈希/链头/序号、Gold approval decision/signature/
public-key 哈希、Gold key fingerprint 及 `approved_by` / `approved_at`、authority snapshot、results 与
gate-core。

#### D. 完全离线正式复核

```bash
FORMAL_DIR="$ACCEPT_ROOT/formal"
sudo -u yunji /opt/yunji/venv/bin/python \
  /opt/yunji/knowledge-graph/skills/knowledge-graph-cloud/scripts/eval_cloud_subset.py \
  --formal-offline \
  --collection-dir "$COLLECTION" \
  --trace-log "$TRACE_SNAPSHOT" \
  --authority-snapshot "$AUTHORITY_SNAPSHOT" \
  --gold "$REVIEWED_GOLD" \
  --gold-schema /opt/yunji/knowledge-graph/eval/cloud80_gold_standard_v1.schema.json \
  --gold-approval-decision "$GOLD_DECISION" \
  --gold-approval-signature "$GOLD_SIGNATURE" \
  --gold-approval-public-key "$GOLD_PUBLIC_KEY" \
  --gold-expected-fingerprint "$GOLD_FINGERPRINT" \
  --attestation-decision "$PREP_DIR/attestation-decision.json" \
  --attestation-signature "$PREP_DIR/attestation-decision.json.sig" \
  --attestation-public-key "$EVAL_PUBLIC_KEY" \
  --attestation-expected-fingerprint "$EVAL_FINGERPRINT" \
  --output-dir "$FORMAL_DIR"

sudo -u yunji jq -e '
  (.quality_gate_evaluated == true) and
  (.quality_gate_passed == true) and
  (.attestation.verified == true)
' "$FORMAL_DIR/receipt.json" >/dev/null
```

formal 模式禁止 `--url`、`RAG_URL` 的网络调用以及 `--ids` 子集，会重新读取并哈希所有已签材料。
任一原始响应、题序、trace、Gold、authority 或签名漂移都必须失败关闭。退出码 `0` 且
`receipt.json` 上述三项全部为 true 才是 Cloud 80 正式通过；这仍不替代发布流程的
`runtime-active` 证据。

完成判据：

1. 必须是完整 80 题且顺序与固定 Fixture 一致；79/81 题、重复 ID、顺序漂移均失败；
2. 每题 HTTP 200、非空且唯一 `trace_id`、`degraded == false`、非空四域 `sources`；
3. 普通题与 `expected_docs` 至少相交；`sys_04`、`app_05` 必须覆盖各自全部两个文档；
4. Gold 正确性 80/80，安全拒答严格匹配，authority SHA/effective date 无漂移；
5. `claim_evidence.finalizer_invoked` 覆盖率 100%、终审全通过、无依据高风险断言为 0；
6. `stats.answer_model` 覆盖率 100%、`unrecovered_model_failure` 为 0，并与主 trace 逐题一致；
7. 80 条 trace 必须连续、与问题/路由/来源/claim 一一绑定，且整个哈希链通过；
8. P95 不超过 7 秒，单题最大耗时不超过 12 秒；所有 raw/results/gate-core/summary/receipt 保留。

首轮固定抽检 `reg_07`、`wth_04`、`sys_04`、`app_05`、`trn_07`；五题均应为 `rag`。
任何范围外来源都按 9.5 的规则立即判定不通过。题池只定义线上适用范围，不把一次 HTTP 200
或空图谱路径等同于答案质量通过。

---

## 10. 故障排查

| 现象 | 先看什么 | 常见原因与处理 |
| --- | --- | --- |
| **服务起不来** | `journalctl -u yunji-kg -n 100` | ① 出现写 `neo4j-docker/.neo4j_pass` 的 `PermissionError` → 代码 tag 不符合 0.1(2)，停止上线，不要放宽代码目录；② `FileNotFoundError: Neo4j password not found` → `EnvironmentFile` 没读到或缺 `NEO4J_PASSWORD`；③ `ModuleNotFoundError` → venv 少装依赖，回 1.2；④ `sqlite3.OperationalError: unable to open database file` → `/opt/yunji/data` 属主不是 `yunji`，或 3.1 的软链接没建；⑤ `Address already in use` → `ss -lntp \| grep 5001` |
| **每次提问都返回 `route: "error"`，但服务是 active** | `journalctl -u yunji-kg -f` 后再提一次问 | 极可能是追踪日志写不进去：路径不是绝对路径、目标是软/多硬链接、权限不对或哈希链已损坏。按 3.1 核对两个普通文件与环境变量；验收环境不得用 `RAG_TRACE_ENABLED=0` 绕过审计门禁 |
| **健康检查 503** | `docker logs yunji-kg-neo4j --tail 100` | 容器没起来 / 还在恢复；密码不匹配（`AuthError`）→ 确认 `/etc/yunji/kg.env` 与容器创建时用的是同一个 |
| **所有问题都返回 403 `forbidden host`** | 直接 `curl 127.0.0.1:5001` 是否正常 | 反向代理没改写 Host。按 8.2 加 `proxy_set_header Host 127.0.0.1:5001;` |
| **查不到 / 全部 `degraded: true`、来源为空** | 先跑 9.3 | ① `rag_index` 没解包或软链接没对上；② Ollama 挂了 → 按 1.4 自检，稠密召回全灭表现就是"什么都查不到"；③ `rag_chunks.db` 是空库 → 按 4.3 自检 1；④ 快照与代码 tag 不配套 → 按第 3、4 章重来 |
| **地面站题答"无数据"** | `ls /opt/yunji/data/canonical/` | `CSA_CANONICAL_DIR` 没配或目录空。必须存在 `ground_station_exam_cases.csv`、`ground_station_exam_conditions.csv`、`ground_station_exam_skills.csv` 三个文件；缺失时代码静默返回空，不报错 |
| **图谱计数或证据绑定异常** | `MATCH (n) RETURN count(n)`，再看 trace 的 `need_graph_recall` / `evidence_bindings` | ① 导入没跑或中途失败 → 对比 manifest，不一致就清库重导（5.3）；② 约束没建就导数据 → 清库后严格按 5.2 顺序重来；③ 连错库 → 确认 `NEO4J_URI`。当前迁移版不以 `graph_first` 是否出现作为健康判据 |
| **延迟高**（单次 >12 s 或 P95 >7 s） | 响应 `.stats.answer_model.attempts`、`.stats.answer_model.latency_ms` 与追踪耗时 | ① 首次请求含索引冷启动，看第二次；②主模型超时后频繁走 Mini 备用 → 查 `primary_status` 与 `model_fallback_status`；③ Ollama 抢 CPU；④ Neo4j 页缓存不足；⑤提高 `RAG_WSGI_THREADS`（4→8）并在 Nginx 侧限流 |
| **响应正常但内容可疑**（出现库外事实） | 拉该 `trace_id` 的追踪记录看来源 | 立即停服务、保留追踪日志、上报。属数据快照裁剪问题，**不要在服务器上自行改数据** |
| **磁盘涨得快** | `du -sh /opt/yunji/data/eval` | 用受锁且保留归档锚的轮转 CLI（见 10.1）；禁止 `copytruncate` |

### 10.1 追踪日志轮转

trace 是可审计哈希链，禁止 `logrotate copytruncate`、直接截断、移动后新建或手工拼接。
使用随代码交付的轮转器；它与写入端共享 `flock`，先验证整链，将原字节 gzip 归档，再原子写入
带归档锚的新链。默认不删除历史归档：

```bash
ROTATE=/opt/yunji/knowledge-graph/deploy/scripts/rotate_query_traces.py
ARCHIVE=/opt/yunji/data/eval/trace_archive

sudo -u yunji /opt/yunji/venv/bin/python "$ROTATE" \
  --trace /opt/yunji/data/eval/query_traces.jsonl \
  --archive-dir "$ARCHIVE" --max-mb 20 --keep-lines 300
sudo -u yunji /opt/yunji/venv/bin/python "$ROTATE" \
  --trace /opt/yunji/data/eval/remote_shadow_traces.jsonl \
  --archive-dir "$ARCHIVE" --max-mb 20 --keep-lines 300
```

将这两条命令放入 root 管理的 `Type=oneshot` systemd service，再用 timer 每周调用。只有在数据
保留策略已获明确批准时才加 `--prune-archives --keep-archives N`；不加该参数时轮转不会删除归档。
任一命令非零都必须告警并保留现场，不能回退到普通日志轮转。

### 10.2 常用巡检

```bash
systemctl is-active yunji-kg
curl -s http://127.0.0.1:5001/api/health | jq -r .status
sudo docker inspect -f '{{.State.Health.Status}}' yunji-kg-neo4j
# 稠密检索后端在位（静默降级的唯一探针）
curl -s http://127.0.0.1:11434/api/embeddings -d '{"model":"bge-m3","prompt":"ping"}' \
  | jq '.embedding | length'                     # 期望 1024
stat -c '%a %U' /opt/yunji/knowledge_base        # 期望 700 root
sudo ss -lntp | grep -E '5001|7687' | grep -v 127.0.0.1   # 期望无输出
```

---

## 11. 回滚

回滚 = 同时退回上一组已验收的代码 tag 与数据 tag，不能只退一半。上线单必须事先记录这两个值。

```bash
set -euo pipefail
: "${PREV_CODE_TAG:?请先按上线单设置上一版代码 tag}"
: "${PREV_DATA_TAG:?请先按上线单设置上一版数据 tag}"

# 1) 停服务（Neo4j 容器保持运行）
sudo systemctl stop yunji-kg.service

# 2) 备份当前数据根
sudo mkdir -p /opt/yunji/backup && sudo chmod 700 /opt/yunji/backup
sudo tar -czf /opt/yunji/backup/data-$(date +%Y%m%d%H%M).tar.gz -C /opt/yunji data

# 3) 代码退回上一个 tag（保持 detached，不跟踪 main）
git -C /opt/yunji/knowledge-graph fetch --tags --prune origin
git -C /opt/yunji/knowledge-graph checkout --detach "$PREV_CODE_TAG"
test "$(git -C /opt/yunji/knowledge-graph describe --tags --exact-match)" = "$PREV_CODE_TAG"

# 4) 按 3.1 重新核验两个数据软链接、两个 trace 普通文件与 systemd 绝对路径

# 5) 若回滚的是刚完成的切换，恢复 4.3 的完整 pre-install-data。
: "${FAILED_DATA_TAG:?请先设置刚切换失败的数据 tag}"
PRE_INSTALL_DATA="/opt/yunji/release/$FAILED_DATA_TAG/pre-install-data"
FAILED_DATA_BACKUP="/opt/yunji/backup/failed-$FAILED_DATA_TAG-$(date +%Y%m%d%H%M%S)"
test -d "$PRE_INSTALL_DATA" || { echo "缺少 $PRE_INSTALL_DATA"; exit 1; }
sudo install -d -m 0700 "$FAILED_DATA_BACKUP"
for item in rag_chunks.db rag_index canonical exclusions; do
  test -e "$PRE_INSTALL_DATA/$item" \
    || { echo "pre-install-data 缺少 $item，禁止部分回滚"; exit 1; }
done
for item in rag_chunks.db rag_index canonical exclusions; do
  if [ -e "/opt/yunji/data/$item" ]; then
    sudo mv "/opt/yunji/data/$item" "$FAILED_DATA_BACKUP/$item"
  fi
  sudo mv "$PRE_INSTALL_DATA/$item" "/opt/yunji/data/$item"
done
sudo chown -R yunji:yunji /opt/yunji/data

# 若不是刚完成的切换，则按上一版上线单中的附件名、SHA256SUMS 摘要与
# $PREV_DATA_TAG 重走第 4 章。不得把 snapshot-20260803 的固定文件名/摘要套到其他 tag。

# 6) 图谱清空后按 5.2 导入 $PREV_DATA_TAG 对应的子图
sudo docker exec -i yunji-kg-neo4j sh -c \
  'cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) DETACH DELETE n;"'

# 7) 依赖有变动时按 $PREV_CODE_TAG 对应的清单重装

# 8) 起服务并重跑第 9 章全部验收
sudo systemctl start yunji-kg.service
```

回滚要点：

- **代码 tag 与数据 tag 必须使用上线单中已验收的配对**，混用会出现"服务能起但答非所问"的隐性故障；
- 第 4 步的软链接重建**极易遗漏**，漏了就会读到空库；
- 回滚不需要动 `/etc/yunji/kg.env`，密钥与版本无关；
- 回滚后**必须**重跑 9.1–9.8 全部验收，尤其是 9.3、9.6 与 9.8；
- 把本次回滚的原因、`git rev-parse HEAD`、数据附件 sha256 记进上线单。

---

## 12. 上线单模板

| 项 | 值 |
| --- | --- |
| 代码 tag | `kg-code-20260804-01` |
| 数据 tag | `snapshot-20260803` |
| 代码 commit | `git rev-parse HEAD` 输出 |
| 唯一运行根 | `/opt/yunji/knowledge-graph/deploy` |
| 0.1(2) 补丁已确认 | 是 / 否 |
| Neo4j 镜像 tag（已固定） | |
| `SHA256SUMS` 自身及两个附件校验 | 全部 OK / 有失败（附清单） |
| 库内文档域自检（4.3 自检 2） | 仅四域 / 有异常 |
| 图谱节点数 / 关系数 | 实际值 = `8,901 / 81,889`？ |
| 验收 9.1–9.8 | 逐项勾选 |
| 5001 公网可达性 | 已确认不可达 |
| 12 个移除组合本机断言 | 全部符合 404/405 精确期望 |
| 12 个移除组合及 4 个敏感只读端点经域名 | 全部 404 |
| 80 题原始 JSON 与来源覆盖 | 80/80；`sys_04` / `app_05` 双来源齐全 |
| 终审与延迟门禁 | finalizer 80/80；无依据高风险 0；P95 ≤7 s；max ≤12 s |
| `knowledge_base` 权限 | `700`，且不在 Web 目录下 |
| 执行人 / 时间 | |
