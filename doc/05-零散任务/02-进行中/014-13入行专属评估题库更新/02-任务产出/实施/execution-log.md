# T0014 实施执行日志

## 2026-08-18 连接前置核对与阻塞

- 当前运行程序：`YunjikejiAdminServerApplication`，默认 `local` profile。
- 实际连接：`114.111.30.111:13306/yunjikeji`，与 `application-local.yaml` 和 Local 正式连接记录一致，用途为测试库。
- 目标分类：`id=13`、`tenant_id=1` 唯一；活动基线为 21 题、101 选项、0 子答案。
- 步骤基线：`yj_practice_setp` 有 4 个活动步骤，均为 `tenant_id=1`，且仅被分类 13 的活动题引用，引用分布为 7/6/6/2。
- 目标映射：48 题、243 选项、6 步；步骤题量为 5/10/1/1/26/5。
- 生成器语法检查：通过。
- 数据库写入：0。
- 阻塞：首次运行只读 `prepare` 时，新建 PyMySQL 连接触发 Windows `WinError 10055`。本机约 4045 个 TCP 连接中，PID 35068 `CocosCreator` 占用约 3859 个；正式 Test 的 `127.0.0.1:13306` 入口也不可用，不能切换旁路。
- 处置：未关闭用户进程，未继续重试连接，等待用户释放套接字资源或授权关闭/重启 PID 35068。
- 凭据：未写入日志或任务产出。

## 恢复后续跑

在套接字资源恢复后，从工作区根目录执行：

```powershell
$taskDir = 'E:\huiyitechworkspace\feixingxueyuan\doc\05-零散任务\02-进行中\014-13入行专属评估题库更新'
$outputDir = Join-Path $taskDir '02-任务产出\实施'
$generator = Join-Path $outputDir 'generate_and_execute_t0014.py'
$config = 'E:\huiyitechworkspace\feixingxueyuan\code\develop\yunjikeji-admin-server\yunjikeji-admin-server\src\main\resources\application-local.yaml'
$source = Join-Path $taskDir '02-任务产出\信息收集\source-questions.json'
$timestamp = Get-Date -Format 'yyyyMMddHHmmss'

python $generator prepare --config $config --source $source --output $outputDir --timestamp $timestamp
```

`prepare` 成功后，先静态审查新生成的 `mapping-48.json`、`backup-before.json`、时间戳 DML、rollback SQL 和 `verify-category-13.sql`。确认精确主键、tenant/category 边界、备份、ID 无碰撞和非目标哈希均通过后，再执行：

```powershell
$dml = Get-ChildItem -LiteralPath $outputDir -Filter '*-dml-update_category_13_assessment.sql' | Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
$rollback = Get-ChildItem -LiteralPath $outputDir -Filter '*-dml-rollback_category_13_assessment.sql' | Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
$verify = Join-Path $outputDir 'verify-category-13.sql'

python $generator workflow --config $config --output $outputDir --dml $dml --rollback $rollback --verify $verify
```

`workflow` 的固定顺序为：执行前旧基线与非目标哈希断言、verify 旧状态、首次更新、verify 最终状态、回滚演练、verify 旧状态和旧哈希、再次更新、verify 最终状态、幂等重跑、最终目标与非目标哈希校验。任一断言失败会停止；若已进入最终新状态，执行器会尝试用对应 rollback SQL 恢复旧状态。
## 2026-08-18T14:00:14+08:00 资产准备

- 命令：`python generate_and_execute_t0014.py prepare --config <application-local.yaml> --source <source-questions.json> --output <实施目录> --timestamp 20260818140012`
- 连接确认：运行中程序默认 `local` profile；生效库 `yunjikeji`；正式用途为测试库。
- 旧基线：21 道活动题、101 个活动选项、0 个活动子答案、4 个仅供目标分类使用的活动步骤。
- 新映射：48 道题、243 个选项、6 个步骤；步骤题量 5/10/1/1/26/5。
- 目标基线哈希：`{"yj_practice_exercises": "543db02b26fe643feafd58914998c38444a252ad2f992375f78b0a024f45dfc5", "yj_practice_exercises_answer": "6d714d6cef098ffa7a1202c2d8be1253929ba4df469e2cffa24133018a59ef55", "yj_practice_exercises_answer_child": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "yj_practice_setp": "a45862301d4927dd83bc80f822e4f010f03b93e4ef3d2775b26a50df1227dcd8"}`
- 非目标基线：`{"yj_practice_exercises": {"rowCount": 1535, "sha256": "02fa3673246d9bf22c0616c39500cbed0439da79a863bbf9f945ff9c1c7d984b"}, "yj_practice_exercises_answer": {"rowCount": 4630, "sha256": "d1d6f71a0ea3dd8e553735facc0ffda97c62bca28644158a8f18ddeae4f190b8"}, "yj_practice_exercises_answer_child": {"rowCount": 0, "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"}, "yj_practice_setp": {"rowCount": 0, "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"}}`
- 凭据：仅由运行时读取生效配置，未写入任何产出。

