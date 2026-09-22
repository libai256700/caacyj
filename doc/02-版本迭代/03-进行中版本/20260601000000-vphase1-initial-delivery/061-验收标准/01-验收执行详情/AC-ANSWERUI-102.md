# AC-ANSWERUI-102 质量命令、浏览器与视觉判定

- 类型：技术-代码级
- 正式入口：APP 学员端 H5 构建入口与 `061-验收标准/03-测试验证/DEV-038/` 自动化脚本。
- 支撑的业务结果：三档常见移动视口中答题页稳定可用，核心题型和结果态无视觉或交互回归。
- 技术边界：Playwright 登录存储与接口拦截只存在于正式测试脚本，不写入应用源码或冒充真实账号联调；测试服务器保持使用现有 H5 开发入口。
- 通过条件：`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均退出码 `0`；三档 Playwright 覆盖单选、多选、末题与错误解析且无页面错误、横向溢出或交互失败；visual-verdict JSON 为 `score >= 90` 且 `verdict=pass`。
- 证据承接：`061-验收标准/03-测试验证/DEV-038/`。

- 当前状态：已通过（独立验收）。
- 独立验收结果：Playwright、`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均 exit `0`；单选与多选独立 visual-verdict 均为 `95/pass`。
