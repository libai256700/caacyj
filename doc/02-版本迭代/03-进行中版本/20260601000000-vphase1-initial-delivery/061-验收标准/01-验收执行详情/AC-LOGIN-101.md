# AC-LOGIN-101 登录逻辑与代码边界不变

- 当前状态：通过（2026-07-17 独立复验：`script setup` 与 HEAD 一致，无短信逻辑，内部 password 验证与既有登录流程不变，`uni_modules/**` 无变更）。

- 类型：技术-代码级
- 关联任务：`DEV-030`
- 正式入口：`code/develop/yunjikeji/src/pages/auth/login.vue`
- 支撑的业务结果：样式改造后全部现有登录方式、角色分流、加载态和协议交互继续可用，新增 iOS 图标不改变业务流程。
- 技术边界：只调整样式及为构图服务的展示结构；可见第二字段显示“验证码 / 请输入验证码 / 获取验证码”，内部仍复用现有 `verifyCode` / password 校验和提交；`script setup` 与返工前 HEAD 完全一致；不修改登录接口契约、业务状态、数据持久化或 `uni_modules/**`。
- 通过条件：代码差异符合上述范围，现有真实机制未被假数据或静态占位替代；“获取验证码”是无 `button`、`@tap`、`@click`、handler、请求或倒计时的纯展示 `view`；iOS 图标不使用 `button` 且无交互；不存在 `requestVerifyCode`、countdown 或短信请求；`git diff --name-only -- '**/uni_modules/**'` 无本任务改动。
- 证据承接：代码差异审查与交互验证记录回写 `../03-测试验证/`。