## 2026-08-18T14:02:14+08:00 执行失败

- 失败：`OperationalError: (1792, 'Cannot execute statement in a READ ONLY transaction.')`
- 自动恢复：`not-needed`
- 结论：停止后续动作，未宣称验收通过。

## 2026-08-18T14:03:19+08:00 执行、回滚演练与最终恢复

- 命令：`python generate_and_execute_t0014.py workflow --config <application-local.yaml> --output <实施目录> --dml <更新SQL> --rollback <回滚SQL> --verify <校验SQL>`
- 第一次更新：成功；verify 检测状态 `final`。
- 回滚演练：成功；verify 检测状态 `old`；旧目标全字段哈希恢复。
- 第二次更新：成功；verify 检测状态 `final`；与第一次最终哈希一致。
- 幂等重跑：成功；更新 SQL 再执行无新增变化，目标最终哈希不变。
- 最终统计：48 道活动题、243 个活动选项、0 个活动子答案、6 个活动步骤。
- 标准答案：243 个活动选项 `is_correct=0`；题目 `score=0`、`question_status=1`。
- 最终目标哈希：`{"yj_practice_exercises": "f6ab711102ab9d6ec129119893112b02fef82504afa9c9806699e057a63b301d", "yj_practice_exercises_answer": "713c99b83a8d93ee8cc83b6ac1e0b19e3bd9b797ddeda3e72c9f05eb7590b14b", "yj_practice_setp": "d2434c9ba82834cd61cf63172bdeed8d65ea85712288c7b862d9a0db45692bb1"}`
- 非目标零变化：`{"yj_practice_exercises": {"rowCount": 1535, "sha256": "02fa3673246d9bf22c0616c39500cbed0439da79a863bbf9f945ff9c1c7d984b"}, "yj_practice_exercises_answer": {"rowCount": 4630, "sha256": "d1d6f71a0ea3dd8e553735facc0ffda97c62bca28644158a8f18ddeae4f190b8"}, "yj_practice_exercises_answer_child": {"rowCount": 0, "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"}, "yj_practice_setp": {"rowCount": 0, "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"}}`
- SQL 断言摘要：`[{"assertions": 11, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\verify-category-13.sql", "statementCount": 18, "verificationState": "old"}, {"assertions": 20, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\20260818140012-dml-update_category_13_assessment.sql", "statementCount": 32, "verificationState": null}, {"assertions": 11, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\verify-category-13.sql", "statementCount": 18, "verificationState": "final"}, {"assertions": 14, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\20260818140013-dml-rollback_category_13_assessment.sql", "statementCount": 23, "verificationState": null}, {"assertions": 11, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\verify-category-13.sql", "statementCount": 18, "verificationState": "old"}, {"assertions": 20, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\20260818140012-dml-update_category_13_assessment.sql", "statementCount": 32, "verificationState": null}, {"assertions": 11, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\verify-category-13.sql", "statementCount": 18, "verificationState": "final"}, {"assertions": 20, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\20260818140012-dml-update_category_13_assessment.sql", "statementCount": 32, "verificationState": null}, {"assertions": 11, "file": "E:\\huiyitechworkspace\\feixingxueyuan\\doc\\05-零散任务\\02-进行中\\014-13入行专属评估题库更新\\02-任务产出\\实施\\verify-category-13.sql", "statementCount": 18, "verificationState": "final"}]`
- 凭据：未写入日志或产出。
- 结论：仅为实施自检，不能替代独立验收。

## 2026-08-18T14:04:00+08:00 进程与最终只读复核

- 用户授权目标 PID `35068` 在执行关闭命令前已经不存在，因此未执行 `Stop-Process`，未停止任何其他进程，也不存在 PID 复用误杀。
- TCP 连接总量由阻塞时约 4045 降至约 352 后恢复；最终复核时约 393。
- 当前运行后端重新定位为 PID `2896` 的 `YunjikejiAdminServerApplication`，使用默认 profile，并保持到 `114.111.30.111:13306` 的数据库连接；与 `local` 生效配置和正式测试库记录一致。
- 最终 verify：状态 `final`，18 条语句、11 个断言全部通过。
- 最终数据：48 题全部启用，`sort_no=1..48` 连续且无重复，`score` 合计为 0；243 个活动选项的 `is_correct` 合计为 0；活动子答案 0，任务答案孤儿 0。
- 六步：基础画像 5、核心量表 10、主要顾虑 1、报告目标 1、补充模块 26、确认提交 5。
