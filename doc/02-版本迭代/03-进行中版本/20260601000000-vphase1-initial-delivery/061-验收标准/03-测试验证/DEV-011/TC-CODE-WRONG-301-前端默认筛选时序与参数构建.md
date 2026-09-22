# TC-CODE-WRONG-301 前端默认筛选时序与参数构建

## 1. 测试层级

`代码级`

## 2. 对应验收项

- 验收项 ID：`AC-ADMIN-WRONG-301`
- 正式验收入口：`../../01-验收执行详情/AC-ADMIN-WRONG-301.md`

## 3. 前置条件

- 环境前置：前端源码与 Python 运行环境可用
- 账号前置：无
- 数据前置：以静态源码契约核对时序与参数构建

## 4. 测试数据

```json
{
  "expectedOrder": [
    "resetDynamicQuery before handleQuery",
    "resetDynamicQuery before first getList"
  ],
  "expectedBuildParamsGuard": "value !== undefined && value !== null && value !== ''"
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 执行 `python verify_wrong_question_default_filter.py` | 结构化结果为 `PASS` |
| 2 | 核对 `resetQuery` | `resetDynamicQuery()` 在 `handleQuery()` 前执行 |
| 3 | 核对资源监听与 `buildParams` | 首次加载前重置默认值，且 `false` 不会被空值过滤 |

## 6. 期望结果

- 首次进入、资源切换和点击重置都会先恢复默认查询态，再触发加载
- `false` 是有效参数，不会在前端构造请求时被误删

## 7. 脚本入口

- 自动化脚本：`verify_wrong_question_default_filter.py`
- 依赖命令：`python verify_wrong_question_default_filter.py`
- 结果输出位置：`command-results.md`

## 8. 失败判定

- `resetDynamicQuery()` 顺序落后于 `handleQuery()` 或 `getList()`
- `buildParams` 把 `false` 当成空值丢弃
