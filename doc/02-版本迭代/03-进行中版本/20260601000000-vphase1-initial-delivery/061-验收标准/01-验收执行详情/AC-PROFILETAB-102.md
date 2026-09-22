# AC-PROFILETAB-102 自动检查与运行验收

- 类型：技术-代码级
- 正式入口：DEV-041 源码契约、类型检查、差异检查和 Chrome DevTools。
- 支撑结果：证明结构、交互、背景和冻结边界均成立。
- 通过条件：源码契约先红后绿；`pnpm type-check`、`git diff --check`、冲突标记、白名单和 `uni_modules` 通过；Chrome DevTools 移动端运行验收由独立验收代理执行。
- 特殊口径：H5 构建只尝试一次；若复现已知 OS esbuild 故障，记录证据并停止枚举。
- 证据承接：`061-验收标准/03-测试验证/DEV-041/`。
