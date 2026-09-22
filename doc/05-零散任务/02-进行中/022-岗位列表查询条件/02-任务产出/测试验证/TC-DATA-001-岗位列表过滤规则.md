# TC-DATA-001 岗位列表过滤规则

## 对应验收项

- `TA-T0022-DATA-001`

## 验证目标

- `name`、`workArea`、`salaryRange` 按 AND 组合过滤。
- 工资区间按闭区间交集判断，支持纯数字、`K/k`、`万`、`元/月`、共享单位写法，边界相等命中。
- 无法解析的工资文本在选择工资筛选时排除。
- 地域匹配覆盖 `湖北省 -> 武汉市洪山区` 与 `陕西省 -> 西安`。

## 证据

- 代码核对：`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/post/service/PostFilterSupport.java`
- 单测结果：`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/test/java/com/huiyitech/app/post/service/FrontPostServiceImplTest.java`
- Maven 结果：`mvn -pl yunjikeji-admin-server -Dtest=FrontPostServiceImplTest -DfailIfNoTests=false test`

## 结论

- 已通过
