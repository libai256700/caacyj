# TC-API-001 岗位列表接口契约

## 对应验收项

- `TA-T0022-API-001`

## 验证目标

- `AppPostPageReqVO` 同时保留 `keyword/pageNo/pageSize/status`，并新增 `name/workArea/salaryRange`。
- 前端请求参数与后端请求参数命名保持兼容，筛选项能透传到岗位分页接口。

## 证据

- 代码核对：`code/develop/yunjikeji/src/services/jobs.ts`
- 代码核对：`code/develop/yunjikeji/src/pages/jobs.vue`
- 代码核对：`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/post/controller/vo/AppPostPageReqVO.java`
- 类型检查：`pnpm type-check`

## 结论

- 已通过
