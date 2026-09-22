# TC-DATA-WRONG-201 默认false落位与其他资源隔离

## 1. 测试层级

`数据级`

## 2. 对应验收项

- 验收项 ID：`AC-ADMIN-WRONG-201`
- 正式验收入口：`../../01-验收执行详情/AC-ADMIN-WRONG-201.md`

## 3. 前置条件

- 环境前置：工作区存在当前前后端源码
- 账号前置：无
- 数据前置：以源码契约结果为准，不伪造数据库运行态

## 4. 测试数据

```json
{
  "resource": "practice-record-detail",
  "expectedDefault": false,
  "expectedIsolation": "queryDefaultValue=false 仅出现在错题管理资源的 is_correct 搜索字段"
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 执行 `python verify_wrong_question_default_filter.py` | 生成 `PASS` 结构化结果 |
| 2 | 核对 `config.ts` 的 `practice-record-detail` | `是否正确` 三态与 `queryDefaultValue: false` 同时存在 |
| 3 | 核对 `queryDefaultValue: false` 的出现范围 | 默认 `false` 不扩散到其他资源页 |

## 6. 期望结果

- 默认错题筛选的配置真实落在错题管理资源字段上
- 其他资源页不被共享默认值污染

## 7. 脚本入口

- 自动化脚本：`verify_wrong_question_default_filter.py`
- 依赖命令：`python verify_wrong_question_default_filter.py`
- 结果输出位置：`command-results.md`

## 8. 失败判定

- `queryDefaultValue: false` 缺失
- 其他资源页也出现同样默认值，导致默认错题筛选扩散
