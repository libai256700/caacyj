# DEV-036 showIntro 二次返工独立重测结论

结论：`DONE`。目标 AC 全部通过，真实账号端到端登录限制单列为环境关注，不计为前端失败。

## 两轮视觉失败关闭

1. 首轮组合退回：分类 heading、提示和白色外壳破坏“应用栏后直接标签”的结构。最终运行态已确认 heading/tip DOM 与文本均为 0，外壳透明、无阴影、零内边距。
2. 第二轮 84/revise：页面 scoped CSS 未穿透共享组件，intro 高约 94.6px、swiper 到卡体间距 108.1px。正式 `showIntro` prop 返工后，新页 intro DOM/text 均为 0，间距缩至 3.83–4.58px；旧页 intro 仍为 1 且可见。

## AC 结果

| AC | 结果 | 证据摘要 |
| --- | --- | --- |
| AC-EXAMASSESS-001 | PASS | Chrome 新页 intro=0、heading/tip=0，应用栏后直接显示分类标签 |
| AC-EXAMASSESS-002 | PASS | 5 分类真实 touch A→B→A；请求 topicId 正确；3 分类边界全部可见 |
| AC-EXAMASSESS-003 | PASS | B 慢响应未覆盖 C，最终为多选题/30题/60分 |
| AC-EXAMASSESS-004 | PASS | 新页分类后 3.83–4.58px 直接衔接卡体；标准/错题动作、防重复、无错题不 POST 均通过 |
| AC-EXAMASSESS-005 | PASS | loading/ready/empty/error 均通过，无硬编码 fallback 分类 |
| AC-EXAMASSESS-101 | PASS | 最新三档视觉 97/100，达到 95 门禁 |
| AC-EXAMASSESS-102 | PASS | Playwright、type-check、build:h5、diff-check 退出码均为 0 |

`AC-EXAMASSESS-201` 的提交与主计划闭环由主代理处理。

## 旧页回归

旧 `pages/practice/start` 的 intro DOM=1，标题与说明文本均可见；共享字段和双按钮完整。

## 边界与服务

- 验收代理仅更新 DEV-036 测试证据，未修改应用、计划、验收定义或 `uni_modules/**`。
- 应用任务白名单仍为五个文件；services、后端、center 的工作区差异为任务前既有差异。
- `5173`、`6379` 保持监听，未停止或重启。
- Chrome 真实接口仍返回业务 401；前端契约使用精准网络测试上下文验证，不冒充真实账号集成通过。
