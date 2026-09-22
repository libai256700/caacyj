# AC-PROFILEBG-001 我的页暖色背景基值

- 类型：业务-交互级
- 业务起点：进入学员或企业我的页。
- 触发动作：观察页面外围与企业内容层背景。
- 业务终点：背景基色使用登录页暖色 `#F5F0EA` 对应 alpha 值。
- 通过条件：仅完成指定七个字面量映射；两个 `180deg`、`0/32/100` 与 `0/34/100` 色标、全部 alpha、`focusAtmosphereUrl`、`center -30rpx / 100% auto no-repeat` 保持。
- 核对方式：源码契约与 Chrome DevTools computed style。
