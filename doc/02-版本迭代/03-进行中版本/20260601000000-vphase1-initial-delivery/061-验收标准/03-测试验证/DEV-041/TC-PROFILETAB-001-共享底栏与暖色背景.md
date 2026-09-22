# TC-PROFILETAB-001 共享底栏与暖色背景

- 对应验收项：`AC-PROFILETAB-001/002/003/101/102`、`AC-PROFILEBG-001`
- 前置条件：保留 DEV-040 当前未提交改动；未修改禁改文件。
- 源码层：运行 `python verify_profile_tab_contract.py`，检查共享 DOM 单一实现、两页引用、路由/active、精确颜色映射、渐变结构、业务全文件冻结和应用白名单。
- 代码质量：运行 `pnpm type-check`、`git diff --check`、冲突标记、白名单与 `uni_modules` 审计。
- 交互层：由独立验收代理使用 Chrome DevTools 移动端运行验收；本实施子代理不自验收。
- 证据入口：`red-test-result.json`、`green-test-result.json`、`command-results.json`。
- 当前状态：源码契约与代码质量实施自检已通过；Chrome DevTools 交互层待独立验收代理执行。
