# DEV-011 命令结果

| 命令 | 结果 |
| --- | --- |
| `python verify_wrong_question_default_filter.py` | `0` |
| `mvn '-Dtest=UserPracticeExercisesRecordSqlContractTest' test` | `0`；`Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`；`BUILD SUCCESS` |
| `pnpm exec eslint src/views/yj/resource/config.ts src/views/yj/resource/index.vue` | `0` |
| `pnpm build:testhost` | `0`；输出 `Build successful. Please see dist-testhost directory` |
| `git diff --check` | `0`；仅出现既有文件 `LF will be replaced by CRLF` 警告，未报格式错误 |
| `git diff --name-only -- ':(glob)uni_modules/**'` | `0`；无输出 |
| `Invoke-WebRequest http://localhost:3000/yj/practice/wrong-question` | `0`；HTTP `200`，返回 Vite 页面骨架；未证明无登录即可进入正式错题页 |
| `rg -n "@playwright/test|playwright" code/develop/yunjikeji-admin-ui/package.json code/develop/yunjikeji-admin-ui/pnpm-lock.yaml` | `1`；无匹配，当前 UI 工程未发现 Playwright 依赖声明 |

## 补充说明

- `verify_wrong_question_default_filter.py` 首轮因资源块锚点写死到 `practice-record` 后继块而失败；修正为当前真实后继块 `post` 后已重跑转绿。
- 本轮未运行 Playwright：当前 `code/develop/yunjikeji-admin-ui/package.json` 未声明 Playwright 依赖，不满足“现有项目依赖执行”的前提。
