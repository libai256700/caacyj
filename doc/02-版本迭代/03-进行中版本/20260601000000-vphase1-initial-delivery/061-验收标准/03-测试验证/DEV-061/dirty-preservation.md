# DEV-061 并行改动保护

- DEV-061 应用源码差异仅为 `code/develop/yunjikeji/src/pages/jobs.vue`。
- `OrganizationBindingRequiredDialog.vue`、`home.vue`、`practice/exam-modes.vue`、`practice/exam-topics.vue` 在 DEV-061 前已存在并行改动，本任务未修改、格式化、回退或归因。
- 岗位页同时监听组件旧 `cancel` 与当前 `close/service/bind` 事件，因此远端旧组件和当前并行组件契约均可承接。
- services、store、backend、锁文件及 `uni_modules/**` 未纳入 DEV-061。
