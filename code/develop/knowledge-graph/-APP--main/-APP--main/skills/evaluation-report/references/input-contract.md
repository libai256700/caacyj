# V3 输入契约

便携契约版本为 `3.1.0`，确定性评分来源版本为 `2026-07-14-v3`，便携规则版本单独记录。新增的授权与报告门禁不会改变现役 V3 的评分、画像、方向和标签计算。

## 核心字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `evalVersion` | number | 固定为 `3`。字符串 `"3"` 不接受。 |
| `likert` | object | 必须包含 `a1` 至 `e2` 共 10 项，每项为 1-5 的整数。 |
| `reportGoals` | string[] | 从 `A`-`H` 选择，最多 3 项。 |
| `truthConfirm` | string | 固定为 `是`；选择或提交 `否` 时拒绝正式生成。 |
| `consent` | string | 发布授权：`同意` 为公开，`不同意` 为私有；缺失或异常会拒绝生成。 |
| `processingConsent` | string | 数据处理授权，固定为 `同意`；缺失时不得准备提示词或调用第三方 LLM。 |

五个维度分别为：`a1/a2` 行业认知、`b1/b2` 职业动机、`c1/c2` 自我效能、`d1/d2` 学习准备度、`e1/e2` 现实推进可行性。

## 基础画像

- `identity`: 身份。
- `backgroundFields`: 背景领域数组，最多 2 项。
- `droneExposure`: 必须使用以下规范值之一：
  - `完全没有接触，只想先了解`
  - `操作过消费级无人机或参加过体验活动`
  - `有过自学或少量实操，但未参加系统培训`
  - `参加过系统培训或已持有相关证照，但尚未正式从业`
  - `已有稳定项目或相关从业经验`
- `caacAwareness`: `完全不了解`、`听说过但不清楚`、`比较了解` 或 `非常了解`。
- `equipmentAccess`: `没有`、`可以借用或偶尔接触` 或 `有可稳定使用的设备`。
- `concerns`: 主要顾虑数组，最多 3 项。
- `truthConfirm`: 真实性确认，只接受 `是`。
- `nickname`、`contact`、`extraNote`: 可选文本。核心不会把 `contact` 放入 LLM 提示词。

## 报告目标

| ID | 目标 | 对应模块 |
|---|---|---|
| `A` | 细分方向匹配 | `moduleA` |
| `B` | 学习、实操、考证与培训路径 | `moduleB` |
| `C` | 就业与转行准备 | `moduleC` |
| `D` | 副业、自由接单与创业可行性 | `moduleD` |
| `E` | 本地学习与项目资源 | `moduleE` |
| `F` | 合规飞行与安全注意事项 | 无附加输入 |
| `G` | 未来 30-90 天行动计划 | 无附加输入 |
| `H` | 其他诉求 | `reportGoalsOther` |

`moduleA` 包含 `directions`、`capabilities` 和 `workFeatures`；`moduleB` 包含 `purpose`、`mode`、`weeklyTime`、`period` 和 `budget`；`moduleC` 包含 `careerMode`、`priorities`、`gaps` 和 `mobility`；`moduleD` 包含 `forms`、`portfolio`、`investment` 和 `barriers`；`moduleE` 包含 `city`、`resourceTypes` 和 `geoScope`。

当前 V3 规则依赖中文选项的精确文本。全部规范值见 JSON Schema，并由核心导出的 `FORM_OPTIONS_V3` 提供。宿主 UI 可以翻译显示文案，但提交前必须映射回这些规范值；翻译文本会被拒绝，不能直接作为协议值。

为控制提示词、内存和 LLM 成本，Schema 与运行时同步限制数组数量和文本长度：`extraNote` 最多 2000 字符，昵称最多 80 字符，联系方式最多 200 字符，“其他”补充最多 200-500 字符。CLI 输入总大小上限为 1,000,000 字节，单份 LLM HTML 上限为 200,000 字符。

结构化评分字段保留一位小数；提示词和仪表盘把这些值四舍五入为整数展示。宿主做计算、比较或审计时必须使用 `bundle.scores`，不要从展示文案反向解析数值。

## 现役规则兼容行为

- 为保持 `sourceRulesetVersion=2026-07-14-v3` 的确定性标签一致，顾虑项中的「其他」及 `concernsOther` 不生成新的顾虑标签。
- `moduleC.careerMode` 的规范值「先实习/兼职积累经验」在 `bundle.career.careerMode` 中保留原文，不归一为新标签。
