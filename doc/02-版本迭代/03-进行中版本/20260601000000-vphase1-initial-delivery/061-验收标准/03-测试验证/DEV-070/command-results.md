# DEV-070 命令执行回执

执行时间：`2026-08-29 11:00:10 +08:00`

## 1. 版本测试资产初始化

```powershell
python "C:\Users\renquan\.codex\skills\40-0100-project-testing\scripts\init_project_testing_assets.py" version "E:\huiyitechworkspace\feixingxueyuan\doc\02-版本迭代\03-进行中版本\20260601000000-vphase1-initial-delivery"
```

- 退出码：`0`。
- 关键输出：版本级接口、数据、交互索引、测试数据模板和测试结论均为 `skipped`，未覆盖既有资产。

## 2. 分类13保护基线

```powershell
node .\dev070-contract.mjs --suite=protection
```

- 工作目录：当前 `DEV-070/`。
- 退出码：`0`。
- 关键输出：

```text
PASS home classification-13 semantic AST
PASS answer/service classification-13 control and API semantics
PASS Java structural AST classification-13 API and Agent2/V3 call chain
PASS Python AST mutation proof rejected 22 targeted false-green variants
PASS built-in dialog/HTTP/Python mutation proofs
PASS Java classification-13/API exact HTTP and mutation contracts
SUMMARY suite=protection passed=3 failed=0
```

- 保护依据为TypeScript AST控制流、Java词法/括号/方法/调用结构树和Python AST数据流，不使用源码SHA，不依赖本机JDK编译器模块。
- Java逐项锁定旧接口的 `GetMapping/PostMapping`、唯一path、参数声明、响应类型、Service调用及参数。
- Python mutation独立入口：`python .\dev070_tool_contract.py --suite mutation --repo-root <仓库根目录>`，退出码 `0`，拒绝22个针对性误绿变体。

## 3. 聚合红灯

```powershell
node .\dev070-contract.mjs --suite=all
```

- 工作目录：当前 `DEV-070/`。
- 退出码：`1`（预期红灯）。
- 关键输出：

```text
PASS home classification-13 semantic AST
PASS answer/service classification-13 control and API semantics
PASS Java structural AST classification-13 API and Agent2/V3 call chain
PASS Python AST mutation proof rejected 22 targeted false-green variants
PASS built-in dialog/HTTP/Python mutation proofs
PASS Java classification-13/API exact HTTP and mutation contracts
FAIL home start dialog ownership and handlers: entry handler state must structurally own one dialog containing 自我评测 / 职业规划评测
FAIL home report dialog ownership and handlers: entry handler state must structurally own one dialog containing 自我评测报告 / 职业规划评测报告
FAIL classification-14 frontend flow: answer page must retain explicit categoryId context
FAIL classification-14 backend structural AST routing: classification 14 constant missing
FAIL manual career question tool AST contract: exactly one independent career question import Python entry is required; actual=0
FAIL manual career Agent tool AST contract: exactly one independent career Agent initialization Python entry is required; actual=0
FAIL manual tool whole-repository isolation: career question tool prerequisite missing; actual=0
SUMMARY suite=all passed=3 failed=7
```

## 4. 证据边界

- 红灯来自真实源码结构化解析和控制流/接口/隔离契约，不是无法执行、语法错误或数据库不可用。
- 同库契约只读取当前应用 `application-local.yaml` 的非敏感 `host/port/database`，要求手工工具分别解析传入配置与仓库固定配置并比较一致，再使用已比较目标连接；拒绝任意host/port/database CLI覆盖或异库JDBC字面量。
- apply契约按AST证明：同库比较后连接 -> 前置校验（Agent含id=3存在即抛错）-> 备份 -> begin/关闭autocommit -> 写入 -> 事务内回读 -> commit；每个异常分支rollback并重新抛出，dry-run路径零连接、零事务、零DML。
- 本任务未连接数据库，未运行浏览器集成测试；实现后的真实交互必须继续使用测试环境 Playwright 验收。

## 5. 最终质量检查

| 命令 | 退出码 | 结论 |
| --- | --- | --- |
| `node --check .\dev070-contract.mjs` | `0` | 脚本语法通过 |
| `python -m py_compile .\dev070_tool_contract.py` | `0` | Python AST契约脚本语法通过 |
| `python .\dev070_tool_contract.py --suite mutation --repo-root <仓库根目录>` | `0` | 22个针对性误绿变体全部被拒绝 |
| `node .\dev070-contract.mjs --suite=protection` | `0` | 分类13保护稳定复现 |
| `node .\dev070-contract.mjs --suite=all` | `1` | 预期功能红灯稳定复现 |
| `git diff --check` | `0` | 差异质量检查通过；仅有其他并行文件的行尾提示 |
| `git diff --cached --check` | `0` | 暂存差异质量检查通过 |
| `git status --short -- ':(glob)**/uni_modules/**'` | `0`且无输出 | 禁区无改动 |
| `rg -n "[ \\t]+$" .`（DEV-070目录） | `1`且无输出 | 专属资产无行尾空白 |

- `AC-CAREER-ASSESS-001/002/101/201/202/301` 六个正式相对入口均已执行 `Test-Path` 并返回 `True`。
