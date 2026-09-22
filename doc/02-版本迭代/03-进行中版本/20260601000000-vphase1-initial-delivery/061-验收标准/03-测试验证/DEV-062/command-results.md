# DEV-062 命令结果

| 命令 | 结果 |
| --- | --- |
| `node DEV-062/dev062-wrong-category-contract.spec.cjs`（红灯） | `1` |
| `node DEV-062/dev062-wrong-category-contract.spec.cjs`（绿色） | `0` |
| `pnpm type-check` | `0` |
| `pnpm run build:h5` | `0` |
| `git diff --check -- <任务白名单>` | `0` |
